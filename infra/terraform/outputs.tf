output "lambda_name"  { value = aws_lambda_function.fn.function_name }
output "invoke_arn"   { value = aws_lambda_function.fn.invoke_arn }
output "api_base_url" { value = aws_apigatewayv2_api.http.api_endpoint }
