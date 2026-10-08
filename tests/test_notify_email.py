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
