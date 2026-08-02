# -*- encoding: utf-8 -*-
"""
Tests de la recherche mesh (local_search / mesh_search / sélection des
pairs), avec `local_search_fn` injecté -- pas besoin de base Xapian réelle
ici, cf. test_mesh_search_xapian.py pour l'implémentation réelle.
"""
from sphinxcontrib.osint.mesh.registry import PeerRegistry


def _registry(**kwargs):
    kwargs.setdefault('self_id', 'osint-en')
    kwargs.setdefault('self_url', '')
    return PeerRegistry(**kwargs)


# -- local_search délégation -------------------------------------------------

def test_local_search_uses_injected_fn():
    def fake_search(query, limit):
        return [{'title': f'result for {query}', 'score': 42}]

    registry = _registry(local_search_fn=fake_search)

    results = registry.local_search('ukraine', limit=5)

    assert results == [{'title': 'result for ukraine', 'score': 42}]


def test_local_search_without_xapian_dir_and_without_injection_returns_empty():
    registry = _registry()  # ni local_search_fn ni xapian_dir
    assert registry.local_search('ukraine') == []


# -- _select_peers_for_query --------------------------------------------------

def test_select_peers_matches_on_keywords():
    registry = _registry()
    registry.add_peer('osint-fr', 'http://fr.example', 'fr')
    registry._peers['osint-fr']['keywords'] = {'ukraine', 'sanctions'}

    registry.add_peer('osint-de', 'http://de.example', 'de')
    registry._peers['osint-de']['keywords'] = {'election', 'economy'}

    selected = registry._select_peers_for_query('ukraine sanctions news')

    assert selected == ['osint-fr']


def test_select_peers_matches_on_entity_words():
    registry = _registry()
    registry.add_peer('osint-fr', 'http://fr.example', 'fr')
    registry._peers['osint-fr']['entities'] = {'volodymyr zelensky'}

    selected = registry._select_peers_for_query('zelensky speech')

    assert selected == ['osint-fr']


def test_select_peers_returns_empty_for_empty_query():
    registry = _registry()
    registry.add_peer('osint-fr', 'http://fr.example', 'fr')
    registry._peers['osint-fr']['keywords'] = {'ukraine'}

    assert registry._select_peers_for_query('   ') == []


def test_select_peers_no_match_returns_empty():
    registry = _registry()
    registry.add_peer('osint-fr', 'http://fr.example', 'fr')
    registry._peers['osint-fr']['keywords'] = {'election'}

    assert registry._select_peers_for_query('ukraine sanctions') == []


# -- mesh_search : fan-out + agrégation, pairs simulés via local_search_fn ---
# (on n'utilise volontairement pas de vrai réseau ici -- ça, c'est
# test_mesh_search_integration.py. Ici on teste juste la logique de
# sélection + agrégation en substituant _search_peer.)

def test_mesh_search_always_includes_self():
    registry = _registry(local_search_fn=lambda q, limit: [{'title': 'self result', 'score': 5}])
    results = registry.mesh_search('ukraine', mode='fast')
    assert any(r['peer_id'] == 'osint-en' for r in results)


def test_mesh_search_fast_mode_skips_unmatching_peers(monkeypatch):
    registry = _registry(local_search_fn=lambda q, limit: [])
    registry.add_peer('osint-fr', 'http://fr.example', 'fr')
    registry._peers['osint-fr']['keywords'] = {'election'}  # ne matche pas "ukraine"

    calls = []

    def fake_search_peer(peer_id, query, limit):
        calls.append(peer_id)
        return [{'title': 'should not be called', 'score': 1}]

    registry._search_peer = fake_search_peer

    registry.mesh_search('ukraine', mode='fast')

    assert calls == []  # osint-fr jamais interrogé, ses mots-clés ne matchent pas


def test_mesh_search_deep_mode_queries_all_peers_regardless_of_keywords():
    registry = _registry(local_search_fn=lambda q, limit: [])
    registry.add_peer('osint-fr', 'http://fr.example', 'fr')
    registry._peers['osint-fr']['keywords'] = {'election'}  # ne matcherait pas en mode fast

    calls = []

    def fake_search_peer(peer_id, query, limit):
        calls.append(peer_id)
        return [{'title': 'ok', 'score': 1}]

    registry._search_peer = fake_search_peer

    registry.mesh_search('ukraine', mode='deep')

    assert calls == ['osint-fr']


def test_mesh_search_merges_and_sorts_results():
    registry = _registry(local_search_fn=lambda q, limit: [{'title': 'local', 'score': 1}])
    registry.add_peer('osint-fr', 'http://fr.example', 'fr')
    registry._peers['osint-fr']['keywords'] = {'ukraine'}
    registry._search_peer = lambda peer_id, query, limit: [{'title': 'remote', 'score': 100}]

    results = registry.mesh_search('ukraine', mode='fast')

    titles_by_peer = {r['peer_id']: r['title'] for r in results}
    assert titles_by_peer == {'osint-en': 'local', 'osint-fr': 'remote'}


def test_mesh_search_respects_total_limit():
    registry = _registry(local_search_fn=lambda q, limit: [
        {'title': f'r{i}', 'score': float(i)} for i in range(5)
    ])

    results = registry.mesh_search('ukraine', mode='fast', total_limit=2)

    assert len(results) == 2


def test_mesh_search_unreachable_peer_is_silently_skipped():
    registry = _registry(local_search_fn=lambda q, limit: [{'title': 'local', 'score': 1}], timeout=1)
    registry.add_peer('osint-down', 'http://127.0.0.1:1', 'fr')  # port fermé
    registry._peers['osint-down']['keywords'] = {'ukraine'}

    results = registry.mesh_search('ukraine', mode='fast')

    assert [r['peer_id'] for r in results] == ['osint-en']


def test_mesh_search_rejects_unknown_mode():
    registry = _registry(local_search_fn=lambda q, limit: [])
    try:
        registry.mesh_search('ukraine', mode='medium')
        assert False, 'devrait lever ValueError'
    except ValueError:
        pass


# -- parallélisme -------------------------------------------------------------

def test_mesh_search_queries_peers_in_parallel_not_in_series():
    import time

    SLEEP = 0.2
    N_PEERS = 5

    registry = _registry(local_search_fn=lambda q, limit: [])
    for i in range(N_PEERS):
        registry.add_peer(f'osint-{i}', f'http://peer{i}.example', 'fr')
        registry._peers[f'osint-{i}']['keywords'] = {'ukraine'}

    def slow_search_peer(peer_id, query, limit):
        time.sleep(SLEEP)
        return [{'title': peer_id, 'score': 1}]

    registry._search_peer = slow_search_peer

    started = time.monotonic()
    results = registry.mesh_search('ukraine', mode='fast')
    elapsed = time.monotonic() - started

    assert len(results) == N_PEERS
    # en série : >= N_PEERS * SLEEP (1.0s). En parallèle : ~SLEEP (0.2s).
    # Marge large pour rester robuste sur une machine chargée.
    assert elapsed < SLEEP * (N_PEERS / 2), (
        f"trop lent ({elapsed:.2f}s) pour {N_PEERS} pairs à {SLEEP}s chacun -- "
        "semble s'exécuter en série plutôt qu'en parallèle"
    )


def test_mesh_search_survives_a_job_that_raises():
    def local_search_fn(q, limit):
        return [{'title': 'local', 'score': 1}]

    registry = _registry(local_search_fn=local_search_fn)
    registry.add_peer('osint-broken', 'http://broken.example', 'fr')
    registry._peers['osint-broken']['keywords'] = {'ukraine'}

    def raising_search_peer(peer_id, query, limit):
        raise RuntimeError('boom')

    registry._search_peer = raising_search_peer

    results = registry.mesh_search('ukraine', mode='fast')

    assert [r['peer_id'] for r in results] == ['osint-en']  # osint-broken absent, pas d'exception propagée
