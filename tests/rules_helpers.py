"""Test-only scheme builder for the rule engine tests (writes a temp snapshot + rules file)."""
import json
from pathlib import Path

import yaml

SOURCE_TEXT = ("The applicant must be a Girl Student. The annual income of the family must not be more than "
               "Rs. 8,00,000 per annum. The beneficiary should belong to BC, MBC or DNC. "
               "The applicant should be residing in the state of Tamil Nadu. Last date is 30 November 2026.")
URL = "https://example.gov.in/test-scheme"


def write_scheme(tmp: Path, rules: list[dict], review=True, deadline=None, scheme_id="test-scheme",
                 benefit=10000, unmodelled=None) -> Path:
    raw = tmp / "raw" / scheme_id
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "src.txt").write_text(SOURCE_TEXT)
    (raw / "meta.json").write_text(json.dumps([{"url": URL, "file": "src.txt", "scraped_at": "2026-10-31"}]))
    data = {"scheme_id": scheme_id, "name": f"Test {scheme_id}", "portal_id": "nsp", "benefit_inr": benefit,
            "benefit_text": "Rs 10,000", "deadline": deadline, "deadline_clause": "Last date is 30 November 2026.",
            "required_docs": ["marksheet"], "sources": [{"url": URL, "scraped_at": "2026-10-31"}],
            "rules": rules, "unmodelled": unmodelled or []}
    if review:
        data["review"] = {"reviewed_by": "test", "reviewed_at": "2026-10-31"}
    (tmp / "rules").mkdir(exist_ok=True)
    path = tmp / "rules" / f"{scheme_id}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    return path


GIRL = {"id": "girl", "field": "gender", "op": "eq", "value": "female", "clause": "The applicant must be a Girl Student."}
INCOME = {"id": "income", "field": "annual_income", "op": "lte", "value": 800000,
          "clause": "The annual income of the family must not be more than Rs. 8,00,000 per annum."}
COMMUNITY = {"id": "community", "field": "community", "op": "in", "value": ["BC", "MBC", "DNC"],
             "clause": "The beneficiary should belong to BC, MBC or DNC."}
STATE = {"id": "state", "field": "state", "op": "eq", "value": "Tamil Nadu",
         "clause": "The applicant should be residing in the state of Tamil Nadu."}
