# Rule engine (M4)

Decides which schemes a citizen qualifies for, in plain Python, from rules copied
out of official scheme pages. Every answer cites its clause and source URL. **No
LLM runs at decision time.** Core loads it through `app/plugins.py`:

```python
def rank_schemes(request: EligibilityRequest) -> EligibilityResponse
```

It returns eligible schemes first, then ones that need more information, best
benefit first. Schemes the citizen fails are left out. `cited_clause` holds the
verbatim rule and its source URL, or says which details are still needed.

## Why it can't make up criteria

1. `scrape.py` snapshots each official page into `schemes/raw/<scheme_id>/`
   with `meta.json` (`url`, `scraped_at`, `sha256`).
2. `draft_rules.py` (one LLM call per scheme) or a person writes
   `schemes/rules/<scheme_id>.draft.yaml`.
3. A person checks every value against the snapshot, adds a `review:` block and
   renames the file to `<scheme_id>.yaml`.
4. `loader.py` **refuses** any rules file that has no `review:` block, or whose
   clauses don't appear **verbatim** in the snapshot they cite.

If no reviewed file exists, `rank_schemes` isn't exported and core carries on
without the rule engine. If a reviewed file fails a check, the import fails and
core logs the error.

## Schemes

| scheme_id | Portal | Source | Status |
| --- | --- | --- | --- |
| `aicte-pragati-degree` | nsp | myscheme.gov.in/schemes/psgs-deg | reviewed |
| `aicte-saksham-degree` | nsp | myscheme.gov.in/schemes/sak-deg | reviewed |
| `pudhumai-penn` | tn_scholarship | myscheme.gov.in/schemes/pudhumai-penn-scheme | reviewed |
| `tn-postmatric-bc-mbc-dnc` | tn_scholarship | myscheme.gov.in/schemes/pmstn, bcmbcmw.tn.gov.in/welfschemes.htm | reviewed |

Reviewed means every clause was checked word for word against its saved snapshot
(the loader re-checks this on every start) and Satyajit approved the files.

**Demo portal.** The browser worker only knows the practice portal. Set
`DEMO_PORTAL_ID` to its id and every scheme keeps its real name and cited rule,
but the browser is sent to the practice portal. Leave it blank for real portals.

Dropped after checking the sources: the myScheme slug `csss` is J&K's Contributory
Social Security Scheme, not the Central Sector Scholarship, and `pmssc` is Punjab's
SC scholarship. TODO(satyajit): find official pages for the Central Sector Scholarship
and Tamil Nadu's SC post-matric scheme.

## Rules file

```yaml
scheme_id: aicte-pragati-degree
name: ...
portal_id: nsp
benefit_inr: 50000            # per year, from the source
benefit_text: "..."           # verbatim
deadline: null                # or a date, with deadline_clause
required_docs: [marksheet, income, community]
sources:
  - url: https://www.myscheme.gov.in/schemes/psgs-deg
    scraped_at: 2026-10-31
review:
  reviewed_by: satyajit
  reviewed_at: 2026-10-31
rules:
  - id: income-ceiling
    field: annual_income        # a profile key, see common/fields.py
    op: lte                     # eq, ne, in, not_in, lt, lte, gt, gte, between, contains_any
    value: 800000
    clause: "verbatim sentence from the source"
    source: 0                   # index into sources
unmodelled:                     # criteria the engine can't test; shown as "also check"
  - clause: "verbatim criterion"
    source: 0
```

## Matching

- A missing field gives `unknown`; any `fail` makes the scheme `not_eligible`, any
  `unknown` makes it `needs_info`, otherwise `eligible`. A passed deadline adds a
  failing `deadline` result.
- Amounts go through `norm_amount` ("Rs. 2,50,000/-", "2.5 lakh"), communities
  through `norm_category` ("Most Backward Class" → `MBC`), states through a short
  alias list ("TN" → Tamil Nadu).
- Core's community buttons (`bc`, `sc_st`, `general`) each stand for several
  categories; a rule passes only if every category in the group passes.
- `questions.missing_questions(schemes, profile)` lists the unknown fields that
  block the most schemes, with fixed wording and button choices.

## Review workflow

```bash
uv run python -m modules.rules.scrape                       # refresh snapshots
uv run python -m modules.rules.draft_rules <scheme_id>       # needs LLM_* in .env
uv run python -m modules.rules.cli --profile p.json --drafts # try drafts before approving
```
