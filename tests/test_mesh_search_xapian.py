# -*- encoding: utf-8 -*-
"""
Test de `_xapian_local_search` (implémentation réelle, pas
`local_search_fn` injecté) : construit une vraie petite base Xapian et
vérifie le pipeline traduction requête -> recherche -> traduction
résultats. Nécessite les bindings `xapian` (`pytest.importorskip`).
"""
import pytest

xapian = pytest.importorskip('xapian')

from sphinxcontrib.osint.mesh.registry import PeerRegistry
from sphinxcontrib.osint.xapianlib import XapianIndexer


def _build_search_db(path, language='french'):
    indexer = XapianIndexer(str(path), language=language)
    db = xapian.WritableDatabase(str(path), xapian.DB_CREATE_OR_OPEN)
    gen = xapian.TermGenerator()
    gen.set_stemmer(xapian.Stem(language))

    doc = xapian.Document()
    gen.set_document(doc)
    doc.add_value(indexer.SLOT_TITLE, 'Sommet sur la guerre en Ukraine')
    doc.add_value(indexer.SLOT_DESCRIPTION, '')
    doc.add_value(indexer.SLOT_TYPE, '')
    doc.add_value(indexer.SLOT_DATA, '')
    doc.add_value(indexer.SLOT_CATS, '')
    doc.add_value(indexer.SLOT_COUNTRY, '')
    doc.add_value(indexer.SLOT_BEGIN, '')
    doc.add_value(indexer.SLOT_NAME, '')
    doc.add_value(indexer.SLOT_URL, 'https://example.org/sommet')
    doc.set_data('sommet.rst')
    gen.index_text('Sommet sur la guerre en Ukraine')
    gen.index_text('Des dirigeants europeens se reunissent pour discuter des sanctions contre la Russie')
    db.add_document(doc)
    db.close()


def _fake_translate_fn(text, dest, src_lang):
    # traducteur jouet, mot-à-mot, suffisant pour vérifier le pipeline
    # (pas la qualité de traduction, testée ailleurs)
    table = {
        'ukraine': 'ukraine', 'sanctions': 'sanctions', 'russia': 'russie', 'russie': 'russia',
        'sommet sur la guerre en ukraine': 'summit on the war in ukraine',
        'summit on the war in ukraine': 'sommet sur la guerre en ukraine',
    }
    key = text.strip().lower()
    return True, table.get(key, text)


def test_xapian_local_search_translates_query_and_title(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_search_db(db_path)

    registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr', xapian_dir=str(db_path),
        translate_fn=_fake_translate_fn,
    )

    results = registry._xapian_local_search('ukraine sanctions', limit=5)

    assert len(results) == 1
    # la requête anglaise a bien été traduite en français pour chercher,
    # et le titre du résultat retraduit vers l'anglais avant de revenir.
    assert results[0]['title'] == 'summit on the war in ukraine'
    assert results[0]['score'] > 0


def test_xapian_local_search_no_translation_when_lang_is_pivot(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_search_db(db_path, language='english')

    calls = []

    def spy_translate_fn(text, dest, src_lang):
        calls.append(text)
        return True, text

    registry = PeerRegistry(
        self_id='osint-en', self_url='', lang='en', xapian_dir=str(db_path),
        translate_fn=spy_translate_fn,
    )

    registry._xapian_local_search('summit ukraine', limit=5)

    assert calls == []  # lang == PIVOT_LANG, aucune traduction nécessaire


def test_xapian_local_search_translate_results_false_keeps_local_title(tmp_path):
    db_path = tmp_path / 'xapian_db'
    _build_search_db(db_path)

    registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr', xapian_dir=str(db_path),
        translate_fn=_fake_translate_fn,
    )

    results = registry._xapian_local_search('ukraine sanctions', limit=5, translate_results=False)

    assert results[0]['title'] == 'Sommet sur la guerre en Ukraine'


def test_xapian_local_search_empty_db_returns_empty(tmp_path):
    db_path = tmp_path / 'empty_db'
    db = xapian.WritableDatabase(str(db_path), xapian.DB_CREATE_OR_OPEN)
    db.close()

    registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr', xapian_dir=str(db_path),
                             translate_fn=_fake_translate_fn)

    assert registry._xapian_local_search('ukraine', limit=5) == []
