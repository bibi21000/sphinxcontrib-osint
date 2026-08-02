# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import sys
import json
import click
import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# Évite un appel réseau de géodétection au chargement du module translators
os.environ.setdefault("translators_default_region", "EN")
import translators as ts  # noqa: E402

from langdetect import detect as lang_detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
import pickle

from . import parser_makefile, cli, get_app, load_quest, JSONEncoder
from ..osintlib import OSIntQuest

from ..plugins import collect_plugins

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

# Rend la détection déterministe (langdetect est probabiliste par défaut)
DetectorFactory.seed = 0

TIMEOUT = 12  # secondes

# Plusieurs profils de User-Agent à essayer en cascade en cas de blocage (403).
# Certains sites (Libération, Le Monde, etc.) bloquent les UA génériques mais
# laissent passer les crawlers connus (Googlebot) ou les vrais navigateurs.
UA_PROFILES = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Referer": "https://www.google.com/",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Referer": "https://fr.wikipedia.org/",
    },
    {
        # UA de crawler : souvent autorisé par les paywalls/anti-bot pour le SEO
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
]

RETRY_STATUS_CODES = {403, 429, 503}

# Configuration du repli "navigateur headless" (rempli depuis les args CLI
# dans main(), mais utilisable avec des valeurs par défaut si le module est
# importé directement).
BROWSER_FALLBACK_ENABLED = True
BROWSER_ENGINE = "playwright"  # "playwright" ou "selenium"
BROWSER_TIMEOUT_MS = 20000

# Signaux textuels typiques des pages de "challenge" anti-bot
# (Cloudflare, Datadome, etc.) qui répondent 200 OK mais sans contenu réel.
BOT_CHALLENGE_HINTS = [
    "veuillez activer javascript",
    "please enable javascript",
    "checking your browser",
    "just a moment",
    "attention required",
    "client challenge",
    "access denied",
    "ddos protection by",
    "enable cookies and reload",
    "verifying you are human",
    "verify you are a human",
    "un instant",
    "vérification de votre navigateur",
    "activer les cookies",
]


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def truncate_words(text: str, max_words: int = 6) -> str:
    """Ne conserve que les N premiers mots d'un texte."""
    if not text:
        return text
    words = text.split()
    return " ".join(words[:max_words])


def slugify(text: str) -> str:
    """Transforme un titre en identifiant sans espaces ni accents."""
    if not text:
        return "sans_titre"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.replace('"', "").replace("'", "")
    text = text.replace("-", "")
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\s+", "_", text.strip())
    text = re.sub(r"_+", "_", text)
    return text[:120] or "sans_titre"


def clean_label(text: str) -> str:
    """Titre affichable, avec les guillemets doubles convertis en
    guillemets français « » (pour :label:)."""
    if not text:
        return "Sans titre"

    def _replace_quotes(match: "re.Match") -> str:
        # Alterne guillemet ouvrant/fermant à chaque occurrence de '"'
        _replace_quotes.count += 1
        return "«" if _replace_quotes.count % 2 == 1 else "»"

    _replace_quotes.count = 0
    text = re.sub(r'"', _replace_quotes, text)
    return text.strip()


def clean_url(url: str) -> str:
    """Nettoie une URL en retirant tout ce qui suit '?' (paramètres de
    requête, souvent des trackers) et '#' (fragment/ancre)."""
    if not url:
        return url
    return url.split("?", 1)[0].split("#", 1)[0]


def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "inconnu"
    except Exception:
        return "inconnu"


def rst_escape(text: str) -> str:
    """Échappe un minimum le texte pour rester lisible en RST."""
    if not text:
        return ""
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Extraction des références depuis la page Wikipedia
# --------------------------------------------------------------------------

def looks_like_bot_challenge(soup: BeautifulSoup) -> bool:
    """Heuristique : la page ressemble-t-elle à un écran anti-bot
    (Cloudflare, Datadome...) plutôt qu'au contenu réel ?"""
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip().lower()

    body_text = soup.get_text(" ", strip=True).lower()
    combined = f"{title} {body_text[:600]}"

    if any(hint in combined for hint in BOT_CHALLENGE_HINTS):
        return True

    # Page quasiment vide de contenu textuel = probablement un mur JS
    if len(body_text) < 150:
        return True

    return False


def _fetch_with_playwright(url: str, timeout_ms: int = BROWSER_TIMEOUT_MS):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "    [playwright] non installé. "
            "Installe-le avec: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent=UA_PROFILES[0]["User-Agent"],
                locale="fr-FR",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"},
            )
            # Masque les traces les plus évidentes d'un navigateur automatisé
            # (utile face aux protections type Datadome/Cloudflare qui
            # inspectent navigator.webdriver, les plugins, etc.)
            context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
                """
            )
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            # Poll : laisse le temps au challenge JS (Cloudflare, Datadome...)
            # de se résoudre, en revérifiant périodiquement le contenu.
            html = page.content()
            for _ in range(4):
                soup_check = BeautifulSoup(html, "lxml")
                if not looks_like_bot_challenge(soup_check):
                    break
                page.wait_for_timeout(2500)
                html = page.content()

            browser.close()
        return BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001
        print(f"    [playwright] échec: {exc}", file=sys.stderr)
        return None


def _fetch_with_selenium(url: str, timeout_ms: int = BROWSER_TIMEOUT_MS):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print(
            "    [selenium] non installé. "
            "Installe-le avec: pip install selenium webdriver-manager",
            file=sys.stderr,
        )
        return None

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={UA_PROFILES[0]['User-Agent']}")
    options.add_argument("--lang=fr-FR")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(timeout_ms / 1000)
        driver.get(url)
        time.sleep(3)  # laisse le JS du challenge s'exécuter
        html = driver.page_source
        return BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001
        print(f"    [selenium] échec: {exc}", file=sys.stderr)
        return None
    finally:
        if driver:
            driver.quit()


def fetch_soup_with_browser(url: str):
    """Récupère une page via un navigateur headless (Playwright ou Selenium
    selon BROWSER_ENGINE), utile pour contourner les challenges JS anti-bot."""
    if BROWSER_ENGINE == "selenium":
        return _fetch_with_selenium(url)
    return _fetch_with_playwright(url)


def fetch_soup(url: str) -> BeautifulSoup:
    """Télécharge une page et renvoie son BeautifulSoup.
    Essaie plusieurs profils de headers/User-Agent en cascade si le
    serveur répond par un blocage (403, 429, 503). Si toutes les
    tentatives HTTP échouent, ou si la page obtenue ressemble à un
    écran anti-bot (Cloudflare, Datadome...), bascule sur un navigateur
    headless (Playwright/Selenium) si activé."""
    last_exc = None
    challenge_soup = None

    for i, headers in enumerate(UA_PROFILES):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            if resp.status_code in RETRY_STATUS_CODES and i < len(UA_PROFILES) - 1:
                time.sleep(0.6)
                continue
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or resp.encoding
            candidate = BeautifulSoup(resp.text, "lxml")

            if looks_like_bot_challenge(candidate):
                challenge_soup = candidate
                print("    -> page suspecte (écran anti-bot ?)", file=sys.stderr)
                if i < len(UA_PROFILES) - 1:
                    time.sleep(0.6)
                    continue
                break  # dernier profil épuisé, on tentera le navigateur

            return candidate

        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            if i < len(UA_PROFILES) - 1:
                time.sleep(0.6)
                continue
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            break

    # Tous les profils HTTP simples ont échoué ou renvoyé un écran anti-bot
    if BROWSER_FALLBACK_ENABLED:
        print(f"    -> repli navigateur headless ({BROWSER_ENGINE})", file=sys.stderr)
        browser_soup = fetch_soup_with_browser(url)
        if browser_soup is not None:
            return browser_soup

    # Rien n'a fonctionné : on renvoie quand même la page de challenge
    # (mieux que rien, le fallback de titre utilisera le texte de citation)
    if challenge_soup is not None:
        return challenge_soup
    if last_exc:
        raise last_exc
    raise requests.exceptions.RequestException(f"Impossible de récupérer {url}")


def extract_wikipedia_references(wiki_url: str, max_refs: int = None):
    """
    Retourne une liste de dicts {id, cite_text, url} pour chaque référence
    trouvée dans les <ol class="references"> de la page Wikipedia.
    """
    soup = fetch_soup(wiki_url)
    references = []

    ref_lists = soup.select("ol.references")
    if not ref_lists:
        # Certaines pages utilisent directement des <li id="cite_note-...">
        ref_items = soup.select('li[id^="cite_note"]')
    else:
        ref_items = []
        for ol in ref_lists:
            ref_items.extend(ol.select("li"))

    seen_urls = set()

    for li in ref_items:
        ref_id = li.get("id", "")

        # Le texte de la citation (souvent dans <span class="reference-text">)
        text_span = li.select_one("span.reference-text") or li
        cite_text = rst_escape(text_span.get_text(" ", strip=True))

        # Recherche du premier lien externe pertinent
        link = None
        for a in text_span.select("a.external, a[href]"):
            href = a.get("href", "")
            if href.startswith("http://") or href.startswith("https://"):
                link = clean_url(href)
                break

        if not link or link in seen_urls:
            continue
        seen_urls.add(link)

        references.append({
            "id": ref_id,
            "cite_text": cite_text,
            "url": link,
        })

        if max_refs and len(references) >= max_refs:
            break

    return references


# --------------------------------------------------------------------------
# Analyse d'une page référencée (titre / description / date)
# --------------------------------------------------------------------------

DATE_META_NAMES = [
    ("meta", {"property": "article:published_time"}),
    ("meta", {"property": "og:updated_time"}),
    ("meta", {"name": "date"}),
    ("meta", {"name": "dc.date"}),
    ("meta", {"name": "dc.date.issued"}),
    ("meta", {"name": "publish-date"}),
    ("meta", {"name": "publication_date"}),
    ("meta", {"itemprop": "datePublished"}),
]

DATE_REGEX = re.compile(
    r"\b(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|"
    r"septembre|octobre|novembre|décembre)\s+\d{4}|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)


def guess_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def guess_description(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        return og["content"].strip()
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        return md["content"].strip()
    p = soup.find("p")
    if p:
        return p.get_text(strip=True)[:300]
    return ""


def guess_date(soup: BeautifulSoup) -> str:
    for tag_name, attrs in DATE_META_NAMES:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()

    time_tag = soup.find("time")
    if time_tag:
        if time_tag.get("datetime"):
            return time_tag["datetime"].strip()
        if time_tag.get_text(strip=True):
            return time_tag.get_text(strip=True)

    # Recherche dans le texte brut (fallback)
    text = soup.get_text(" ", strip=True)
    match = DATE_REGEX.search(text)
    if match:
        return match.group(0)

    return ""


# Schémas de date fréquents dans les chemins d'URL d'articles de presse :
#   /2024/04/03/mon-article   /2024-04-03-mon-article   /20240403-mon-article
URL_DATE_YMD_RE = re.compile(r"(?<!\d)(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?!\d)")
URL_DATE_COMPACT_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")
# Repli : seulement année/mois (ex: /2024/04/mon-article)
URL_DATE_YM_RE = re.compile(r"(?<!\d)(\d{4})[/-](\d{1,2})(?!\d)")


def guess_date_from_url(url: str) -> str:
    """Essaie d'extraire une date directement depuis le chemin de l'URL,
    utilisé en dernier recours quand aucune date n'a pu être trouvée dans
    le contenu de la page (meta tags, balise <time>, texte). Reconnaît les
    schémas les plus courants (année/mois/jour, avec ou sans séparateurs,
    ou année/mois seul). Renvoie une chaîne ISO (YYYY-MM-DD ou YYYY-MM),
    ou "" si rien n'a pu être détecté de façon fiable."""
    if not url:
        return ""

    path = urlparse(url).path
    current_year = datetime.now().year

    for pattern in (URL_DATE_YMD_RE, URL_DATE_COMPACT_RE):
        for match in pattern.finditer(path):
            year, month, day = (int(g) for g in match.groups())
            if not (1990 <= year <= current_year + 1):
                continue
            if not (1 <= month <= 12):
                continue
            if not (1 <= day <= 31):
                continue
            try:
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                continue

    for match in URL_DATE_YM_RE.finditer(path):
        year, month = int(match.group(1)), int(match.group(2))
        if 1990 <= year <= current_year + 1 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    return ""



# Format ISO 8601 (YYYY-MM-DD, éventuellement suivi d'une heure/offset).
# C'est la forme la plus fréquente dans les balises <meta> (article:
# published_time, etc.). Elle n'est PAS ambiguë : on ne doit surtout pas
# forcer dayfirst dessus. dateutil.parser.parse(..., fuzzy=True, dayfirst=True)
# inverse pourtant le jour et le mois même sur ce format non ambigu
# (ex: "2024-04-03T08:00:00+00:00" -> 4 mars au lieu du 3 avril) : on passe
# donc par dateutil.parser.isoparse, qui est prévu pour ce format précis.
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?.*)?$")


class _FrenchParserInfo(dateparser.parserinfo):
    """Ajoute les noms de mois français, absents par défaut de dateutil
    (qui, sans ça, ignore silencieusement "avril", "août"... et retombe
    sur des valeurs par défaut n'importe quoi, ex: le jour du jour même)."""
    MONTHS = [
        ("Jan", "January", "janvier"),
        ("Feb", "February", "février", "fevrier"),
        ("Mar", "March", "mars"),
        ("Apr", "April", "avril"),
        ("May", "May", "mai"),
        ("Jun", "June", "juin"),
        ("Jul", "July", "juillet"),
        ("Aug", "August", "août", "aout"),
        ("Sep", "Sept", "September", "septembre"),
        ("Oct", "October", "octobre"),
        ("Nov", "November", "novembre"),
        ("Dec", "December", "décembre", "decembre"),
    ]


_FR_PARSERINFO = _FrenchParserInfo(dayfirst=True)


def normalize_date(raw_date: str) -> str:
    """Essaie de renvoyer une date au format ISO (YYYY-MM-DD)."""
    if not raw_date:
        return ""
    raw_date = raw_date.strip()

    # 1) Format ISO 8601 non ambigu -> isoparse, sans notion de dayfirst.
    if ISO_DATE_RE.match(raw_date):
        try:
            dt = dateparser.isoparse(raw_date)
            if dt:
                return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # 2) Reste des cas (dates en toutes lettres en français, "DD/MM/YYYY"...)
    #    -> parserinfo francophone, avec dayfirst=True (convention FR pour
    #    les formats numériques réellement ambigus comme "03/04/2024").
    try:
        dt = dateparser.parse(raw_date, fuzzy=True, parserinfo=_FR_PARSERINFO)
        if dt:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return raw_date


def analyze_reference(ref: dict) -> dict:
    """Télécharge la page cible et en extrait titre / description / date."""
    result = {
        "url": ref["url"],
        "cite_text": ref["cite_text"],
        "domain": domain_of(ref["url"]),
        "title": "",
        "description": "",
        "title_fr": "",
        "description_fr": "",
        "date": "",
        "lang": "",
        "status": "ok",
    }

    try:
        soup = fetch_soup(ref["url"])

        if looks_like_bot_challenge(soup):
            # Même après tous les replis (headers, navigateur headless), la
            # page reçue est toujours un écran anti-bot (Datadome/Cloudflare
            # Enterprise...). On ne récupère surtout PAS son "titre"/
            # "description" (ex: "Défi client" / "Veuillez activer
            # JavaScript..."), on laisse le fallback vers le texte de la
            # citation Wikipedia s'en charger plus bas.
            result["status"] = "bloqué par protection anti-bot (challenge non résolu)"
        else:
            result["title"] = guess_title(soup)
            result["description"] = guess_description(soup)
            result["date"] = normalize_date(guess_date(soup))
    except requests.exceptions.RequestException as exc:
        result["status"] = f"erreur: {exc}"
    except Exception as exc:  # noqa: BLE001
        result["status"] = f"erreur inattendue: {exc}"

    # Fallback : si le titre n'a pas pu être récupéré, on utilise le texte
    # de la citation Wikipedia elle-même.
    if not result["title"]:
        result["title"] = result["cite_text"][:120] or result["domain"]

    # Fallback : si aucune date n'a pu être extraite du contenu de la page
    # (meta tags, <time>, texte) -- y compris lorsque la page n'a pas pu être
    # récupérée du tout (erreur réseau, anti-bot...) -- on tente de la
    # détecter directement depuis le chemin de l'URL (ex: /2024/04/03/...).
    if not result["date"]:
        result["date"] = guess_date_from_url(ref["url"])

    # Détection de la langue de la page (à partir du titre + description)
    sample_text = f"{result['title']} {result['description']}".strip()
    detected_lang = detect_language(sample_text)
    result["lang"] = detected_lang or "?"

    if detected_lang == "fr":
        # Déjà en français : pas besoin de traduire
        result["title_fr"] = result["title"]
        result["description_fr"] = result["description"]
    else:
        from_lang = detected_lang or "auto"
        result["title_fr"] = translate_to_fr(result["title"], from_language=from_lang)
        result["description_fr"] = translate_to_fr(result["description"], from_language=from_lang)

    return result


# --------------------------------------------------------------------------
# Détection de langue (langdetect)
# --------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """Détecte la langue d'un texte (code ISO 639-1, ex: 'fr', 'en').
    Renvoie '' si la détection échoue (texte trop court/vide)."""
    text = (text or "").strip()
    if len(text) < 3:
        return ""
    try:
        return lang_detect(text)
    except LangDetectException:
        return ""


# --------------------------------------------------------------------------
# Traduction (translators)
# --------------------------------------------------------------------------

# Liste de moteurs à essayer dans l'ordre (fallback en cas d'échec/blocage)
TRANSLATE_ENGINES = ["bing", "google", "alibaba", "argos"]


def translate_to_fr(text: str, from_language: str = "auto", max_len: int = 3000) -> str:
    """Traduit un texte vers le français via la librairie `translators`.
    Essaie plusieurs moteurs en cas d'échec. Renvoie le texte original
    si aucune traduction n'a pu être obtenue."""
    if not text:
        return ""

    text = text[:max_len]

    for engine in TRANSLATE_ENGINES:
        try:
            translated = ts.translate_text(
                text,
                translator=engine,
                from_language=from_language,
                to_language="fr",
            )
            if translated:
                return translated.strip()
        except Exception as exc:  # noqa: BLE001
            print(f"    [traduction:{engine}] échec: {exc}", file=sys.stderr)
            continue

    print("    [traduction] toutes les tentatives ont échoué, texte original conservé.",
          file=sys.stderr)
    return text


# --------------------------------------------------------------------------
# Correspondance avec un quest sphinxcontrib-osint (fichier .pickle)
# --------------------------------------------------------------------------

def normalize_url(url: str):
    """Normalise une URL pour comparaison (insensible à la casse, sans
    paramètres de requête, ni fragment, ni slash final)."""
    if not url:
        return None
    url = clean_url(url).rstrip("/")
    return url.lower()


def load_quest_data(quest):

    from_map = {}
    existing_urls = set()

    events = getattr(quest, "events", {}) or {}
    sources = getattr(quest, "sources", {}) or {}

    for ev in events.values():
        pd = getattr(ev, "plugins_data", {}) or {}
        event_url = pd.get("url") or pd.get("link") or pd.get("youtube")

        norm = normalize_url(event_url)
        if norm:
            existing_urls.add(norm)

        from_value = pd.get("from")
        if from_value and event_url:
            dom = domain_of(event_url)
            if dom and dom not in from_map:
                from_map[dom] = from_value

    for src in sources.values():
        src_url = getattr(src, "url", None)
        norm = normalize_url(src_url)
        if norm:
            existing_urls.add(norm)

    print(
        f"[*] {len(from_map)} domain->from mapping(s) and "
        f"{len(existing_urls)} Known URL(s) loaded from quest",
        file=sys.stderr,
    )
    return from_map, existing_urls


def find_from_for_domain(domain: str, quest_map: dict):
    """Cherche `domain` dans la table domaine->from du quest.
    Autorise une correspondance par sous-domaine dans les deux sens
    (ex: 'background.tagesspiegel.de' et 'tagesspiegel.de')."""
    if not quest_map or not domain:
        return None

    if domain in quest_map:
        return quest_map[domain]

    for known_domain, from_value in quest_map.items():
        if domain.endswith("." + known_domain) or known_domain.endswith("." + domain):
            return from_value

    return None


# --------------------------------------------------------------------------
# Génération du bloc osint:event
# --------------------------------------------------------------------------

def render_osint_block(ref_id: str, info: dict, quest_map: dict = None) -> str:
    domain = info["domain"]

    # Cherche si le domaine de la référence correspond à un event du quest
    matched_from = find_from_for_domain(domain, quest_map or {})

    # Le slug (nom de l'event) reste basé sur le titre ORIGINAL, non traduit,
    # tronqué aux 6 premiers mots. Préfixé par <from>_ si une correspondance
    # a été trouvée dans le quest.
    base_slug = slugify(truncate_words(info["title"], 7))
    slug = f"{slugify(matched_from)}_{base_slug}" if matched_from else base_slug

    # :from: utilise le from du quest si trouvé, sinon le domaine brut
    from_value = matched_from or domain

    # :label: et :description: sont traduits en français
    label_fr = clean_label(info["title_fr"] or info["title"])
    description_fr = info["description_fr"] or info["description"]

    url = info["url"]
    begin = info["date"] or ""

    lines = [
        f".. osint:event:: {slug}",
        f"    :label: {label_fr}",
    ]

    if description_fr:
        lines.append(f"    :description: {description_fr}")

    lines += [
        f"    :from: {from_value}",
        f"    :from-label: publie",
        f"    :cats: media",
        f"    :source:",
        f"    :url: {url}",
        f"    :begin: {begin}",
        "",
    ]

    return "\n".join(lines)


osint_plugins = collect_plugins()

if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)

def process_references(references: list, quest_map: dict, quest_existing_urls: set,
                        delay: float) -> str:
    """Analyse une liste de références {id, cite_text, url}, génère le bloc
    osint:event de chacune, puis renvoie le texte final classé par :from:.
    Factorise la logique commune aux commandes `wikipedia` et `file`."""
    entries = []
    for i, ref in enumerate(references, 1):
        print(f"[{i}/{len(references)}] {ref['url']}", file=sys.stderr)

        if normalize_url(ref["url"]) in quest_existing_urls:
            print(f"    -> already present on the Quest, ignored (not downloaded)",
                  file=sys.stderr)
            continue

        info = analyze_reference(ref)
        if info["status"] != "ok":
            print(f"    -> {info['status']}", file=sys.stderr)
        print(f"    -> language detected: {info['lang']}", file=sys.stderr)

        # Valeur utilisée pour le tri final (identique à celle écrite
        # dans le champ :from: du bloc osint:event généré ci-dessous).
        matched_from = find_from_for_domain(info["domain"], quest_map)
        from_value = matched_from or info["domain"]

        block = render_osint_block(ref["id"], info, quest_map)
        entries.append((from_value, block))
        time.sleep(delay)

    # Classe les résultats par :from: (insensible à la casse)
    entries.sort(key=lambda entry: entry[0].lower())

    return "\n".join(block for _, block in entries)


def extract_file_references(file_path: str, max_refs: int = None):
    """
    Retourne une liste de dicts {id, cite_text, url} à partir d'un fichier
    texte local contenant une URL par ligne. Les lignes vides et celles
    commençant par '#' sont ignorées, ainsi que les doublons.
    """
    references = []
    seen_urls = set()

    with open(file_path, "r", encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            link = clean_url(line)
            if not (link.startswith("http://") or link.startswith("https://")):
                print(f"    [ligne {line_no}] ignorée (pas une URL http(s)) : {line}",
                      file=sys.stderr)
                continue

            if link in seen_urls:
                continue
            seen_urls.add(link)

            references.append({
                "id": f"file-{line_no}",
                "cite_text": "",
                "url": link,
            })

            if max_refs and len(references) >= max_refs:
                break

    return references


@cli.command()
@click.argument('wiki_url', default=None)
@click.option('--max', type=int, default=None, help="Maximum number of references to process (useful for testing).")
@click.option('--delay', type=int, default=0.5, help="Delay between reference downloads (default: 0.5)")
@click.option('--no-browser-fallback', is_flag=True, help="Disables the fallback to a headless browser (Playwright/Selenium) in the event of anti-bot blocking (403, JS challenge, etc.).")
@click.option('--browser-engine', type=click.Choice(["playwright", "selenium"]), default="playwright", help="Headless browser engine to use for fallback (default: playwright)")
@click.option('--output', '-o', type=click.Path(dir_okay=False), default=None, help="Write the result to this text file instead of stdout.")
@click.pass_obj
def wikipedia(common, wiki_url, max, delay, no_browser_fallback, browser_engine, output):
    """Analyzes the references of a Wikipedia page and generates osint:event blocks."""
    sourcedir, builddir = parser_makefile(common.docdir)
    data = load_quest(builddir)

    global BROWSER_FALLBACK_ENABLED, BROWSER_ENGINE
    BROWSER_FALLBACK_ENABLED = not no_browser_fallback
    BROWSER_ENGINE = browser_engine

    quest_map = {}
    quest_existing_urls = set()
    quest_map, quest_existing_urls = load_quest_data(data)

    print(f"[*] Retrieving the Wikipedia page : {wiki_url}", file=sys.stderr)
    try:
        references = extract_wikipedia_references(wiki_url, max_refs=max)
    except requests.exceptions.RequestException as exc:
        print(f"[!] Unable to retrieve the Wikipedia page : {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] {len(references)} reference(s) found.", file=sys.stderr)

    output_text = process_references(references, quest_map, quest_existing_urls, delay)

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(output_text)
        print(f"[*] Result written to : {output}", file=sys.stderr)
    else:
        print(output_text)


@cli.command(name="file")
@click.argument('file_path', type=click.Path(exists=True, dir_okay=False), default=None)
@click.option('--max', type=int, default=None, help="Maximum number of URLs to process (useful for testing).")
@click.option('--delay', type=int, default=0.5, help="Delay between downloads (default: 0.5)")
@click.option('--no-browser-fallback', is_flag=True, help="Disables the fallback to a headless browser (Playwright/Selenium) in the event of anti-bot blocking (403, JS challenge, etc.).")
@click.option('--browser-engine', type=click.Choice(["playwright", "selenium"]), default="playwright", help="Headless browser engine to use for fallback (default: playwright)")
@click.option('--output', '-o', type=click.Path(dir_okay=False), default=None, help="Write the result to this text file instead of stdout.")
@click.pass_obj
def file_cmd(common, file_path, max, delay, no_browser_fallback, browser_engine, output):
    """Analyzes a local text file (one URL per line) and generates osint:event blocks."""
    sourcedir, builddir = parser_makefile(common.docdir)
    data = load_quest(builddir)

    global BROWSER_FALLBACK_ENABLED, BROWSER_ENGINE
    BROWSER_FALLBACK_ENABLED = not no_browser_fallback
    BROWSER_ENGINE = browser_engine

    quest_map = {}
    quest_existing_urls = set()
    quest_map, quest_existing_urls = load_quest_data(data)

    print(f"[*] Reading URLs from file : {file_path}", file=sys.stderr)
    references = extract_file_references(file_path, max_refs=max)

    print(f"[*] {len(references)} URL(s) found.", file=sys.stderr)

    output_text = process_references(references, quest_map, quest_existing_urls, delay)

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(output_text)
        print(f"[*] Result written to : {output}", file=sys.stderr)
    else:
        print(output_text)
