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
    assert resp.mismatches[0].field == "full_name" and "9012" not in resp.model_dump_json()
