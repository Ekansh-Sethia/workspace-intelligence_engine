from fastapi.testclient import TestClient
from main import app
from utils.config import settings
import io
import zipfile

client = TestClient(app)

def create_dummy_zip():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("test.txt", "hello world")
    zip_buffer.seek(0)
    return zip_buffer

def test_list_workspaces():
    pass

def test_upload_workspace():
    # To test upload:
    # files = {"file": ("test.zip", create_dummy_zip(), "application/zip")}
    # data = {"name": "Test Workspace", "description": "Desc"}
    pass

def test_empty_zip():
    # Should test that an empty zip throws a 400 Bad Request
    pass

def test_corrupt_zip():
    # Should test that a corrupt zip throws a 400 Bad Request
    pass
