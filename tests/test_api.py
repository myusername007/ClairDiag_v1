import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# Health / root

def test_root_returns_200():
    response = client.get("/")
    assert response.status_code == 200


# POST /analyze — валідні запити

def test_analyze_returns_200():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    assert response.status_code == 200


def test_analyze_response_has_required_fields():
    response = client.post("/v1/analyze", json={"symptoms": ["температура"]})
    data = response.json()
    assert "diagnoses" in data
    assert "tests" in data
    assert "cost" in data


def test_analyze_tests_has_required_and_optional():
    response = client.post("/v1/analyze", json={"symptoms": ["температура", "кашель"]})
    data = response.json()
    assert "required" in data["tests"]
    assert "optional" in data["tests"]


def test_analyze_cost_has_all_fields():
    response = client.post("/v1/analyze", json={"symptoms": ["температура"]})
    data = response.json()
    assert "required" in data["cost"]
    assert "optional" in data["cost"]
    assert "savings" in data["cost"]


def test_analyze_diagnoses_are_list():
    response = client.post("/v1/analyze", json={"symptoms": ["кашель"]})
    data = response.json()
    assert isinstance(data["diagnoses"], list)


# POST /analyze — граничні випадки 

def test_analyze_unknown_symptoms_returns_empty():
    response = client.post("/v1/analyze", json={"symptoms": ["невідомий симптом"]})
    assert response.status_code == 200
    data = response.json()
    assert data["diagnoses"] == []


def test_analyze_empty_symptoms_returns_200():
    response = client.post("/v1/analyze", json={"symptoms": []})
    assert response.status_code == 200


# Валідація вхідних даних 

def test_analyze_missing_body_returns_422():
    response = client.post("/v1/analyze")
    assert response.status_code == 422


def test_analyze_wrong_type_returns_422():
    response = client.post("/v1/analyze", json={"symptoms": "температура"})
    assert response.status_code == 422
