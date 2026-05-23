from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_existing_user():
    response = client.get("/users/1")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Alice"
    assert "email" in data
    assert data["email"] == "alice@example.com"

def test_get_nonexistent_user():
    response = client.get("/users/999")
    assert response.status_code == 404

def test_search_users():
    response = client.get("/users/search?q=Ali")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(u["name"] == "Alice" for u in data)

def test_search_empty_query():
    response = client.get("/users/search?q=")
    assert response.status_code in (200, 400)

def test_create_duplicate_user():
    response = client.post("/users", json={"name": "Alice2", "email": "alice@example.com"})
    assert response.status_code == 409
