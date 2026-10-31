"""India's states and union territories, so a place is read in code and never guessed."""
import re

# Full name -> the other ways people write it, including its own language.
STATES: dict[str, tuple[str, ...]] = {
    "Andhra Pradesh": ("ap", "andhra", "andra pradesh", "ఆంధ్ర ప్రదేశ్", "ఆంధ్రప్రదేశ్"),
    "Arunachal Pradesh": ("ar", "arunachal"),
    "Assam": ("as", "অসম", "আসাম"),
    "Bihar": ("br", "बिहार"),
    "Chhattisgarh": ("cg", "chattisgarh", "छत्तीसगढ़"),
    "Goa": ("ga",),
    "Gujarat": ("gj", "gujrat", "ગુજરાત"),
    "Haryana": ("hr", "हरियाणा"),
    "Himachal Pradesh": ("hp", "himachal", "हिमाचल प्रदेश"),
    "Jharkhand": ("jh", "झारखंड"),
    "Karnataka": ("ka", "ಕರ್ನಾಟಕ"),
    "Kerala": ("kl", "kerela", "കേരളം"),
    "Madhya Pradesh": ("mp", "मध्य प्रदेश"),
    "Maharashtra": ("mh", "maharastra", "महाराष्ट्र"),
    "Manipur": ("mn",),
    "Meghalaya": ("ml",),
    "Mizoram": ("mz",),
    "Nagaland": ("nl",),
    "Odisha": ("od", "or", "orissa", "ଓଡ଼ିଶା"),
    "Punjab": ("pb", "ਪੰਜਾਬ", "पंजाब"),
    "Rajasthan": ("rj", "राजस्थान"),
    "Sikkim": ("sk",),
    "Tamil Nadu": ("tn", "tamilnadu", "tamizh nadu", "tamizhnadu", "தமிழ்நாடு", "தமிழகம்", "तमिलनाडु"),
    "Telangana": ("ts", "tg", "telengana", "తెలంగాణ"),
    "Tripura": ("tr",),
    "Uttar Pradesh": ("up", "उत्तर प्रदेश"),
    "Uttarakhand": ("uk", "uttaranchal", "उत्तराखंड"),
    "West Bengal": ("wb", "bengal", "পশ্চিমবঙ্গ"),
    "Andaman and Nicobar Islands": ("an", "andaman"),
    "Chandigarh": ("ch",),
    "Dadra and Nagar Haveli and Daman and Diu": ("dn", "dd", "daman", "dadra"),
    "Delhi": ("dl", "new delhi", "दिल्ली"),
    "Jammu and Kashmir": ("jk", "j&k", "kashmir"),
    "Ladakh": ("la",),
    "Lakshadweep": ("ld",),
    "Puducherry": ("py", "pondicherry", "pondy"),
}
# Other short forms are everyday words ("up", "as"), or Tanglish and Hindi ones ("la",
# "ka"), so inside a sentence only these count. Alone, any of them is an answer.
SAFE_CODES = {"ap", "tn", "mp", "hp", "wb", "jk", "kl", "mh", "gj", "rj", "hr", "jh", "cg"}

_NAMES = {
    written.lower(): name
    for name, others in STATES.items()
    for written in (name, *others)
}
_LONG_NAMES = sorted((written for written in _NAMES if len(written) > 2), key=len, reverse=True)
_NOT_THIS = re.compile(r"\bnot\s+(?:from\s+|in\s+)?$", re.IGNORECASE)
_EDGES = re.compile(r"^[\s.,:;!?'\"-]+|[\s.,:;!?'\"-]+$")


def indian_state(text: str) -> str | None:
    """The full name, when the whole of `text` is a state. Never a near match."""
    return _NAMES.get(_EDGES.sub("", text).lower())


def states_in_message(text: str) -> list[str]:
    """States a sentence clearly names, skipping any it rules out, as in "not Kerala"."""
    whole = indian_state(text)
    if whole:
        return [whole]
    lowered = text.lower()
    found: dict[int, str] = {}
    for written in [*_LONG_NAMES, *SAFE_CODES]:
        for match in re.finditer(rf"(?<!\w){re.escape(written)}(?!\w)", lowered):
            if not _NOT_THIS.search(lowered[: match.start()]):
                found[match.start()] = _NAMES[written]
    return list(dict.fromkeys(found[start] for start in sorted(found)))
