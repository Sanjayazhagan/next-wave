"""The doctor's findings in Tamil through the real language service. Needs a Sarvam key."""
import pytest

from contracts.doctor import DoctorRequest
from contracts.documents import ExtractedDocument
from contracts.profile import Profile, ProfileField
from modules.doctor import check_application
from tests.remote_helpers import has_keys, real_language_url  # noqa: F401

pytestmark = [pytest.mark.live, pytest.mark.skipif(not has_keys("SARVAM_API_KEY"), reason="no Sarvam key")]


def test_findings_arrive_in_tamil_with_names_and_numbers_intact(real_language_url, monkeypatch):
    monkeypatch.setenv("LANGUAGE_SERVICE_URL", real_language_url)
    docs = [ExtractedDocument(document_type=t, file_ref=t, fields={
        k: ProfileField(value=v, source_document=t, confidence=1.0) for k, v in f.items()})
        for t, f in [("marksheet", {"full_name": "SATYAJIT S"}),
                     ("income", {"full_name": "Satyajit", "certificate_number": "TN-4202402207792",
                                 "issue_date": "2024-02-27", "valid_until": "2025-02-26"})]]
    resp = check_application(DoctorRequest(profile=Profile(), documents=docs, language="ta"))
    text = " ".join(f"{m.field} {m.detail}" for m in resp.mismatches)
    assert "வருமானச் சான்றிதழ்" in text                        # heading: Income certificate
    assert "'SATYAJIT S'" in text and "'Satyajit'" in text       # quoted names unchanged
    assert sum("஀" <= ch <= "௿" for ch in text) > 50     # mostly Tamil
    assert "valid_until" not in text and "full_name" not in text
