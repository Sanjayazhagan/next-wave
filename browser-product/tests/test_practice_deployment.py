import json
from pathlib import Path
import pytest
from scripts.configure_scholarship_practice import configure


def test_merge_preserves_secrets_other_portals_and_submit_policy():
    source = 'INTERNAL_KEY=private\nBROWSER_ENABLE_FINAL_SUBMIT=false\nBROWSER_PORTALS_JSON=\'{"existing":{"url":"https://example.org"}}\'\nBROWSER_ALLOWED_ORIGINS=https://example.org\n'
    result = configure(source, 'browser.example.org')
    assert 'INTERNAL_KEY=private\n' in result
    assert 'BROWSER_ENABLE_FINAL_SUBMIT=false\n' in result
    value = next(line.split('=', 1)[1] for line in result.splitlines() if line.startswith('BROWSER_PORTALS_JSON='))
    registry = json.loads(value[1:-1])
    assert registry['existing']['url'] == 'https://example.org'
    assert registry['scholarship_practice']['url'] == 'https://browser.example.org/practice/scholarship'
    assert 'receipt_pattern' in registry['scholarship_practice']
    assert 'BROWSER_ALLOWED_ORIGINS=https://example.org,https://browser.example.org' in result
    assert configure(result, 'browser.example.org') == result


@pytest.mark.parametrize('source', ['BROWSER_PORTALS_JSON=oops', 'BROWSER_PORTALS_JSON=[]', 'BROWSER_PORTALS_JSON={}\nBROWSER_PORTALS_JSON={}'])
def test_invalid_configuration_is_not_overwritten(source):
    with pytest.raises(ValueError):
        configure(source, 'browser.example.org')


def test_public_route_is_narrow():
    caddy = (Path(__file__).resolve().parents[1] / 'deploy/Caddyfile').read_text()
    assert '@scholarship path /practice/scholarship /practice/scholarship/*' in caddy
    assert '@scholarship path /practice/*' not in caddy
    assert 'basic_auth {' in caddy
