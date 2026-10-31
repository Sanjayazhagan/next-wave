import time
from datetime import date

import pytest
import yaml

from contracts.eligibility import EligibilityRequest, EligibilityResponse
from contracts.profile import Profile, ProfileField
from modules.rules import rank_with
from modules.rules.engine import evaluate, match, rank
from modules.rules.loader import SCHEMES_DIR, load_file
from modules.rules.models import Scheme
from modules.rules.questions import missing_questions
from tests.rules_helpers import COMMUNITY, GIRL, INCOME, STATE, write_scheme


def profile(**values) -> Profile:
    return Profile(fields={k: ProfileField(value=str(v), source_document="user_answer", confidence=1.0)
                           for k, v in values.items()})


def scheme(tmp_path, rules, **kw) -> Scheme:
    return load_file(write_scheme(tmp_path, rules, **kw), raw_dir=tmp_path / "raw")


# --- Generated boundary tests over every rule in the repo (reviewed and draft) ---

def _all_rules():
    out = []
    for path in sorted((SCHEMES_DIR / "rules").glob("*.yaml")):
        s = Scheme.model_validate(yaml.safe_load(path.read_text()))
        out += [(s, r) for r in s.rules]
    return out


NUMERIC = {"lt": (False, False, True), "lte": (False, True, True), "gt": (True, False, False),
           "gte": (True, True, False)}  # pass? for value+1, value, value-1


@pytest.mark.parametrize("s,rule", [(s, r) for s, r in _all_rules() if r.op in NUMERIC],
                         ids=lambda x: getattr(x, "id", getattr(x, "scheme_id", "")))
def test_numeric_boundaries(s, rule):
    for delta, want in zip((1, 0, -1), NUMERIC[rule.op]):
        got = evaluate(s, rule, profile(**{rule.field: rule.value + delta})).status
        assert got == ("pass" if want else "fail"), (rule.id, delta)


@pytest.mark.parametrize("s,rule", [(s, r) for s, r in _all_rules() if r.op in ("in", "eq")],
                         ids=lambda x: getattr(x, "id", getattr(x, "scheme_id", "")))
def test_membership(s, rule):
    member = rule.value[0] if rule.op == "in" else rule.value
    assert evaluate(s, rule, profile(**{rule.field: member})).status == "pass"
    outsider = {"community": "OC", "gender": "male", "state": "Kerala"}.get(rule.field, "zzz-not-a-member")
    assert evaluate(s, rule, profile(**{rule.field: outsider})).status == "fail"


# --- Cases ---

def test_missing_field_gives_needs_info(tmp_path):
    m = match(scheme(tmp_path, [GIRL, INCOME]), profile(annual_income=300000))
    assert m.status == "needs_info" and [r.status for r in m.results] == ["unknown", "pass"]


def test_one_failing_rule_makes_scheme_not_eligible(tmp_path):
    m = match(scheme(tmp_path, [GIRL, INCOME]), profile(gender="Female", annual_income="Rs. 9,00,000"))
    assert m.status == "not_eligible"
    fail = next(r for r in m.results if r.status == "fail")
    assert fail.clause.source_url.startswith("https://") and "8,00,000" in fail.clause.text


def test_passed_deadline_makes_scheme_not_eligible(tmp_path):
    s = scheme(tmp_path, [INCOME], deadline="2026-11-30")
    assert match(s, profile(annual_income=1), today=date(2026, 11, 1)).status == "eligible"
    m = match(s, profile(annual_income=1), today=date(2026, 12, 1))
    assert m.status == "not_eligible" and m.results[-1].rule_id == "deadline"


def test_core_community_buttons(tmp_path):
    s = scheme(tmp_path, [COMMUNITY])
    assert match(s, profile(community="SC / ST")).status == "not_eligible"   # no SC/ST member qualifies
    assert match(s, profile(community="BC / MBC")).status == "needs_info"    # BC/MBC answer: BCM/OBC uncertain
    assert match(s, profile(community="sc_st")).status == "not_eligible"     # button ids work too
    assert match(s, profile(community="General")).status == "not_eligible"
    assert match(s, profile(community="Most Backward Class")).status == "eligible"


def test_state_aliases_and_gender_words(tmp_path):
    s = scheme(tmp_path, [STATE, GIRL])
    assert match(s, profile(state="TN", gender="girl")).status == "eligible"
    assert match(s, profile(state="Tamilnadu", gender="F")).status == "eligible"


def test_rank_order_and_speed(tmp_path):
    a = scheme(tmp_path, [INCOME], scheme_id="a", benefit=5000)
    b = scheme(tmp_path, [INCOME], scheme_id="b", benefit=50000)
    c = scheme(tmp_path, [GIRL], scheme_id="c", benefit=99999)
    d = scheme(tmp_path, [STATE], scheme_id="d", benefit=1)
    p = profile(annual_income=100000, state="Kerala")
    t0 = time.perf_counter()
    ranked = rank([a, b, c, d], p)
    assert (time.perf_counter() - t0) * 1000 < 50
    assert [m.scheme_id for m in ranked] == ["b", "a", "c", "d"]


def test_plugin_response_skips_not_eligible(tmp_path):
    a = scheme(tmp_path, [INCOME], scheme_id="a")
    c = scheme(tmp_path, [GIRL], scheme_id="c")
    d = scheme(tmp_path, [STATE], scheme_id="d")
    resp = rank_with([a, c, d], EligibilityRequest(profile=profile(annual_income=1, state="Kerala")))
    assert isinstance(resp, EligibilityResponse)
    assert [(s.scheme_id, s.rank) for s in resp.schemes] == [("a", 1), ("c", 2)]
    assert "example.gov.in" in resp.schemes[0].cited_clause
    assert resp.schemes[1].cited_clause.startswith("To check Test c, I need your gender")


def test_questions_on_empty_profile(tmp_path):
    schemes = [scheme(tmp_path, [STATE, INCOME, COMMUNITY], scheme_id="x"),
               scheme(tmp_path, [STATE, INCOME], scheme_id="y")]
    fields = [q.field for q in missing_questions(schemes, Profile())]
    assert fields[:2] == ["state", "annual_income"] and "community" in fields


def test_demo_portal_sends_browser_to_practice_portal(tmp_path, monkeypatch):
    a = scheme(tmp_path, [INCOME], scheme_id="a")
    req = EligibilityRequest(profile=profile(annual_income=1))
    assert rank_with([a], req).schemes[0].portal_id == "nsp"
    monkeypatch.setenv("DEMO_PORTAL_ID", "mock-scholarship")
    s = rank_with([a], req).schemes[0]
    assert s.portal_id == "mock-scholarship" and s.name == "Test a" and "example.gov.in" in s.cited_clause


def test_committed_rules_load_and_plugin_is_on():
    import modules.rules as rules
    from app.plugins import load_plugins

    assert {s.scheme_id for s in rules.SCHEMES} == {
        "aicte-pragati-degree", "aicte-saksham-degree", "pudhumai-penn", "tn-postmatric-bc-mbc-dnc"}
    assert load_plugins().rules is rules.rank_schemes


def test_central_obc_certificate_is_unknown_for_state_categories(tmp_path):
    s = scheme(tmp_path, [COMMUNITY])
    assert match(s, profile(community="OBC")).status == "needs_info"
    assert match(s, profile(community="OC")).status == "not_eligible"


def ranked(**answers: str):
    import modules.rules as rules
    from contracts.eligibility import EligibilityRequest
    from contracts.profile import Profile, ProfileField

    values = {"state": "Tamil Nadu", "course": "B.E. first year", "annual_income": "200000",
              "community": "BC / MBC", **answers}
    profile = Profile(fields={
        name: ProfileField(value=value, source_document="user_answer", confidence=1.0)
        for name, value in values.items()
    })
    return rules.rank_schemes(EligibilityRequest(profile=profile))


def test_undecided_details_come_back_as_questions_with_buttons() -> None:
    questions = {q.field: q for q in ranked().questions}
    assert "gender" in questions
    assert questions["gender"].choices["male"] == "Male"


def test_a_boy_is_not_offered_a_girls_scheme() -> None:
    names = [s.scheme_id for s in ranked(gender="male").schemes]
    assert "aicte-pragati-degree" not in names
    assert "pudhumai-penn" not in names


def test_a_girl_keeps_the_girls_scheme() -> None:
    assert "aicte-pragati-degree" in [s.scheme_id for s in ranked(gender="female").schemes]


def test_under_forty_percent_disability_rules_out_saksham() -> None:
    names = [s.scheme_id for s in ranked(disability_percent="10").schemes]
    assert "aicte-saksham-degree" not in names


def test_no_questions_remain_once_all_are_answered() -> None:
    answers = {
        "gender": "female", "disability_percent": "0", "govt_school_6_to_12": "no",
        "community": "BC",
    }
    assert ranked(**answers).questions == []


def test_a_grouped_community_is_asked_exactly_when_it_decides_a_scheme() -> None:
    assert "community" in [q.field for q in ranked().questions]
