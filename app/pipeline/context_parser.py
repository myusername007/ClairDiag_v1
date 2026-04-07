# ── Context Parser — ClairDiag (patch final) ─────────────────────────────────
# Розширений: frequency, chronology, aggravation_time, after_food, post_medication,
# night_worsening + symptom_trace support
import re


CONTEXT_BOOSTS: dict[str, dict[str, float]] = {
    "after_meal": {
        "Gastrite":   0.15,
        "Dyspepsie":  0.15,
        "RGO":        0.10,
    },
    "after_antibiotics": {
        "Dysbiose":                 0.05,   # déjà haut — léger boost
        "Clostridioides difficile": 0.30,
        "Infection intestinale":    0.15,
    },
}

# Penalties appliquées si contexte détecté
CONTEXT_PENALTIES: dict[str, dict[str, float]] = {
    "after_antibiotics": {
        "SII":      0.55,   # SII multiplié par 0.45 — diagnostic chronique inapproprié en phase aiguë
    },
}


def parse_context(text: str) -> dict:
    """
    Витягує повний клінічний контекст з вільного тексту.

    Повертає:
    {
        "trigger":           str | None,
        "pattern":           str | None,
        "cause":             str | None,
        "frequency":         str | None,   # "chaque fois" | "souvent" | "parfois"
        "chronology":        str | None,   # "depuis 3 jours" | "depuis plusieurs semaines"
        "aggravation_time":  str | None,   # "la nuit" | "le matin" | "après repas"
        "after_food":        bool,
        "post_medication":   bool,
        "night_worsening":   bool,
        "flags": { ... }
    }
    """
    t = text.lower()

    # ── after_meal ────────────────────────────────────────────────────────────
    after_meal = bool(re.search(
        r'\b(après (le |les )?(repas|manger|déjeuner|dîner)|'
        r'en mangeant|après avoir mangé|après manger|apres manger|'
        r'apres avoir mange|après repas|'
        r'quand je mange|dès que je mange|à chaque repas|après chaque repas)\b',
        t
    ))

    # ── after_antibiotics ────────────────────────────────────────────────────
    after_antibiotics = bool(re.search(
        r'\b(antibiotique|antibiotiques|antibiothérapie|'
        r'amoxicilline|augmentin|azithromycine|doxycycline|'
        r'après (les |une cure d\')?antibio|après antibiotiques|'
        r'depuis (les |mes )?antibiotiques|suite aux antibiotiques)\b',
        t
    ))

    # ── frequency ─────────────────────────────────────────────────────────────
    freq_high = bool(re.search(
        r'\b(chaque fois|à chaque fois|toujours|tout le temps|'
        r'systématiquement|à répétition|encore et encore|à chaque repas)\b', t
    ))
    freq_often = bool(re.search(r'\b(souvent|régulièrement|fréquemment|plusieurs fois)\b', t))
    freq_sometimes = bool(re.search(r'\b(parfois|de temps en temps|occasionnellement)\b', t))

    if freq_high:
        frequency = "chaque fois"
    elif freq_often:
        frequency = "souvent"
    elif freq_sometimes:
        frequency = "parfois"
    else:
        frequency = None

    # ── chronology (depuis) ───────────────────────────────────────────────────
    chrono_match = re.search(
        r'depuis\s+([\w\s]+?)(?=[,;]|\s+(?:je|j\'|il|et)|$)', t
    )
    chronology = None
    if chrono_match:
        raw_chrono = chrono_match.group(1).strip()
        # Нормалізуємо
        if re.search(r'\b(semaine|semaines)\b', raw_chrono):
            chronology = "depuis plusieurs semaines"
        elif re.search(r'\b(mois)\b', raw_chrono):
            chronology = "depuis plusieurs mois"
        elif re.search(r'\b(jour|jours)\b', raw_chrono):
            chronology = "depuis plusieurs jours"
        elif re.search(r'\b(hier|avant-hier)\b', raw_chrono):
            chronology = "depuis hier"
        elif raw_chrono:
            chronology = f"depuis {raw_chrono}"[:40]

    # ── aggravation_time — après repas prioritaire sur la nuit ───────────────
    if re.search(r'\b(après (le )?repas|après manger|apres manger|à chaque repas)\b', t):
        aggravation_time = "après repas"
    elif re.search(r'\b(le matin|au réveil|au matin|dès le matin)\b', t):
        aggravation_time = "le matin"
    elif re.search(r'\b(à l\'effort|en marchant|en courant|lors de l\'effort)\b', t):
        aggravation_time = "à l'effort"
    elif re.search(r'\b(la nuit|nocturne|nocturnes|de nuit|la nuit surtout)\b', t):
        aggravation_time = "la nuit"
    else:
        aggravation_time = None

    # ── night_worsening ───────────────────────────────────────────────────────
    night_worsening = bool(re.search(
        r'\b(la nuit|nocturne|nocturnes|pire la nuit|'
        r'empire la nuit|réveillé|se réveille|insomnie)\b', t
    ))

    # ── digestive_pattern ────────────────────────────────────────────────────
    digestive_pattern = bool(re.search(
        r'\b(ballonnement|ballonnements|crampes|transit|'
        r'intestin|colon|côlon|digestion|digestif|'
        r'gaz|flatulences|constipation|diarrhée|selles)\b', t
    ))

    # ── Human-readable fields ─────────────────────────────────────────────────
    trigger: str | None = None
    cause:   str | None = None
    pattern: str | None = None

    if after_meal:
        trigger = "après repas"
    if after_antibiotics:
        cause = "post-antibiotiques"
    if frequency == "chaque fois":
        pattern = "répétitif"
    elif digestive_pattern:
        pattern = "digestif"
    elif frequency:
        pattern = frequency

    return {
        "trigger":          trigger,
        "pattern":          pattern,
        "cause":            cause,
        "frequency":        frequency,
        "chronology":       chronology,
        "aggravation_time": aggravation_time,
        "after_food":       after_meal,
        "post_medication":  after_antibiotics,
        "night_worsening":  night_worsening,
        "flags": {
            "after_meal":        after_meal,
            "after_antibiotics": after_antibiotics,
            "frequency_high":    freq_high,
            "digestive_pattern": digestive_pattern,
            "night_worsening":   night_worsening,
        },
    }


def apply_context_boosts(
    probs: dict[str, float],
    context: dict,
) -> dict[str, float]:
    flags = context.get("flags", {})
    boosted = dict(probs)

    for flag_name, boost_map in CONTEXT_BOOSTS.items():
        if not flags.get(flag_name):
            continue
        for diag, delta in boost_map.items():
            # Boost: якщо діагноз є — збільшуємо; якщо немає — додаємо
            current = boosted.get(diag, 0.0)
            boosted[diag] = min(0.95, current + delta)

    for flag_name, penalty_map in CONTEXT_PENALTIES.items():
        if not flags.get(flag_name):
            continue
        for diag, multiplier in penalty_map.items():
            if diag in boosted:
                boosted[diag] = round(boosted[diag] * multiplier, 3)

    return boosted