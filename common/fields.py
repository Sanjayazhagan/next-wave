"""Profile field names, aligned with core.

PROFILE_FIELDS mirrors FIELD_NAMES in core's contracts/profile.py (on the
integrate/browser-product branch): only these go into a Profile. Anything else a
document shows (certificate number, issue date, QR contents) stays on that
ExtractedDocument, where the doctor reads it.
"""

PROFILE_FIELDS = {
    "full_name", "date_of_birth", "gender", "state", "district", "course", "marks_percentage",
    "annual_income", "community", "father_name", "mother_name", "aadhaar_number",
    "bank_account_number", "bank_ifsc",
}

FIELD_KEYS = [
    "full_name", "date_of_birth", "gender", "father_name", "mother_name",
    "community", "annual_income", "state", "district",
    "course", "year_of_study", "institution", "marks_percentage", "exam_year",
    "certificate_number", "issue_date", "aadhaar_last4", "bank_ifsc",
]

# Core's community answers ("BC / MBC", "SC / ST", "General", or the button ids) each
# stand for a group of categories. Keys are compared after norm_text.
COMMUNITY_BUTTONS = {
    "bc / mbc": {"BC", "BCM", "MBC", "DNC", "OBC"},
    "sc / st": {"SC", "SCA", "ST"},
    "general": {"OC", "GEN", "EWS"},
}
# The button ids behind those labels, in case a caller stores the id instead.
COMMUNITY_IDS = {"bc": "bc / mbc", "sc_st": "sc / st", "general": "general"}

# Asked only when a scheme's rules need them (see modules/rules/questions.py).
EXTRA_FIELDS = ["disability_percent", "govt_school_6_to_12"]
