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
                'punkt', 'punkt_tab', 'stopwords',
                'averaged_perceptron_tagger',
                'maxent_ne_chunker', 'maxent_ne_chunker_tab',
                'words', 'vader_lexicon'
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
    def _nltk_download(cls, resource, nltk_download=True):
        """Download resource"""
        if nltk_download is True:
            cls._imp_nltk.download(resource, quiet=True)
            return True
        else:
            logger.warning(f"Need to download {resource} ... but won't do ... Set osint_analyse_nltk_download to True ")
            return False

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
                    cls._nltk_download(ressource, nltk_download=nltk_download)
                except Exception:
                    logger.exception(f"Downloading of {ressource}...")
            cls._setup_nltk = cls._imp_nltk


class SeleniumInterface():
    _selenium_driver = None

    @classmethod
    @reify
    def _imp_selenium(cls):
        """Lazy loader for import selenium"""
        import importlib
        return importlib.import_module('selenium')

    @classmethod
    @reify
    def _imp_selenium_webdriver(cls):
        """Lazy loader for import selenium.webdriver"""
        import importlib
        return importlib.import_module('selenium.webdriver')

    @classmethod
    @reify
    def _imp_selenium_webdriver_common_print_page_options(cls):
        """Lazy loader for import selenium.webdriver.common.print_page_options"""
        import importlib
        return importlib.import_module('selenium.webdriver.common.print_page_options')

    @classmethod
    @reify
    def _imp_selenium_webdriver_common_proxy(cls):
        """Lazy loader for import selenium.webdriver.common.proxy"""
        import importlib
        return importlib.import_module('selenium.webdriver.common.proxy')

    @classmethod
    @reify
    def _imp_selenium_webdriver_common_alert(cls):
        """Lazy loader for import selenium.webdriver.common.alert"""
        import importlib
        return importlib.import_module('selenium.webdriver.common.alert')

    @classmethod
    @reify
    def _imp_selenium_webdriver_chrome(cls):
        """Lazy loader for import selenium.webdriver.chrome"""
        import importlib
        return importlib.import_module('selenium.webdriver.chrome')

    @classmethod
    @reify
    def _imp_webdriver_manager(cls):
        """Lazy loader for import webdriver_manager"""
        import importlib
        return importlib.import_module('webdriver_manager')

    @classmethod
    @reify
    def _imp_webdriver_manager_chrome(cls):
        """Lazy loader for import webdriver_manager.chrome"""
        import importlib
        return importlib.import_module('webdriver_manager.chrome')

    @classmethod
    @reify
    def _imp_webdriver_manager_firefox(cls):
        """Lazy loader for import webdriver_manager.firefox"""
        import importlib
        return importlib.import_module('webdriver_manager.firefox')

    @classmethod
    @reify
    def _imp_webdriver_manager_opera(cls):
        """Lazy loader for import webdriver_manager.opera"""
        import importlib
        return importlib.import_module('webdriver_manager.opera')

    @classmethod
    def get_proxy(cls, env):
        """Get a proxy configuration"""

        proxy = cls._imp_selenium_webdriver_common_proxy.Proxy({
            'proxyType': ProxyType.MANUAL,
            'httpProxy': env.config.osint_http_proxy,
            'sslProxy': env.config.osint_http_proxy,
            'noProxy': ''})

        return proxy

    @classmethod
    def selenium_fetch_url(cls, env, url):
        """Fetch url using selenium"""
        if cls._selenium_driver is None:
            if env.config.osint_text_selenium == 'chrome':
                selfopt = {
                    'service': cls._imp_selenium_webdriver.chrome.service.Service(cls._imp_webdriver_manager_chrome.ChromeDriverManager().install())
                }
                if env.config.osint_http_proxy is not None:
                    selfopt['options'] = cls._imp_selenium_webdriver.ChromeOptions()
                    selfopt['options'].proxy = cls.get_proxy(env)

                cls._selenium_driver = cls._imp_selenium_webdriver.Chrome(**selfopt)

            elif env.config.osint_text_selenium == 'firefox':
                selfopt = {
                    'service': cls._imp_selenium_webdriver.firefox.service.Service(cls._imp_webdriver_manager_firefox.GeckoDriverManager().install())
                }
                if env.config.osint_http_proxy is not None:
                    selfopt['options'] = cls._imp_selenium_webdriver.FirefoxOptions()
                    selfopt['options'].proxy = cls.get_proxy(env)

                cls._selenium_driver = cls._imp_selenium_webdriver.Firefox(**selfopt)

            elif env.config.osint_text_selenium == 'opera':
                webdriver_service = cls._imp_selenium_webdriver_chrome.service.Service(cls._imp_webdriver_manager_opera.OperaDriverManager().install())
                webdriver_service.start()

                options = cls._imp_selenium_webdriver.ChromeOptions()
                options.add_experimental_option('w3c', True)
                if env.config.osint_http_proxy is not None:
                    options.proxy = cls.get_proxy(env)

                cls._selenium_driver = cls._imp_selenium_webdriver.Remote(webdriver_service.service_url, options=options)

        if cls._selenium_driver is None:
            raise RuntimeError("Can't use selenium")
        cls._selenium_driver.delete_all_cookies()
        cls._selenium_driver.get(url)
        ret = cls._selenium_driver
        # ~ cls._selenium_driver.quit()
        cls._selenium_driver = None
        return ret
