"""
ClairDiag v3 — Followup Engine Tests
Module: test_followup_engine
Version: v1.0

Запуск:
  cd clairdiag_v1/v3_dev
  python -m pytest tests/test_followup_engine.py -v

  або напряму:
  python tests/test_followup_engine.py
"""

import sys
import os

# Додаємо v3_dev в path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from followup_engine import (
    FollowupConfig,
    FollowupEngine,
    should_trigger_followup,
    apply_followup_answers,
    select_questions_for_round,
)


def get_config():
    return FollowupConfig()


# ── 6 original tests ──────────────────────────────────────────────────────────

def test_1_high_confidence_no_followup():
    """Test 1: confidence high → pas de followup"""
    v3 = {
        "urgency": "non_urgent",
        "confidence_detail": {"score": 8},
        "general_orientation": {"category": "ORL_simple"},
    }
    assert should_trigger_followup(v3) == False, "FAIL: high confidence should not trigger followup"
    print("✓ Test 1 PASS — high confidence → no followup")


def test_2_low_confidence_triggers_followup():
    """Test 2: confidence low → followup"""
    v3 = {
        "urgency": "non_urgent",
        "confidence_detail": {"score": 3},
        "general_orientation": {"category": "fatigue_asthenie"},
    }
    assert should_trigger_followup(v3) == True, "FAIL: low confidence should trigger followup"
    print("✓ Test 2 PASS — low confidence → followup triggered")


def test_3_vague_category_triggers_followup():
    """Test 3: vague → followup"""
    v3 = {
        "urgency": "medical_consultation",
        "confidence_detail": {"score": 2},
        "general_orientation": {"category": "general_vague_non_specifique"},
    }
    assert should_trigger_followup(v3) == True, "FAIL: vague category should trigger followup"
    print("✓ Test 3 PASS — vague category → followup triggered")


def test_4_urgent_no_followup():
    """Test 4: urgent déjà → pas de followup (safety prime)"""
    v3 = {
        "urgency": "urgent",
        "confidence_detail": {"score": 9},
        "red_flag_triggered": True,
    }
    assert should_trigger_followup(v3) == False, "FAIL: urgent should never trigger followup"
    print("✓ Test 4 PASS — urgent → no followup (safety prime)")


def test_5_facial_swelling_triggers_urgent():
    """Test 5: apply answer 'facial_swelling' → urgent"""
    config = get_config()
    v3 = {
        "urgency": "non_urgent",
        "confidence_detail": {"score": 4},
    }
    answers = [{"qid": "DERM-Q3", "tag": "facial_swelling"}]
    result = apply_followup_answers(config, v3, answers, "dermatologie_simple")

    assert result.get("urgency") == "urgent" or result.get("final_triage") == "urgent", \
        f"FAIL: expected urgent, got {result.get('urgency')} / {result.get('final_triage')}"
    assert result.get("red_flag_triggered") == True, "FAIL: red_flag_triggered should be True"
    print("✓ Test 5 PASS — facial_swelling → urgent + red_flag_triggered")


def test_6_suicidal_ideation_override_all():
    """Test 6: idéation suicidaire → override_all, message 3114"""
    config = get_config()
    v3 = {
        "urgency": "non_urgent",
        "confidence_detail": {"score": 5},
    }
    answers = [{"qid": "STR-Q1", "tag": "suicidal_ideation"}]
    result = apply_followup_answers(config, v3, answers, "sommeil_stress_anxiete_non_urgent")

    assert result.get("urgency") == "urgent" or result.get("final_triage") == "urgent", \
        f"FAIL: expected urgent, got {result.get('urgency')}"
    assert "3114" in result.get("specific_message", ""), \
        f"FAIL: '3114' not in specific_message: {result.get('specific_message')}"
    print("✓ Test 6 PASS — suicidal_ideation → override_all + 3114 message")


# ── Regression guard ──────────────────────────────────────────────────────────

def test_regression_urgent_never_gets_followup():
    """Regression: urgent/medical_urgent responses never trigger followup"""
    for urgency in ("urgent", "medical_urgent"):
        v3 = {"urgency": urgency, "confidence_detail": {"score": 2}}
        assert should_trigger_followup(v3) == False, \
            f"FAIL regression: {urgency} triggered followup"
    print("✓ Regression PASS — urgent/medical_urgent never trigger followup")


def test_regression_engine_session_flow():
    """Regression: FollowupEngine full session flow"""
    engine = FollowupEngine()
    v3 = {
        "urgency": "non_urgent",
        "confidence_detail": {"score": 2},
        "general_orientation": {"category": "ORL_simple"},
    }
    patient_context = {"age": 35}

    # Step 1: initiate
    result = engine.initiate_followup(v3, patient_context)
    assert result["followup_needed"] == True
    assert "session_id" in result
    assert len(result["questions"]) > 0
    session_id = result["session_id"]

    # Step 2: submit answers (non-urgent)
    answers = [{"qid": result["questions"][0]["qid"], "tag": result["questions"][0]["answer_options"][0]["tag"]}]
    final = engine.submit_answers(session_id, round_number=1, answers=answers)

    # Session devrait être terminée ou continuer au round 2
    assert "error" not in final, f"FAIL: unexpected error: {final}"
    print("✓ Regression PASS — full session flow OK")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        test_1_high_confidence_no_followup,
        test_2_low_confidence_triggers_followup,
        test_3_vague_category_triggers_followup,
        test_4_urgent_no_followup,
        test_5_facial_swelling_triggers_urgent,
        test_6_suicidal_ideation_override_all,
        test_regression_urgent_never_gets_followup,
        test_regression_engine_session_flow,
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