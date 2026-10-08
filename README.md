# Data Reconciliation & Validation en AWS

Implementación de referencia para impedir que un pipeline bronze → silver → gold termine en
verde cuando no cargó datos o incumplió su contrato de volumen/frescura.

## Proyectos

| Proyecto | Tecnología | Función |
| --- | --- | --- |
| `01-pyspark-pipeline` | Python + PySpark | Extracción y Bronze |
| `02-dbt-transformations` | DBT + SQL | Silver y Gold |
| `src/reconciliation` | Python | Cuadratura reusable de Bronze, Silver y Gold |

El orden en `us-east-2` es CSV, PySpark con validación de Bronze, y un solo CodeBuild que hace DBT Silver, comparación, DBT Gold y comparación. Las ventas quedan en Iceberg. DynamoDB guarda la traza y una copia de cada fila. Si una validación falla, la Lambda envía la alerta a `lion180596@gmail.com` y el pipeline no sigue.

El bucket físico es `s3-bucket-carga-data`. AWS no acepta el guion bajo de
`s3_bucket_carga_data`, así que ese nombre queda como identificador del recurso Terraform.

- `src/reconciliation`: motor reusable compartido por PySpark y la validación final.
- `config`: contratos de reconciliación.
- `infra/terraform`: un bucket, Glue, CodeBuild, Step Functions, SNS e IAM.

La explicación de las decisiones está en [docs/architecture.md](docs/architecture.md).

## Prueba local

Requiere Python 3.10 o superior.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

En PowerShell, la activación es `.venv\Scripts\Activate.ps1` y el `PYTHONPATH` no es necesario
después de instalar el paquete.

## Prerrequisitos AWS

- Terraform 1.6 o superior.
- AWS CLI autenticado con permisos para crear IAM, S3, Glue, CodeBuild, Step Functions,
  SNS.

## Despliegue

```bash
cd infra/terraform
terraform init
terraform apply
```

CodeBuild toma el proyecto DBT del zip que Terraform sube a `s3-bucket-carga-data`.

Un push a `master` en `https://github.com/lion-m-d/Cencosud` vuelve a aplicar Terraform. En IntelliJ eso es **Commit and Push** (`Ctrl+K` y luego push, o marca "Commit and Push"). Un commit que se queda solo en el equipo no despliega.

Después del `apply`:

1. Confirmar la suscripción que SNS envía a `lion180596@gmail.com`. Sin esa confirmación el correo no llega.
2. En Postman, importar `postman/carga-ventas.postman_collection.json`. En **Body** elige **form-data**, tipo **File**, y selecciona `demo/data/ventas.csv`. No escribas `@demo/data/ventas.csv` en el cuerpo: Postman lo envía como texto. Una respuesta `202` incluye `execution_arn`.

El `POST /carga` acepta `text/csv` o JSON con `records`. Sube el archivo a
`s3://s3-bucket-carga-data/raw/` con el mismo nombre. Si ese nombre ya existe, usa
`nombre_1.csv`, `nombre_2.csv` y así en adelante. La fecha sale del header
`X-Load-Date`, del query `load_date` o de `fecha_venta`. La respuesta `202` incluye
`execution_arn` y `file_name`. El correo indica ese nombre y, si hubo registros
rechazados o la validación falló, dice que el archivo falló en los registros.

Ejemplo conceptual de entrada:

```json
{
  "input_path": "s3://BUCKET/raw/ventas.csv",
  "load_date": "2026-10-07",
  "file_name": "ventas.csv"
}
```

Step Functions genera `run_id` en `us-east-2` y lo propaga a Bronze y a CodeBuild. Silver y Gold
corren en la misma ejecución de DBT y reutilizan la sesión de Glue. DBT mide cada capa con SQL
y el motor compara esas métricas con `config/reconciliation_rules.yml`. La ejecución solo llega
a `Succeed` si las tres validaciones pasan.

## Consultar la traza

En DataGrip, agrega un origen DynamoDB en `us-east-2` con el perfil `cencosud` y abre la tabla
`cencosud-reconciliation-dev-control`. La clave de partición es `run_id`.

- `sk` que empieza por `metrics#` es el conteo de una capa.
- `sk` que empieza por `result#` es el veredicto de una regla.

Las tablas de ventas se siguen viendo por Athena: `bronze.ventas`, `silver.ventas` y
`gold.ventas_tienda_dia`.

## Contratos

Editar `config/reconciliation_rules.yml` para incorporar un dataset. El conteo se compara al
grano indicado en `grain`; por ello una agregación gold no necesita ser 1:1 con las filas de
silver. Los controles duros usan `severity: FAIL`; los informativos, `WARN`.

## Limpieza

```bash
cd infra/terraform
terraform destroy
```

Si `force_destroy_buckets` está desactivado, vaciar primero `s3-bucket-carga-data`. No se deben reutilizar
los datos de esta demo como política de retención productiva.
