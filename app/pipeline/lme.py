# ── LME — Lab & Medical Exam Engine (étape 9) ───────────────────────────────
# Entrée : liste de diagnostics (Diagnosis), symptômes, probabilités
# Sortie : Tests(required, optional) + coûts + comparaison
#
# Logique ТЗ :
#   test_score = diagnostic_value / cost   → sélectionner les plus rentables
#   maximum 3 tests en required
#   optional = complémentaires conditionnels (filtrés par symptômes)
#
# Source unique des données : app/data/tests.py

from app.data.tests import (
    TEST_CATALOG,
    TEST_COSTS,
    TEST_COSTS_MIN,
    TEST_COSTS_MAX,
    TEST_EXPLANATIONS,
    TEST_PRESCRIPTION_PROBABILITY,
    DIAGNOSIS_TESTS,
    CONDITIONAL_REQUIRED,
    CONSULTATION_COST,
)
from app.models.schemas import Tests, Cost, Comparison

_MAX_REQUIRED_TESTS: int = 3

# Diagnostics viraux simples — réduire l'agressivité des tests
_VIRAL_SIMPLE: set[str] = {"Grippe", "Rhinopharyngite", "Bronchite", "Allergie"}


def _test_score(test: str, top_diagnoses: list[str]) -> float:
    """
    Score = max(diagnostic_value pour les top diagnostics) / coût.
    Plus le score est élevé, plus le test est rentable.
    """
    catalog_entry = TEST_CATALOG.get(test, {})
    dv = catalog_entry.get("diagnostic_value", {})
    cost = catalog_entry.get("cost", 1)

    # Valeur maximale parmi les top diagnostics
    max_value = max((dv.get(d, 0.0) for d in top_diagnoses), default=0.0)
    if cost == 0:
        return 0.0
    return max_value / cost


def run(
    diagnoses_names: list[str],
    symptom_set: set[str],
    probs: dict[str, float],
) -> tuple[Tests, Cost, Comparison, dict, dict, dict]:
    """
    Sélectionne les tests selon le score valeur/coût.
    Retourne : (Tests, Cost, Comparison, test_explanations, test_probabilities, test_costs)
    """
    # Collecte tous les tests candidats depuis les diagnostics détectés
    required_candidates: set[str] = set()
    optional_candidates: set[str] = set()

    for diag in diagnoses_names:
        tests = DIAGNOSIS_TESTS.get(diag, {})
        for t in tests.get("required", []):
            cond = CONDITIONAL_REQUIRED.get(t)
            if cond is None or symptom_set.intersection(cond):
                required_candidates.add(t)
        for t in tests.get("optional", []):
            cond = CONDITIONAL_REQUIRED.get(t)
            if cond is None or symptom_set.intersection(cond):
                optional_candidates.add(t)

    optional_candidates -= required_candidates

    # ── Sélection LME : top 3 required par score valeur/coût ─────────────────
    top_diag_names = diagnoses_names[:3]  # on limite aux top 3 diagnostics

    # ── Réduction agressivité selon contexte ────────────────────────────────
    top_diag = diagnoses_names[0] if diagnoses_names else ""
    n_symptoms = len(symptom_set)

    is_viral_simple = (
        top_diag in _VIRAL_SIMPLE
        and not any(d not in _VIRAL_SIMPLE for d in diagnoses_names[:2])
    )

    if n_symptoms <= 1:
        max_required = 1   # 1 symptôme → 1 test max
    elif is_viral_simple:
        max_required = 2   # viral simple → 2 tests max
    else:
        max_required = _MAX_REQUIRED_TESTS

    scored_required = sorted(
        required_candidates,
        key=lambda t: _test_score(t, top_diag_names),
        reverse=True,
    )
    selected_required: list[str] = scored_required[:max_required]

    # Les required candidats non sélectionnés passent en optional
    demoted = set(scored_required[_MAX_REQUIRED_TESTS:])
    optional_candidates |= demoted

    required_list = sorted(selected_required)
    optional_list = sorted(optional_candidates)
    standard_set = set(required_list) | optional_candidates

    # ── Calcul des coûts ──────────────────────────────────────────────────────
    required_tests_cost = sum(TEST_COSTS.get(t, 0) for t in selected_required)
    optional_weighted = sum(
        TEST_COSTS.get(t, 0) * TEST_PRESCRIPTION_PROBABILITY.get(t, 0.50)
        for t in optional_candidates
    )
    optimized_cost = CONSULTATION_COST + required_tests_cost
    standard_cost = round(CONSULTATION_COST + required_tests_cost + optional_weighted)
    savings = standard_cost - optimized_cost
    optional_cost = sum(TEST_COSTS.get(t, 0) for t in optional_candidates)

    # ── Fourchettes de prix ───────────────────────────────────────────────────
    opt_min = sum(TEST_COSTS_MIN.get(t, 0) for t in selected_required) + CONSULTATION_COST
    opt_max = sum(TEST_COSTS_MAX.get(t, 0) for t in selected_required) + CONSULTATION_COST
    std_min = opt_min + sum(
        TEST_COSTS_MIN.get(t, 0) * TEST_PRESCRIPTION_PROBABILITY.get(t, 0.5)
        for t in optional_candidates
    )
    std_max = opt_max + sum(
        TEST_COSTS_MAX.get(t, 0) * TEST_PRESCRIPTION_PROBABILITY.get(t, 0.5)
        for t in optional_candidates
    )

    # ── Probabilités de prescription par test ─────────────────────────────────
    test_probabilities: dict[str, int] = {
        t: round(TEST_PRESCRIPTION_PROBABILITY.get(t, 1.0) * 100)
        for t in standard_set
    }

    tests = Tests(required=required_list, optional=optional_list)
    cost = Cost(required=optimized_cost, optional=optional_cost, savings=savings)
    comparison = Comparison(
        standard_tests=sorted(standard_set),
        standard_cost=standard_cost,
        optimized_tests=required_list,
        optimized_cost=optimized_cost,
        savings=savings,
        savings_multiplier=(
            f"~{round(standard_cost / optimized_cost, 1)}x moins cher"
            if optimized_cost > 0 else "—"
        ),
        cost_note=(
            f"Parcours optimisé : ~{opt_min}€–{opt_max}€ | "
            f"Parcours standard : ~{round(std_min)}€–{round(std_max)}€. "
            "Tarifs orientatifs France (secteur 1 / Assurance Maladie). "
            "Sélection basée sur le rapport valeur diagnostique / coût."
        ),
    )

    test_explanations = {t: TEST_EXPLANATIONS[t] for t in required_list if t in TEST_EXPLANATIONS}
    test_costs_out = {t: TEST_COSTS[t] for t in standard_set if t in TEST_COSTS}

    return tests, cost, comparison, test_explanations, test_probabilities, test_costs_out