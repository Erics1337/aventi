import os

os.environ.pop('AVENTI_DATABASE_URL', None)
os.environ['AVENTI_AUTH_DEV_BYPASS'] = 'true'

from fastapi.testclient import TestClient

from aventi_backend.app import create_app
from aventi_backend.core.settings import get_settings
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import build_repository


def _client() -> TestClient:
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: build_repository(None)
    return TestClient(app)


def test_bootstrap_and_feed_flow() -> None:
    client = _client()

    bootstrap = client.post('/v1/me/bootstrap')
    assert bootstrap.status_code == 200
    body = bootstrap.json()
    assert body['id'] == 'dev-user'

    feed = client.get('/v1/feed', params={'latitude': 30.2672, 'longitude': -97.7431})
    assert feed.status_code == 200
    payload = feed.json()
    assert len(payload['items']) >= 1
    assert payload['remainingFreeSwipes'] == 10
    assert payload['remainingFreePreferenceActions'] == 10

    location_update = client.put(
        '/v1/me/location',
        json={
            'latitude': 30.2672,
            'longitude': -97.7431,
            'city': 'Austin',
            'timezone': 'America/Chicago',
        },
    )
    assert location_update.status_code == 200
    location_body = location_update.json()
    assert location_body['ok'] is True
    assert location_body['profile']['city'] == 'Austin'
    assert location_body['profile']['timezone'] == 'America/Chicago'
    assert location_body['profile']['onboarded'] is True

    me = client.get('/v1/me')
    assert me.status_code == 200
    assert me.json()['profile']['latitude'] == 30.2672
    assert me.json()['profile']['longitude'] == -97.7431


def test_favorites_reports_and_swipes_memory_repo() -> None:
    client = _client()

    save = client.put('/v1/favorites/evt-seed-1')
    assert save.status_code == 200
    assert save.json()['ok'] is True

    favorites = client.get('/v1/favorites')
    assert favorites.status_code == 200
    assert 'evt-seed-1' in favorites.json()['items']

    swipe = client.post(
        '/v1/swipes',
        json={
            'eventId': 'evt-seed-1',
            'action': 'like',
            'surfacedAt': '2026-02-26T12:00:00Z',
            'position': 0,
            'vibes': ['social', 'energetic'],
        },
    )
    assert swipe.status_code == 200
    assert swipe.json()['accepted'] is True
    assert swipe.json()['remainingFreeSwipes'] == 9
    assert swipe.json()['remainingFreePreferenceActions'] == 9

    impression = client.post(
        '/v1/feed/impressions',
        json={
            'eventId': 'evt-seed-1',
            'servedAt': '2026-02-26T12:01:00Z',
            'position': 0,
            'filters': {'date': 'week', 'price': 'any'},
        },
    )
    assert impression.status_code == 200
    assert impression.json()['ok'] is True

    for _ in range(3):
        report = client.post('/v1/events/evt-hide-me/report', json={'reason': 'invalid'})
        assert report.status_code == 200

    # Same dev user can't increment count beyond 1 due unique-user semantics in memory store.
    report_again = client.post('/v1/events/evt-hide-me/report', json={'reason': 'invalid'})
    assert report_again.status_code == 200
    assert report_again.json()['reportCount'] == 1
