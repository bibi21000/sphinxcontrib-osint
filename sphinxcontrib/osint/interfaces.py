# -*- encoding: utf-8 -*-
"""
The osint interfaces
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
from . import reify
from sphinx.util import logging

logger = logging.getLogger(__name__)

class NltkInterface():
    _setup_nltk = None
    ressources = [
                'punkt', 'stopwords', 'averaged_perceptron_tagger',
                'maxent_ne_chunker', 'words', 'vader_lexicon'
            ]

    @classmethod
    @reify
    def _imp_nltk(cls):
        """Lazy loader for import nltk"""
        import importlib
        return importlib.import_module('nltk')

    @classmethod
    @reify
    def _imp_nltk_sentiment(cls):
        """Lazy loader for import nltk.sentiment"""
        import importlib
        return importlib.import_module('nltk.sentiment')

    @classmethod
    @reify
    def _imp_nltk_tokenize(cls):
        """Lazy loader for import nltk.tokenize"""
        import importlib
        return importlib.import_module('nltk.tokenize')

    @classmethod
    @reify
    def _imp_nltk_corpus(cls):
        """Lazy loader for import nltk.corpus"""
        import importlib
        return importlib.import_module('nltk.corpus')

    @classmethod
    def init_nltk(cls, ntlk_data_dir='.ntlk_data', nltk_download=True):
        """Télécharge les ressources NLTK nécessaires"""
        if cls._setup_nltk is None:
            os.environ["NLTK_DATA"] = ntlk_data_dir
            os.makedirs(ntlk_data_dir, exist_ok=True)
            for ressource in cls.ressources:
                try:
                    cls._imp_nltk.data.find(f'tokenizers/{ressource}')
                except LookupError:
                    logger.debug(f"Download of {ressource}...")
                    if nltk_download is True:
                        cls._imp_nltk.download(ressource, quiet=True)
                    else:
                        logger.warning(f"Need to download {ressource} ... but won't do ... Set osint_analyse_nltk_download to True ")
                except Exception:
                    logger.exception(f"Downloading of {ressource}...")
            cls._setup_nltk = cls._imp_nltk

