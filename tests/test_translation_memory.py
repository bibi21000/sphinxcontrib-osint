# -*- encoding: utf-8 -*-
"""Tests de TranslationMemory (cache disque terme -> traduction)."""
from sphinxcontrib.osint.mesh.translation_memory import TranslationMemory


def test_get_missing_returns_none(tmp_path):
    memory = TranslationMemory(str(tmp_path / 'tm.json'))
    assert memory.get('fr', 'inconnu') is None


def test_set_then_get(tmp_path):
    memory = TranslationMemory(str(tmp_path / 'tm.json'))
    memory.set('fr', 'guerre', 'war')
    assert memory.get('fr', 'guerre') == 'war'


def test_different_languages_do_not_collide(tmp_path):
    memory = TranslationMemory(str(tmp_path / 'tm.json'))
    memory.set('fr', 'chat', 'cat')
    memory.set('de', 'chat', 'chat')  # 'chat' n'existe pas en allemand, coïncidence orthographique
    assert memory.get('fr', 'chat') == 'cat'
    assert memory.get('de', 'chat') == 'chat'


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / 'tm.json')
    TranslationMemory(path).set('fr', 'guerre', 'war')

    reloaded = TranslationMemory(path)
    assert reloaded.get('fr', 'guerre') == 'war'


def test_update_batches_multiple_entries(tmp_path):
    path = str(tmp_path / 'tm.json')
    memory = TranslationMemory(path)
    memory.update('fr', {'guerre': 'war', 'paix': 'peace'})

    reloaded = TranslationMemory(path)
    assert reloaded.get('fr', 'guerre') == 'war'
    assert reloaded.get('fr', 'paix') == 'peace'


def test_manual_override_replaces_existing_entry(tmp_path):
    path = str(tmp_path / 'tm.json')
    memory = TranslationMemory(path)
    memory.update('fr', {'guerre': 'war'})  # traduction automatique initiale

    memory.set('fr', 'guerre', 'conflict')  # correction manuelle

    assert TranslationMemory(path).get('fr', 'guerre') == 'conflict'


def test_missing_file_starts_empty_without_error(tmp_path):
    memory = TranslationMemory(str(tmp_path / 'does-not-exist.json'))
    assert memory.as_dict() == {}


def test_corrupted_file_starts_empty_without_crashing(tmp_path):
    path = tmp_path / 'tm.json'
    path.write_text('{not valid json', encoding='utf-8')

    memory = TranslationMemory(str(path))

    assert memory.as_dict() == {}
    # et reste utilisable normalement malgré le fichier corrompu au départ
    memory.set('fr', 'guerre', 'war')
    assert memory.get('fr', 'guerre') == 'war'


def test_no_path_means_in_memory_only_no_crash():
    memory = TranslationMemory(path=None)
    memory.set('fr', 'guerre', 'war')
    assert memory.get('fr', 'guerre') == 'war'  # utilisable pendant la durée du process
    # un rechargement n'a juste rien à charger (pas de fichier) -- comportement
    # attendu, pas une erreur.
    assert TranslationMemory(path=None).get('fr', 'guerre') is None


def test_as_dict_returns_a_copy_not_a_live_reference(tmp_path):
    memory = TranslationMemory(str(tmp_path / 'tm.json'))
    memory.set('fr', 'guerre', 'war')

    snapshot = memory.as_dict('fr')
    snapshot['guerre'] = 'tampered'

    assert memory.get('fr', 'guerre') == 'war'
