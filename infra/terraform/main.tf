data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  raw_prefix  = "${trim(var.raw_prefix, "/")}/"

  bronze_database_name  = "bronze"
  silver_database_name  = "silver"
  gold_database_name = "gold"
  carga_function_arn = "arn:${data.aws_partition.current.partition}:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.name_prefix}-carga"
  state_machine_arn  = "arn:${data.aws_partition.current.partition}:states:${var.aws_region}:${data.aws_caller_identity.current.account_id}:stateMachine:${local.name_prefix}-pipeline"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    },
    var.tags
  )
}

# -----------------------------------------------------------------------------
# S3: un solo bucket, recurso s3_bucket_carga_data, region us-east-2
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "s3_bucket_carga_data" {
  bucket        = var.s3_bucket_carga_data_name
  force_destroy = var.force_destroy_buckets
}

resource "aws_s3_bucket_public_access_block" "s3_bucket_carga_data" {
  bucket = aws_s3_bucket.s3_bucket_carga_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "s3_bucket_carga_data" {
  bucket = aws_s3_bucket.s3_bucket_carga_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "s3_bucket_carga_data" {
  bucket = aws_s3_bucket.s3_bucket_carga_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "s3_bucket_carga_data" {
  bucket = aws_s3_bucket.s3_bucket_carga_data.id

  depends_on = [aws_s3_bucket_versioning.s3_bucket_carga_data]

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

data "aws_iam_policy_document" "s3_bucket_carga_data" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.s3_bucket_carga_data.arn,
      "${aws_s3_bucket.s3_bucket_carga_data.arn}/*"
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "s3_bucket_carga_data" {
  bucket = aws_s3_bucket.s3_bucket_carga_data.id
  policy = data.aws_iam_policy_document.s3_bucket_carga_data.json
}

resource "aws_s3_object" "glue_scripts" {
  for_each = {
    bronze = "${path.module}/../../01-pyspark-pipeline/bronze_job.py"
  }

  bucket                 = aws_s3_bucket.s3_bucket_carga_data.id
  key                    = "glue-scripts/${each.key}.py"
  source                 = each.value
  etag                   = filemd5(each.value)
  server_side_encryption = "AES256"
  content_type           = "text/x-python"
}

data "archive_file" "reconciliation_library" {
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/reconciliation-library.zip"
}

resource "aws_s3_object" "reconciliation_library" {
  bucket                 = aws_s3_bucket.s3_bucket_carga_data.id
  key                    = "libraries/reconciliation-library.zip"
  source                 = data.archive_file.reconciliation_library.output_path
  etag                   = data.archive_file.reconciliation_library.output_md5
  server_side_encryption = "AES256"
}

resource "aws_s3_object" "reconciliation_rules" {
  bucket                 = aws_s3_bucket.s3_bucket_carga_data.id
  key                    = "config/reconciliation_rules.yml"
  source                 = "${path.module}/../../config/reconciliation_rules.yml"
  etag                   = filemd5("${path.module}/../../config/reconciliation_rules.yml")
  server_side_encryption = "AES256"
}

data "archive_file" "dbt_project" {
  type        = "zip"
  source_dir  = "${path.module}/../../02-dbt-transformations"
  output_path = "${path.module}/dbt-project.zip"
}

resource "aws_s3_object" "dbt_project" {
  bucket                 = aws_s3_bucket.s3_bucket_carga_data.id
  key                    = "codebuild/dbt-project.zip"
  source                 = data.archive_file.dbt_project.output_path
  etag                   = data.archive_file.dbt_project.output_md5
  server_side_encryption = "AES256"
}

resource "aws_s3_object" "demo_sales" {
  bucket                 = aws_s3_bucket.s3_bucket_carga_data.id
  key                    = "${local.raw_prefix}ventas.csv"
  source                 = "${path.module}/../../demo/data/ventas.csv"
  etag                   = filemd5("${path.module}/../../demo/data/ventas.csv")
  server_side_encryption = "AES256"
}

# -----------------------------------------------------------------------------
# Glue Data Catalog y jobs
# -----------------------------------------------------------------------------

resource "aws_glue_catalog_database" "bronze" {
  name        = local.bronze_database_name
  description = "Catálogo de datos normalizados por el job bronze."
}

resource "aws_glue_catalog_database" "silver" {
  name        = local.silver_database_name
  description = "Capa silver generada por dbt."
}

resource "aws_glue_catalog_database" "gold" {
  name        = local.gold_database_name
  description = "Capa gold generada por dbt."
}

resource "aws_dynamodb_table" "control" {
  name         = "${local.name_prefix}-control"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"
  range_key    = "sk"

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "entity_key"
    type = "S"
  }

  attribute {
    name = "measured_at"
    type = "S"
  }

  global_secondary_index {
    name            = "by_entity"
    hash_key        = "entity_key"
    range_key       = "measured_at"
    projection_type = "ALL"
  }
}

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${local.name_prefix}-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
}

data "aws_iam_policy_document" "glue" {
  statement {
    sid       = "ReadJobScripts"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.s3_bucket_carga_data.arn}/*"]
  }

  statement {
    sid       = "ListBuckets"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.s3_bucket_carga_data.arn, aws_s3_bucket.s3_bucket_carga_data.arn]
  }

  statement {
    sid = "ReadWritePipelineData"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListMultipartUploadParts",
      "s3:PutObject"
    ]
    resources = ["${aws_s3_bucket.s3_bucket_carga_data.arn}/*"]
  }

  statement {
    sid = "GlueCatalog"
    actions = [
      "glue:BatchCreatePartition",
      "glue:BatchDeletePartition",
      "glue:BatchGetPartition",
      "glue:CreateDatabase",
      "glue:CreatePartition",
      "glue:CreateTable",
      "glue:DeletePartition",
      "glue:DeleteTable",
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdatePartition",
      "glue:UpdateTable"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/default",
      aws_glue_catalog_database.bronze.arn,
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/default/*",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.bronze.name}/*",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.silver.name}/*",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.gold.name}/*"
    ]
  }

  statement {
    sid = "ReconciliationRecords"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query"
    ]
    resources = [
      aws_dynamodb_table.control.arn,
      "${aws_dynamodb_table.control.arn}/index/*"
    ]
  }

  statement {
    sid = "WriteLogs"
    actions = [
      "logs:AssociateKmsKey",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"]
  }
}

resource "aws_iam_role_policy" "glue" {
  name   = "${local.name_prefix}-glue"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue.json
}

resource "aws_glue_job" "bronze" {
  name              = "${local.name_prefix}-bronze"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_object.glue_scripts["bronze"].bucket}/${aws_s3_object.glue_scripts["bronze"].key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-observability-metrics"     = "true"
    "--datalake-formats"                  = "iceberg"
    "--additional-python-modules"         = "PyYAML==6.0.2"
    "--extra-py-files"                    = "s3://${aws_s3_object.reconciliation_library.bucket}/${aws_s3_object.reconciliation_library.key}"
    "--conf"                              = "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions --conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.glue_catalog.warehouse=s3://${aws_s3_bucket.s3_bucket_carga_data.id}/warehouse/ --conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog --conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO"
    "--PIPELINE"                          = "ventas"
    "--TARGET_TABLE"                      = "glue_catalog.${aws_glue_catalog_database.bronze.name}.ventas"
    "--RULES_URI"                         = "s3://${aws_s3_object.reconciliation_rules.bucket}/${aws_s3_object.reconciliation_rules.key}"
    "--CONTROL_TABLE"                     = aws_dynamodb_table.control.name
  }

  execution_property {
    max_concurrent_runs = 1
  }
}

# -----------------------------------------------------------------------------
# CodeBuild para dbt
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "codebuild_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${local.name_prefix}-codebuild"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume_role.json
}

data "aws_iam_policy_document" "codebuild" {
  statement {
    sid = "BuildLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${local.name_prefix}-dbt*"]
  }

  statement {
    sid       = "ListDataBucket"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [aws_s3_bucket.s3_bucket_carga_data.arn]
  }

  statement {
    sid = "ReadWriteData"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListMultipartUploadParts",
      "s3:PutObject"
    ]
    resources = ["${aws_s3_bucket.s3_bucket_carga_data.arn}/*"]
  }

  statement {
    sid = "ReconciliationRecords"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query"
    ]
    resources = [
      aws_dynamodb_table.control.arn,
      "${aws_dynamodb_table.control.arn}/index/*"
    ]
  }

  statement {
    sid = "GlueCatalogForDbt"
    actions = [
      "glue:BatchCreatePartition",
      "glue:BatchDeletePartition",
      "glue:BatchGetPartition",
      "glue:CreateDatabase",
      "glue:CreatePartition",
      "glue:CreateTable",
      "glue:DeletePartition",
      "glue:DeleteTable",
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdatePartition",
      "glue:UpdateTable"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/default",
      aws_glue_catalog_database.bronze.arn,
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/default/*",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.bronze.name}/*",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.silver.name}/*",
      "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.gold.name}/*"
    ]
  }

  statement {
    sid = "GlueInteractiveSessions"
    actions = [
      "glue:CreateSession",
      "glue:GetSession",
      "glue:ListSessions",
      "glue:RunStatement",
      "glue:GetStatement",
      "glue:CancelStatement",
      "glue:StopSession",
      "glue:DeleteSession"
    ]
    resources = ["*"]
  }

  statement {
    sid       = "PassGlueRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.glue.arn]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "${local.name_prefix}-codebuild"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild.json
}

resource "aws_codebuild_project" "dbt" {
  name          = "${local.name_prefix}-dbt"
  description   = "02-dbt-transformations. Silver, validación, Gold y validación en una sola ejecución."
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 60

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = var.codebuild_compute_type
    image                       = var.codebuild_image
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "AWS_REGION"
      value = var.aws_region
    }

    environment_variable {
      name  = "DBT_PROJECT_DIR"
      value = "."
    }

    environment_variable {
      name  = "DATA_BUCKET"
      value = aws_s3_bucket.s3_bucket_carga_data.id
    }

    environment_variable {
      name  = "DBT_BRONZE_DATABASE"
      value = aws_glue_catalog_database.bronze.name
    }

    environment_variable {
      name  = "DBT_BRONZE_TABLE"
      value = "ventas"
    }

    environment_variable {
      name  = "DBT_SILVER_DATABASE"
      value = aws_glue_catalog_database.silver.name
    }

    environment_variable {
      name  = "DBT_GLUE_DATABASE"
      value = aws_glue_catalog_database.silver.name
    }

    environment_variable {
      name  = "DBT_GLUE_LOCATION"
      value = "s3://${aws_s3_bucket.s3_bucket_carga_data.id}/warehouse/"
    }

    environment_variable {
      name  = "DBT_GLUE_ROLE_ARN"
      value = aws_iam_role.glue.arn
    }

    environment_variable {
      name  = "CONTROL_TABLE"
      value = aws_dynamodb_table.control.name
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "/aws/codebuild/${local.name_prefix}-dbt"
      stream_name = "build"
    }
  }

  source {
    type      = "S3"
    location  = "${aws_s3_object.dbt_project.bucket}/${aws_s3_object.dbt_project.key}"
    buildspec = "buildspec.yml"
  }
}

# -----------------------------------------------------------------------------
# Notificaciones y orquestación
# -----------------------------------------------------------------------------

resource "aws_sns_topic" "pipeline" {
  name = "${local.name_prefix}-pipeline-events"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.notification_email == null ? 0 : 1

  topic_arn = aws_sns_topic.pipeline.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

data "aws_iam_policy_document" "step_functions_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "${local.name_prefix}-sfn"
  assume_role_policy = data.aws_iam_policy_document.step_functions_assume_role.json
}

data "aws_iam_policy_document" "step_functions" {
  statement {
    sid = "RunGlueJobs"
    actions = [
      "glue:BatchStopJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:StartJobRun"
    ]
    resources = [aws_glue_job.bronze.arn]
  }

  statement {
    sid = "RunCodeBuild"
    actions = [
      "codebuild:BatchGetBuilds",
      "codebuild:StartBuild",
      "codebuild:StopBuild"
    ]
    resources = [aws_codebuild_project.dbt.arn]
  }

  statement {
    sid       = "NotifyByEmail"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.carga_function_arn]
  }

  statement {
    sid = "ManageSyncRules"
    actions = [
      "events:DescribeRule",
      "events:PutRule",
      "events:PutTargets"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForGlueJobRule",
      "arn:${data.aws_partition.current.partition}:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventForCodeBuildStartBuildRule"
    ]
  }
}

resource "aws_iam_role_policy" "step_functions" {
  name   = "${local.name_prefix}-sfn"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.step_functions.json
}

resource "aws_sfn_state_machine" "reconciliation" {
  name     = "${local.name_prefix}-pipeline"
  role_arn = aws_iam_role.step_functions.arn
  type     = "STANDARD"

  depends_on = [aws_iam_role_policy.step_functions]

  definition = jsonencode({
    Comment = "CSV, bronze, DBT silver y gold. Registros en DynamoDB. ${data.archive_file.reconciliation_library.output_md5}"
    StartAt = "InitializeRun"
    States = {
      InitializeRun = {
        Type = "Pass"
        Parameters = {
          "run_id.$" = "States.UUID()"
          "input.$"  = "$"
        }
        Next = "HasLoadDate"
      }
      HasLoadDate = {
        Type = "Choice"
        Choices = [{
          Variable  = "$.input.load_date"
          IsPresent = true
          Next      = "UseProvidedDate"
        }]
        Default = "UseExecutionDate"
      }
      UseProvidedDate = {
        Type = "Pass"
        Parameters = {
          "run_id.$"     = "$.run_id"
          "input_path.$" = "$.input.input_path"
          "load_date.$"  = "$.input.load_date"
        }
        Next = "RunBronze"
      }
      UseExecutionDate = {
        Type = "Pass"
        Parameters = {
          "run_id.$"     = "$.run_id"
          "input_path.$" = "$.input.input_path"
          "load_date.$"  = "States.ArrayGetItem(States.StringSplit($$.Execution.StartTime, 'T'), 0)"
        }
        Next = "RunBronze"
      }
      RunBronze = {
        Type     = "Task"
        Resource = "arn:${data.aws_partition.current.partition}:states:::glue:startJobRun.sync"
        Parameters = {
          JobName = aws_glue_job.bronze.name
          Arguments = {
            "--RUN_ID.$"     = "$.run_id"
            "--INPUT_PATH.$" = "$.input_path"
            "--LOAD_DATE.$"  = "$.load_date"
          }
        }
        ResultPath = "$.bronze"
        Next       = "RunDbt"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "NotifyFailure"
        }]
      }
      RunDbt = {
        Type     = "Task"
        Resource = "arn:${data.aws_partition.current.partition}:states:::codebuild:startBuild.sync"
        Parameters = {
          ProjectName = aws_codebuild_project.dbt.name
          EnvironmentVariablesOverride = [
            {
              Name      = "RUN_ID"
              Type      = "PLAINTEXT"
              "Value.$" = "$.run_id"
            },
            {
              Name      = "LOAD_DATE"
              Type      = "PLAINTEXT"
              "Value.$" = "$.load_date"
            }
          ]
        }
        ResultPath = "$.dbt"
        Next       = "NotifySuccess"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "NotifyFailure"
        }]
      }
      NotifySuccess = {
        Type     = "Task"
        Resource = "arn:${data.aws_partition.current.partition}:states:::lambda:invoke"
        Parameters = {
          FunctionName = local.carga_function_arn
          Payload = {
            outcome      = "PASS"
            "run_id.$"   = "$.run_id"
            "load_date.$" = "$.load_date"
          }
        }
        ResultPath = "$.notice"
        Next       = "PipelineSucceeded"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineSucceeded"
        }]
      }
      NotifyFailure = {
        Type     = "Task"
        Resource = "arn:${data.aws_partition.current.partition}:states:::lambda:invoke"
        Parameters = {
          FunctionName = local.carga_function_arn
          Payload = {
            outcome       = "FAIL"
            "run_id.$"    = "$.run_id"
            "load_date.$" = "$.load_date"
            "cause.$"     = "$.error.Cause"
          }
        }
        ResultPath = "$.notice"
        Next       = "PipelineFailed"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "PipelineFailed"
        }]
      }
      PipelineFailed = {
        Type  = "Fail"
        Error = "ReconciliationPipelineFailed"
        Cause = "Una etapa de la reconciliación falló; se intentó publicar el detalle en SNS."
      }
      PipelineSucceeded = {
        Type = "Succeed"
      }
    }
  })
}

# -----------------------------------------------------------------------------
# Programación opcional con EventBridge
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "eventbridge_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge" {
  count = var.eventbridge_schedule_expression == null ? 0 : 1

  name               = "${local.name_prefix}-events"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume_role.json
}

data "aws_iam_policy_document" "eventbridge" {
  count = var.eventbridge_schedule_expression == null ? 0 : 1

  statement {
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.reconciliation.arn]
  }
}

resource "aws_iam_role_policy" "eventbridge" {
  count = var.eventbridge_schedule_expression == null ? 0 : 1

  name   = "${local.name_prefix}-events"
  role   = aws_iam_role.eventbridge[0].id
  policy = data.aws_iam_policy_document.eventbridge[0].json
}

resource "aws_cloudwatch_event_rule" "schedule" {
  count = var.eventbridge_schedule_expression == null ? 0 : 1

  name                = "${local.name_prefix}-schedule"
  description         = "Inicia periódicamente la reconciliación."
  schedule_expression = var.eventbridge_schedule_expression
}

resource "aws_cloudwatch_event_target" "pipeline" {
  count = var.eventbridge_schedule_expression == null ? 0 : 1

  rule      = aws_cloudwatch_event_rule.schedule[0].name
  target_id = "ReconciliationStateMachine"
  arn       = aws_sfn_state_machine.reconciliation.arn
  role_arn  = aws_iam_role.eventbridge[0].arn
  input = jsonencode({
    trigger    = "eventbridge"
    input_path = "s3://${aws_s3_bucket.s3_bucket_carga_data.id}/${local.raw_prefix}ventas.csv"
  })
}

# -----------------------------------------------------------------------------
# Carga por POST /carga, consumida desde Postman
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "carga_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "carga" {
  name               = "${local.name_prefix}-carga"
  assume_role_policy = data.aws_iam_policy_document.carga_assume_role.json
}

data "aws_iam_policy_document" "carga" {
  statement {
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.name_prefix}-carga:*"]
  }

  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.s3_bucket_carga_data.arn}/${local.raw_prefix}*"]
  }

  statement {
    actions   = ["states:StartExecution"]
    resources = [local.state_machine_arn]
  }

  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.pipeline.arn]
  }

  statement {
    actions   = ["dynamodb:Query"]
    resources = [aws_dynamodb_table.control.arn]
  }
}

resource "aws_iam_role_policy" "carga" {
  name   = "${local.name_prefix}-carga"
  role   = aws_iam_role.carga.id
  policy = data.aws_iam_policy_document.carga.json
}

resource "aws_iam_role_policy_attachment" "carga_logs" {
  role       = aws_iam_role.carga.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "carga" {
  function_name    = "${local.name_prefix}-carga"
  role             = aws_iam_role.carga.arn
  runtime          = "python3.11"
  handler          = "carga.http.handler"
  filename         = data.archive_file.reconciliation_library.output_path
  source_code_hash = data.archive_file.reconciliation_library.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      BUCKET_NAME       = aws_s3_bucket.s3_bucket_carga_data.id
      OBJECT_KEY        = "${local.raw_prefix}ventas.csv"
      STATE_MACHINE_ARN = local.state_machine_arn
      TOPIC_ARN         = aws_sns_topic.pipeline.arn
      CONTROL_TABLE     = aws_dynamodb_table.control.name
    }
  }
}

resource "aws_apigatewayv2_api" "carga" {
  name          = "${local.name_prefix}-carga"
  protocol_type = "HTTP"
  description   = "Recibe el CSV de ventas desde Postman."

  cors_configuration {
    allow_headers = ["content-type", "x-load-date"]
    allow_methods = ["POST", "OPTIONS"]
    allow_origins = ["*"]
  }
}

resource "aws_apigatewayv2_integration" "carga" {
  api_id                 = aws_apigatewayv2_api.carga.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.carga.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "carga" {
  api_id    = aws_apigatewayv2_api.carga.id
  route_key = "POST /carga"
  target    = "integrations/${aws_apigatewayv2_integration.carga.id}"
}

resource "aws_apigatewayv2_stage" "carga" {
  api_id      = aws_apigatewayv2_api.carga.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "carga" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.carga.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.carga.execution_arn}/*/*/carga"
}

resource "aws_lambda_permission" "carga_states" {
  statement_id  = "AllowStepFunctionsInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.carga.function_name
  principal     = "states.amazonaws.com"
  source_arn    = local.state_machine_arn
}
