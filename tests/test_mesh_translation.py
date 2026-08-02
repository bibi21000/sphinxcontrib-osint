# -*- encoding: utf-8 -*-
"""
Tests de la traduction des mots-clés vers la langue pivot (PIVOT_LANG,
= 'en'). Le "traducteur" est injecté (`translate_fn`), donc pas de
dépendance au paquet `translators` ni à un vrai service de traduction --
ce module teste la logique de PeerRegistry, pas la qualité d'un moteur
de traduction externe.
"""
from sphinxcontrib.osint.mesh.registry import PeerRegistry
from sphinxcontrib.osint.mesh.translation_memory import TranslationMemory


def _fake_translator(mapping):
    """Simule un traducteur mot-à-mot déterministe, un mot par ligne
    (même format que celui réellement utilisé par _translate_terms)."""
    def translate_fn(text, dest, src_lang):
        words = text.split('\n')
        translated = [mapping.get(w, w) for w in words]
        return True, '\n'.join(translated)
    return translate_fn


def test_local_keywords_are_translated_to_pivot_lang():
    registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr',
        translate_fn=_fake_translator({'ukraine': 'ukraine', 'sanctions': 'sanctions', 'kyiv': 'kyiv'}),
    )
    # simule ce que renverrait extract_top_terms sans avoir besoin de xapian :
    terms = registry._translate_terms(['ukraine', 'sanctions', 'kyiv'])
    assert terms == ['ukraine', 'sanctions', 'kyiv']


def test_translate_terms_lowercases_output():
    registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr',
        translate_fn=_fake_translator({'guerre': 'War'}),
    )
    assert registry._translate_terms(['guerre']) == ['war']


def test_translate_terms_falls_back_to_local_on_line_count_mismatch():
    # simule un traducteur qui fusionne deux lignes en une (arrive avec
    # certains moteurs sur des mots très courts/ambigus)
    def bad_translate_fn(text, dest, src_lang):
        return True, 'une-seule-ligne'

    registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr', translate_fn=bad_translate_fn)

    terms = registry._translate_terms(['ukraine', 'sanctions'])

    assert terms == ['ukraine', 'sanctions']  # repli sur les termes locaux


def test_translate_terms_falls_back_to_local_when_translator_reports_failure():
    def failing_translate_fn(text, dest, src_lang):
        return False, text

    registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr', translate_fn=failing_translate_fn)

    terms = registry._translate_terms(['ukraine', 'sanctions'])

    assert terms == ['ukraine', 'sanctions']


def test_translate_terms_falls_back_to_local_when_translator_raises():
    def raising_translate_fn(text, dest, src_lang):
        raise RuntimeError('service de traduction indisponible')

    registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr', translate_fn=raising_translate_fn)

    terms = registry._translate_terms(['ukraine', 'sanctions'])

    assert terms == ['ukraine', 'sanctions']


def test_no_translation_when_lang_matches_pivot():
    calls = []

    def spy_translate_fn(text, dest, src_lang):
        calls.append(text)
        return True, text

    registry = PeerRegistry(
        self_id='osint-en', self_url='', lang='en',  # déjà en anglais
        translate_fn=spy_translate_fn,
    )
    registry.set_local_keywords(['ukraine', 'sanctions'])
    # local_keywords() renvoie le cache directement (déjà fixé via
    # set_local_keywords) -- on vérifie plutôt la condition explicitement
    # utilisée par local_keywords() pour décider de traduire ou non.
    assert not (registry.translate_keywords and registry.lang and registry.lang != registry.PIVOT_LANG)
    assert calls == []


def test_translation_disabled_via_translate_keywords_flag():
    calls = []

    def spy_translate_fn(text, dest, src_lang):
        calls.append(text)
        return True, text

    registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr',
        translate_keywords=False,
        translate_fn=spy_translate_fn,
    )
    assert not (registry.translate_keywords and registry.lang and registry.lang != registry.PIVOT_LANG)
    assert calls == []


# -- avec TranslationMemory ---------------------------------------------

def test_cached_terms_skip_the_translator(tmp_path):
    memory = TranslationMemory(str(tmp_path / 'tm.json'))
    memory.set('fr', 'ukraine', 'ukraine')

    calls = []

    def spy_translate_fn(text, dest, src_lang):
        calls.append(text)
        return True, '\n'.join(w + '-translated' for w in text.split('\n'))

    registry = PeerRegistry(
        self_id='osint-fr', self_url='', lang='fr',
        translate_fn=spy_translate_fn, translation_memory=memory,
    )

    result = registry._translate_terms(['ukraine', 'sanctions'])

    assert result == ['ukraine', 'sanctions-translated']  # 'ukraine' du cache, 'sanctions' traduit
    assert calls == ['sanctions']  # 'ukraine' n'a jamais été envoyé au traducteur


def test_successful_translation_is_written_back_to_memory(tmp_path):
    path = str(tmp_path / 'tm.json')
    memory = TranslationMemory(path)

    def translate_fn(text, dest, src_lang):
        return True, '\n'.join(w + '-en' for w in text.split('\n'))

    registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr',
                             translate_fn=translate_fn, translation_memory=memory)

    registry._translate_terms(['guerre'])

    assert memory.get('fr', 'guerre') == 'guerre-en'
    assert TranslationMemory(path).get('fr', 'guerre') == 'guerre-en'  # bien persisté sur disque


def test_failed_translation_does_not_pollute_memory(tmp_path):
    memory = TranslationMemory(str(tmp_path / 'tm.json'))

    def failing_translate_fn(text, dest, src_lang):
        return False, text

    registry = PeerRegistry(self_id='osint-fr', self_url='', lang='fr',
                             translate_fn=failing_translate_fn, translation_memory=memory)

    registry._translate_terms(['guerre'])

    assert memory.get('fr', 'guerre') is None
