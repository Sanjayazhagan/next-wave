"""Regression: a bare assistance URL is safe, and CAPTCHA uses a scoped link."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from browser.core_compat import challenge_info
from server.core_assist import router


def test_bare_assistance_landing_has_no_session_and_does_not_return_404():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get('/core-assist/')
        assert response.status_code == 200
        assert 'Verification link required' in response.text
        assert 'complete' in response.text
        assert response.headers['cache-control'] == 'no-store'
        assert "default-src 'none'" in response.headers['content-security-policy']
        assert 'assistance_path' not in response.text
        assert 'X-Internal-Key' not in response.text


def test_caddy_matches_assistance_landing_and_generated_links():
    caddy = (Path(__file__).parents[1] / 'deploy' / 'Caddyfile').read_text()
    assert '@human path /core-assist/ /core-assist/*' in caddy
    assert 'reverse_proxy api:8000' in caddy


def test_challenge_with_captcha_input_uses_link_not_image():
    observation = {'elements': [
        {'risk': 'human_auth', 'tag': 'input', 'label': 'CAPTCHA answer',
         'type': 'text', 'ref': 'answer'},
        {'risk': 'normal', 'tag': 'button', 'label': 'Verify',
         'type': 'button', 'ref': 'verify'},
    ]}
    result = challenge_info(observation, {'answer':'CAPTCHA answer','verify':'Verify'})
    assert result['kind'] == 'captcha'
    assert result['human_task_reason'] == 'captcha'
    assert result['image_base64'] is None
    assert result['delivery_mode'] == 'human_assistance_link'
    assert result['requires_human'] is True
    assert result['input'] == {'role':'textbox','name':'CAPTCHA answer'}


def test_iframe_only_captcha_still_prompts_for_link():
    observation = {'elements': [], 'human_signals': [
        {'kind':'challenge_frame','frame_id':'opaque-frame'},
    ]}
    result = challenge_info(observation, {})
    assert result['kind'] == 'captcha'
    assert result['delivery_mode'] == 'human_assistance_link'
    assert result['input'] is None
    assert result['image_base64'] is None


def test_otp_does_not_turn_into_captcha_or_disclose_image():
    observation = {'elements': [
        {'risk':'human_auth', 'tag':'input', 'type':'number',
         'auth_kind':'otp', 'label':'OTP Code', 'ref':'otp'},
    ]}
    result = challenge_info(observation, {'otp':'OTP Code'})
    assert result['kind'] == 'otp'
    assert result['human_task_reason'] == 'otp'
    assert result['image_base64'] is None
    assert result['input']['role'] == 'spinbutton'


def test_ordinary_page_does_not_invent_captcha():
    assert challenge_info({'elements':[], 'human_signals':[]}, {}) is None
