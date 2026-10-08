# Arquitectura de Data Reconciliation & Validation

## Capas

El código Python sigue SOLID y separa dos contextos:

- `carga`: recibe el archivo, lo guarda y arranca la orquestación.
- `reconciliation`: compara capas y emite el veredicto.

Dentro de cada contexto la dependencia apunta hacia el dominio.

```text
interfaces        bronze_job, validate_cli, carga.http
      │
      ▼
application       AcceptLoad, ValidateRun, evaluate
      │
      ▼
ports             RuleSource, MetricsReader, ObjectStore, PipelineRunner
      ▲
      │
adapters          YAML, Spark/Iceberg, DynamoDB, S3, Step Functions
```

- Una clase tiene una responsabilidad: un control no persiste, un adaptador no decide el veredicto.
- Un control nuevo se agrega como estrategia. `evaluate` no se reescribe.
- Los controles comparten el mismo contrato y se pueden sustituir entre sí.
- Los puertos son pequeños: validar no conoce cómo guardar un archivo.
- Los casos de uso reciben sus dependencias. AWS y Spark se componen solo en el borde.

## Decisión

La cuadratura se implementa como una capacidad compartida: contratos YAML y un motor Python
independiente de Spark. Las ventas quedan en Iceberg. La traza de cada ejecución queda en
DynamoDB. Cada pipeline declara sus reglas; no vuelve a implementar el algoritmo.

El identificador `run_id` lo genera Step Functions y se propaga a Glue y CodeBuild/dbt. Así se
pueden unir las métricas de todas las capas aunque los motores sean distintos.

## Flujo

Todo el despliegue queda fijo en `us-east-2`. Hay un solo bucket, `s3-bucket-carga-data`,
referenciado en Terraform como `s3_bucket_carga_data`.

1. Postman hace `POST /carga`. La Lambda `carga` guarda el CSV y arranca Step Functions.
2. `01-pyspark-pipeline` escribe `bronze.ventas`, mide esa capa y valida Bronze. El registro queda en DynamoDB.
3. `02-dbt-transformations` construye Silver, mide la capa en SQL y el motor compara Bronze contra Silver. Después construye Gold y compara Silver contra Gold. Los veredictos quedan en la misma tabla DynamoDB.
4. La misma Lambda publica el correo. `PASS` lista los pasos validados. `FAIL` indica que la carga no concuerda, o el fallo de la etapa, en `lion180596@gmail.com`.

## Semántica de reglas

- `min_rows` impide éxitos vacíos.
- `min_ratio` y `max_ratio` comparan cantidades en el grano de negocio, no necesariamente filas
  físicas. Esto admite filtros y agregaciones legítimas.
- `max_drop_pct` compara contra la última referencia disponible cuando se informa
  `previous_count`.
- `load_date_column` activa el control de frescura contra la fecha de negocio de la ejecución.
- `severity: WARN` conserva la evidencia sin bloquear; `FAIL` bloquea el pipeline.

No se utiliza hash fila a fila en esta versión. Es costoso para tablas grandes y no reemplaza
controles específicos de calidad. Los tests DBT cubren claves, nulos y relaciones en el punto
donde el modelo conoce esas restricciones.

## Persistencia y operación

Las ventas quedan en Iceberg. Las métricas y los veredictos son pocos registros por ejecución
y se guardan en DynamoDB, con clave `run_id`. Los logs de CloudWatch ayudan al diagnóstico,
pero no son la fuente de auditoría.

Los umbrales se versionan junto al código. Un cambio debe pasar pruebas y despliegue; esto evita
que una edición manual silenciosa cambie el significado histórico de una ejecución.

## Seguridad y límites

- Buckets bloquean acceso público y cifran objetos.
- Glue, CodeBuild y Step Functions usan roles separados.
- El correo SNS requiere confirmar la suscripción después del despliegue.
- Para producción se recomienda KMS administrado por cliente, Lake Formation, VPC endpoints,
  alarmas de ausencia de ejecución y expiración de snapshots Iceberg.
- Los conteos exactos recorren datos. En tablas grandes se puede sustituir su captura por
  estadísticas de snapshots, manteniendo el mismo contrato y esquema de resultados.
