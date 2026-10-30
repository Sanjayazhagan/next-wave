"""User-facing text, in English. The channel translates it for each session."""
from dataclasses import dataclass

CONSENT_VERSION = "2026-10-31"
CONSENT = (
    "Vanakkam! I can apply for government schemes for you.\n\n"
    "To do this I will read the documents you send, fill the portal form for you, "
    "and show you everything before anything is submitted. "
    "Your Aadhaar and bank numbers are kept encrypted. "
    "Reply STOP at any time to end.\n\nDo you agree?"
)
DECLINED = "No problem. Nothing was saved. Message me any time to start again."
DOCUMENTS = (
    "Please send photos of your documents, one at a time: marksheet, "
    "income certificate and community certificate. Press Done when finished."
)
DOCUMENTS_NEEDED = "Please send at least one document photo first."
NO_SCHEME = "I could not find a scheme you qualify for right now."
NO_PORTAL = "No portal is set up for this scheme yet, so I have to stop here."
PORTAL_ID = "What is your login ID on this portal?"
CAPTCHA = "The portal is showing this security image. Please reply with the text in it."
OTP = "The portal sent an OTP to your phone. Please reply with it."
HANDOVER = "I'm having trouble with this step, so a helper will take over. You don't need to do anything."
EDIT = "Reply with the number of the item and the new value. For example: 2 120000"
EDIT_INVALID = "I couldn't read that."
ABORTED = "The helper stopped this application. Nothing was submitted."
STOPPED_AT_REVIEW = (
    "Your application is filled and ready on the portal, but I stopped at the "
    "review page. Nothing has been submitted."
)
EARLIER_RECEIPT = "Earlier genuine receipt, from a past application: {number}"
SUBMITTED = "Your application is submitted. Your receipt number is {number}."
SUBMIT_UNCERTAIN = (
    "The application may or may not have gone through, and I won't press "
    "submit twice. A helper must check the portal."
)


@dataclass(frozen=True)
class Question:
    field: str
    text: str
    choices: tuple[tuple[str, str], ...] = ()


# The work split says 4 quick questions but does not list them.
QUESTIONS = (
    Question("state", "Which state do you live in?"),
    Question("course", "What are you studying now? For example: Class 12, or B.E. second year."),
    Question("annual_income", "What is your family's yearly income in rupees?"),
    Question(
        "community",
        "What is your community category?",
        (("bc", "BC / MBC"), ("sc_st", "SC / ST"), ("general", "General")),
    ),
)
