#!/usr/bin/env python3
"""
ClairDiag — Clinical Validation 20 Cases (Sprint Final)
6 критеріїв ТЗ: top1 / urgency / tests / confidence / tcs / red_flags
+ severity + таблиця + TOP FIXES
"""
import sys

try:
    from app.pipeline import run as pipeline_run
    from app.models.schemas import AnalyzeRequest
    from app.data.tests import DIAGNOSIS_TESTS
except ImportError as e:
    print(f"[ERROR] {e}\nЗапускай з кореня: python run_clinical_20.py")
    sys.exit(1)

G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[1m"; E="\033[0m"

def allowed(*diags):
    s = set()
    for d in diags:
        e = DIAGNOSIS_TESTS.get(d, {})
        s |= set(e.get("required",[])) | set(e.get("optional",[]))
    return s

TCS_ORDER  = {"incertain":0,"besoin_tests":1,"fort":2}
CONF_ORDER = {"faible":0,"modéré":1,"élevé":2}
SEV_ORDER  = ["MINOR","MAJOR","CRITICAL"]

CASES = [
    dict(id=1,  label="ASTHME CLAIR",     syms=["essoufflement","sifflement"],                        onset="progressif",duration="days",  exp_top1="Asthme",    exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Asthme","Bronchite")),
    dict(id=2,  label="ASTHME FAIBLE",    syms=["toux","essoufflement","sifflement"],                 onset=None,        duration=None,     exp_top1="Asthme",    exp_urg="faible", exp_tcs_max="fort",        exp_emrg=False,ok_tests=allowed("Asthme","Bronchite","Pneumonie")),
    dict(id=3,  label="BRONCHITE",        syms=["toux","fatigue","fièvre"],                           onset=None,        duration=None,     exp_top1=None,        exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Bronchite","Grippe")),
    dict(id=4,  label="PNEUMONIE",        syms=["fièvre","toux","douleur thoracique","fatigue"],      onset=None,        duration=None,     exp_top1="Pneumonie", exp_urg="élevé",  exp_tcs_max="fort",        exp_emrg=False,ok_tests=allowed("Pneumonie")),
    dict(id=5,  label="PNEUMONIE FAIBLE", syms=["toux","fatigue","fièvre"],                           onset=None,        duration=None,     exp_top1=None,        exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Pneumonie","Grippe")),
    dict(id=6,  label="EMBOLIE",          syms=["essoufflement","douleur thoracique","palpitations"], onset="brutal",    duration="hours",  exp_top1="Angor",     exp_urg="élevé",  exp_tcs_max="fort",        exp_emrg=False,ok_tests=allowed("Angor","Pneumonie","Bronchite")),
    dict(id=7,  label="CYANOSE",          syms=["essoufflement","cyanose"],                           onset=None,        duration=None,     exp_top1=None,        exp_urg="élevé",  exp_tcs_max="fort",        exp_emrg=True, ok_tests=set()),
    dict(id=8,  label="HÉMOPTYSIE",       syms=["essoufflement","hémoptysie"],                       onset=None,        duration=None,     exp_top1=None,        exp_urg="élevé",  exp_tcs_max="fort",        exp_emrg=True, ok_tests=set()),
    dict(id=9,  label="IC CLAIRE",        syms=["essoufflement","œdèmes","fatigue"],                 onset="progressif",duration="weeks",  exp_top1=None,        exp_urg="modéré", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Asthme","Anémie","Angor")),
    dict(id=10, label="IC NOCTURNE",      syms=["essoufflement","fatigue","œdèmes"],                 onset=None,        duration=None,     exp_top1=None,        exp_urg="modéré", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Asthme","Angor")),
    dict(id=11, label="RYTHME",           syms=["palpitations","fatigue"],                            onset=None,        duration=None,     exp_top1=None,        exp_urg="modéré", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Hypertension","Anémie","Angor")),
    dict(id=12, label="SYNCOPE",          syms=["palpitations","syncope"],                            onset=None,        duration=None,     exp_top1=None,        exp_urg="élevé",  exp_tcs_max="fort",        exp_emrg=True, ok_tests=set()),
    dict(id=13, label="RGO",              syms=["douleur thoracique","nausées"],                      onset=None,        duration=None,     exp_top1=None,        exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Gastrite","Angor")),
    dict(id=14, label="GASTRITE",         syms=["nausées"],                                           onset=None,        duration=None,     exp_top1="Gastrite",  exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Gastrite")),
    dict(id=15, label="SII",              syms=["nausées"],                                           onset=None,        duration=None,     exp_top1="Gastrite",  exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Gastrite")),
    dict(id=16, label="VIRAL",            syms=["fatigue","fièvre","courbatures"],                    onset=None,        duration=None,     exp_top1="Grippe",    exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Grippe")),
    dict(id=17, label="GRIPPE",           syms=["fièvre","courbatures","fatigue"],                    onset="brutal",    duration=None,     exp_top1="Grippe",    exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Grippe")),
    dict(id=18, label="COVID-LIKE",       syms=["fièvre","toux","fatigue"],                           onset=None,        duration="days",   exp_top1="Grippe",    exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Grippe","Bronchite")),
    dict(id=19, label="BACTÉRIEN",        syms=["fièvre","fatigue"],                                  onset=None,        duration=None,     exp_top1="Grippe",    exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=allowed("Grippe","Angine")),
    dict(id=20, label="FAIBLE DATA",      syms=["fatigue"],                                           onset=None,        duration=None,     exp_top1=None,        exp_urg="faible", exp_tcs_max="besoin_tests",exp_emrg=False,ok_tests=set()),
]

def run_case(c):
    try:
        req  = AnalyzeRequest(symptoms=c["syms"], onset=c.get("onset"), duration=c.get("duration"))
        resp = pipeline_run(req)
    except Exception as ex:
        return dict(id=c["id"],label=c["label"],passed=False,
                    fails={"exception":str(ex)[:80]},severities=["CRITICAL"],actual={})

    top1  = resp.diagnoses[0].name if resp.diagnoses else None
    top3  = [(d.name,round(d.probability,2)) for d in resp.diagnoses]
    urg   = resp.urgency_level
    tcs   = resp.tcs_level
    conf  = resp.confidence_level
    emrg  = resp.emergency_flag
    tests = list(resp.tests.required) if resp.tests else []
    warns = list(resp.sgl_warnings)   if resp.sgl_warnings else []
    n     = len(c["syms"])

    fails={}; sevs=[]

    # 1. Top1
    if c["exp_top1"] and top1 != c["exp_top1"]:
        fails["top1"] = f"{top1} (exp={c['exp_top1']})"
        sevs.append("MAJOR")

    # 2. Urgence
    if urg != c["exp_urg"]:
        fails["urgency"] = f"{urg} (exp={c['exp_urg']})"
        sevs.append("CRITICAL" if c["exp_urg"]=="élevé" and urg=="faible" else "MAJOR")

    # 3. Tests — зайві аналізи
    if not emrg and c["ok_tests"]:
        extra = [t for t in tests if t not in c["ok_tests"]]
        if extra:
            fails["tests"] = f"зайві={extra}"
            sevs.append("MAJOR")

    # 4. Confidence cap при ≤2 симптомах
    if n <= 2 and CONF_ORDER.get(conf,0) >= CONF_ORDER["élevé"]:
        fails["confidence"] = f"{conf} при {n} симптомах (max=modéré)"
        sevs.append("MAJOR")

    # 5. TCS — не вище дозволеного
    if TCS_ORDER.get(tcs,0) > TCS_ORDER.get(c["exp_tcs_max"],2):
        fails["tcs"] = f"{tcs} (max={c['exp_tcs_max']})"
        sevs.append("MAJOR")

    # 6. Red flag / emergency
    if emrg != c["exp_emrg"]:
        fails["red_flag"] = f"emergency={emrg} (exp={c['exp_emrg']})"
        sevs.append("CRITICAL")

    return dict(id=c["id"],label=c["label"],passed=len(fails)==0,
                fails=fails,severities=sevs,
                actual=dict(top1=top1,top3=top3,urgency=urg,tcs=tcs,
                            conf=conf,emergency=emrg,tests=tests,warnings=warns))

def topsev(sevs): return max(sevs,key=lambda s:SEV_ORDER.index(s)) if sevs else "—"

def fixtype(fails):
    if "red_flag"   in fails: return "safety"
    if "urgency"    in fails: return "rule(RME)"
    if "top1"       in fails: return "weight"
    if "tests"      in fails: return "LME"
    if "confidence" in fails: return "threshold"
    if "tcs"        in fails: return "threshold"
    return "—"

def main():
    print(f"\n{B}═══ ClairDiag Clinical Validation — Sprint Final ═══{E}\n")
    results=[]
    for c in CASES:
        r=run_case(c); results.append(r)
        st=f"{G}✓ PASS{E}" if r["passed"] else f"{R}✗ FAIL{E}"
        sv=f" [{topsev(r['severities'])}]" if not r["passed"] else ""
        print(f"  {st} [{r['id']:2d}] {r['label']}{sv}")
        if not r["passed"]:
            for k,v in r["fails"].items(): print(f"         → {k}: {v}")

    fails_only=[r for r in results if not r["passed"]]
    if fails_only:
        print(f"\n{B}═══ ДЕТАЛІ ПОМИЛОК ═══{E}\n")
        for r in fails_only:
            a=r["actual"]
            print(f"Case {r['id']} — {r['label']}")
            print(f"  Top1:       {a.get('top1')}")
            print(f"  Top3:       {a.get('top3')}")
            print(f"  Urgence:    {a.get('urgency')}")
            print(f"  Tests:      {a.get('tests')}")
            print(f"  Confidence: {a.get('conf')}")
            print(f"  TCS:        {a.get('tcs')}")
            print(f"  Warning(s): {a.get('warnings')}")
            print(f"  Severity:   {topsev(r['severities'])}")
            print(f"  Fails:      {list(r['fails'].keys())}")
            print()

    # Таблиця
    print(f"\n{B}═══ ПІДСУМКОВА ТАБЛИЦЯ ═══{E}\n")
    print(f"  {'Case':<5}{'Label':<18}{'P/F':<6}{'Sev':<10}{'Main issue':<33}Fix")
    print(f"  {'─'*5}{'─'*18}{'─'*6}{'─'*10}{'─'*33}{'─'*12}")
    for r in results:
        pf  = f"{G}PASS{E}" if r["passed"] else f"{R}FAIL{E}"
        sv  = topsev(r["severities"])
        iss = (list(r["fails"].keys())[0]+": "+list(r["fails"].values())[0])[:32] if r["fails"] else "—"
        fx  = fixtype(r["fails"])
        print(f"  {r['id']:<5}{r['label']:<18}{pf:<15}{sv:<10}{iss:<33}{fx}")

    # Зведення
    pn=sum(1 for r in results if r["passed"]); fn=len(results)-pn
    cr=sum(1 for r in results for s in r["severities"] if s=="CRITICAL")
    ma=sum(1 for r in results for s in r["severities"] if s=="MAJOR")
    mi=sum(1 for r in results for s in r["severities"] if s=="MINOR")
    print(f"\n{B}═══ ЗВЕДЕННЯ ═══{E}")
    print(f"  TOTAL:    {len(results)}")
    print(f"  {G}PASS:     {pn}{E}")
    print(f"  {R}FAIL:     {fn}{E}")
    print(f"  CRITICAL: {cr}")
    print(f"  MAJOR:    {ma}")
    print(f"  MINOR:    {mi}")
    print(f"  Rate:     {pn/len(results)*100:.0f}%")

    has=lambda k: any(k in r["fails"] for r in results)
    fixes=[]
    if cr:            fixes.append("[CRITICAL] Urgence/emergency пропущені — перевірити RME+RFE")
    if has("top1"):   fixes.append("[MAJOR] BPU weights — хибні top1")
    if has("tests"):  fixes.append("[MAJOR] LME — зайві аналізи поза клінічно виправданими")
    if has("tcs"):    fixes.append("[MAJOR] TCS — fort при слабких даних")
    if has("confidence"): fixes.append("[MAJOR] SGL — confidence élevé при ≤2 симптомах")
    if not fixes:     fixes.append("Всі 6 критеріїв виконані — патч не потрібен")

    print(f"\n{B}TOP FIXES FOR NEXT PATCH:{E}")
    for i,f in enumerate(fixes[:5],1): print(f"  {i}. {f}")
    print()
    sys.exit(0 if fn==0 else 1)

if __name__=="__main__":
    main()