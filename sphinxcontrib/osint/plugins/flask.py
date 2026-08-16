# -*- encoding: utf-8 -*-
"""
The flask plugin
----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import sys
import io
import json
import time
import logging
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..osintlib import OSIntCountry, OSIntCity, OSIntOrg, OSIntIdent, OSIntEvent
from ..owebuilib import OwebuiAPI, AdaptiveConcurrency
from . import Plugin

logger = logging.getLogger(__name__)


class Flask(Plugin):
    """Sphinx-osint plugin for holding conf values."""

    name = 'flask'
    order = 10
    category = 'flask'

    @classmethod
    def config_values(cls):
        return [
            # Redis connection shared by the per-visitor chat history store
            # (chat_history_store.py) and the Flask-Caching HTTP cache
            # (flask.py) - same instance/db, so each consumer gets its own
            # key prefix below to avoid ever colliding on the same keys.
            ('osint_jssearch_enabled', False, 'html'),
            ('osint_xapian_enabled', False, 'html'),
            ('osint_xapian_sidebar_enabled', True, 'html'),
            ('osint_flask_redis_host', '127.0.0.1', ''),
            ('osint_flask_redis_port', 6379, ''),
            ('osint_flask_redis_db', 0, ''),
            ('osint_flask_redis_password', None, ''),
            ('osint_flask_cache_redis_prefix', 'osint_cache:', ''),
        ]
