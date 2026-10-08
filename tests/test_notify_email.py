import json

from notify.email import build_notice


def test_pass_lists_every_validated_step() -> None:
    subject, message = build_notice(
        {"outcome": "PASS", "run_id": "abc", "load_date": "2026-10-07"}
    )
    assert subject.startswith("Pipeline validado")
    assert "VALIDADO" in message
    assert "concuerda" in message
    assert "1. Bronze — validado" in message
    assert "2. Silver — validado" in message
    assert "3. Gold — validado" in message


def test_mismatch_names_the_failed_step() -> None:
    cause = (
        '{"ErrorMessage":"Reconciliation FAILED | ventas_bronze_silver: '
        'layer_ratio: valor 0.4 fuera de lo esperado (0.95..1.0)"}'
    )
    subject, message = build_notice(
        {"outcome": "FAIL", "run_id": "abc", "load_date": "2026-10-07", "cause": cause}
    )
    assert "no concuerda" in subject
    assert "1. Bronze — validado" in message
    assert "2. Silver — no concuerda" in message
    assert "3. Gold — no se ejecutó" in message
    assert "layer_ratio" in message


def test_notice_includes_how_many_records_moved() -> None:
    _, message = build_notice(
        {
            "outcome": "PASS",
            "run_id": "abc",
            "load_date": "2026-10-07",
            "layers": [
                {"layer": "bronze", "input_count": 23, "output_count": 23},
                {"layer": "silver", "input_count": 23, "output_count": 22},
            ],
        }
    )
    assert "bronze: entraron 23, salieron 23" in message
    assert "silver: entraron 23, salieron 22" in message


def test_notice_names_records_left_out_of_the_file() -> None:
    subject, message = build_notice(
        {
            "outcome": "PASS",
            "run_id": "abc",
            "load_date": "2026-10-07",
            "layers": [
                {"layer": "bronze", "input_count": 22, "output_count": 22},
                {"layer": "silver", "input_count": 22, "output_count": 18, "rejected_count": 4},
            ],
            "rejects": [
                {"ticket_id": "T-019", "reason": "monto vacío"},
                {"ticket_id": "T-020", "reason": "monto vacío"},
                {"ticket_id": "T-021", "reason": "monto vacío"},
                {"ticket_id": "T-022", "reason": "monto vacío"},
            ],
        }
    )
    assert subject == "Se procesaron 18 de 22 registros"
    assert "No se procesaron 4 de 22 registros enviados." in message
    assert "Se procesaron 18 registros correctos." in message
    assert "- T-019: monto vacío" in message
    assert "- T-022: monto vacío" in message


def test_boundary_line_is_not_counted_as_a_ticket() -> None:
    subject, message = build_notice(
        {
            "outcome": "FAIL",
            "run_id": "abc",
            "load_date": "2026-10-07",
            "layers": [
                {"layer": "silver", "input_count": 23, "output_count": 18, "rejected_count": 5},
            ],
            "rejects": [
                {"ticket_id": "T-019", "reason": "monto vacío"},
                {"ticket_id": "T-020", "reason": "monto vacío"},
                {"ticket_id": "T-021", "reason": "monto vacío"},
                {"ticket_id": "T-022", "reason": "monto vacío"},
                {"ticket_id": "----------------------------527214442355101885544272--", "reason": "monto vacío"},
            ],
            "cause": json.dumps({
                "Build": {
                    "Phases": [
                        {
                            "PhaseStatus": "FAILED",
                            "Contexts": [{"Message": "No existen metricas de bronze"}],
                        }
                    ]
                }
            }),
        }
    )
    assert "No se procesaron 4 de 22 registros enviados." in message
    assert "Se procesaron 18 registros correctos." in message
    assert "527214442355101885544272" not in message
    assert "No existen metricas de bronze" in message
    assert "SdkHttpMetadata" not in message
    assert subject.startswith("Fallo") or "no concuerda" in subject
    assert "Archivo procesado: sin nombre" in message
    assert "falló en los registros" in message


def test_notice_names_the_file_and_failed_records() -> None:
    _subject, message = build_notice(
        {
            "outcome": "PASS",
            "run_id": "abc",
            "load_date": "2026-10-07",
            "file_name": "ventas_error.csv",
            "layers": [
                {"layer": "bronze", "input_count": 22, "output_count": 22},
                {"layer": "silver", "input_count": 22, "output_count": 18, "rejected_count": 4},
            ],
            "rejects": [
                {"ticket_id": "T-019", "reason": "monto vacío"},
                {"ticket_id": "T-020", "reason": "monto vacío"},
                {"ticket_id": "T-021", "reason": "monto vacío"},
                {"ticket_id": "T-022", "reason": "monto vacío"},
            ],
        }
    )
    assert "Archivo procesado: ventas_error.csv" in message
    assert "El archivo ventas_error.csv falló en los registros: no se procesaron 4 de 22." in message
