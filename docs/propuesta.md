# Propuesta: Data Reconciliation & Validation

Demo en `us-east-2` con datos de prueba. La ejecución `62ab7a75-6846-4869-84cf-06ae96e94650`
(`load_date` 2026-10-07) terminó en `PipelineSucceeded` y el correo dijo VALIDADO en Bronze,
Silver y Gold. Cuando la cuadratura no pasa, Step Functions marca `PipelineFailed` y envía el
correo de no concordancia. Las ventas viven en Iceberg. DynamoDB guarda la traza y una copia de cada fila.

## Qué se compara y cómo

Se compara cantidad, no el contenido fila a fila. Un hash de cada registro sería caro y no
responde la pregunta del ejercicio: si la capa cargó y si lo que salió es coherente con lo que
entró.

Cada regla declara el grano de negocio. El conteo aceptable se mide en ese grano, no en filas
físicas.

| Tramo | Grano | Aceptable |
| --- | --- | --- |
| Bronze | `ticket_id` | Al menos 1 fila. La fecha de carga coincide con la de la ejecución. |
| Bronze → Silver | `ticket_id` | Silver conserva entre el 95 % y el 100 % de los tickets. Puede filtrar nulos; no puede perder más de ese margen. |
| Silver → Gold | `tienda_id` + `fecha_venta` | Gold conserva entre el 98 % y el 102 % de esas combinaciones. Agrupar 22 tickets en 6 tiendas es válido: no se exige 1:1. |

Además, si ya existe una carga anterior, ninguna capa puede caer más del 30 % sin fallar. Así
una carga “muchos menos de lo esperado” no termina en verde. Los tests DBT (`not_null`,
`unique`) cubren claves y nulos del modelo; no reemplazan la cuadratura entre capas.

Los umbrales viven en `config/reconciliation_rules.yml`.

## Dónde vive la lógica

Es una librería, `src/reconciliation`, no un servicio aparte y no código copiado dentro de
cada job.

PySpark y DBT son motores distintos. Un servicio HTTP obligaría a los dos a hablar con otro
proceso solo para comparar tres números. La librería se importa en el borde de cada motor, el
algoritmo está una sola vez (`ValidateRun` y los controles de `domain/checks.py`) y un pipeline
nuevo agrega una regla YAML sin reescribir la comparación.

## Cómo se integra en cada tramo

Bronze corre en un Glue job PySpark. Después de escribir `bronze.ventas` en Iceberg, el mismo
job llama a `ValidateRun` con la etapa `bronze`. Si no pasa, el job falla y Step Functions no
sigue.

Silver y Gold corren con DBT sobre el conector de Glue, en un solo CodeBuild. DBT construye la
tabla y, al terminar el modelo, mide en SQL cuántas filas y cuántos valores del grano salieron.
Esa medición no decide el veredicto. El paso siguiente, posterior al `dbt run`, importa la
misma librería y compara. Silver se valida antes de construir Gold. No hay una segunda copia
de las reglas en SQL.

## Qué pasa cuando falla

Pasan las dos cosas. La ejecución queda `FAILED` (`PipelineFailed`) y se envía una alerta.

El canal es correo, por SNS, a `lion180596@gmail.com`. Lo arma la misma Lambda que recibió el
archivo. El mensaje dice VALIDADO y lista Bronze, Silver y Gold, o dice que la carga no
concuerda e indica el paso que falló. Quien opera la carga es quien debe enterarse antes de
que una capa vacía se tome por buena.

## Dónde queda la traza

No queda solo en el log. Cada ejecución escribe en DynamoDB, tabla
`cencosud-reconciliation-dev-control`, con clave `run_id`.

- `metrics#...` guarda cuántos registros entraron y salieron de la capa, el conteo del grano,
  la fecha de carga y la comparación con la ejecución anterior.
- `result#...` guarda el veredicto, el ratio y el control que falló.

Se consulta después por `run_id`. Las tablas de negocio siguen en Iceberg y se leen con
Athena: `bronze.ventas`, `silver.ventas`, `gold.ventas_tienda_dia`.
