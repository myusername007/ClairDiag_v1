"""
ClairDiag v1.1.0 — Abstract Pattern Evaluator Tests
Module: test_pattern_evaluator
Version: v2.0

Запуск:
  cd clairdiag_v1/v3_dev
  python tests/test_pattern_evaluator.py

  або:
  python -m pytest tests/test_pattern_evaluator.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pattern_evaluator import (
    AbstractPatternsConfig,
    evaluate_abstract_layer,
    hybrid_pre_triage,
)


def get_config():
    return AbstractPatternsConfig()


# ── 9 IND test cases ──────────────────────────────────────────────────────────

def test_ind001_sca_typique():
    """IND-001 — SCA typique 58 ans tabac+HTA → ABS-01 urgent"""
    config = get_config()
    features = {
        "symptoms": ["douleur_thoracique"],
        "demographics": {"age": 58, "sex": "M"},
        "risk_factors": ["tabac_actif", "HTA"],
        "temporal": {"onset_speed": "rapid"},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert result["abstract_match"], "IND-001 should match ABS-01"
    assert "ABS-01" in result["matched_patterns"], f"Expected ABS-01, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-001 (SCA typique): {result['matched_patterns']} → {result['triage_level']}")


def test_ind006_sca_atypique_epigastrique():
    """IND-006 — SCA atypique épigastrique 62 ans tabac+HTA+dyslipidemie → ABS-01"""
    config = get_config()
    features = {
        "symptoms": ["douleur_epigastrique"],
        "demographics": {"age": 62, "sex": "M"},
        "risk_factors": ["tabac_actif", "HTA", "dyslipidemie"],
        "temporal": {"onset_speed": "rapid", "duration_days": 2},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-01" in result["matched_patterns"], f"IND-006 expected ABS-01, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-006 (SCA atypique épigastrique): {result['matched_patterns']} → {result['triage_level']}")


def test_ind008_ep_cop():
    """IND-008 — EP femme 35 sous COP dyspnée → ABS-02"""
    config = get_config()
    features = {
        "symptoms": ["dyspnee"],
        "demographics": {"age": 35, "sex": "F"},
        "risk_factors": ["COP"],
        "temporal": {"onset_speed": "progressive", "duration_days": 1},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-02" in result["matched_patterns"], f"IND-008 expected ABS-02, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-008 (EP COP): {result['matched_patterns']} → {result['triage_level']}")


def test_ind002_hsa_thunderclap():
    """IND-002 — HSA céphalée thunderclap 'pire de ma vie' → ABS-03"""
    config = get_config()
    features = {
        "symptoms": ["cephalee"],
        "demographics": {"age": 45, "sex": "F"},
        "risk_factors": [],
        "temporal": {"onset_speed": "brutal"},
        "context_flags": ["pire_de_ma_vie"],
        "escalation": {"detected": True},
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-03" in result["matched_patterns"], f"IND-002 expected ABS-03, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-002 (HSA thunderclap): {result['matched_patterns']} → {result['triage_level']}")


def test_ind013_meningite_triade():
    """IND-013 — Méningite triade fièvre+céphalée intense+raideur nuque → ABS-04"""
    config = get_config()
    features = {
        "symptoms": ["fievre", "cephalee_intense", "raideur_nuque"],
        "demographics": {"age": 50, "sex": "M"},
        "risk_factors": [],
        "temporal": {"onset_speed": "rapid"},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-04" in result["matched_patterns"], f"IND-013 expected ABS-04, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-013 (Méningite triade): {result['matched_patterns']} → {result['triage_level']}")


def test_ind016_neutropenie_febrile():
    """IND-016 — Neutropénie fébrile (sepsis branche chimio) → ABS-05"""
    config = get_config()
    features = {
        "symptoms": ["fievre"],
        "demographics": {"age": 48, "sex": "F"},
        "risk_factors": ["chimio_active", "cancer_actif"],
        "temporal": {"onset_speed": "rapid", "duration_days": 1},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-05" in result["matched_patterns"], f"IND-016 expected ABS-05, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-016 (Neutropénie fébrile): {result['matched_patterns']} → {result['triage_level']}")


def test_ind017_geu():
    """IND-017 — GEU femme 28 retard règles + douleur pelvienne → ABS-06"""
    config = get_config()
    features = {
        "symptoms": ["douleur_pelvienne", "retard_regles"],
        "demographics": {"age": 28, "sex": "F"},
        "risk_factors": [],
        "temporal": {"onset_speed": "rapid"},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-06" in result["matched_patterns"], f"IND-017 expected ABS-06, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent_medical_review"
    print(f"✓ IND-017 (GEU): {result['matched_patterns']} → {result['triage_level']}")


def test_ind019_hsd_anticoagule():
    """IND-019 — HSD anticoagulé somnolent+confus 78 ans → ABS-07"""
    config = get_config()
    features = {
        "symptoms": ["somnolence", "confusion"],
        "demographics": {"age": 78, "sex": "M"},
        "risk_factors": ["anticoagulation_AOD_AVK"],
        "temporal": {"onset_speed": "rapid", "duration_days": 1},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-07" in result["matched_patterns"], f"IND-019 expected ABS-07, got {result['matched_patterns']}"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-019 (HSD anticoagulé): {result['matched_patterns']} → {result['triage_level']}")


def test_ind005_ideation_suicidaire():
    """IND-005 — Idéation suicidaire → ABS-08 override_all"""
    config = get_config()
    features = {
        "symptoms": [],
        "demographics": {"age": 35, "sex": "F"},
        "risk_factors": [],
        "context_flags": ["ideation_suicidaire"],
    }
    result = evaluate_abstract_layer(config, features)
    assert "ABS-08" in result["matched_patterns"], f"IND-005 expected ABS-08, got {result['matched_patterns']}"
    assert result["override_all"] == True, "ABS-08 must set override_all=True"
    assert result["triage_level"] == "urgent"
    print(f"✓ IND-005 (Idéation suicidaire): {result['matched_patterns']} → override_all={result['override_all']}")


# ── 2 false positive traps ────────────────────────────────────────────────────

def test_fp_rhume_banal():
    """IND-043 — Rhume banal → NO abstract match"""
    config = get_config()
    features = {
        "symptoms": ["rhinorrhee", "mal_de_gorge"],
        "demographics": {"age": 28, "sex": "F"},
        "risk_factors": [],
        "temporal": {"onset_speed": "rapid", "duration_days": 2},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert not result["abstract_match"], \
        f"IND-043 (rhume banal) should NOT match, got {result['matched_patterns']}"
    print(f"✓ IND-043 (rhume banal — FP trap): no abstract match (correct)")


def test_fp_acne():
    """IND-046 — Acné → NO abstract match"""
    config = get_config()
    features = {
        "symptoms": ["acne"],
        "demographics": {"age": 22, "sex": "F"},
        "risk_factors": [],
        "temporal": {"onset_speed": "progressive"},
        "context_flags": [],
    }
    result = evaluate_abstract_layer(config, features)
    assert not result["abstract_match"], \
        f"IND-046 (acné) should NOT match, got {result['matched_patterns']}"
    print(f"✓ IND-046 (acné — FP trap): no abstract match (correct)")


# ── 3 hybrid resolution tests ────────────────────────────────────────────────

def test_hybrid_abstract_wins():
    """Hybrid: abstract match → wins, fallback logged for audit"""
    config = get_config()
    features = {
        "symptoms": ["douleur_pelvienne", "retard_regles"],
        "demographics": {"age": 28, "sex": "F"},
        "risk_factors": [],
        "context_flags": [],
    }
    fake_token = lambda f: {"matched_patterns": ["PE-13"], "triage_level": "urgent_medical_review"}
    result = hybrid_pre_triage(config, features, token_layer_callable=fake_token)
    assert result["primary_layer_used"] == "abstract_v2"
    assert "ABS-06" in result["matched_patterns"]
    assert "PE-13" in result["fallback_would_have_matched"], \
        "Fallback match must be logged even when abstract wins"
    print(f"✓ Hybrid: abstract wins (ABS-06), fallback PE-13 logged for audit")


def test_hybrid_fallback_used():
    """Hybrid: no abstract match → fallback token layer used"""
    config = get_config()
    features = {
        "symptoms": ["mal_de_dos_simple"],
        "demographics": {"age": 35, "sex": "M"},
        "risk_factors": [],
        "context_flags": [],
    }
    fake_token = lambda f: {"matched_patterns": ["PE-X"], "triage_level": "non_urgent"}
    result = hybrid_pre_triage(config, features, token_layer_callable=fake_token)
    assert result["primary_layer_used"] == "token_v1_fallback"
    assert "PE-X" in result["matched_patterns"]
    print(f"✓ Hybrid: fallback used (no abstract match), PE-X")


def test_hybrid_no_match():
    """Hybrid: neither layer matches → primary_layer_used='none'"""
    config = get_config()
    features = {
        "symptoms": [],
        "demographics": {"age": 30, "sex": "F"},
        "risk_factors": [],
        "context_flags": [],
    }
    fake_token = lambda f: {"matched_patterns": [], "triage_level": None}
    result = hybrid_pre_triage(config, features, token_layer_callable=fake_token)
    assert result["primary_layer_used"] == "none"
    assert result["triage_level"] is None
    print(f"✓ Hybrid: no match in either layer (correct)")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        test_ind001_sca_typique,
        test_ind006_sca_atypique_epigastrique,
        test_ind008_ep_cop,
        test_ind002_hsa_thunderclap,
        test_ind013_meningite_triade,
        test_ind016_neutropenie_febrile,
        test_ind017_geu,
        test_ind019_hsd_anticoagule,
        test_ind005_ideation_suicidaire,
        test_fp_rhume_banal,
        test_fp_acne,
        test_hybrid_abstract_wins,
        test_hybrid_fallback_used,
        test_hybrid_no_match,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(tests)} PASS | {failed} FAIL")
    if failed == 0:
        print("✓ ALL TESTS PASSED — safe to integrate")
    else:
        print("✗ TESTS FAILED — DO NOT INTEGRATE")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)