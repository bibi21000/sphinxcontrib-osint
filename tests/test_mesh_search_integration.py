# -*- encoding: utf-8 -*-
"""
Test d'intégration bout-en-bout de la recherche mesh : deux vrais
serveurs Flask sur 127.0.0.1, un vrai appel HTTP POST /mesh/v1/search de
l'un vers l'autre. `local_search_fn` reste injecté (pas de vraie base
Xapian ici) -- ce qui est testé, c'est le transport HTTP + l'agrégation,
pas le moteur de recherche Xapian lui-même (cf. test_mesh_keywords.py
pour extract_top_terms/extract_canonical_labels avec un vrai xapian).
"""
from sphinxcontrib.osint.mesh.registry import PeerRegistry


def test_search_route_round_trip(live_server_factory):
    peer_registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr',
        local_search_fn=lambda q, limit: [{'title': f'résultat pour {q}', 'score': 80}],
    )
    peer_server = live_server_factory(peer_registry)
    peer_registry.self_url = peer_server.url

    client_registry = PeerRegistry(self_id='osint-en', self_url='')
    client_registry.add_peer('osint-fr', peer_server.url, lang='fr')
    client_registry._peers['osint-fr']['keywords'] = {'ukraine'}  # simule une synchro déjà faite

    results = client_registry.mesh_search('ukraine sanctions', mode='fast')

    assert len(results) == 1
    assert results[0]['peer_id'] == 'osint-fr'
    assert results[0]['title'] == 'résultat pour ukraine sanctions'


def test_search_route_rejects_empty_query(live_server_factory):
    peer_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr',
                                  local_search_fn=lambda q, limit: [])
    peer_server = live_server_factory(peer_registry)

    resp = peer_server.app.test_client().post('/mesh/v1/search', json={'q': ''})

    assert resp.status_code == 400


def test_search_route_caps_limit(live_server_factory):
    captured = {}

    def fake_search(query, limit):
        captured['limit'] = limit
        return []

    peer_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr', local_search_fn=fake_search)
    peer_server = live_server_factory(peer_registry)

    peer_server.app.test_client().post('/mesh/v1/search', json={'q': 'ukraine', 'limit': 100000})

    assert captured['limit'] == 50  # plafonné


def test_search_route_requires_mesh_token_when_configured(live_server_factory):
    peer_registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr', secret='s3cret',
        local_search_fn=lambda q, limit: [{'title': 'x', 'score': 1}],
    )
    peer_server = live_server_factory(peer_registry)
    client = peer_server.app.test_client()

    resp = client.post('/mesh/v1/search', json={'q': 'ukraine'})
    assert resp.status_code == 401

    resp = client.post('/mesh/v1/search', json={'q': 'ukraine'}, headers={'X-Mesh-Token': 's3cret'})
    assert resp.status_code == 200


def test_deep_search_queries_peer_even_without_matching_keywords(live_server_factory):
    peer_registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr',
        local_search_fn=lambda q, limit: [{'title': 'trouvé quand même', 'score': 10}],
    )
    peer_server = live_server_factory(peer_registry)

    client_registry = PeerRegistry(self_id='osint-en', self_url='')
    client_registry.add_peer('osint-fr', peer_server.url, lang='fr')
    client_registry._peers['osint-fr']['keywords'] = {'election'}  # ne matcherait pas en fast

    fast_results = client_registry.mesh_search('ukraine', mode='fast')
    deep_results = client_registry.mesh_search('ukraine', mode='deep')

    assert fast_results == []
    assert len(deep_results) == 1
    assert deep_results[0]['title'] == 'trouvé quand même'


# -- sanitisation des résultats distants ------------------------------------

def test_remote_result_with_dangerous_url_scheme_is_stripped(live_server_factory):
    peer_registry = PeerRegistry(
        self_id='osint-evil', self_url='', lang='fr',
        local_search_fn=lambda q, limit: [{'title': 'x', 'score': 1, 'url': 'javascript:alert(1)'}],
    )
    peer_server = live_server_factory(peer_registry)

    client_registry = PeerRegistry(self_id='osint-en', self_url='')
    client_registry.add_peer('osint-evil', peer_server.url, lang='fr')
    client_registry._peers['osint-evil']['keywords'] = {'ukraine'}

    results = client_registry.mesh_search('ukraine', mode='fast')

    assert results[0]['url'] == ''  # neutralisée, jamais transmise telle quelle


def test_remote_result_with_safe_https_url_is_kept(live_server_factory):
    peer_registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr',
        local_search_fn=lambda q, limit: [{'title': 'x', 'score': 1, 'url': 'https://example.org/a'}],
    )
    peer_server = live_server_factory(peer_registry)

    client_registry = PeerRegistry(self_id='osint-en', self_url='')
    client_registry.add_peer('osint-fr', peer_server.url, lang='fr')
    client_registry._peers['osint-fr']['keywords'] = {'ukraine'}

    results = client_registry.mesh_search('ukraine', mode='fast')

    assert results[0]['url'] == 'https://example.org/a'


def test_sanitize_remote_result_does_not_mutate_input():
    original = {'title': 'x', 'score': 1, 'url': 'javascript:alert(1)'}
    PeerRegistry._sanitize_remote_result(original)
    assert original['url'] == 'javascript:alert(1)'  # pas modifié en place


# -- get_mesh_registry() (accès public au registre en place) ----------------

def test_get_mesh_registry_returns_the_same_cached_instance(app_factory):
    from sphinxcontrib.osint.mesh.routes import get_mesh_registry

    registry = PeerRegistry(self_id='osint-en', self_url='')
    app = app_factory(registry)

    with app.test_request_context():
        assert get_mesh_registry() is registry


# -- /mesh/v1/admin/sync ------------------------------------------------------

def test_admin_sync_requires_token_env_var(app_factory, monkeypatch):
    monkeypatch.delenv('OSINT_ADMIN_TOKEN', raising=False)
    registry = PeerRegistry(self_id='osint-en', self_url='')
    app = app_factory(registry)

    resp = app.test_client().post('/mesh/v1/admin/sync')

    assert resp.status_code == 404  # endpoint désactivé sans jeton configuré


def test_admin_sync_rejects_wrong_token(app_factory, monkeypatch):
    monkeypatch.setenv('OSINT_ADMIN_TOKEN', 'correct-token')
    registry = PeerRegistry(self_id='osint-en', self_url='')
    app = app_factory(registry)

    resp = app.test_client().post('/mesh/v1/admin/sync', headers={'X-Admin-Token': 'wrong'})

    assert resp.status_code == 403


def test_admin_sync_syncs_the_live_registry(app_factory, monkeypatch, live_server_factory):
    monkeypatch.setenv('OSINT_ADMIN_TOKEN', 'correct-token')

    peer_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr')
    peer_registry.set_local_keywords(['ukraine'])
    peer_server = live_server_factory(peer_registry)

    live_registry = PeerRegistry(self_id='osint-en', self_url='')
    live_registry.add_peer('osint-fr', peer_server.url, lang='fr')
    app = app_factory(live_registry)

    resp = app.test_client().post('/mesh/v1/admin/sync', headers={'X-Admin-Token': 'correct-token'})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['peers'] == {'osint-fr': True}
    # c'est bien LE MÊME registre (celui de current_app.extensions) qui a
    # été mis à jour, pas une copie -- la synchro doit être visible après coup.
    assert live_registry.known_peers()['osint-fr']['keywords'] == {'ukraine'}
