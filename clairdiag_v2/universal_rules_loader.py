"""
ClairDiag v2.0 — UniversalRulesLoader
core/universal_rules_loader.py

Charge tous les fichiers JSON de règles au démarrage.
Valide meta, compute checksum, expose versions().
Aucune logique médicale hardcodée ici.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Règles obligatoires — doivent être présentes et valides au démarrage
REQUIRED_RULE_FILES = [
    "symptoms_rules.json",
    "red_flags.json",
    "care_pathway_rules.json",
]

# Règles optionnelles — chargées si présentes, ignorées sinon (content pending)
OPTIONAL_RULE_FILES = [
    "analysis_rules.json",
    "specialist_mapping.json",
    "exam_interpretation_rules.json",
    "reimbursement_rules.json",
    "learning_feedback_schema.json",
]

REQUIRED_META_FIELDS = [
    "schema_version",
    "rule_file_version",
    "validation_status",
    "last_modified",
    "checksum",
    "description",
]


@dataclass
class RuleFile:
    """Représente un fichier de règles chargé."""
    name: str
    path: Path
    data: Dict[str, Any]
    checksum_computed: str
    checksum_declared: str
    meta_valid: bool
    optional: bool
    load_error: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        return self.load_error is None

    @property
    def schema_version(self) -> Optional[str]:
        return self.data.get("meta", {}).get("schema_version")

    @property
    def rule_file_version(self) -> Optional[str]:
        return self.data.get("meta", {}).get("rule_file_version")

    @property
    def validation_status(self) -> Optional[str]:
        return self.data.get("meta", {}).get("validation_status")


@dataclass
class LoaderStatus:
    """Résumé du chargement de tous les fichiers de règles."""
    success: bool
    loaded: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _compute_checksum(data: Dict[str, Any]) -> str:
    """
    Calcule le checksum SHA256 du contenu JSON (sans le champ meta.checksum).
    Déterministe : tri des clés, encodage UTF-8.
    """
    data_copy = {k: v for k, v in data.items()}
    if "meta" in data_copy:
        meta_copy = {k: v for k, v in data_copy["meta"].items() if k != "checksum"}
        data_copy["meta"] = meta_copy
    serialized = json.dumps(data_copy, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_meta(meta: Dict[str, Any], filename: str) -> tuple[bool, List[str]]:
    """Valide que tous les champs meta obligatoires sont présents."""
    errors = []
    for field_name in REQUIRED_META_FIELDS:
        if field_name not in meta:
            errors.append(f"{filename}: meta.{field_name} manquant")
    return len(errors) == 0, errors


def _load_single_file(path: Path, optional: bool = False) -> RuleFile:
    """Charge et valide un seul fichier JSON de règles."""
    name = path.name
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        msg = f"{name}: fichier non trouvé à {path}"
        logger.error(msg)
        return RuleFile(
            name=name, path=path, data={}, checksum_computed="",
            checksum_declared="", meta_valid=False, optional=optional,
            load_error=msg,
        )
    except json.JSONDecodeError as e:
        msg = f"{name}: JSON invalide — {e}"
        logger.error(msg)
        return RuleFile(
            name=name, path=path, data={}, checksum_computed="",
            checksum_declared="", meta_valid=False, optional=optional,
            load_error=msg,
        )

    meta = data.get("meta", {})
    meta_valid, meta_errors = _validate_meta(meta, name)
    for err in meta_errors:
        logger.warning(err)

    checksum_computed = _compute_checksum(data)
    checksum_declared = meta.get("checksum", "computed_at_load_time")

    # Mettre à jour le checksum dans les données en mémoire
    if "meta" in data:
        data["meta"]["checksum"] = checksum_computed

    logger.info(f"Loaded: {name} | version={meta.get('rule_file_version')} | checksum={checksum_computed[:12]}...")

    return RuleFile(
        name=name,
        path=path,
        data=data,
        checksum_computed=checksum_computed,
        checksum_declared=checksum_declared,
        meta_valid=meta_valid,
        optional=optional,
    )


class UniversalRulesLoader:
    """
    Charge et expose toutes les règles JSON de ClairDiag v2.0.

    Usage:
        loader = UniversalRulesLoader(rules_dir=Path("rules/"))
        status = loader.load()
        symptoms = loader.get("symptoms_rules")["symptoms"]

    Singleton recommandé au niveau du backend (un seul chargement par process).
    """

    def __init__(self, rules_dir: Optional[Path] = None):
        if rules_dir is None:
            rules_dir = Path(__file__).parent.parent / "rules"
        self.rules_dir = rules_dir
        self._files: Dict[str, RuleFile] = {}
        self._loaded = False

    def load(self) -> LoaderStatus:
        """
        Charge tous les fichiers de règles.
        Retourne LoaderStatus avec résumé succès/échec.
        Les fichiers required qui échouent → status.success = False.
        Les fichiers optional qui échouent → warning seulement.
        """
        status = LoaderStatus(success=True)
        self._files = {}

        for filename in REQUIRED_RULE_FILES:
            path = self.rules_dir / filename
            rf = _load_single_file(path, optional=False)
            key = filename.replace(".json", "")
            self._files[key] = rf
            if rf.is_loaded:
                status.loaded.append(filename)
            else:
                status.success = False
                status.failed.append(filename)
                status.errors.append(rf.load_error or f"{filename}: erreur inconnue")

        for filename in OPTIONAL_RULE_FILES:
            path = self.rules_dir / filename
            rf = _load_single_file(path, optional=True)
            key = filename.replace(".json", "")
            self._files[key] = rf
            if rf.is_loaded:
                status.loaded.append(filename)
                # Check if file has actual content — different files use different keys
                _CONTENT_KEYS = {
                    "analysis_rules.json":             ["analyses", "modifiers"],
                    "specialist_mapping.json":         ["routing_rules", "specialists"],
                    "exam_interpretation_rules.json":  ["exam_interpretations", "modifiers"],
                    "reimbursement_rules.json":        ["exam_tariffs", "pathways", "consultation_tariffs"],
                    "learning_feedback_schema.json":   ["feedback_event_schema", "queue_routing"],
                }
                content_keys = _CONTENT_KEYS.get(filename, ["rules"])
                has_content = any(
                    len(rf.data.get(k, [])) > 0 or
                    (isinstance(rf.data.get(k), dict) and len(rf.data.get(k)) > 0)
                    for k in content_keys
                )
                if not has_content:
                    msg = f"{filename}: chargé mais contenu vide (content pending)"
                    status.warnings.append(msg)
                    logger.warning(msg)
            else:
                status.warnings.append(f"{filename}: optionnel, non chargé — {rf.load_error}")
                logger.warning(f"{filename}: optionnel, ignoré")

        self._loaded = status.success
        logger.info(
            f"UniversalRulesLoader: {len(status.loaded)} loaded, "
            f"{len(status.failed)} failed, {len(status.warnings)} warnings"
        )
        return status

    def is_ready(self) -> bool:
        """True si tous les fichiers required sont chargés."""
        return self._loaded

    def get(self, rule_name: str) -> Optional[Dict[str, Any]]:
        """
        Retourne les données d'un fichier de règles par nom (sans .json).
        Ex: loader.get("symptoms_rules") → dict complet
        Retourne None si non chargé.
        """
        rf = self._files.get(rule_name)
        if rf is None or not rf.is_loaded:
            return None
        return rf.data

    def get_rules(self, rule_name: str, key: str = "rules") -> List[Any]:
        """
        Retourne la liste de règles d'un fichier.
        Ex: loader.get_rules("red_flags", "red_flags") → list[dict]
        """
        data = self.get(rule_name)
        if data is None:
            return []
        return data.get(key, [])

    def versions(self) -> Dict[str, Dict[str, str]]:
        """
        Retourne les versions de tous les fichiers chargés.
        Format: {"symptoms_rules": {"version": "...", "schema": "...", "checksum": "..."}}
        """
        result = {}
        for key, rf in self._files.items():
            result[key] = {
                "loaded": rf.is_loaded,
                "optional": rf.optional,
                "version": rf.rule_file_version or "unknown",
                "schema_version": rf.schema_version or "unknown",
                "validation_status": rf.validation_status or "unknown",
                "checksum": rf.checksum_computed[:16] + "..." if rf.checksum_computed else "n/a",
                "error": rf.load_error or None,
            }
        return result

    def checksum(self, rule_name: str) -> Optional[str]:
        """Retourne le checksum SHA256 complet d'un fichier."""
        rf = self._files.get(rule_name)
        if rf is None:
            return None
        return rf.checksum_computed

    def get_meta(self, rule_name: str) -> Optional[Dict[str, Any]]:
        """Retourne le bloc meta d'un fichier de règles."""
        data = self.get(rule_name)
        if data is None:
            return None
        return data.get("meta", {})