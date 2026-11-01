"""Form controls that need the user's own word, never the model's."""
import re

from contracts.browser import NodeOption, PageNode, Snapshot


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def usable(options: list[NodeOption]) -> list[NodeOption]:
    """What a person can pick: nothing disabled, and not the empty "Choose..." line."""
    return [option for option in options if not option.disabled and option.value != ""]


def match_option(options: list[NodeOption], value: str) -> NodeOption | None:
    """The option a stored answer plainly names, by value or by label. Never a guess."""
    wanted = _norm(value)
    if not wanted:
        return None
    for option in usable(options):
        if wanted in (_norm(option.value), _norm(option.label)):
            return option
    return None


def pending_consent(snapshot: Snapshot) -> PageNode | None:
    """A required box that is still unticked. Only the user may tick it."""
    return next(
        (n for n in snapshot.nodes if n.role == "checkbox" and n.required and not n.checked),
        None,
    )


def pending_choice(snapshot: Snapshot) -> PageNode | None:
    """A required drop-down still on its "Choose..." line. The user picks; the model never does."""
    return next(
        (n for n in snapshot.nodes if usable(n.options) and n.required and not n.value), None
    )
