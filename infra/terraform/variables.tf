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

# Your base env map; you can override entirely via -var 'env={...}' if needed.
variable "env" {
  type = map(string)
  default = {
    OTEL_SERVICE_NAME        = "llmops-starter-api"
    OTEL_RESOURCE_ATTRIBUTES = "service.version=0.3.2,deployment.environment=prod"
    LLM_PROVIDER             = "openai"
    TIMEOUT_SECONDS          = "8"
    MAX_RETRIES              = "2"
  }
}
