# -*- encoding: utf-8 -*-
"""
Tests de l'extraction des mots-clés depuis une base Xapian.

Nécessitent le module `xapian` (déjà une dépendance du projet pour la
recherche) -- ignorés automatiquement (`pytest.importorskip`) si absent,
pour ne pas casser le reste de la suite sur une machine qui ne les a pas.
"""
import pytest

xapian = pytest.importorskip('xapian')

from sphinxcontrib.osint.mesh.keywords import extract_canonical_labels, extract_top_terms
from sphinxcontrib.osint.xapianlib import XapianIndexer

_SLOTS = XapianIndexer()  # juste pour lire SLOT_TITLE / SLOT_ALTLABELS, pas d'E/S


def _build_test_db(path):
    """Construit une mini base Xapian avec le même schéma de préfixes que
    xapianlib.py (S=titre, C=catégorie booléenne, texte libre sans
    préfixe) pour vérifier que le filtre ne garde bien que le texte libre.
    """
    db = xapian.WritableDatabase(str(path), xapian.DB_CREATE_OR_OPEN)
    indexer = xapian.TermGenerator()
    indexer.set_stemmer(xapian.Stem('french'))

    docs = [
        ('Guerre en Ukraine', "La Russie et l'Ukraine sont en guerre depuis 2022."),
        ('Sanctions economiques', "Les sanctions contre la Russie visent l'economie russe."),
        ('Sommet a Kyiv', "Kyiv accueille un sommet sur l'Ukraine et la Russie."),
    ]
    for title, body in docs:
        doc = xapian.Document()
        indexer.set_document(doc)
        indexer.index_text(title, 1, 'S')  # champ titre préfixé -> ne doit pas ressortir
        indexer.index_text(body)  # texte libre, sans préfixe -> vocabulaire mesh
        doc.add_boolean_term('Cconflit-arme')  # catégorie booléenne -> ne doit pas ressortir
        db.add_document(doc)
    db.close()


def test_extract_top_terms_ranks_by_frequency(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_test_db(db_path)

    terms = extract_top_terms(str(db_path), limit=10, min_length=3)

    # "russie"/"ukraine" apparaissent dans les 3 documents -> forcément
    # dans le lot le plus fréquent, avant les termes qui n'apparaissent
    # qu'une fois (ex: "kyiv").
    top_terms = set(terms[:2])
    assert top_terms & {'russie', 'ukraine'}
    assert 'kyiv' in terms


def test_extract_top_terms_excludes_prefixed_terms(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_test_db(db_path)

    terms = extract_top_terms(str(db_path), limit=1000, min_length=1)

    # ni le terme booléen de catégorie...
    assert not any('conflit' in t for t in terms)
    # ...ni un terme provenant uniquement du champ titre préfixé "S"
    # (ex: "sommet" n'apparaît QUE dans un titre, jamais dans le texte libre)
    assert 'sommet' not in terms


def test_extract_top_terms_respects_min_length(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_test_db(db_path)

    terms = extract_top_terms(str(db_path), limit=1000, min_length=6)

    assert all(len(t) >= 6 for t in terms)


def test_extract_top_terms_respects_limit(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_test_db(db_path)

    terms = extract_top_terms(str(db_path), limit=2, min_length=1)

    assert len(terms) <= 2


# -- extract_canonical_labels ---------------------------------------------

def _build_entities_db(path):
    """Base avec des documents portant un titre (SLOT_TITLE) et des
    altlabels (SLOT_ALTLABELS, chaîne pipe-séparée) -- comme le fait
    réellement index_quest() pour idents/countries/cities/orgs.
    """
    db = xapian.WritableDatabase(str(path), xapian.DB_CREATE_OR_OPEN)

    doc1 = xapian.Document()
    doc1.add_value(_SLOTS.SLOT_TITLE, 'Volodymyr Zelensky')
    doc1.add_value(_SLOTS.SLOT_ALTLABELS, 'Volodymyr Zelensky|Zelensky|Володимир Зеленський')
    db.add_document(doc1)

    doc2 = xapian.Document()
    doc2.add_value(_SLOTS.SLOT_TITLE, 'Kyiv')
    doc2.add_value(_SLOTS.SLOT_ALTLABELS, 'Kyiv|Kiev|Київ')
    db.add_document(doc2)

    doc3 = xapian.Document()
    doc3.add_value(_SLOTS.SLOT_TITLE, 'Sommet a Kyiv')  # pas d'altlabels
    db.add_document(doc3)

    db.close()


def test_extract_canonical_labels_reads_title_and_altlabels(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_entities_db(db_path)

    labels = extract_canonical_labels(str(db_path))

    assert 'Volodymyr Zelensky' in labels  # phrase entière, pas explosée en mots
    assert 'Zelensky' in labels
    assert 'Kyiv' in labels
    assert 'Kiev' in labels
    assert 'Sommet a Kyiv' in labels  # titre seul, sans altlabels


def test_extract_canonical_labels_deduplicates_case_insensitively(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_entities_db(db_path)

    labels = extract_canonical_labels(str(db_path))

    # "Kyiv" apparaît comme titre du doc2 ET comme premier altlabel du même doc2
    assert labels.count('Kyiv') == 1


def test_extract_canonical_labels_respects_limit(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_entities_db(db_path)

    labels = extract_canonical_labels(str(db_path), limit=2)

    assert len(labels) <= 2


def test_extract_canonical_labels_empty_db(tmp_path):
    db_path = tmp_path / 'empty_db'
    db = xapian.WritableDatabase(str(db_path), xapian.DB_CREATE_OR_OPEN)
    db.close()

    assert extract_canonical_labels(str(db_path)) == []
