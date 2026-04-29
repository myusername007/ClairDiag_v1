"""
ClairDiag v3 — Final Validation Pack 100 Cases
===============================================
Запуск: python v3_dev/tests/run_final_validation_100.py

Не використовує HTTP — викликає engine напряму.
Формат звіту: case_id | output_category | output_urgency | confidence | status | issue
"""

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from common_symptom_mapper import common_symptom_mapper, normalize_text
from and_triggers import check_mollet_gonflement, check_all_urgent_and_triggers
from v3_confidence_engine import compute_v3_confidence
from loader import COMMON_SYMPTOM_MAPPING, COMMON_CONDITIONS_CONFIG
from pattern_engine_v3 import run_pattern_engine

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def get_category_priority(category):
    for m in COMMON_SYMPTOM_MAPPING:
        if m["category"] == category:
            return m["priority"]
    return 0


def get_urgency_from_config(category):
    if not category:
        return "unknown"
    return COMMON_CONDITIONS_CONFIG.get(category, {}).get("urgency", "unknown")


def run_case(text):
    mapped = common_symptom_mapper(text)
    got_urgent = mapped.get("urgent_trigger") is not None
    got_cat = mapped.get("category")
    matched = mapped.get("matched_symptoms", [])
    cat_priority = get_category_priority(got_cat) if got_cat else 0
    norm_text = normalize_text(text)
    and_trigger = check_all_urgent_and_triggers(norm_text)
    and_trigger_urgency = and_trigger.get("urgency") if and_trigger else None
    ctrl17 = check_mollet_gonflement(got_cat or "", matched, norm_text)
    ctrl17_urgency = ctrl17.get("urgency_override") if ctrl17 else None

    # Pattern engine (pre-triage)
    pattern_result = run_pattern_engine(norm_text)
    pattern_urgency = pattern_result.get("urgency") if pattern_result else None

    confidence = compute_v3_confidence(
        category=got_cat,
        category_matches=mapped.get("category_matches", 0),
        all_hits=mapped.get("all_hits", []),
        combination_matched=False,
        temporal=mapped.get("temporal", "unknown"),
        patient_context=None,
        urgent_trigger=mapped.get("urgent_trigger"),
        matched_symptoms=matched,
        category_priority=cat_priority,
        and_trigger=and_trigger,
    )

    if got_urgent:
        urgency = "urgent"
    elif pattern_urgency == "urgent":
        urgency = "urgent"
    elif and_trigger_urgency == "urgent":
        urgency = "urgent"
    elif pattern_urgency == "medical_urgent":
        urgency = "medical_urgent"
    elif and_trigger_urgency == "medical_urgent":
        urgency = "medical_urgent"
    elif ctrl17_urgency:
        urgency = ctrl17_urgency
    elif and_trigger_urgency == "medical_consultation":
        urgency = "medical_consultation"
    elif got_cat:
        urgency = get_urgency_from_config(got_cat)
    else:
        urgency = "unknown"

    return {
        "category": got_cat,
        "urgency": urgency,
        "urgent_trigger": mapped.get("urgent_trigger"),
        "and_trigger": and_trigger,
        "pattern_result": pattern_result,
        "ctrl17": ctrl17,
        "confidence_level": confidence["level"],
        "confidence_score": confidence["score"],
        "matched_symptoms": matched,
    }


# ── 100 кейсів ────────────────────────────────────────────────────────────────

CASES = [
  # CRITICAL
  {"case_id":"CRIT-001","zone":"CRITICAL","input":"J'ai mal à la poitrine avec des sueurs froides","expected_urgency":"urgent"},
  {"case_id":"CRIT-002","zone":"CRITICAL","input":"Douleur thoracique qui serre et bras gauche engourdi","expected_urgency":"urgent"},
  {"case_id":"CRIT-003","zone":"CRITICAL","input":"Je respire mal depuis ce matin","expected_urgency":"urgent"},
  {"case_id":"CRIT-004","zone":"CRITICAL","input":"Difficulté à respirer + oppression poitrine","expected_urgency":"urgent"},
  {"case_id":"CRIT-005","zone":"CRITICAL","input":"J'ai perdu connaissance il y a une heure","expected_urgency":"urgent"},
  {"case_id":"CRIT-006","zone":"CRITICAL","input":"Syncope pendant effort sans prévenir","expected_urgency":"urgent"},
  {"case_id":"CRIT-007","zone":"CRITICAL","input":"Faiblesse d'un côté du corps et parole bizarre","expected_urgency":"urgent"},
  {"case_id":"CRIT-008","zone":"CRITICAL","input":"Trouble de la parole soudain + visage qui tombe","expected_urgency":"urgent"},
  {"case_id":"CRIT-009","zone":"CRITICAL","input":"Douleur ventre très forte et brutale","expected_urgency":"urgent"},
  {"case_id":"CRIT-010","zone":"CRITICAL","input":"Ventre dur comme du bois et douleur intense","expected_urgency":"urgent"},
  {"case_id":"CRIT-011","zone":"CRITICAL","input":"Idées suicidaires, envie d'en finir","expected_urgency":"urgent"},
  {"case_id":"CRIT-012","zone":"CRITICAL","input":"Envie de me faire du mal ce soir","expected_urgency":"urgent"},
  {"case_id":"CRIT-013","zone":"CRITICAL","input":"Œdème langue et difficulté à respirer","expected_urgency":"urgent"},
  {"case_id":"CRIT-014","zone":"CRITICAL","input":"Gonflement visage + je respire mal","expected_urgency":"urgent"},
  {"case_id":"CRIT-015","zone":"CRITICAL","input":"Brûlure urinaire + fièvre + mal au dos","expected_urgency":"medical_urgent"},
  {"case_id":"CRIT-016","zone":"CRITICAL","input":"Fièvre, mal aux reins, ça brûle quand j'urine","expected_urgency":"medical_urgent"},
  {"case_id":"CRIT-017","zone":"CRITICAL","input":"Douleur mollet gonflé + essoufflement","expected_urgency":"urgent"},
  {"case_id":"CRIT-018","zone":"CRITICAL","input":"Trauma crânien sous anticoagulant, confusion","expected_urgency":"urgent"},
  {"case_id":"CRIT-019","zone":"CRITICAL","input":"Saignement abondant avec malaise","expected_urgency":"urgent"},
  {"case_id":"CRIT-020","zone":"CRITICAL","input":"Douleur ventre + retard règles + malaise","expected_urgency":"medical_urgent"},

  # MODERATE
  {"case_id":"MOD-001","zone":"MODERATE","input":"Femme 80 ans, douleur abdominale forte après repas ou après verre d'eau, répétée chaque matin","expected_category":"digestif_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-002","zone":"MODERATE","input":"Douleur après repas depuis plusieurs semaines, analyses normales","expected_category":"digestif_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-003","zone":"MODERATE","input":"Ballonnements et constipation depuis un mois","expected_category":"digestif_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-004","zone":"MODERATE","input":"Nausées et vomissements depuis deux jours","expected_category":"digestif_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-005","zone":"MODERATE","input":"Brûlures d'estomac et remontées acides après repas","expected_category":"digestif_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-006","zone":"MODERATE","input":"Fatigue, prise de poids et peau sèche depuis 2 mois","expected_category":"metabolique_hormonal_suspect","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-007","zone":"MODERATE","input":"Perte de poids, palpitations et fatigue","expected_category":"metabolique_hormonal_suspect","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-008","zone":"MODERATE","input":"J'ai très soif et j'urine beaucoup","expected_category":"metabolique_hormonal_suspect","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-009","zone":"MODERATE","input":"Froid tout le temps et chute de cheveux","expected_category":"metabolique_hormonal_suspect","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-010","zone":"MODERATE","input":"Fatigue chronique mais pas de fièvre","expected_category":"fatigue_asthenie","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-011","zone":"MODERATE","input":"Douleur mollet avec gonflement","expected_category":"musculo_squelettique","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-012","zone":"MODERATE","input":"Mal au dos depuis 3 semaines, ça descend dans la jambe","expected_category":"musculo_squelettique","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-013","zone":"MODERATE","input":"Douleur genou après sport, gonflé depuis hier","expected_category":"musculo_squelettique","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-014","zone":"MODERATE","input":"Brûlures urinaires et envies fréquentes","expected_category":"urinaire","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-015","zone":"MODERATE","input":"Urines troubles et douleur en urinant","expected_category":"urinaire","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-016","zone":"MODERATE","input":"Règles en retard avec douleur bas ventre","expected_category":"gynecologique_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-017","zone":"MODERATE","input":"Pertes vaginales bizarres et douleurs pelviennes","expected_category":"gynecologique_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-018","zone":"MODERATE","input":"Douleurs de règles très gênantes tous les mois","expected_category":"gynecologique_simple","expected_urgency":"medical_consultation"},
  {"case_id":"MOD-019","zone":"MODERATE","input":"Je dors mal, stress, fatigue depuis longtemps","expected_category":"sommeil_stress_anxiete","expected_urgency":"non_urgent"},
  {"case_id":"MOD-020","zone":"MODERATE","input":"Anxiété légère, insomnie et ruminations","expected_category":"sommeil_stress_anxiete","expected_urgency":"non_urgent"},

  # LOW
  {"case_id":"LOW-001","zone":"LOW","input":"J'ai mal à la gorge et le nez bouché","expected_category":"orl_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-002","zone":"LOW","input":"Nez qui coule, éternuements, gorge irritée","expected_category":"orl_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-003","zone":"LOW","input":"Petite toux depuis hier sans fièvre","expected_category":"orl_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-004","zone":"LOW","input":"Rhume, nez bouché, je tousse un peu","expected_category":"orl_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-005","zone":"LOW","input":"Boutons rouges sur le visage, ça gratte","expected_category":"dermatologie_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-006","zone":"LOW","input":"Plaques sèches sur la peau depuis quelques jours","expected_category":"dermatologie_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-007","zone":"LOW","input":"Acné sur les joues depuis 2 mois","expected_category":"dermatologie_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-008","zone":"LOW","input":"Eczéma et démangeaisons","expected_category":"dermatologie_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-009","zone":"LOW","input":"Mal au dos après sport","expected_category":"musculo_squelettique","expected_urgency":"non_urgent"},
  {"case_id":"LOW-010","zone":"LOW","input":"Douleur épaule après effort","expected_category":"musculo_squelettique","expected_urgency":"non_urgent"},
  {"case_id":"LOW-011","zone":"LOW","input":"Courbatures après entraînement","expected_category":"musculo_squelettique","expected_urgency":"non_urgent"},
  {"case_id":"LOW-012","zone":"LOW","input":"Je dors mal depuis deux nuits","expected_category":"sommeil_stress_anxiete","expected_urgency":"non_urgent"},
  {"case_id":"LOW-013","zone":"LOW","input":"Stress au travail, un peu fatigué","expected_category":"sommeil_stress_anxiete","expected_urgency":"non_urgent"},
  {"case_id":"LOW-014","zone":"LOW","input":"Ballonnements après repas, pas de douleur forte","expected_category":"digestif_simple","expected_urgency":"non_urgent"},
  {"case_id":"LOW-015","zone":"LOW","input":"Je ne me sens pas bien depuis quelques jours","expected_category":"general_vague","expected_urgency":"medical_consultation"},

  # DIRTY
  {"case_id":"DIRTY-001","zone":"DIRTY","input":"jsui ko mal o ventre depui 3j","expected_zone":"digestif_or_vague_medical"},
  {"case_id":"DIRTY-002","zone":"DIRTY","input":"g mal au bide apres manger sa fait super mal","expected_zone":"digestif_medical"},
  {"case_id":"DIRTY-003","zone":"DIRTY","input":"douleur ventre +++++ apres eau ????","expected_zone":"digestif_medical"},
  {"case_id":"DIRTY-004","zone":"DIRTY","input":"fatigue mais pa de fievre jsais pa pk","expected_zone":"fatigue_medical"},
  {"case_id":"DIRTY-005","zone":"DIRTY","input":"mal coeur + transpire jcroi","expected_urgency":"urgent"},
  {"case_id":"DIRTY-006","zone":"DIRTY","input":"respire pa bien depuis ce matin","expected_urgency":"urgent"},
  {"case_id":"DIRTY-007","zone":"DIRTY","input":"jai perdu connaissance taleur","expected_urgency":"urgent"},
  {"case_id":"DIRTY-008","zone":"DIRTY","input":"envie d'en finir j'en peux plus","expected_urgency":"urgent"},
  {"case_id":"DIRTY-009","zone":"DIRTY","input":"brulure pipi fievre mal dos","expected_urgency":"medical_urgent"},
  {"case_id":"DIRTY-010","zone":"DIRTY","input":"mollet gonfle douloureux","expected_category":"musculo_squelettique","expected_urgency":"medical_consultation"},
  {"case_id":"DIRTY-011","zone":"DIRTY","input":"regles retard mal bas ventre","expected_category":"gynecologique_simple","expected_urgency":"medical_consultation"},
  {"case_id":"DIRTY-012","zone":"DIRTY","input":"nez bouche gorge pique toux","expected_category":"orl_simple","expected_urgency":"non_urgent"},
  {"case_id":"DIRTY-013","zone":"DIRTY","input":"bouton joue gratte de ouf","expected_category":"dermatologie_simple","expected_urgency":"non_urgent"},
  {"case_id":"DIRTY-014","zone":"DIRTY","input":"je dor pa stress fatigue","expected_category":"sommeil_stress_anxiete","expected_urgency":"non_urgent"},
  {"case_id":"DIRTY-015","zone":"DIRTY","input":"chaud froid tremblement bizarre","expected_category":"metabolique_hormonal_suspect","expected_urgency":"medical_consultation"},
  {"case_id":"DIRTY-016","zone":"DIRTY","input":"j'ai un truc chelou gorge ca passe pas","expected_category":"orl_simple","expected_urgency":"non_urgent"},
  {"case_id":"DIRTY-017","zone":"DIRTY","input":"mal partout jsui ko complet","expected_category":"fatigue_asthenie","expected_urgency":"medical_consultation"},
  {"case_id":"DIRTY-018","zone":"DIRTY","input":"jme sens pas bien jsp expliquer","expected_category":"general_vague","expected_urgency":"medical_consultation"},
  {"case_id":"DIRTY-019","zone":"DIRTY","input":"ventre dur bois douleur grave","expected_urgency":"urgent"},
  {"case_id":"DIRTY-020","zone":"DIRTY","input":"douleur poitrine ca serre sueur froide","expected_urgency":"urgent"},

  # EDGE
  {"case_id":"EDGE-001","zone":"EDGE","input":"Femme 80 ans, douleur abdominale forte après repas, tous les matins","expected_category":"digestif_simple","expected_urgency":"medical_consultation"},
  {"case_id":"EDGE-002","zone":"EDGE","input":"Homme 82 ans, fatigue brutale et essoufflement","expected_urgency":"urgent"},
  {"case_id":"EDGE-003","zone":"EDGE","input":"Femme 75 ans, confusion légère et fièvre","expected_urgency":"medical_urgent"},
  {"case_id":"EDGE-004","zone":"EDGE","input":"Enfant 5 ans, fièvre et mal de gorge","expected_category":"orl_simple","expected_urgency":"medical_consultation"},
  {"case_id":"EDGE-005","zone":"EDGE","input":"Femme enceinte, douleur bas ventre","expected_urgency":"medical_urgent"},
  {"case_id":"EDGE-006","zone":"EDGE","input":"Personne sous anticoagulant, chute avec hématome tête","expected_urgency":"urgent"},
  {"case_id":"EDGE-007","zone":"EDGE","input":"Douleur thoracique mais anxieux, ça passe parfois","expected_urgency":"urgent"},
  {"case_id":"EDGE-008","zone":"EDGE","input":"Fatigue chronique, perte de poids et sueurs nocturnes","expected_urgency":"medical_consultation"},
  {"case_id":"EDGE-009","zone":"EDGE","input":"Mal au ventre après repas, perte de poids, 80 ans","expected_urgency":"medical_consultation"},
  {"case_id":"EDGE-010","zone":"EDGE","input":"Douleur abdominale légère mais sang dans les selles","expected_urgency":"medical_urgent"},
  {"case_id":"EDGE-011","zone":"EDGE","input":"Mal de tête violent soudain, jamais eu ça","expected_urgency":"urgent"},
  {"case_id":"EDGE-012","zone":"EDGE","input":"Vertiges et faiblesse d'un bras","expected_urgency":"urgent"},
  {"case_id":"EDGE-013","zone":"EDGE","input":"Éruption cutanée + gonflement visage","expected_urgency":"medical_urgent"},
  {"case_id":"EDGE-014","zone":"EDGE","input":"Douleur jambe après long voyage, mollet gonflé","expected_urgency":"medical_consultation"},
  {"case_id":"EDGE-015","zone":"EDGE","input":"Brûlure urinaire sans fièvre ni mal au dos","expected_category":"urinaire","expected_urgency":"medical_consultation"},
]


def evaluate_case(case, result):
    """
    Повертає: status (PASS/PARTIAL/FAIL), issue
    Логіка:
      - CRITICAL/DIRTY з expected_urgency=urgent/medical_urgent → FAIL якщо не виконано
      - expected_category → PARTIAL якщо urgency ok але cat wrong
      - expected_zone → PASS якщо urgency не urgent і cat не vague (для dirty з zone)
    """
    issues = []
    zone = case["zone"]
    exp_urgency = case.get("expected_urgency")
    exp_category = case.get("expected_category")
    exp_zone = case.get("expected_zone", "")

    got_urgency = result["urgency"]
    got_cat = result["category"]

    # ── Urgency check ──
    if exp_urgency:
        if exp_urgency == "urgent":
            if got_urgency != "urgent":
                issues.append(f"MISSED DANGER: expected=urgent, got={got_urgency}")
        elif exp_urgency == "medical_urgent":
            if got_urgency not in ("urgent", "medical_urgent"):
                issues.append(f"UNDER-ALARM: expected=medical_urgent, got={got_urgency}")
        elif exp_urgency == "medical_consultation":
            if got_urgency == "urgent":
                issues.append(f"OVER-ALARM: expected=medical_consultation, got=urgent")
            elif got_urgency == "non_urgent":
                issues.append(f"UNDER: expected=medical_consultation, got=non_urgent")
        elif exp_urgency == "non_urgent":
            if got_urgency == "urgent":
                issues.append(f"OVER-ALARM: expected=non_urgent, got=urgent")

    # ── Category check ──
    if exp_category:
        if got_cat != exp_category:
            # Tolerant: якщо urgency правильний і cat суміжна — PARTIAL
            issues.append(f"WRONG CAT: expected={exp_category}, got={got_cat}")

    # ── Zone check (DIRTY без explicit expected) ──
    if exp_zone and not exp_urgency and not exp_category:
        if "digestif" in exp_zone:
            if got_cat not in ("digestif_simple", "general_vague"):
                issues.append(f"ZONE: expected digestif/vague, got={got_cat}")
            if got_urgency == "non_urgent" and got_cat == "general_vague":
                issues.append("ZONE: vague+non_urgent not acceptable for digestif zone")
        elif "fatigue" in exp_zone:
            if got_cat not in ("fatigue_asthenie", "general_vague"):
                issues.append(f"ZONE: expected fatigue/vague, got={got_cat}")

    # ── Status ──
    if not issues:
        return "PASS", ""

    # Missed danger = завжди FAIL
    missed = any("MISSED DANGER" in i or "UNDER-ALARM" in i for i in issues)
    over = any("OVER-ALARM" in i for i in issues)
    cat_only = all("WRONG CAT" in i or "ZONE" in i for i in issues)

    if missed:
        return "FAIL", "; ".join(issues)
    if over:
        return "FAIL", "; ".join(issues)
    if cat_only:
        return "PARTIAL", "; ".join(issues)
    return "PARTIAL", "; ".join(issues)


def run():
    results = []
    pass_count = partial_count = fail_count = 0
    missed_danger = []

    print(f"\n{'='*100}")
    print("ClairDiag v3 — Final Validation Pack 100 Cases")
    print(f"{'='*100}")
    print(f"\n{'case_id':<12} {'zone':<10} {'cat':<30} {'urgency':<22} {'conf':<12} {'status':<8} issue")
    print(f"{'-'*100}")

    for case in CASES:
        result = run_case(case["input"])
        status, issue = evaluate_case(case, result)

        if status == "PASS":
            pass_count += 1
            icon = "✅"
        elif status == "PARTIAL":
            partial_count += 1
            icon = "🟡"
        else:
            fail_count += 1
            icon = "❌"

        if "MISSED DANGER" in issue or "UNDER-ALARM" in issue:
            missed_danger.append({"case_id": case["case_id"], "input": case["input"][:60], "issue": issue})

        conf_str = f"{result['confidence_level']}({result['confidence_score']})"
        cat_str = (result["category"] or "None")[:28]
        urg_str = result["urgency"][:20]
        issue_str = issue[:45] if issue else ""

        print(f"{icon} {case['case_id']:<10} {case['zone']:<10} {cat_str:<30} {urg_str:<22} {conf_str:<12} {status:<8} {issue_str}")

        results.append({
            "case_id": case["case_id"],
            "zone": case["zone"],
            "input": case["input"][:60],
            "output_category": result["category"],
            "output_urgency": result["urgency"],
            "confidence": conf_str,
            "status": status,
            "issue": issue,
        })

    # ── Підсумок ──
    total = len(CASES)
    print(f"\n{'='*100}")
    print(f"РЕЗУЛЬТАТ: {pass_count}/{total} PASS | {partial_count} PARTIAL | {fail_count} FAIL")
    print(f"{'='*100}")

    # ── Missed danger ──
    print(f"\n🔴 MISSED DANGER / UNDER-ALARM: {len(missed_danger)}")
    if missed_danger:
        for m in missed_danger:
            print(f"   [{m['case_id']}] {m['input']}")
            print(f"           issue: {m['issue']}")
    else:
        print("   ✅ Жодного — критичний поріг виконано")

    # ── FAIL список ──
    fails = [r for r in results if r["status"] == "FAIL"]
    partials = [r for r in results if r["status"] == "PARTIAL"]

    if fails:
        print(f"\n❌ FAIL ({len(fails)}):")
        for r in fails:
            print(f"   [{r['case_id']}] {r['input']}")
            print(f"           cat={r['output_category']} | urg={r['output_urgency']} | {r['issue']}")

    if partials:
        print(f"\n🟡 PARTIAL ({len(partials)}):")
        for r in partials:
            print(f"   [{r['case_id']}] {r['input']}")
            print(f"           cat={r['output_category']} | urg={r['output_urgency']} | {r['issue']}")

    # ── По зонах ──
    print(f"\n📊 По зонах:")
    for zone in ["CRITICAL", "MODERATE", "LOW", "DIRTY", "EDGE"]:
        zone_res = [r for r in results if r["zone"] == zone]
        z_pass = sum(1 for r in zone_res if r["status"] == "PASS")
        z_part = sum(1 for r in zone_res if r["status"] == "PARTIAL")
        z_fail = sum(1 for r in zone_res if r["status"] == "FAIL")
        print(f"   {zone:<10} {z_pass}/{len(zone_res)} PASS | {z_part} PARTIAL | {z_fail} FAIL")

    print()


if __name__ == "__main__":
    run()