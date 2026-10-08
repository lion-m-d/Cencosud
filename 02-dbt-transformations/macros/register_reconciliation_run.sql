{% macro log_metrics(payload) %}
    {% do log("RECON_METRICS " ~ (payload | tojson), info=True) %}
{% endmacro %}

{% macro metric_row(table_name, sql) %}
    {% set table = run_query(sql) %}
    {% if table is none or (table.rows | length) == 0 %}
        {{ exceptions.raise_compiler_error("DBT no devolvio metricas de " ~ table_name) }}
    {% endif %}
    {{ return(table.rows[0]) }}
{% endmacro %}

{% macro register_reconciliation_run(results) %}
    -- depends_on: {{ ref('ventas') }}
    -- depends_on: {{ source('bronze', 'ventas') }}
    {% if execute %}
        {% set run_id = env_var('RUN_ID', invocation_id) | replace("'", "''") %}
        {% for result in results if result.node.resource_type == 'model' and result.status == 'success' %}
            {% if result.node.name == 'ventas' %}
                {% set metrics_sql %}
                    select
                        count(*) as output_count,
                        count(distinct cast(ticket_id as string)) as tickets,
                        count(distinct concat_ws('||', cast(tienda_id as string), cast(fecha_venta as string))) as tienda_dia,
                        cast(max(fecha_carga) as string) as max_load_date,
                        (select count(*) from {{ source('bronze', 'ventas') }}
                         where _run_id = '{{ run_id }}') as input_count
                    from {{ result.node.relation_name }}
                    where run_id = '{{ run_id }}'
                {% endset %}
                {% set row = metric_row('silver.ventas', metrics_sql) %}
                {% do log_metrics({
                    "run_id": env_var("RUN_ID", invocation_id),
                    "pipeline": "ventas",
                    "layer": "silver",
                    "table_name": "silver.ventas",
                    "output_count": row[0],
                    "grain_count": row[1],
                    "grain_counts": {"ticket_id": row[1], "tienda_id|fecha_venta": row[2]},
                    "max_load_date": row[3],
                    "input_count": row[4]
                }) %}
            {% elif result.node.name == 'ventas_tienda_dia' %}
                {% set metrics_sql %}
                    select
                        count(*) as output_count,
                        count(distinct concat_ws('||', cast(tienda_id as string), cast(fecha_venta as string))) as tienda_dia,
                        cast(max(fecha_carga) as string) as max_load_date,
                        (select count(*) from {{ ref('ventas') }} where run_id = '{{ run_id }}') as input_count
                    from {{ result.node.relation_name }}
                    where run_id = '{{ run_id }}'
                {% endset %}
                {% set row = metric_row('gold.ventas_tienda_dia', metrics_sql) %}
                {% do log_metrics({
                    "run_id": env_var("RUN_ID", invocation_id),
                    "pipeline": "ventas",
                    "layer": "gold",
                    "table_name": "gold.ventas_tienda_dia",
                    "output_count": row[0],
                    "grain_count": row[1],
                    "grain_counts": {"tienda_id|fecha_venta": row[1]},
                    "max_load_date": row[2],
                    "input_count": row[3]
                }) %}
            {% endif %}
        {% endfor %}
    {% endif %}
    {{ return("select 1") }}
{% endmacro %}
