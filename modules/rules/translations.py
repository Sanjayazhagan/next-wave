"""Tamil and Hindi for every question and button the rule engine sends to core.

Core translates Tamil and Hindi from built-in tables only (app/translations.py), never
through a translation service, so these are merged into those tables. Keys are the
exact English text in questions.QUESTIONS and the button labels in ANSWERS.
"""

TAMIL = {
    # Questions
    "Which state do you live in?": "நீங்கள் எந்த மாநிலத்தில் வசிக்கிறீர்கள்?",
    "What are you studying now? For example: B.E. first year.":
        "நீங்கள் இப்போது என்ன படிக்கிறீர்கள்? உதாரணம்: B.E. முதல் ஆண்டு.",
    "What is your family's yearly income?": "உங்கள் குடும்பத்தின் ஆண்டு வருமானம் என்ன?",
    "What is your community category?": "உங்கள் சமூகப் பிரிவு எது?",
    "Which year of your course are you in?": "நீங்கள் உங்கள் படிப்பின் எந்த ஆண்டில் இருக்கிறீர்கள்?",
    "What is your gender?": "உங்கள் பாலினம் என்ன?",
    "What percentage did you score in your last exam?": "உங்கள் கடைசித் தேர்வில் எத்தனை சதவீதம் பெற்றீர்கள்?",
    "Do you have a disability certificate? If yes, what percentage does it show?":
        "உங்களிடம் மாற்றுத்திறனாளி சான்றிதழ் உள்ளதா? இருந்தால், அதில் எத்தனை சதவீதம் குறிப்பிடப்பட்டுள்ளது?",
    "Did you study from Class 6 to 12 in Tamil Nadu government schools?":
        "நீங்கள் 6 முதல் 12 ஆம் வகுப்பு வரை தமிழ்நாடு அரசுப் பள்ளிகளில் படித்தீர்களா?",
    # Buttons
    "Female": "பெண்",
    "Male": "ஆண்",
    "Transgender": "திருநங்கை / திருநம்பி",
    "Yes, 40% or more": "ஆம், 40% அல்லது அதற்கு மேல்",
    "Yes, under 40%": "ஆம், 40% க்குக் குறைவு",
    "No disability certificate": "மாற்றுத்திறனாளி சான்றிதழ் இல்லை",
    "Yes, all in government schools": "ஆம், அனைத்தும் அரசுப் பள்ளிகளில்",
    "No, not all": "இல்லை, அனைத்தும் இல்லை",
    "Up to ₹1 lakh": "₹1 லட்சம் வரை",
    "Up to ₹2.5 lakh": "₹2.5 லட்சம் வரை",
    "Up to ₹8 lakh": "₹8 லட்சம் வரை",
    "More than ₹8 lakh": "₹8 லட்சத்திற்கு மேல்",
    "Other or not sure": "மற்றவை / தெரியவில்லை",
    "1st year": "முதல் ஆண்டு",
    "2nd year (lateral entry)": "இரண்டாம் ஆண்டு (நேரடி இரண்டாம் ஆண்டுச் சேர்க்கை)",
    "2nd year": "இரண்டாம் ஆண்டு",
    "3rd year": "மூன்றாம் ஆண்டு",
    "4th year": "நான்காம் ஆண்டு",
}

HINDI = {
    # Questions
    "Which state do you live in?": "आप किस राज्य में रहते हैं?",
    "What are you studying now? For example: B.E. first year.":
        "आप अभी क्या पढ़ रहे हैं? उदाहरण: B.E. पहला वर्ष।",
    "What is your family's yearly income?": "आपके परिवार की सालाना आय कितनी है?",
    "What is your community category?": "आपकी सामाजिक श्रेणी क्या है?",
    "Which year of your course are you in?": "आप अपने कोर्स के किस वर्ष में हैं?",
    "What is your gender?": "आपका लिंग क्या है?",
    "What percentage did you score in your last exam?": "आपकी पिछली परीक्षा में कितने प्रतिशत अंक आए?",
    "Do you have a disability certificate? If yes, what percentage does it show?":
        "क्या आपके पास दिव्यांगता प्रमाणपत्र है? यदि हाँ, तो उसमें कितना प्रतिशत लिखा है?",
    "Did you study from Class 6 to 12 in Tamil Nadu government schools?":
        "क्या आपने कक्षा 6 से 12 तक तमिलनाडु के सरकारी स्कूलों में पढ़ाई की?",
    # Buttons
    "Female": "महिला",
    "Male": "पुरुष",
    "Transgender": "ट्रांसजेंडर",
    "Yes, 40% or more": "हाँ, 40% या अधिक",
    "Yes, under 40%": "हाँ, 40% से कम",
    "No disability certificate": "दिव्यांगता प्रमाणपत्र नहीं है",
    "Yes, all in government schools": "हाँ, सभी सरकारी स्कूलों में",
    "No, not all": "नहीं, सभी में नहीं",
    "Up to ₹1 lakh": "₹1 लाख तक",
    "Up to ₹2.5 lakh": "₹2.5 लाख तक",
    "Up to ₹8 lakh": "₹8 लाख तक",
    "More than ₹8 lakh": "₹8 लाख से अधिक",
    "Other or not sure": "अन्य / पता नहीं",
    "1st year": "पहला वर्ष",
    "2nd year (lateral entry)": "दूसरा वर्ष (लेटरल एंट्री)",
    "2nd year": "दूसरा वर्ष",
    "3rd year": "तीसरा वर्ष",
    "4th year": "चौथा वर्ष",
}
