# ClairDiag v3 — Medical Triage + Probability Engine
## AI Clinical Orientation System (Deterministic, Explainable, Auditable)

**Version:** `ClairDiag v1.1.0 — FINAL DEMO LOCKED`  
**Branch:** `v3_dev`  
**Status:** `LOCKED`

---

## Live Demo

| Environment | URL |
|---|---|
| Production v3 | https://clairdiagv1-production-9dc2.up.railway.app/v3 |
| Swagger / Docs | https://clairdiagv1-production-9dc2.up.railway.app/docs |
| Health check | https://clairdiagv1-production-9dc2.up.railway.app/v3/health |

---

## What it is

ClairDiag v3 is a deterministic clinical triage and orientation engine that:
- Detects medical emergencies from free-text French input
- Orients patients toward the right specialist and relevant exams
- Calculates economic impact vs unguided care pathway
- Generates explainable, auditable clinical reasoning
- Supports adaptive follow-up questions when confidence is low

## What it is NOT

- **Not** a diagnostic tool
- **Not** a replacement for physician judgment
- **Not** a medical device
- Requires physician validation before any clinical action

---

## Why it matters

- 20–40% of medical tests are unnecessary *(OECD data)*
- Diagnostic delays cost billions annually across healthcare systems
- ClairDiag reduces cost while increasing clarity and traceability
- Every decision is explainable, reproducible and auditable — no black box
- No ML, no randomness — fully deterministic and auditable

---

## Architecture

```
free text (French, conversational, argot, typos)
       │
       ▼
[normalize_text]          — apostrophes, lowercase, accents preserved
[common_symptom_mapper]   — fuzzy match → category + urgent_trigger + AND-triggers
       │
       ├── urgent_trigger → STOP → urgent output (SAMU 15)
       ├── AND-trigger    → STOP → medical_urgent output
       │
       ▼
[pattern_engine_v3]       — 34 clinical patterns (PE-01..PE-34)
  PE-01..PE-10: existing (anticoag, saignement, EP, confusion, SCA, HSA, AVC, IC, syncope)
  PE-11..PE-25: new (FAST, méningite, sepsis, neutropénie, GEU, dissection, DVT, prééclampsie, HSD, hémorragie, suicidal, hémoptysie, pyélo, ischémie, AIT)
  PE-26..PE-34: new (dyspnée sévère, SCA atypique, grossesse+dyspnée, anticoag+GI, palpitations, migraine atypique, SCA épigastrique, GEU contexte, AINS+GI)
       │
       ├── match → urgent / urgent_medical_review / medical_urgent output
       │
       ▼
[v2_safety_floor]         — v2 core (locked, unchanged)
[clinical_combinations]   — AND-trigger combinations
[general_orientation_router] — category → urgency + reasoning
[v3_confidence_engine]    — confidence score (low/medium/high)
       │
       ▼
[economy_calculator]      — economic impact hook (Module 02, additive)
       │
       ▼
  Multi-layer JSON output (triage / clinical / danger / confidence / engine / economic_value)
       │
       ▼
[followup_engine]         — Module 01: adaptive follow-up if confidence < 5 or vague
```

### Pattern Engine Coverage (PE-01..PE-34)

| Pattern | Condition | Urgency |
|---|---|---|
| PE-01 | Anticoagulant + trauma crânien | urgent |
| PE-05 | Douleur thoracique (anchor-resist) | urgent |
| PE-07 | Céphalée thunderclap (HSA) | urgent |
| PE-09 | Orthopnée / IC décompensée | urgent |
| PE-11 | FAST / AVC / AIT | urgent |
| PE-12 | Méningite / purpura fulminans | urgent |
| PE-13 | Sepsis (fièvre + altération AEG) | urgent |
| PE-14 | Neutropénie fébrile sous chimio | urgent |
| PE-16 | Dissection aortique | urgent |
| PE-18 | Prééclampsie | urgent |
| PE-21 | Idéation suicidaire | urgent |
| PE-27 | SCA atypique (sueurs + nausée) | urgent |
| PE-15 | GEU (règles retard + douleur) | urgent_medical_review |
| PE-17 | TVP / EP (mollet + contexte) | urgent_medical_review |
| PE-22 | Hémoptysie | urgent_medical_review |
| PE-23 | Pyélonéphrite | urgent_medical_review |
| PE-24 | Ischémie mésentérique | urgent_medical_review |
| ... | + 17 autres | ... |

---

## API Endpoints

| Method | URL | Description |
|---|---|---|
| GET | `/v3/health` | Engine status |
| POST | `/v3/analyze` | Main triage pipeline |
| POST | `/v3/analyze/followup` | Adaptive follow-up questions |

### POST /v3/analyze — Request

```json
{
  "free_text": "J'ai très mal à la tête, c'est apparu d'un coup",
  "patient_context": {
    "age": 45,
    "sex": "F",
    "duration_days": 0,
    "risk_factors": ["HTA"]
  }
}
```

### POST /v3/analyze — Response (multi-layer)

```json
{
  "triage": {
    "urgency": "urgent",
    "urgent_message": "Céphalée violente soudaine : évaluation médicale immédiate — hémorragie sous-arachnoïdienne à exclure en urgence.",
    "pattern_triggered": true,
    "pattern_id": "PE-07",
    "pattern_name": "Céphalée thunderclap (HSA suspectée)"
  },
  "clinical": {
    "category": "general_vague",
    "general_orientation": null,
    "clinical_reasoning": null,
    "matched_symptoms": []
  },
  "danger": { "danger_output": null },
  "confidence": {
    "level": "high",
    "score": 9,
    "orientation_summary": "Signaux d'urgence détectés — évaluation médicale immédiate requise."
  },
  "economic_value": null,
  "followup_needed": false,
  "disclaimer": "ClairDiag v3 — outil d'aide à la décision uniquement."
}
```

### Urgency Levels

| Level | Meaning |
|---|---|
| `urgent` | Appel 15 / Urgences immédiats |
| `medical_urgent` | Consultation dans les heures / 24h |
| `urgent_medical_review` | Consultation rapide (24-72h) |
| `medical_consultation` | Rendez-vous médecin (quelques jours) |
| `non_urgent` | Surveillance à domicile |

### POST /v3/analyze/followup — Request

```json
{
  "session_id": "uuid-from-analyze",
  "round": 1,
  "answers": [
    { "qid": "DERM-Q1", "tag": "duration_acute" },
    { "qid": "DERM-Q2", "tags": ["zone_face", "zone_torso"], "tag": "zone_face" }
  ]
}
```

`tags[]` = multi-select (plusieurs zones / symptômes). `tag` = premier sélectionné (backward compat).

---

## Modules

### Module 01 — Adaptive Follow-up Questions

**Trigger:** confidence < 5 OR category = `general_vague` OR fallback_used  
**Files:**
- `v3_dev/followup_engine.py` — `FollowupEngine` class
- `v3_dev/data/followup_questions_v1.json` — 10 categories × 3 questions + safety globals

**Logic:**
- Max 2 rounds, 3 questions per round
- Safety-critical questions (suicidal ideation) = single-choice, always first
- Body zone questions = multi-select (checkbox)
- `override_all` tag → immediate urgent escalation

**Non-regression:** never triggers if urgency = `urgent` already detected.

### Module 02 — Economy Real-time Calculator

**Trigger:** always, additive hook after Stage 5 in `core.py`  
**Files:**
- `v3_dev/economy_calculator.py` — `EconomyConfig` + `estimate_economic_value()`
- `v3_dev/data/economy_tariffs_fr_v1.json` — tarifs Sécu FR 2025-2026

**Coverage:** `fatigue_asthenie`, `urinaire`, `orl_simple`  
**Output:** `economic_value` field in response (None if not applicable, never blocks pipeline)

```json
{
  "economic_value": {
    "applicable": true,
    "consultations_avoided": 2,
    "tests_avoided": ["ecg", "echo_abdominale"],
    "estimated_savings_eur": 152.63,
    "confidence": "high",
    "economy_patient_eur": 12.0,
    "time_saved_days": 23,
    "patient_summary": "Le parcours recommandé économise..."
  }
}
```

**Disclaimer:** tarifs pending physician/accountant validation before production use.

---

## Frontend

**File:** `frontend/index_v3.html`  
**Tech:** vanilla JS, mobile-first, no framework dependencies

**Result screen order (LOCKED):**
1. Urgency / action banner
2. Examens recommandés (exams-first by category)
3. Professionnel adapté (specialist, never GP-first)
4. Pourquoi cette orientation
5. Où aller (local_orientation if available)
6. Que faire maintenant
7. Bénéfices patient (8 lines + gain de temps)
8. Impact économique estimé (grid: patient / système / total 80-450€)
9. Suivi CTA
10. Trust block (final sentences LOCKED)

**Follow-up UX:** checkbox multi-select for body zones, radio for safety-critical questions.

---

## Project Structure

```
clairdiag_v1/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── routes.py          — v1 endpoints (locked)
│   │   ├── routes_v2.py       — v2 endpoints (locked)
│   │   └── routes_v3.py       — v3 endpoints (active)
│   ├── data/
│   │   ├── symptoms.py
│   │   └── tests.py
│   ├── models/
│   │   └── schemas.py
│   └── pipeline/              — v1/v2 core (locked, untouched)
│       ├── orchestrator.py
│       ├── nse.py / scm.py / rfe.py / bpu.py / rme.py
│       ├── tce.py / cre.py / tcs.py / lme.py / sgl.py
│       └── ...
├── v3_dev/
│   ├── core.py                — v3 pipeline orchestrator
│   ├── pattern_engine_v3.py   — PE-01..PE-34 (34 clinical patterns)
│   ├── common_symptom_mapper.py
│   ├── medical_normalizer_v3.py
│   ├── clinical_combinations_engine.py
│   ├── general_orientation_router.py
│   ├── v3_confidence_engine.py
│   ├── and_triggers.py
│   ├── fuzzy_utils.py
│   ├── loader.py
│   ├── schemas.py
│   ├── followup_engine.py     — Module 01
│   ├── economy_calculator.py  — Module 02
│   └── data/
│       ├── urgent_triggers_v1.json
│       ├── common_symptom_mapping_v1.json
│       ├── clinical_combinations_v1.json
│       ├── common_conditions_config.json
│       ├── danger_exclusion_rules_v1.json
│       ├── danger_reformulation_v1.json
│       ├── followup_questions_v1.json  — Module 01
│       └── economy_tariffs_fr_v1.json  — Module 02
├── frontend/
│   ├── index.html             — v1 UI
│   ├── index_v2.html          — v2 UI
│   └── index_v3.html          — v3 UI (active, LOCKED)
└── v3_dev/tests/
    ├── run_final_validation_100.py   — 90 regression cases
    ├── run_independent_test_50.py    — 50 independent cases
    ├── run_validation_v3.py
    └── run_rw_stress_test_v3.py
```

---

## Deploy

### Railway (production)

Auto-deploy from GitHub branch `v3_dev` on push.

1. Push to `v3_dev` branch
2. Railway detects Dockerfile → builds and deploys automatically
3. No environment variables required
4. Port: `8006`

### Docker (local)

```bash
git clone https://github.com/pervouhinigor/ClairDiag.git
cd ClairDiag
git checkout v3_dev
docker build -t clairdiag-v3 .
docker run -p 8006:8006 clairdiag-v3
```

| URL | |
|---|---|
| http://localhost:8006/v3 | v3 UI |
| http://localhost:8006/docs | Swagger |
| http://localhost:8006/v3/health | Health check |

### Without Docker

```bash
git checkout v3_dev
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8006 --reload
```

No environment variables. No external services. No API keys. No database.

---

## Tests

### Run all (recommended order)

```bash
# 1. Regression — doit donner 90/90 PASS, 0 missed danger
python v3_dev/tests/run_final_validation_100.py

# 2. Independent test — doit donner 49/50 PASS, 0 missed danger, 0 over-triage
python v3_dev/tests/run_independent_test_50.py

# 3. Validation générale
python v3_dev/tests/run_validation_v3.py

# 4. Stress test real-world
python v3_dev/tests/run_rw_stress_test_v3.py
```

### Current baseline (LOCKED)

| Test | Result | Criteria |
|---|---|---|
| Final Validation 90 | **90/90 PASS** | 0 missed danger, 0 fail |
| Independent Test 50 | **49/50 PASS** | 0 missed danger, 0 over-triage |
| Adversarial 20 | **20/20 PASS** | 0 missed danger |

### Criteria for READY status

```
MISSED_DANGER ≤ 2 / 35 urgent cases  → OK for pilot
OVER_TRIAGE   = 0 / 8 traps          → OK
MISSED_DANGER > 5                    → revoir architecture
```

---

## Safety Rules

Always active. Cannot be disabled:

- Pattern engine runs **before** urgent_triggers — no danger missed by categorization
- `urgent_medical_review` correctly escalated in runner
- Negation guard: "pas de fièvre" blocks PE-13 (sepsis)
- Sciatique guard: "descend dans la jambe" without "faiblesse" blocks PE-11c (AIT)
- False positive rate on 8 traps: **0/8**
- Economy module: always in `try/except` — never blocks pipeline

---

## Demo curl

```bash
# Thunderclap headache → urgent (PE-07)
curl -X POST https://clairdiagv1-production-9dc2.up.railway.app/v3/analyze \
  -H "Content-Type: application/json" \
  -d '{"free_text": "J'\''ai très mal à la tête, c'\''est apparu d'\''un coup, c'\''est la pire douleur de ma vie"}'

# Cystite simple → medical_consultation + economic_value
curl -X POST https://clairdiagv1-production-9dc2.up.railway.app/v3/analyze \
  -H "Content-Type: application/json" \
  -d '{"free_text": "J'\''ai des brûlures quand je fais pipi depuis hier", "patient_context": {"age": 28, "sex": "F"}}'

# Neutropénie fébrile → urgent (PE-14)
curl -X POST https://clairdiagv1-production-9dc2.up.railway.app/v3/analyze \
  -H "Content-Type: application/json" \
  -d '{"free_text": "Je suis sous chimio pour cancer du sein, j'\''ai 38.5 de fièvre depuis ce matin"}'
```

---

## Version Lock

| Component | Version | Status |
|---|---|---|
| v3 Engine | v3.2.0 | ACTIVE |
| Pattern Engine | v1.1.0 | LOCKED |
| Module 01 Follow-up | v1.0 | ACTIVE |
| Module 02 Economy | v1.0 | ACTIVE |
| Frontend v3 | v1.1.0 | LOCKED |
| v1/v2 Core | v2.3 | LOCKED, untouched |
| Test Baseline | 90/90 + 49/50 | LOCKED |

---

## Reproducibility Checklist

- [ ] `git clone` + `git checkout v3_dev`
- [ ] `pip install -r requirements.txt`
- [ ] `uvicorn app.main:app --port 8006`
- [ ] `python v3_dev/tests/run_final_validation_100.py` → 90/90
- [ ] `python v3_dev/tests/run_independent_test_50.py` → 49/50
- [ ] Open http://localhost:8006/v3 → enter symptom → see result

No external dependencies. No API keys. No database. Fully self-contained.

---

## Disclaimer

This system is not a medical device and does not replace physician judgment.  
In case of red flag symptoms — call emergency services immediately (15 / 112).  
Economic estimates are indicative — average costs France, pending expert validation.  
Medical content status: `pending_physician_validation`.

---

*ClairDiag v1.1.0 — FINAL DEMO LOCKED*