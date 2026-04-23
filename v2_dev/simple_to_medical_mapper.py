"""
ClairDiag v2 — Simple-to-Medical Mapper (TASK #014)
Converts patient free-text (FR) → normalized v2 symptom keys.

RULES:
- Rule-based only, no ML
- Voice: pluggable stub (skip if ASR not configured)
- Low confidence → flag, do NOT over-infer
"""

from __future__ import annotations
import re
from typing import Optional

# ── NORMALIZATION ─────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = text.lower()
    for src, dst in {
        'é':'e','è':'e','ê':'e','ë':'e',
        'à':'a','â':'a','ä':'a',
        'î':'i','ï':'i',
        'ô':'o','ö':'o',
        'ù':'u','û':'u','ü':'u',
        'ç':'c','œ':'oe','æ':'ae',
    }.items():
        text = text.replace(src, dst)
    return text


# ── SIMPLE LANGUAGE RULES (FR → v2 keys) ─────────────────────────────────────
# Format: (pattern, key, weight)
# weight: 2 = specific, 1 = generic

_SIMPLE_RULES: list[tuple[str, str, int]] = [
    # Thoracique
    ("serre.*poitrine|oppression.*poitrine|poitrine.*serre",   "douleur_thoracique_oppressive", 2),
    ("mal.*poitrine|douleur.*poitrine|poitrine.*fait mal",     "douleur_thoracique",            2),
    ("brule.*poitrine|brulure.*poitrine",                      "douleur_thoracique",            2),
    ("douleur.*dos|mal.*dos",                                  "douleur_thoracique",            1),
    # Respiratoire
    ("souffle.*court|manque.*souffle|essouffl",                "dyspnee_effort",                2),
    ("respir.*mal|mal.*respir|du mal a respir",                "dyspnee",                       2),
    ("siffle.*respir|respir.*siffle",                          "sifflement_respiratoire",       2),
    ("touss",                                                  "toux_seche",                    1),
    ("crache.*sang|sang.*crache",                              "hemoptysie",                    2),
    # Cardiaque
    ("coeur.*bat.*vite|palpitation|coeur.*s.emballe",          "palpitations",                  2),
    ("sueur.*froid|transpir.*froid|froid.*sueur",              "sueur_froide",                  2),
    ("evanoui|perdu.*connaissance|tombe.*dans.*les.*pommes",   "syncope",                       2),
    # Neurologique
    ("tourne.*tete|tete.*tourne|vertige|equilibre",            "vertige_positionnel",           2),
    ("mal.*tete|tete.*fait mal|cephalee|migraine",             "cephalee_pulsatile",            1),
    ("mal.*tete.*brutal|tete.*explose|pire.*mal.*tete",        "cephalee_intense_brutale",      2),
    ("bras.*faible|jambe.*faible|cote.*faible|faiblesse",      "faiblesse_unilaterale",         2),
    ("parle.*mal|mot.*sorti|bafouille|elocution",              "trouble_parole",                2),
    ("vue.*trouble|vision.*floue|voit.*mal",                   "trouble_vision_brutal",         2),
    ("nuque.*raide|raideur.*nuque",                            "raideur_nuque",                 2),
    ("confus|perdu|desorientation",                            "confusion",                     2),
    ("engourdi|formicament|fourmillement",                     "engourdissement_membre",        2),
    # Digestif
    ("mal.*ventre|ventre.*fait mal|douleur.*ventre|abdomen",   "douleur_abdominale",            1),
    ("mal.*estomac|estomac.*fait mal|epigastre",               "douleur_epigastrique",          2),
    ("envie.*vomir|nausee|coeur.*leve|mal.*coeur",             "nausees",                       2),
    ("vomi|a vomi|vomissement",                                "vomissements",                  2),
    ("diarrhee|selles.*liquide|ventre.*court",                 "diarrhee",                      2),
    ("constip",                                                "constipation",                  2),
    # Général / Infectieux
    ("fievre|temperature|chaud|38|39|40",                      "fievre_moderee",                1),
    ("tres.*fatigu|epuis|plus.*force|fatigue.*intense",        "fatigue_intense",               2),
    ("fatigu|asthenie|sans.*energie",                          "fatigue",                       1),
    ("frisson",                                                "frissons",                      2),
    ("mal.*partout|courbature|myalgie",                        "myalgies_intenses",             2),
    ("mange.*plus|plus.*appetit|appetit.*coupe",               "perte_appetit",                 2),
    # Anxiété
    ("angoisse|anxieux|panique|stress.*intense",               "anxiete_intense",               2),
    # Oedème
    ("cheville.*gonfle|jambe.*gonfle|gonflement",              "oedeme_membre_inferieur",       2),
    ("mollet.*douloureux|mollet.*gonfl",                       "oedeme_membre_inferieur",       2),
]

# Negation prefixes — skip symptom if negated
_NEGATION_PATTERNS = (
    "pas de ", "pas d'", "sans ", "aucun ", "aucune ",
    "ne pas ", "n'ai pas", "jamais ",
)


def _is_negated(fragment: str, text_norm: str) -> bool:
    """Check if fragment appears after a negation in the text."""
    for neg in _NEGATION_PATTERNS:
        if neg + fragment[:8] in text_norm:
            return True
    return False


# ── VOICE STUB ────────────────────────────────────────────────────────────────

def transcribe_audio(audio_base64: str) -> Optional[str]:
    """
    Pluggable ASR stub.
    Replace with real ASR (Whisper, Google STT, etc.) when configured.
    Returns None if not configured.
    """
    # TODO: implement when ASR service is configured
    return None


# ── MAPPER ────────────────────────────────────────────────────────────────────

def map_free_text(free_text: str) -> dict:
    """
    Map French free-text to v2 normalized symptom keys.

    Returns:
    {
        "symptoms_normalized": [...],
        "mapping_confidence": "high|medium|low",
        "unmapped_fragments": [...],
        "free_text_used": true
    }
    """
    if not free_text or not free_text.strip():
        return {
            "symptoms_normalized":  [],
            "mapping_confidence":   "low",
            "unmapped_fragments":   [],
            "free_text_used":       True,
        }

    text_norm = _normalize(free_text)
    mapped:   list[str] = []
    seen:     set[str]  = set()
    hit_count = 0
    total_weight = 0

    for pattern, key, weight in _SIMPLE_RULES:
        try:
            if re.search(pattern, text_norm):
                if key not in seen:
                    mapped.append(key)
                    seen.add(key)
                    hit_count  += 1
                    total_weight += weight
        except re.error:
            if pattern in text_norm and key not in seen:
                mapped.append(key)
                seen.add(key)
                hit_count += 1
                total_weight += weight

    # Confidence scoring
    words = len(free_text.split())
    if hit_count == 0:
        confidence = "low"
    elif total_weight >= 4 and hit_count >= 2:
        confidence = "high"
    elif hit_count >= 1 and words >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    # Unmapped fragments — sentences with no match
    sentences = re.split(r'[.,;!?]|\bet\b|\bou\b', free_text)
    unmapped  = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        sent_norm = _normalize(sent)
        matched = False
        for p, _, _ in _SIMPLE_RULES:
            try:
                if re.search(p, sent_norm):
                    matched = True
                    break
            except re.error:
                if p in sent_norm:
                    matched = True
                    break
        if not matched and len(sent.split()) >= 2:
            unmapped.append(sent)

    return {
        "symptoms_normalized":  mapped,
        "mapping_confidence":   confidence,
        "unmapped_fragments":   unmapped,
        "free_text_used":       True,
    }


def map_input(
    free_text: Optional[str] = None,
    audio_base64: Optional[str] = None,
) -> dict:
    """
    Main entry point.
    Accepts free_text and/or audio_base64.
    Audio is transcribed first if ASR is configured.
    """
    text = free_text or ""

    # Voice path
    audio_transcribed = False
    if audio_base64:
        transcribed = transcribe_audio(audio_base64)
        if transcribed:
            text = transcribed
            audio_transcribed = True

    result = map_free_text(text)
    result["audio_transcribed"] = audio_transcribed
    return result