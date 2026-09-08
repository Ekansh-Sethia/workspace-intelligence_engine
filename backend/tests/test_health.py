from fastapi.testclient import TestClient
from main import app
from utils.config import settings

client = TestClient(app)

def test_health_check():
    response = client.get(f"{settings.API_V1_STR}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["message"] == "ContextIQ is running"

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": f"Welcome to {settings.PROJECT_NAME} API"}
