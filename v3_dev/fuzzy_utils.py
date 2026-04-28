"""
ClairDiag v3 — Fuzzy Utils v1.0.0

Нечітке співпадіння для "брудних" текстів пацієнта:
  - орфографічні помилки (cystitte, fievre, briulure)
  - відсутні акценти (douleur lombaire → douleur lombaire)
  - скорочення (pipi, mal dos)

Використовує тільки стандартну бібліотеку — без залежностей.
Порогова подібність: 0.82 (емпірично, медичний контекст).
"""

from difflib import SequenceMatcher
from typing import List, Optional, Tuple


_FUZZY_THRESHOLD = 0.90


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def fuzzy_find_in_text(phrase: str, text: str, threshold: float = _FUZZY_THRESHOLD) -> bool:
    """
    Перевіряє чи є phrase (або схожа) в text.
    Спочатку точний пошук, потім fuzzy по sliding window.
    """
    if phrase in text:
        return True

    words_phrase = phrase.split()
    words_text = text.split()
    n = len(words_phrase)

    if n == 0 or len(words_text) < n:
        return False

    # Sliding window по тексту розміром n слів
    for i in range(len(words_text) - n + 1):
        window = " ".join(words_text[i:i + n])
        if _similarity(phrase, window) >= threshold:
            return True

    # Для однослівних фраз — перевіряємо кожне слово окремо
    if n == 1:
        for word in words_text:
            if _similarity(phrase, word) >= threshold:
                return True

    return False


def fuzzy_check_urgent_triggers(triggers: List[str], text: str) -> Optional[str]:
    """
    Перевіряє urgent triggers з fuzzy matching.
    Повертає перший знайдений тригер або None.
    Точний match завжди пріоритетний.
    """
    # Спочатку точний прохід
    for expr in triggers:
        if expr in text:
            return expr
    # Потім fuzzy (тільки для довших виразів — ≥ 2 слів, щоб уникнути FP)
    for expr in triggers:
        if len(expr.split()) >= 2 and fuzzy_find_in_text(expr, text):
            return expr
    return None


def fuzzy_match_phrase(phrase: str, text: str) -> bool:
    """
    Перевіряє точне або fuzzy співпадіння фрази в тексті.
    Однослівні фрази — тільки точно (уникаємо FP на коротких словах).
    """
    if len(phrase.split()) == 1:
        return phrase in text
    return fuzzy_find_in_text(phrase, text)