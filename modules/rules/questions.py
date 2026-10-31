"""Which missing fields block the most schemes, as questions with fixed wording."""
from __future__ import annotations

from collections import Counter

from contracts.profile import Profile

from .engine import match
from .models import Question, Scheme

PRIORITY = ["state", "course", "annual_income", "community", "year_of_study", "gender", "marks_percentage"]

# Band answers store the band's upper bound, as an unverified user answer.
INCOME_BANDS = {"Up to ₹1 lakh": "100000", "Up to ₹2.5 lakh": "250000", "Up to ₹8 lakh": "800000",
                "More than ₹8 lakh": "800001"}

QUESTIONS = {
    "state": Question(field="state", text_en="Which state do you live in?"),
    "course": Question(field="course", text_en="What are you studying now? For example: B.E. first year."),
    "annual_income": Question(field="annual_income", text_en="What is your family's yearly income?",
                              choices=list(INCOME_BANDS)),
    "community": Question(field="community", text_en="What is your community category?",
                          choices=["SC", "ST", "BC", "MBC", "OC", "Other"]),
    "year_of_study": Question(field="year_of_study", text_en="Which year of your course are you in?",
                              choices=["1st year", "2nd year (lateral entry)", "2nd year", "3rd year", "4th year"]),
    "gender": Question(field="gender", text_en="What is your gender?", choices=["Female", "Male", "Transgender"]),
    "marks_percentage": Question(field="marks_percentage", text_en="What percentage did you score in your last exam?"),
    "disability_percent": Question(field="disability_percent",
                                   text_en="Do you have a disability certificate? If yes, what percentage does it show?"),
    "govt_school_6_to_12": Question(field="govt_school_6_to_12",
                                    text_en="Did you study from Class 6 to 12 in Tamil Nadu government schools?",
                                    choices=["Yes", "No"]),
}


def missing_questions(schemes: tuple[Scheme, ...] | list[Scheme], profile: Profile, top_k: int = 4) -> list[Question]:
    """Unknown fields counted across schemes not already ruled out, most blocking first."""
    blocked: Counter[str] = Counter()
    for scheme in schemes:
        m = match(scheme, profile)
        if m.status == "not_eligible":
            continue
        for field in {r.field for r in m.results if r.status == "unknown"}:
            blocked[field] += 1
    order = sorted(blocked, key=lambda f: (-blocked[f], PRIORITY.index(f) if f in PRIORITY else len(PRIORITY), f))
    return [QUESTIONS.get(f) or Question(field=f, text_en=f"What is your {f.replace('_', ' ')}?") for f in order[:top_k]]
