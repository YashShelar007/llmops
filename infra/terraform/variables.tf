variable "region" {
  type    = string
  default = "us-east-1"
}

variable "function_name" {
  type    = string
  default = "llmops-starter-api"
}

# Default to x86_64 to match your pushed image.
variable "architecture" {
  type    = string
  default = "x86_64"
}

# ECR image URI in the form: <acct>.dkr.ecr.<region>.amazonaws.com/<repo>@sha256:<digest>
variable "image_uri" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 14
}

# -------- OpenAI ----------
variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "openai_model" {
  type    = string
  default = "gpt-4o-mini"
}

variable "openai_max_tokens" {
  type    = number
  default = 300
}

# -------- Langfuse (optional: only injected if all three are non-empty) ----------
variable "langfuse_public_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "langfuse_secret_key" {
  type      = string
  default   = ""
  sensitive = true
}

# Use your project region host, e.g. "https://us.cloud.langfuse.com" or "https://cloud.langfuse.com"
variable "langfuse_host" {
  type    = string
  default = ""
}

# -------- OTEL ----------
variable "otel_service_name" {
  type    = string
  default = "llmops-starter-api"
}

variable "otel_resource_attributes" {
  type    = string
  default = "service.version=0.3.2,deployment.environment=prod"
}

variable "metrics_log" {
  type    = string
  default = "/tmp/metrics.jsonl"
}

variable "ssm_namespace" { 
  type = string 
  default = "/llmops-starter" 
}

# We WON’T read secrets in TF to avoid leaking into state.
variable "env" {
  type = map(string)
  default = {
    OTEL_SERVICE_NAME        = "llmops-starter-api"
    OTEL_RESOURCE_ATTRIBUTES = "service.version=0.3.2,deployment.environment=prod"
    LLM_PROVIDER             = "openai"
    TIMEOUT_SECONDS          = "8"
    MAX_RETRIES              = "2"
    METRICS_LOG              = "/tmp/metrics.jsonl"

    # SSM name hints for runtime fetch in code:
    SSM_OPENAI_API_KEY        = "/llmops-starter/openai_api_key"
    SSM_LANGFUSE_PUBLIC_KEY   = "/llmops-starter/langfuse_public_key"
    SSM_LANGFUSE_SECRET_KEY   = "/llmops-starter/langfuse_secret_key"
    SSM_LANGFUSE_HOST         = "/llmops-starter/langfuse_host"
    SSM_DEMO_API_KEY          = "/llmops-starter/demo_api_key"

    # Optional model/caps (non-secret)
    OPENAI_MODEL              = "gpt-4o-mini"
    OPENAI_MAX_TOKENS         = "300"
    OPENAI_TIMEOUT_S          = "8"
  }
}
