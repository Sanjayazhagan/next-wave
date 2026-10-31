"""User-facing text, in English. The channel translates it for each session."""
from dataclasses import dataclass

CHOOSE_LANGUAGE = "Choose your language\nஉங்கள் மொழியைத் தேர்ந்தெடுக்கவும்\nअपनी भाषा चुनें"
# Titles are written in each language, so anyone can read their own option.
LANGUAGE_CHOICES = {
    "en": "English",
    "ta": "தமிழ்",
    "hi": "हिन्दी",
    "te": "తెలుగు",
    "kn": "ಕನ್ನಡ",
    "ml": "മലയാളം",
    "bn": "বাংলা",
    "mr": "मराठी",
    "gu": "ગુજરાતી",
    "pa": "ਪੰਜਾਬੀ",
    "or": "ଓଡ଼ିଆ",
    "ur": "اردو",
}
LANGUAGE_NAMES = {
    "en": "English",
    "ta": "Tamil",
    "hi": "Hindi",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "or": "Odia",
    "ur": "Urdu",
}
LANGUAGE_WORDS = {
    **{name.lower(): code for code, name in LANGUAGE_NAMES.items()},
    **{title.lower(): code for code, title in LANGUAGE_CHOICES.items()},
    "हिंदी": "hi",
    "oriya": "or",
}

CONSENT_VERSION = "2026-10-31c"
CONSENT = (
    "Vanakkam! I'm Dakiya. I can find government schemes for you and apply for them.\n\n"
    "To do this I will chat with you, read the documents you send, fill the portal form "
    "for you, and show you everything before anything is submitted.\n\n"
    "Our chat, including details like your course, income and community, is handled by "
    "AI providers. Your OTPs, passwords, documents, Aadhaar and bank numbers are not "
    "sent to them. Please don't type those numbers into the chat.\n\n"
    "Reply STOP at any time to end, or /start to begin again.\n\nDo you agree?"
)
DECLINED = "No problem. Nothing was saved. Message me any time to start again."
DOCUMENTS = (
    "Please send photos of your documents, one at a time: marksheet, "
    "income certificate and community certificate. Press Done when finished."
)
DOCUMENT_RECEIVED = "Got it. Send the next one, or press Done."
DOCUMENTS_NEEDED = "Please send at least one document photo first, then press Done."
SCHEMES_INTRO = "You qualify for these schemes:"
SCHEMES_QUESTION = "Which one should I apply for?"
FIELD_NEEDED = "The form needs your {label}. Please reply with it."
REVIEW_INTRO = "Please check your application:"
REVIEW_FLAGS = "Please check:"
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


CONFIRM_INTRO = "Please check these details:"
CONFIRM_QUESTION = "Is everything correct?"


@dataclass(frozen=True)
class Question:
    field: str
    label: str  # Shown when the user confirms their details.
    text: str  # The fixed wording, used when the AI chat is unavailable.
    hint: str  # What the AI chat should gather.
    choices: tuple[tuple[str, str], ...] = ()
    digits_only: bool = False


# The work split says 4 quick questions but does not list them.
QUESTIONS = (
    Question("state", "State:", "Which state do you live in?", "the Indian state they live in"),
    Question(
        "course",
        "Studying:",
        "What are you studying now? For example: Class 12, or B.E. second year.",
        "what they are studying now, such as Class 12 or B.E. second year",
    ),
    Question(
        "annual_income",
        "Family yearly income:",
        "What is your family's yearly income in rupees?",
        "family yearly income in rupees, as digits only, such as 120000",
        digits_only=True,
    ),
    Question(
        "community",
        "Community:",
        "What is your community category?",
        "community category, exactly one of: BC / MBC, SC / ST, General",
        choices=(("bc", "BC / MBC"), ("sc_st", "SC / ST"), ("general", "General")),
    ),
)
