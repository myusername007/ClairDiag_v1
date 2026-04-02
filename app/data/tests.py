# ── Données analyses — source unique ────────────────────────────────────────
# TEST_CATALOG est la source de vérité pour tous les modules.
# Ne pas dupliquer les prix ou valeurs ailleurs.

# Tarif consultation médecin généraliste (Assurance Maladie)
CONSULTATION_COST: int = 30

# Catalogue complet des analyses
# diagnostic_value : {diagnostic → valeur informative 0.0–1.0} pour LME (score = value / cost)
TEST_CATALOG: dict[str, dict] = {
    "NFS": {
        "cost": 20, "cost_min": 18, "cost_max": 28,
        "prescription_probability": 1.0,
        "explanation": "évalue l'inflammation et l'état général du système immunitaire",
        "diagnostic_value": {"Grippe": 0.6, "Rhinopharyngite": 0.5, "Bronchite": 0.7,
                              "Pneumonie": 0.8, "Angine": 0.6, "Anémie": 0.9, "Allergie": 0.5},
    },
    "CRP": {
        "cost": 25, "cost_min": 22, "cost_max": 32,
        "prescription_probability": 1.0,
        "explanation": "marqueur d'inflammation aiguë — mesure la sévérité de l'infection",
        "diagnostic_value": {"Grippe": 0.7, "Bronchite": 0.8, "Pneumonie": 0.9, "Angor": 0.6},
    },
    "PCR grippe": {
        "cost": 30, "cost_min": 25, "cost_max": 40,
        "prescription_probability": 0.50,
        "explanation": "confirme ou exclut précisément le virus de la grippe",
        "diagnostic_value": {"Grippe": 0.95},
    },
    "Prélèvement pharyngé": {
        "cost": 35, "cost_min": 30, "cost_max": 45,
        "prescription_probability": 0.60,
        "explanation": "identifie une infection bactérienne de la gorge",
        "diagnostic_value": {"Angine": 0.90, "Rhinopharyngite": 0.55},
    },
    "Radiographie pulmonaire": {
        "cost": 70, "cost_min": 60, "cost_max": 85,
        "prescription_probability": 1.0,
        "explanation": "visualise l'état des poumons et des bronches",
        "diagnostic_value": {"Pneumonie": 0.90, "Bronchite": 0.70},
    },
    "Scanner thoracique": {
        "cost": 180, "cost_min": 150, "cost_max": 210,
        "prescription_probability": 0.30,
        "explanation": "imagerie détaillée des poumons en cas de complications suspectées",
        "diagnostic_value": {"Pneumonie": 0.95, "Bronchite": 0.75, "Embolie pulmonaire": 0.99},
    },
    "Culture des expectorations": {
        "cost": 45, "cost_min": 40, "cost_max": 55,
        "prescription_probability": 0.35,
        "explanation": "identifie l'agent pathogène et sa sensibilité aux antibiotiques",
        "diagnostic_value": {"Pneumonie": 0.85, "Bronchite": 0.60},
    },
    "ASLO": {
        "cost": 22, "cost_min": 18, "cost_max": 30,
        "prescription_probability": 0.55,
        "explanation": "détecte une infection streptococcique récente",
        "diagnostic_value": {"Angine": 0.80},
    },
    "Spirométrie": {
        "cost": 50, "cost_min": 40, "cost_max": 65,
        "prescription_probability": 0.50,
        "explanation": "évalue la fonction respiratoire en cas d'asthme suspecté",
        "diagnostic_value": {"Asthme": 0.95, "Bronchite": 0.55},
    },
    "Tests allergologiques": {
        "cost": 80, "cost_min": 65, "cost_max": 100,
        "prescription_probability": 0.45,
        "explanation": "identifie les allergènes responsables",
        "diagnostic_value": {"Allergie": 0.95},
    },
    "ECG": {
        "cost": 45, "cost_min": 40, "cost_max": 55,
        "prescription_probability": 1.0,
        "explanation": "évalue le fonctionnement du cœur",
        "diagnostic_value": {"Angor": 0.85, "Hypertension": 0.70, "Trouble du rythme": 0.95, "Insuffisance cardiaque": 0.70},
    },
    "Échocardiographie": {
        "cost": 100, "cost_min": 85, "cost_max": 120,
        "prescription_probability": 0.40,
        "explanation": "imagerie détaillée du muscle cardiaque",
        "diagnostic_value": {"Angor": 0.90, "Hypertension": 0.75, "Insuffisance cardiaque": 0.95},
    },
    "Test Helicobacter pylori": {
        "cost": 30, "cost_min": 25, "cost_max": 40,
        "prescription_probability": 1.0,
        "explanation": "détecte la bactérie principale responsable de la gastrite",
        "diagnostic_value": {"Gastrite": 0.90},
    },
    "Fibroscopie gastrique": {
        "cost": 180, "cost_min": 150, "cost_max": 220,
        "prescription_probability": 0.30,
        "explanation": "examen visuel de la muqueuse gastrique",
        "diagnostic_value": {"Gastrite": 0.95},
    },
    "Ferritine": {
        "cost": 15, "cost_min": 12, "cost_max": 20,
        "prescription_probability": 0.65,
        "explanation": "mesure les réserves en fer de l'organisme",
        "diagnostic_value": {"Anémie": 0.90},
    },
    "Vitamine B12": {
        "cost": 15, "cost_min": 12, "cost_max": 20,
        "prescription_probability": 0.55,
        "explanation": "contrôle le taux de vitamine B12, dont le déficit cause une anémie",
        "diagnostic_value": {"Anémie": 0.85},
    },
    "IgE totales": {
        "cost": 35, "cost_min": 28, "cost_max": 45,
        "prescription_probability": 0.50,
        "explanation": "mesure le niveau global d'anticorps allergiques",
        "diagnostic_value": {"Allergie": 0.80},
    },
    "Troponine": {
        "cost": 30, "cost_min": 25, "cost_max": 38,
        "prescription_probability": 0.70,
        "explanation": "marqueur de lésion du muscle cardiaque",
        "diagnostic_value": {"Angor": 0.95},
    },
    "D-dimères": {
        "cost": 25, "cost_min": 20, "cost_max": 35,
        "prescription_probability": 1.0,
        "explanation": "marqueur de coagulation — exclut ou confirme une embolie pulmonaire",
        "diagnostic_value": {"Embolie pulmonaire": 0.99, "Angor": 0.10},
    },
    "BNP": {
        "cost": 35, "cost_min": 28, "cost_max": 45,
        "prescription_probability": 1.0,
        "explanation": "marqueur d'insuffisance cardiaque — élevé en cas de décompensation",
        "diagnostic_value": {"Insuffisance cardiaque": 0.99, "Angor": 0.10},
    },
    "TSH": {
        "cost": 20, "cost_min": 15, "cost_max": 28,
        "prescription_probability": 0.50,
        "explanation": "évalue la fonction thyroïdienne — cause fréquente de palpitations",
        "diagnostic_value": {"Trouble du rythme": 0.70},
    },
    "pH-métrie": {
        "cost": 120, "cost_min": 100, "cost_max": 150,
        "prescription_probability": 0.35,
        "explanation": "mesure l'acidité oesophagienne sur 24h — confirme le RGO",
        "diagnostic_value": {"RGO": 0.95},
    },
    "Coloscopie": {
        "cost": 250, "cost_min": 200, "cost_max": 300,
        "prescription_probability": 0.25,
        "explanation": "examen du côlon — exclut une pathologie organique",
        "diagnostic_value": {"SII": 0.80},
    },
    "Holter ECG": {
        "cost": 80, "cost_min": 65, "cost_max": 100,
        "prescription_probability": 0.28,
        "explanation": "monitoring cardiaque sur 24 heures",
        "diagnostic_value": {"Angor": 0.80, "Hypertension": 0.60, "Trouble du rythme": 0.90},
    },
}

# ── Helpers — accès rapide ───────────────────────────────────────────────────
TEST_COSTS: dict[str, int]    = {k: v["cost"] for k, v in TEST_CATALOG.items()}
TEST_COSTS_MIN: dict[str, int] = {k: v["cost_min"] for k, v in TEST_CATALOG.items()}
TEST_COSTS_MAX: dict[str, int] = {k: v["cost_max"] for k, v in TEST_CATALOG.items()}
TEST_EXPLANATIONS: dict[str, str] = {k: v["explanation"] for k, v in TEST_CATALOG.items()}
TEST_PRESCRIPTION_PROBABILITY: dict[str, float] = {
    k: v["prescription_probability"] for k, v in TEST_CATALOG.items()
}

# Liens : diagnostic → analyses (required / optional)
DIAGNOSIS_TESTS: dict[str, dict[str, list[str]]] = {
    "Grippe":          {"required": ["NFS", "CRP"],                              "optional": ["PCR grippe"]},
    "Rhinopharyngite": {"required": ["NFS"],                                     "optional": ["Prélèvement pharyngé"]},
    "Bronchite":       {"required": ["NFS", "CRP", "Radiographie pulmonaire"],   "optional": ["Scanner thoracique"]},
    "Pneumonie":       {"required": ["NFS", "CRP", "Radiographie pulmonaire"],   "optional": ["Scanner thoracique", "Culture des expectorations"]},
    "Angine":          {"required": ["NFS", "Prélèvement pharyngé"],             "optional": ["ASLO"]},
    "Asthme":          {"required": ["Spirométrie", "NFS"],                      "optional": ["Tests allergologiques"]},
    "Hypertension":    {"required": ["ECG", "NFS"],                              "optional": ["Échocardiographie"]},
    "Gastrite":        {"required": ["NFS", "Test Helicobacter pylori"],         "optional": ["Fibroscopie gastrique"]},
    "Anémie":          {"required": ["NFS", "Ferritine"],                        "optional": ["Vitamine B12"]},
    "Allergie":        {"required": ["NFS", "IgE totales"],                      "optional": ["Tests allergologiques"]},
    "Angor":           {"required": ["ECG", "Troponine", "CRP"],                 "optional": ["Échocardiographie", "Holter ECG"]},
    "Embolie pulmonaire": {"required": ["D-dimères"],                                  "optional": ["Scanner thoracique", "ECG", "Troponine"]},
    "Insuffisance cardiaque": {"required": ["BNP", "ECG"],                           "optional": ["Échocardiographie", "Radiographie pulmonaire"]},
    "Trouble du rythme": {"required": ["ECG"],                                         "optional": ["Holter ECG", "TSH"]},
    "RGO":            {"required": ["pH-métrie"],                                       "optional": ["Test Helicobacter pylori", "Fibroscopie gastrique"]},
    "SII":            {"required": ["NFS", "CRP"],                                    "optional": ["Coloscopie", "Test Helicobacter pylori"]},
}

# Analyses conditionnelles selon les symptômes
CONDITIONAL_REQUIRED: dict[str, list[str]] = {
    "Radiographie pulmonaire":    ["essoufflement", "douleur thoracique"],
    "Scanner thoracique":         ["essoufflement", "douleur thoracique"],
    "Spirométrie":                ["essoufflement", "toux"],
    "ECG":                        ["douleur thoracique", "essoufflement", "palpitations"],
    "Troponine":                  ["douleur thoracique"],
    "Holter ECG":                 ["douleur thoracique", "essoufflement", "palpitations"],
    "Échocardiographie":          ["douleur thoracique", "essoufflement"],
    "Fibroscopie gastrique":      ["nausées", "perte d'appétit"],
    "ASLO":                       ["mal de gorge"],
    "Prélèvement pharyngé":       ["mal de gorge"],
    "PCR grippe":                 ["fièvre", "toux"],
    "Tests allergologiques":      ["éternuements", "irritation de la gorge"],
    "IgE totales":                ["éternuements", "irritation de la gorge"],
    "D-dimères":                 ["douleur thoracique"],  # тільки при дулі thoracique
    "BNP":                       ["œdèmes"],  # тільки при œdèmes
    "TSH":                       ["palpitations"],
    "pH-métrie":                 ["reflux acide", "brûlure rétrosternale", "après repas"],
    "Coloscopie":                ["ballonnements", "douleur chronique"],
    "Culture des expectorations": ["essoufflement", "douleur thoracique"],
}