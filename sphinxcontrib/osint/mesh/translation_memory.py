# -*- encoding: utf-8 -*-
"""
Mémoire de traduction des mots-clés mesh
-------------------------------------------

Petit cache persistant terme (langue locale) -> terme (PIVOT_LANG), pour
deux raisons :

  1. Coût : les mots-clés publiés sont, par construction, les termes les
     plus fréquents de l'index -- donc les plus stables d'un cycle de
     sync à l'autre. Sans cache, on repaie une traduction déjà obtenue à
     chaque exécution de `mesh-sync`.
  2. Cohérence : un moteur de MT ne garantit pas de renvoyer exactement
     la même traduction à chaque appel pour un mot ambigu. Sans cache, un
     pair pourrait voir un mot-clé "changer" d'un cycle à l'autre sans
     que rien n'ait changé dans l'index local.

C'est aussi un point d'override manuel : `set()` (ou l'édition directe du
fichier JSON) permet de corriger une traduction jugée mauvaise, une fois
pour toutes -- elle ne sera plus jamais renvoyée au traducteur externe
tant qu'elle reste dans le fichier.

Format sur disque : {"<lang_source>": {"<terme>": "<traduction>", ...}}
-- une table par langue source, pour ne jamais mélanger deux langues qui
partageraient accidentellement une même orthographe.

Important en déploiement Docker/systemd (cf. INTEGRATION.md) : ce fichier
doit vivre sur un volume qui survit au conteneur (le carnet de pairs
lui-même est volontairement sans état entre deux runs -- cf.
PeerRegistry -- mais cette mémoire-là, elle, DOIT persister, sinon on
perd tout le bénéfice du cache et de l'override manuel à chaque
redéploiement).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading

logger = logging.getLogger(__name__)


class TranslationMemory:
    """Cache disque, thread-safe, terme -> traduction, par langue source."""

    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self._data = {}  # lang -> {term: translation}
        self._load()

    # -- persistance -----------------------------------------------------

    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as fp:
                self._data = json.load(fp)
        except (OSError, ValueError):
            logger.exception(
                'Impossible de charger la mémoire de traduction %s, on repart d\'un cache vide',
                self.path,
            )
            self._data = {}

    def _save(self):
        if not self.path:
            return
        directory = os.path.dirname(self.path) or '.'
        try:
            fd, tmp_path = tempfile.mkstemp(prefix='.mesh-translation-', dir=directory)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as fp:
                    json.dump(self._data, fp, ensure_ascii=False, indent=2, sort_keys=True)
                os.replace(tmp_path, self.path)  # écriture atomique
            except BaseException:
                os.unlink(tmp_path)
                raise
        except OSError:
            logger.exception('Impossible d\'écrire la mémoire de traduction %s', self.path)

    # -- lecture/écriture --------------------------------------------------

    def get(self, lang, term):
        with self._lock:
            return self._data.get(lang, {}).get(term)

    def set(self, lang, term, translation, persist=True):
        """Ajoute ou écrase une entrée -- c'est le point d'override manuel
        (appelable depuis le code, ou via `mesh-translation-set` en CLI).
        """
        with self._lock:
            self._data.setdefault(lang, {})[term] = translation
            if persist:
                self._save()

    def update(self, lang, mapping, persist=True):
        """Ajoute plusieurs entrées d'un coup -- une seule écriture disque
        au lieu d'une par terme traduit.
        """
        if not mapping:
            return
        with self._lock:
            self._data.setdefault(lang, {}).update(mapping)
            if persist:
                self._save()

    def as_dict(self, lang=None):
        """Copie du cache (tout, ou pour une langue donnée) -- utile pour
        l'inspection/debug, pas pour être modifiée in-place.
        """
        with self._lock:
            if lang is not None:
                return dict(self._data.get(lang, {}))
            return {l: dict(terms) for l, terms in self._data.items()}
