"""
ClairDiag v3 — Independent Test 50 Cases
=========================================
Запуск: python v3_dev/tests/run_independent_test_50.py

50 кейсів незалежних (Roman не бачив їх під час розробки).
Не дивись на expected_* — запусти спочатку, порівняй після.

Формат: case_id | category | urgency | confidence | status | issue
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


def get_category_priority(category):
    for m in COMMON_SYMPTOM_MAPPING:
        if m["category"] == category:
            return m["priority"]
    return 0


def get_urgency_from_config(category):
    if not category:
        return "unknown"
    return COMMON_CONDITIONS_CONFIG.get(category, {}).get("urgency", "unknown")


def run_case(text, patient_context=None):
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

    pattern_result = run_pattern_engine(norm_text, patient_context)
    pattern_urgency = pattern_result.get("urgency") if pattern_result else None

    confidence = compute_v3_confidence(
        category=got_cat,
        category_matches=mapped.get("category_matches", 0),
        all_hits=mapped.get("all_hits", []),
        combination_matched=False,
        temporal=mapped.get("temporal", "unknown"),
        patient_context=patient_context,
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
    elif pattern_urgency == "urgent_medical_review":
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


# ── Urgency normalization ────────────────────────────────────────────────────
# v3 використовує "medical_urgent", тест очікує "urgent_medical_review"
# маппінг: urgent_medical_review → medical_urgent (рівнозначні для scoring)

def normalize_urgency(u):
    """Нормалізує urgent_medical_review → medical_urgent для порівняння."""
    if u == "urgent_medical_review":
        return "medical_urgent"
    return u


# ── Evaluate ────────────────────────────────────────────────────────────────

def evaluate_case(case, result):
    issues = []
    exp_urgency = normalize_urgency(case.get("expected_urgency", ""))
    got_urgency = result["urgency"]

    if exp_urgency == "urgent":
        if got_urgency != "urgent":
            issues.append(f"MISSED_DANGER: expected=urgent, got={got_urgency}")
    elif exp_urgency == "medical_urgent":
        if got_urgency not in ("urgent", "medical_urgent"):
            issues.append(f"MISSED_DANGER: expected=urgent_medical_review, got={got_urgency}")
    elif exp_urgency == "medical_consultation":
        if got_urgency == "urgent":
            issues.append(f"OVER_TRIAGE: expected=medical_consultation, got=urgent")
        elif got_urgency == "non_urgent":
            issues.append(f"UNDER: expected=medical_consultation, got=non_urgent")
    elif exp_urgency == "non_urgent":
        if got_urgency == "urgent":
            issues.append(f"OVER_TRIAGE: expected=non_urgent, got=urgent")

    if not issues:
        return "PASS", ""
    missed = any("MISSED_DANGER" in i for i in issues)
    over = any("OVER_TRIAGE" in i for i in issues)
    if missed:
        return "FAIL", "; ".join(issues)
    if over:
        return "FAIL_OVER", "; ".join(issues)
    return "PARTIAL", "; ".join(issues)


# ── 50 Cases ──────────────────────────────────────────────────────────────────

CASES = [
    # easy_red_flag (5)
    {"case_id": "IND-001", "meta": "easy_red_flag", "input": "J'ai une douleur thoracique très forte qui irradie dans le bras gauche depuis 30 minutes", "patient_context": {"age": 58, "sex": "M", "risk_factors": ["tabac_actif", "HTA"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-002", "meta": "easy_red_flag", "input": "J'ai très mal à la tête, c'est apparu d'un coup il y a 1 heure, c'est la pire douleur de ma vie", "patient_context": {"age": 45, "sex": "F"}, "expected_urgency": "urgent"},
    {"case_id": "IND-003", "meta": "easy_red_flag", "input": "J'ai la bouche qui se déforme et je n'arrive plus à parler depuis 20 minutes", "patient_context": {"age": 65, "sex": "M"}, "expected_urgency": "urgent"},
    {"case_id": "IND-004", "meta": "easy_red_flag", "input": "Mon enfant a 2 ans, il a 39.5 de fièvre depuis ce matin et des taches rouges sur les jambes qui ne disparaissent pas quand j'appuie", "patient_context": {"age": 2, "sex": "F"}, "expected_urgency": "urgent"},
    {"case_id": "IND-005", "meta": "easy_red_flag", "input": "J'ai des idées noires, je pense à en finir avec ma vie", "patient_context": {"age": 35, "sex": "F"}, "expected_urgency": "urgent"},

    # clinical_patterns PATTERN-01..03 (3)
    {"case_id": "IND-006", "meta": "PATTERN-01_atypique", "input": "Depuis 2 jours j'ai des brûlures à l'estomac qui ne passent pas, c'est différent de mes aigreurs habituelles", "patient_context": {"age": 62, "sex": "M", "risk_factors": ["tabac_actif", "HTA", "dyslipidémie"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-007", "meta": "PATTERN-02_femme_diabetique", "input": "Je me sens vraiment pas bien depuis ce matin, j'ai des sueurs et la nausée, je crois que c'est l'estomac", "patient_context": {"age": 67, "sex": "F", "risk_factors": ["diabete"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-008", "meta": "PATTERN-03_EP", "input": "Depuis hier j'ai du mal à respirer, c'est apparu progressivement", "patient_context": {"age": 35, "sex": "F", "risk_factors": ["COP"]}, "expected_urgency": "urgent"},

    # clinical_patterns PATTERN-04..10 (7)
    {"case_id": "IND-009", "meta": "PATTERN-03_post_op", "input": "Je suis essoufflé, ça fait 3 jours, j'ai été opéré du genou il y a 2 semaines", "patient_context": {"age": 55, "sex": "M", "risk_factors": ["post_op_recent"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-010", "meta": "PATTERN-04_asthme_EP", "input": "J'ai une crise d'asthme qui ne passe pas avec ma ventoline depuis ce matin, j'ai mal sur le côté quand je respire", "patient_context": {"age": 42, "sex": "F", "risk_factors": ["asthme"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-011", "meta": "PATTERN-05_dissection", "input": "J'ai eu une douleur déchirante dans le dos d'un coup, qui descend maintenant", "patient_context": {"age": 68, "sex": "M", "risk_factors": ["HTA"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-012", "meta": "PATTERN-08_AIT", "input": "Hier soir j'ai eu une faiblesse dans le bras droit pendant 20 minutes, ça a disparu, je vais bien maintenant", "patient_context": {"age": 70, "sex": "M", "risk_factors": ["HTA", "FA_connue"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-013", "meta": "PATTERN-09_meningite", "input": "Mon mari de 50 ans a 39 de fièvre, mal à la tête très fort et la nuque raide depuis ce matin", "patient_context": {"age": 50, "sex": "M"}, "expected_urgency": "urgent"},
    {"case_id": "IND-014", "meta": "PATTERN-10_meningite_atypique", "input": "Ma mère de 82 ans est confuse depuis hier, elle ne reconnaît pas bien les gens. Pas de fièvre mesurée", "patient_context": {"age": 82, "sex": "F", "risk_factors": ["immunodepression"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-015", "meta": "PATTERN-11_sepsis", "input": "J'ai 38.7 de fièvre depuis hier, je me sens vraiment faible, j'ai du mal à tenir debout, mon cœur bat vite", "patient_context": {"age": 56, "sex": "F"}, "expected_urgency": "urgent"},

    # clinical_patterns PATTERN-12..19 (8)
    {"case_id": "IND-016", "meta": "PATTERN-12_neutropenie", "input": "Je suis sous chimio pour mon cancer du sein, j'ai 38.2 de fièvre depuis ce matin", "patient_context": {"age": 48, "sex": "F", "risk_factors": ["chimio_active", "cancer_actif"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-017", "meta": "PATTERN-13_GEU", "input": "J'ai mal au ventre depuis ce matin, mes règles sont en retard de 10 jours", "patient_context": {"age": 28, "sex": "F"}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-018", "meta": "PATTERN-14_preeclampsie", "input": "Je suis enceinte de 7 mois, j'ai mal à la tête fort et je vois des étoiles depuis hier", "patient_context": {"age": 32, "sex": "F", "pregnancy_status": "pregnant"}, "expected_urgency": "urgent"},
    {"case_id": "IND-019", "meta": "PATTERN-15_HSD", "input": "Mon père de 78 ans est somnolent depuis hier soir et un peu confus. Il prend du Préviscan pour son cœur", "patient_context": {"age": 78, "sex": "M", "risk_factors": ["anticoagulation_AOD_AVK"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-020", "meta": "PATTERN-16_hemorragie_dig", "input": "Je me suis senti faible et j'ai failli tomber ce matin. Je prends de l'aspirine et de l'Ibuprofène pour mon arthrose", "patient_context": {"age": 65, "sex": "M", "risk_factors": ["AINS_chronique"]}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-021", "meta": "PATTERN-17_pyelonephrite", "input": "J'ai des brûlures quand je fais pipi depuis hier et j'ai 38.5 de fièvre avec mal au dos", "patient_context": {"age": 35, "sex": "F"}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-022", "meta": "PATTERN-18_cystite_homme", "input": "J'ai des brûlures quand j'urine depuis 2 jours", "patient_context": {"age": 45, "sex": "M"}, "expected_urgency": "medical_consultation"},
    {"case_id": "IND-023", "meta": "PATTERN-19_ischem_mesent", "input": "J'ai très mal au ventre depuis ce matin, ça a commencé d'un coup", "patient_context": {"age": 75, "sex": "M", "risk_factors": ["FA_connue", "FA_non_anticoagulée"]}, "expected_urgency": "urgent_medical_review"},

    # PE-09 orthopnée + DVT (2)
    {"case_id": "IND-024", "meta": "PE09_orthopnee", "input": "Je dors avec 4 oreillers parce que je suffoque allongé depuis 1 semaine", "patient_context": {"age": 72, "sex": "M", "risk_factors": ["HTA", "diabete"]}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-025", "meta": "DVT", "input": "J'ai le mollet droit qui est gonflé, chaud et douloureux depuis hier", "patient_context": {"age": 55, "sex": "F", "risk_factors": ["COP", "voyage_long"]}, "expected_urgency": "urgent_medical_review"},

    # Atypical + minimization (10)
    {"case_id": "IND-026", "meta": "AIT_amaurose", "input": "Tout à coup ce matin j'ai vu trouble d'un œil pendant quelques minutes puis ça a passé", "patient_context": {"age": 68, "sex": "M", "risk_factors": ["HTA", "tabac_sevré"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-027", "meta": "neutropenie_frissons", "input": "Je suis en chimio pour leucémie, j'ai des frissons et je ne me sens pas bien", "patient_context": {"age": 60, "sex": "M", "risk_factors": ["chimio_active", "cancer_actif", "immunodepression"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-028", "meta": "EP_grossesse", "input": "Je suis enceinte de 6 mois, je n'arrive plus à respirer normalement, c'est apparu en quelques heures", "patient_context": {"age": 30, "sex": "F", "pregnancy_status": "pregnant"}, "expected_urgency": "urgent"},
    {"case_id": "IND-029", "meta": "purpura_fulminans", "input": "J'ai 39.5 de fièvre, mal à la tête et de petites taches rouges qui apparaissent sur mes jambes", "patient_context": {"age": 22, "sex": "M"}, "expected_urgency": "urgent"},
    {"case_id": "IND-030", "meta": "dissection_atypique", "input": "J'ai eu une douleur très forte entre les épaules d'un coup ce matin, maintenant ça pulse dans le ventre", "patient_context": {"age": 72, "sex": "M", "risk_factors": ["HTA", "tabac_actif"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-031", "meta": "sepsis_atypique", "input": "Mon mari de 70 ans est très fatigué et un peu confus depuis hier, sa peau est marbrée", "patient_context": {"age": 70, "sex": "M"}, "expected_urgency": "urgent"},
    {"case_id": "IND-032", "meta": "GEU_atypique", "input": "J'ai un peu mal au ventre du côté droit, ça fait 3-4 jours", "patient_context": {"age": 24, "sex": "F"}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-033", "meta": "EP_post_partum", "input": "J'ai accouché il y a 3 semaines et depuis hier je suis très essoufflée", "patient_context": {"age": 31, "sex": "F", "pregnancy_status": "post_partum_6w"}, "expected_urgency": "urgent"},
    {"case_id": "IND-034", "meta": "HSD_chute_oubliee", "input": "Mon père de 75 ans est tombé dans la salle de bain il y a 3 jours, ça allait, mais aujourd'hui il a mal à la tête et il dort beaucoup. Il prend Eliquis pour le cœur", "patient_context": {"age": 75, "sex": "M", "risk_factors": ["anticoagulation_AOD_AVK"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-035", "meta": "hemoptysie", "input": "Je tousse et il y a du sang dans mes crachats depuis hier", "patient_context": {"age": 58, "sex": "M", "risk_factors": ["tabac_actif"]}, "expected_urgency": "urgent_medical_review"},

    # Anti-anchor + minimization (7)
    {"case_id": "IND-036", "meta": "anchor_anxiety_SCA", "input": "Je suis anxieuse depuis longtemps, là j'ai des palpitations et le cœur qui bat vite, c'est sûrement encore une crise", "patient_context": {"age": 56, "sex": "F", "risk_factors": ["HTA", "diabete"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-037", "meta": "anchor_migraine_atypique", "input": "J'ai ma migraine, mais cette fois c'est différent, ça dure depuis 3 jours et j'ai des fourmillements dans le bras", "patient_context": {"age": 40, "sex": "F", "risk_factors": ["migraine_connue"]}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-038", "meta": "min_dyspnee", "input": "Je m'essouffle un peu en montant les escaliers ces derniers jours, mais ça va, je vieillis", "patient_context": {"age": 64, "sex": "M", "risk_factors": ["tabac_actif", "HTA"]}, "expected_urgency": "medical_consultation"},
    {"case_id": "IND-039", "meta": "min_chest_pain", "input": "J'ai eu un peu mal à la poitrine cette semaine, juste 4/10, sûrement musculaire vu comme j'ai porté", "patient_context": {"age": 60, "sex": "M", "risk_factors": ["tabac_actif", "atcd_familial_cv_precoce"]}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-040", "meta": "AIT_minimise", "input": "J'ai eu un drôle de moment hier, je n'arrivais plus à trouver mes mots pendant 5 minutes, mais c'est passé, je suis fatigué en ce moment", "patient_context": {"age": 66, "sex": "F", "risk_factors": ["HTA", "FA_connue"]}, "expected_urgency": "urgent"},
    {"case_id": "IND-041", "meta": "GI_bleed_minimise", "input": "Mes selles sont un peu plus foncées que d'habitude, j'ai aussi des vertiges, j'ai dû mal manger", "patient_context": {"age": 70, "sex": "M", "risk_factors": ["AINS_chronique", "alcool_chronique"]}, "expected_urgency": "urgent_medical_review"},
    {"case_id": "IND-042", "meta": "BPCO_EP", "input": "Je suis BPCO et plus essoufflé qu'habituellement, j'ai mal sur le côté droit en respirant", "patient_context": {"age": 68, "sex": "M", "risk_factors": ["BPCO", "tabac_sevré"]}, "expected_urgency": "urgent"},

    # False positive traps (8)
    {"case_id": "IND-043", "meta": "FP_rhume", "input": "J'ai un rhume avec le nez qui coule et un mal de gorge depuis 2 jours", "patient_context": {"age": 28, "sex": "F"}, "expected_urgency": "non_urgent"},
    {"case_id": "IND-044", "meta": "FP_lumbago", "input": "J'ai un lumbago depuis hier, j'ai porté un meuble, j'ai mal au bas du dos", "patient_context": {"age": 35, "sex": "M"}, "expected_urgency": "non_urgent"},
    {"case_id": "IND-045", "meta": "FP_fatigue_chronique", "input": "Je suis fatiguée ces derniers temps, j'ai du mal à me lever le matin, je dors mal", "patient_context": {"age": 38, "sex": "F"}, "expected_urgency": "medical_consultation"},
    {"case_id": "IND-046", "meta": "FP_acne", "input": "J'ai des boutons sur le visage depuis 1 semaine", "patient_context": {"age": 22, "sex": "F"}, "expected_urgency": "non_urgent"},
    {"case_id": "IND-047", "meta": "FP_dysmenorrhee", "input": "J'ai des règles douloureuses comme d'habitude depuis hier", "patient_context": {"age": 25, "sex": "F"}, "expected_urgency": "non_urgent"},
    {"case_id": "IND-048", "meta": "FP_stress", "input": "Je suis stressée par mon travail, je dors mal, je ne mange pas bien", "patient_context": {"age": 33, "sex": "F"}, "expected_urgency": "non_urgent"},
    {"case_id": "IND-049", "meta": "FP_gastro", "input": "J'ai eu la diarrhée hier, ça commence à passer aujourd'hui", "patient_context": {"age": 30, "sex": "M"}, "expected_urgency": "non_urgent"},
    {"case_id": "IND-050", "meta": "FP_cystite_simple", "input": "J'ai des brûlures quand je fais pipi depuis hier, c'est la 3e fois cette année", "patient_context": {"age": 32, "sex": "F"}, "expected_urgency": "medical_consultation"},
]


def run():
    results = []
    pass_count = partial_count = fail_count = fail_over_count = 0
    missed_danger = []
    over_triage = []

    print(f"\n{'='*110}")
    print("ClairDiag v3 — Independent Test 50 Cases")
    print(f"{'='*110}")
    print(f"\n{'case_id':<12} {'meta':<28} {'category':<28} {'urgency':<22} {'conf':<12} {'status':<10} issue")
    print(f"{'-'*110}")

    for case in CASES:
        result = run_case(case["input"], case.get("patient_context"))
        status, issue = evaluate_case(case, result)

        if status == "PASS":
            pass_count += 1
            icon = "✅"
        elif status == "FAIL_OVER":
            fail_over_count += 1
            fail_count += 1
            icon = "🟠"
        elif status == "PARTIAL":
            partial_count += 1
            icon = "🟡"
        else:
            fail_count += 1
            icon = "❌"

        if "MISSED_DANGER" in issue:
            missed_danger.append({
                "case_id": case["case_id"],
                "meta": case["meta"],
                "input": case["input"][:70],
                "expected": case.get("expected_urgency"),
                "got": result["urgency"],
                "issue": issue,
            })
        if "OVER_TRIAGE" in issue:
            over_triage.append({
                "case_id": case["case_id"],
                "meta": case["meta"],
                "input": case["input"][:70],
                "expected": case.get("expected_urgency"),
                "got": result["urgency"],
            })

        conf_str = f"{result['confidence_level']}({result['confidence_score']})"
        cat_str = (result["category"] or "None")[:26]
        urg_str = result["urgency"][:20]
        meta_str = case["meta"][:26]
        issue_str = issue[:40] if issue else ""

        print(f"{icon} {case['case_id']:<10} {meta_str:<28} {cat_str:<28} {urg_str:<22} {conf_str:<12} {status:<10} {issue_str}")

        results.append({
            "case_id": case["case_id"],
            "meta": case["meta"],
            "input": case["input"][:70],
            "expected_urgency": case.get("expected_urgency"),
            "output_category": result["category"],
            "output_urgency": result["urgency"],
            "confidence": conf_str,
            "status": status,
            "issue": issue,
        })

    total = len(CASES)
    print(f"\n{'='*110}")
    print(f"РЕЗУЛЬТАТ: {pass_count}/{total} PASS | {partial_count} PARTIAL | {fail_count} FAIL")
    print(f"{'='*110}")

    # Missed danger
    print(f"\n🔴 MISSED_DANGER: {len(missed_danger)} / 42 (urgent/medical_urgent expected)")
    if missed_danger:
        for m in missed_danger:
            print(f"   [{m['case_id']}] {m['meta']}")
            print(f"           input:    {m['input']}")
            print(f"           expected: {m['expected']} | got: {m['got']}")
    else:
        print("   ✅ Жодного")

    # Over-triage
    print(f"\n🟠 OVER_TRIAGE: {len(over_triage)} / 8 traps")
    if over_triage:
        for o in over_triage:
            print(f"   [{o['case_id']}] {o['meta']}")
            print(f"           expected: {o['expected']} | got: {o['got']}")
    else:
        print("   ✅ Жодного")

    # Scoring criteria
    print(f"\n📊 SCORING CRITERIA:")
    missed_urgent = [m for m in missed_danger if m["expected"] == "urgent"]
    missed_med = [m for m in missed_danger if m["expected"] == "urgent_medical_review"]
    print(f"   MISSED_DANGER total:    {len(missed_danger)} (urgent: {len(missed_urgent)}, urgent_med: {len(missed_med)})")
    print(f"   OVER_TRIAGE on traps:   {len(over_triage)}/8")

    if len(missed_danger) == 0:
        print(f"\n   🟢 READY FOR MODULE INTEGRATION")
    elif len(missed_danger) <= 2:
        print(f"\n   🟡 OK FOR PILOT (≤2 missed danger)")
    elif len(missed_danger) <= 5:
        print(f"\n   🟠 REVIEW PATTERNS BEFORE PILOT (3-5 missed danger)")
    else:
        print(f"\n   🔴 NOT READY — revoir architecture (>5 missed danger)")

    print()


if __name__ == "__main__":
    run()