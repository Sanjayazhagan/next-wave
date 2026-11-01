from datetime import date

from app.plugins import load_plugins
from contracts.doctor import DoctorRequest, DoctorResponse
from contracts.documents import ExtractedDocument
from contracts.portal import DocSpec, PreparedFile
from contracts.profile import Profile, ProfileField
from modules.doctor import check_application, diagnose
from modules.doctor import checks
from modules.rules.loader import load_file
from tests.rules_helpers import GIRL, INCOME, write_scheme


def doc(doc_type, conf=0.95, **fields) -> ExtractedDocument:
    return ExtractedDocument(document_type=doc_type, file_ref=f"ref-{doc_type}", fields={
        k: ProfileField(value=str(v), source_document=doc_type, confidence=conf) for k, v in fields.items()})


def prof(**fields) -> Profile:
    return Profile(fields={k: ProfileField(value=str(v), source_document="user_answer", confidence=1.0)
                           for k, v in fields.items()})


def scheme(tmp_path, rules=(INCOME,)):
    path = write_scheme(tmp_path, list(rules))
    s = load_file(path, raw_dir=tmp_path / "raw")
    return s.model_copy(update={"required_docs": ["marksheet", "income"]})


def test_name_mismatch_high_and_initials_ok():
    f = checks.name_consistency([doc("marksheet", full_name="S Satyajit"), doc("income", full_name="Ramesh Kumar")])
    assert len(f) == 1 and f[0].severity == "high" and f[0].points == 30
    assert f[0].values_by_doc == {"marksheet": "S Satyajit", "income": "Ramesh Kumar"}
    assert "tap Confirm" in f[0].fix
    ok = checks.name_consistency([doc("marksheet", full_name="S Satyajit"), doc("community", full_name="Satyajit S")])
    assert ok == []


def test_name_minor_spelling_is_medium():
    f = checks.name_consistency([doc("marksheet", full_name="Sathyajith R"), doc("income", full_name="Satyajit R")])
    assert f and f[0].severity == "medium" and f[0].points == 15


def test_eligibility_recheck_blocks_on_document_income(tmp_path):
    p = Profile(fields={"annual_income": ProfileField(value="950000", source_document="income", confidence=0.9)})
    f = checks.eligibility_recheck(p, scheme(tmp_path))
    assert f[0].severity == "blocker" and f[0].field == "annual_income"


def test_eligibility_recheck_ignores_low_confidence_reads(tmp_path):
    p = Profile(fields={"annual_income": ProfileField(value="950000", source_document="income", confidence=0.5)})
    f = checks.eligibility_recheck(p, scheme(tmp_path))
    assert f[0].severity == "medium"   # unverified read -> needs info, not a block


def test_required_docs_missing_is_blocker(tmp_path):
    f = checks.required_docs([doc("marksheet")], scheme(tmp_path))
    assert [(x.severity, x.detail) for x in f] == [("blocker", "income not uploaded")]
    # No document read at all: ask for a manual check rather than claiming they're missing.
    assert checks.required_docs([], scheme(tmp_path))[0].severity == "medium"


def test_file_spec():
    pf = PreparedFile(mime="image/jpeg", size_kb=1500, px=(100, 100), pages=1, actions=[], legible=False,
                      words_before=40, words_after=10)
    f = checks.file_spec({"income": pf}, {"*": DocSpec(doc_type="*", accepted_types=["pdf"], max_kb=1024)})
    assert {x.detail.split(",")[0] for x in f} == {"is image/jpeg", "is 1500 KB", "may be hard to read after compressing"}


def test_field_consistency_income_certificate_wins():
    f = checks.field_consistency([doc("income", annual_income="Rs. 2,40,000"), doc("community", annual_income="300000"),
                                  doc("marksheet", date_of_birth="15/08/2005"),
                                  doc("community", date_of_birth="2005-08-15")])
    assert len(f) == 1 and f[0].field == "annual_income" and "go by the income certificate" in f[0].fix


def test_image_quality_and_date_validity():
    assert checks.image_quality({"income": {"too_blurry": True, "too_dark": False}})[0].points == 15
    f = checks.date_validity([doc("income", issue_date="2027-01-05"), doc("community")], today=date(2026, 10, 31))
    assert [x.detail for x in f] == ["issue date in the future", "issue date not found"]


def test_score_is_sum_of_points_and_band(tmp_path):
    docs = [doc("marksheet", full_name="S Satyajit"), doc("community", full_name="Ramesh Kumar", issue_date="2025-01-01")]
    d = diagnose(prof(annual_income=100000), docs, scheme(tmp_path), today=date(2026, 10, 31))
    assert d.risk_score == min(100, sum(f.points for f in d.findings))
    assert d.band == "blocked"   # the income certificate is missing


def test_clean_application_is_low_risk(tmp_path):
    docs = [doc("marksheet", full_name="S Satyajit"),
            doc("income", full_name="Satyajit S", annual_income=200000, issue_date="2026-06-01")]
    d = diagnose(prof(annual_income=200000), docs, scheme(tmp_path), today=date(2026, 10, 31))
    assert d.findings == [] and d.band == "low" and d.risk_score == 0


def test_plugin_contract_and_no_sensitive_numbers():
    assert load_plugins().doctor is check_application
    docs = [doc("marksheet", full_name="S Satyajit", aadhaar_last4="9012"), doc("income", full_name="Ramesh Kumar")]
    resp = check_application(DoctorRequest(profile=prof(), documents=docs, scheme_id="unknown-scheme"))
    assert isinstance(resp, DoctorResponse) and 0 <= resp.risk_score <= 1
    assert resp.mismatches[0].field == "Name" and "9012" not in resp.model_dump_json()


def test_income_certificate_in_parents_name_is_not_a_mismatch():
    docs = [doc("marksheet", full_name="SATYAJIT S"),
            doc("community", full_name="Satyajit", father_name="Solai Rajan"),
            doc("income", full_name="Solairajan P", father_name="Patchaimal", annual_income=144000)]
    # Only the student's own documents are compared: "SATYAJIT S" vs "Satyajit" is a gentle check,
    # and the father's name on the parent's income certificate (the grandfather) is not compared.
    assert [(f.severity, f.values_by_doc) for f in checks.name_consistency(docs)] == [
        ("medium", {"marksheet": "SATYAJIT S", "community": "Satyajit"})]
    assert checks.field_consistency(docs) == []
    assert checks.parent_held(docs) == {2}


def test_expired_certificate_is_high():
    f = checks.date_validity([doc("income", issue_date="2024-02-27", valid_until="2025-02-26")], today=date(2026, 10, 31))
    assert [(x.severity, x.detail) for x in f] == [("high", "expired on 2025-02-26")]
    assert "TN e-District" in f[0].fix


def test_names_spaced_differently_match():
    from modules.doctor.names import compare
    assert compare("Solairajan P", "Solai Rajan")[0] >= 95
    assert compare("Satyajit", "Ramesh")[0] < 85


def test_central_obc_asks_for_state_certificate(tmp_path):
    from tests.rules_helpers import COMMUNITY
    p = Profile(fields={"community": ProfileField(value="OBC", source_document="community", confidence=1.0)})
    f = checks.eligibility_recheck(p, scheme(tmp_path, [COMMUNITY]))
    assert f[0].severity == "medium" and "from the Tamil Nadu government" in f[0].fix


def _cert(doc_type="community", **qr):
    fields = {"full_name": "Satyajit", "certificate_number": "TN-6202605053287", **qr}
    return doc(doc_type, **fields)


def test_qr_matching_print_is_clean():
    d = _cert(qr_status="decoded", qr_certificate_number="TN-6202605053287", qr_name="Satyajit",
              qr_service="OBC Certificate")
    assert checks.authenticity([d]) == []


def test_qr_mismatch_is_flagged_as_possible_tampering():
    d = _cert(qr_status="decoded", qr_certificate_number="TN-6202605059999", qr_name="Ramesh Kumar",
              qr_service="OBC Certificate")
    f = checks.authenticity([d])
    assert len(f) == 1 and f[0].severity == "blocker" and f[0].check == "authenticity"
    assert "certificate number and name" in f[0].fix and "may have been edited" in f[0].fix


def test_qr_for_a_different_certificate_type():
    d = _cert("income", qr_status="decoded", qr_certificate_number="TN-6202605053287", qr_name="Satyajit",
              qr_service="OBC Certificate")
    assert "certificate type" in checks.authenticity([d])[0].detail


def test_unreadable_or_missing_qr_on_e_district_certificate():
    assert checks.authenticity([_cert(qr_status="unreadable")])[0].severity == "low"
    assert checks.authenticity([_cert(qr_status="absent")])[0].severity == "medium"
    other = doc("community", full_name="Satyajit", certificate_number="12/2019", qr_status="absent")
    assert checks.authenticity([other]) == []



def test_headings_are_readable_never_raw_field_names():
    from modules.doctor.messages import heading
    assert heading("date_validity", "valid_until", "income") == "Income certificate"
    assert heading("name_consistency", "full_name", None) == "Name"
    assert heading("field_consistency", "father_name", None) == "Father's name"
    assert heading("eligibility_recheck", None, None) == "Eligibility"
    resp = check_application(DoctorRequest(profile=prof(), documents=[
        doc("income", full_name="Satyajit", issue_date="2024-02-27", valid_until="2025-02-26")]))
    assert all("_" not in m.field for m in resp.mismatches)


def test_findings_are_translated_with_values_kept(monkeypatch):
    import importlib
    loc = importlib.import_module("modules.doctor.localize")
    sent = []

    def fake_post(url, timeout, json):
        sent.append(json)
        return httpx.Response(200, json={"text": f"[ta] {json['text']}"}, request=httpx.Request("POST", url))

    import httpx
    monkeypatch.setenv("LANGUAGE_SERVICE_URL", "http://language.test")
    monkeypatch.setattr(loc.httpx, "post", fake_post)
    out = loc.localize([("Name", "Your name is 'SATYAJIT S' on the marksheet."), ("Weird heading", "x")], "ta", ["Pragati"])
    assert out[0] == ("பெயர்", "[ta] Your name is 'SATYAJIT S' on the marksheet.")   # table heading
    assert out[1][0] == "[ta] Weird heading"                                          # unknown heading: service
    assert "SATYAJIT S" in sent[0]["keep"] and "Pragati" in sent[0]["keep"] and sent[0]["target"] == "ta"


def test_findings_stay_in_english_without_a_working_service(monkeypatch):
    import httpx
    import importlib
    loc = importlib.import_module("modules.doctor.localize")
    monkeypatch.delenv("LANGUAGE_SERVICE_URL", raising=False)
    assert loc.localize([("Name", "Fix it.")], "ta") == [("பெயர்", "Fix it.")]
    monkeypatch.setenv("LANGUAGE_SERVICE_URL", "http://language.test")

    def down(url, timeout, json):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(loc.httpx, "post", down)
    assert loc.localize([("Name", "Fix it.")], "hi") == [("नाम", "Fix it.")]
    assert loc.localize([("Name", "Fix it.")], "en") == [("Name", "Fix it.")]
