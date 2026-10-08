{{ config(partition_by=['fecha_venta']) }}

select
    cast(ticket_id as string) as ticket_id,
    cast(tienda_id as string) as tienda_id,
    cast(fecha_venta as date) as fecha_venta,
    cast(monto as decimal(18, 2)) as monto,
    cast(fecha_carga as date) as fecha_carga,
    cast(_run_id as string) as run_id,
    current_timestamp() as processed_at
from {{ source('bronze', 'ventas') }}
where _run_id = '{{ var("run_id") | replace("'", "''") }}'
  and nullif(trim(cast(ticket_id as string)), '') is not null
  and nullif(trim(cast(monto as string)), '') is not null
