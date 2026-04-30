"""
ClairDiag v1.1.0 — Feature Extractor Tests
Module: test_feature_extractor

Запуск:
  cd clairdiag_v1/v3_dev
  python tests/test_feature_extractor.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feature_extractor import extract_features


def _make_features(free_text, patient_context=None):
    """Helper: симулює pipeline до Stage 3."""
    # Імпортуємо тільки тут щоб не ламати якщо запускаємо standalone
    from common_symptom_mapper import common_symptom_mapper, normalize_text
    from medical_normalizer_v3 import normalize_to_medical_tokens

    norm_text = normalize_text(free_text)
    mapped = common_symptom_mapper(free_text)
    norm_tokens = normalize_to_medical_tokens(free_text)
    return extract_features(
        free_text=free_text,
        norm_text=norm_text,
        mapped=mapped,
        norm_tokens=norm_tokens,
        patient_context=patient_context or {},
    )


def test_sca_atypique_features():
    """SCA atypique: douleur_epigastrique + age 62 + risk factors"""
    features = _make_features(
        "j'ai mal à l'estomac, brûlures estomac depuis hier, je transpire",
        {"age": 62, "sex": "M", "risk_factors": ["HTA", "tabac_actif"]},
    )
    assert "douleur_epigastrique" in features["symptoms"] or \
           "sueurs_profuses" in features["symptoms"], \
        f"Expected epigastrique or sueurs, got {features['symptoms']}"
    assert features["demographics"]["age"] == 62
    assert "HTA" in features["risk_factors"]
    print(f"✓ SCA atypique features: symptoms={features['symptoms'][:4]}, rf={features['risk_factors'][:3]}")


def test_thunderclap_context_flag():
    """HSA: céphalée brutale pire de ma vie → thunderclap flag"""
    features = _make_features(
        "j'ai une céphalée soudaine, pire de ma vie, comme un coup de tonnerre"
    )
    assert "thunderclap" in features["context_flags"] or \
           "pire_de_ma_vie" in features["context_flags"], \
        f"Expected thunderclap, got {features['context_flags']}"
    assert features["temporal"]["onset_speed"] in ("brutal", "rapid"), \
        f"Expected brutal onset, got {features['temporal']['onset_speed']}"
    print(f"✓ Thunderclap: context_flags={features['context_flags']}, onset={features['temporal']['onset_speed']}")


def test_suicidal_ideation_context_flag():
    """ABS-08: idéation suicidaire → context flag"""
    features = _make_features("j'ai envie d'en finir avec la vie, plus envie de vivre")
    assert "ideation_suicidaire" in features["context_flags"] or \
           "envie_d_en_finir" in features["context_flags"], \
        f"Expected suicidal flag, got {features['context_flags']}"
    print(f"✓ Suicidal ideation: context_flags={features['context_flags']}")


def test_anticoagulant_risk_factor():
    """HSD: anticoagulant → risk_factor"""
    features = _make_features(
        "je prends du xarelto depuis 6 mois, j'ai des maux de tête",
        {"age": 75, "sex": "M"},
    )
    assert "anticoagulation_AOD_AVK" in features["risk_factors"], \
        f"Expected anticoagulation, got {features['risk_factors']}"
    print(f"✓ Anticoagulant: risk_factors={features['risk_factors']}")


def test_pregnancy_demographics():
    """GEU: enceinte dans le texte → sex=F, pregnancy_status"""
    features = _make_features(
        "je suis enceinte et j'ai une douleur en bas du ventre",
        {"age": 28},
    )
    assert features["demographics"]["sex"] == "F"
    assert features["demographics"]["pregnancy_status"] == "pregnant"
    assert "douleur_abdominale_basse" in features["symptoms"] or \
           "douleur_pelvienne" in features["symptoms"], \
        f"Expected pelvic symptom, got {features['symptoms']}"
    print(f"✓ Pregnancy: sex={features['demographics']['sex']}, status={features['demographics']['pregnancy_status']}")


def test_no_false_positive_orl():
    """ORL banal → pas de symptoms ABS critiques"""
    features = _make_features(
        "j'ai le nez bouché et mal à la gorge depuis 2 jours",
        {"age": 28, "sex": "F"},
    )
    critical = {"douleur_thoracique", "dyspnee", "cephalee", "fievre",
                "douleur_pelvienne", "confusion", "raideur_nuque"}
    overlap = critical & set(features["symptoms"])
    assert len(overlap) == 0, f"ORL should not produce critical symptoms: {overlap}"
    print(f"✓ ORL no false positive: symptoms={features['symptoms']}")


def test_minimization_detected():
    """Minimization: 'mais ça va' → detected=True"""
    features = _make_features("j'ai mal à la poitrine mais ça va, c'est rien")
    assert features["minimization"]["detected"] == True, \
        "minimization should be detected"
    print(f"✓ Minimization detected: {features['minimization']}")


def run_all():
    tests = [
        test_sca_atypique_features,
        test_thunderclap_context_flag,
        test_suicidal_ideation_context_flag,
        test_anticoagulant_risk_factor,
        test_pregnancy_demographics,
        test_no_false_positive_orl,
        test_minimization_detected,
    ]
    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(tests)} PASS | {failed} FAIL")
    if failed == 0:
        print("✓ ALL TESTS PASSED")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)