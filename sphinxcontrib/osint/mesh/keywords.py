# -*- encoding: utf-8 -*-
"""
Extraction des mots-clés locaux depuis la base Xapian
-------------------------------------------------------

Ce qu'un serveur mesh publie sur /mesh/v1/keywords, c'est simplement les
termes les plus fréquents de son index Xapian local -- ce qui permet à un
pair de décider, sans l'interroger, s'il vaut la peine de lui envoyer une
requête "recherche rapide".

Pourquoi c'est rapide même avec beaucoup de documents : `Database.allterms()`
ne relit pas les documents un par un. C'est un parcours de la liste des
termes déjà triée et indexée par Xapian, et chaque `TermListItem` expose
directement `.termfreq` (le nombre de documents contenant ce terme) sans
recherche supplémentaire -- donc un seul passage, en O(nombre de termes
uniques), pas O(nombre de documents).

Un point d'attention documenté par les bindings Python : `termfreq` est
évalué paresseusement sur l'item courant de l'itérateur, et devient
inaccessible dès qu'on avance à l'item suivant. On le lit donc bien à
l'intérieur de la boucle, avant de passer au terme suivant (cf. boucle
ci-dessous) -- pas après coup sur une liste d'items gardés de côté.

Filtrage : xapianlib.py indexe deux familles de termes bien distinctes :
- du texte libre, via `indexer.index_text(...)` sans préfixe -> ce sont
  des mots simples en minuscules (ex: "ukraine"). C'est ce qu'on veut.
- des termes "structurés" avec un préfixe majuscule collé devant
  (S=titre, D=description, C=catégorie, T=type, R=pays, ... + les termes
  booléens ajoutés par les plugins, + les formes stemmées préfixées "Z"
  générées automatiquement dès qu'un stemmer est configuré).

Comme ces préfixes sont toujours en majuscule alors que le texte libre
est toujours en minuscule, un simple `term.islower()` suffit à ne garder
que le texte libre -- sans avoir à maintenir une liste des préfixes
utilisés par le projet ou ses plugins (qui pourraient en ajouter d'autres
avec le temps).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _decode(term):
    """Les bindings xapian récents renvoient déjà des `str` UTF-8, mais
    certaines versions plus anciennes renvoient des `bytes` -- on gère
    les deux sans avoir besoin de connaître la version installée.
    """
    if isinstance(term, bytes):
        return term.decode('utf-8', errors='ignore')
    return term


def extract_top_terms(db_path, limit=300, min_length=3, stopwords=None):
    """Retourne la liste des `limit` termes les plus fréquents de la base
    Xapian située à `db_path`, triés par fréquence décroissante.

    Args:
        db_path: chemin vers la base Xapian (répertoire).
        limit: nombre maximum de mots-clés retournés.
        min_length: longueur minimale d'un terme pour être retenu (filtre
            les mots trop courts/peu discriminants).
        stopwords: ensemble optionnel de mots à exclure explicitement, en
            plus du filtre structurel décrit ci-dessus.

    Raises:
        Toute exception levée par l'ouverture de la base Xapian (fichier
        absent, base corrompue...) est laissée remonter -- c'est à
        l'appelant (PeerRegistry.local_keywords) de décider quoi faire
        d'un index indisponible.
    """
    import xapian  # import différé : cf. flask_chat_routes.py, on ne veut
    # pas que sphinx-build échoue sur une machine qui n'a pas encore les
    # bindings xapian installés si elle n'utilise pas le mesh.

    stopwords = stopwords or set()
    db = xapian.Database(db_path)
    try:
        terms = []
        for item in db.allterms():
            term = _decode(item.term)
            freq = item.termfreq  # lu ICI, avant que l'itérateur n'avance
            if len(term) < min_length:
                continue
            if not term.isalpha() or not term.islower():
                continue
            if term in stopwords:
                continue
            terms.append((term, freq))
    finally:
        db.close()

    terms.sort(key=lambda t: t[1], reverse=True)
    return [term for term, _freq in terms[:limit]]


def extract_canonical_labels(db_path, limit=None, min_length=2):
    """Retourne les libellés canoniques (titre + altlabels) des entités de
    la base -- des CHAÎNES ENTIÈRES telles que saisies par l'auteur du
    contenu ("Volodymyr Zelensky"), pas des mots isolés comme le fait
    `extract_top_terms` ("volodymyr", "zelensky" séparément).

    Volontairement PAS traduites par l'appelant (cf. PeerRegistry, point
    "noms canoniques" de la conception) : ce sont en général des noms
    propres, souvent stables d'une langue à l'autre ou déjà multilingues
    via les altlabels (`_index_altlabels` dans xapianlib.py relie déjà
    toutes les variantes connues d'une même entité en synonymes Xapian --
    si l'auteur a saisi une variante anglaise, elle est ici telle quelle).
    Faire passer un nom propre dans un traducteur généraliste risque de
    le déformer plus que ça n'aide à le faire matcher.

    Contrairement à extract_top_terms, il n'y a pas de "fréquence" à trier
    ici : chaque document contribue au plus un titre + ses altlabels,
    donc le tri se fait alphabétiquement et `limit` coupe simplement la
    liste plutôt que de garder les N plus fréquents.
    """
    import xapian  # import différé, cf. extract_top_terms

    from ..xapianlib import XapianIndexer
    # Instancié sans `app` juste pour lire les constantes SLOT_TITLE /
    # SLOT_ALTLABELS -- __init__ ne fait aucune E/S tant qu'on n'appelle
    # pas une méthode de recherche/indexation, donc pas de dépendance
    # cachée sur un contexte Sphinx ici.
    slots = XapianIndexer()

    db = xapian.Database(db_path)
    try:
        seen = set()
        labels = []
        for docid in range(1, db.get_lastdocid() + 1):
            try:
                doc = db.get_document(docid)
            except xapian.DocNotFoundError:
                continue

            candidates = []
            title = doc.get_value(slots.SLOT_TITLE)
            if title:
                candidates.append(_decode(title))
            altlabels = doc.get_value(slots.SLOT_ALTLABELS)
            if altlabels:
                candidates.extend(
                    label.strip() for label in _decode(altlabels).split('|') if label.strip()
                )

            for label in candidates:
                if len(label) < min_length:
                    continue
                key = label.lower()
                if key in seen:
                    continue
                seen.add(key)
                labels.append(label)
    finally:
        db.close()

    labels.sort(key=str.lower)
    if limit is not None:
        labels = labels[:limit]
    return labels
