from fastapi.testclient import TestClient
from main import app
import pytest
from unittest.mock import AsyncMock, MagicMock

client = TestClient(app)

def get_mock_user_override():
    from authentication.models import User
    return User(id=1, email="test@test.com")

def get_mock_other_user_override():
    from authentication.models import User
    return User(id=2, email="other@test.com")

@pytest.fixture
def mock_dependencies(monkeypatch):
    from authentication.dependencies import get_current_user
    from core.database import get_db
    
    mock_session = AsyncMock()
    app.dependency_overrides[get_current_user] = get_mock_user_override
    app.dependency_overrides[get_db] = lambda: mock_session
    
    yield mock_session
    
    app.dependency_overrides.clear()

def test_get_workspace_not_found(mock_dependencies):
    mock_session = mock_dependencies
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    response = client.get("/api/v1/workspaces/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found"

def test_get_workspace_auth_bypass(mock_dependencies):
    from authentication.dependencies import get_current_user
    from workspaces.models import Workspace
    mock_session = mock_dependencies
    
    # Switch to the 'other' user
    app.dependency_overrides[get_current_user] = get_mock_other_user_override
    
    mock_result = MagicMock()
    # Workspace exists but it's not owned by current user (DB query would return None due to where clause)
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    response = client.get("/api/v1/workspaces/1")
    assert response.status_code == 404

def test_search_workspace_not_ready(mock_dependencies):
    from workspaces.models import Workspace
    mock_session = mock_dependencies
    
    mock_result = MagicMock()
    # Workspace is pending
    mock_ws = Workspace(id=1, owner_id=1, status="pending")
    mock_result.scalars.return_value.first.return_value = mock_ws
    mock_session.execute.return_value = mock_result
    
    response = client.post("/api/v1/workspaces/1/search", json={"query": "test", "limit": 5})
    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]

def test_search_workspace_malformed_query(mock_dependencies):
    mock_session = mock_dependencies
    
    # Missing required query field
    response = client.post("/api/v1/workspaces/1/search", json={"limit": 5})
    assert response.status_code == 422 # Unprocessable Entity

def test_export_workspace_invalid_format(mock_dependencies):
    mock_session = mock_dependencies
    
    # Format must be txt or md
    response = client.get("/api/v1/workspaces/1/export?format=pdf")
    assert response.status_code == 422
    assert "String should match pattern" in response.json()["detail"][0]["msg"]

def test_delete_workspace_not_found(mock_dependencies):
    mock_session = mock_dependencies
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    response = client.delete("/api/v1/workspaces/999")
    assert response.status_code == 404

def test_actions_quiz_not_ready(mock_dependencies):
    from workspaces.models import Workspace
    mock_session = mock_dependencies
    
    mock_result = MagicMock()
    mock_ws = Workspace(id=1, owner_id=1, status="processing")
    mock_result.scalars.return_value.first.return_value = mock_ws
    mock_session.execute.return_value = mock_result
    
    response = client.post("/api/v1/workspaces/1/actions/quiz")
    assert response.status_code == 409

def test_actions_notes_not_ready(mock_dependencies):
    from workspaces.models import Workspace
    mock_session = mock_dependencies
    
    mock_result = MagicMock()
    mock_ws = Workspace(id=1, owner_id=1, status="processing")
    mock_result.scalars.return_value.first.return_value = mock_ws
    mock_session.execute.return_value = mock_result
    
    response = client.post("/api/v1/workspaces/1/actions/notes")
    assert response.status_code == 409
