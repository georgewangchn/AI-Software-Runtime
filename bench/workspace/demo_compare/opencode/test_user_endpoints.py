import pytest
from fastapi.testclient import TestClient
from main import app
from models import User, UserCreate

client = TestClient(app)


def test_get_user_includes_email():
    """Response from get_user endpoint contains email field matching request"""
    response = client.get("/users/1")
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "name" in data
    assert "email" in data
    assert data["email"] == "alice@example.com"


def test_search_users_empty_query():
    """search_users returns empty list on empty or whitespace-only query"""
    # Test empty string
    response = client.get("/users/search?q=")
    assert response.status_code == 200
    assert response.json() == []

    # Test whitespace-only
    response = client.get("/users/search?q=  \t\n")
    assert response.status_code == 200
    assert response.json() == []

    # Test None query (no query parameter)
    response = client.get("/users/search")
    assert response.status_code == 200
    assert response.json() == []


def test_create_user_blocks_duplicates():
    """Create user with existing email returns 409 Conflict"""
    # First create a user
    response = client.post("/users", json={"name": "David", "email": "david@example.com"})
    assert response.status_code == 201
    
    # Try to create user with same email
    response = client.post("/users", json={"name": "Eve", "email": "david@example.com"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Email already exists"


def test_search_users_returns_correct_results():
    """Test that search_users returns users with matching name"""
    response = client.get("/users/search?q=al")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Alice"
    assert data[0]["email"] == "alice@example.com"


def test_get_user_not_found():
    """Test get_user returns 404 for non-existent user"""
    response = client.get("/users/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_create_user_validates_model():
    """Test create_user validates required fields"""
    # Missing name
    response = client.post("/users", json={"email": "test@example.com"})
    assert response.status_code == 422
    
    # Missing email
    response = client.post("/users", json={"name": "Test User"})
    assert response.status_code == 422


def test_create_user_returns_full_user_object():
    """Test create_user returns complete user object with id"""
    response = client.post("/users", json={"name": "Frank", "email": "frank@example.com"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Frank"
    assert data["email"] == "frank@example.com"
    assert "id" in data
    assert isinstance(data["id"], int)


def test_search_users_case_insensitive():
    """Test search_users is case-insensitive"""
    response = client.get("/users/search?q=AL")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Alice"


def test_search_users_partial_match():
    """Test search_users does partial match on name"""
    response = client.get("/users/search?q=ob")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Bob"


def test_search_users_no_match():
    """Test search_users returns empty list when no match"""
    response = client.get("/users/search?q=xyz")
    assert response.status_code == 200
    assert response.json() == []