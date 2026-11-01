"""Built-in Tamil and Hindi for every fixed bot message.

These are looked up rather than sent to a translation service, so they are instant
and personal details in a message, such as the review, go nowhere.
"""
import json
import re
from pathlib import Path

from app.conversation import (
    CANCELLED_TEXT,
    ENGLISH,
    FILE_FAILED_TEXT,
    NOT_EXPECTING_FILE_TEXT,
    UNSUPPORTED_TEXT,
    VOICE_FAILED_TEXT,
    VOICE_UNAVAILABLE_TEXT,
    WRONG_FILE_TEXT,
)
from app.graph import messages as m
from app.language import LanguageService
from app.sessions import BUSY_TEXT, FAILED_TEXT, HELPER_TEXT, OLD_BUTTON_TEXT

_QUESTIONS = {question.field: question.text for question in m.QUESTIONS}

TAMIL = {
    m.CONSENT: (
        "வணக்கம்! நான் டாக்கியா. உங்களுக்கான அரசுத் திட்டங்களைக் கண்டறிந்து விண்ணப்பிக்க உதவுவேன்.\n\n"
        "இதற்காக உங்களுடன் உரையாடி, நீங்கள் அனுப்பும் ஆவணங்களைப் படித்து, போர்ட்டல் படிவத்தை நிரப்புவேன். "
        "எதையும் சமர்ப்பிக்கும் முன் அனைத்தையும் உங்களுக்குக் காட்டுவேன்.\n\n"
        "உங்கள் படிப்பு, வருமானம், சமூகம் போன்ற விவரங்கள் உட்பட நமது உரையாடலை AI "
        "வழங்குநர்கள் கையாளுவார்கள். நீங்கள் அனுப்பும் ஆவணப் புகைப்படங்களையும் அவர்கள் "
        "படிப்பார்கள். ஆதார் மற்றும் வங்கி எண்களை முதலில் மறைப்போம், ஆனால் பெயர், வருமானம், "
        "சமூகம் தெரியும், நாங்கள் தவறவிடும் எண்ணும் தெரியலாம். உங்கள் OTP மற்றும் கடவுச்சொல் "
        "அவர்களுக்கு ஒருபோதும் அனுப்பப்படாது. ஆதார் அல்லது வங்கி எண்களை உரையாடலில் "
        "தட்டச்சு செய்ய வேண்டாம்.\n\n"
        "எப்போது வேண்டுமானாலும் நிறுத்த STOP என்றும், மீண்டும் தொடங்க /start என்றும் அனுப்பவும்.\n\n"
        "நீங்கள் ஒப்புக்கொள்கிறீர்களா?"
    ),
    "I agree": "ஒப்புக்கொள்கிறேன்",
    "No thanks": "வேண்டாம்",
    "Done": "முடிந்தது",
    "Approve": "அங்கீகரி",
    "Edit": "திருத்து",
    m.DECLINED: "பரவாயில்லை. எதுவும் சேமிக்கப்படவில்லை. மீண்டும் தொடங்க எப்போது வேண்டுமானாலும் செய்தி அனுப்புங்கள்.",
    m.DOCUMENTS: (
        "உங்கள் ஆவணங்களின் புகைப்படங்களை ஒவ்வொன்றாக அனுப்புங்கள்: மதிப்பெண் பட்டியல், "
        "வருமானச் சான்றிதழ், சமூகச் சான்றிதழ். முடிந்ததும் முடிந்தது என்பதை அழுத்துங்கள்."
    ),
    m.DOCUMENT_RECEIVED: "கிடைத்தது. அடுத்ததை அனுப்புங்கள், அல்லது முடிந்தது என்பதை அழுத்துங்கள்.",
    m.DOCUMENTS_NEEDED: "முதலில் குறைந்தது ஒரு ஆவணப் புகைப்படத்தை அனுப்புங்கள், பிறகு முடிந்தது என்பதை அழுத்துங்கள்.",
    m.SCHEMES_INTRO: "நீங்கள் இந்தத் திட்டங்களுக்குத் தகுதி பெறுகிறீர்கள்:",
    m.SCHEMES_QUESTION: "எதற்கு விண்ணப்பிக்க வேண்டும்?",
    m.FIELD_NEEDED: "படிவத்திற்கு உங்கள் {label} தேவை. தயவுசெய்து அதை அனுப்புங்கள்.",
    m.REVIEW_INTRO: "உங்கள் விண்ணப்பத்தைச் சரிபாருங்கள்:",
    m.REVIEW_FLAGS: "இவற்றைச் சரிபாருங்கள்:",
    m.NO_SCHEME: "இப்போது நீங்கள் தகுதி பெறும் திட்டம் எதையும் என்னால் கண்டறிய முடியவில்லை.",
    m.NO_PORTAL: "இந்தத் திட்டத்திற்கு இன்னும் போர்ட்டல் அமைக்கப்படவில்லை, எனவே இங்கே நிறுத்த வேண்டியுள்ளது.",
    m.PORTAL_ID: "இந்த போர்ட்டலில் உங்கள் உள்நுழைவு ID என்ன?",
    m.CAPTCHA: "போர்ட்டல் இந்தப் பாதுகாப்புப் படத்தைக் காட்டுகிறது. அதில் உள்ள எழுத்துகளை அனுப்புங்கள்.",
    m.OTP: "போர்ட்டல் உங்கள் தொலைபேசிக்கு OTP அனுப்பியுள்ளது. அதை அனுப்புங்கள்.",
    m.HANDOVER: "இந்தப் படியில் எனக்குச் சிரமமாக உள்ளது, எனவே ஓர் உதவியாளர் தொடர்வார். நீங்கள் எதுவும் செய்ய வேண்டாம்.",
    m.EDIT: "உருப்படியின் எண்ணையும் புதிய மதிப்பையும் அனுப்புங்கள். எடுத்துக்காட்டு: 2 120000",
    m.EDIT_INVALID: "அதை என்னால் புரிந்துகொள்ள முடியவில்லை.",
    m.ABORTED: "உதவியாளர் இந்த விண்ணப்பத்தை நிறுத்திவிட்டார். எதுவும் சமர்ப்பிக்கப்படவில்லை.",
    m.STOPPED_AT_REVIEW: (
        "உங்கள் விண்ணப்பம் நிரப்பப்பட்டு போர்ட்டலில் தயாராக உள்ளது, ஆனால் சரிபார்ப்புப் பக்கத்தில் "
        "நிறுத்திவிட்டேன். எதுவும் சமர்ப்பிக்கப்படவில்லை."
    ),
    m.EARLIER_RECEIPT: "முந்தைய விண்ணப்பத்தின் உண்மையான ரசீது: {number}",
    m.CAPTCHA_LINK: "போர்டலில் பாதுகாப்பு சரிபார்ப்பு தேவை. இந்த தனிப்பட்ட இணைப்பைத் திறந்து, நீங்களே முடித்து, பிறகு Done அழுத்தவும்.",
    m.SUBMIT_LINK: "இந்த தனிப்பட்ட இணைப்பைத் திறந்து, உங்கள் படிவத்தைச் சரிபார்த்து, நீங்களே Submit அழுத்தவும். இது ஒரு முறை மட்டும், 10 நிமிடங்களுக்கு வேலை செய்யும். பிறகு Done அழுத்தவும்.",
    m.SUBMIT_LINK_ENDED: "அந்த இணைப்பை இனி பயன்படுத்த முடியாது, சமர்ப்பிப்பு உறுதி செய்யப்படவில்லை.",
    m.SUBMITTED: "உங்கள் விண்ணப்பம் சமர்ப்பிக்கப்பட்டது. உங்கள் ரசீது எண் {number}.",
    _QUESTIONS["state"]: "நீங்கள் எந்த மாநிலத்தில் வசிக்கிறீர்கள்?",
    _QUESTIONS["course"]: "இப்போது என்ன படிக்கிறீர்கள்? எடுத்துக்காட்டு: 12ஆம் வகுப்பு, அல்லது B.E. இரண்டாம் ஆண்டு.",
    _QUESTIONS["annual_income"]: "உங்கள் குடும்பத்தின் ஆண்டு வருமானம் எத்தனை ரூபாய்?",
    _QUESTIONS["community"]: "உங்கள் சமூகப் பிரிவு எது?",
    "General": "பொதுப் பிரிவு",
    m.CONFIRM_INTRO: "இந்த விவரங்களைச் சரிபாருங்கள்:",
    m.CONFIRM_QUESTION: "எல்லாம் சரியா?",
    "Yes, correct": "ஆம், சரி",
    "Change": "மாற்று",
    "State:": "மாநிலம்:",
    "Studying:": "படிப்பு:",
    "Family yearly income:": "குடும்ப ஆண்டு வருமானம்:",
    "Community:": "சமூகம்:",
    BUSY_TEXT: "கடைசிப் படியில் இன்னும் வேலை செய்கிறேன். உங்கள் உதவி தேவைப்படும்போது செய்தி அனுப்புவேன்.",
    HELPER_TEXT: "ஓர் உதவியாளர் உங்கள் விண்ணப்பத்தில் பணியாற்றுகிறார். முடிந்ததும் செய்தி அனுப்புவேன்.",
    OLD_BUTTON_TEXT: "அந்தப் பொத்தான் முந்தைய செய்தியைச் சேர்ந்தது. சமீபத்திய செய்தியில் உள்ளதைப் பயன்படுத்துங்கள்.",
    FAILED_TEXT: (
        "என் பக்கத்தில் ஏதோ தவறு நடந்துவிட்டது. உங்கள் முன்னேற்றம் சேமிக்கப்பட்டுள்ளது. "
        "ஏதேனும் செய்தி அனுப்புங்கள், நிறுத்திய இடத்திலிருந்து மீண்டும் முயல்கிறேன்."
    ),
    CANCELLED_TEXT: "நிறுத்தப்பட்டது. மீண்டும் தொடங்க எப்போது வேண்டுமானாலும் செய்தி அனுப்புங்கள்.",
    NOT_EXPECTING_FILE_TEXT: "இப்போது நான் கோப்பை எதிர்பார்க்கவில்லை.",
    WRONG_FILE_TEXT: "புகைப்படம் அல்லது PDF அனுப்புங்கள்.",
    FILE_FAILED_TEXT: "அந்தக் கோப்பைப் பெற முடியவில்லை. மீண்டும் அனுப்புங்கள்.",
    VOICE_UNAVAILABLE_TEXT: "இன்னும் குரல் செய்திகளைக் கேட்க முடியாது. தட்டச்சு செய்யுங்கள்.",
    VOICE_FAILED_TEXT: "அந்தக் குரல் செய்தியைப் புரிந்துகொள்ள முடியவில்லை. மீண்டும் முயலுங்கள் அல்லது தட்டச்சு செய்யுங்கள்.",
    UNSUPPORTED_TEXT: "அந்த வகைச் செய்தியைப் படிக்க முடியாது. தட்டச்சு செய்யுங்கள்.",
}

HINDI = {
    m.CONSENT: (
        "नमस्ते! मैं डाकिया हूँ। मैं आपके लिए सरकारी योजनाएँ ढूँढकर उनमें आवेदन करने में मदद कर सकता हूँ।\n\n"
        "इसके लिए मैं आपसे बात करूँगा, आपके भेजे दस्तावेज़ पढ़ूँगा और पोर्टल का फ़ॉर्म भरूँगा। "
        "कुछ भी जमा करने से पहले सब कुछ आपको दिखाऊँगा।\n\n"
        "आपकी पढ़ाई, आय और समुदाय जैसी जानकारी समेत हमारी बातचीत AI कंपनियाँ संभालती हैं। "
        "आपके भेजे दस्तावेज़ों की फ़ोटो भी वे पढ़ती हैं। हम आधार और बैंक नंबर पहले छिपा देते "
        "हैं, लेकिन नाम, आय और समुदाय दिखते हैं, और कोई छूटा नंबर भी दिख सकता है। आपके OTP "
        "और पासवर्ड उन्हें कभी नहीं भेजे जाते। कृपया आधार या बैंक नंबर चैट में न लिखें।\n\n"
        "कभी भी रोकने के लिए STOP और दोबारा शुरू करने के लिए /start भेजें।\n\n"
        "क्या आप सहमत हैं?"
    ),
    "I agree": "मैं सहमत हूँ",
    "No thanks": "नहीं, धन्यवाद",
    "Done": "हो गया",
    "Approve": "स्वीकृत करें",
    "Edit": "बदलें",
    m.DECLINED: "कोई बात नहीं। कुछ भी सहेजा नहीं गया। दोबारा शुरू करने के लिए कभी भी संदेश भेजें।",
    m.DOCUMENTS: (
        "कृपया अपने दस्तावेज़ों की फ़ोटो एक-एक करके भेजें: मार्कशीट, आय प्रमाण पत्र और "
        "जाति प्रमाण पत्र। पूरा होने पर हो गया दबाएँ।"
    ),
    m.DOCUMENT_RECEIVED: "मिल गया। अगला भेजें, या हो गया दबाएँ।",
    m.DOCUMENTS_NEEDED: "कृपया पहले कम से कम एक दस्तावेज़ की फ़ोटो भेजें, फिर हो गया दबाएँ।",
    m.SCHEMES_INTRO: "आप इन योजनाओं के लिए पात्र हैं:",
    m.SCHEMES_QUESTION: "मैं किसके लिए आवेदन करूँ?",
    m.FIELD_NEEDED: "फ़ॉर्म में आपकी {label} चाहिए। कृपया भेजें।",
    m.REVIEW_INTRO: "कृपया अपना आवेदन जाँच लें:",
    m.REVIEW_FLAGS: "कृपया इन्हें जाँचें:",
    m.NO_SCHEME: "अभी मुझे ऐसी कोई योजना नहीं मिली जिसके लिए आप पात्र हों।",
    m.NO_PORTAL: "इस योजना के लिए अभी पोर्टल तैयार नहीं है, इसलिए मुझे यहीं रुकना होगा।",
    m.PORTAL_ID: "इस पोर्टल पर आपकी लॉगिन ID क्या है?",
    m.CAPTCHA: "पोर्टल यह सुरक्षा चित्र दिखा रहा है। कृपया उसमें लिखा पाठ भेजें।",
    m.OTP: "पोर्टल ने आपके फ़ोन पर OTP भेजा है। कृपया उसे भेजें।",
    m.HANDOVER: "इस चरण में मुझे दिक्कत हो रही है, इसलिए एक सहायक इसे संभालेगा। आपको कुछ करने की ज़रूरत नहीं है।",
    m.EDIT: "आइटम का नंबर और नया मान भेजें। उदाहरण: 2 120000",
    m.EDIT_INVALID: "मैं वह समझ नहीं पाया।",
    m.ABORTED: "सहायक ने यह आवेदन रोक दिया। कुछ भी जमा नहीं किया गया।",
    m.STOPPED_AT_REVIEW: (
        "आपका आवेदन भरकर पोर्टल पर तैयार है, लेकिन मैं समीक्षा पेज पर रुक गया। "
        "कुछ भी जमा नहीं किया गया है।"
    ),
    m.EARLIER_RECEIPT: "पिछले आवेदन की असली रसीद: {number}",
    m.CAPTCHA_LINK: "पोर्टल को सुरक्षा जाँच चाहिए। यह निजी लिंक खोलें, इसे खुद पूरा करें, फिर Done दबाएँ।",
    m.SUBMIT_LINK: "यह निजी लिंक खोलें, अपना फ़ॉर्म जाँचें और Submit खुद दबाएँ। यह एक बार, 10 मिनट तक चलेगा। फिर Done दबाएँ।",
    m.SUBMIT_LINK_ENDED: "वह लिंक अब इस्तेमाल नहीं हो सकता, और जमा होने की पुष्टि नहीं हुई।",
    m.SUBMITTED: "आपका आवेदन जमा हो गया है। आपकी रसीद संख्या {number} है।",
    _QUESTIONS["state"]: "आप किस राज्य में रहते हैं?",
    _QUESTIONS["course"]: "आप अभी क्या पढ़ रहे हैं? उदाहरण: कक्षा 12, या B.E. दूसरा वर्ष।",
    _QUESTIONS["annual_income"]: "आपके परिवार की सालाना आय कितने रुपये है?",
    _QUESTIONS["community"]: "आपकी सामाजिक श्रेणी क्या है?",
    "General": "सामान्य",
    m.CONFIRM_INTRO: "कृपया ये जानकारी जाँच लें:",
    m.CONFIRM_QUESTION: "क्या सब सही है?",
    "Yes, correct": "हाँ, सही है",
    "Change": "बदलें",
    "State:": "राज्य:",
    "Studying:": "पढ़ाई:",
    "Family yearly income:": "परिवार की सालाना आय:",
    "Community:": "समुदाय:",
    BUSY_TEXT: "मैं अभी पिछले चरण पर काम कर रहा हूँ। ज़रूरत होने पर आपको संदेश भेजूँगा।",
    HELPER_TEXT: "एक सहायक आपके आवेदन पर काम कर रहा है। पूरा होने पर मैं संदेश भेजूँगा।",
    OLD_BUTTON_TEXT: "वह बटन पिछले संदेश का है। कृपया नवीनतम संदेश का बटन इस्तेमाल करें।",
    FAILED_TEXT: (
        "मेरी तरफ़ से कुछ गड़बड़ हो गई। आपकी प्रगति सुरक्षित है। "
        "कोई भी संदेश भेजें, मैं वहीं से दोबारा कोशिश करूँगा।"
    ),
    CANCELLED_TEXT: "रोक दिया गया। दोबारा शुरू करने के लिए कभी भी संदेश भेजें।",
    NOT_EXPECTING_FILE_TEXT: "मुझे अभी किसी फ़ाइल की ज़रूरत नहीं है।",
    WRONG_FILE_TEXT: "कृपया फ़ोटो या PDF भेजें।",
    FILE_FAILED_TEXT: "वह फ़ाइल नहीं मिल पाई। कृपया दोबारा भेजें।",
    VOICE_UNAVAILABLE_TEXT: "मैं अभी वॉइस नोट नहीं सुन सकता। कृपया लिखकर भेजें।",
    VOICE_FAILED_TEXT: "मैं वह वॉइस नोट समझ नहीं पाया। दोबारा कोशिश करें या लिखकर भेजें।",
    UNSUPPORTED_TEXT: "मैं इस तरह का संदेश नहीं पढ़ सकता। कृपया लिखकर भेजें।",
}

# Machine-translated by scripts/generate_translations.py and not yet reviewed.
_GENERATED = Path(__file__).with_name("translations_generated.json")
BUILT_IN = {
    "ta": TAMIL,
    "hi": HINDI,
    **json.loads(_GENERATED.read_text(encoding="utf-8")),
}


def _rule_engine_tables() -> dict[str, dict[str, str]]:
    """Tamil and Hindi for the rule engine's scheme questions, when that module is merged."""
    try:
        from modules.rules.translations import HINDI as RULES_HINDI
        from modules.rules.translations import TAMIL as RULES_TAMIL
    except Exception:  # Not merged, or failed to load: its questions stay in English.
        return {}
    return {"ta": RULES_TAMIL, "hi": RULES_HINDI}


# Kept apart from BUILT_IN, which holds the same messages in every language.
_LOOKUP = {
    language: {**_rule_engine_tables().get(language, {}), **table}  # Core's own entries win.
    for language, table in BUILT_IN.items()
}
_PLACEHOLDER = re.compile(r"\{\w+\}")
_ESCAPED_PLACEHOLDER = re.compile(r"\\\{\w+\\\}")


def translate_fixed(text: str, language: str) -> str:
    """Swap every known message inside `text`, longest first."""
    table = _LOOKUP.get(language)
    if table is None:
        return text
    for english in sorted(table, key=len, reverse=True):
        translated = table[english]
        if "{" not in english:
            text = text.replace(english, translated)
            continue
        pattern = _ESCAPED_PLACEHOLDER.sub("(.+?)", re.escape(english))
        text = re.sub(
            pattern,
            lambda match: _PLACEHOLDER.sub(lambda _: match[1], translated),
            text,
        )
    return text


async def localize(text: str, language: str, service: LanguageService) -> str:
    if language == ENGLISH:
        return text
    if language in BUILT_IN:
        return translate_fixed(text, language)
    return await service.translate(text, ENGLISH, language)
