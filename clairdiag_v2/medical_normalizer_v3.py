"""
ClairDiag v3 — Medical Normalizer
Rule-based: free text → medical tokens з пріоритетами.
Використовується для clinical_combinations engine.
"""

import re
from typing import Dict, List, Tuple

# ──────────────────────────────────────────────
# TOKEN MAP: "фраза": (medical_token, priority)
# priority: 1 (низький) → 10 (urgent)
# ──────────────────────────────────────────────

NORMALIZATION_MAP: Dict[str, Tuple[str, int]] = {
    # CARDIAQUE / URGENT
    "ça serre la poitrine":        ("douleur_thoracique_oppressive", 10),
    "serrement poitrine":          ("douleur_thoracique_oppressive", 10),
    "mal à la poitrine":           ("douleur_thoracique", 10),
    "douleur thoracique":          ("douleur_thoracique", 10),
    "poitrine qui fait mal":       ("douleur_thoracique", 10),
    "sueurs froides":              ("sueur_froide", 10),
    "je transpire froid":          ("sueur_froide", 10),
    "essoufflé d'un coup":         ("dyspnee", 10),
    "difficulté à respirer":       ("dyspnee", 10),
    "je n'arrive plus à respirer": ("dyspnee", 10),
    # DERMATOLOGIE
    "bouton":             ("eruption_cutanee", 6),
    "boutons":            ("eruption_cutanee", 6),
    "acné":               ("eruption_cutanee", 6),
    "points rouges":      ("eruption_cutanee", 6),
    "rougeur":            ("eruption_cutanee", 6),
    "rougeurs":           ("eruption_cutanee", 6),
    "plaques":            ("eruption_cutanee", 6),
    "plaque rouge":       ("eruption_cutanee", 6),
    "eczéma":             ("eruption_cutanee", 6),
    "urticaire":          ("eruption_cutanee", 7),
    "ça gratte":          ("prurit", 6),
    "démangeaison":       ("prurit", 6),
    "démangeaisons":      ("prurit", 6),
    "prurit":             ("prurit", 6),
    "peau sèche":         ("secheresse_cutanee", 5),
    "peau très sèche":    ("secheresse_cutanee", 5),
    "sécheresse peau":    ("secheresse_cutanee", 5),
    "irritation peau":    ("eruption_cutanee", 5),
    # ORL
    "rhume":           ("rhinorrhee", 5),
    "nez bouché":      ("congestion_nasale", 5),
    "nez qui coule":   ("rhinorrhee", 5),
    "rhinorrhée":      ("rhinorrhee", 5),
    "mal de gorge":    ("odynophagie", 5),
    "mal à la gorge":  ("odynophagie", 5),
    "gorge irritée":   ("odynophagie", 5),
    "toux":            ("toux", 5),
    "je tousse":       ("toux", 5),
    "petite toux":     ("toux_legere", 4),
    "éternuements":    ("eternuements", 4),
    "voix enrouée":    ("dysphonie", 4),
    "enrouement":      ("dysphonie", 4),
    "oreille bouchée": ("otalgie_legere", 4),
    "sinus bouchés":   ("sinusite_suspecte", 5),
    # DIGESTIF
    "mal au ventre":       ("douleur_abdominale", 6),
    "douleur ventre":      ("douleur_abdominale", 6),
    "ventre gonflé":       ("ballonnements", 5),
    "ballonnements":       ("ballonnements", 5),
    "gaz":                 ("ballonnements", 4),
    "constipation":        ("constipation", 5),
    "constipé":            ("constipation", 5),
    "diarrhée":            ("diarrhee", 5),
    "selles liquides":     ("diarrhee", 5),
    "nausée":              ("nausees", 5),
    "nausées":             ("nausees", 5),
    "envie de vomir":      ("nausees", 5),
    "vomissements":        ("vomissements", 6),
    "brûlures estomac":    ("pyrosis", 5),
    "aigreurs":            ("pyrosis", 5),
    "remontées acides":    ("reflux_gastro_oesophagien", 5),
    "indigestion":         ("dyspepsie", 5),
    # FATIGUE
    "fatigue":             ("fatigue", 5),
    "fatigué":             ("fatigue", 5),
    "fatiguée":            ("fatigue", 5),
    "je suis crevé":       ("fatigue_intense", 6),
    "je suis crevée":      ("fatigue_intense", 6),
    "épuisé":              ("fatigue_intense", 6),
    "épuisée":             ("fatigue_intense", 6),
    "manque d'énergie":    ("fatigue", 5),
    "pas d'énergie":       ("fatigue", 5),
    "à plat":              ("fatigue", 5),
    "vaseux":              ("fatigue", 4),
    "vaseuse":             ("fatigue", 4),
    "faiblesse générale":  ("fatigue", 5),
    # MÉTABOLIQUE / HORMONAL
    "prise de poids":           ("prise_de_poids", 6),
    "j'ai grossi":              ("prise_de_poids", 6),
    "poids qui monte":          ("prise_de_poids", 6),
    "j'ai maigri":              ("perte_de_poids", 6),
    "perte de poids":           ("perte_de_poids", 6),
    "frilosité":                ("intolerance_froid", 5),
    "j'ai toujours froid":      ("intolerance_froid", 5),
    "chute de cheveux":         ("alopecie", 5),
    "je perds mes cheveux":     ("alopecie", 5),
    "soif intense":             ("polydipsie", 6),
    "j'ai très soif":           ("polydipsie", 6),
    "j'urine beaucoup":         ("polyurie", 6),
    "palpitations":             ("palpitations", 6),
    "tremblements":             ("tremblements", 5),
    # MUSCULO-SQUELETTIQUE
    "mal au dos":                  ("lombalgie", 5),
    "lombalgie":                   ("lombalgie", 5),
    "tour de reins":               ("lombalgie", 5),
    "mal à la nuque":              ("cervicalgie", 5),
    "torticolis":                  ("cervicalgie", 5),
    "mal à l'épaule":              ("douleur_epaule", 5),
    "épaule bloquée":              ("raideur_epaule", 5),
    "mal au genou":                ("douleur_genou", 5),
    "mal à la jambe":              ("douleur_membre_inferieur", 5),
    "mal au mollet":               ("douleur_mollet", 5),
    "mal au bras":                 ("douleur_membre_superieur", 5),
    "courbatures":                 ("myalgies", 4),
    "raideur":                     ("raideur_articulaire", 4),
    "entorse":                     ("entorse", 6),
    "claquage":                    ("claquage_musculaire", 6),
    # URINAIRE
    "ça brûle quand j'urine":  ("dysurie", 6),
    "brûlure urinaire":        ("dysurie", 6),
    "brûlures en urinant":     ("dysurie", 6),
    "envie fréquente d'uriner": ("pollakiurie", 6),
    "j'urine tout le temps":   ("pollakiurie", 6),
    "infection urinaire":      ("infection_urinaire_suspecte", 6),
    "urines troubles":         ("urines_troubles", 5),
    # GYNÉCO
    "règles irrégulières":  ("trouble_cycle", 5),
    "retard de règles":     ("amenorrhee_suspecte", 6),
    "douleurs de règles":   ("dysmenorrhee", 5),
    "douleur pelvienne":    ("douleur_pelvienne", 6),
    "pertes blanches":      ("leucorrhees", 4),
    # SOMMEIL / STRESS
    "je dors mal":         ("trouble_sommeil", 5),
    "insomnie":            ("insomnie", 6),
    "réveils nocturnes":   ("reveils_nocturnes", 5),
    "stress":              ("stress", 5),
    "stressé":             ("stress", 5),
    "anxiété":             ("anxiete", 5),
    "angoisse":            ("anxiete", 5),
    "irritable":           ("irritabilite", 4),
    "ruminations":         ("ruminations", 4),
    # VAGUE
    "je ne me sens pas bien":    ("malaise_general", 3),
    "pas la forme":              ("malaise_general", 3),
    "j'ai mal partout":          ("douleurs_diffuses", 3),
    "je sais pas ce que j'ai":   ("malaise_non_specifique", 2),
}

_NEGATION_PREFIXES = ["pas de", "pas", "aucun", "aucune", "jamais", "sans"]


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[^\w\sàâäéèêëîïôöùûüç\-']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_negated(text: str, phrase: str) -> bool:
    idx = text.find(phrase)
    if idx == -1:
        return False
    window = text[max(0, idx - 25):idx]
    return any(neg in window for neg in _NEGATION_PREFIXES)


def normalize_to_medical_tokens(free_text: str) -> Dict:
    """
    Повертає dict з medical tokens, sorted by priority desc.
    Використовується clinical_combinations_engine для match правил.
    """
    text = _normalize(free_text)

    best: Dict[str, int] = {}
    raw_matches: List[Tuple[str, int]] = []

    # Довгі фрази спочатку (greedy matching)
    for phrase in sorted(NORMALIZATION_MAP, key=len, reverse=True):
        token, priority = NORMALIZATION_MAP[phrase]
        if phrase in text and not _is_negated(text, phrase):
            raw_matches.append((token, priority))
            if priority > best.get(token, 0):
                best[token] = priority

    tokens_sorted = [t for t, _ in sorted(best.items(), key=lambda x: x[1], reverse=True)]

    confidence = "high" if len(tokens_sorted) >= 2 else "medium" if tokens_sorted else "low"

    return {
        "tokens": tokens_sorted,
        "raw_matches": raw_matches,
        "confidence": confidence,
    }