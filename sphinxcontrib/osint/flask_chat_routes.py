# -*- encoding: utf-8 -*-
"""
Flask routes for the osint chat agents (medor / Octopus).

IMPORTANT: this module gets imported at `sphinx-build` time (through
`setup()` -> `.flask` -> here), long before any Flask app - or a request
context - exists. So nothing here may run at import time: no config
access, no network client construction (Redis, OwebuiAPI...). Everything
is built lazily, on the first request, from
`current_app.config['SPHINX'].config` (the Sphinx `Config` object,
stashed there when the Flask app was created), and cached on the Flask
app itself via `current_app.extensions['osint_chat']` - the standard
Flask-extension pattern for "build once per app, not once per request".

Per-visitor history, no login: each browser gets an anonymous, opaque
random id in an httponly cookie (NOT a user account - just enough to
group messages from the same visitor). History itself lives in Redis
with a TTL, so it's purged automatically without a cron job.
"""
import logging
import secrets
import threading

import requests
from flask import Blueprint, request, jsonify, current_app

from .webuichat import WebuiChat
from .chat_history_store import RedisHistoryStore

logger = logging.getLogger(__name__)

chat_bp = Blueprint('osint_chat', __name__)

#: how many turns (user+assistant pairs) of history to keep per conversation
MAX_HISTORY_TURNS = 10
#: name of the anonymous visitor-id cookie
VISITOR_COOKIE = 'osint_chat_vid'

# Guards the lazy build below against two requests racing to initialize
# the same Flask app's chat state concurrently (Flask can be multi-threaded).
_init_lock = threading.Lock()


def _sphinx_config():
    """The Sphinx `Config` object for this app, as stashed by whoever
    created the Flask app (`app.config['SPHINX']` is the Sphinx `Sphinx`
    instance itself, `.config` is its `Config` object).
    """
    return current_app.config['SPHINX'].config


def _build_redis_client(cfg):
    # Deferred on purpose: `redis` is only needed once a chat route is
    # actually hit, never by `sphinx-build` itself - a machine that only
    # builds the docs doesn't need the package installed at all.
    try:
        import redis
    except ImportError as exc:
        raise ImportError(
            "The 'redis' package is required to run the chat routes "
            "(pip install redis) - it is NOT required to build the docs."
        ) from exc
    return redis.Redis(
        host=cfg.osint_flask_redis_host,
        port=cfg.osint_flask_redis_port,
        db=cfg.osint_flask_redis_db,
        password=cfg.osint_flask_redis_password,
    )


def _get_chat_state():
    """Return (building it once, on first use) this Flask app's
    `{'chat': WebuiChat, 'history': RedisHistoryStore, 'ttl': int}`.
    """
    state = current_app.extensions.get('osint_chat')
    if state is not None:
        return state

    with _init_lock:
        state = current_app.extensions.get('osint_chat')
        if state is not None:  # another thread/request built it meanwhile
            return state

        cfg = _sphinx_config()
        chat = WebuiChat(
            url=cfg.osint_webui_chat_url,
            token=cfg.osint_webui_chat_token,
            knowledge=cfg.osint_webui_chat_knowledge,
            prompts=cfg.osint_webui_chat_prompts,
            # Kept well below gunicorn's own --timeout on purpose - see
            # the osint_webui_chat_read_timeout config value docstring in
            # plugins/webui.py - so a slow model reply surfaces as a clean
            # 502 from the chat route instead of gunicorn SIGKILLing the
            # worker mid-request.
            connect_timeout=cfg.osint_webui_chat_connect_timeout,
            read_timeout=cfg.osint_webui_chat_read_timeout,
        )
        history = RedisHistoryStore(_build_redis_client(cfg), ttl=cfg.osint_webui_chat_history_ttl,
            prefix=cfg.osint_webui_chat_redis_prefix)
        state = {'chat': chat, 'history': history, 'ttl': cfg.osint_webui_chat_history_ttl}
        current_app.extensions['osint_chat'] = state
        return state


def _visitor_id():
    """Return the caller's anonymous visitor id, generating one if absent.

    Not tied to any account - just random bytes so different browsers
    don't share history. Safe to ignore/clear client-side at any time; the
    server-side history for an unknown id is simply empty.
    """
    vid = request.cookies.get(VISITOR_COOKIE)
    if not vid:
        vid = secrets.token_urlsafe(24)
    return vid


def _set_visitor_cookie(response, vid, ttl):
    response.set_cookie(
        VISITOR_COOKIE, vid,
        max_age=ttl,
        httponly=True,
        samesite='Lax',
        # secure=True,  # uncomment once served over https
    )


@chat_bp.route('/chat/<agent>/<knowledge>', methods=['POST'])
def chat(agent, knowledge):
    payload = request.get_json(silent=True) or {}
    question = payload.get('question')
    if not question:
        return jsonify(error='missing "question"'), 400

    state = _get_chat_state()
    vid = _visitor_id()
    history_key = f'{vid}:{agent}:{knowledge}'
    history = state['history'].get(history_key)

    try:
        status, answer = state['chat'].ask(agent, knowledge, question, history=history)
    except KeyError as exc:
        # unknown agent or knowledge name -> client error, not a backend failure
        return jsonify(error=str(exc)), 404
    except requests.exceptions.RequestException as exc:
        # connect/read timeout, connection refused, etc. - the point of
        # osint_webui_chat_read_timeout being set well below gunicorn's own
        # --timeout is precisely so we land here with a clean response
        # instead of gunicorn SIGKILLing the worker mid-request.
        logger.error('Chat backend unreachable for agent=%s knowledge=%s: %s', agent, knowledge, exc)
        return jsonify(error='chat backend error'), 502

    if status is not True:
        logger.error('Chat backend error for agent=%s knowledge=%s: %s', agent, knowledge, answer)
        return jsonify(error='chat backend error'), 502

    history = history + [
        {'role': 'user', 'content': question},
        {'role': 'assistant', 'content': answer},
    ]
    state['history'].set(history_key, history[-(2 * MAX_HISTORY_TURNS):])

    resp = jsonify(answer=answer)
    _set_visitor_cookie(resp, vid, state['ttl'])
    return resp


@chat_bp.route('/chat/<agent>/<knowledge>/reset', methods=['POST'])
def chat_reset(agent, knowledge):
    state = _get_chat_state()
    vid = _visitor_id()
    state['history'].delete(f'{vid}:{agent}:{knowledge}')
    return '', 204
