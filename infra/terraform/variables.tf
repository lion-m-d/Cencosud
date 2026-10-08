variable "aws_region" {
  description = "Región AWS donde se desplegará la solución. Ohio."
  type        = string
  default     = "us-east-2"

  validation {
    condition     = var.aws_region == "us-east-2"
    error_message = "La solución se despliega en us-east-2 (Ohio)."
  }
}

variable "project_name" {
  description = "Nombre corto usado para nombrar recursos."
  type        = string
  default     = "cencosud-reconciliation"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.project_name))
    error_message = "project_name debe tener entre 3 y 31 caracteres: minúsculas, números y guiones."
  }
}

variable "environment" {
  description = "Ambiente de despliegue."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "qa", "staging", "prod"], var.environment)
    error_message = "environment debe ser dev, qa, staging o prod."
  }
}

variable "tags" {
  description = "Etiquetas adicionales para todos los recursos compatibles."
  type        = map(string)
  default     = {}
}

variable "force_destroy_buckets" {
  description = "Permite borrar buckets con objetos. Recomendado sólo en desarrollo."
  type        = bool
  default     = false
}

variable "glue_version" {
  description = "Versión del runtime de AWS Glue."
  type        = string
  default     = "4.0"
}

variable "glue_worker_type" {
  description = "Tipo de worker para los jobs Glue."
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Cantidad de workers para cada job Glue."
  type        = number
  default     = 2

  validation {
    condition     = var.glue_number_of_workers >= 2
    error_message = "Glue requiere al menos 2 workers para jobs Spark."
  }
}

variable "glue_job_timeout_minutes" {
  description = "Timeout de jobs Glue en minutos."
  type        = number
  default     = 60
}

variable "codebuild_compute_type" {
  description = "Capacidad de cómputo de CodeBuild."
  type        = string
  default     = "BUILD_GENERAL1_SMALL"
}

variable "codebuild_image" {
  description = "Imagen administrada usada para ejecutar dbt."
  type        = string
  default     = "aws/codebuild/standard:7.0"
}

variable "notification_email" {
  description = "Correo que recibe la alerta SNS cuando el pipeline falla. Hay que confirmar la suscripción."
  type        = string
  default     = "lion180596@gmail.com"
  nullable    = true
}

variable "s3_bucket_carga_data_name" {
  description = "Nombre físico del bucket. AWS rechaza guiones bajos, por eso el recurso s3_bucket_carga_data usa guiones."
  type        = string
  default     = "s3-bucket-carga-data"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.s3_bucket_carga_data_name))
    error_message = "El nombre S3 solo puede usar minúsculas, números, puntos y guiones."
  }
}

variable "raw_prefix" {
  description = "Prefijo de entrada de archivos crudos dentro de s3_bucket_carga_data."
  type        = string
  default     = "raw/"
}
