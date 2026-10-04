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
            # Recherche sémantique (cf. semanticlib.py). Désactivée tant que
            # osint_xapian_embedder vaut None. Valeurs possibles:
            #   'ollama:bge-m3'                      (modèle servi par Ollama)
            #   'ollama:bge-m3@http://hote:11434'    (avec l'URL dans la valeur)
            #   'lemonade:nomic-embed-text-v1-GGUF'  (serveur Lemonade, API OpenAI)
            #   'st:intfloat/multilingual-e5-base'   (sentence-transformers local)
            # Changer de modèle recalcule tous les vecteurs à l'indexation suivante.
            ('osint_xapian_embedder', None, ''),
            # URL du serveur Ollama (recherche sémantique et scripts/bs_detect.py)
            # (ex: 'http://host.docker.internal:11434' ou
            # 'http://ollama:11434'). Défaut: http://127.0.0.1:11434. Ignorée si
            # l'URL est déjà donnée après '@' dans osint_xapian_embedder.
            ('osint_ollama_url', None, ''),
            # URL de base de l'API du serveur Lemonade (embedder 'lemonade:...' et
            # scripts/bs_detect.py --backend lemonade),
            # selon la version: 'http://127.0.0.1:13305/v1' (défaut) ou
            # 'http://127.0.0.1:8000/api/v1'. Ignorée si l'URL est donnée après '@'.
            # Seuls les modèles llamacpp/flm gèrent les embeddings (pas ONNX/OGA).
            ('osint_lemonade_url', None, ''),
            # Calcul des embeddings sur un serveur distant (embedders ollama:/lemonade:).
            # osint_xapian_embed_batch: textes par requête (défaut 32; 64 si le serveur a la
            # mémoire, 16 s'il sature). osint_xapian_embed_workers: requêtes envoyées en
            # parallèle (défaut 2; 1 = séquentiel). Le serveur doit les traiter en
            # parallèle pour que ça serve (OLLAMA_NUM_PARALLEL pour Ollama, --parallel
            # pour Lemonade/llama.cpp); sinon les requêtes s'empilent sans gain.
            # Changer ces valeurs ne recalcule pas les vecteurs déjà indexés.
            ('osint_xapian_embed_batch', None, ''),
            ('osint_xapian_embed_workers', None, ''),
            # Durée de maintien du modèle d'embedding en mémoire côté Ollama après la
            # dernière requête (keep_alive de /api/embed): '30m' (défaut), '1h', 3600
            # (secondes) ou -1 (jamais déchargé). Le défaut d'Ollama est 5 minutes.
            # Pour qu'un modèle de chat (ex. scripts/bs_detect.py) n'éjecte pas le
            # modèle d'embedding, autoriser 2 modèles chargés côté serveur:
            # OLLAMA_MAX_LOADED_MODELS=2 (variable d'environnement d'Ollama).
            ('osint_ollama_keep_alive', None, ''),
        ]
