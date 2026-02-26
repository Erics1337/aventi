from fastapi.testclient import TestClient

from aventi_backend.app import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get('/v1/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
