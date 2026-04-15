# ── Branch Modifiers — Clinical Context Weighting Layer ──────────────────────
# VERSION: v1.1 — two-level ACS logic per TZ
from __future__ import annotations
import logging

logger = logging.getLogger("clairdiag.branch_modifiers")

_BOOST_STRONG    = 0.25
_BOOST_MODERATE  = 0.15
_PENALTY_STRONG  = 0.30
_PENALTY_MODERATE = 0.15
_MAX_PROB = 0.90
_MIN_PROB = 0.01

# ── Cardiac symptom classifiers (ТЗ) ─────────────────────────────────────────

STRONG_CARDIAC = frozenset({
    "douleur thoracique", "douleur thoracique intense", "oppression thoracique",
    "irradiation bras gauche", "irradiation machoire", "irradiation dos",
    "sueurs froides", "syncope", "oppression",
})

SUPPORTIVE_CARDIAC = frozenset({
    "essoufflement", "nausées", "fatigue", "palpitations", "dyspnée",
})

WEAK_CARDIAC = frozenset({
    "douleur vague poitrine", "gêne thoracique", "gêne poitrine",
    "inconfort thoracique", "douleur poitrine légère", "douleur légère poitrine",
})

_HARD_STRONG = frozenset({
    "douleur thoracique", "douleur thoracique intense", "oppression thoracique",
    "oppression", "irradiation bras gauche", "irradiation machoire",
})


def _classify_acs_level(symptom_set: set[str]) -> str | None:
    """
    Retourne "emergency" | "urgent" | None selon qualité des symptômes cardiaques.

    EMERGENCY:
      - 2+ strong markers
      - 1 strong + 2+ supportive
      - hard_strong + 1 supportive non-fatigue

    URGENT:
      - weak chest + 1+ supportive
      - 1 strong isolé
      - 2+ supportive sans strong
    """
    strong   = symptom_set & STRONG_CARDIAC
    support  = symptom_set & SUPPORTIVE_CARDIAC
    weak     = symptom_set & WEAK_CARDIAC
    hard_str = symptom_set & _HARD_STRONG

    # EMERGENCY
    if len(strong) >= 2:
        return "emergency"
    if len(strong) >= 1 and len(support) >= 2:
        return "emergency"
    if hard_str and strong and (support - {"fatigue"}):
        return "emergency"

    # URGENT
    if weak and support:
        return "urgent"
    # strong isolé SEULEMENT si accompagné d'au moins 1 supportive
    # douleur thoracique seule → pas de branch activation
    if strong and support:
        return "urgent"
    if len(support) >= 2:
        return "urgent"

    return None


BRANCH_DEFINITIONS: dict[str, dict] = {

    # ── 1a. ACS EMERGENCY ────────────────────────────────────────────────────
    "cardio_acs_emergency": {
        "any_of": [
            frozenset({"douleur thoracique", "irradiation bras gauche"}),
            frozenset({"douleur thoracique", "irradiation machoire"}),
            frozenset({"douleur thoracique intense", "sueurs froides"}),
            frozenset({"douleur thoracique", "sueurs froides"}),
            frozenset({"douleur thoracique intense", "essoufflement"}),
            frozenset({"oppression thoracique", "essoufflement", "nausées"}),
            frozenset({"douleur thoracique", "syncope"}),
            frozenset({"douleur thoracique", "oppression", "essoufflement"}),
        ],
        "boosts": {
            "Infarctus du myocarde": _BOOST_STRONG,
            "Angor":                 _BOOST_MODERATE,
            "Embolie pulmonaire":    _BOOST_MODERATE,
        },
        "penalties": {
            "Gastrite":        _PENALTY_STRONG,
            "RGO":             _PENALTY_STRONG,
            "Bronchite":       _PENALTY_MODERATE,
            "Rhinopharyngite": _PENALTY_STRONG,
        },
        "forbid_top1":    {"Gastrite", "RGO", "Rhinopharyngite", "Bronchite"},
        "do_not_miss":    ["Infarctus du myocarde", "Embolie pulmonaire"],
        "min_urgency":    "élevé",
        "forbid_decisions": set(),
    },

    # ── 1b. ACS URGENT ───────────────────────────────────────────────────────
    "cardio_acs_urgent": {
        "any_of": [
            frozenset({"douleur vague poitrine", "essoufflement"}),
            frozenset({"gêne thoracique", "essoufflement"}),
            frozenset({"douleur thoracique", "fatigue"}),
            frozenset({"gêne poitrine", "palpitations"}),
            frozenset({"essoufflement", "fatigue", "douleur vague poitrine"}),
            frozenset({"douleur poitrine légère", "essoufflement"}),
            frozenset({"inconfort thoracique", "fatigue"}),
        ],
        "boosts": {
            "Angor":              _BOOST_MODERATE,
            "Embolie pulmonaire": _BOOST_MODERATE,
        },
        "penalties": {
            "Gastrite":        _PENALTY_MODERATE,
            "Rhinopharyngite": _PENALTY_STRONG,
        },
        "forbid_top1":    {"Gastrite", "RGO", "Rhinopharyngite"},
        "do_not_miss":    ["Angor", "Embolie pulmonaire", "Infarctus du myocarde"],
        "min_urgency":    "modéré",
        "forbid_decisions": {"LOW_RISK_MONITOR", "MEDICAL_REVIEW"},
    },

    # ── 2. Dissection aortique ────────────────────────────────────────────────
    "cardio_dissection": {
        "any_of": [
            frozenset({"douleur thoracique", "douleur dos", "sensation déchirure"}),
            frozenset({"douleur thoracique", "douleur dorsale", "déchirure"}),
            frozenset({"douleur thoracique intense", "irradiation dos"}),
        ],
        "boosts":   {"Infarctus du myocarde": _BOOST_MODERATE},
        "penalties": {"Gastrite": _PENALTY_STRONG, "RGO": _PENALTY_STRONG, "Angor": _PENALTY_MODERATE},
        "forbid_top1":    {"Gastrite", "RGO", "Bronchite", "Rhinopharyngite"},
        "do_not_miss":    ["Dissection aortique", "Infarctus du myocarde"],
        "min_urgency":    "élevé",
        "forbid_decisions": set(),
    },

    # ── 3. AVC / AIT ──────────────────────────────────────────────────────────
    "neuro_avc": {
        "any_of": [
            frozenset({"faiblesse bras", "difficulté parler"}),
            frozenset({"faiblesse unilatérale", "trouble parole"}),
            frozenset({"asymétrie visage", "faiblesse bras"}),
            frozenset({"paralysie", "trouble parole"}),
            frozenset({"déficit neurologique", "apparition soudaine"}),
        ],
        "boosts":   {"Hypertension": _BOOST_MODERATE},
        "penalties": {
            "Gastrite": _PENALTY_STRONG, "Bronchite": _PENALTY_STRONG,
            "Grippe": _PENALTY_MODERATE, "Anémie": _PENALTY_MODERATE,
        },
        "forbid_top1": {"Gastrite", "Bronchite", "Grippe", "Rhinopharyngite", "Anémie", "RGO", "SII"},
        "do_not_miss": ["AVC ischémique", "AIT", "Hémorragie cérébrale"],
        "min_urgency": "élevé",
        "forbid_decisions": set(),
    },

    # ── 4. TVP / Embolie pulmonaire ───────────────────────────────────────────
    "thrombo_embolic": {
        "any_of": [
            frozenset({"jambe unilatérale gonflée", "douleur mollet"}),
            frozenset({"œdème unilatéral", "douleur mollet"}),
            frozenset({"gonflement jambe", "douleur mollet"}),
            frozenset({"jambe gonflée", "essoufflement"}),
            frozenset({"douleur mollet", "essoufflement"}),
        ],
        "boosts":   {"Embolie pulmonaire": _BOOST_STRONG},
        "penalties": {
            "Insuffisance cardiaque": _PENALTY_MODERATE,
            "Anémie": _PENALTY_STRONG, "Bronchite": _PENALTY_STRONG, "Gastrite": _PENALTY_STRONG,
        },
        "forbid_top1":    {"Anémie", "Bronchite", "Gastrite", "RGO", "Rhinopharyngite", "Grippe"},
        "do_not_miss":    ["TVP", "Embolie pulmonaire"],
        "min_urgency":    "élevé",
        "forbid_decisions": set(),
    },

    # ── 5. Abdomen aigu ───────────────────────────────────────────────────────
    "abdomen_aigu": {
        "any_of": [
            frozenset({"douleur abdominale intense", "fièvre", "vomissements"}),
            frozenset({"douleur abdominale intense", "fièvre", "défense abdominale"}),
            frozenset({"douleur abdominale", "fièvre élevée", "vomissements"}),
        ],
        "boosts":   {"Gastrite": _BOOST_MODERATE},
        "penalties": {
            "Bronchite": _PENALTY_STRONG, "Rhinopharyngite": _PENALTY_STRONG,
            "Anémie": _PENALTY_MODERATE, "RGO": _PENALTY_MODERATE,
        },
        "forbid_top1":    {"Bronchite", "Rhinopharyngite", "Anémie", "Grippe"},
        "do_not_miss":    ["Appendicite", "Péritonite", "Pancréatite aiguë", "Cholécystite"],
        "min_urgency":    "modéré",
        "forbid_decisions": set(),
    },
}


def apply(
    probs: dict[str, float],
    symptoms_compressed: list[str],
) -> tuple[dict[str, float], dict]:
    """
    Applique les branch modifiers. Logique ACS à deux niveaux via _classify_acs_level().
    """
    symptom_set = set(symptoms_compressed)
    modified = dict(probs)

    active_branches: list[str] = []
    do_not_miss_additions: list[str] = []
    forbid_top1: set[str] = set()
    forbid_decisions: set[str] = set()
    min_urgency: str | None = None
    applied_boosts: list[str] = []
    applied_penalties: list[str] = []

    # ACS two-level pre-check
    acs_level = _classify_acs_level(symptom_set)
    acs_branch_override: str | None = None
    if acs_level == "emergency":
        acs_branch_override = "cardio_acs_emergency"
    elif acs_level == "urgent":
        acs_branch_override = "cardio_acs_urgent"

    for branch_name, branch in BRANCH_DEFINITIONS.items():

        # ACS: controlled by classifier, not by any_of alone
        if branch_name in ("cardio_acs_emergency", "cardio_acs_urgent"):
            triggered = (branch_name == acs_branch_override)
        else:
            triggered = False
            if "trigger" in branch:
                triggered = branch["trigger"].issubset(symptom_set)
            elif "any_of" in branch:
                triggered = any(combo.issubset(symptom_set) for combo in branch["any_of"])

        if not triggered:
            continue

        active_branches.append(branch_name)
        logger.info(f"BRANCH MODIFIER active: {branch_name}")

        for diag, boost in branch.get("boosts", {}).items():
            old = modified.get(diag, 0.0)
            new = min(old + boost, _MAX_PROB)
            modified[diag] = new
            if old != new:
                applied_boosts.append(f"{branch_name} → {diag} +{boost:.2f} ({old:.2f}→{new:.2f})")

        for diag, penalty in branch.get("penalties", {}).items():
            if diag in modified:
                old = modified[diag]
                new = max(old - penalty, _MIN_PROB)
                modified[diag] = new
                applied_penalties.append(f"{branch_name} → {diag} -{penalty:.2f} ({old:.2f}→{new:.2f})")

        forbid_top1.update(branch.get("forbid_top1", set()))
        forbid_decisions.update(branch.get("forbid_decisions", set()))

        for item in branch.get("do_not_miss", []):
            if item not in do_not_miss_additions:
                do_not_miss_additions.append(item)

        branch_urgency = branch.get("min_urgency")
        if branch_urgency:
            if min_urgency is None:
                min_urgency = branch_urgency
            elif branch_urgency == "élevé":
                min_urgency = "élevé"

    # Any chest pattern → forbid LOW_RISK_MONITOR + MEDICAL_REVIEW
    if acs_level is not None:
        forbid_decisions.update({"LOW_RISK_MONITOR", "MEDICAL_REVIEW"})
        logger.info(f"ACS pattern ({acs_level}) → forbid LOW_RISK + MEDICAL_REVIEW")

    if active_branches:
        logger.info(
            f"Branch modifiers applied: {active_branches} | "
            f"boosts={len(applied_boosts)} penalties={len(applied_penalties)}"
        )

    return modified, {
        "active_branches":       active_branches,
        "do_not_miss_additions": do_not_miss_additions,
        "forbid_top1":           forbid_top1,
        "forbid_decisions":      forbid_decisions,
        "min_urgency":           min_urgency,
        "applied_boosts":        applied_boosts,
        "applied_penalties":     applied_penalties,
    }


def enforce_forbid_top1(diagnoses: list, forbid_top1: set[str]) -> list:
    """
    Si le top1 est dans forbid_top1 → le descend, monte le premier non-interdit.
    Ne supprime pas le diag — reste dans le différentiel.
    """
    if not forbid_top1 or not diagnoses:
        return diagnoses

    first_valid_idx = next(
        (i for i, d in enumerate(diagnoses) if d.name not in forbid_top1), None
    )
    if first_valid_idx is None or first_valid_idx == 0:
        return diagnoses

    reordered = [diagnoses[first_valid_idx]] + [
        d for i, d in enumerate(diagnoses) if i != first_valid_idx
    ]
    logger.info(
        f"forbid_top1 enforced: {diagnoses[0].name} → pos {first_valid_idx+1}, "
        f"new top1: {reordered[0].name}"
    )
    return reordered