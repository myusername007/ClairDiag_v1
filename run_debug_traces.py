#!/usr/bin/env python3
"""
ClairDiag — Debug Traces v2: cases 6,9,10,11,13,15,20
Запуск: python run_debug_traces.py
"""
import sys

try:
    from app.pipeline import run as pipeline_run
    from app.models.schemas import AnalyzeRequest
except ImportError as e:
    print(f"[ERROR] {e}\nЗапускай з кореня: python run_debug_traces.py")
    sys.exit(1)

G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[1m"; E="\033[0m"

DEBUG_CASES = [
    dict(id=6,  label="EMBOLIE",    syms=["essoufflement","douleur thoracique","palpitations"], onset="brutal",    duration="hours", exp_top1="Embolie pulmonaire", exp_urg="élevé"),
    dict(id=9,  label="IC CLAIRE",  syms=["essoufflement","œdèmes","fatigue"],                 onset="progressif",duration="weeks", exp_top1=None,                 exp_urg="modéré"),
    dict(id=10, label="IC NOCTURNE",syms=["essoufflement","fatigue","œdèmes"],                 onset=None,        duration=None,    exp_top1=None,                 exp_urg="modéré"),
    dict(id=11, label="RYTHME",     syms=["palpitations","fatigue"],                            onset=None,        duration=None,    exp_top1=None,                 exp_urg="modéré"),
    dict(id=13, label="RGO",        syms=["brûlure rétrosternale","reflux acide","après repas"],onset=None,        duration=None,    exp_top1="RGO",                exp_urg="faible"),
    dict(id=15, label="SII",        syms=["ballonnements","douleur chronique","fatigue"],        onset="progressif",duration="weeks", exp_top1="SII",                exp_urg="faible"),
    dict(id=20, label="FAIBLE DATA",syms=["fatigue"],                                           onset=None,        duration=None,    exp_top1=None,                 exp_urg="faible"),
]

def run_trace(c):
    req = AnalyzeRequest(
        symptoms=c["syms"],
        onset=c.get("onset"),
        duration=c.get("duration"),
        debug=True,
    )
    resp = pipeline_run(req)

    top1      = resp.diagnoses[0].name if resp.diagnoses else "—"
    top3      = [(d.name, round(d.probability, 2)) for d in resp.diagnoses]
    urg       = resp.urgency_level
    tcs       = resp.tcs_level
    conf      = resp.confidence_level
    emrg      = resp.emergency_flag
    tests_req = list(resp.tests.required) if resp.tests else []
    tests_opt = list(resp.tests.optional) if resp.tests else []
    warns     = list(resp.sgl_warnings) if resp.sgl_warnings else []

    bpu_probs = {}
    if resp.debug_trace and resp.debug_trace.bpu:
        bpu_probs = dict(resp.debug_trace.bpu.final_probs)

    passed = True
    fails = []
    if c["exp_top1"] and top1 != c["exp_top1"]:
        passed = False
        fails.append(f"top1={top1} (exp={c['exp_top1']})")
    if urg != c["exp_urg"]:
        passed = False
        fails.append(f"urgency={urg} (exp={c['exp_urg']})")

    return dict(
        id=c["id"], label=c["label"], passed=passed, fails=fails,
        top1=top1, top3=top3, urgency=urg, tcs=tcs, conf=conf,
        emergency=emrg, tests_req=tests_req, tests_opt=tests_opt,
        warnings=warns, bpu_probs=bpu_probs,
    )

def print_trace(r):
    status = f"{G}✓ PASS{E}" if r["passed"] else f"{R}✗ FAIL{E}"
    print(f"\n{'═'*60}")
    print(f"{B}Case {r['id']} — {r['label']}{E}  {status}")
    print(f"{'═'*60}")
    if r["fails"]:
        for f in r["fails"]:
            print(f"  {R}FAIL → {f}{E}")
    print(f"  {B}Top1:{E}        {r['top1']}")
    print(f"  {B}Top3:{E}        {r['top3']}")
    print(f"  {B}Urgence:{E}     {r['urgency']}")
    print(f"  {B}TCS:{E}         {r['tcs']}")
    print(f"  {B}Confidence:{E}  {r['conf']}")
    print(f"  {B}Emergency:{E}   {r['emergency']}")
    print(f"  {B}Tests req:{E}   {r['tests_req']}")
    print(f"  {B}Tests opt:{E}   {r['tests_opt']}")
    print(f"  {B}Warnings:{E}    {r['warnings']}")
    if r["bpu_probs"]:
        top5 = sorted(r["bpu_probs"].items(), key=lambda x: -x[1])[:5]
        print(f"  {B}BPU top5:{E}    {top5}")

def main():
    print(f"\n{B}═══ ClairDiag Debug Traces v2 — Clinical Fix Pack ═══{E}\n")
    results = []
    for c in DEBUG_CASES:
        try:
            r = run_trace(c)
        except Exception as ex:
            r = dict(
                id=c["id"], label=c["label"], passed=False, fails=[f"EXCEPTION: {ex}"],
                top1="—", top3=[], urgency="—", tcs="—", conf="—",
                emergency=False, tests_req=[], tests_opt=[], warnings=[], bpu_probs={},
            )
        results.append(r)
        print_trace(r)

    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'═'*60}")
    print(f"{B}ЗВЕДЕННЯ: {passed}/{len(results)} PASS{E}")
    print(f"{'═'*60}\n")

if __name__ == "__main__":
    main()