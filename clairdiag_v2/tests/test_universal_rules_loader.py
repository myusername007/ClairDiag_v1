"""
ClairDiag v2.0 — Tests UniversalRulesLoader
tests/test_universal_rules_loader.py

Couvre:
- Chargement JSON (required + optional)
- Validation meta
- Checksum computation
- versions()
- get() / get_rules()
- Fallback gracieux si fichier manquant
- Fichiers required vs optional
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from universal_rules_loader import UniversalRulesLoader, REQUIRED_META_FIELDS


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_valid_json(name: str, rules_key: str = "rules", rules_count: int = 2) -> dict:
    return {
        "meta": {
            "schema_version": "v2.0",
            "rule_file_version": "2026-test-001",
            "validation_status": "test",
            "last_modified": "2026-01-01T00:00:00Z",
            "modified_by": "test",
            "checksum": "computed_at_load_time",
            "description": f"Test file for {name}",
        },
        rules_key: [{"id": f"rule_{i}"} for i in range(rules_count)],
    }


def _write_file(directory: Path, filename: str, data: dict) -> Path:
    path = directory / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def _make_full_rules_dir(tmp_dir: Path) -> Path:
    """Crée un répertoire de règles complet pour les tests."""
    # Required files
    symptoms = {
        "meta": {
            "schema_version": "v1.0", "rule_file_version": "2026-test",
            "validation_status": "test", "last_modified": "2026-01-01T00:00:00Z",
            "modified_by": "test", "checksum": "computed_at_load_time",
            "description": "Test symptoms",
        },
        "symptoms": [
            {"symptom_id": "test_sym", "body_system": "cardio", "body_zone": "thorax",
             "default_severity": "high", "triggers": ["test trigger"]},
        ],
    }
    _write_file(tmp_dir, "symptoms_rules.json", symptoms)
    _write_file(tmp_dir, "red_flags.json", {**_make_valid_json("red_flags", "red_flags"), })
    _write_file(tmp_dir, "care_pathway_rules.json", _make_valid_json("care_pathway"))

    # Optional files (skeleton)
    for name in ["analysis_rules", "specialist_mapping", "exam_interpretation_rules",
                 "reimbursement_rules", "learning_feedback_schema"]:
        _write_file(tmp_dir, f"{name}.json", _make_valid_json(name, "rules", 0))

    return tmp_dir


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_load_all_files():
    """Tous les fichiers present → success=True."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        status = loader.load()
        assert status.success is True, f"Expected success, errors: {status.errors}"
        assert len(status.failed) == 0
        print(f"  PASS — load_all_files: {len(status.loaded)} loaded")


def test_required_files_missing_fails():
    """Fichier required manquant → success=False."""
    with tempfile.TemporaryDirectory() as tmp:
        # Créer seulement 2 sur 3 required
        rules_dir = Path(tmp)
        _write_file(rules_dir, "symptoms_rules.json", _make_valid_json("symptoms", "symptoms", 1))
        _write_file(rules_dir, "red_flags.json", _make_valid_json("red_flags", "red_flags"))
        # care_pathway_rules.json manquant intentionnellement

        loader = UniversalRulesLoader(rules_dir)
        status = loader.load()
        assert status.success is False
        assert "care_pathway_rules.json" in status.failed
        print(f"  PASS — required_missing → success=False, failed={status.failed}")


def test_optional_files_missing_ok():
    """Fichiers optional manquants → success=True (warnings seulement)."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = Path(tmp)
        symptoms = {
            "meta": {"schema_version": "v1.0", "rule_file_version": "test",
                     "validation_status": "test", "last_modified": "2026-01-01T00:00:00Z",
                     "modified_by": "test", "checksum": "computed_at_load_time", "description": "test"},
            "symptoms": [],
        }
        _write_file(rules_dir, "symptoms_rules.json", symptoms)
        _write_file(rules_dir, "red_flags.json", _make_valid_json("rf", "red_flags"))
        _write_file(rules_dir, "care_pathway_rules.json", _make_valid_json("cp"))
        # Optionals absents

        loader = UniversalRulesLoader(rules_dir)
        status = loader.load()
        assert status.success is True
        assert len(status.warnings) > 0
        print(f"  PASS — optional_missing → success=True, warnings={len(status.warnings)}")


def test_invalid_json_fails_gracefully():
    """JSON invalide → pas de crash, load_error set."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = Path(tmp)
        # Écrire du JSON invalide pour un required
        bad_path = rules_dir / "symptoms_rules.json"
        bad_path.write_text("{ invalid json {{{{", encoding="utf-8")
        _write_file(rules_dir, "red_flags.json", _make_valid_json("rf", "red_flags"))
        _write_file(rules_dir, "care_pathway_rules.json", _make_valid_json("cp"))

        loader = UniversalRulesLoader(rules_dir)
        status = loader.load()
        assert status.success is False
        assert "symptoms_rules.json" in status.failed
        print(f"  PASS — invalid_json → graceful failure, failed={status.failed}")


def test_checksum_computed():
    """Checksum calculé et différent de 'computed_at_load_time'."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        loader.load()
        cs = loader.checksum("symptoms_rules")
        assert cs is not None
        assert cs != "computed_at_load_time"
        assert len(cs) == 64  # SHA256 hex
        print(f"  PASS — checksum computed: {cs[:16]}...")


def test_checksum_deterministic():
    """Même fichier → même checksum à chaque load."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader1 = UniversalRulesLoader.__new__(UniversalRulesLoader)
        loader1.rules_dir = rules_dir
        loader1._files = {}
        loader1._loaded = False
        loader1.load()
        cs1 = loader1.checksum("symptoms_rules")

        loader2 = UniversalRulesLoader.__new__(UniversalRulesLoader)
        loader2.rules_dir = rules_dir
        loader2._files = {}
        loader2._loaded = False
        loader2.load()
        cs2 = loader2.checksum("symptoms_rules")

        assert cs1 == cs2
        print(f"  PASS — checksum deterministic: {cs1[:16]}...")


def test_versions_returns_all_files():
    """versions() retourne un dict avec toutes les entrées."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        loader.load()
        versions = loader.versions()
        assert "symptoms_rules" in versions
        assert "red_flags" in versions
        assert "care_pathway_rules" in versions
        # Vérifier structure
        for key, info in versions.items():
            assert "loaded" in info
            assert "version" in info
            assert "checksum" in info
        print(f"  PASS — versions() returns {len(versions)} entries")


def test_get_returns_data():
    """get() retourne les données du fichier."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        loader.load()
        data = loader.get("symptoms_rules")
        assert data is not None
        assert "symptoms" in data
        assert "meta" in data
        print(f"  PASS — get('symptoms_rules') returns data with {len(data['symptoms'])} symptoms")


def test_get_unknown_returns_none():
    """get() pour fichier inconnu → None."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        loader.load()
        result = loader.get("nonexistent_file")
        assert result is None
        print(f"  PASS — get('nonexistent') → None")


def test_get_rules_returns_list():
    """get_rules() retourne une liste."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        loader.load()
        rules = loader.get_rules("red_flags", "red_flags")
        assert isinstance(rules, list)
        print(f"  PASS — get_rules('red_flags') returns list of {len(rules)} items")


def test_is_ready_after_load():
    """is_ready() True après load réussi."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        assert not loader.is_ready()
        loader.load()
        assert loader.is_ready()
        print(f"  PASS — is_ready() False before load, True after")


def test_meta_validation_missing_field():
    """Meta avec champ manquant → warning mais chargement continue."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = Path(tmp)
        # Fichier avec meta incomplet (manque 'description')
        bad_meta = {
            "meta": {
                "schema_version": "v1.0",
                "rule_file_version": "test",
                "validation_status": "test",
                "last_modified": "2026-01-01T00:00:00Z",
                "modified_by": "test",
                "checksum": "computed_at_load_time",
                # description manquant
            },
            "symptoms": [],
        }
        _write_file(rules_dir, "symptoms_rules.json", bad_meta)
        _write_file(rules_dir, "red_flags.json", _make_valid_json("rf", "red_flags"))
        _write_file(rules_dir, "care_pathway_rules.json", _make_valid_json("cp"))

        loader = UniversalRulesLoader(rules_dir)
        status = loader.load()
        # Le fichier est chargé malgré meta invalide (graceful)
        assert loader.get("symptoms_rules") is not None
        print(f"  PASS — meta_missing_field → loaded anyway, meta_valid=False")


def test_get_meta():
    """get_meta() retourne le bloc meta."""
    with tempfile.TemporaryDirectory() as tmp:
        rules_dir = _make_full_rules_dir(Path(tmp))
        loader = UniversalRulesLoader(rules_dir)
        loader.load()
        meta = loader.get_meta("symptoms_rules")
        assert meta is not None
        assert "schema_version" in meta
        # Checksum doit être mis à jour (non 'computed_at_load_time')
        assert meta.get("checksum") != "computed_at_load_time"
        print(f"  PASS — get_meta() returns meta with checksum updated")


def test_real_rules_dir():
    """Test avec les vrais fichiers JSON du projet."""
    real_rules_dir = Path(__file__).parent.parent / "rules"
    if not real_rules_dir.exists():
        print(f"  SKIP — real rules dir not found at {real_rules_dir}")
        return

    loader = UniversalRulesLoader(real_rules_dir)
    status = loader.load()
    assert status.success is True, f"Real rules load failed: {status.errors}"

    # Vérifier symptoms
    symptoms = loader.get_rules("symptoms_rules", "symptoms")
    assert len(symptoms) > 0

    # Vérifier red_flags
    red_flags = loader.get_rules("red_flags", "red_flags")
    assert len(red_flags) > 0

    # Vérifier care_pathway
    cp_data = loader.get("care_pathway_rules")
    assert cp_data is not None
    assert len(cp_data.get("rules", [])) > 0

    versions = loader.versions()
    print(f"  PASS — real_rules_dir: symptoms={len(symptoms)}, "
          f"red_flags={len(red_flags)}, "
          f"care_pathway={len(cp_data.get('rules', []))}")
    for k, v in versions.items():
        status_str = "OK" if v["loaded"] else "FAIL"
        print(f"    [{status_str}] {k}: v={v['version']} cs={v['checksum']}")


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("Load all files", test_load_all_files),
        ("Required missing → fails", test_required_files_missing_fails),
        ("Optional missing → ok", test_optional_files_missing_ok),
        ("Invalid JSON → graceful", test_invalid_json_fails_gracefully),
        ("Checksum computed", test_checksum_computed),
        ("Checksum deterministic", test_checksum_deterministic),
        ("versions() returns all", test_versions_returns_all_files),
        ("get() returns data", test_get_returns_data),
        ("get() unknown → None", test_get_unknown_returns_none),
        ("get_rules() returns list", test_get_rules_returns_list),
        ("is_ready() lifecycle", test_is_ready_after_load),
        ("Meta missing field graceful", test_meta_validation_missing_field),
        ("get_meta() updated checksum", test_get_meta),
        ("Real rules dir", test_real_rules_dir),
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print(f"UniversalRulesLoader — Test suite")
    print(f"{'='*60}\n")

    for name, fn in tests:
        try:
            print(f"Test: {name}")
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL — {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR — {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} PASS / {failed} FAIL / {passed + failed} TOTAL")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
