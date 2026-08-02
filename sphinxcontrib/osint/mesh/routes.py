# -*- encoding: utf-8 -*-
"""
Routes Flask pour le mesh (/mesh/v1)
---------------------------------------

IMPORTANT (même remarque que flask_chat_routes.py) : ce module est
importé au moment du `sphinx-build`, avant qu'une app Flask - ou un
contexte de requête - n'existe. Donc rien ici ne doit s'exécuter à
l'import : le PeerRegistry est construit paresseusement, à la première
requête, à partir de `current_app.config['SPHINX'].config`
(`osint_mesh_*`), et mis en cache sur `current_app.extensions['osint_mesh']`.

Pour les tests (ou tout usage hors app Sphinx complète), on peut aussi
injecter directement `app.extensions['osint_mesh'] = {'registry': ...}`
avant la première requête : `_get_mesh_state()` court-circuite alors la
construction paresseuse et utilise ce qui a été fourni. C'est exactement
le point d'extension utilisé par les tests de ce module (cf. tests/).
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, request

from .registry import MESH_TOKEN_HEADER, PeerRegistry
from .translation_memory import TranslationMemory

logger = logging.getLogger(__name__)

mesh_bp = Blueprint('osint_mesh', __name__, url_prefix='/mesh/v1')

_init_lock = threading.Lock()


def _sphinx_config():
    return current_app.config['SPHINX'].config


def _build_registry(cfg):
    registry = PeerRegistry(
        self_id=cfg.osint_mesh_peer_id,
        self_url=cfg.osint_mesh_self_url,
        # osint_mesh_lang est la langue "annoncée" (route /info) ; si elle
        # n'est pas configurée explicitement, on retombe sur la langue
        # réelle de l'index (osint_text_translate) -- c'est celle-là qui
        # compte pour savoir depuis quelle langue traduire les mots-clés.
        lang=cfg.osint_mesh_lang or getattr(cfg, 'osint_text_translate', None),
        xapian_dir=current_app.config.get('UPLOAD_XAPIAN'),
        keywords_limit=cfg.osint_mesh_keywords_limit,
        keywords_min_length=cfg.osint_mesh_keywords_min_length,
        entities_limit=getattr(cfg, 'osint_mesh_entities_limit', 500),
        secret=cfg.osint_mesh_secret,
        timeout=cfg.osint_mesh_sync_timeout,
        translate_keywords=getattr(cfg, 'osint_mesh_keywords_translate', True),
        translation_memory=TranslationMemory(getattr(cfg, 'osint_mesh_translation_memory', '') or None),
    )
    if cfg.osint_mesh_bootstrap:
        registry.load_bootstrap(cfg.osint_mesh_bootstrap)
    return registry


def _get_mesh_state():
    """Retourne (en la construisant une seule fois par app) l'état mesh de
    cette app Flask : `{'registry': PeerRegistry}`.
    """
    state = current_app.extensions.get('osint_mesh')
    if state is not None:
        return state

    with _init_lock:
        state = current_app.extensions.get('osint_mesh')
        if state is not None:  # un autre thread/requête l'a construit entre-temps
            return state

        registry = _build_registry(_sphinx_config())
        state = {'registry': registry}
        current_app.extensions['osint_mesh'] = state
        return state


def get_mesh_registry():
    """Point d'accès PUBLIC au PeerRegistry de cette app -- le même objet
    que celui utilisé par les routes /mesh/v1/* et /mesh/v1/admin/sync
    (construit une fois, mis en cache sur current_app.extensions).

    Pensé pour être appelé depuis d'AUTRES routes de l'app (typiquement
    /searchmesh.html dans flask.py, cf. INTEGRATION.md) sans dupliquer la
    logique de construction paresseuse -- et surtout pour que ces routes
    voient le même registre que celui rafraîchi par /mesh/v1/admin/sync,
    pas une copie indépendante qui resterait figée.

    Lève la même ValueError que le constructeur de PeerRegistry si le
    mesh n'est pas configuré (osint_mesh_peer_id manquant) -- à
    l'appelant de décider comment l'afficher (cf. searchmesh() dans
    flask.py qui l'attrape pour afficher un message plutôt que planter).
    """
    return _get_mesh_state()['registry']


def _require_mesh_token(view):
    """Si un secret mesh est configuré, exige l'en-tête X-Mesh-Token pour
    accéder à la route. Sans secret configuré, le mesh est ouvert (utile
    en développement local / réseau de confiance fermé).
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        registry = _get_mesh_state()['registry']
        if registry.secret:
            token = request.headers.get(MESH_TOKEN_HEADER, '')
            if not hmac.compare_digest(token, registry.secret):
                return jsonify(error='jeton mesh manquant ou invalide'), 401
        return view(*args, **kwargs)
    return wrapped


def _require_admin_token(view):
    """Protège une route d'ADMINISTRATION mesh avec le même jeton que
    `/admin/reload` déjà présent dans flask.py (variable d'environnement
    `OSINT_ADMIN_TOKEN`, en-tête `X-Admin-Token` ou paramètre `token`) --
    on lit directement la variable d'environnement plutôt que d'importer
    la constante ADMIN_TOKEN de flask.py, pour éviter un import circulaire
    (flask.py importe ce module pour enregistrer le blueprint).

    Volontairement un jeton DIFFÉRENT de `osint_mesh_secret` (qui
    authentifie les appels ENTRE PAIRS) : ce n'est pas le même périmètre
    de confiance. `osint_mesh_secret` dit "un autre serveur du mesh a le
    droit de m'interroger" ; `OSINT_ADMIN_TOKEN` dit "la personne qui
    opère CE déploiement a le droit de déclencher une tâche
    d'administration dessus" -- même si en pratique les deux finissent
    souvent appelés depuis la même infra (le timer systemd), ce sont deux
    questions différentes et les mélanger rendrait la rotation d'un
    secret sans l'autre plus difficile.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin_token = os.environ.get('OSINT_ADMIN_TOKEN')
        if not admin_token:
            abort(404)
        supplied = request.headers.get('X-Admin-Token') or request.args.get('token', '')
        if not supplied or not hmac.compare_digest(supplied, admin_token):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@mesh_bp.route('/admin/sync', methods=['POST'])
@_require_admin_token
def admin_sync():
    """Synchronise EN PLACE le PeerRegistry de CETTE app Flask (celui mis
    en cache sur `current_app.extensions`, cf. `_get_mesh_state`).

    C'est distinct de la commande CLI `mesh-sync` : la CLI construit son
    propre PeerRegistry jetable dans un process séparé -- la synchroniser
    ne met à jour QUE ce process CLI éphémère, jamais le registre utilisé
    par cette app Flask pour répondre aux vraies requêtes de recherche
    mesh. C'est CET endpoint qu'il faut appeler périodiquement (timer
    systemd, cf. INTEGRATION.md) pour que les recherches réellement
    servies par cette app voient des pairs/mots-clés à jour.
    """
    registry = _get_mesh_state()['registry']
    results = registry.sync_all()
    failed = [peer_id for peer_id, ok in results.items() if not ok]
    return jsonify(status='ok', peers=results, failed=failed)


@mesh_bp.route('/info')
@_require_mesh_token
def info():
    """Identité de ce serveur : de quoi être ajouté au carnet d'un pair."""
    registry = _get_mesh_state()['registry']
    return jsonify(id=registry.self_id, url=registry.self_url, lang=registry.lang)


@mesh_bp.route('/keywords')
@_require_mesh_token
def keywords():
    """Mots-clés publiés par ce serveur : `keywords` (vocabulaire traduit
    vers PIVOT_LANG, cf. registry.py) + `entities` (libellés canoniques
    d'entités -- titres/altlabels, volontairement non traduits).
    """
    registry = _get_mesh_state()['registry']
    kws, generated_at = registry.local_keywords()
    entities, entities_generated_at = registry.local_entities()
    return jsonify(
        peer_id=registry.self_id,
        keywords=kws,
        generated_at=generated_at,
        entities=entities,
        entities_generated_at=entities_generated_at,
    )


@mesh_bp.route('/peers')
@_require_mesh_token
def peers():
    """Carnet d'adresses connu par ce serveur (nous compris) -- permet à un
    pair de découvrir des pairs de pairs sans passer par un serveur central.
    """
    registry = _get_mesh_state()['registry']
    return jsonify(peers=registry.known_peers_public())


@mesh_bp.route('/search', methods=['POST'])
@_require_mesh_token
def search():
    """Recherche locale, appelée par un pair (jamais relayée à d'autres
    pairs -- mesh à un saut, cf. registry.py). Requête et résultats sont
    en anglais (PIVOT_LANG), traduits à la frontière côté serveur.

    Payload attendu : `{"q": "ukraine sanctions", "limit": 10}`.
    """
    registry = _get_mesh_state()['registry']
    payload = request.get_json(silent=True) or {}
    query = (payload.get('q') or '').strip()
    if not query:
        return jsonify(error='paramètre "q" manquant ou vide'), 400

    try:
        limit = int(payload.get('limit', 10))
    except (TypeError, ValueError):
        limit = 10
    # borne raisonnable : un pair ne doit pas pouvoir faire demander à un
    # autre un nombre de résultats arbitrairement grand.
    limit = max(1, min(limit, 50))

    results = registry.local_search(query, limit=limit)
    return jsonify(peer_id=registry.self_id, query=query, results=results)
