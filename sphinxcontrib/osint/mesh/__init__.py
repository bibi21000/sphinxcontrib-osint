# -*- encoding: utf-8 -*-
"""
Mesh network (/mesh/v1)
------------------------

Réseau mesh à plat (un saut, pas de relais/gossip) entre serveurs
sphinxcontrib-osint : découverte des pairs à partir d'un fichier bootstrap
JSON, et échange des mots-clés que chaque serveur indexe localement (utile
plus tard pour router une recherche rapide vers les seuls pairs pertinents).

Ce sous-module ne contient volontairement que la synchronisation
(découverte + mots-clés). La recherche mesh proprement dite (fast/deep
search) viendra dans une étape suivante, une fois cette base posée.
"""
from __future__ import annotations

from .aggregation import aggregate_results, normalize_peer_scores
from .keywords import extract_canonical_labels, extract_top_terms
from .registry import PeerRegistry
from .routes import get_mesh_registry, mesh_bp
from .translation_memory import TranslationMemory

__all__ = [
    'mesh_bp', 'PeerRegistry', 'extract_top_terms', 'extract_canonical_labels',
    'TranslationMemory', 'aggregate_results', 'normalize_peer_scores', 'get_mesh_registry',
]
