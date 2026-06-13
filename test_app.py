import pytest

import app as proxy


@pytest.fixture
def client(monkeypatch):
    # Avoid any AWS dependency: stub out the pre-signed URL generation.
    monkeypatch.setattr(
        proxy.s3_client,
        'generate_presigned_url',
        lambda *args, **kwargs: 'https://example.com/signed',
    )
    return proxy.app.test_client()


def test_health(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_missing_required_param_returns_400(client):
    # Default config requires 'objectkey'
    resp = client.get('/?foo=bar')
    assert resp.status_code == 400
    assert 'objectkey' in resp.get_json()['error']


def test_valid_request_redirects(client):
    resp = client.get('/?objectkey=files/doc.pdf')
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'https://example.com/signed'


def test_extra_required_param_enforced(client, monkeypatch):
    monkeypatch.setattr(proxy, 'REQUIRED_PARAMS', ['tenant', 'objectkey'])
    resp = client.get('/?objectkey=a/b.pdf')
    assert resp.status_code == 400
    assert 'tenant' in resp.get_json()['error']


def test_object_key_param_is_configurable(client, monkeypatch):
    monkeypatch.setattr(proxy, 'OBJECT_KEY_PARAM', 'key')
    monkeypatch.setattr(proxy, 'REQUIRED_PARAMS', ['key'])
    resp = client.get('/?key=a/b.pdf')
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'https://example.com/signed'
