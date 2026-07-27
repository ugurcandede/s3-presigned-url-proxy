import importlib

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
    # Pin the passthrough config so an ambient PASSTHROUGH_PORT can't flip the 400 tests.
    monkeypatch.setattr(proxy, 'PASSTHROUGH_PORT', None)
    monkeypatch.setattr(proxy, 'PASSTHROUGH_HOSTS', [])
    monkeypatch.setattr(proxy, 'PASSTHROUGH_ANY_HOST', False)
    return proxy.app.test_client()


@pytest.fixture
def passthrough(monkeypatch):
    monkeypatch.setattr(proxy, 'PASSTHROUGH_PORT', '8088')
    monkeypatch.setattr(proxy, 'PASSTHROUGH_HOSTS', ['example.com'])
    monkeypatch.setattr(proxy, 'PASSTHROUGH_ANY_HOST', False)


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


def test_passthrough_redirects_to_configured_port(client, passthrough):
    resp = client.get(
        '/download/file?id=81a31868',
        base_url='http://example.com:8087',
    )
    assert resp.status_code == 307
    assert resp.headers['Location'] == 'http://example.com:8088/download/file?id=81a31868'


def test_passthrough_preserves_encoded_path(client, passthrough):
    # %23 must stay encoded; decoding it would make the rest of the URL a fragment.
    resp = client.get(
        '/download/file%231.pdf?id=7',
        base_url='http://example.com:8087',
    )
    assert resp.headers['Location'] == 'http://example.com:8088/download/file%231.pdf?id=7'


def test_passthrough_does_not_affect_valid_requests(client, passthrough):
    resp = client.get('/?objectkey=files/doc.pdf', base_url='http://example.com:8087')
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'https://example.com/signed'


def test_partial_params_still_report_400(client, passthrough, monkeypatch):
    # A typo'd/incomplete proxy request must not be silently routed to the other app.
    monkeypatch.setattr(proxy, 'REQUIRED_PARAMS', ['tenant', 'objectkey'])
    resp = client.get('/?tenant=acme', base_url='http://example.com:8087')
    assert resp.status_code == 400
    assert 'objectkey' in resp.get_json()['error']


def test_passthrough_covers_missing_object_key(client, passthrough, monkeypatch):
    # OBJECT_KEY_PARAM outside REQUIRED_PARAMS must not escape the passthrough branch.
    monkeypatch.setattr(proxy, 'REQUIRED_PARAMS', ['tenant'])
    resp = client.get('/ui/page', base_url='http://example.com:8087')
    assert resp.status_code == 307


def test_passthrough_rejects_unlisted_host(client, passthrough):
    resp = client.get('/x', base_url='http://evil.test:8087')
    assert resp.status_code == 400
    assert 'Location' not in resp.headers


def test_passthrough_hosts_parsing(monkeypatch):
    # Entries are trimmed and lowercased; only a bare '*' carries special meaning.
    monkeypatch.setenv('PASSTHROUGH_PORT', '8088')
    monkeypatch.setenv('PASSTHROUGH_HOSTS', 'A.test, b.test ,*')
    try:
        importlib.reload(proxy)
        assert proxy.PASSTHROUGH_HOSTS == ['a.test', 'b.test', '*']
        assert proxy.PASSTHROUGH_ANY_HOST is True
    finally:
        monkeypatch.undo()
        importlib.reload(proxy)


def test_star_prefix_is_not_a_wildcard(client, monkeypatch):
    # Subdomains are covered by the bare host, so '*.host' is just an unmatchable literal.
    monkeypatch.setattr(proxy, 'PASSTHROUGH_PORT', '8088')
    monkeypatch.setattr(proxy, 'PASSTHROUGH_HOSTS', ['*.example.com'])
    assert client.get('/x', base_url='http://ui.example.com:8087').status_code == 400


def test_passthrough_matches_subdomains(client, passthrough):
    # Entry 'example.com' covers the host itself and anything under it.
    for host in ('example.com', 'ui.example.com', 'a.b.example.com'):
        assert client.get('/x', base_url=f'http://{host}:8087').status_code == 307


def test_passthrough_wildcard_allows_any_host(client, monkeypatch):
    monkeypatch.setattr(proxy, 'PASSTHROUGH_PORT', '8088')
    monkeypatch.setattr(proxy, 'PASSTHROUGH_HOSTS', ['*'])
    monkeypatch.setattr(proxy, 'PASSTHROUGH_ANY_HOST', True)
    resp = client.get('/x', base_url='http://anything.test:8087')
    assert resp.status_code == 307
    assert resp.headers['Location'] == 'http://anything.test:8088/x'


def test_passthrough_refuses_to_redirect_to_itself(client, passthrough):
    resp = client.get('/download/x?id=1', base_url='http://example.com:8088')
    assert resp.status_code == 500
    assert 'Location' not in resp.headers


def test_passthrough_handles_ipv6_host(client, monkeypatch):
    monkeypatch.setattr(proxy, 'PASSTHROUGH_PORT', '8088')
    monkeypatch.setattr(proxy, 'PASSTHROUGH_HOSTS', ['::1'])
    resp = client.get('/download/file?id=1', base_url='http://[::1]:8087')
    assert resp.status_code == 307
    assert resp.headers['Location'] == 'http://[::1]:8088/download/file?id=1'


def test_passthrough_preserves_post(client, passthrough):
    resp = client.post('/api/file', base_url='http://example.com:8087')
    assert resp.status_code == 307
    assert resp.headers['Location'] == 'http://example.com:8088/api/file'


def test_object_key_param_is_configurable(client, monkeypatch):
    monkeypatch.setattr(proxy, 'OBJECT_KEY_PARAM', 'key')
    monkeypatch.setattr(proxy, 'REQUIRED_PARAMS', ['key'])
    resp = client.get('/?key=a/b.pdf')
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'https://example.com/signed'
