from fastapi.testclient import TestClient
from main import app
import io
import zipfile
import pytest

client = TestClient(app)

def create_zip_slip_payload():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../../../malicious.txt", "evil")
        zf.writestr("normal.txt", "normal")
    zip_buffer.seek(0)
    return zip_buffer

def get_mock_user_override():
    from authentication.models import User
    return User(id=1, email="test@test.com")

def test_secure_extract_zip_slip(monkeypatch):
    """
    Test that the workspace upload endpoint silently ignores malicious zip slip paths
    but accepts normal files in the same zip.
    """
    from authentication.dependencies import get_current_user
    from core.database import get_db
    from unittest.mock import AsyncMock, MagicMock
    from datetime import datetime, UTC
    
    # Mock Celery task
    from workspaces.tasks import process_workspace_upload
    mock_delay = MagicMock()
    monkeypatch.setattr(process_workspace_upload, "delay", mock_delay)
    
    # Mock db
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    async def mock_refresh(instance):
        instance.id = 999
        instance.created_at = datetime.now(UTC)
        instance.document_count = 0
        instance.image_count = 0
        instance.total_chunk_count = 0
    mock_session.refresh = mock_refresh
    
    app.dependency_overrides[get_current_user] = get_mock_user_override
    app.dependency_overrides[get_db] = lambda: mock_session
    
    zip_buffer = create_zip_slip_payload()
    
    response = client.post(
        "/api/v1/workspaces",
        data={"name": "Zip Slip Test", "description": "Testing zip slip"},
        files={"file": ("test.zip", zip_buffer.read(), "application/zip")}
    )
    
    assert response.status_code == 202
    
    # The actual database extraction and parsing is now done in a background task
    # which we mocked. However, since extraction happens synchronously inside the
    # router before DB insertion (Wait, NO! The router extracts it IN MEMORY during the request!)
    # Let's check how the router works now. The router reads the zip and creates File objects.
    # We should verify that `mock_session.add_all` was called with only `normal.txt`.
    
    assert mock_session.add.called
    
    file_paths = []
    # add() is called for the workspace first, then for each file
    for call in mock_session.add.call_args_list:
        obj = call[0][0]
        if hasattr(obj, "relative_path"):
            file_paths.append(obj.relative_path)
    
    assert "normal.txt" in file_paths
    assert "../../../../malicious.txt" not in file_paths
    assert len(file_paths) == 1
    
    app.dependency_overrides.clear()
