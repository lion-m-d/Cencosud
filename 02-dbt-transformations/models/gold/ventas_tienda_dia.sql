{{ config(partition_by=['fecha_venta']) }}

select
    tienda_id,
    fecha_venta,
    count(*) as tickets,
    sum(monto) as monto_total,
    max(fecha_carga) as fecha_carga,
    run_id,
    current_timestamp() as summarized_at
from {{ ref('ventas') }}
where run_id = '{{ var("run_id") | replace("'", "''") }}'
group by tienda_id, fecha_venta, run_id
