import pytest
from fastapi.testclient import TestClient
from ..main import app  # Adjust the import according to your app structure

# Create a TestClient instance
client = TestClient(app)

# Sample data for testing
valid_user_value = {
    "assignment_description": "Implement a new feature.",
    "github_url": "https://github.com/aunth/tic-tac-toe",
    "user_level": "junior"
}

invalid_user_value = {
    "assignment_description": "Short",
    "github_url": "invalid_url",
    "user_level": "expert"  # invalid level
}

@pytest.mark.asyncio
async def test_valid_review_code():
    response = client.post("/review", json=valid_user_value)
    assert response.status_code == 200
    data = response.json()
    assert "downsides_comments" in data
    assert "rating" in data
    assert "conclusion" in data
    assert isinstance(data["found_files"], list)

@pytest.mark.asyncio
async def test_invalid_github_url():
    invalid_data = valid_user_value.copy()
    invalid_data["github_url"] = "invalid_url"
    
    response = client.post("/review", json=invalid_data)
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_missing_user_level():
    missing_level_data = valid_user_value.copy()
    missing_level_data["user_level"] = "expert"

    response = client.post("/review", json=missing_level_data)
    assert response.status_code == 422
