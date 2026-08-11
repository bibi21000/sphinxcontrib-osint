# -*- encoding: utf-8 -*-
"""
The osint interfaces
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
from . import reify_classmethod
from sphinx.util import logging

logger = logging.getLogger(__name__)

class NltkInterface():
    _setup_nltk = None
    ressources = [
                'punkt', 'punkt_tab', 'stopwords',
                'averaged_perceptron_tagger', 'averaged_perceptron_tagger_eng',
                'maxent_ne_chunker', 'maxent_ne_chunker_tab',
                'words', 'vader_lexicon'
            ]

    @reify_classmethod
    def _imp_nltk(cls):
        """Lazy loader for import nltk"""
        import importlib
        return importlib.import_module('nltk')

    @reify_classmethod
    def _imp_nltk_sentiment(cls):
        """Lazy loader for import nltk.sentiment"""
        import importlib
        return importlib.import_module('nltk.sentiment')

    @reify_classmethod
    def _imp_nltk_tokenize(cls):
        """Lazy loader for import nltk.tokenize"""
        import importlib
        return importlib.import_module('nltk.tokenize')

    @reify_classmethod
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
        """Télécharge les ressources NLTK nécessaires

        nltk.download() already checks locally whether a resource is present
        before doing anything over the network, so there is no need (and it
        was actually wrong) to pre-check with nltk.data.find() using a
        single hardcoded 'tokenizers/' namespace: punkt/punkt_tab do live
        there, but stopwords/words live under corpora/, the taggers under
        taggers/, the chunkers under chunkers/, and vader_lexicon under
        sentiment/. That mismatch made the pre-check always report "missing"
        for most resources, and skipped the one thing this needs to be
        aware of anyway: some resource ids are renamed across nltk versions
        (e.g. 'averaged_perceptron_tagger' -> 'averaged_perceptron_tagger_eng').
        """
        if cls._setup_nltk is None:
            os.environ["NLTK_DATA"] = ntlk_data_dir
            os.makedirs(ntlk_data_dir, exist_ok=True)
            for ressource in cls.ressources:
                try:
                    cls._nltk_download(ressource, nltk_download=nltk_download)
                except Exception:
                    logger.exception(f"Downloading of {ressource}...")
            cls._setup_nltk = cls._imp_nltk


class SeleniumInterface():
    _selenium_driver = None

    @reify_classmethod
    def _imp_selenium(cls):
        """Lazy loader for import selenium"""
        import importlib
        return importlib.import_module('selenium')

    @reify_classmethod
    def _imp_selenium_webdriver(cls):
        """Lazy loader for import selenium.webdriver"""
        import importlib
        return importlib.import_module('selenium.webdriver')

    @reify_classmethod
    def _imp_selenium_webdriver_common_print_page_options(cls):
        """Lazy loader for import selenium.webdriver.common.print_page_options"""
        import importlib
        return importlib.import_module('selenium.webdriver.common.print_page_options')

    @reify_classmethod
    def _imp_selenium_webdriver_common_proxy(cls):
        """Lazy loader for import selenium.webdriver.common.proxy"""
        import importlib
        return importlib.import_module('selenium.webdriver.common.proxy')

    @reify_classmethod
    def _imp_selenium_webdriver_common_alert(cls):
        """Lazy loader for import selenium.webdriver.common.alert"""
        import importlib
        return importlib.import_module('selenium.webdriver.common.alert')

    @reify_classmethod
    def _imp_selenium_webdriver_chrome(cls):
        """Lazy loader for import selenium.webdriver.chrome"""
        import importlib
        return importlib.import_module('selenium.webdriver.chrome')

    @reify_classmethod
    def _imp_webdriver_manager(cls):
        """Lazy loader for import webdriver_manager"""
        import importlib
        return importlib.import_module('webdriver_manager')

    @reify_classmethod
    def _imp_webdriver_manager_chrome(cls):
        """Lazy loader for import webdriver_manager.chrome"""
        import importlib
        return importlib.import_module('webdriver_manager.chrome')

    @reify_classmethod
    def _imp_webdriver_manager_firefox(cls):
        """Lazy loader for import webdriver_manager.firefox"""
        import importlib
        return importlib.import_module('webdriver_manager.firefox')

    @reify_classmethod
    def _imp_webdriver_manager_opera(cls):
        """Lazy loader for import webdriver_manager.opera"""
        import importlib
        return importlib.import_module('webdriver_manager.opera')

    @classmethod
    def get_proxy(cls, env):
        """Get a proxy configuration"""

        proxy = cls._imp_selenium_webdriver_common_proxy.Proxy({
            'proxyType': cls._imp_selenium_webdriver_common_proxy.ProxyType.MANUAL,
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
        # ~ cls._selenium_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        cls._selenium_driver.get(url)
        ret = cls._selenium_driver
        # ~ cls._selenium_driver.quit()
        cls._selenium_driver = None
        return ret


class PlaywrightInterface():
    _playwright_api = None
    _playwright_browser = None

    @reify_classmethod
    def _imp_playwright_sync_api(cls):
        """Lazy loader for import playwright.sync_api"""
        import importlib
        return importlib.import_module('playwright.sync_api')

    @classmethod
    def playwright_fetch_url(cls, env, url):
        """Fetch url using playwright"""
        if cls._playwright_api is None:
            cls._playwright_api = cls._imp_playwright_sync_api.sync_playwright().start()
            # osint_text_playwright can be "chrome", "msedge", "chrome-beta", "msedge-beta" or "msedge-dev".
            cls._playwright_browser = cls._playwright_api.chromium.launch(channel=env.config.osint_text_playwright)
        page = cls._playwright_browser.new_page()
        page.goto(url)
        return page
