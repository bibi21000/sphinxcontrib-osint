# -*- encoding: utf-8 -*-
"""
Tests d'intégration : deux (ou trois) "serveurs" mesh réels -- vrais
sockets sur 127.0.0.1, dans des threads -- qui se synchronisent via
/mesh/v1/* en HTTP, comme ils le feraient en production. Pas de mock de
`requests` : on teste le vrai comportement réseau, y compris les échecs.
"""
from sphinxcontrib.osint.mesh.registry import PeerRegistry


def test_sync_peer_fetches_keywords_and_lang(live_server_factory):
    peer_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr')
    peer_registry.set_local_keywords(['ukraine', 'sanctions', 'kyiv'])
    peer_server = live_server_factory(peer_registry)

    client_registry = PeerRegistry(self_id='osint-en', self_url='')
    client_registry.add_peer('osint-fr', peer_server.url, lang='fr', source='bootstrap')

    ok = client_registry.sync_peer('osint-fr')

    assert ok is True
    known = client_registry.known_peers()['osint-fr']
    assert known['lang'] == 'fr'
    assert known['keywords'] == {'ukraine', 'sanctions', 'kyiv'}
    assert known['keywords_at'] is not None


def test_sync_peer_fetches_entities_lowercased(live_server_factory):
    peer_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr')
    peer_registry.set_local_entities(['Volodymyr Zelensky', 'Kyiv'])
    peer_server = live_server_factory(peer_registry)

    client_registry = PeerRegistry(self_id='osint-en', self_url='')
    client_registry.add_peer('osint-fr', peer_server.url, lang='fr', source='bootstrap')

    client_registry.sync_peer('osint-fr')

    known = client_registry.known_peers()['osint-fr']
    # casse d'origine publiée par le pair, mais normalisée en local pour
    # un matching insensible à la casse
    assert known['entities'] == {'volodymyr zelensky', 'kyiv'}
    assert known['entities_at'] is not None


def test_sync_peer_discovers_peers_of_peers(live_server_factory):
    # osint-de est connu par osint-fr mais pas encore par osint-en :
    # après synchro avec osint-fr, osint-en doit l'avoir appris.
    fr_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr')
    fr_server = live_server_factory(fr_registry)
    fr_registry.self_url = fr_server.url  # pour qu'il s'annonce avec la bonne URL
    fr_registry.add_peer('osint-de', 'http://osint-de.invalid', lang='de', source='bootstrap')

    en_registry = PeerRegistry(self_id='osint-en', self_url='')
    en_registry.add_peer('osint-fr', fr_server.url, lang='fr', source='bootstrap')

    en_registry.sync_peer('osint-fr')

    known = en_registry.known_peers()
    assert 'osint-de' in known
    assert known['osint-de']['url'] == 'http://osint-de.invalid'
    assert known['osint-de']['source'] == 'peer'  # découvert, pas dans le bootstrap d'origine


def test_sync_peer_self_is_never_added_back():
    # osint-fr nous renvoie potentiellement notre propre entrée dans sa
    # liste de pairs (on est l'un de ses pairs) -- add_peer doit l'ignorer.
    registry = PeerRegistry(self_id='osint-en', self_url='http://osint-en.example.org')
    registry.add_peer('osint-en', 'http://osint-en.example.org')

    assert 'osint-en' not in registry.known_peers()


def test_sync_peer_handles_unreachable_peer_gracefully():
    registry = PeerRegistry(self_id='osint-en', self_url='', timeout=1)
    # port 1 : personne n'y écoute -> connexion refusée rapidement
    registry.add_peer('osint-down', 'http://127.0.0.1:1', lang='fr', source='bootstrap')

    ok = registry.sync_peer('osint-down')

    assert ok is False
    # le pair reste dans le carnet, juste avec des mots-clés non rafraîchis
    assert 'osint-down' in registry.known_peers()
    assert registry.known_peers()['osint-down']['keywords'] == set()


def test_sync_all_continues_after_one_peer_fails(live_server_factory):
    good_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr')
    good_registry.set_local_keywords(['ukraine'])
    good_server = live_server_factory(good_registry)

    client_registry = PeerRegistry(self_id='osint-en', self_url='', timeout=1)
    client_registry.add_peer('osint-fr', good_server.url, lang='fr', source='bootstrap')
    client_registry.add_peer('osint-down', 'http://127.0.0.1:1', lang='fr', source='bootstrap')

    results = client_registry.sync_all()

    assert results == {'osint-fr': True, 'osint-down': False}
    assert client_registry.known_peers()['osint-fr']['keywords'] == {'ukraine'}


def test_auth_between_peers_with_shared_secret(live_server_factory):
    peer_registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr', secret='s3cret')
    peer_registry.set_local_keywords(['ukraine'])
    peer_server = live_server_factory(peer_registry)

    # secret manquant côté client -> le pair distant refuse (401), sync_peer
    # doit voir ça comme un échec propre, pas planter.
    wrong_registry = PeerRegistry(self_id='osint-en', self_url='', secret='')
    wrong_registry.add_peer('osint-fr', peer_server.url, lang='fr', source='bootstrap')
    assert wrong_registry.sync_peer('osint-fr') is False

    good_registry = PeerRegistry(self_id='osint-en', self_url='', secret='s3cret')
    good_registry.add_peer('osint-fr', peer_server.url, lang='fr', source='bootstrap')
    assert good_registry.sync_peer('osint-fr') is True
