# ── Context Parser — ClairDiag ───────────────────────────────────────────────
# Новий шар (патч п.4): витягує контекстуальні тригери з тексту.
# Не змінює pipeline кроки 1-10, додається поверх як окремий модуль.
import re


# ── Boost rules (патч п.5) ────────────────────────────────────────────────────
# IF context → boost ці діагнози (назви мають збігатись з engine)
CONTEXT_BOOSTS: dict[str, dict[str, float]] = {
    "after_meal": {
        "Gastrite":   0.15,
        "Dyspepsie":  0.15,
        "RGO":        0.10,
    },
    "after_antibiotics": {
        "Dysbiose":   0.20,
        "SII":        0.15,   # Syndrome de l'intestin irritable / IBS
    },
}


def parse_context(text: str) -> dict:
    """
    Витягує контекстуальні тригери з вільного тексту.

    Повертає dict:
    {
        "trigger":  str | None,   # après repas / post-antibiotiques / ...
        "pattern":  str | None,   # répétitif / occasionnel / ...
        "cause":    str | None,   # post-antibiotiques / ...
        "flags": {
            "after_meal":        bool,
            "after_antibiotics": bool,
            "frequency_high":    bool,
            "digestive_pattern": bool,
        }
    }
    """
    t = text.lower()

    # ── after_meal ────────────────────────────────────────────────────────────
    after_meal = bool(re.search(
        r'\b(après (le |les )?(repas|manger|déjeuner|dîner|manger)|'
        r'en mangeant|après avoir mangé|après manger|'
        r'quand je mange|dès que je mange|après le repas)\b',
        t
    ))

    # ── after_antibiotics ────────────────────────────────────────────────────
    after_antibiotics = bool(re.search(
        r'\b(antibiotique|antibiotiques|antibiothérapie|'
        r'amoxicilline|augmentin|azithromycine|doxycycline|'
        r'après (les |une cure d\')?antibio)\b',
        t
    ))

    # ── frequency (chaque fois, toujours, souvent, régulièrement) ─────────────
    frequency_high = bool(re.search(
        r'\b(chaque fois|à chaque fois|toujours|souvent|régulièrement|'
        r'tout le temps|systématiquement|à répétition|encore et encore)\b',
        t
    ))

    # ── digestive_pattern (ballonnements, crampes post-repas, transit) ────────
    digestive_pattern = bool(re.search(
        r'\b(ballonnement|ballonnements|crampes|transit|'
        r'intestin|colon|côlon|digestion|digestif|'
        r'gaz|flatulences|constipation|diarrhée)\b',
        t
    ))

    # ── Будуємо human-readable поля ──────────────────────────────────────────
    trigger: str | None = None
    cause:   str | None = None
    pattern: str | None = None

    if after_meal:
        trigger = "après repas"
    if after_antibiotics:
        cause = "post-antibiotiques"
    if frequency_high:
        pattern = "répétitif"
    elif digestive_pattern:
        pattern = "digestif"

    return {
        "trigger": trigger,
        "pattern": pattern,
        "cause":   cause,
        "flags": {
            "after_meal":        after_meal,
            "after_antibiotics": after_antibiotics,
            "frequency_high":    frequency_high,
            "digestive_pattern": digestive_pattern,
        },
    }


def apply_context_boosts(
    probs: dict[str, float],
    context: dict,
) -> dict[str, float]:
    """
    Застосовує context boosts до словника ймовірностей діагнозів.
    Не змінює діагнози яких немає в probs — тільки підсилює наявні.
    Стеля: 0.95.
    """
    flags = context.get("flags", {})
    boosted = dict(probs)

    for flag_name, boost_map in CONTEXT_BOOSTS.items():
        if not flags.get(flag_name):
            continue
        for diag, delta in boost_map.items():
            if diag in boosted:
                boosted[diag] = min(0.95, boosted[diag] + delta)

    return boosted