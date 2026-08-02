# -*- encoding: utf-8 -*-
"""Tests des routes /mesh/v1/* en isolation (pas de vrai réseau, pas de
Xapian requis : ces tests utilisent uniquement des routes/registre)."""
from sphinxcontrib.osint.mesh.registry import PeerRegistry


def _registry(**kwargs):
    kwargs.setdefault('self_id', 'osint-test')
    kwargs.setdefault('self_url', 'http://testserver')
    kwargs.setdefault('lang', 'fr')
    return PeerRegistry(**kwargs)


def test_info_returns_identity(app_factory):
    app = app_factory(_registry())
    resp = app.test_client().get('/mesh/v1/info')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {'id': 'osint-test', 'url': 'http://testserver', 'lang': 'fr'}


def test_keywords_empty_without_xapian_dir(app_factory):
    app = app_factory(_registry())  # xapian_dir=None par défaut
    resp = app.test_client().get('/mesh/v1/keywords')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['peer_id'] == 'osint-test'
    assert body['keywords'] == []
    assert body['generated_at'] is not None


def test_keywords_returns_manually_set_list(app_factory):
    registry = _registry()
    registry.set_local_keywords(['ukraine', 'sanctions', 'kyiv'])
    app = app_factory(registry)

    resp = app.test_client().get('/mesh/v1/keywords')

    assert resp.get_json()['keywords'] == ['ukraine', 'sanctions', 'kyiv']


def test_keywords_returns_manually_set_entities(app_factory):
    registry = _registry()
    registry.set_local_entities(['Volodymyr Zelensky', 'Kyiv'])
    app = app_factory(registry)

    resp = app.test_client().get('/mesh/v1/keywords')
    body = resp.get_json()

    assert body['entities'] == ['Volodymyr Zelensky', 'Kyiv']
    assert body['entities_generated_at'] is not None


def test_peers_lists_self_and_known_peers(app_factory):
    registry = _registry()
    registry.add_peer('osint-fr', 'http://osint-fr.example.org', 'fr', source='bootstrap')
    app = app_factory(registry)

    resp = app.test_client().get('/mesh/v1/peers')

    ids = {p['id'] for p in resp.get_json()['peers']}
    assert ids == {'osint-test', 'osint-fr'}


def test_no_auth_required_when_no_secret_configured(app_factory):
    app = app_factory(_registry(secret=''))
    resp = app.test_client().get('/mesh/v1/info')

    assert resp.status_code == 200


def test_auth_required_when_secret_configured(app_factory):
    app = app_factory(_registry(secret='s3cret'))
    client = app.test_client()

    resp = client.get('/mesh/v1/info')
    assert resp.status_code == 401

    resp = client.get('/mesh/v1/info', headers={'X-Mesh-Token': 'wrong'})
    assert resp.status_code == 401

    resp = client.get('/mesh/v1/info', headers={'X-Mesh-Token': 's3cret'})
    assert resp.status_code == 200
