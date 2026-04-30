"""
ClairDiag v3 — Local Directory Engine Tests
Module: test_local_directory
Version: v1.0

Запуск:
  cd clairdiag_v1/v3_dev
  python tests/test_local_directory.py

  або:
  python -m pytest tests/test_local_directory.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from local_directory_engine import (
    LocalDirectoryConfig,
    lookup_commune,
    find_closest_specialists,
    find_available_medecin_traitant,
    enrich_with_local_resources,
    enrich_with_pilot_mode,
    _normalize_commune_key,
    _hash_code_postal,
)


def get_config():
    return LocalDirectoryConfig()


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_1_lookup_commune_by_code_postal_and_nom():
    """Test 1: lookup commune by code_postal + nom"""
    config = get_config()
    commune = lookup_commune(config, "83250", "La Londe-les-Maures")
    assert commune is not None, "FAIL: commune 83250 not found"
    assert commune["nom"] == "La Londe-les-Maures", f"FAIL: wrong nom: {commune['nom']}"
    print("✓ Test 1 PASS — lookup by code_postal + nom")


def test_2_lookup_unknown_commune():
    """Test 2: lookup unknown commune → None"""
    config = get_config()
    commune = lookup_commune(config, "75001", "Paris")
    assert commune is None, f"FAIL: unexpected commune found: {commune}"
    print("✓ Test 2 PASS — unknown commune → None")


def test_3_enrich_urgent_returns_samu_15():
    """Test 3: enrich urgent → SAMU 15"""
    config = get_config()
    v3 = {"urgency": "urgent"}
    ctx = {"code_postal": "83250", "commune": "La Londe-les-Maures"}
    res = enrich_with_local_resources(config, v3, ctx)
    assert res["primary_recommendation"]["telephone"] == "15", \
        f"FAIL: expected '15', got {res['primary_recommendation'].get('telephone')}"
    assert res["commune_found"] == "La Londe-les-Maures"
    print("✓ Test 3 PASS — urgent → SAMU 15")


def test_4_enrich_medical_consultation_returns_mt():
    """Test 4: enrich medical_consultation → médecin traitant"""
    config = get_config()
    v3 = {
        "urgency": "medical_consultation",
        "general_orientation": {"category": "fatigue_asthenie", "possible_specialist": None},
    }
    ctx = {"code_postal": "83250", "commune": "La Londe-les-Maures"}
    res = enrich_with_local_resources(config, v3, ctx)
    assert res["primary_recommendation"] is not None, "FAIL: primary_recommendation is None"
    action_lower = res["primary_recommendation"]["action"].lower()
    assert any(kw in action_lower for kw in ["médecin", "maison", "consultation"]), \
        f"FAIL: unexpected action: {res['primary_recommendation']['action']}"
    print("✓ Test 4 PASS — medical_consultation → MT or MSP")


def test_5_enrich_with_specialist_hint_dermatologue():
    """Test 5: enrich avec specialist hint dermatologue → specialiste_propose"""
    config = get_config()
    v3 = {
        "urgency": "medical_consultation",
        "general_orientation": {
            "category": "dermatologie_simple",
            "possible_specialist": "dermatologue",
        },
    }
    ctx = {"code_postal": "83250", "commune": "La Londe-les-Maures"}
    res = enrich_with_local_resources(config, v3, ctx)
    assert res["primary_recommendation"] is not None, "FAIL: no primary_recommendation"
    specialist = res["primary_recommendation"].get("specialiste_propose")
    assert specialist is not None, \
        f"FAIL: specialiste_propose missing. Got: {res['primary_recommendation']}"
    assert specialist["specialite"] == "dermatologue", \
        f"FAIL: wrong specialite: {specialist['specialite']}"
    print(f"✓ Test 5 PASS — dermatologue → {specialist['nom']}")


def test_6_fallback_national_unknown_commune():
    """Test 6: commune inconnue → fallback national"""
    config = get_config()
    v3 = {"urgency": "medical_consultation"}
    ctx = {"code_postal": "75001"}  # Paris — absent de l'annuaire
    res = enrich_with_local_resources(config, v3, ctx)
    assert res.get("fallback_used") == True, \
        f"FAIL: fallback_used not True. Got: {res}"
    assert res["commune_found"] is None
    print("✓ Test 6 PASS — unknown commune → fallback national")


def test_7_no_code_postal_fallback():
    """Test 7: pas de code_postal → fallback national"""
    config = get_config()
    v3 = {"urgency": "non_urgent"}
    ctx = {}
    res = enrich_with_local_resources(config, v3, ctx)
    assert res.get("fallback_used") == True, "FAIL: expected fallback_used=True"
    print("✓ Test 7 PASS — no code_postal → fallback national")


def test_8_pilot_mode_anonymized():
    """Test 8: pilot_mode wrapper anonymisé (Roman's required format)"""
    config = get_config()
    v3 = {
        "urgency": "medical_consultation",
        "general_orientation": {"category": "fatigue_asthenie"},
    }
    ctx = {"code_postal": "83250", "commune": "La Londe-les-Maures"}
    pilot = enrich_with_pilot_mode(config, v3, ctx, region="PACA", anonymized=True)

    assert pilot["pilot_mode"] == True
    assert pilot["region"] == "PACA"
    assert pilot["export_format"] == "ARS_ready"
    assert pilot["anonymized"] == True
    assert pilot["session_metadata"]["code_postal"] == "83***", \
        f"FAIL: expected '83***', got {pilot['session_metadata']['code_postal']}"
    assert pilot["session_metadata"]["category"] == "fatigue_asthenie"
    assert "timestamp" in pilot["session_metadata"]
    print(f"✓ Test 8 PASS — pilot mode anonymized, cp={pilot['session_metadata']['code_postal']}")


def test_9_pilot_mode_not_anonymized():
    """Test 9: pilot_mode sans anonymisation → code postal brut"""
    config = get_config()
    v3 = {
        "urgency": "medical_consultation",
        "general_orientation": {"category": "fatigue_asthenie"},
    }
    ctx = {"code_postal": "83250", "commune": "La Londe-les-Maures"}
    pilot = enrich_with_pilot_mode(config, v3, ctx, region="PACA", anonymized=False)

    assert pilot["session_metadata"]["code_postal"] == "83250", \
        f"FAIL: expected '83250', got {pilot['session_metadata']['code_postal']}"
    assert pilot["anonymized"] == False
    print("✓ Test 9 PASS — pilot mode not anonymized, cp=83250")


# ── Regression guard ──────────────────────────────────────────────────────────

def test_regression_module_is_additive():
    """Regression: module ne modifie pas urgency/category d'origine"""
    config = get_config()
    v3_original = {
        "urgency": "non_urgent",
        "general_orientation": {"category": "ORL_simple"},
    }
    import copy
    v3_copy = copy.deepcopy(v3_original)
    ctx = {"code_postal": "83250", "commune": "La Londe-les-Maures"}
    enrich_with_local_resources(config, v3_copy, ctx)
    # v3_response ne doit pas être modifié par le module
    assert v3_copy["urgency"] == "non_urgent"
    assert v3_copy["general_orientation"]["category"] == "ORL_simple"
    print("✓ Regression PASS — module additif, v3_response non modifié")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        test_1_lookup_commune_by_code_postal_and_nom,
        test_2_lookup_unknown_commune,
        test_3_enrich_urgent_returns_samu_15,
        test_4_enrich_medical_consultation_returns_mt,
        test_5_enrich_with_specialist_hint_dermatologue,
        test_6_fallback_national_unknown_commune,
        test_7_no_code_postal_fallback,
        test_8_pilot_mode_anonymized,
        test_9_pilot_mode_not_anonymized,
        test_regression_module_is_additive,
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
    import sys
    success = run_all()
    sys.exit(0 if success else 1)