"""
ClairDiag v3 — Follow-up Journey Engine Tests
Module: test_followup_journey
Version: v1.0

Запуск:
  cd clairdiag_v1/v3_dev
  python tests/test_followup_journey.py

  або:
  python -m pytest tests/test_followup_journey.py -v
"""

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from followup_journey_engine import (
    create_followup_schedule,
    handle_checkin_response,
    get_pending_checkpoints,
    expire_journey_if_needed,
)


def test_1_non_urgent_minimal_schedule():
    """Test 1: non_urgent → minimal schedule (J+7 only)"""
    v3 = {"urgency": "non_urgent", "general_orientation": {"category": "ORL_simple"}}
    journey = create_followup_schedule(v3)
    assert journey is not None
    assert journey["schedule_type"] == "minimal"
    assert len(journey["checkpoints"]) == 1
    assert journey["checkpoints"][0]["days_offset"] == 7
    print("✓ Test 1 PASS — non_urgent → minimal (J+7)")


def test_2_medical_consultation_standard_schedule():
    """Test 2: medical_consultation → standard (J+3, J+7)"""
    v3 = {"urgency": "medical_consultation", "general_orientation": {"category": "fatigue_asthenie"}}
    journey = create_followup_schedule(v3)
    assert journey["schedule_type"] == "standard"
    assert len(journey["checkpoints"]) == 2
    assert journey["checkpoints"][0]["days_offset"] == 3
    assert journey["checkpoints"][1]["days_offset"] == 7
    print("✓ Test 2 PASS — medical_consultation → standard (J+3, J+7)")


def test_3_urgent_medical_review_high_risk():
    """Test 3: urgent_medical_review → high_risk (J+1, J+3, J+7, J+14)"""
    v3 = {"urgency": "urgent_medical_review", "general_orientation": {"category": "urinaire"}}
    journey = create_followup_schedule(v3)
    assert journey["schedule_type"] == "high_risk"
    assert len(journey["checkpoints"]) == 4
    assert [c["days_offset"] for c in journey["checkpoints"]] == [1, 3, 7, 14]
    print("✓ Test 3 PASS — urgent_medical_review → high_risk (J+1,3,7,14)")


def test_4_no_consent_returns_none():
    """Test 4: pas de consent → None (RGPD)"""
    v3 = {"urgency": "urgent_medical_review", "general_orientation": {"category": "urinaire"}}
    journey = create_followup_schedule(v3, patient_consent=False)
    assert journey is None
    print("✓ Test 4 PASS — no consent → None (RGPD)")


def test_5_response_better_closes_journey():
    """Test 5: réponse 'better' → close_journey"""
    v3 = {"urgency": "non_urgent", "general_orientation": {"category": "ORL_simple"}}
    journey = create_followup_schedule(v3)
    checkpoint_id = journey["checkpoints"][0]["checkpoint_id"]
    result = handle_checkin_response(journey, checkpoint_id, "better")
    assert result["action_recommended"] == "close_journey"
    assert result["journey"]["status"] == "closed"
    assert result["trigger_re_evaluation"] == False
    print("✓ Test 5 PASS — 'better' → close_journey")


def test_6_response_worse_escalates():
    """Test 6: réponse 'worse' → escalation + pending checkpoints annulés"""
    v3 = {"urgency": "medical_consultation", "general_orientation": {"category": "ORL_simple"}}
    journey = create_followup_schedule(v3)
    checkpoint_id = journey["checkpoints"][0]["checkpoint_id"]
    result = handle_checkin_response(journey, checkpoint_id, "worse")
    assert result["action_recommended"] == "trigger_re_evaluation"
    assert result["journey"]["status"] == "escalated"
    assert result["trigger_re_evaluation"] == True
    # Remaining checkpoints should be cancelled
    remaining = [c for c in result["journey"]["checkpoints"] if c["status"] == "pending"]
    assert len(remaining) == 0, f"FAIL: pending checkpoints not cancelled: {remaining}"
    print("✓ Test 6 PASS — 'worse' → escalated + pending cancelled")


def test_7_invalid_response_returns_error():
    """Test 7: réponse invalide → error dict"""
    v3 = {"urgency": "non_urgent", "general_orientation": {"category": "ORL_simple"}}
    journey = create_followup_schedule(v3)
    checkpoint_id = journey["checkpoints"][0]["checkpoint_id"]
    result = handle_checkin_response(journey, checkpoint_id, "this_is_not_valid")
    assert "error" in result
    assert result["error"] == "invalid_response"
    assert "valid_responses" in result
    print("✓ Test 7 PASS — invalid response → error")


def test_8_pending_checkpoints_empty_immediately():
    """Test 8: checkpoints vides immédiatement après création (tous dans le futur)"""
    v3 = {"urgency": "non_urgent", "general_orientation": {"category": "ORL_simple"}}
    journey = create_followup_schedule(v3)
    pending = get_pending_checkpoints(journey)
    assert len(pending) == 0, f"FAIL: expected 0 pending, got {len(pending)}"
    print("✓ Test 8 PASS — no pending checkpoints immediately after creation")


def test_9_pending_checkpoints_after_j7():
    """Test 9: J+8 simulé → J+7 checkpoint doit être pending"""
    v3 = {"urgency": "non_urgent", "general_orientation": {"category": "ORL_simple"}}
    journey = create_followup_schedule(v3)
    future = datetime.now(timezone.utc) + timedelta(days=8)
    pending = get_pending_checkpoints(journey, now=future)
    assert len(pending) >= 1, f"FAIL: expected >=1 pending at J+8, got {len(pending)}"
    assert pending[0]["days_offset"] == 7
    print(f"✓ Test 9 PASS — J+8 sim → {len(pending)} pending checkpoint(s)")


def test_10_journey_expires_after_30_days():
    """Test 10: expiration à J+40"""
    v3 = {"urgency": "non_urgent", "general_orientation": {"category": "ORL_simple"}}
    journey = create_followup_schedule(v3)
    far_future = datetime.now(timezone.utc) + timedelta(days=40)
    expired = expire_journey_if_needed(journey, now=far_future)
    assert expired == True
    assert journey["status"] == "expired"
    print("✓ Test 10 PASS — journey expired at J+40")


def test_11_roman_required_fields():
    """Test 11: Roman's required fields présents dans le journey"""
    v3 = {
        "urgency": "medical_consultation",
        "general_orientation": {"category": "fatigue_asthenie"},
    }
    journey = create_followup_schedule(v3)
    assert journey["follow_up_needed"] == True
    assert journey["delay_days"] == 3  # Standard: premier checkpoint J+3
    assert journey["trigger_condition"] == "symptoms_persist"
    assert journey["action"] == "re-evaluate"
    # Vérifier fields par checkpoint
    for cp in journey["checkpoints"]:
        assert cp["trigger_condition"] == "symptoms_persist"
        assert cp["action_on_worse"] == "re-evaluate"
        assert cp["action_on_better"] == "close_journey"
        assert cp["action_on_same"] == "continue_monitoring"
    print(
        f"✓ Test 11 PASS — Roman fields: "
        f"follow_up_needed={journey['follow_up_needed']}, "
        f"delay_days={journey['delay_days']}, "
        f"trigger={journey['trigger_condition']}, "
        f"action={journey['action']}"
    )


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    tests = [
        test_1_non_urgent_minimal_schedule,
        test_2_medical_consultation_standard_schedule,
        test_3_urgent_medical_review_high_risk,
        test_4_no_consent_returns_none,
        test_5_response_better_closes_journey,
        test_6_response_worse_escalates,
        test_7_invalid_response_returns_error,
        test_8_pending_checkpoints_empty_immediately,
        test_9_pending_checkpoints_after_j7,
        test_10_journey_expires_after_30_days,
        test_11_roman_required_fields,
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