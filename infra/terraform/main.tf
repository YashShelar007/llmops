provider "aws" { region = var.region }

# Basic logs for Lambda
resource "aws_cloudwatch_log_group" "fn" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

# Allow Lambda to read SSM params (SecureString) encrypted with AWS-managed SSM key
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

# Policy to read only our namespace (least privilege)
data "aws_iam_policy_document" "ssm_access" {
  statement {
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      "arn:${data.aws_partition.current.partition}:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_namespace}/*"
    ]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = ["arn:${data.aws_partition.current.partition}:kms:${var.region}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"]
  }
}

resource "aws_iam_policy" "ssm_access" {
  name   = "${var.function_name}-ssm-access"
  policy = data.aws_iam_policy_document.ssm_access.json
}

resource "aws_iam_role_policy_attachment" "ssm_access" {
  role       = aws_iam_role.fn.name
  policy_arn = aws_iam_policy.ssm_access.arn
}

# --- CloudWatch alarms ---
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.function_name}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  dimensions = { FunctionName = var.function_name }
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration_p95" {
  alarm_name          = "${var.function_name}-duration-p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  extended_statistic  = "p95"
  threshold           = 4000  # 4s p95
  dimensions = { FunctionName = var.function_name }
}


# IAM role for Lambda
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fn" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.fn.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda function from container image (already pushed to ECR)
resource "aws_lambda_function" "fn" {
  function_name = var.function_name
  role          = aws_iam_role.fn.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = [var.architecture]

  # Build the env in layers: base map -> OTEL/OpenAI -> optional Langfuse
  environment {
    variables = merge(
      var.env,
      {
        # OTEL override/control
        OTEL_SERVICE_NAME        = var.otel_service_name
        OTEL_RESOURCE_ATTRIBUTES = var.otel_resource_attributes

        # OpenAI
        OPENAI_API_KEY     = var.openai_api_key
        OPENAI_MODEL       = var.openai_model
        OPENAI_MAX_TOKENS  = tostring(var.openai_max_tokens)

        METRICS_LOG        = var.metrics_log
      },
      var.langfuse_public_key != "" && var.langfuse_secret_key != "" && var.langfuse_host != "" ? {
        LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
        LANGFUSE_SECRET_KEY = var.langfuse_secret_key
        LANGFUSE_HOST       = var.langfuse_host
      } : {}
    )
  }

  timeout     = 15
  memory_size = 1024
  depends_on  = [aws_cloudwatch_log_group.fn]
}

# HTTP API Gateway -> Lambda
resource "aws_apigatewayv2_api" "http" {
  name          = "${var.function_name}-http"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fn.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 10000
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
