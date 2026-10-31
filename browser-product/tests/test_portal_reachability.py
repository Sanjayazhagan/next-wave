import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    'portal_reachability', Path(__file__).resolve().parents[1] / 'scripts' / 'portal_reachability.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_official_public_urls_only():
    for url in mod.PORTALS.values():
        mod.assert_public_research_url(url)
    with pytest.raises(ValueError):
        mod.assert_public_research_url('http://scholarships.gov.in/home')
    with pytest.raises(ValueError):
        mod.assert_public_research_url('https://127.0.0.1/secret')
    with pytest.raises(ValueError):
        mod.assert_public_research_url('https://example.com')
