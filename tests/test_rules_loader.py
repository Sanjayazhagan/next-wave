import pytest

from modules.rules.loader import RulesError, load_file
from tests.rules_helpers import GIRL, INCOME, write_scheme


def test_reviewed_file_loads(tmp_path):
    s = load_file(write_scheme(tmp_path, [GIRL, INCOME]), raw_dir=tmp_path / "raw")
    assert [r.id for r in s.rules] == ["girl", "income"]


def test_file_without_review_is_refused(tmp_path):
    with pytest.raises(RulesError, match="no review block"):
        load_file(write_scheme(tmp_path, [GIRL], review=False), raw_dir=tmp_path / "raw")


def test_clause_not_in_source_is_refused(tmp_path):
    made_up = {**INCOME, "clause": "Family income must be below Rs. 10 lakh."}
    with pytest.raises(RulesError, match="not found verbatim"):
        load_file(write_scheme(tmp_path, [made_up]), raw_dir=tmp_path / "raw")


def test_committed_drafts_are_verbatim_and_unreviewed():
    """The drafts in the repo must still quote their snapshots exactly, and must not load."""
    import yaml

    from modules.rules.loader import SCHEMES_DIR, load_all
    from modules.rules.models import Review, Scheme

    drafts = sorted((SCHEMES_DIR / "rules").glob("*.draft.yaml"))
    for path in drafts:
        scheme = Scheme.model_validate(yaml.safe_load(path.read_text()))
        assert scheme.review is None
        tmp = path.with_suffix(".check.yaml")
        try:
            data = yaml.safe_load(path.read_text())
            data["review"] = Review(reviewed_by="t", reviewed_at="2026-10-31").model_dump(mode="json")
            tmp.write_text(yaml.safe_dump(data, allow_unicode=True))
            load_file(tmp)   # raises if any clause is not verbatim
        finally:
            tmp.unlink(missing_ok=True)
    assert all(not s.scheme_id.endswith("draft") for s in load_all())
