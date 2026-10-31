from fastapi.testclient import TestClient

from tests.conftest import API_TOKEN, Network

HEADERS = {"X-API-Key": API_TOKEN}


def start(client: TestClient) -> str:
    return client.post("/session", json={}, headers=HEADERS).json()["id"]


def reply(client: TestClient, sid: str, **body) -> None:
    assert client.post(f"/session/{sid}/reply", json=body, headers=HEADERS).status_code == 202


def test_every_route_needs_the_api_key(client: TestClient) -> None:
    sid = start(client)
    assert client.post("/session", json={}).status_code == 401
    assert client.get(f"/session/{sid}").status_code == 401
    assert client.get(f"/session/{sid}/audit", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post(f"/session/{sid}/reply", json={"text": "x"}).status_code == 401


def test_unknown_session_is_404(client: TestClient) -> None:
    assert client.get("/session/nope", headers=HEADERS).status_code == 404


def test_web_session_runs_the_same_loop(client: TestClient, network: Network) -> None:
    sid = start(client)
    view = client.get(f"/session/{sid}", headers=HEADERS).json()
    assert view["status"] == "paused"
    assert view["prompt"]["kind"] == "consent"

    reply(client, sid, button="consent:yes")
    reply(client, sid, text="Tamil Nadu")
    reply(client, sid, text="Class 12")
    reply(client, sid, text="120000")
    reply(client, sid, button="question_community:bc")
    reply(client, sid, button="confirm:yes")
    upload = client.post(
        f"/session/{sid}/files",
        files={"file": ("mark.jpg", b"image-bytes", "image/jpeg")},
        headers=HEADERS,
    )
    assert upload.status_code == 202
    reply(client, sid, button="documents:done")
    reply(client, sid, text="portal-user")
    reply(client, sid, text="123456")
    reply(client, sid, text="ABCD")

    view = client.get(f"/session/{sid}", headers=HEADERS).json()
    assert view["prompt"]["kind"] == "approval"
    assert view["filled"]["full_name"]["source_document"] == "marksheet"
    assert view["profile"]["annual_income"]["source_document"] == "user_answer"
    assert view["mode"] == "explore"
    assert network.sent == []  # A web-only session sends no WhatsApp messages.

    types = [event["type"] for event in client.get(f"/session/{sid}/audit", headers=HEADERS).json()]
    assert {"step_started", "otp_needed", "captcha_needed", "approval_needed"} <= set(types)


def test_event_stream_replays_and_ends_when_done(client: TestClient) -> None:
    sid = start(client)
    reply(client, sid, button="consent:no")

    with client.stream("GET", f"/session/{sid}/events", params={"key": API_TOKEN}) as stream:
        body = "".join(stream.iter_text())

    assert "event: question_needed" in body
    assert "event: done" in body
    assert "id: " in body


def test_event_stream_resumes_after_last_event_id(client: TestClient) -> None:
    sid = start(client)
    reply(client, sid, button="consent:no")
    events = client.get(f"/session/{sid}/audit", headers=HEADERS).json()

    with client.stream(
        "GET",
        f"/session/{sid}/events",
        headers={**HEADERS, "Last-Event-ID": str(events[0]["seq"])},
    ) as stream:
        body = "".join(stream.iter_text())

    assert "event: question_needed" not in body
    assert "event: done" in body


def test_file_is_refused_when_not_expected(client: TestClient) -> None:
    sid = start(client)
    response = client.post(
        f"/session/{sid}/files",
        files={"file": ("a.jpg", b"x", "image/jpeg")},
        headers=HEADERS,
    )
    assert response.status_code == 409


def test_handover_is_refused_unless_waiting_for_a_helper(client: TestClient) -> None:
    sid = start(client)
    response = client.post(f"/session/{sid}/handover", json={}, headers=HEADERS)
    assert response.status_code == 409


def test_web_session_can_be_linked_to_a_phone(client: TestClient, network: Network) -> None:
    client.post("/session", json={"phone": "919000000002"}, headers=HEADERS)
    assert network.sent[-1]["to"] == "919000000002"
