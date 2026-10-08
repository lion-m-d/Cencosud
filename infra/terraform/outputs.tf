output "s3_bucket_carga_data" {
  description = "Bucket único de carga, warehouse Iceberg, scripts y resultados Athena."
  value       = aws_s3_bucket.s3_bucket_carga_data.id
}

output "aws_region" {
  description = "Región de despliegue."
  value       = var.aws_region
}

output "layer_database_names" {
  description = "Bases de datos Glue de las capas de ventas."
  value = {
    bronze = aws_glue_catalog_database.bronze.name
    silver = aws_glue_catalog_database.silver.name
    gold   = aws_glue_catalog_database.gold.name
  }
}

output "control_table_name" {
  description = "Tabla DynamoDB con métricas y veredictos de cada ejecución."
  value       = aws_dynamodb_table.control.name
}

output "projects" {
  description = "Los tres proyectos y el orden en que los llama Step Functions."
  value = {
    pyspark_pipeline    = aws_glue_job.bronze.name
    dbt_transformations = aws_codebuild_project.dbt.name
    validation_engine   = "bronze en Glue y silver/gold en el build DBT; registros en DynamoDB"
  }
}

output "state_machine_arn" {
  description = "ARN de la máquina de estados que encadena los tres módulos."
  value       = aws_sfn_state_machine.reconciliation.arn
}

output "notification_topic_arn" {
  description = "Tópico SNS de fallos del pipeline."
  value       = aws_sns_topic.pipeline.arn
}

output "eventbridge_rule_arn" {
  description = "ARN de la regla programada, si fue habilitada."
  value       = try(aws_cloudwatch_event_rule.schedule[0].arn, null)
}

output "carga_endpoint" {
  description = "POST de Postman que carga el CSV y arranca el pipeline."
  value       = "${aws_apigatewayv2_api.carga.api_endpoint}/carga"
}

output "sample_execution_input" {
  description = "Plantilla de entrada para iniciar Step Functions."
  value = {
    input_path = "s3://${aws_s3_bucket.s3_bucket_carga_data.id}/${local.raw_prefix}ventas.csv"
    load_date  = "2026-10-07"
  }
}
