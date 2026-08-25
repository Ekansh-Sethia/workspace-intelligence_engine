from fastapi.testclient import TestClient
from main import app
from utils.config import settings
from unittest.mock import AsyncMock, MagicMock
from authentication.models import User
from core.database import get_db
import pytest

client = TestClient(app)

@pytest.fixture
def mock_db():
    mock_session = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.clear()

def test_signup_success(mock_db):
    mock_session = mock_db
    
    from datetime import datetime, UTC
    
    async def mock_refresh(instance):
        instance.id = 1
        instance.created_at = datetime.now(UTC)
    mock_session.refresh = mock_refresh
    
    # DB query to check existing user returns None
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    response = client.post(
        f"{settings.API_V1_STR}/auth/signup",
        json={"email": "newuser@example.com", "password": "password123"}
    )
    assert response.status_code == 201
    assert "email" in response.json()
    assert response.json()["email"] == "newuser@example.com"

def test_signup_duplicate_email(mock_db):
    mock_session = mock_db
    
    # DB query to check existing user returns a User
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = User(id=1, email="test@example.com")
    mock_session.execute.return_value = mock_result
    
    response = client.post(
        f"{settings.API_V1_STR}/auth/signup",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

def test_signup_invalid_email(mock_db):
    # Pydantic should catch invalid email
    response = client.post(
        f"{settings.API_V1_STR}/auth/signup",
        json={"email": "not-an-email", "password": "password123"}
    )
    assert response.status_code == 422 # Unprocessable Entity

def test_login_success(mock_db):
    from authentication.security import get_password_hash
    mock_session = mock_db
    
    # DB query to get user by email returns a User with matching password
    mock_result = MagicMock()
    user = User(id=1, email="test@example.com", hashed_password=get_password_hash("password123"))
    mock_result.scalars.return_value.first.return_value = user
    mock_session.execute.return_value = mock_result
    
    # login uses form data (OAuth2PasswordRequestForm)
    response = client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_login_wrong_password(mock_db):
    from authentication.security import get_password_hash
    mock_session = mock_db
    
    mock_result = MagicMock()
    user = User(id=1, email="test@example.com", hashed_password=get_password_hash("password123"))
    mock_result.scalars.return_value.first.return_value = user
    mock_session.execute.return_value = mock_result
    
    response = client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "test@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_login_user_not_found(mock_db):
    mock_session = mock_db
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    response = client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "notfound@example.com", "password": "password123"}
    )
    assert response.status_code == 401
