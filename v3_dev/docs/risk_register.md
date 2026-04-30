# ClairDiag v1.1.0 — Risk Register

**Prepared for:** Technical due diligence / external review
**Version covered:** v1.1.0 (production frozen 2026-04-30)
**Date:** April 30, 2026

This document lists known risks and limitations of the ClairDiag system at version 1.1.0. Explicit risk acknowledgment is part of the engineering discipline of the project. This document is updated with each release.

---

## Risk severity legend

- **Critical** — Could cause patient harm if unmitigated. Active mitigation required.
- **High** — Significant impact on system reliability, sales, or regulatory acceptance. Mitigation in progress.
- **Medium** — Limits scalability or quality. Acceptable for v1.x. Roadmapped.
- **Low** — Known limitation, documented, not blocking.

---

## R1 — Physician validation not completed

**Severity:** Critical
**Category:** Clinical / regulatory

**Description:** All medical content (30 conditions in `conditions_evidence.json`, 10 categories in `common_symptom_groups`, 35 patterns total, 110 internal test cases, 50 independent cases) was authored by Claude and Roman. No external physician has reviewed and signed off the clinical content as of April 2026.

**Impact:**

- Cannot present system as clinically validated to acquéreurs or regulators
- Pilot deployment with real patients raises ethical and legal concerns (responsibility chain unclear)
- Without physician sign-off, the project cannot proceed to CE marking process

**Mitigation status:** Active recruitment of physician validator in progress. Candidate pool includes local GPs (La Londe / Hyères area), URPS PACA contacts, ARS network. ETA: 30 days target.

**Required before pilot:** Yes (blocker).
**Required before sale:** Yes (blocker).

---

## R2 — NLP fragility

**Severity:** High
**Category:** Technical

**Description:** A bug in `_strip_accents` normalization caused 14 test failures before being identified. The cause was a preprocessing mismatch between mapping table (with accents) and input text (stripped). The bug is now fixed, but the incident reveals that:

- The NLP layer is a single point of failure for the entire pipeline
- Other similar bugs may exist undiscovered
- Patterns depend on token presence in normalized text; one missed normalization step breaks pattern matching

**Impact:**

- Real-world variations in spelling, accents, voice-to-text artifacts, slang may bypass patterns
- Refactor to feature-based abstract patterns (v2 layer) reduces this risk for the 8 critical patterns

**Mitigation status:**

- v1.1.0: critical bug fixed
- v1.1.0: 8 critical patterns migrated to feature-based (less NLP-dependent)
- v1.2 roadmap: dirty input testing protocol (typos, slang, voice-to-text simulation)
- v1.3 roadmap: continued migration to feature-based for remaining patterns

**Required before pilot:** Dirty input test pass (4-7 days work).
**Required before sale:** Documented test methodology.

---

## R3 — Pattern overfitting to test corpus

**Severity:** High
**Category:** Technical / clinical

**Description:** Of 34 token patterns in v1.1.0, 24 were added reactively after observing failures on internal test cases. While they fix the specific cases, they may not generalize to real-world variations of the same clinical scenarios.

**Impact:**

- Real-world cases with slight wording variations may fall through
- Estimated real-world failure rate: 5-15% on unseen presentations (vs 0% on test corpora)

**Mitigation status:**

- v1.1.0: 8 patterns migrated to abstract feature-based (less expression-dependent)
- v1.2 roadmap: real-world FP/FN rate measurement during pilot
- v1.3-v2.0 roadmap: progressive migration of remaining patterns to abstract

**Required before pilot:** No (acceptable for early pilot).
**Required before sale:** Documented in risk register and roadmap (this document).

---

## R4 — Real-world false positive rate unknown

**Severity:** High
**Category:** Operational

**Description:** Internal test corpora yield 0% over-triage on 8 false positive traps. This is suspicious. Real-world over-triage is expected to be 5-15% based on:

- Patient writing variability (anxious patients, hypochondriacs)
- Edge cases not in test corpora
- Voice-to-text errors
- Trolling or low-effort input

**Impact:**

- If real-world over-triage exceeds 20%, the value proposition for mayors / mutuelles is undermined (system creates more consultations, not fewer)
- 0% is unrealistic; presenting as such damages credibility with sophisticated reviewers

**Mitigation status:**

- v1.1.0: documented openly (this document)
- v1.2 roadmap: pilot deployment with monitoring of false positive rate on real users
- v1.2 roadmap: target ≤ 15% over-triage acceptable

**Required before pilot:** No (measure during pilot is the point).
**Required before sale:** Honest disclosure in pitch deck.

---

## R5 — Hybrid layer complexity

**Severity:** Medium
**Category:** Technical / maintenance

**Description:** v1.1.0 runs both abstract patterns (8) and token patterns (27+) in parallel. This dual-layer architecture, while justified (strangler fig migration), introduces:

- Doubled maintenance surface
- Potential for layers to disagree (abstract says non-urgent, token says urgent)
- Higher cognitive load for new developers

**Impact:** Maintenance debt accumulates if not actively managed.

**Mitigation status:**

- Conflict resolution rule explicit: abstract layer wins, token layer is fallback only
- Audit trail logs when fallback compensates abstract gap (signal for next migration)
- Versioning explicit: `clinical_patterns_v2_abstract.json` (new) vs `pattern_engine_v3.py` (legacy)
- Roadmap to v2.0 deprecates token layer entirely (Q1 2027)

**Required before pilot:** No.
**Required before sale:** Yes (this document + migration roadmap).

---

## R6 — Test corpus circularity

**Severity:** Medium
**Category:** Validation

**Description:** All test corpora (90 internal + 50 independent + 20 adversarial = 160 cases) are authored by ClairDiag team members. Even "independent" cases (Claude wrote them, Roman did not see during dev) suffer from author bias: same logical framework, similar phrasing patterns.

**Impact:** Internal test PASS rate (160/160 with one PARTIAL) overestimates real-world performance.

**Mitigation status:**

- v1.1.0: documented openly (this document and `architecture_overview.md`)
- v1.1.0: physician validator recruitment in progress (independent corpus author)
- v1.2 roadmap: real-world data from pilot will provide independent test cases
- v1.3 roadmap: 50 cases written by validator physician for next regression set

**Required before pilot:** No.
**Required before sale:** Disclosure in DD documents.

---

## R7 — Single-shot conversational architecture

**Severity:** Medium
**Category:** Product

**Description:** v1.1.0 produces an output from a single free-text input. Unlike Ada Health's adaptive interview, no follow-up questions are asked when input is ambiguous. Result: orientation may be sub-optimal for vague cases (e.g., `IND-045` partial result).

**Impact:**

- Lower confidence scores in 10-20% of cases
- Sub-optimal orientation when patient input is sparse

**Mitigation status:**

- Module 1 (Adaptive Follow-up Questions) delivered in v1.1.0 (`followup_engine.py`)
- Integration complete: `POST /v3/analyze/followup` endpoint active

**Required before pilot:** No (system handles vague cases by routing to medical_consultation, which is safe).
**Required before sale:** Roadmap visibility.

---

## R8 — No real users, no production traffic

**Severity:** High
**Category:** Commercial

**Description:** Zero deployed users as of April 2026. All performance metrics come from internal validation, not real usage.

**Impact:**

- Acquéreurs heavily discount pre-revenue, pre-traction systems
- Realistic valuation today: €100k-€500k acqui-hire (vs €1M+ target)
- Without traction proof, no insurance/mutuelle partnership conversations possible

**Mitigation status:**

- Pilot mairie La Londe in active discussion (target Q3 2026)
- After pilot: 100-500 real users → traction data
- After pilot: case study publication (BMJ Open / JMIR target Q4 2026)

**Required before pilot:** N/A (pilot is the mitigation).
**Required before sale:** Mandatory for premium valuation. Without real users, sale = acqui-hire scenario only.

---

## R9 — No CE marking process started

**Severity:** High
**Category:** Regulatory

**Description:** ClairDiag is positioned as orientation tool (not diagnostic), which limits MDR class I or low-Class IIa. No CE marking process has been initiated. Competitors (Ada — Class IIa, Infermedica — Class IIb) hold this credential.

**Impact:**

- Cannot enter B2B insurance markets that require CE marking
- Cannot partner with hospitals (require Class II minimum)
- Buyer DD will flag this as missing path to enterprise revenue

**Mitigation status:**

- v1.1.0: positioning explicit as orientation only (architecture document, user disclaimers)
- v1.2 roadmap: legal consultation with regulatory affairs counsel (~€2000) — define class
- v1.3-v2.0 roadmap: ISO 13485 quality management system structure (no certification yet, just framework)

**Required before pilot with mairie:** No (mairie pilot does not require CE marking for orientation tool).
**Required before sale at premium valuation:** Yes (or at least process started).

---

## R10 — Solo founder, no medical co-founder

**Severity:** High
**Category:** Commercial / structural

**Description:** Igor Pervouhin is solo founder. No medical co-founder, no business co-founder. Roman is developer (contractor), not equity partner.

**Impact:**

- Acquéreurs view as acqui-hire risk: who continues the project after acquisition?
- Bus factor = 1 (project halts if founder unavailable)
- Reduces credibility with mutuelles, hospitals, regulators

**Mitigation status:**

- v1.x: identify medical advisor or part-time CMO during pilot
- v2.x: explore co-founder options (medical doctor or business)

**Required before pilot:** No.
**Required before premium sale:** Yes (cofounder or strong medical advisor on board).

---

## R11 — No HDS hosting (RGPD blocker for real patients)

**Severity:** Critical
**Category:** Regulatory

**Description:** Real patient data (even pseudonymized) requires HDS-certified hosting (Hébergeur de Données de Santé) under French law. Current dev environment is not HDS.

**Impact:**

- Cannot legally process real patient data in pilot
- RGPD violation if deployed without HDS

**Mitigation status:**

- v1.2 pre-pilot: OVH Healthcare HDS hosting setup planned (~3-6 weeks setup, recurring cost)

**Required before pilot:** Yes (absolute blocker).

---

## Summary table

| Risk                          | Severity | Pilot blocker?     | Sale blocker?          |
|-------------------------------|----------|--------------------|------------------------|
| R1 — No physician validation  | Critical | Yes                | Yes                    |
| R2 — NLP fragility            | High     | No (test required) | No (documented)        |
| R3 — Pattern overfitting      | High     | No                 | No (documented)        |
| R4 — Real-world FP unknown    | High     | No                 | No (honest disclosure) |
| R5 — Hybrid complexity        | Medium   | No                 | No (roadmap)           |
| R6 — Test circularity         | Medium   | No                 | No (disclosure)        |
| R7 — Single-shot architecture | Medium   | No                 | No (roadmap)           |
| R8 — No real users            | High     | N/A                | Yes (premium)          |
| R9 — No CE marking            | High     | No                 | Yes (premium)          |
| R10 — Solo founder            | High     | No                 | Yes (premium)          |
| R11 — No HDS hosting          | Critical | Yes                | Yes                    |

---

## Pre-pilot checklist (R1, R2, R11 are blockers)

- [ ] R1: Physician validator recruited and signed engagement letter
- [ ] R2: Dirty input test protocol executed, ≥ 90% pass rate
- [ ] R11: HDS hosting (OVH Healthcare or equivalent) operational
- [ ] R1 secondary: 110 cases reviewed by validator, sign-off documented

## Pre-sale checklist (premium valuation pathway)

- [ ] R1: Physician validation completed and published
- [ ] R8: Pilot completed with documented metrics (orientation accuracy, user satisfaction, economic impact)
- [ ] R9: CE marking pathway initiated (regulatory consultation done, classification determined)
- [ ] R10: Medical advisor or co-founder on board
- [ ] R8: Case study published (BMJ Open or JMIR or equivalent)

---

*End of document.*