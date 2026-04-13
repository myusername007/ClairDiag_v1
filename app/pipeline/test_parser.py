# ── Test Results Parser — ClairDiag v2.4 ──────────────────────────────────────
# Pipeline:
#   Step 1: raw text extraction (pymupdf)
#   Step 2: token sequence reconstruction (Biogroup format)
#   Step 3: field parsing (name / value / unit / ref_range)
#   Step 4: normalization
#   Step 5: validation (allowed ranges, reject garbage)
#   Step 6: confirmation output (valid / rejected / needs_review)
#
# Biogroup PDF format: each field on its own line after text extraction
#   "Hémoglobine AC\n17,1\ng/dL\n(13,4−16,7)\n15,8\n"
# ─────────────────────────────────────────────────────────────────────────────

import re
import logging
from typing import Optional

logger = logging.getLogger("clairdiag.test_parser")


# ── Step 4: Normalization — canonical name mapping ───────────────────────────

# raw label (lowercase, stripped) → canonical name
_LABEL_MAP: dict[str, str] = {
    # Hématologie
    "hématies":                         "Hématies",
    "hematies":                         "Hématies",
    "hémoglobine":                      "Hémoglobine",
    "hemoglobine":                      "Hémoglobine",
    "hb":                               "Hémoglobine",
    "hématocrite":                      "Hématocrite",
    "hematocrite":                      "Hématocrite",
    "v.g.m.":                           "VGM",
    "vgm":                              "VGM",
    "t.c.m.h.":                         "TCMH",
    "tcmh":                             "TCMH",
    "c.c.m.h.":                         "CCMH",
    "ccmh":                             "CCMH",
    "leucocytes":                       "Leucocytes",
    "polynucléaires neutrophiles":      "Neutrophiles",
    "polynucleaires neutrophiles":      "Neutrophiles",
    "polynucléaires éosinophiles":      "Éosinophiles",
    "polynucléaires basophiles":        "Basophiles",
    "lymphocytes":                      "Lymphocytes",
    "monocytes":                        "Monocytes",
    "plaquettes":                       "Plaquettes",
    # Ionogramme
    "sodium sérique":                   "Sodium",
    "sodium serique":                   "Sodium",
    "potassium sérique":                "Potassium",
    "potassium serique":                "Potassium",
    # Biochimie
    "créatinine":                       "Créatinine",
    "creatinine":                       "Créatinine",
    "estimation du dfg selon la formule ckd−epi": "DFG CKD-EPI",
    "estimation du dfg selon la formule ckd-epi": "DFG CKD-EPI",
    "dfg":                              "DFG CKD-EPI",
    "ferritine":                        "Ferritine",
    # Bilan hépatique
    "asat (transaminases tgo)":         "ASAT",
    "asat":                             "ASAT",
    "alat (transaminases tgp)":         "ALAT",
    "alat":                             "ALAT",
    # Glycémie / Lipides
    "glycémie à jeun":                  "Glycémie",
    "glycemie a jeun":                  "Glycémie",
    "glycémie":                         "Glycémie",
    "triglycérides":                    "Triglycérides",
    "triglycerides":                    "Triglycérides",
    "cholestérol total":                "Cholestérol total",
    "cholesterol total":                "Cholestérol total",
    "cholestérol hdl":                  "HDL",
    "cholesterol hdl":                  "HDL",
    "cholestérol non-hdl":              "Non-HDL",
    "cholestérol non−hdl":              "Non-HDL",
    "cholestérol ldl calculé":          "LDL",
    "cholesterol ldl calcule":          "LDL",
    # Marqueurs tumoraux
    "psa total":                        "PSA",
    # CRP (si présent)
    "crp":                              "CRP",
    "protéine c réactive":              "CRP",
}

# preferred unit per canonical name (pour sélection quand plusieurs unités)
_PREFERRED_UNIT: dict[str, str] = {
    "Hémoglobine":      "g/dL",
    "Créatinine":       "µmol/L",
    "Glycémie":         "g/L",
    "Triglycérides":    "g/L",
    "Cholestérol total":"g/L",
    "HDL":              "g/L",
    "LDL":              "g/L",
    "Non-HDL":          "g/L",
    "Sodium":           "mmol/L",
    "Potassium":        "mmol/L",
    "Ferritine":        "µg/L",
    "ASAT":             "U/L",
    "ALAT":             "U/L",
    "PSA":              "ng/mL",
    "DFG CKD-EPI":      "mL/min/1,73m2",
    # Formule leucocytaire: prefer absolute G/L, not %
    "Neutrophiles":     "G/L",
    "Éosinophiles":     "G/L",
    "Basophiles":       "G/L",
    "Lymphocytes":      "G/L",
    "Monocytes":        "G/L",
}


# ── Step 5: Validation — allowed physical ranges ──────────────────────────────

# canonical name → (min, max) physically possible values
_ALLOWED_RANGES: dict[str, tuple[float, float]] = {
    "Hématies":         (1.0,   10.0),
    "Hémoglobine":      (3.0,   25.0),
    "Hématocrite":      (5.0,   75.0),
    "VGM":              (50.0,  150.0),
    "TCMH":             (10.0,  50.0),
    "CCMH":             (20.0,  45.0),
    "Leucocytes":       (0.1,   100.0),
    "Neutrophiles":     (0.0,   15.0),
    "Éosinophiles":     (0.0,   2.0),
    "Basophiles":       (0.0,   0.5),
    "Lymphocytes":      (0.0,   8.0),
    "Monocytes":        (0.0,   3.0),
    "Plaquettes":       (10.0,  1500.0),
    "Sodium":           (100.0, 200.0),
    "Potassium":        (1.0,   10.0),
    "Créatinine":       (10.0,  2000.0),
    "DFG CKD-EPI":      (1.0,   150.0),
    "Ferritine":        (1.0,   5000.0),
    "ASAT":             (0.0,   2000.0),
    "ALAT":             (0.0,   2000.0),
    "Glycémie":         (0.1,   5.0),
    "Triglycérides":    (0.1,   20.0),
    "Cholestérol total":(0.5,   15.0),
    "HDL":              (0.1,   5.0),
    "LDL":              (0.1,   10.0),
    "Non-HDL":          (0.1,   12.0),
    "PSA":              (0.0,   1000.0),
    "CRP":              (0.0,   500.0),
}

# Patterns that indicate garbage in value field
_GARBAGE_PATTERNS = [
    re.compile(r'^[A-ZÀ-Ÿ]{4,}$'),           # ALL CAPS word = likely a name
    re.compile(r'[a-zA-Z]{6,}'),              # long word = method name
    re.compile(r'impédance|spectropho|fluoro|cinétique|potentiométrie|chimiluminescence|héxokinase|friedewald', re.I),
]

# Lines to skip entirely
_SKIP_PATTERNS = [
    re.compile(r'validé par', re.I),
    re.compile(r'page \d+ sur \d+', re.I),
    re.compile(r'nature de l.échantillon', re.I),
    re.compile(r'intervalle de référence', re.I),
    re.compile(r'antériorités', re.I),
    re.compile(r'^\d{2}[−-]\d{2}[−-]\d{4}$'),   # date line DD-MM-YYYY
    re.compile(r'^demande\s+ax', re.I),
    re.compile(r'^édité le', re.I),
    re.compile(r'^prélevé le', re.I),
    re.compile(r'^patient\s+', re.I),
    re.compile(r'^né\(e\)', re.I),
    re.compile(r'laboratoire de la londe', re.I),
    re.compile(r'selas biogroup', re.I),
    re.compile(r'attention, changement', re.I),
    re.compile(r'objectifs lipidiques', re.I),
    re.compile(r'risque cardiovasculaire', re.I),
    re.compile(r'association française', re.I),
    re.compile(r'lettre individuelle', re.I),
    re.compile(r'dans le cadre', re.I),
    re.compile(r'^\s*\*', re.I),
    re.compile(r'bilan lipidique', re.I),
    re.compile(r'^aspect\s+', re.I),
    re.compile(r'limpide', re.I),
]

# Regex: is this token a numeric value?
_RE_NUMBER = re.compile(r'^[<>]?\s*\d+[,.]?\d*$')
# Regex: is this token a unit?
_RE_UNIT = re.compile(r'^(g/dL|g/L|mmol/L|µmol/L|µg/L|pmol/L|ng/mL|U/L|G/L|T/L|fL|pg|%|mL/min/1,73m2|mL/min/1\.73m2)$', re.I)
# Regex: is this token a reference range?
_RE_REF = re.compile(r'^\(.*\)$')
# Regex: is this a method line?
_RE_METHOD = re.compile(r'^\(.*[a-zA-Z]{5,}.*\)$')


def _is_skip(line: str) -> bool:
    for p in _SKIP_PATTERNS:
        if p.search(line.strip()):
            return True
    return False


def _is_garbage_value(val_str: str) -> bool:
    for p in _GARBAGE_PATTERNS:
        if p.search(val_str):
            return True
    return False


def _parse_number(s: str) -> Optional[float]:
    s = s.strip().lstrip('<>').strip()
    s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_label(raw: str) -> Optional[str]:
    """Strip ' AC' suffix, lowercase, map to canonical."""
    clean = re.sub(r'\s+AC\s*$', '', raw, flags=re.I).strip()
    key = clean.lower()
    if key in _LABEL_MAP:
        return _LABEL_MAP[key]
    # Partial match
    for k, v in _LABEL_MAP.items():
        if k in key:
            return v
    return None


def _validate(canonical: str, value: float, unit: str) -> tuple[bool, str]:
    """Returns (is_valid, reason)."""
    allowed = _ALLOWED_RANGES.get(canonical)
    if allowed is None:
        return True, "no_range_check"
    lo, hi = allowed
    if value < lo or value > hi:
        return False, f"impossible_value: {value} not in [{lo}, {hi}]"
    return True, "ok"


# ── Step 2+3: Token-based reconstruction for Biogroup format ─────────────────

def _extract_tokens(text: str) -> list[str]:
    """Split text into non-empty lines, skip header/footer garbage."""
    tokens = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if _is_skip(line):
            continue
        if _RE_METHOD.match(line):
            continue  # skip method lines like "(Spectrophotométrie ...)"
        tokens.append(line)
    return tokens


def _parse_biogroup_tokens(tokens: list[str]) -> list[dict]:
    """
    State machine over token list.
    Biogroup format after text extraction:
      [label_with_AC] [value] [unit] [(ref_range)] [anteriorite]
    Each on its own line.
    """
    results = []
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]

        # Try to identify as a label (non-numeric, non-unit, non-ref)
        if (_RE_NUMBER.match(tok) or _RE_UNIT.match(tok)
                or _RE_REF.match(tok) or _RE_METHOD.match(tok)):
            i += 1
            continue

        canonical = _normalize_label(tok)
        if canonical is None:
            i += 1
            continue

        # Found a label — collect following tokens
        value_num: Optional[float] = None
        unit_str: str = ""
        ref_str: str = ""
        raw_value: str = ""
        preferred = _PREFERRED_UNIT.get(canonical, "")

        j = i + 1
        # Collect up to 8 tokens ahead (some tests have dual units with method line between)
        collected = []
        while j < n and j < i + 9:
            t = tokens[j]
            # Stop if we hit another label (non-numeric, non-unit, non-ref, non-method)
            if (not _RE_NUMBER.match(t) and not _RE_UNIT.match(t)
                    and not _RE_REF.match(t) and not _RE_METHOD.match(t)):
                if _normalize_label(t) is not None:
                    break
            collected.append(t)
            j += 1

        # Parse collected tokens: value, unit, ref
        # Strategy: find numeric tokens and unit tokens
        # If preferred unit exists, prefer the value that comes just before it
        nums_with_units: list[tuple[float, str, str]] = []  # (val, unit, raw)

        k = 0
        while k < len(collected):
            t = collected[k]
            if _RE_REF.match(t):
                ref_str = t
                k += 1
                continue
            if _RE_METHOD.match(t):
                k += 1
                continue
            if _RE_NUMBER.match(t) and not _is_garbage_value(t):
                v = _parse_number(t)
                if v is not None:
                    # Look for unit in next token
                    u = ""
                    if k + 1 < len(collected) and _RE_UNIT.match(collected[k + 1]):
                        u = collected[k + 1]
                        k += 1
                    nums_with_units.append((v, u, t))
            k += 1

        if not nums_with_units:
            i = j
            continue

        # Select best (value, unit) pair
        if preferred:
            chosen = next(((v, u, r) for v, u, r in nums_with_units if u == preferred), None)
            if chosen is None:
                # fallback: first with any unit
                chosen = next(((v, u, r) for v, u, r in nums_with_units if u), None)
            if chosen is None:
                chosen = nums_with_units[0]
        else:
            chosen = next(((v, u, r) for v, u, r in nums_with_units if u), None) or nums_with_units[0]

        value_num, unit_str, raw_value = chosen

        # Validate
        valid, reason = _validate(canonical, value_num, unit_str)

        results.append({
            "canonical_name": canonical,
            "raw_label":      tok,
            "value":          value_num,
            "unit":           unit_str,
            "ref_range":      ref_str,
            "raw_value":      raw_value,
            "valid":          valid,
            "reject_reason":  "" if valid else reason,
        })

        i = j

    return results


# ── ERL format conversion ─────────────────────────────────────────────────────

_CANONICAL_TO_ERL: dict[str, str] = {
    "Hémoglobine":      "NFS",
    "Hématies":         "NFS",
    "Hématocrite":      "NFS",
    "Leucocytes":       "NFS",
    "Neutrophiles":     "NFS",
    "Plaquettes":       "NFS",
    "Créatinine":       "Créatinine",
    "DFG CKD-EPI":      "Créatinine",
    "Ferritine":        "Bilan martial",
    "ASAT":             "Bilan hépatique",
    "ALAT":             "Bilan hépatique",
    "Glycémie":         "Glycémie",
    "Sodium":           "Ionogramme",
    "Potassium":        "Ionogramme",
    "CRP":              "CRP",
    "PSA":              "PSA total",
    "Triglycérides":    "Bilan lipidique",
    "Cholestérol total":"Bilan lipidique",
    "HDL":              "Bilan lipidique",
    "LDL":              "Bilan lipidique",
    "Non-HDL":          "Bilan lipidique",
}

_REFERENCE_RANGES_STATUS: dict[str, tuple[float, float]] = {
    "Hémoglobine":      (13.4, 16.7),
    "Hématies":         (4.39, 5.68),
    "Hématocrite":      (39,   49),
    "VGM":              (80.2, 95.0),
    "TCMH":             (27.2, 32.8),
    "CCMH":             (32.4, 36.3),
    "Leucocytes":       (4.1,  10.8),
    "Neutrophiles":     (1.8,  6.8),
    "Éosinophiles":     (0.05, 0.56),
    "Basophiles":       (0.0,  0.09),
    "Lymphocytes":      (1.3,  3.8),
    "Monocytes":        (0.23, 0.74),
    "Plaquettes":       (171,  397),
    "Sodium":           (136,  145),
    "Potassium":        (3.5,  5.5),
    "Créatinine":       (64.5, 104.3),
    "DFG CKD-EPI":      (90,   200),
    "Ferritine":        (22,   322),
    "ASAT":             (0,    40),
    "ALAT":             (0,    40),
    "Glycémie":         (0.70, 1.10),
    # Lipides (g/L, France baseline)
    "Triglycérides":    (0.0,  1.50),
    "Cholestérol total":(0.0,  1.90),
    "HDL":              (0.40, 0.80),
    "Non-HDL":          (0.0,  1.50),
    "LDL":              (0.0,  1.60),
    # Marqueurs tumoraux
    "PSA":              (0.0,  3.00),
    "CRP":              (0,    5),
}


def _get_status(canonical: str, value: float) -> str:
    ref = _REFERENCE_RANGES_STATUS.get(canonical)
    if ref is None:
        return "inconnu"
    lo, hi = ref
    if value < lo:
        return "bas"
    if value > hi:
        return "élevé"
    return "normal"


def to_erl_format(parsed_results: list[dict]) -> dict[str, str]:
    """
    Convert parsed/confirmed results to ERL dict: {erl_test_name: status_string}.
    Accepts both new parser format and routes confirmed_results format.
    """
    erl = {}
    for r in parsed_results:
        # Support both formats:
        # new parser:  canonical_name, value (float)
        # routes confirmed: canonical_name, value (float or str), status (str)
        name = r.get("canonical_name")
        if not name:
            continue

        erl_name = _CANONICAL_TO_ERL.get(name)
        if not erl_name:
            continue

        # Try to get status directly (routes confirmed_results already has it)
        status = r.get("status", "")
        if status in ("élevé", "bas", "normal", "positif", "négatif"):
            erl[erl_name] = status
            continue

        # Compute from value
        val = r.get("value")
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        erl[erl_name] = _get_status(name, val)

    return erl


# ── Legacy compatibility ──────────────────────────────────────────────────────

def _to_routes_format(parse_result: dict) -> list[dict]:
    """
    Convert new parse result dict → old list[dict] format expected by routes.py.
    Fields: raw_name, canonical_name, value, raw_value, unit, status, recognized
    """
    out = []
    for r in parse_result.get("recognised_valid", []) + parse_result.get("needs_review", []):
        name = r["canonical_name"]
        val = r["value"]
        status = _get_status(name, val) if val is not None else "inconnu"
        out.append({
            "raw_name":      r.get("raw_label", name),
            "canonical_name": name,
            "value":         val,
            "raw_value":     r.get("raw_value", str(val) if val else ""),
            "unit":          r.get("unit", ""),
            "status":        status,
            "recognized":    True,
        })
    for r in parse_result.get("rejected", []):
        out.append({
            "raw_name":      r.get("raw_label", r["canonical_name"]),
            "canonical_name": r["canonical_name"],
            "value":         r.get("value"),
            "raw_value":     r.get("raw_value", ""),
            "unit":          r.get("unit", ""),
            "status":        "inconnu",
            "recognized":    False,
        })
    return out


def parse_test_pdf(pdf_bytes: bytes) -> list[dict]:
    """Entry point for routes.py — returns list[dict] in legacy format."""
    result = _parse_test_pdf_internal(pdf_bytes)
    return _to_routes_format(result)


def parse_test_text(text: str) -> list[dict]:
    """Entry point for routes.py — returns list[dict] in legacy format."""
    result = _parse_test_text_internal(text)
    return _to_routes_format(result)


def parse_test_image(image_bytes: bytes) -> list[dict]:
    """OCR fallback — requires pytesseract."""
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang="fra+eng")
        result = _parse_test_text_internal(text)
        return _to_routes_format(result)
    except ImportError:
        return []
    except Exception as e:
        logger.error(f"Image OCR error: {e}")
        return []


# ── Internal functions (full dict output) ────────────────────────────────────

def _parse_test_pdf_internal(pdf_bytes: bytes) -> dict:
    """Internal — returns full dict with recognised_valid/rejected/needs_review."""
    try:
        import fitz
    except ImportError:
        logger.error("pymupdf not installed")
        return {"recognised_valid": [], "rejected": [], "needs_review": [], "error": "pymupdf_missing"}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        logger.error(f"PDF read error: {e}")
        return {"recognised_valid": [], "rejected": [], "needs_review": [], "error": str(e)}
    return _parse_test_text_internal(full_text)


def _parse_test_text_internal(text: str) -> dict:
    """Internal — parse text, return full dict."""
    tokens = _extract_tokens(text)
    raw_results = _parse_biogroup_tokens(tokens)
    recognised_valid = []
    rejected = []
    needs_review = []
    seen = set()
    for r in raw_results:
        name = r["canonical_name"]
        if name in seen:
            continue
        seen.add(name)
        if not r["valid"]:
            rejected.append(r)
        elif r["reject_reason"] == "no_range_check":
            needs_review.append(r)
        else:
            recognised_valid.append(r)
    return {"recognised_valid": recognised_valid, "rejected": rejected, "needs_review": needs_review}