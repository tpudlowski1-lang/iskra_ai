"""Classify questions using the historical Iskra Cloud vocabulary."""
CATEGORIES = (
    ("ANATOMIA_SPOLECZNA", ("relacj", "psychologi", "społecz", "ludz", "socj")),
    ("LOGIKA_I_MATEMATYKA", ("logik", "matematy", "algorytm", "obliczeni")),
    ("FILOZOFIA_I_MADROSC", ("etyk", "filozof", "mądroś", "wartoś", "moral")),
)


def classify_question(question):
    text = question.lower()
    for category, words in CATEGORIES:
        if any(word in text for word in words):
            return category
    return "OGOLNE"
