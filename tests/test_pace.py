import common.pace as pace


def test_calls_are_spaced_by_requests_per_minute(monkeypatch) -> None:
    monkeypatch.setenv("LLM_RPM", "30")
    monkeypatch.setenv("LLM_TPM", "0")
    monkeypatch.setattr(pace, "_next_slot", 0.0)
    waits = [pace.book(10) for _ in range(3)]
    assert waits[0] == 0
    assert 1.9 < waits[1] < 2.1
    assert 3.9 < waits[2] < 4.1


def test_a_big_call_pushes_the_next_slot_out(monkeypatch) -> None:
    monkeypatch.setenv("LLM_RPM", "30")
    monkeypatch.setenv("LLM_TPM", "8000")
    monkeypatch.setattr(pace, "_next_slot", 0.0)
    monkeypatch.setattr(pace, "_booked", [])
    assert pace.book(5000) == 0
    assert pace.book(1000) < 3
    assert 55 < pace.book(4000) < 61


def test_a_null_field_from_the_model_is_accepted() -> None:
    from modules.extraction.schemas import schema_for

    answer = schema_for("income").model_validate_json('{"issue_date": null}')
    assert answer.issue_date is None


def test_zero_turns_it_off(monkeypatch) -> None:
    monkeypatch.setenv("LLM_RPM", "0")
    monkeypatch.setenv("LLM_TPM", "0")
    monkeypatch.setattr(pace, "_next_slot", 0.0)
    assert pace.book(5000) == 0
    assert pace.book(5000) == 0


def test_images_count_as_a_fixed_size_not_as_base64() -> None:
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "a" * 400},
        {"type": "image_url", "image_url": {"url": "x" * 100000}},
    ]}]
    assert pace.estimate_tokens(messages, 600) == 100 + pace.IMAGE_TOKENS + 600
