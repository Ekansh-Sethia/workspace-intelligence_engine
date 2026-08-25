from fastapi.testclient import TestClient
from main import app
import io
import zipfile
import pytest

client = TestClient(app)

# Helper to create an in-memory zip file
def create_dummy_zip(files_dict=None):
    zip_buffer = io.BytesIO()
    if files_dict is None:
        files_dict = {"test.txt": "hello world"}
        
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for filename, content in files_dict.items():
            zf.writestr(filename, content)
            
    zip_buffer.seek(0)
    return zip_buffer

def get_mock_user_override():
    from authentication.models import User
    return User(id=1, email="test@test.com")

def test_list_workspaces():
    from authentication.dependencies import get_current_user
    from core.database import get_db
    from unittest.mock import AsyncMock, MagicMock
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Return an empty list for workspaces
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    
    app.dependency_overrides[get_current_user] = get_mock_user_override
    app.dependency_overrides[get_db] = lambda: mock_session
    
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 200
    assert response.json() == []
    
    app.dependency_overrides.clear()

@pytest.mark.parametrize("scenario, file_content_func, expected_status", [
    ("valid_zip", lambda: create_dummy_zip().read(), 202),
    ("empty_payload", lambda: b"", 400),
    ("corrupt_zip_garbage_bytes", lambda: b"this is not a zip file", 400),
    ("text_file_disguised_as_zip", lambda: b"just some text", 400),
    ("valid_zip_multiple_files", lambda: create_dummy_zip({"a.txt": "a", "b.pdf": "b"}).read(), 202),
    ("oversized_file", lambda: b"0" * (51 * 1024 * 1024), 400)
], ids=["valid", "empty", "corrupt", "text_disguised", "valid_multiple", "oversized"])
def test_upload_workspace_generalized(scenario, file_content_func, expected_status, monkeypatch):
    file_content = file_content_func()
    from authentication.dependencies import get_current_user
    from core.database import get_db
    from unittest.mock import AsyncMock, MagicMock
    from datetime import datetime, UTC
    
    # We must also mock the Celery task so it doesn't try to run
    from workspaces.tasks import process_workspace_upload
    mock_delay = MagicMock()
    monkeypatch.setattr(process_workspace_upload, "delay", mock_delay)
    
    # Mock db
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    # Give the workspace an ID and created_at during refresh
    async def mock_refresh(instance):
        instance.id = 999
        instance.created_at = datetime.now(UTC)
        instance.document_count = 0
        instance.image_count = 0
        instance.total_chunk_count = 0
    mock_session.refresh = mock_refresh
    
    app.dependency_overrides[get_current_user] = get_mock_user_override
    app.dependency_overrides[get_db] = lambda: mock_session
    
    # Post request
    files = {"file": ("test.zip", file_content, "application/zip")}
    data = {"name": "Test Workspace", "description": "Desc"}
    
    response = client.post("/api/v1/workspaces", data=data, files=files)
    
    assert response.status_code == expected_status
    if expected_status == 202:
        assert mock_delay.called
    else:
        assert not mock_delay.called
        
    app.dependency_overrides.clear()

def test_get_workspace_files():
    from authentication.dependencies import get_current_user
    from core.database import get_db
    from unittest.mock import AsyncMock, MagicMock
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result
    
    app.dependency_overrides[get_current_user] = get_mock_user_override
    app.dependency_overrides[get_db] = lambda: mock_session
    
    response = client.get("/api/v1/workspaces/999/files")
    assert response.status_code == 404
    
    app.dependency_overrides.clear()
