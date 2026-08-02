# -*- encoding: utf-8 -*-
"""
Agrégation des résultats entre pairs
----------------------------------------

Ce module ne dépend d'aucun transport réseau ni de la recherche mesh
elle-même (pas encore construite à ce stade, cf. INTEGRATION.md) -- il
prend en entrée des résultats de recherche déjà obtenus, un par pair, et
produit un classement unique. Pensé pour être branché tel quel le jour où
`/mesh/v1/search` existera : chaque appel à un pair renverra une liste de
résultats avec un score Xapian brut, et c'est ce module qui les fusionne.

Le problème qu'il résout (cf. discussion "agrégation des scores") : le
score/poids qu'un `xapian.MSet` renvoie dépend du vocabulaire et de la
taille du corpus de CE serveur -- un score de 8.3 sur un petit index très
ciblé n'a rien de comparable à un score de 8.3 sur un gros index
généraliste. Comparer les scores bruts entre pairs reviendrait à trier
des pommes et des oranges.

La correction : normaliser les scores DE CHAQUE PAIR à l'intérieur de son
propre lot de résultats (ils sont, eux, comparables entre eux -- même
index, même requête) avant de fusionner. Deux méthodes, choisies au cas
par cas :

- 'minmax' (défaut) : score ramené entre 0 et 1 par rapport au meilleur
  et au moins bon résultat *de ce pair pour cette requête*. Garde une
  notion de "à quel point ce résultat est net par rapport aux autres
  résultats de ce même pair" -- utile si un pair renvoie un seul résultat
  très pertinent quand un autre en renvoie cinquante moyens.
- 'rank' : uniquement la position dans le classement de ce pair, sans
  tenir compte de l'écart de score. Plus robuste si les scores bruts de
  deux pairs ne sont vraiment pas sur la même échelle (moteurs de
  pondération différents, etc.), au prix de perdre l'info "ce résultat
  est BEAUCOUP mieux que le second" au sein d'un même pair.

Aucune des deux ne prétend donner un score de pertinence globalement
"vrai" -- l'objectif est un ordre de présentation raisonnable, pas une
vérité statistique.
"""
from __future__ import annotations


def _normalize_minmax(results):
    scores = [r.get('score', 0) or 0 for r in results]
    lo, hi = min(scores), max(scores)
    span = hi - lo
    normalized = []
    for r, score in zip(results, scores):
        value = 1.0 if span == 0 else (score - lo) / span
        normalized.append(dict(r, normalized_score=value))
    return normalized


def _normalize_rank(results):
    # trié par score brut décroissant d'abord -- on ne suppose pas que
    # l'appelant a déjà trié ses résultats.
    ordered = sorted(range(len(results)), key=lambda i: results[i].get('score', 0) or 0, reverse=True)
    n = len(results)
    normalized = [None] * n
    for rank, idx in enumerate(ordered):
        value = 1.0 if n == 1 else 1.0 - (rank / (n - 1))
        normalized[idx] = dict(results[idx], normalized_score=value)
    return normalized


_METHODS = {
    'minmax': _normalize_minmax,
    'rank': _normalize_rank,
}


def normalize_peer_scores(results, method='minmax'):
    """Ajoute `normalized_score` (float, 0..1) à chaque résultat d'UN
    pair, calculé uniquement par rapport aux autres résultats de ce même
    pair. Ne modifie pas `results` en place -- retourne de nouveaux dicts.

    `results` : liste de dicts avec au moins une clé `score` (le poids
    Xapian brut). Les autres clés (titre, url, id...) sont conservées
    telles quelles.
    """
    if not results:
        return []
    try:
        normalize_fn = _METHODS[method]
    except KeyError:
        raise ValueError(f"méthode de normalisation inconnue: {method!r} (attendu: {sorted(_METHODS)})")
    return normalize_fn(results)


def aggregate_results(results_by_peer, method='minmax', limit=None):
    """Fusionne les résultats de plusieurs pairs en un seul classement.

    Args:
        results_by_peer: {peer_id: [résultat, ...]} -- un lot de
            résultats bruts (non normalisés) par pair, typiquement ce que
            renverrait chaque appel à `/mesh/v1/search` (à venir).
        method: 'minmax' (défaut) ou 'rank', cf. docstring du module.
        limit: nombre maximum de résultats retournés (après fusion et
            tri), ou None pour tout garder.

    Returns:
        Liste de résultats triée par `normalized_score` décroissant,
        chacun enrichi de `peer_id` (pour savoir d'où il vient) et
        `normalized_score`. Un pair qui n'a renvoyé aucun résultat est
        simplement absent du résultat final -- pas d'entrée vide.

    Ne déduplique PAS les résultats qui référenceraient la même entité
    réelle chez deux pairs différents (mirrors) -- il n'existe pas
    aujourd'hui d'identifiant d'entité partagé de façon fiable à travers
    le mesh pour détecter ça. Laissé pour une itération ultérieure si le
    besoin se confirme.
    """
    merged = []
    for peer_id, results in results_by_peer.items():
        for result in normalize_peer_scores(results, method=method):
            merged.append(dict(result, peer_id=peer_id))

    merged.sort(key=lambda r: r['normalized_score'], reverse=True)

    if limit is not None:
        merged = merged[:limit]
    return merged
