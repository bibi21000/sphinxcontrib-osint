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


class BrowserProfileInterface():
    """Resolve the browser profile configuration shared by selenium and playwright.

    For an engine (``selenium`` or ``playwright``) and a plugin prefix
    (``text`` or ``pdf``), the following config values are looked up, first
    for the plugin (``osint_<prefix>_<engine>...``) and then, if not set,
    for the text plugin (``osint_text_<engine>...``):

    - ``osint_<prefix>_<engine>`` : the browser to use
    - ``osint_<prefix>_<engine>_user_data_dir`` : the browser user data
      directory (for firefox : the profile directory)
    - ``osint_<prefix>_<engine>_profile`` : the profile name inside the user
      data directory (chromium based browsers only, ie ``Default``,
      ``Profile 1``)
    """

    @classmethod
    def _browser_conf(cls, env, prefix, engine, suffix=''):
        """Get a browser config value for a plugin, falling back to the text plugin"""
        for pfx in (prefix, 'text'):
            val = getattr(env.config, f'osint_{pfx}_{engine}{suffix}', None)
            if val is not None:
                return val
        return None

    @classmethod
    def browser_profile(cls, env, prefix, engine):
        """Return (user_data_dir, profile) or (None, None) if no profile is configured"""
        user_data_dir = cls._browser_conf(env, prefix, engine, '_user_data_dir')
        profile = cls._browser_conf(env, prefix, engine, '_profile')
        if user_data_dir is None:
            if profile is not None:
                logger.warning(
                    f"osint_{prefix}_{engine}_profile is set but osint_{prefix}_{engine}_user_data_dir is not : "
                    "profile ignored")
            return None, None
        user_data_dir = os.path.expanduser(str(user_data_dir))
        if not os.path.isabs(user_data_dir):
            user_data_dir = os.path.join(env.srcdir, user_data_dir)
        return os.path.abspath(user_data_dir), profile

    @classmethod
    def chromium_profile_args(cls, user_data_dir, profile):
        """Command line arguments selecting a profile on chromium based browsers"""
        args = []
        if user_data_dir is not None:
            args.append(f'--user-data-dir={user_data_dir}')
            if profile is not None:
                args.append(f'--profile-directory={profile}')
        return args


class SeleniumInterface(BrowserProfileInterface):
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
    def selenium_fetch_url(cls, env, url, prefix='text'):
        """Fetch url using selenium

        :param prefix: the plugin config prefix used to find the browser and
            its profile (``text`` or ``pdf``).
        """
        user_data_dir, profile = cls.browser_profile(env, prefix, 'selenium')
        if cls._selenium_driver is None:
            browser = cls._browser_conf(env, prefix, 'selenium') or 'chrome'
            if browser == 'chrome':
                options = cls._imp_selenium_webdriver.ChromeOptions()
                if env.config.osint_http_proxy is not None:
                    options.proxy = cls.get_proxy(env)
                for arg in cls.chromium_profile_args(user_data_dir, profile):
                    options.add_argument(arg)
                selfopt = {
                    'service': cls._imp_selenium_webdriver.chrome.service.Service(cls._imp_webdriver_manager_chrome.ChromeDriverManager().install()),
                    'options': options,
                }
                cls._selenium_driver = cls._imp_selenium_webdriver.Chrome(**selfopt)

            elif browser == 'firefox':
                options = cls._imp_selenium_webdriver.FirefoxOptions()
                if env.config.osint_http_proxy is not None:
                    options.proxy = cls.get_proxy(env)
                if user_data_dir is not None:
                    # For firefox, the profile is the directory itself
                    options.add_argument('-profile')
                    options.add_argument(user_data_dir)
                    if profile is not None:
                        logger.warning("osint_*_selenium_profile is ignored with firefox : use osint_*_selenium_user_data_dir with the profile directory")
                selfopt = {
                    'service': cls._imp_selenium_webdriver.firefox.service.Service(cls._imp_webdriver_manager_firefox.GeckoDriverManager().install()),
                    'options': options,
                }
                cls._selenium_driver = cls._imp_selenium_webdriver.Firefox(**selfopt)

            elif browser == 'opera':
                webdriver_service = cls._imp_selenium_webdriver_chrome.service.Service(cls._imp_webdriver_manager_opera.OperaDriverManager().install())
                webdriver_service.start()

                options = cls._imp_selenium_webdriver.ChromeOptions()
                options.add_experimental_option('w3c', True)
                if env.config.osint_http_proxy is not None:
                    options.proxy = cls.get_proxy(env)
                for arg in cls.chromium_profile_args(user_data_dir, profile):
                    options.add_argument(arg)

                cls._selenium_driver = cls._imp_selenium_webdriver.Remote(webdriver_service.service_url, options=options)

        if cls._selenium_driver is None:
            raise RuntimeError("Can't use selenium")
        if user_data_dir is None:
            # Never wipe the cookies of a real profile : they are the point of using it
            cls._selenium_driver.delete_all_cookies()
        # ~ cls._selenium_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        cls._selenium_driver.get(url)
        ret = cls._selenium_driver
        # ~ cls._selenium_driver.quit()
        cls._selenium_driver = None
        return ret


class PlaywrightInterface(BrowserProfileInterface):
    _playwright_api = None
    _playwright_browsers = {}

    @reify_classmethod
    def _imp_playwright_sync_api(cls):
        """Lazy loader for import playwright.sync_api"""
        import importlib
        return importlib.import_module('playwright.sync_api')

    @classmethod
    def playwright_fetch_url(cls, env, url, prefix='text'):
        """Fetch url using playwright

        :param prefix: the plugin config prefix used to find the browser and
            its profile (``text`` or ``pdf``).

        With a ``user_data_dir`` a persistent context is used : cookies and
        logins of the profile are available. The browser/context is kept
        opened and reused for the next urls.
        """
        if cls._playwright_api is None:
            cls._playwright_api = cls._imp_playwright_sync_api.sync_playwright().start()
        # can be "chrome", "msedge", "chrome-beta", "msedge-beta" or "msedge-dev".
        channel = cls._browser_conf(env, prefix, 'playwright') or 'chrome'
        user_data_dir, profile = cls.browser_profile(env, prefix, 'playwright')
        key = (channel, user_data_dir, profile)
        if key not in cls._playwright_browsers:
            if user_data_dir is None:
                cls._playwright_browsers[key] = cls._playwright_api.chromium.launch(channel=channel)
            else:
                args = [a for a in cls.chromium_profile_args(user_data_dir, profile)
                    if not a.startswith('--user-data-dir=')]
                cls._playwright_browsers[key] = cls._playwright_api.chromium.launch_persistent_context(
                    user_data_dir, channel=channel, args=args)
        page = cls._playwright_browsers[key].new_page()
        page.goto(url)
        return page
