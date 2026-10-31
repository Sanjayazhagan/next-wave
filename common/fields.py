"""Profile field keys used by the remote modules, aligned with core.

Core asks for state, course, annual_income and community, and its stand-in uses
full_name and date_of_birth. Values in contracts.profile.ProfileField are strings.
"""

FIELD_KEYS = [
    "full_name", "date_of_birth", "gender", "father_name", "mother_name",
    "community", "annual_income", "state", "district",
    "course", "year_of_study", "institution", "marks_percent", "exam_year",
    "certificate_number", "issue_date", "aadhaar_last4", "bank_ifsc",
]

# Core's community buttons store these values; each stands for a group of categories.
COMMUNITY_BUTTONS = {
    "bc": {"BC", "BCM", "MBC", "DNC", "OBC"},
    "sc_st": {"SC", "SCA", "ST"},
    "general": {"OC", "GEN", "EWS"},
}
