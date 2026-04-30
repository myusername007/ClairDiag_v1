# ClairDiag v1.1.0 — Architecture Overview

**Prepared for:** Technical due diligence / external review
**Version covered:** v1.1.0 (production frozen 2026-04-30)
**Date:** April 30, 2026
**Audience:** Technical reviewers (acquéreurs, partenaires, organismes notifiés, médecins validateurs)

---

## 1. Executive summary

ClairDiag is a deterministic clinical orientation engine for general medicine in French ambulatory care. It takes patient-reported symptoms in free French text plus minimal structured context (age, sex, risk factors), and produces:

- An urgency level (4 classes)
- A clinical category (10 classes)
- A short reasoning trace
- A recommended action (with specialist or generalist routing)

The system is **not** a diagnostic tool. It is positioned as orientation only, conformément aux articles R.4127-39 et R.4127-70 du Code de la santé publique.

**Validation status (April 2026):**

- 90/90 cases — main internal validation set
- 49/50 cases — independent test set (Claude-authored, Roman did not see during dev)
- 20/20 cases — adversarial set
- 0 missed danger across all sets
- 0 over-triage on 8 false positive traps
- Physician validation: pending (active candidate search)

---

## 2. Pipeline architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    POST /v3/analyze                          │
│              { free_text, patient_context }                  │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │ STAGE 1: Text normalization (NLP)      │
        │   - accent stripping (fixed bug v3.2.1)│
        │   - lowercase, whitespace cleanup      │
        │   - typo tolerance (fuzzy match)       │
        └────────────────────┬───────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │ STAGE 2: Symptom mapping               │
        │   - 10 categories                      │
        │   - 224+ patient expressions           │
        │   - R6 disambiguation rules            │
        └────────────────────┬───────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │ STAGE 3: Feature extraction (NEW v1.1) │
        │   Single source of truth for patterns: │
        │   - symptoms[]                         │
        │   - temporal {onset, duration}         │
        │   - demographics {age, sex, pregnancy} │
        │   - risk_factors[]                     │
        │   - minimization_detected              │
        │   - escalation_detected                │
        └────────────────────┬───────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │ STAGE 4: Pre-triage (HYBRID)           │
        │                                        │
        │   PRIMARY: Abstract patterns v2 (8)    │
        │     evaluator-based, feature-driven    │
        │                                        │
        │   FALLBACK: Token patterns v1 (27+)    │
        │     legacy, expression-driven          │
        │                                        │
        │   Resolution: PRIMARY wins; FALLBACK   │
        │   only if PRIMARY returns no match     │
        └────────────────────┬───────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │ STAGE 5: Safety floor (v2 core)        │
        │   - urgent_triggers list (53+)         │
        │   - AND-triggers (CTRL-XX)             │
        │   - Always priority over patterns      │
        └────────────────────┬───────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │ STAGE 6: Fusion & output build         │
        │   final_triage = MAX(safety, pre_triage,│
        │                      category_default)  │
        │   - confidence calibration             │
        │   - danger_to_exclude visibility rules │
        └────────────────────┬───────────────────┘
                             │
                             ▼
                    response API JSON
```

**Key architectural property: Safety dominance**

At each fusion point, the higher urgency level wins. A category that suggests "non_urgent" can never override a safety floor or pattern that flags "urgent". This is unidirectional and non-negotiable.

---

## 3. Pattern taxonomy

The system uses three distinct pattern families, each with its own role.

### 3.1 Abstract patterns v2 (primary layer — 8 active in v1.1.0)

Feature-driven, evaluator-based. Each pattern is a tree of conditions over the feature object produced by Stage 3. Patterns do not parse raw text directly.

**Active in v1.1.0:**

| ID     | Name                                  | Mortality if missed                      |
|--------|---------------------------------------|------------------------------------------|
| ABS-01 | SCA atypique (>50 + risk factors)     | 5-15%                                    |
| ABS-02 | Pulmonary embolism                    | 30%                                      |
| ABS-03 | Subarachnoid hemorrhage / thunderclap | 40-50%                                   |
| ABS-04 | Meningitis                            | 10-30%                                   |
| ABS-05 | Sepsis                                | +7%/h                                    |
| ABS-06 | Ectopic pregnancy (GEU)               | 1-5% rupture                             |
| ABS-07 | Subdural hematoma (anticoagulated)    | 30-90%                                   |
| ABS-08 | Suicidal ideation                     | catastrophic, immediate redirect to 3114 |

**Roadmap to v2.0:** convert remaining token patterns to abstract over Q3-Q4 2026.

### 3.2 Token patterns v1 (fallback layer — 27+ active)

Legacy patterns developed iteratively from observed test failures. Expression-driven (matches against tokens in normalized text). Active as safety net for cases not yet covered by abstract layer.

Examples: PE-01..PE-08 (initial set), PE-09..PE-34 (organic growth).

**Status:** maintained, not extended. New patterns go into abstract layer v2.

### 3.3 Anti-anchor and minimization rules (cross-cutting)

Operate at Stage 4 alongside patterns. Their role: prevent the system from accepting patient self-diagnosis or minimization as ground truth.

- **ANCHOR-RESIST-01:** Anxiety history does not reduce triage on physical symptoms.
- **ANCHOR-RESIST-02:** Asthma history does not mask EP suspicion.
- **ANCHOR-RESIST-03:** Migraine history does not apply if "different from usual."
- **MIN-01:** Verbal minimization (`"mais ça va"`, `"rien de grave"`) reweights subjective vs objective signals.
- **MIN-02:** Self-diagnosis (`"c'est mon stress"`) is logged but never primary category.

---

## 4. Hybrid resolution: how primary and fallback interact

```python
def pre_triage(features):
    # Step 1: Abstract patterns (primary)
    abstract_matches = []
    for pattern in ABSTRACT_PATTERNS_V2:
        if evaluate_pattern(pattern, features):
            abstract_matches.append(pattern)

    # Step 2: Token patterns (fallback) — always evaluated for logging
    token_matches = []
    for pattern in TOKEN_PATTERNS_V1:
        if evaluate_token_pattern(pattern, features):
            token_matches.append(pattern)

    # Step 3: Resolution
    if abstract_matches:
        return {
            "primary_layer_used": "abstract_v2",
            "matched_patterns": [p["pattern_id"] for p in abstract_matches],
            "triage_level": max_severity([p["triage_level"] for p in abstract_matches]),
            "fallback_would_have_matched": [p["pattern_id"] for p in token_matches]
        }

    if token_matches:
        return {
            "primary_layer_used": "token_v1_fallback",
            "matched_patterns": [p["pattern_id"] for p in token_matches],
            "triage_level": max_severity([p["triage_level"] for p in token_matches])
        }

    return {"primary_layer_used": "none", "triage_level": None}
```

**Why this matters:**

- Conflict resolution explicit (abstract wins)
- Audit trail shows when fallback compensates abstract gap (signal for next pattern to migrate)
- No silent disagreement between layers

---

## 5. Design decisions and their rationale

### 5.1 Why deterministic, not ML

ClairDiag uses no neural networks, no Bayesian inference, no machine learning. This is intentional.

**Reasons:**

- **Explicability for regulators.** Every output traceable to specific rules. ANSM and notified bodies prefer transparent decision logic over black-box statistical models.
- **No drift.** Production behavior is exactly the version's behavior. ML models drift over time and require re-validation.
- **No training data dependency.** ClairDiag does not require thousands of labeled clinical cases to function. Knowledge is encoded as rules vetted by the medical team.
- **Auditable failure modes.** When the system fails, the failure path is directly readable in the rules. ML failure analysis requires statistical investigation.

**Trade-off:** abstract pattern coverage requires manual rule authoring (one-time work). ML would generalize automatically (with risk of unsafe generalization).

### 5.2 Why hybrid (abstract + fallback) instead of clean rewrite

ClairDiag chose the **strangler fig** migration pattern (Martin Fowler):

- Production system (token patterns v1) keeps working
- New layer (abstract patterns v2) progressively replaces it
- Each migration step independently testable
- No big-bang risk

**Trade-off:** dual-layer increases short-term complexity. Mitigation: explicit roadmap, layer versioning, test coverage on abstract layer ≥ 95%.

### 5.3 Why safety floor cannot be reduced by patterns

Architectural rule: at each fusion point, urgency level can only **increase**, never decrease. A category mapper finding "ORL_simple" cannot override a safety floor flagging "urgent".

**Reason:** the cost of false negative (missed danger) is mortality. The cost of false positive (sur-triage) is one unnecessary consultation. Asymmetric error costs justify asymmetric resolution.

### 5.4 Why "differential-only" classification exists

Some pathologies are frequent and non-specific in early evolution (e.g., appendicitis as epigastric pain). Treating them as primary hypothesis on weak signals creates massive over-triage. Excluding them creates dangerous misses.

**Solution:** classify as `differential_only`. Pathology stays in differential list (visible to clinician audit), but never as primary unless specific trigger present.

### 5.5 Why no continuous learning

ClairDiag does not learn from production user data. This is regulatory: continuous learning under MDR triggers higher-class certification (IIb minimum) and ongoing post-market surveillance. v1.x scope is class I to early Class IIa. Continuous learning is a v3.x consideration.

---

## 6. Test methodology

Three corpora, used independently:

### 6.1 Internal regression set (90 cases)

- Built incrementally during development
- Roman authored most cases
- **Risk:** circular validation (same author wrote system and tests). Disclosed openly.
- Purpose: prevent regression as patterns are added

### 6.2 Independent test set (50 cases)

- Authored by Claude (separate from Roman's development context)
- Targets the 20 vital patterns + 6 anti-anchor + 2 minimization rules
- 8 false positive traps included
- Roman did not see expected outputs during integration
- **Result v1.1.0:** 49/50 PASS (one PARTIAL, no missed danger)

### 6.3 Adversarial set (20 cases)

- Edge cases, atypical presentations, minimized symptoms
- **Result v1.1.0:** 20/20 PASS

### 6.4 Validation gap acknowledged

All three corpora are written by ClairDiag team (Roman + Claude). **Physician validation is the gap.** Active recruitment in progress for an external clinical reviewer to validate corpora and orientation logic.

Until physician validation completes, all clinical content is tagged `pending_physician_validation`.

---

## 7. Performance characteristics (v1.1.0)

| Metric                         | Value                 | Notes                              |
|--------------------------------|-----------------------|------------------------------------|
| Missed danger rate (90+50+20)  | 0/160                 | Zero across all controlled corpora |
| Over-triage on FP traps (8)    | 0/8                   | Strong specificity on tested cases |
| Pattern coverage               | 8 abstract + 27 token | 80%+ of vital scenarios            |
| Mean response latency          | TBD                   | To measure in pilot                |
| Real-world false positive rate | Unknown               | To measure in pilot                |
| Languages                      | French only           | Roadmap: not multi-language for v1 |

---

## 8. Known limitations (also see risk_register.md)

1. **NLP fragility.** A bug in `_strip_accents` caused 14 failures before fix. Other NLP layer bugs likely undiscovered.
2. **Pattern overfitting risk.** 24 of 34 token patterns added reactively to test failures. Real-world cases with slight wording differences may fall through.
3. **Single-shot architecture.** No proactive clarification questions in v1.1.0. Module 1 (adaptive follow-up questions) integrated in v1.2.
4. **No imagery / biology integration.** Patient cannot upload labs or photos. v1.x scope is text-only orientation.
5. **No physician validation completed.** All clinical content `pending_physician_validation`.
6. **French ambulatory only.** Pediatrics, pregnancy 3rd trimester, suicidal ideation are explicitly out-of-scope or hard-routed.
7. **Real-world FP rate unmeasured.** Internal test FP rate is 0%, but real-world expected at 5-15% given patient writing variability.

---

## 9. Roadmap to v2.0 (architectural maturity)

| Version | Scope                                                                         | ETA               |
|---------|-------------------------------------------------------------------------------|-------------------|
| v1.1.0  | Current — hybrid abstract + token, 8 abstract patterns                        | Frozen 2026-04-30 |
| v1.2    | +Module 1 (adaptive follow-up questions) ✅ delivered                         | Q3 2026           |
| v1.3    | +5 patterns abstracted (13 total)                                             | Q3 2026           |
| v1.4    | +Module 2 (économie real-time) integrated                                     | Q3-Q4 2026        |
| v1.5    | +Module 3 (local directory ARS PACA) ✅ delivered                             | Q4 2026           |
| v1.6    | +Module 4 (follow-up journey) ✅ delivered                                    | Q4 2026           |
| v2.0    | All patterns abstract, token layer deprecated, physician validation completed | Q1 2027           |

---

## 10. Repository structure (for code review)

```
clairdiag_v1/
├── v3_dev/
│   ├── core.py                              # Main pipeline v3.2.0 / v1.1.0
│   ├── feature_extractor.py                 # Stage 3 (NEW v1.1)
│   ├── pattern_evaluator.py                 # Abstract pattern evaluator (NEW v1.1)
│   ├── pattern_engine_v3.py                 # Token patterns v1 (fallback)
│   ├── followup_engine.py                   # Module 01 — adaptive follow-up
│   ├── followup_journey_engine.py           # Module 04 — patient journey
│   ├── local_directory_engine.py            # Module 03 — local directory
│   ├── common_symptom_mapper.py             # Stage 2
│   ├── medical_normalizer_v3.py             # Stage 1 NLP
│   ├── and_triggers.py                      # AND-triggers CTRL-XX
│   ├── general_orientation_router.py        # Stage 6 orientation
│   ├── v3_confidence_engine.py              # Confidence calibration
│   ├── data/
│   │   ├── clinical_patterns_v2_abstract.json  # ABS-01..ABS-08
│   │   ├── followup_questions_v1.json           # Module 01 config
│   │   ├── local_directory_v1.json             # Module 03 seed
│   │   ├── urgent_triggers_v1.json
│   │   └── common_symptom_mapping_v1.json
│   └── tests/
│       ├── run_final_validation_100.py      # 90 internal cases
│       ├── run_independent_test_50.py       # 50 independent cases
│       ├── test_pattern_evaluator.py        # 14 abstract pattern tests
│       ├── test_followup_engine.py          # 8 followup tests
│       ├── test_local_directory.py          # 10 directory tests
│       ├── test_followup_journey.py         # 11 journey tests
│       └── test_feature_extractor.py        # 7 extractor tests
├── app/
│   └── api/
│       └── routes_v3.py                    # POST /v3/analyze + /v3/analyze/followup
└── docs/
    ├── architecture_overview.md            # this file
    └── risk_register.md
```

---

## 11. Contact and references

- **Project lead:** Igor Pervouhin, La Londe-les-Maures
- **Technical lead:** Roman (developer)
- **Architecture and clinical review:** Claude (Anthropic)
- **Soleau IP deposit:** DSO2026009584 (16/03/2026) + complementary deposit pending

---

*End of document.*