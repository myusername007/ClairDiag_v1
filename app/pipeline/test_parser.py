# ── Test Results Parser — ClairDiag v2.5 ──────────────────────────────────────
# Парсит результаты анализов из текста, PDF, изображений
# Нормализует названия, значения, единицы, статусы
# ─────────────────────────────────────────────────────────────────────────────

import re
import logging
import base64
from typing import Optional

logger = logging.getLogger("clairdiag.test_parser")


# ── Reference ranges (France baseline) ────────────────────────────────────────

REFERENCE_RANGES: dict[str, dict] = {
    "CRP":         {"unit": "mg/L",    "low": 0,   "high": 5,     "type": "numeric"},
    "NFS":         {"unit": "G/L",     "low": 4.0, "high": 10.0,  "type": "numeric"},
    "leucocytes":  {"unit": "G/L",     "low": 4.0, "high": 10.0,  "type": "numeric"},
    "hémoglobine": {"unit": "g/dL",    "low": 12,  "high": 17,    "type": "numeric"},
    "plaquettes":  {"unit": "G/L",     "low": 150, "high": 400,   "type": "numeric"},
    "ferritine":   {"unit": "ng/mL",   "low": 20,  "high": 300,   "type": "numeric"},
    "troponine":   {"unit": "ng/L",    "low": 0,   "high": 14,    "type": "numeric"},
    "D-dimères":   {"unit": "ng/mL",   "low": 0,   "high": 500,   "type": "numeric"},
    "BNP":         {"unit": "pg/mL",   "low": 0,   "high": 100,   "type": "numeric"},
    "créatinine":  {"unit": "µmol/L",  "low": 60,  "high": 110,   "type": "numeric"},
    "ALT":         {"unit": "UI/L",    "low": 0,   "high": 40,    "type": "numeric"},
    "AST":         {"unit": "UI/L",    "low": 0,   "high": 40,    "type": "numeric"},
    "TSH":         {"unit": "mUI/L",   "low": 0.4, "high": 4.0,   "type": "numeric"},
    "glycémie":    {"unit": "g/L",     "low": 0.7, "high": 1.1,   "type": "numeric"},
    "ionogramme Na": {"unit": "mmol/L","low": 136, "high": 145,   "type": "numeric"},
    "ionogramme K":  {"unit": "mmol/L","low": 3.5, "high": 5.0,   "type": "numeric"},
    "procalcitonine":{"unit": "ng/mL", "low": 0,   "high": 0.5,   "type": "numeric"},
    "gaz du sang pH":{"unit": "",      "low": 7.35,"high": 7.45,  "type": "numeric"},
    # Qualitative tests
    "C. difficile":       {"type": "qualitative"},
    "coproculture":       {"type": "qualitative"},
    "hémocultures":       {"type": "qualitative"},
    "test Strep A":       {"type": "qualitative"},
    "test grippe":        {"type": "qualitative"},
    "H. pylori":          {"type": "qualitative"},
    # Imaging
    "ECG":                {"type": "qualitative"},
    "Rx thorax":          {"type": "qualitative"},
    "scanner thoracique": {"type": "qualitative"},
    "spirométrie":        {"type": "qualitative"},
    "échocardiographie":  {"type": "qualitative"},
}


# ── Aliases for test name normalization ─────────────────────────────────────

TEST_ALIASES: dict[str, str] = {
    # CRP
    "crp": "CRP", "c-reactive protein": "CRP", "protéine c réactive": "CRP",
    "proteine c reactive": "CRP", "c réactive": "CRP",
    # NFS / Blood count
    "nfs": "NFS", "numération formule sanguine": "NFS", "hémogramme": "NFS",
    "hemogramme": "NFS", "blood count": "NFS", "fsc": "NFS",
    "globules blancs": "leucocytes", "gb": "leucocytes", "wbc": "leucocytes",
    "leucocytes": "leucocytes", "leuco": "leucocytes",
    "hémoglobine": "hémoglobine", "hemoglobine": "hémoglobine", "hb": "hémoglobine",
    "hgb": "hémoglobine",
    "plaquettes": "plaquettes", "plt": "plaquettes", "thrombocytes": "plaquettes",
    # Ferritine
    "ferritine": "ferritine", "fer sérique": "ferritine",
    # Troponine
    "troponine": "troponine", "trop": "troponine", "troponine i": "troponine",
    "troponine t": "troponine", "tnl": "troponine",
    # D-dimères
    "d-dimères": "D-dimères", "d dimères": "D-dimères", "d-dimeres": "D-dimères",
    "d dimeres": "D-dimères", "ddimeres": "D-dimères",
    # BNP
    "bnp": "BNP", "nt-probnp": "BNP", "pro-bnp": "BNP",
    # Créatinine
    "créatinine": "créatinine", "creatinine": "créatinine", "créat": "créatinine",
    "creat": "créatinine",
    # ALT/AST
    "alt": "ALT", "alat": "ALT", "sgpt": "ALT", "alanine aminotransférase": "ALT",
    "ast": "AST", "asat": "AST", "sgot": "AST",
    "transaminases": "ALT",  # maps to ALT as primary
    # TSH
    "tsh": "TSH", "thyréostimuline": "TSH",
    # Glycémie
    "glycémie": "glycémie", "glycemie": "glycémie", "glucose": "glycémie",
    "glycémie à jeun": "glycémie",
    # Ionogramme
    "sodium": "ionogramme Na", "na": "ionogramme Na", "na+": "ionogramme Na",
    "potassium": "ionogramme K", "k": "ionogramme K", "k+": "ionogramme K",
    "ionogramme": "ionogramme Na",
    # Procalcitonine
    "procalcitonine": "procalcitonine", "pct": "procalcitonine",
    # Gaz du sang
    "gaz du sang": "gaz du sang pH", "ph": "gaz du sang pH",
    "gazométrie": "gaz du sang pH",
    # C. difficile
    "c. difficile": "C. difficile", "c difficile": "C. difficile",
    "clostridium": "C. difficile", "clostridioides": "C. difficile",
    "test c. difficile": "C. difficile", "recherche c. difficile": "C. difficile",
    # Coproculture
    "coproculture": "coproculture", "copro": "coproculture",
    "selles": "coproculture",
    # Hémocultures
    "hémocultures": "hémocultures", "hemocultures": "hémocultures",
    "hémoculture": "hémocultures",
    # Strep A
    "strep a": "test Strep A", "test rapide strep a": "test Strep A",
    "tdr strep": "test Strep A", "streptatest": "test Strep A",
    # Grippe
    "test grippe": "test grippe", "test rapide grippe": "test grippe",
    "grippe rapide": "test grippe",
    # H. pylori
    "h. pylori": "H. pylori", "helicobacter": "H. pylori",
    "helicobacter pylori": "H. pylori", "test helicobacter": "H. pylori",
    # ECG
    "ecg": "ECG", "électrocardiogramme": "ECG", "electrocardiogramme": "ECG",
    # Rx thorax
    "rx thorax": "Rx thorax", "radiographie thoracique": "Rx thorax",
    "radio thorax": "Rx thorax", "radiographie pulmonaire": "Rx thorax",
    "radio pulmonaire": "Rx thorax",
    # Scanner
    "scanner thoracique": "scanner thoracique", "tdm thorax": "scanner thoracique",
    "angio-tdm": "scanner thoracique", "ct thorax": "scanner thoracique",
    # Spirométrie
    "spirométrie": "spirométrie", "spirometrie": "spirométrie",
    "efr": "spirométrie",
    # Échocardiographie
    "échocardiographie": "échocardiographie", "echocardiographie": "échocardiographie",
    "écho cœur": "échocardiographie", "echo coeur": "échocardiographie",
    "ett": "échocardiographie",
}


# ── Positive/Negative value keywords ──────────────────────────────────────────

_POSITIVE_KW = {
    "positif", "positive", "présent", "présente", "present",
    "détecté", "detecte", "detected", "anormal", "abnormal",
    "pathologique", "infiltrat", "opacité", "épanchement",
    "positivo", "pos", "+", "oui", "yes",
}

_NEGATIVE_KW = {
    "négatif", "negative", "négatif", "absent", "absente",
    "normal", "normale", "ras", "sans particularité",
    "négatif", "neg", "non", "no", "−", "negatif",
    "sans anomalie", "aucune anomalie",
}


def normalize_test_name(raw_name: str) -> Optional[str]:
    """Normalize a test name to canonical form."""
    key = raw_name.strip().lower()
    # Direct alias match
    if key in TEST_ALIASES:
        return TEST_ALIASES[key]
    # Partial match
    for alias, canonical in TEST_ALIASES.items():
        if alias in key or key in alias:
            return canonical
    return None


def determine_status(
    canonical_name: str,
    value: Optional[float],
    raw_value: str,
) -> str:
    """Determine status: normal / élevé / bas / positif / négatif / inconnu."""
    ref = REFERENCE_RANGES.get(canonical_name)
    if not ref:
        return "inconnu"

    if ref["type"] == "qualitative":
        raw_lower = raw_value.strip().lower()
        if any(kw in raw_lower for kw in _POSITIVE_KW):
            return "positif"
        if any(kw in raw_lower for kw in _NEGATIVE_KW):
            return "négatif"
        return "inconnu"

    # Numeric
    if value is None:
        return "inconnu"
    if value < ref["low"]:
        return "bas"
    if value > ref["high"]:
        return "élevé"
    return "normal"


def get_unit(canonical_name: str) -> str:
    """Get expected unit for a test."""
    ref = REFERENCE_RANGES.get(canonical_name, {})
    return ref.get("unit", "")


# ── Text parser ───────────────────────────────────────────────────────────────

_QUAL_KEYWORDS = [
    "positif", "positive", "négatif", "negatif", "negative",
    "normal", "normale", "anormal", "anormale",
    "présent", "presente", "absent", "absente",
    "détecté", "detecte", "infiltrat", "opacité",
    "pathologique", "ras", "sans anomalie",
]


def parse_test_text(text: str) -> list[dict]:
    """Parse free-text test results into structured data."""
    results = []
    seen = set()

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or len(line) < 2:
            continue

        parsed = _parse_single_line(line)
        if parsed:
            key = parsed["canonical_name"] or parsed["raw_name"]
            if key not in seen:
                seen.add(key)
                results.append(parsed)

    return results


def _parse_single_line(line: str) -> Optional[dict]:
    """Parse a single line as a test result using split-based approach."""

    # Try "name : value" or "name = value"
    for sep in [":", "="]:
        if sep in line:
            parts = line.split(sep, 1)
            name_part = parts[0].strip()
            value_part = parts[1].strip() if len(parts) > 1 else ""
            result = _try_parse(name_part, value_part)
            if result:
                return result

    # No separator — try to split at first digit
    m = re.search(r'(\d)', line)
    if m:
        idx = m.start()
        name_part = line[:idx].strip()
        value_part = line[idx:].strip()
        if name_part:
            result = _try_parse(name_part, value_part)
            if result:
                return result

    # Try qualitative: "name keyword"
    lower = line.lower().strip()
    for kw in _QUAL_KEYWORDS:
        if kw in lower:
            idx = lower.find(kw)
            name_part = line[:idx].strip().rstrip(":= ")
            if name_part:
                canonical = normalize_test_name(name_part)
                if canonical:
                    status = determine_status(canonical, None, kw)
                    return {
                        "raw_name": name_part,
                        "canonical_name": canonical,
                        "value": None,
                        "raw_value": kw,
                        "unit": "",
                        "status": status,
                        "recognized": True,
                    }

    # Last resort: whole line as test name
    canonical = normalize_test_name(line.strip())
    if canonical:
        return {
            "raw_name": line.strip(),
            "canonical_name": canonical,
            "value": None,
            "raw_value": "",
            "unit": get_unit(canonical),
            "status": "inconnu",
            "recognized": True,
        }

    return None


def _try_parse(name_part: str, value_part: str) -> Optional[dict]:
    """Try to parse name + value parts into a test result."""
    canonical = normalize_test_name(name_part)
    if not canonical:
        return None

    # Extract number
    nums = re.findall(r'[\d]+[.,]?\d*', value_part)
    value = None
    if nums:
        try:
            value = float(nums[0].replace(",", "."))
        except ValueError:
            pass

    # Extract unit (letters after number)
    unit = ""
    if nums:
        after_num = value_part[value_part.find(nums[0]) + len(nums[0]):].strip()
        um = re.match(r'[A-Za-z\u00c0-\u00ffµ/%°·]+', after_num)
        unit = um.group() if um else ""
    if not unit:
        unit = get_unit(canonical)

    status = determine_status(canonical, value, value_part)

    return {
        "raw_name": name_part,
        "canonical_name": canonical,
        "value": value,
        "raw_value": value_part,
        "unit": unit,
        "status": status,
        "recognized": True,
    }


    return None


# ── PDF parser ────────────────────────────────────────────────────────────────

def parse_test_pdf(pdf_bytes: bytes) -> list[dict]:
    """Extract test results from PDF. Requires pymupdf (fitz)."""
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.warning("pymupdf not installed — PDF parsing unavailable")
        return []

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()
        return parse_test_text(full_text)
    except Exception as e:
        logger.error(f"PDF parse error: {e}")
        return []


# ── Image parser (OCR) ───────────────────────────────────────────────────────

def parse_test_image(image_bytes: bytes) -> list[dict]:
    """Extract test results from image via OCR. Requires pytesseract + Pillow."""
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        logger.warning("pytesseract/Pillow not installed — image OCR unavailable")
        return []

    try:
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang="fra+eng")
        return parse_test_text(text)
    except Exception as e:
        logger.error(f"Image OCR error: {e}")
        return []


# ── Convert parsed results to ERL format ──────────────────────────────────────

# Mapping from canonical test names to ERL-compatible test names
_CANONICAL_TO_ERL: dict[str, str] = {
    "CRP": "CRP",
    "NFS": "NFS",
    "leucocytes": "NFS",
    "hémoglobine": "NFS",
    "plaquettes": "NFS",
    "troponine": "Troponine",
    "D-dimères": "D-dimères",
    "BNP": "BNP",
    "créatinine": "Créatinine",
    "ALT": "Bilan hépatique",
    "AST": "Bilan hépatique",
    "TSH": "TSH",
    "glycémie": "Glycémie",
    "ferritine": "Bilan martial",
    "procalcitonine": "Procalcitonine",
    "C. difficile": "Test C. difficile",
    "coproculture": "Coproculture",
    "hémocultures": "Hémocultures",
    "test Strep A": "Test rapide Strep A",
    "test grippe": "Test rapide grippe",
    "H. pylori": "Test Helicobacter pylori",
    "ECG": "ECG",
    "Rx thorax": "Radiographie pulmonaire",
    "scanner thoracique": "Scanner thoracique",
    "spirométrie": "Spirométrie",
    "échocardiographie": "Échocardiographie",
}

_STATUS_TO_ERL_VALUE: dict[str, str] = {
    "élevé":    "élevé",
    "bas":      "bas",
    "normal":   "normal",
    "positif":  "positif",
    "négatif":  "négatif",
    "inconnu":  "normal",  # safe fallback
}


def to_erl_format(parsed_results: list[dict]) -> dict[str, str]:
    """Convert parsed test results to ERL-compatible format: {test_name: value_string}."""
    erl = {}
    for r in parsed_results:
        if not r.get("recognized") or not r.get("canonical_name"):
            continue
        erl_name = _CANONICAL_TO_ERL.get(r["canonical_name"])
        if not erl_name:
            continue
        erl_value = _STATUS_TO_ERL_VALUE.get(r["status"], "normal")
        erl[erl_name] = erl_value
    return erl