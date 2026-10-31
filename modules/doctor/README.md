# Application doctor (M5)

Catches what gets applications rejected before the portal sees it, with one
clear fix per problem. Core loads it through `app/plugins.py` and lists the
fixes on the review step:

```python
def check_application(request: DoctorRequest) -> DoctorResponse
```

**The risk score is a transparent checklist, not a trained model.** Each finding
carries points (blocker 100, high 30, medium 15, low 5); the score is their sum,
capped at 100. `DoctorResponse.risk_score` is that number divided by 100. The
full breakdown is in `diagnose(...) -> Diagnosis` (`findings`, `points`,
`values_by_doc` for side-by-side display).

| # | Check | How | Severity |
| --- | --- | --- | --- |
| 1 | `name_consistency` | names on every document compared pairwise (`names.compare`) | high 30, or medium 15 for a minor spelling difference |
| 2 | `eligibility_recheck` | rule engine on verified fields only (user answers, or document reads with confidence ≥ 0.8) | blocker if not eligible; medium if it needs info |
| 3 | `required_docs` | the scheme's `required_docs` against the documents read | blocker per missing document |
| 4 | `file_spec` | prepared file type, size and legibility against the portal spec | medium each |
| 5 | `field_consistency` | date of birth, father's name, community, income across documents (the income certificate wins for income, the community certificate for community) | high 30 |
| 6 | `image_quality` | blurry or dark photo | medium 15 |
| 7 | `date_validity` | certificate expired (printed validity period has ended) | high 30 |
|   |  | issue date missing or in the future | low 5 |

Checks 2 and 3 run only when the chosen scheme has reviewed rules. Checks 4 and
6 need the prepared files and photo quality, which `DoctorRequest` doesn't carry
yet; `diagnose()` accepts them when core can pass them.

## Name matching

`names.compare(a, b, father)` handles Tamil Nadu conventions:

- the same tokens in any order score 100 ("S Satyajit" vs "Satyajit S");
- initials expand to a full token in the other name, or to the father's name
  (the initial is usually the father's), scoring 92;
- honorifics (Selvi, Thiru, Tmt, Kumari, ...) are ignored;
- otherwise `rapidfuzz.token_set_ratio`. 95 and above is consistent, 85 to 94 a
  minor spelling difference, below 85 different names.

An income certificate issued in a parent's name (its holder matches the father's
name on another document) is normal: it still counts for income, but it is left out
of the name and father's-name comparisons.

Fix messages (`messages.py`) are English; core translates them. They never
include Aadhaar or bank numbers: those fields are never compared.
