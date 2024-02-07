import pytest
from fastapi.testclient import TestClient

from seertall_api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client: TestClient):
    res = client.get("/")
    assert res.json() == {"message": "Hello World"}
