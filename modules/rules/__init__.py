"""M4 eligibility rule engine, loaded by core through app/plugins.py.

    rank_schemes(request: EligibilityRequest) -> EligibilityResponse

Rules come from reviewed files in schemes/rules/*.yaml (see loader.py). A rules
file that fails its checks stops the import, so core logs the error and skips the
rule engine. With no reviewed files at all, `rank_schemes` is not defined and core
carries on without the rule engine, as it does before this module is merged.
"""
from __future__ import annotations

import logging

from common.config import env
from contracts.eligibility import EligibilityRequest, EligibilityResponse, SchemeQuestion
from contracts.eligibility import SchemeMatch as ContractMatch

from .engine import rank
from .explain import cited_clause
from .loader import load_all
from .models import Question, Scheme
from .questions import INCOME_BANDS, missing_questions

log = logging.getLogger(__name__)


def portal_for(scheme_portal_id: str) -> str:
    """DEMO_PORTAL_ID, when set, sends the browser to the practice portal instead of the scheme's
    real portal. The scheme's name and cited rule stay real."""
    return env("DEMO_PORTAL_ID") or scheme_portal_id


# Value to store -> button label, for answers the rules compare exactly. Labels are distinct phrases
# (no bare "Yes"/"No"): core translates by replacing known English text inside a message.
ANSWERS = {
    "gender": {"female": "Female", "male": "Male", "transgender": "Transgender"},
    "disability_percent": {"40": "Yes, 40% or more", "10": "Yes, under 40%", "0": "No disability certificate"},
    "govt_school_6_to_12": {"yes": "Yes, all in government schools", "no": "No, not all"},
    # A band stores its upper bound; "More than 8 lakh" stores 800001, so it fails an 8 lakh ceiling.
    "annual_income": {value: label for label, value in INCOME_BANDS.items()},
}


def to_contract(question: Question) -> SchemeQuestion:
    labels = question.choices or []
    choices = ANSWERS.get(question.field) or dict(zip(labels, labels, strict=True))
    return SchemeQuestion(field=question.field, text=question.text_en, choices=choices)


def rank_with(schemes: tuple[Scheme, ...] | list[Scheme], request: EligibilityRequest) -> EligibilityResponse:
    """Eligible and needs-info schemes, best first. Schemes the user fails are left out."""
    matches = [m for m in rank(schemes, request.profile) if m.status != "not_eligible"]
    return EligibilityResponse(schemes=[
        ContractMatch(scheme_id=m.scheme_id, name=m.name, portal_id=portal_for(m.portal_id), rank=i,
                      cited_clause=cited_clause(m))
        for i, m in enumerate(matches, start=1)],
        questions=[to_contract(q) for q in missing_questions(schemes, request.profile)])


SCHEMES = load_all()

if SCHEMES:
    def rank_schemes(request: EligibilityRequest) -> EligibilityResponse:
        """Core's plug-in entry point."""
        return rank_with(SCHEMES, request)
else:
    log.warning("No reviewed rules in modules/rules/schemes/rules/, so the rule engine is off")
