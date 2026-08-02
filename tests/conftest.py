# -*- encoding: utf-8 -*-
"""
Fixtures partagées pour les tests du mesh (/mesh/v1).

On ne construit jamais une vraie app Sphinx complète ici (ça demanderait
un `sphinx-build` complet + une base Xapian réelle) : on monte une app
Flask minimale qui ne porte que le blueprint mesh, avec un PeerRegistry
injecté directement dans `app.extensions['osint_mesh']` -- exactement le
même point d'extension que celui utilisé par `_get_mesh_state()` en
production (cf. sphinxcontrib/osint/mesh/routes.py), donc les routes sont
testées telles quelles, sans doublure de la logique de construction.

Pour les tests de synchronisation, `live_server_factory` démarre un vrai
serveur Flask sur 127.0.0.1:<port aléatoire> dans un thread, pour tester
les vrais appels HTTP entre deux "serveurs" plutôt que de mocker requests.
"""
from __future__ import annotations

import threading

import pytest
from flask import Flask
from werkzeug.serving import make_server

from sphinxcontrib.osint.mesh.routes import mesh_bp


def make_app(registry):
    app = Flask(__name__)
    app.register_blueprint(mesh_bp)
    app.extensions['osint_mesh'] = {'registry': registry}
    return app


class LiveServer:
    """Un vrai serveur Flask sur un port local, dans un thread démon."""

    def __init__(self, registry):
        self.registry = registry
        self.app = make_app(registry)
        self.server = make_server('127.0.0.1', 0, self.app)
        self.port = self.server.server_port
        self.url = f'http://127.0.0.1:{self.port}'
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self._thread.join(timeout=5)


@pytest.fixture
def app_factory():
    """Fabrique d'app Flask minimale portant le blueprint mesh."""
    return make_app


@pytest.fixture
def live_server_factory():
    """Fabrique de serveurs mesh réels sur 127.0.0.1. Tous les serveurs
    créés pendant le test sont arrêtés proprement à la fin, même en cas
    d'échec du test.
    """
    servers = []

    def _start(registry):
        srv = LiveServer(registry).start()
        servers.append(srv)
        return srv

    yield _start

    for srv in servers:
        srv.stop()
