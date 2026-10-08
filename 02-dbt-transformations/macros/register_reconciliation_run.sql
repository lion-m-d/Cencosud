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

{% macro log_rejects(payload) %}
    {% do log("RECON_REJECTS " ~ (payload | tojson), info=True) %}
{% endmacro %}

{% macro register_reconciliation_run(results) %}
    -- depends_on: {{ ref('ventas') }}
    -- depends_on: {{ ref('ventas_rechazadas') }}
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
                         where _run_id = '{{ run_id }}') as input_count,
                        (select count(*) from {{ ref('ventas_rechazadas') }}
                         where run_id = '{{ run_id }}') as rejected_count
                    from {{ result.node.relation_name }}
                    where run_id = '{{ run_id }}'
                {% endset %}
                {% set bronze_sql %}
                    select
                        count(*) as output_count,
                        count(distinct cast(ticket_id as string)) as tickets,
                        cast(max(fecha_carga) as string) as max_load_date
                    from {{ source('bronze', 'ventas') }}
                    where _run_id = '{{ run_id }}'
                {% endset %}
                {% set bronze = metric_row('bronze.ventas', bronze_sql) %}
                {% do log_metrics({
                    "run_id": env_var("RUN_ID", invocation_id),
                    "pipeline": "ventas",
                    "layer": "bronze",
                    "table_name": "bronze.ventas",
                    "output_count": bronze[0],
                    "input_count": bronze[0],
                    "grain_count": bronze[1],
                    "grain_counts": {"ticket_id": bronze[1]},
                    "max_load_date": bronze[2]
                }) %}
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
                    "input_count": row[4],
                    "rejected_count": row[5],
                    "rejected_grain": ["ticket_id"]
                }) %}
                {% set silver_rows_sql %}
                    select
                        coalesce(cast(ticket_id as string), ''),
                        coalesce(cast(tienda_id as string), ''),
                        coalesce(cast(fecha_venta as string), ''),
                        coalesce(cast(monto as string), ''),
                        coalesce(cast(fecha_carga as string), '')
                    from {{ result.node.relation_name }}
                    where run_id = '{{ run_id }}'
                {% endset %}
                {% set silver_loaded = run_query(silver_rows_sql) %}
                {% set silver_ns = namespace(records=[]) %}
                {% if silver_loaded is not none %}
                    {% for row in silver_loaded.rows %}
                        {% set silver_ns.records = silver_ns.records + [{
                            "ticket_id": row[0],
                            "tienda_id": row[1],
                            "fecha_venta": row[2],
                            "monto": row[3],
                            "fecha_carga": row[4]
                        }] %}
                    {% endfor %}
                {% endif %}
                {% if silver_ns.records | length > 0 %}
                    {% do log("RECON_ROWS " ~ ({
                        "run_id": env_var("RUN_ID", invocation_id),
                        "layer": "silver",
                        "table_name": "silver.ventas",
                        "records": silver_ns.records
                    } | tojson), info=True) %}
                {% endif %}
            {% elif result.node.name == 'ventas_rechazadas' %}
                {% set rejects_sql %}
                    select
                        coalesce(cast(ticket_id as string), ''),
                        coalesce(cast(tienda_id as string), ''),
                        coalesce(cast(fecha_venta as string), ''),
                        coalesce(cast(monto as string), ''),
                        reason
                    from {{ result.node.relation_name }}
                    where run_id = '{{ run_id }}'
                {% endset %}
                {% set rejected = run_query(rejects_sql) %}
                {% set records = [] %}
                {% if rejected is not none %}
                    {% for row in rejected.rows %}
                        {% if loop.index0 < 100 %}
                            {% do records.append({
                                "ticket_id": row[0],
                                "tienda_id": row[1],
                                "fecha_venta": row[2],
                                "monto": row[3],
                                "reason": row[4]
                            }) %}
                        {% endif %}
                    {% endfor %}
                {% endif %}
                {% if records | length > 0 %}
                    {% do log_rejects({
                        "run_id": env_var("RUN_ID", invocation_id),
                        "records": records
                    }) %}
                {% endif %}
            {% elif result.node.name == 'ventas_tienda_dia' %}
                {% set metrics_sql %}
                    select
                        coalesce(sum(tickets), 0) as output_count,
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
                {% set gold_rows_sql %}
                    select
                        coalesce(cast(tienda_id as string), ''),
                        coalesce(cast(fecha_venta as string), ''),
                        coalesce(cast(tickets as string), ''),
                        coalesce(cast(monto_total as string), ''),
                        coalesce(cast(fecha_carga as string), '')
                    from {{ result.node.relation_name }}
                    where run_id = '{{ run_id }}'
                {% endset %}
                {% set gold_loaded = run_query(gold_rows_sql) %}
                {% set gold_ns = namespace(records=[]) %}
                {% if gold_loaded is not none %}
                    {% for row in gold_loaded.rows %}
                        {% set gold_ns.records = gold_ns.records + [{
                            "tienda_id": row[0],
                            "fecha_venta": row[1],
                            "tickets": row[2],
                            "monto_total": row[3],
                            "fecha_carga": row[4]
                        }] %}
                    {% endfor %}
                {% endif %}
                {% if gold_ns.records | length > 0 %}
                    {% do log("RECON_ROWS " ~ ({
                        "run_id": env_var("RUN_ID", invocation_id),
                        "layer": "gold",
                        "table_name": "gold.ventas_tienda_dia",
                        "records": gold_ns.records
                    } | tojson), info=True) %}
                {% endif %}
            {% endif %}
        {% endfor %}
    {% endif %}
    {{ return("select 1") }}
{% endmacro %}
