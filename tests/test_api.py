import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── Root / Health ─────────────────────────────────────────────────────

def test_root_returns_200():
    response = client.get("/")
    assert response.status_code == 200


def test_health_returns_200():
    response = client.get("/v1/health")
    assert response.status_code == 200


def test_health_returns_ok_status():
    response = client.get("/v1/health")
    assert response.json()["status"] == "ok"



# ── POST /v1/analyze — структура відповіді ───────────────────────────

def test_analyze_returns_200():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    assert response.status_code == 200


def test_analyze_response_has_all_fields():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    data = response.json()
    assert "diagnoses" in data
    assert "tests" in data
    assert "cost" in data
    assert "explanation" in data
    assert "comparison" in data


def test_analyze_tests_has_required_and_optional():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    data = response.json()
    assert "required" in data["tests"]
    assert "optional" in data["tests"]


def test_analyze_cost_has_all_fields():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    data = response.json()
    assert "required" in data["cost"]
    assert "optional" in data["cost"]
    assert "savings" in data["cost"]


def test_analyze_comparison_has_savings_multiplier():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    data = response.json()
    assert "savings_multiplier" in data["comparison"]
    assert "x" in data["comparison"]["savings_multiplier"]


# ── GET /v1/scenarios ─────────────────────────────────────────────────

def test_scenarios_returns_200():
    response = client.get("/v1/scenarios")
    assert response.status_code == 200


def test_scenarios_returns_list():
    response = client.get("/v1/scenarios")
    data = response.json()
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
    assert len(data["scenarios"]) > 0


def test_scenarios_have_name_and_symptoms():
    response = client.get("/v1/scenarios")
    for scenario in response.json()["scenarios"]:
        assert "name" in scenario
        assert "symptoms" in scenario
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    data = response.json()
    c = data["comparison"]
    assert "standard_tests" in c
    assert "standard_cost" in c
    assert "optimized_tests" in c
    assert "optimized_cost" in c
    assert "savings" in c


def test_analyze_explanation_is_string():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    data = response.json()
    assert isinstance(data["explanation"], str)
    assert len(data["explanation"]) > 0


def test_analyze_diagnoses_are_list():
    response = client.post("/v1/analyze", json={"symptoms": ["кашель"]})
    data = response.json()
    assert isinstance(data["diagnoses"], list)


# ── POST /v1/analyze — граничні випадки ──────────────────────────────

def test_analyze_unknown_symptoms_returns_empty_diagnoses():
    response = client.post("/v1/analyze", json={"symptoms": ["невідомий симптом"]})
    assert response.status_code == 200
    assert response.json()["diagnoses"] == []


def test_analyze_empty_symptoms_returns_200():
    response = client.post("/v1/analyze", json={"symptoms": []})
    assert response.status_code == 200


def test_analyze_empty_symptoms_returns_empty_diagnoses():
    response = client.post("/v1/analyze", json={"symptoms": []})
    assert response.json()["diagnoses"] == []


# ── Валідація ─────────────────────────────────────────────────────────

def test_analyze_missing_body_returns_422():
    response = client.post("/v1/analyze")
    assert response.status_code == 422


def test_analyze_wrong_type_returns_422():
    response = client.post("/v1/analyze", json={"symptoms": "температура"})
    assert response.status_code == 422


def test_analyze_invalid_field_returns_422():
    response = client.post("/v1/analyze", json={"wrong_field": ["температура"]})
    assert response.status_code == 422