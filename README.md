# ClairDiag v2.3 — Absolute Mode (LOCKED)
## AI Clinical Decision System (Explainable, Auditable, Safe)

---

## What it is

ClairDiag is a deterministic clinical reasoning engine designed to:
- reduce unnecessary medical tests
- improve diagnostic orientation
- provide explainable, auditable decision paths
- detect emergencies and flag high-risk profiles

## What it is NOT

- **not** a diagnostic tool
- **not** a medical decision system
- **not** a replacement for physician judgment
- **requires** physician validation before any clinical action

---

## Why it matters

- 20–40% of medical tests are unnecessary *(OECD data)*
- Diagnostic delays cost billions annually across healthcare systems
- ClairDiag reduces cost while increasing clarity and traceability
- Every decision is explainable, reproducible and auditable — no black box

---

## Live

https://clairdiagv1-production.up.railway.app/

**Version:** `ClairDiag v2.3 — Absolute Mode (LOCKED)`
**Build hash:** `8ea6d8f3e436`
**Core status:** `LOCKED`

---

## What it does

- Understands **any French text**: conversational, argot, typos (`mal au ventre`, `je suis KO`, `barbouillé`)
- Returns up to 3 probable diagnoses with weighted probability
- Recommends tests by diagnostic value / cost ratio
- Calculates savings vs standard diagnostic path in €
- Generates clinical reasoning, diagnostic tree, scenarios
- Expert Mode — full logic breakdown for physician / investor
- Detects red flags → emergency alert
- Voice input via Web Speech API (Chrome/Edge, HTTPS required)
- Context detection: after_meal, post-antibiotics, chronology, aggravation_time

---

## Demo

```json
{
  "input": ["fièvre", "toux", "essoufflement", "fatigue"],
  "onset": "brutal",
  "expected_output": {
    "top1": "Pneumonie",
    "decision": "URGENT_MEDICAL_REVIEW",
    "quality_gate": true
  }
}
```

```bash
curl -X POST https://clairdiagv1-production.up.railway.app/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"symptoms": ["fièvre", "toux", "essoufflement", "fatigue"], "onset": "brutal"}'
```

Full demo case with verify checks: [`demo.json`](./demo.json)

---

## Startup

### Docker (recommended)

```bash
git clone https://github.com/myusername007/ClairDiag_v1.git
cd ClairDiag_v1
docker build -t clairdiag .
docker run -p 8006:8006 clairdiag
```

| URL | |
|---|---|
| http://localhost:8006/ | UI |
| http://localhost:8006/docs | Swagger |
| http://localhost:8006/v1/health | Health check |

### Without Docker

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8006 --reload
```

No environment variables required. No external services, no API keys, no database.

---

## API Endpoints

| Method | URL | Description |
|---|---|---|
| GET | `/v1/health` | Health check + engine versions |
| POST | `/v1/analyze` | Symptom analysis → 35+ fields |
| POST | `/v1/clinical-decision` | Alias for /v1/analyze |
| POST | `/v1/parse-symptoms` | Extract symptoms from free text |
| POST | `/v1/parse-confirm` | Extract + confirmation message + context |
| POST | `/v1/revaluate` | Post-test reasoning |
| GET | `/v1/scenarios` | Clinical demo scenarios |
| GET | `/v1/admin/debug` | Full pipeline debug trace |

---

## Architecture — CORE v2.3 LOCKED

Deterministic pipeline — no ML, no randomness, fully auditable.

```
free text / symptoms
       │
       ▼
[NLP Normalizer]   — 120+ FR synonyms, fuzzy, negation, typo, trace
[Context Parser]   — after_meal, post-antibiotics, chronology, aggravation_time
       │
       ▼
1.  NSE  — normalization, aliases → SYMPTOM_DIAGNOSES
2.  SCM  — compression to 5–12 key symptoms
3.  RFE  — red flags → EMERGENCY if detected
4.  BPU  — probabilistic scoring + combos + exclusions + incoherence
5.  RME  — risk level (urgency_level)
6.  TCE  — temporal adjustments (onset + duration)
7.  CRE  — medical rules (HAS-like)
8.  TCS  — decision thresholds + composite confidence
9.  LME  — test selection: score = diagnostic_value / cost
10. SGL  — safety layer: incoherence, conflicts, cap confidence
       │
       ▼
  AnalyzeResponse (35+ fields, Absolute Mode)
```

### Composite confidence

| Component | Weight | Description |
|---|---|---|
| couverture | 35% | share of symptoms covered by top diagnosis |
| cohérence | 35% | gap between top1 and top2 |
| qualité | 20% | number of symptoms provided |
| red_flag penalty | −10% | if urgent symptoms present |

Cap rules: ≤ 1 symptom → 0.35 max, ≤ 2 symptoms → 0.55 max, gap < 0.10 → 0.55 max.

### Decision Engine 2.0

| Decision | Condition |
|---|---|
| `EMERGENCY` | red flag detected |
| `URGENT_MEDICAL_REVIEW` | urgency_level = élevé |
| `TESTS_REQUIRED` | TCS_2 / besoin_tests |
| `MEDICAL_REVIEW` | TCS_3 / TCS_4 / incertain |
| `LOW_RISK_MONITOR` | TCS_1, low risk |

---

## API Response — full structure (35+ fields)

| Block | Fields |
|---|---|
| Core | `diagnoses`, `tests`, `explanation`, `decision` |
| Confidence | `confidence_level`, `tcs_level`, `urgency_level` |
| Safety | `emergency_flag`, `safety`, `do_not_miss`, `sgl_warnings` |
| Clinical | `clinical_reasoning`, `diagnostic_path`, `differential`, `test_details` |
| Economics | `economics`, `economic_impact` |
| NLP | `interpreted_symptoms`, `input_confidence`, `symptom_trace` |
| Context | `context` (trigger, pattern, cause, frequency, chronology, aggravation_time) |
| Decision | `decision_logic`, `consistency_check`, `scenario_simulation`, `diagnostic_tree` |
| Trust | `trust_score`, `edge_case_analysis`, `misdiagnosis_risk` |
| Absolute Mode | `quality_gate`, `self_check`, `stability`, `trace_id`, `is_valid_output` |
| Final Layer | `audit`, `engine_meta`, `safe_output` |
| Meta | `compliance`, `is_fallback`, `session_id`, `worsening_signs` |

---

## Example response `/v1/analyze`

```json
{
  "diagnoses": [
    {"name": "Grippe", "probability": 0.46, "key_symptoms": ["fièvre","toux","fatigue"]},
    {"name": "Bronchite", "probability": 0.35, "key_symptoms": ["toux"]},
    {"name": "Rhinopharyngite", "probability": 0.31, "key_symptoms": ["fièvre","fatigue"]}
  ],
  "tests": {"required": ["CRP","NFS"], "optional": ["PCR grippe"]},
  "decision": "TESTS_REQUIRED",
  "confidence_level": "modéré",
  "urgency_level": "faible",
  "economics": {"standard_cost": 120, "optimized_cost": 75, "savings": 45},
  "context": {"trigger": null, "cause": null, "frequency": null, "after_food": false},
  "clinical_reasoning": {
    "why_top1": "Grippe retenu car fièvre, toux, fatigue (46%)",
    "context_influence": "",
    "negative_signals": [],
    "discriminator_logic": "fièvre discrimine Grippe vs Bronchite"
  },
  "diagnostic_tree": [
    {
      "step": 1, "action": "CRP",
      "goal": "Évaluer le niveau d'inflammation",
      "priority": "haute", "estimated_value": "sensibilité 80%",
      "if_positive": "Chest X-ray if respiratory context",
      "if_negative": "Infectious profile unlikely"
    }
  ],
  "trust_score": {
    "global_score": 0.72, "data_quality": 0.6,
    "model_confidence": 0.8, "parser_reliability": 0.55,
    "context_quality": 0.0
  },
  "consistency_check": {
    "top1_stability": true, "score_gap": 0.11,
    "decision_robustness": "medium",
    "symptom_logic_consistent": true,
    "context_logic_consistent": true
  },
  "edge_case_analysis": {
    "atypical_presentation": false, "conflict_detected": false,
    "fallback_reason": "", "manual_review_recommended": false
  },
  "audit": {
    "final_decision_path": "input(3 syms) → compress(3) → score(top=0.46) → decision=TESTS_REQUIRED",
    "context_detected": {},
    "symptom_trace": {"fièvre": "fièvre", "toux": "toux"}
  },
  "quality_gate": {"passed": true, "score": 0.97, "threshold": 0.97},
  "self_check": {"logic_consistent": true, "no_conflicts": true, "decision_valid": true},
  "engine_meta": {"build_hash": "8ea6d8f3e436", "mode": "ABSOLUTE", "core_status": "LOCKED"},
  "safe_output": {"is_medical_advice": false, "requires_validation": true},
  "trace_id": "87e56f416921900d",
  "is_valid_output": true
}
```

---

## Quality Gate

Every response is automatically validated before delivery:

```json
"quality_gate": {
  "passed": true,
  "score": 0.97,
  "threshold": 0.97,
  "block_reason": ""
}
```

**Self-check rules:**
- `logic_consistent` — top diagnosis supported by at least 1 symptom
- `no_conflicts` — incoherence_score < 0.30
- `decision_valid` — decision matches risk profile
- `tests_relevant` — tests have diagnostic_value for top diagnosis
- `risk_aligned` — confidence does not contradict misdiagnosis_risk

**Anti-fake validation:**
- High probability without supporting symptoms → penalty
- Single symptom + confidence ≥ 0.75 → penalty
- All probabilities identical (degenerate output) → penalty
- Symptom added without trace → blocked by normalizer

---

## Safe Mode

Always active. Cannot be disabled:

```json
"safe_output": {
  "is_medical_advice": false,
  "requires_validation": true,
  "risk_level": "controlled",
  "usage_scope": "orientation_only"
}
```

---

## Voice Input

- **Technology:** Web Speech API (browser-native, no backend)
- **Language:** fr-FR
- **Supported:** Chrome, Edge (recommended)
- **Partial:** Safari iOS (unstable, requires permission each time)
- **Not supported:** Firefox
- **Requires:** HTTPS (works on localhost for testing)
- **Auto-correction:** removes euh, genre, tu vois, ben, bah, hein, attends, comment dire
- **Confidence display:** high ✓ / medium ~ / low ⚠
- **Note:** Web Speech API sends audio to Google servers — requires internet connection

---

## NLP Normalizer

Understands any French text — conversational, argot, typos.

```python
extract_symptoms("mal au ventre envie de vomir je suis KO")
# → ["douleur abdominale", "nausées", "fatigue"]

extract_symptoms("barbouillé depuis ce matin")
# → ["nausées"]

extract_symptoms("fiavr toux fatig")
# → ["fièvre", "toux", "fatigue"]

extract_symptoms("ventre gonflé après manger")
# → ["ballonnements", "après repas"]

extract_symptoms("douleur la nuit")
# → ["symptomes nocturnes"]
```

**Calibration: 55/55 (100%)** across three test packs (basic / extended / ultra-chaotic).

---

## Version lock

| Component | Version |
|---|---|
| ENGINE | v2.3 |
| RULES | v1.2 |
| REGISTRY | v1.0 |
| CORE STATUS | LOCKED |
| BUILD HASH | 8ea6d8f3e436 |
| VALIDATION BASELINE | H15_G30_F40_S100 |

Core is frozen. Extensions only via new fields on top of existing structure (steps 1–10 untouched).

---

## Tests

```bash
python run_tests.py           # gold pack (35 cases)
python run_gold_30.py         # 30 gold cases
python test_pack1.py          # NLP pack 1 (15 cases)
python test_pack2.py          # NLP pack 2 (20 cases)
python test_pack3.py          # NLP pack 3 (20 cases, chaotic)
python run_stress_100.py      # stress 100
python run_failure_pack.py    # failure pack 40
```

---

## Project structure

```
app/
├── data/
│   ├── symptoms.py          — SYMPTOM_DIAGNOSES, ALIASES, COMBO_BONUSES, EXCLUSIONS
│   └── tests.py             — TEST_CATALOG with diagnostic_value and cost
├── models/
│   └── schemas.py           — Pydantic v2 (35+ fields, AnalyzeResponse)
├── pipeline/
│   ├── nlp_normalizer.py    — NLP: 120+ synonyms, fuzzy, negation, trace
│   ├── context_parser.py    — Context: after_meal, chronology, aggravation_time
│   ├── orchestrator.py      — orchestrator + all builder functions
│   ├── nse.py               — step 1: parser + aliases
│   ├── scm.py               — step 2: compression
│   ├── rfe.py               — step 3: red flags
│   ├── bpu.py               — step 4: scoring + incoherence
│   ├── rme.py               — step 5: risk
│   ├── tce.py               — step 6: temporal
│   ├── cre.py               — step 7: medical rules
│   ├── tcs.py               — step 8: confidence + TCS level
│   ├── lme.py               — step 9: test selection
│   ├── sgl.py               — step 10: safety layer
│   ├── erl.py               — post-test re-evaluation
│   ├── session.py           — session store (TTL 30 min)
│   ├── cost_engine.py       — economic layer
│   └── request_logger.py    — structured request logging
└── api/
    └── routes.py            — FastAPI endpoints
static/
└── index.html               — UI (vanilla JS, voice input, expert mode)
```

---

## Disclaimer

This system is not a medical device and does not replace physician judgment.
In case of red flag symptoms — call emergency services immediately (15 / 112).
Probabilities are weighted scores, not clinical statistics.
Test costs are indicative — average prices France / EU.