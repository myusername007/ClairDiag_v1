"""
Tests для care_pathway_engine. 18/18 PASS expected.

Покриває:
- Loading JSON (20 categories)
- Detection via triggers
- Mapping category names → JSON ids
- Specialist resolution з fallback doctrine
- Minimum output guarantee
- Edge cases (JSON manquant, category inconnue)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from care_pathway_engine import (
    CarePathwayConfig,
    detect_category_from_text,
    match_urgency_level,
    resolve_specialist,
    enrich_with_care_pathway,
    enrich,
    get_engine,
)


def test_loading():
    """JSON chargé correctement, 20 catégories."""
    config = CarePathwayConfig()
    assert config.is_available(), "Config should be available"
    assert config.loaded_count == 20, f"Expected 20 categories, got {config.loaded_count}"
    print(f"  PASS — Loaded {config.loaded_count} categories")


def test_all_categories_have_rules():
    """Chaque catégorie a tous les champs requis."""
    config = CarePathwayConfig()
    required = [
        "category_id", "triggers", "specialists", "exams",
        "urgency_rules", "patient_message", "warning_signs",
    ]
    for cat_id, rule in config.rules_by_category.items():
        for field in required:
            assert field in rule, f"{cat_id} missing field '{field}'"
    print(f"  PASS — All 20 categories have required fields")


def test_detect_talon():
    """Trigger 'talon' → catégorie pied_talon_cheville."""
    config = CarePathwayConfig()
    detected = detect_category_from_text("J'ai mal au talon gauche", config)
    assert detected == "pied_talon_cheville", f"Got '{detected}'"
    print(f"  PASS — 'mal au talon' → {detected}")


def test_detect_peau():
    """Trigger 'démangeaisons' → dermatologie."""
    config = CarePathwayConfig()
    detected = detect_category_from_text("J'ai des démangeaisons sur la peau", config)
    assert detected == "dermatologie", f"Got '{detected}'"
    print(f"  PASS — 'démangeaisons peau' → {detected}")


def test_detect_cardio():
    """Triggers cardiaques."""
    config = CarePathwayConfig()
    detected = detect_category_from_text("Douleur thoracique avec essoufflement", config)
    assert detected in ["cardio", "respiratoire"], f"Got '{detected}'"
    print(f"  PASS — 'douleur thoracique' → {detected}")


def test_detect_unknown():
    """Texte sans triggers → None."""
    config = CarePathwayConfig()
    detected = detect_category_from_text("xyz blablabla aucun symptôme", config)
    assert detected is None, f"Got '{detected}'"
    print(f"  PASS — texte sans trigger → None (fallback)")


def test_specialist_red_flag():
    """Red flag → urgences en priorité."""
    config = CarePathwayConfig()
    rule = config.get_rule("cardio")
    spec = resolve_specialist(rule, "urgent", has_red_flag=True)
    primary = spec["primary_recommended"].lower()
    assert "urgences" in primary or "15" in primary, f"Got '{spec['primary_recommended']}'"
    print(f"  PASS — Red flag cardio → {spec['primary_recommended']}")


def test_specialist_dermato_first():
    """Dermato → dermatologue en première intention (PAS médecin généraliste)."""
    config = CarePathwayConfig()
    rule = config.get_rule("dermatologie")
    spec = resolve_specialist(rule, "consultation", has_red_flag=False)
    assert "dermatologue" in spec["primary_recommended"].lower(), \
        f"Dermato should route to dermatologue, got '{spec['primary_recommended']}'"
    print(f"  PASS — Dermato → {spec['primary_recommended']} (PAS médecin généraliste)")


def test_specialist_pied_first():
    """Pied/talon → podologue en première intention."""
    config = CarePathwayConfig()
    rule = config.get_rule("pied_talon_cheville")
    spec = resolve_specialist(rule, "consultation", has_red_flag=False)
    assert "podologue" in spec["primary_recommended"].lower(), \
        f"Pied should route to podologue, got '{spec['primary_recommended']}'"
    print(f"  PASS — Pied/talon → {spec['primary_recommended']} (PAS médecin généraliste)")


def test_fallback_doctrine_vague():
    """Cas vague → MT légitime (fallback doctrine respect)."""
    config = CarePathwayConfig()
    rule = config.get_rule("douleur_generale_vague")
    spec = resolve_specialist(rule, "consultation", has_red_flag=False)
    primary_lower = spec["primary_recommended"].lower()
    assert "traitant" in primary_lower or "généraliste" in primary_lower, \
        f"Vague case should legitimately route to MT, got '{spec['primary_recommended']}'"
    print(f"  PASS — Vague → {spec['primary_recommended']} (MT légitime ici)")


def test_enrich_full_flow():
    """Test du flow complet enrich — structure réelle core.py."""
    # Simule la structure réelle de core.py (clinical.category)
    v3_response = {
        "triage": {"urgency": "non_urgent", "urgent_message": None},
        "clinical": {"category": "dermatologie_simple"},
        "red_flag_triggered": False,
    }
    result = enrich(v3_response, "j'ai des boutons sur le visage", {"age": 28})
    cp = result["care_pathway"]
    assert cp["applicable"] is True
    assert cp["matched_category"] == "dermatologie"
    assert "dermatologue" in cp["specialist"]["primary_recommended"].lower()
    assert len(cp["warning_signs"]) >= 3
    assert cp["patient_message"]
    print(f"  PASS — enrich() retourne structure complète pour dermato")


def test_enrich_with_text_fallback():
    """Si pipeline donne general_vague → détecter via triggers texte."""
    v3_response = {
        "triage": {"urgency": "consultation"},
        "clinical": {"category": "general_vague_non_specifique"},
    }
    result = enrich(v3_response, "douleur talon gauche en marchant", {})
    cp = result["care_pathway"]
    assert cp["applicable"] is True, f"Expected applicable=True, got {cp}"
    assert cp["matched_category"] == "pied_talon_cheville", \
        f"Expected pied_talon_cheville, got '{cp['matched_category']}'"
    assert "podologue" in cp["specialist"]["primary_recommended"].lower()
    print(f"  PASS — Détection via triggers: 'douleur talon' → pied_talon_cheville")


def test_minimum_output_guarantee():
    """Tous les champs minimaux présents même cas dégradé."""
    v3_response = {
        "triage": {"urgency": "non_urgent"},
        "clinical": {"category": "dermatologie_simple"},
    }
    result = enrich(v3_response, "boutons", {})
    cp = result["care_pathway"]
    assert cp["urgency_level"], "urgency_level missing"
    assert cp["specialist"]["primary_recommended"], "specialist missing"
    assert cp["exams"], "exams missing"
    assert len(cp["warning_signs"]) >= 3, f"warning_signs: {cp['warning_signs']}"
    assert len(cp["patient_message"]) > 20, "patient_message too short"
    print(f"  PASS — Minimum output guarantee respectée")


def test_unknown_category_fallback():
    """Catégorie inconnue → applicable=False, pas de crash."""
    v3_response = {
        "triage": {"urgency": "non_urgent"},
        "clinical": {"category": "unknown_category_xyz"},
    }
    result = enrich(v3_response, "blabla", {})
    assert result["care_pathway"]["applicable"] is False
    print(f"  PASS — Catégorie inconnue → fallback gracieux")


def test_pediatrie_no_fallback():
    """Pédiatrie n'a PAS de fallback médecin généraliste (par design)."""
    config = CarePathwayConfig()
    rule = config.get_rule("pediatrie")
    spec = resolve_specialist(rule, "consultation", has_red_flag=False)
    primary_lower = spec["primary_recommended"].lower()
    assert "pédiatre" in primary_lower or "urgences" in primary_lower, \
        f"Pediatrie should route to pédiatre/urgences, got '{spec['primary_recommended']}'"
    print(f"  PASS — Pédiatrie → {spec['primary_recommended']} (pas MT)")


def test_psychiatrie_suicide_override():
    """psychiatrie_suicide a override_all_other_logic = true dans JSON."""
    config = CarePathwayConfig()
    rule = config.get_rule("psychiatrie_suicide")
    assert rule.get("override_all_other_logic") is True, \
        "psychiatrie_suicide doit avoir override_all_other_logic = true"
    spec = resolve_specialist(rule, "urgent", has_red_flag=True)
    assert "3114" in spec["primary_recommended"], \
        f"Expected 3114, got '{spec['primary_recommended']}'"
    print(f"  PASS — Suicide → {spec['primary_recommended']} avec override")


def test_global_rules_present():
    """Global rules section accessible."""
    config = CarePathwayConfig()
    gr = config.global_rules
    assert "fallback_doctrine" in gr
    assert "specialist_resolution_order" in gr
    assert "minimum_output_guarantee" in gr
    print(f"  PASS — Global rules section accessible")


def test_singleton():
    """CarePathwayConfig est singleton — même instance."""
    a = CarePathwayConfig()
    b = CarePathwayConfig()
    assert a is b, "Config should be singleton"
    assert get_engine() is a, "get_engine() should return same instance"
    print(f"  PASS — Singleton pattern fonctionne")


# ============================================================
# Run all tests
# ============================================================

if __name__ == "__main__":
    tests = [
        ("Loading JSON",                    test_loading),
        ("All categories have rules",       test_all_categories_have_rules),
        ("Detect talon trigger",            test_detect_talon),
        ("Detect peau trigger",             test_detect_peau),
        ("Detect cardio trigger",           test_detect_cardio),
        ("Detect unknown returns None",     test_detect_unknown),
        ("Red flag → urgences",             test_specialist_red_flag),
        ("Dermato → dermatologue first",    test_specialist_dermato_first),
        ("Pied → podologue first",          test_specialist_pied_first),
        ("Vague → MT legitimate",           test_fallback_doctrine_vague),
        ("Full enrich flow",                test_enrich_full_flow),
        ("Detect via text fallback",        test_enrich_with_text_fallback),
        ("Minimum output guarantee",        test_minimum_output_guarantee),
        ("Unknown category fallback",       test_unknown_category_fallback),
        ("Pediatrie no MT",                 test_pediatrie_no_fallback),
        ("Suicide override",                test_psychiatrie_suicide_override),
        ("Global rules present",            test_global_rules_present),
        ("Singleton pattern",               test_singleton),
    ]

    passed = 0
    failed = 0
    print(f"\n{'='*60}")
    print(f"care_pathway_engine — Test suite")
    print(f"{'='*60}\n")

    for name, fn in tests:
        try:
            print(f"Test: {name}")
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL — {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR — {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} PASS / {failed} FAIL / {passed + failed} TOTAL")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)