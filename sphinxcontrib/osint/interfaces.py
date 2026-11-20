# -*- encoding: utf-8 -*-
"""
The osint interfaces
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import atexit
import logging
import time
import random
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

    #: chromium argument hiding the automation (navigator.webdriver...)
    STEALTH_ARG = '--disable-blink-features=AutomationControlled'

    @classmethod
    def page_timeout(cls, env):
        """Seconds before a page load by a browser times out (osint_text_page_timeout)"""
        return getattr(env.config, 'osint_text_page_timeout', 30)

    @classmethod
    def referer(cls, env):
        """The Referer sent with the first request (osint_text_referer), or None"""
        return getattr(env.config, 'osint_text_referer', 'https://www.google.com/') or None

    @classmethod
    def humanize_enabled(cls, env):
        return getattr(env.config, 'osint_text_humanize', True) is True

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
    # (browser, user_data_dir, profile) -> driver, shared by all the plugins
    _selenium_drivers = {}
    _selenium_counts = {}

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
    def _selenium_stealth(cls, options):
        """Don't announce the automation (chromium based browsers)"""
        options.add_argument(cls.STEALTH_ARG)
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)

    @classmethod
    def _selenium_humanize(cls, driver):
        """Scroll the page by steps, like someone reading it, then go back to the top"""
        try:
            for _ in range(random.randint(3, 6)):
                driver.execute_script("window.scrollBy(0, arguments[0]);", random.randint(300, 700))
                time.sleep(random.uniform(0.2, 0.6))
            driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            logger.debug("Error humanizing selenium page", exc_info=True)

    @classmethod
    def _selenium_new_driver(cls, env, prefix, user_data_dir, profile):
        """Start a new selenium driver"""
        browser = cls._browser_conf(env, prefix, 'selenium') or 'chrome'
        driver = None
        if browser == 'chrome':
            options = cls._imp_selenium_webdriver.ChromeOptions()
            cls._selenium_stealth(options)
            if env.config.osint_http_proxy is not None:
                options.proxy = cls.get_proxy(env)
            for arg in cls.chromium_profile_args(user_data_dir, profile):
                options.add_argument(arg)
            selfopt = {
                'service': cls._imp_selenium_webdriver.chrome.service.Service(cls._imp_webdriver_manager_chrome.ChromeDriverManager().install()),
                'options': options,
            }
            driver = cls._imp_selenium_webdriver.Chrome(**selfopt)

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
            driver = cls._imp_selenium_webdriver.Firefox(**selfopt)

        elif browser == 'opera':
            webdriver_service = cls._imp_selenium_webdriver_chrome.service.Service(cls._imp_webdriver_manager_opera.OperaDriverManager().install())
            webdriver_service.start()

            options = cls._imp_selenium_webdriver.ChromeOptions()
            options.add_experimental_option('w3c', True)
            cls._selenium_stealth(options)
            if env.config.osint_http_proxy is not None:
                options.proxy = cls.get_proxy(env)
            for arg in cls.chromium_profile_args(user_data_dir, profile):
                options.add_argument(arg)

            driver = cls._imp_selenium_webdriver.Remote(webdriver_service.service_url, options=options)
        if driver is None:
            raise RuntimeError("Can't use selenium")
        driver.set_page_load_timeout(cls.page_timeout(env))
        driver.set_script_timeout(cls.page_timeout(env))
        return driver

    @classmethod
    def selenium_close(cls, key=None):
        """Quit the shared selenium driver(s) : one (key) or all"""
        drivers = SeleniumInterface._selenium_drivers
        for k in ([key] if key is not None else list(drivers)):
            driver = drivers.pop(k, None)
            SeleniumInterface._selenium_counts.pop(k, None)
            if driver is not None:
                try:
                    process = getattr(getattr(driver, 'service', None), 'process', None)
                    if process is not None and process.poll() is not None:
                        # chromedriver is already dead (^C kills the whole process group) : nothing to quit
                        continue
                    # (urllib3 retries and logs a warning if chromedriver is dying)
                    urllib3_logger = logging.getLogger('urllib3.connectionpool')
                    level = urllib3_logger.level
                    urllib3_logger.setLevel(logging.ERROR)
                    try:
                        driver.quit()
                    finally:
                        urllib3_logger.setLevel(level)
                except Exception:
                    logger.debug("Error quitting selenium driver", exc_info=True)

    @classmethod
    def selenium_driver(cls, env, prefix='text', restart=True):
        """Return the shared selenium driver (started if needed).

        The driver is shared by all the downloads (and plugins and scripts)
        using the same browser and profile : the session, with its cookies, is
        kept from a download to the next one. It must NOT be quit by the caller :
        it's done at exit, and every ``osint_text_browser_restart`` downloads
        (a fresh driver, with the same profile, is started) unless restart is False.

        :param prefix: the plugin config prefix used to find the browser and
            its profile (``text`` or ``pdf``).
        """
        user_data_dir, profile = cls.browser_profile(env, prefix, 'selenium')
        browser = cls._browser_conf(env, prefix, 'selenium') or 'chrome'
        key = (browser, user_data_dir, profile)
        drivers = SeleniumInterface._selenium_drivers
        counts = SeleniumInterface._selenium_counts
        restarts = getattr(env.config, 'osint_text_browser_restart', 50)
        if key in drivers:
            if restart and restarts and counts.get(key, 0) >= restarts:
                cls.selenium_close(key)
            else:
                try:
                    drivers[key].current_url
                except Exception:
                    # The browser died or was closed : start a new one
                    cls.selenium_close(key)
        if key not in drivers:
            drivers[key] = cls._selenium_new_driver(env, prefix, user_data_dir, profile)
            counts[key] = 0
            cls._register_close()
        counts[key] += 1
        return drivers[key]

    @classmethod
    def selenium_goto(cls, env, driver, url, humanize=True):
        """Load url in the driver, with the referer, and read it like a human"""
        referer = cls.referer(env)
        if referer is not None:
            try:
                # chromium only
                driver.execute_cdp_cmd('Network.enable', {})
                driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {'headers': {'Referer': referer}})
            except Exception:
                logger.debug("Can't set the referer with this browser", exc_info=True)
        driver.get(url)
        if humanize and cls.humanize_enabled(env):
            cls._selenium_humanize(driver)
        return driver

    @classmethod
    def selenium_fetch_url(cls, env, url, prefix='text'):
        """Fetch url using selenium and return the shared driver, with the page
        loaded (see selenium_driver : the caller must not quit it)."""
        return cls.selenium_goto(env, cls.selenium_driver(env, prefix), url)


class PlaywrightInterface(BrowserProfileInterface):
    _playwright_api = None
    # (channel, user_data_dir, profile) -> context / browser, shared by all the plugins
    _playwright_browsers = {}
    _playwright_launched = {}
    _playwright_counts = {}
    # key -> headless mode of the open browser, and the keys pinned by a session
    # (an interactive page which must not be closed by a change of mode)
    _playwright_modes = {}
    _playwright_pinned = set()

    @reify_classmethod
    def _imp_playwright_sync_api(cls):
        """Lazy loader for import playwright.sync_api"""
        import importlib
        return importlib.import_module('playwright.sync_api')

    @classmethod
    def playwright_close(cls, key=None):
        """Close the shared playwright browser(s) : one (key) or all (and stop playwright)"""
        browsers = PlaywrightInterface._playwright_browsers
        launched = PlaywrightInterface._playwright_launched
        for k in ([key] if key is not None else list(browsers)):
            for store in (browsers, launched):
                obj = store.pop(k, None)
                if obj is not None:
                    try:
                        obj.close()
                    except Exception:
                        logger.debug("Error closing playwright browser", exc_info=True)
            PlaywrightInterface._playwright_counts.pop(k, None)
            PlaywrightInterface._playwright_modes.pop(k, None)
            PlaywrightInterface._playwright_pinned.discard(k)
        if key is None and PlaywrightInterface._playwright_api is not None:
            try:
                PlaywrightInterface._playwright_api.stop()
            except Exception:
                logger.debug("Error stopping playwright", exc_info=True)
            PlaywrightInterface._playwright_api = None

    @classmethod
    def playwright_headless(cls, env):
        """osint_text_headless (default False) : True to hide the browser, False to show
        it (needs a display, ie xvfb-run). Overridden by the fetchheadless option of the
        ident of the site. The pdf is printed using the devtools protocol if visible."""
        return getattr(env.config, 'osint_text_headless', False) is True

    @classmethod
    def _playwright_humanize(cls, page):
        """Wait for the page to settle, move the mouse and scroll by steps, like
        someone reading it, then go back to the top"""
        try:
            page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            logger.debug("Page not idle after 10s", exc_info=True)
        try:
            vp = page.viewport_size or {'width': 1280, 'height': 720}
            page.mouse.move(random.randint(100, max(101, vp['width'] - 100)),
                random.randint(100, max(101, vp['height'] - 100)), steps=random.randint(8, 20))
            for _ in range(random.randint(3, 6)):
                page.mouse.wheel(0, random.randint(300, 700))
                page.wait_for_timeout(random.randint(200, 600))
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            logger.debug("Error humanizing playwright page", exc_info=True)

    @classmethod
    def _playwright_open(cls, env, key, channel, user_data_dir, profile, headless=True):
        """Open the (shared) context for key"""
        if PlaywrightInterface._playwright_api is None:
            PlaywrightInterface._playwright_api = cls._imp_playwright_sync_api.sync_playwright().start()
        api = PlaywrightInterface._playwright_api
        # Playwright starts chromium with --no-sandbox by default (Chrome then displays
        # "unsupported command-line flag" : less stable and secure). The sandbox can't be
        # used by root (containers) : disabled there, or with osint_text_playwright_sandbox = False
        sandbox = getattr(env.config, 'osint_text_playwright_sandbox', True) is not False \
            and getattr(os, 'geteuid', lambda: 1)() != 0
        if user_data_dir is None:
            # One context for all the pages : they share their cookies
            browser = api.chromium.launch(channel=channel, headless=headless, chromium_sandbox=sandbox,
                ignore_default_args=['--enable-automation'], args=[cls.STEALTH_ARG])
            PlaywrightInterface._playwright_launched[key] = browser
            context = browser.new_context()
        else:
            args = [a for a in cls.chromium_profile_args(user_data_dir, profile)
                if not a.startswith('--user-data-dir=')] + [cls.STEALTH_ARG]
            context = api.chromium.launch_persistent_context(
                user_data_dir, channel=channel, args=args, headless=headless, chromium_sandbox=sandbox,
                ignore_default_args=['--enable-automation'])
        # The playwright api can't be interrupted by a signal : its own timeouts bound the downloads
        context.set_default_timeout(cls.page_timeout(env) * 1000)
        PlaywrightInterface._playwright_browsers[key] = context
        PlaywrightInterface._playwright_counts[key] = 0
        PlaywrightInterface._playwright_modes[key] = headless
        cls._register_close()
        return context

    @classmethod
    def playwright_context(cls, env, prefix='text', restart=True, headless=None, pin=False):
        """Return the shared playwright context (started if needed).

        The browser and its context (cookies, logins, and the profile if a
        ``user_data_dir`` is configured) are shared by all the downloads (and
        plugins and scripts) : the session is kept from a download to the next
        one. Every ``osint_text_browser_restart`` downloads, the browser is
        restarted (the profile is kept) unless restart is False.

        :param prefix: the plugin config prefix used to find the browser and
            its profile (``text`` or ``pdf``).
        :param headless: the fetchheadless of the ident of the site (None :
            osint_text_headless). If the open browser has the other mode, it is
            restarted with the same profile (a profile can't be used by 2 browsers).
        :param pin: True for an interactive session : its browser is not restarted
            for a change of mode (the mode asked is ignored).
        """
        # can be "chrome", "msedge", "chrome-beta", "msedge-beta" or "msedge-dev".
        channel = cls._browser_conf(env, prefix, 'playwright') or 'chrome'
        user_data_dir, profile = cls.browser_profile(env, prefix, 'playwright')
        key = (channel, user_data_dir, profile)
        wanted = cls.playwright_headless(env) if headless is None else headless
        browsers = PlaywrightInterface._playwright_browsers
        counts = PlaywrightInterface._playwright_counts
        modes = PlaywrightInterface._playwright_modes
        restarts = getattr(env.config, 'osint_text_browser_restart', 50)
        if key in browsers:
            if key in PlaywrightInterface._playwright_pinned:
                wanted = modes[key]
            elif modes.get(key) != wanted:
                cls.playwright_close(key)
            elif restart and restarts and counts.get(key, 0) >= restarts:
                cls.playwright_close(key)
        if key not in browsers:
            cls._playwright_open(env, key, channel, user_data_dir, profile, wanted)
        if pin:
            PlaywrightInterface._playwright_pinned.add(key)
        counts[key] += 1
        return key, browsers[key]

    @classmethod
    def playwright_goto(cls, env, page, url, humanize=True, **kwargs):
        """Load url in the page, with the referer, and read it like a human"""
        page.goto(url, referer=cls.referer(env), **kwargs)
        if humanize and cls.humanize_enabled(env):
            cls._playwright_humanize(page)
        return page

    @classmethod
    def playwright_fetch_url(cls, env, url, prefix='text', headless=None):
        """Fetch url using playwright and return the page, loaded (see
        playwright_context). The caller must close the page."""
        key, context = cls.playwright_context(env, prefix, headless=headless)
        try:
            page = context.new_page()
        except Exception:
            # The browser died or was closed : start a new one
            logger.debug("Playwright browser lost : restarting it", exc_info=True)
            cls.playwright_close(key)
            key, context = cls.playwright_context(env, prefix, headless=headless)
            page = context.new_page()
        return cls.playwright_goto(env, page, url)


_close_registered = False

def _register_close(cls):
    """Close the shared browsers at exit (registered once)"""
    global _close_registered
    if _close_registered is False:
        _close_registered = True
        def close_all():
            SeleniumInterface.selenium_close()
            PlaywrightInterface.playwright_close()
        atexit.register(close_all)

BrowserProfileInterface._register_close = classmethod(_register_close)
