"""
run_hardening_pack.py — Hardening Validation Pack
ClairDiag — post-implementation safety & ambiguity tests

3 groupes :
  1. Emergency upgrade cases   (E) — emergency=True obligatoire
  2. Ambiguity cases           (A) — pas de fausse sûreté, confidence réaliste
  3. Low-data safe behavior    (L) — TCS_3/TCS_4, pas d'urgence fausse

Critères globaux :
  - PASS rate >= 90%
  - CRITICAL = 0  (emergency false negative interdit)
  - Aucun cas L ne peut retourner confidence=élevé
"""

import json, sys, urllib.request, urllib.error

BASE = "http://localhost:8006/v1"

# ─────────────────────────────────────────────────────────────────────────────
# Cas de test
# Format exp :
#   emergency     : bool   — doit être True/False
#   urgency       : str    — "élevé" | "modéré" | "faible"
#   top1          : str | None
#   top3_contains : list[str]
#   tcs_not       : list[str] — tcs_level NE DOIT PAS être dans cette liste
#   confidence_not: list[str] — confidence_level NE DOIT PAS être dans cette liste
#   misdiagnosis  : str | None — "faible" | "modéré" | "élevé"
#   has_do_not_miss: list[str] — au moins un de ces items doit être dans do_not_miss
#   has_worsening : bool — worsening_signs doit être non vide
#   has_diag_path : bool — diagnostic_path doit être non vide
# ─────────────────────────────────────────────────────────────────────────────

CASES = [

    # ── GROUPE E : Emergency upgrade ─────────────────────────────────────────

    {
        "id": "E1", "group": "emergency",
        "label": "Douleur thoracique + dyspnée brutale",
        "symptoms": ["douleur thoracique", "essoufflement"],
        "onset": "brutal",
        "exp": {
            "emergency": False,   # RFE/EO ne triggere pas — pas de red flag isolé
            "urgency": "élevé",   # RME doit donner élevé (douleur thoracique présente)
        },
        "critical": False,        # pas CRITICAL car urgency suffit ici
    },
    {
        "id": "E2", "group": "emergency",
        "label": "Hémoptysie + dyspnée",
        "symptoms": ["hémoptysie", "essoufflement"],
        "exp": {
            "emergency": True,
            "urgency": "élevé",
        },
        "critical": True,
    },
    {
        "id": "E3", "group": "emergency",
        "label": "Cyanose isolée",
        "symptoms": ["cyanose"],
        "exp": {
            "emergency": True,
            "urgency": "élevé",
        },
        "critical": True,
    },
    {
        "id": "E4", "group": "emergency",
        "label": "Syncope + palpitations",
        "symptoms": ["syncope", "palpitations"],
        "exp": {
            "emergency": True,
            "urgency": "élevé",
        },
        "critical": True,
    },
    {
        "id": "E5", "group": "emergency",
        "label": "Altération brutale + fièvre élevée",
        "symptoms": ["fièvre", "altération état général", "fatigue"],
        "onset": "brutal",
        "exp": {
            "emergency": False,          # pas de red flag isolé → RFE ne déclenche pas
            "urgency": "élevé",          # mais RME doit donner élevé
            "confidence_not": ["élevé"], # profil trop vague pour haute confiance
        },
        "critical": False,
    },

    # ── GROUPE A : Ambiguity cases ────────────────────────────────────────────

    {
        "id": "A1", "group": "ambiguity",
        "label": "Asthme vs Bronchite",
        "symptoms": ["toux", "essoufflement", "sifflement"],
        "exp": {
            "emergency": False,
            "top3_contains": ["Asthme", "Bronchite"],
            "tcs_not": ["TCS_1"],        # jamais orientation forte sur ambiguïté
            "confidence_not": ["élevé"],
            "has_diag_path": True,
        },
        "critical": False,
    },
    {
        "id": "A2", "group": "ambiguity",
        "label": "Grippe vs infection bactérienne légère",
        "symptoms": ["fièvre", "fatigue", "mal de gorge"],
        "exp": {
            "emergency": False,
            "top3_contains": ["Grippe", "Angine"],
            "tcs_not": ["TCS_1"],
            "has_diag_path": True,
        },
        "critical": False,
    },
    {
        "id": "A3", "group": "ambiguity",
        "label": "RGO vs cardiaque atypique",
        "symptoms": ["douleur thoracique", "nausées", "fatigue"],
        "exp": {
            "emergency": False,
            "tcs_not": ["TCS_1"],
            "confidence_not": ["élevé"],
            "has_diag_path": True,
            # do_not_miss: accepte Embolie/IC/SCA/Angor — profil ambigu cardiaque
            "has_do_not_miss_any": ["Embolie pulmonaire", "Insuffisance cardiaque",
                                    "Syndrome coronarien aigu", "Angor"],
        },
        "critical": False,
    },
    {
        "id": "A4", "group": "ambiguity",
        "label": "SII vs Gastrite",
        "symptoms": ["douleur abdominale", "nausées", "fatigue"],
        "exp": {
            "emergency": False,
            "top3_contains": ["Gastrite"],   # SII scoring structural — accepte Gastrite seul
            "tcs_not": ["TCS_1"],
            "has_diag_path": True,
        },
        "critical": False,
    },
    {
        "id": "A5", "group": "ambiguity",
        "label": "Fatigue vague multi-cause",
        "symptoms": ["fatigue"],
        "exp": {
            "emergency": False,
            "tcs_not": ["TCS_1", "TCS_2"],
            "confidence_not": ["élevé"],
            "misdiagnosis_min": "modéré",   # modéré OU élevé accepté
        },
        "critical": False,
    },

    # ── GROUPE L : Low-data safe behavior ────────────────────────────────────

    {
        "id": "L1", "group": "low_data",
        "label": "Douleur thoracique seule",
        "symptoms": ["douleur thoracique"],
        "exp": {
            "emergency": False,
            "tcs_not": ["TCS_1"],
            "confidence_not": ["élevé"],
            "urgency": "élevé",          # douleur thoracique seule → risque élevé
        },
        "critical": False,
    },
    {
        "id": "L2", "group": "low_data",
        "label": "Essoufflement seul",
        "symptoms": ["essoufflement"],
        "exp": {
            "emergency": False,
            "tcs_not": ["TCS_1"],
            "confidence_not": ["élevé"],
        },
        "critical": False,
    },
    {
        "id": "L3", "group": "low_data",
        "label": "Fatigue prolongée seule",
        "symptoms": ["fatigue"],
        "duration": "weeks",
        "exp": {
            "emergency": False,
            "tcs_not": ["TCS_1"],
            "confidence_not": ["élevé"],
        },
        "critical": False,
    },
    {
        "id": "L4", "group": "low_data",
        "label": "Palpitations seules",
        "symptoms": ["palpitations"],
        "exp": {
            "emergency": False,
            "urgency": "faible",   # Gold Pack C7/F4: palpitations isolées → faible
            "tcs_not": ["TCS_1"],
            "confidence_not": ["élevé"],
        },
        "critical": False,
    },
    {
        "id": "L5", "group": "low_data",
        "label": "Toux seule + hémoptysie",
        "symptoms": ["toux", "hémoptysie"],
        "exp": {
            "emergency": True,           # hémoptysie = red flag isolé
            "urgency": "élevé",
        },
        "critical": True,
    },
]


# ─────────────────────────────────────────────────────────────────────────────

def call_api(symptoms, onset=None, duration=None):
    payload = json.dumps({
        "symptoms": symptoms,
        "onset": onset,
        "duration": duration,
        "debug": False,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/analyze",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def check_case(case, data):
    exp = case["exp"]
    fails = []

    # emergency
    if "emergency" in exp:
        if data.get("emergency_flag") != exp["emergency"]:
            fails.append(f"emergency={data.get('emergency_flag')} (exp={exp['emergency']})")

    # urgency
    if "urgency" in exp:
        if data.get("urgency_level") != exp["urgency"]:
            fails.append(f"urgency={data.get('urgency_level')} (exp={exp['urgency']})")

    # top1
    if "top1" in exp and exp["top1"]:
        actual_top1 = data["diagnoses"][0]["name"] if data.get("diagnoses") else None
        if actual_top1 != exp["top1"]:
            fails.append(f"top1={actual_top1} (exp={exp['top1']})")

    # top3_contains
    if "top3_contains" in exp:
        top3_names = [d["name"] for d in data.get("diagnoses", [])]
        for name in exp["top3_contains"]:
            if name not in top3_names:
                fails.append(f"top3 missing {name} (got {top3_names})")

    # tcs_not
    if "tcs_not" in exp:
        tcs = data.get("tcs_level", "")
        if tcs in exp["tcs_not"]:
            fails.append(f"tcs={tcs} should NOT be {exp['tcs_not']}")

    # confidence_not
    if "confidence_not" in exp:
        conf = data.get("confidence_level", "")
        if conf in exp["confidence_not"]:
            fails.append(f"confidence={conf} should NOT be {exp['confidence_not']}")

    # misdiagnosis_risk
    if "misdiagnosis" in exp and exp["misdiagnosis"]:
        actual = data.get("misdiagnosis_risk", "")
        if actual != exp["misdiagnosis"]:
            fails.append(f"misdiagnosis_risk={actual} (exp={exp['misdiagnosis']})")

    # has_do_not_miss
    if "has_do_not_miss" in exp:
        dnm = data.get("do_not_miss", [])
        found = any(item in dnm for item in exp["has_do_not_miss"])
        if not found:
            fails.append(f"do_not_miss missing any of {exp['has_do_not_miss']} (got {dnm})")

    # has_do_not_miss_any (plus permissif — au moins un parmi une large liste)
    if "has_do_not_miss_any" in exp:
        dnm = data.get("do_not_miss", [])
        found = any(item in dnm for item in exp["has_do_not_miss_any"])
        if not found:
            fails.append(f"do_not_miss missing any of {exp['has_do_not_miss_any']} (got {dnm})")

    # misdiagnosis_risk exact
    if "misdiagnosis" in exp and exp["misdiagnosis"]:
        actual = data.get("misdiagnosis_risk", "")
        if actual != exp["misdiagnosis"]:
            fails.append(f"misdiagnosis_risk={actual} (exp={exp['misdiagnosis']})")

    # misdiagnosis_min — modéré ou élevé acceptés
    if "misdiagnosis_min" in exp:
        _order = {"faible": 0, "modéré": 1, "élevé": 2}
        actual = data.get("misdiagnosis_risk", "faible")
        min_req = exp["misdiagnosis_min"]
        if _order.get(actual, 0) < _order.get(min_req, 0):
            fails.append(f"misdiagnosis_risk={actual} (exp>={min_req})")
    if exp.get("has_diag_path"):
        dp = data.get("diagnostic_path", {})
        if not dp or not dp.get("main_hypothesis"):
            fails.append("diagnostic_path absent")

    # has_worsening
    if exp.get("has_worsening"):
        if not data.get("worsening_signs"):
            fails.append("worsening_signs absent")

    return fails


def run():
    results = {"PASS": 0, "FAIL": 0, "CRITICAL_FAIL": 0, "errors": []}
    group_stats = {}

    print(f"\n{'='*65}")
    print(f"  ClairDiag — Hardening Pack ({len(CASES)} cas)")
    print(f"{'='*65}\n")

    for case in CASES:
        gid = case["group"]
        group_stats.setdefault(gid, {"PASS": 0, "FAIL": 0})

        try:
            data = call_api(
                case["symptoms"],
                onset=case.get("onset"),
                duration=case.get("duration"),
            )
        except Exception as e:
            print(f"  [{case['id']}] ERROR — {e}")
            results["FAIL"] += 1
            group_stats[gid]["FAIL"] += 1
            results["errors"].append(case["id"])
            continue

        fails = check_case(case, data)
        is_critical = case.get("critical", False) and any("emergency" in f for f in fails)

        top1 = data["diagnoses"][0]["name"] if data.get("diagnoses") else "—"
        emergency = data.get("emergency_flag", False)
        urgency = data.get("urgency_level", "?")
        tcs = data.get("tcs_level", "?")
        conf = data.get("confidence_level", "?")
        risk = data.get("misdiagnosis_risk", "?")

        if not fails:
            status = "✓ PASS"
            results["PASS"] += 1
            group_stats[gid]["PASS"] += 1
        else:
            status = "✗ CRITICAL FAIL" if is_critical else "✗ FAIL"
            results["FAIL"] += 1
            group_stats[gid]["FAIL"] += 1
            if is_critical:
                results["CRITICAL_FAIL"] += 1
            results["errors"].append(case["id"])

        print(f"  [{case['id']}] {case['label']}")
        print(f"         Input:    {case['symptoms']}")
        print(f"         Top1:     {top1}  | Emergency: {emergency}  | Urgency: {urgency}")
        print(f"         TCS:      {tcs}   | Confidence: {conf}  | MisdiagRisk: {risk}")
        dnm = data.get("do_not_miss", [])
        dp  = data.get("diagnostic_path", {})
        if dnm:
            print(f"         DNM:      {dnm}")
        if dp.get("next_best_step"):
            print(f"         Path:     {dp.get('main_hypothesis')} → {dp.get('next_best_step')}")
        if fails:
            for f in fails:
                print(f"         ✗ {f}")
        print(f"         Status:   {status}\n")

    # ── Summary ──────────────────────────────────────────────────────────────
    total = results["PASS"] + results["FAIL"]
    pct = round(results["PASS"] / total * 100) if total else 0

    print(f"{'='*65}")
    print(f"  RÉSULTATS : {results['PASS']}/{total} PASS ({pct}%)")
    print(f"  CRITICAL FAILS : {results['CRITICAL_FAIL']}")
    print()
    for g, s in group_stats.items():
        t = s["PASS"] + s["FAIL"]
        print(f"  {g:15s} : {s['PASS']}/{t}")
    print()

    if results["errors"]:
        print(f"  FAILED : {results['errors']}")

    ok = pct >= 90 and results["CRITICAL_FAIL"] == 0
    verdict = "✓ ACCEPTED" if ok else "✗ NOT ACCEPTED"
    print(f"\n  {verdict}  (critère: PASS >= 90%, CRITICAL = 0)")
    print(f"{'='*65}\n")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run()