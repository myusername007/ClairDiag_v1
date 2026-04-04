#!/usr/bin/env python3
"""
ClairDiag — Validation Gold Pack 30 Cases
5 зон: respiratoire / cardiaque / digestif / infectieux / faible data
Критерии: top1 / top3 / urgency / tests / confidence / tcs / emergency
"""
import sys

try:
    from app.pipeline import run as pipeline_run
    from app.models.schemas import AnalyzeRequest
    from app.data.tests import DIAGNOSIS_TESTS
except ImportError as e:
    print(f"[ERROR] {e}\nЗапускай з кореня: python run_gold_30.py")
    sys.exit(1)

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[1m"; E = "\033[0m"

def allowed(*diags):
    s = set()
    for d in diags:
        e = DIAGNOSIS_TESTS.get(d, {})
        s |= set(e.get("required", [])) | set(e.get("optional", []))
    return s

TCS_ORDER  = {"incertain": 0, "besoin_tests": 1, "fort": 2}
CONF_ORDER = {"faible": 0, "modéré": 1, "élevé": 2}
SEV_ORDER  = ["MINOR", "MAJOR", "CRITICAL"]

# ─────────────────────────────────────────────
# 30 КЕЙСОВ — input_text → симптомы вручную
# expected_urgency: faible / modéré / élevé (french, как в pipeline)
# ─────────────────────────────────────────────
CASES = [
    # ── RESPIRATOIRE (R1–R8) ──
    dict(id="R1", zone="respiratoire",
         label="ASTHME NOCTURNE",
         syms=["essoufflement", "sifflement"],
         onset="progressif", duration="days",
         exp_top1="Asthme",
         exp_top3=["Asthme", "Bronchite"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Asthme", "Bronchite")),

    dict(id="R2", zone="respiratoire",
         label="ASTHME EFFORT",
         syms=["toux", "essoufflement", "sifflement"],
         onset=None, duration=None,
         exp_top1="Asthme",
         exp_top3=["Asthme", "Bronchite"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Asthme", "Bronchite")),

    dict(id="R3", zone="respiratoire",
         label="BRONCHITE",
         syms=["toux", "fatigue", "fièvre"],
         onset=None, duration=None,
         exp_top1=None,           # toux+fatigue+fièvre → Grippe ou Bronchite également valides
         exp_top3=["Bronchite", "Grippe"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Bronchite", "Grippe")),

    dict(id="R4", zone="respiratoire",
         label="PNEUMONIE",
         syms=["fièvre", "toux", "douleur thoracique", "fatigue"],
         onset=None, duration=None,
         exp_top1="Pneumonie",
         exp_top3=["Pneumonie"],
         exp_urg="élevé", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Pneumonie")),

    dict(id="R5", zone="respiratoire",
         label="EMBOLIE",
         syms=["essoufflement", "douleur thoracique", "palpitations"],
         onset="brutal", duration="hours",
         exp_top1="Embolie pulmonaire",
         exp_top3=["Embolie pulmonaire"],
         exp_urg="élevé", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Embolie pulmonaire", "Angor", "Pneumonie")),

    dict(id="R6", zone="respiratoire",
         label="CYANOSE EMERGENCY",
         syms=["essoufflement", "cyanose"],
         onset=None, duration=None,
         exp_top1=None,
         exp_top3=[],
         exp_urg="élevé", exp_tcs=None, exp_emrg=True,
         ok_tests=set()),

    dict(id="R7", zone="respiratoire",
         label="HÉMOPTYSIE EMERGENCY",
         syms=["essoufflement", "hémoptysie"],
         onset=None, duration=None,
         exp_top1=None,
         exp_top3=[],
         exp_urg="élevé", exp_tcs=None, exp_emrg=True,
         ok_tests=set()),

    dict(id="R8", zone="respiratoire",
         label="ASTHME FIÈVRE",
         syms=["sifflement", "essoufflement", "fièvre", "toux"],
         onset=None, duration=None,
         exp_top1="Asthme",
         exp_top3=["Asthme"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Asthme", "Bronchite", "Pneumonie")),

    # ── CARDIAQUE (C1–C7) ──
    dict(id="C1", zone="cardiaque",
         label="IC CLASSIQUE",
         syms=["essoufflement", "œdèmes", "fatigue"],
         onset="progressif", duration="weeks",
         exp_top1="Insuffisance cardiaque",
         exp_top3=["Insuffisance cardiaque"],
         exp_urg="modéré", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Insuffisance cardiaque", "Anémie", "Angor")),

    dict(id="C2", zone="cardiaque",
         label="IC NOCTURNE",
         syms=["essoufflement", "fatigue", "œdèmes"],
         onset=None, duration=None,
         exp_top1="Insuffisance cardiaque",
         exp_top3=["Insuffisance cardiaque"],
         exp_urg="modéré", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Insuffisance cardiaque", "Angor")),

    dict(id="C3", zone="cardiaque",
         label="TROUBLE RYTHME",
         syms=["palpitations", "malaise", "fatigue"],
         onset=None, duration=None,
         exp_top1="Trouble du rythme",
         exp_top3=["Trouble du rythme"],
         exp_urg="modéré", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Trouble du rythme", "Anémie", "Hypertension")),

    dict(id="C4", zone="cardiaque",
         label="SYNCOPE EMERGENCY",
         syms=["palpitations", "syncope"],
         onset=None, duration=None,
         exp_top1=None,
         exp_top3=[],
         exp_urg="élevé", exp_tcs=None, exp_emrg=True,
         ok_tests=set()),

    dict(id="C5", zone="cardiaque",
         label="ANGOR TYPIQUE",
         syms=["douleur thoracique", "essoufflement", "fatigue"],
         onset="brutal", duration="hours",
         exp_top1="Angor",
         exp_top3=["Angor"],
         exp_urg="élevé", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Angor")),

    dict(id="C6", zone="cardiaque",
         label="IC OEDEMES",
         syms=["essoufflement", "œdèmes", "fatigue"],
         onset=None, duration=None,
         exp_top1="Insuffisance cardiaque",
         exp_top3=["Insuffisance cardiaque"],
         exp_urg="modéré", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Insuffisance cardiaque", "Angor")),

    dict(id="C7", zone="cardiaque",
         label="PALPITATIONS ISOLÉES",
         syms=["palpitations"],
         onset=None, duration=None,
         exp_top1="Trouble du rythme",
         exp_top3=["Trouble du rythme"],
         exp_urg="faible", exp_tcs="incertain", exp_emrg=False,
         ok_tests=allowed("Trouble du rythme")),

    # ── DIGESTIF (D1–D6) ──
    dict(id="D1", zone="digestif",
         label="RGO TYPIQUE",
         syms=["brûlure rétrosternale", "reflux acide", "après repas"],
         onset=None, duration=None,
         exp_top1="RGO",
         exp_top3=["RGO"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("RGO", "Gastrite")),

    dict(id="D2", zone="digestif",
         label="RGO RÉGURGITATIONS",
         syms=["reflux acide", "brûlure rétrosternale", "après repas"],
         onset=None, duration=None,
         exp_top1="RGO",
         exp_top3=["RGO"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("RGO", "Gastrite")),

    dict(id="D3", zone="digestif",
         label="GASTRITE",
         syms=["nausées", "douleur épigastrique"],
         onset=None, duration=None,
         exp_top1="Gastrite",
         exp_top3=["Gastrite"],
         exp_urg="faible", exp_tcs="incertain", exp_emrg=False,
         ok_tests=allowed("Gastrite")),

    dict(id="D4", zone="digestif",
         label="GASTRITE AIGUË",
         syms=["nausées", "douleur épigastrique", "brûlure gastrique"],
         onset=None, duration=None,
         exp_top1="Gastrite",
         exp_top3=["Gastrite"],
         exp_urg="faible", exp_tcs="incertain", exp_emrg=False,
         ok_tests=allowed("Gastrite")),

    dict(id="D5", zone="digestif",
         label="SII CHRONIQUE",
         syms=["ballonnements", "douleur chronique"],
         onset="progressif", duration="weeks",
         exp_top1="SII",
         exp_top3=["SII"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("SII", "Gastrite")),

    dict(id="D6", zone="digestif",
         label="SII TRANSIT",
         syms=["ballonnements", "douleur chronique"],
         onset=None, duration=None,
         exp_top1="SII",
         exp_top3=["SII"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("SII", "Gastrite")),

    # ── INFECTIEUX (I1–I5) ──
    dict(id="I1", zone="infectieux",
         label="VIRAL FAIBLE",
         syms=["fatigue", "fièvre", "courbatures"],
         onset=None, duration=None,
         exp_top1=None,           # слабые данные — любой вирусный приемлем
         exp_top3=["Grippe"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Grippe")),

    dict(id="I2", zone="infectieux",
         label="GRIPPE TYPIQUE",
         syms=["fièvre", "courbatures", "fatigue"],
         onset="brutal", duration="days",
         exp_top1="Grippe",
         exp_top3=["Grippe"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Grippe")),

    dict(id="I3", zone="infectieux",
         label="COVID-LIKE",
         syms=["fièvre", "toux", "fatigue"],
         onset="progressif", duration="days",
         exp_top1=None,           # слабые данные
         exp_top3=["Grippe"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Grippe", "Bronchite")),

    dict(id="I4", zone="infectieux",
         label="BACTÉRIEN FAIBLE",
         syms=["fièvre", "fatigue"],
         onset=None, duration=None,
         exp_top1=None,           # слабые данные
         exp_top3=["Grippe"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Grippe", "Angine")),

    dict(id="I5", zone="infectieux",
         label="GRIPPE FRISSONS",
         syms=["fièvre", "courbatures", "fatigue", "frissons"],
         onset="brutal", duration="days",
         exp_top1="Grippe",
         exp_top3=["Grippe"],
         exp_urg="faible", exp_tcs="besoin_tests", exp_emrg=False,
         ok_tests=allowed("Grippe")),

    # ── FAIBLE DATA / SAFETY (F1–F4) ──
    dict(id="F1", zone="faible_data",
         label="FATIGUE SEULE",
         syms=["fatigue"],
         onset=None, duration=None,
         exp_top1=None,
         exp_top3=[],
         exp_urg="faible", exp_tcs="incertain", exp_emrg=False,
         ok_tests=set()),

    dict(id="F2", zone="faible_data",
         label="DOULEUR VAGUE",
         syms=["douleur"],
         onset=None, duration=None,
         exp_top1=None,
         exp_top3=[],
         exp_urg="faible", exp_tcs="incertain", exp_emrg=False,
         ok_tests=set()),

    dict(id="F3", zone="faible_data",
         label="TOUX SEULE",
         syms=["toux"],
         onset=None, duration=None,
         exp_top1=None,
         exp_top3=[],
         exp_urg="faible", exp_tcs="incertain", exp_emrg=False,
         ok_tests=allowed("Bronchite", "Grippe")),

    dict(id="F4", zone="faible_data",
         label="PALPITATIONS SEULES",
         syms=["palpitations"],
         onset=None, duration=None,
         exp_top1="Trouble du rythme",
         exp_top3=["Trouble du rythme"],
         exp_urg="faible", exp_tcs="incertain", exp_emrg=False,
         ok_tests=allowed("Trouble du rythme")),
]

# ─────────────────────────────────────────────
DEBUG_TRACES = {"R5", "C1", "C3", "D1", "D5", "I2", "F1"}
# ─────────────────────────────────────────────

def run_case(c):
    try:
        req  = AnalyzeRequest(symptoms=c["syms"], onset=c.get("onset"), duration=c.get("duration"))
        resp = pipeline_run(req)
    except Exception as ex:
        return dict(id=c["id"], zone=c["zone"], label=c["label"], passed=False,
                    fails={"exception": str(ex)[:100]}, severities=["CRITICAL"], actual={})

    top1  = resp.diagnoses[0].name if resp.diagnoses else None
    top3n = [d.name for d in resp.diagnoses[:3]]
    top3  = [(d.name, round(d.probability, 2)) for d in resp.diagnoses[:3]]
    urg   = resp.urgency_level
    tcs   = resp.tcs_level
    conf  = resp.confidence_level
    emrg  = resp.emergency_flag
    tests = list(resp.tests.required) if resp.tests else []
    warns = list(resp.sgl_warnings) if resp.sgl_warnings else []
    n     = len(c["syms"])

    fails = {}; sevs = []

    # 1. Top1 (только если задан)
    if c["exp_top1"] and top1 != c["exp_top1"]:
        fails["top1"] = f"{top1} (exp={c['exp_top1']})"
        sevs.append("MAJOR")

    # 2. Top3 must contain
    for exp in c["exp_top3"]:
        if exp not in top3n:
            fails["top3"] = f"{exp} не в top3={top3n}"
            sevs.append("MAJOR")
            break

    # 3. Urgence
    if urg != c["exp_urg"]:
        is_critical = c["exp_urg"] == "élevé" and urg == "faible"
        fails["urgency"] = f"{urg} (exp={c['exp_urg']})"
        sevs.append("CRITICAL" if is_critical else "MAJOR")

    # 4. Emergency flag
    if emrg != c["exp_emrg"]:
        fails["emergency"] = f"{emrg} (exp={c['exp_emrg']})"
        sevs.append("CRITICAL")

    # 5. TCS (только если задан)
    if c["exp_tcs"] and tcs != c["exp_tcs"]:
        fails["tcs"] = f"{tcs} (exp={c['exp_tcs']})"
        sevs.append("MINOR")

    # 6. Tests — зайні (только если не emergency)
    if not emrg and c["ok_tests"]:
        extra = [t for t in tests if t not in c["ok_tests"]]
        if extra:
            fails["tests"] = f"зайні={extra}"
            sevs.append("MAJOR")

    # 7. Confidence cap при 1 симптомі
    if n == 1 and CONF_ORDER.get(conf, 0) >= CONF_ORDER["élevé"]:
        fails["confidence"] = f"{conf} при 1 симптомі"
        sevs.append("MAJOR")

    return dict(id=c["id"], zone=c["zone"], label=c["label"],
                passed=len(fails) == 0,
                fails=fails, severities=sevs,
                actual=dict(top1=top1, top3=top3, urgency=urg, tcs=tcs,
                            conf=conf, emergency=emrg, tests=tests, warnings=warns))


def topsev(sevs):
    return max(sevs, key=lambda s: SEV_ORDER.index(s)) if sevs else "—"


def fixtype(fails):
    if "emergency" in fails: return "safety(SGL/RFE)"
    if "urgency"   in fails: return "rule(RME)"
    if "top1"      in fails: return "weight(BPU)"
    if "top3"      in fails: return "weight(BPU)"
    if "tests"     in fails: return "filter(LME)"
    if "tcs"       in fails: return "threshold(TCS)"
    if "confidence" in fails: return "threshold(SGL)"
    return "—"


def print_debug(case_id, c, r):
    a = r["actual"]
    print(f"\n{'─'*55}")
    print(f"{B}DEBUG TRACE — {case_id} ({c['label']}){E}")
    print(f"  Input:      {c['syms']}")
    print(f"  Onset:      {c.get('onset')}  Duration: {c.get('duration')}")
    print(f"  Top1:       {a.get('top1')}")
    print(f"  Top3:       {a.get('top3')}")
    print(f"  Urgence:    {a.get('urgency')}  (exp={c['exp_urg']})")
    print(f"  TCS:        {a.get('tcs')}  (exp={c['exp_tcs']})")
    print(f"  Confidence: {a.get('conf')}")
    print(f"  Emergency:  {a.get('emergency')}  (exp={c['exp_emrg']})")
    print(f"  Tests:      {a.get('tests')}")
    print(f"  Warnings:   {a.get('warnings')}")
    status = f"{G}PASS{E}" if r["passed"] else f"{R}FAIL — {list(r['fails'].keys())}{E}"
    print(f"  Status:     {status}")


def main():
    print(f"\n{B}══════════════════════════════════════════════════════{E}")
    print(f"{B}   ClairDiag — Validation Gold Pack 30 Cases          {E}")
    print(f"{B}══════════════════════════════════════════════════════{E}\n")

    results = {}
    zones = ["respiratoire", "cardiaque", "digestif", "infectieux", "faible_data"]

    for zone in zones:
        zone_cases = [c for c in CASES if c["zone"] == zone]
        print(f"{B}── {zone.upper()} ──{E}")
        for c in zone_cases:
            r = run_case(c)
            results[c["id"]] = (c, r)
            st = f"{G}✓ PASS{E}" if r["passed"] else f"{R}✗ FAIL{E}"
            sv = f" [{topsev(r['severities'])}]" if not r["passed"] else ""
            print(f"  {st} [{c['id']}] {c['label']}{sv}")
            if not r["passed"]:
                for k, v in r["fails"].items():
                    print(f"         → {k}: {v}")
        print()

    # ── DEBUG TRACES ──
    print(f"\n{B}══════ DEBUG TRACES ══════{E}")
    for cid in DEBUG_TRACES:
        if cid in results:
            c, r = results[cid]
            print_debug(cid, c, r)

    # ── ТАБЛИЦЯ ──
    print(f"\n\n{B}══════════════════════════════════════════════════════{E}")
    print(f"{B}   ПІДСУМКОВА ТАБЛИЦЯ{E}")
    print(f"{B}══════════════════════════════════════════════════════{E}")
    print(f"  {'Case':<5} {'Zone':<14} {'Expected':<24} {'Actual':<24} {'Status':<6} {'Sev':<10} Fix")
    print(f"  {'─'*5} {'─'*14} {'─'*24} {'─'*24} {'─'*6} {'─'*10} {'─'*16}")

    for cid in [c["id"] for c in CASES]:
        c, r = results[cid]
        a = r["actual"]
        exp_s = c["exp_top1"] or "—"
        act_s = (a.get("top1") or "—")
        pf    = f"{G}PASS{E}" if r["passed"] else f"{R}FAIL{E}"
        sv    = topsev(r["severities"])
        fx    = fixtype(r["fails"])
        print(f"  {cid:<5} {c['zone']:<14} {exp_s:<24} {act_s:<24} {pf:<15} {sv:<10} {fx}")

    # ── ЗВЕДЕННЯ ──
    all_results = [r for _, r in results.values()]
    pn = sum(1 for r in all_results if r["passed"])
    fn = len(all_results) - pn
    cr = sum(1 for r in all_results for s in r["severities"] if s == "CRITICAL")
    ma = sum(1 for r in all_results for s in r["severities"] if s == "MAJOR")
    mi = sum(1 for r in all_results for s in r["severities"] if s == "MINOR")

    top3_fails = sum(1 for r in all_results if "top3" in r["fails"])
    top3_pass  = len(all_results) - top3_fails

    print(f"\n{B}══════ ЗВЕДЕННЯ ══════{E}")
    print(f"  TOTAL:     {len(all_results)}")
    print(f"  {G}PASS:      {pn}  ({pn/len(all_results)*100:.0f}%){E}")
    print(f"  {R}FAIL:      {fn}{E}")
    print(f"  CRITICAL:  {cr}")
    print(f"  MAJOR:     {ma}")
    print(f"  MINOR:     {mi}")
    print(f"  Top3 pass: {top3_pass}/{len(all_results)}  ({top3_pass/len(all_results)*100:.0f}%)")

    # ── Зони ──
    print(f"\n{B}── По зонам ──{E}")
    for zone in zones:
        zr = [r for cid, (c, r) in results.items() if c["zone"] == zone]
        zp = sum(1 for r in zr if r["passed"])
        print(f"  {zone:<16} {zp}/{len(zr)}")

    # ── Критерій прийняття ──
    print(f"\n{B}── Критерій прийняття ──{E}")
    ok_critical  = cr == 0
    ok_pass_rate = pn / len(all_results) >= 0.90
    ok_top3      = top3_pass / len(all_results) >= 0.95

    print(f"  CRITICAL = 0       {'✓' if ok_critical  else '✗'}  (actual={cr})")
    print(f"  PASS ≥ 90%         {'✓' if ok_pass_rate else '✗'}  (actual={pn/len(all_results)*100:.0f}%)")
    print(f"  Top3 ≥ 95%         {'✓' if ok_top3      else '✗'}  (actual={top3_pass/len(all_results)*100:.0f}%)")

    all_ok = ok_critical and ok_pass_rate and ok_top3
    verdict = f"{G}✓ GOLD PACK ACCEPTED{E}" if all_ok else f"{R}✗ GOLD PACK FAILED — потрібні фікси{E}"
    print(f"\n  {verdict}\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()