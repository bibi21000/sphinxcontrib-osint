# -*- encoding: utf-8 -*-
"""
The harvest scripts
------------------------

"""
from __future__ import annotations
import os
import sys
import json
import click
import re
import time
import heapq
import unicodedata
from collections import defaultdict, deque
from datetime import datetime
from urllib.parse import urlparse, urlencode, parse_qs, urljoin
import random

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# Évite un appel réseau de géodétection au chargement du module translators
os.environ.setdefault("translators_default_region", "EN")
import translators as ts  # noqa: E402

from langdetect import detect as lang_detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
import pickle

from types import SimpleNamespace

from . import parser_makefile, cli, get_app, load_quest, JSONEncoder
from ..osintlib import OSIntQuest
from ..interfaces import BrowserProfileInterface

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

        if not link:
            continue

        norm_link = normalize_url(link)
        if norm_link in seen_urls:
            print(f"    [doublon] URL déjà vue dans les références Wikipedia, ignorée : {link}",
                  file=sys.stderr)
            continue
        seen_urls.add(norm_link)

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


def _jsonld_objects(soup: BeautifulSoup) -> list:
    """Renvoie tous les objets JSON-LD (schema.org) d'une page, à plat
    (listes et "@graph" dépliés)."""
    objects = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                objects.append(item)
                graph = item.get("@graph")
                if isinstance(graph, (list, dict)):
                    stack.append(graph)
    return objects


def guess_date_jsonld(soup: BeautifulSoup) -> str:
    """Date de publication déclarée dans le JSON-LD (datePublished en priorité)."""
    objects = _jsonld_objects(soup)
    for key in ("datePublished", "dateCreated", "dateModified"):
        for obj in objects:
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def guess_date(soup: BeautifulSoup) -> str:
    for tag_name, attrs in DATE_META_NAMES:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()

    jsonld_date = guess_date_jsonld(soup)
    if jsonld_date:
        return jsonld_date

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


def analyze_reference(ref: dict, fetcher=None) -> dict:
    """Télécharge la page cible et en extrait titre / description / date.

    `fetcher` : fonction url -> BeautifulSoup à utiliser à la place de
    `fetch_soup` (ex: navigateur déjà ouvert, avec son profil)."""
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
        soup = (fetcher or fetch_soup)(ref["url"])

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

def reorder_avoid_consecutive_domains(references: list) -> list:
    """Réordonne une liste de références {id, cite_text, url} pour éviter
    d'enchaîner deux téléchargements de suite sur le même domaine (afin de
    limiter le risque de blocage côté site distant).

    N'affecte QUE l'ordre de téléchargement : le regroupement par :from:
    lors de l'affichage final reste géré séparément par `entries.sort(...)`
    dans `process_references`.

    Algorithme glouton classique (cf. "Reorganize String", LeetCode 767) :
    à chaque étape, on prend une référence dans le domaine qui a le plus
    de références restantes, en excluant le domaine utilisé juste avant.
    Si un domaine est trop majoritaire pour éviter toute répétition
    consécutive, l'ordre obtenu reste le meilleur possible (les répétitions
    résiduelles sont alors inévitables)."""
    groups = defaultdict(deque)
    for ref in references:
        groups[domain_of(ref["url"])].append(ref)

    # Tas max simulé avec des compteurs négatifs (nombre de références
    # restantes pour chaque domaine).
    heap = [(-len(dq), dom) for dom, dq in groups.items()]
    heapq.heapify(heap)

    result = []
    delayed = None  # (compteur, domaine) du domaine utilisé à l'étape précédente

    # `or delayed` : quand il ne reste plus qu'un domaine (ou un domaine très
    # majoritaire), le tas est vide alors que ce domaine « en attente » a
    # encore des références : sans cette condition elles étaient perdues.
    while heap or delayed is not None:
        if not heap:
            heapq.heappush(heap, delayed)  # répétition consécutive inévitable
            delayed = None
        count, dom = heapq.heappop(heap)
        result.append(groups[dom].popleft())

        # Le domaine qu'on vient d'utiliser ne peut pas être réutilisé au
        # tour suivant : on le remet en attente d'un tour, puis on le
        # réinjecte dans le tas une fois qu'un autre domaine a été choisi.
        if delayed is not None:
            heapq.heappush(heap, delayed)
            delayed = None

        count += 1  # count est négatif -> incrémenter = décrémenter le restant
        if count < 0:
            delayed = (count, dom)

    return result


def process_references(references: list, quest_map: dict, quest_existing_urls: set,
                        delay: float, fetcher=None, sort_by: str = "from") -> str:
    """Analyse une liste de références {id, cite_text, url}, génère le bloc
    osint:event de chacune, puis renvoie le texte final classé par :from:.
    Factorise la logique commune aux commandes `wikipedia` et `file`.

    `sort_by` : "from" (défaut, classement par :from:) ou "date" (du plus
    récent au plus ancien, sans date en dernier)."""
    entries = []
    seen_urls = set()

    references = reorder_avoid_consecutive_domains(references)

    for i, ref in enumerate(references, 1):
        rank = f"#{ref['rank']} " if ref.get("rank") else ""
        print(f"[{i}/{len(references)}] {rank}{ref['url']}", file=sys.stderr)

        norm_url = normalize_url(ref["url"])

        if norm_url in quest_existing_urls:
            print(f"    -> already present on the Quest, ignored (not downloaded)",
                  file=sys.stderr)
            continue

        if norm_url in seen_urls:
            print(f"    -> URL en double dans la liste fournie / les références, ignorée",
                  file=sys.stderr)
            continue
        seen_urls.add(norm_url)

        info = analyze_reference(ref, fetcher=fetcher)
        if info["status"] != "ok":
            print(f"    -> {info['status']}", file=sys.stderr)
        print(f"    -> language detected: {info['lang']}", file=sys.stderr)

        # Valeur utilisée pour le tri final (identique à celle écrite
        # dans le champ :from: du bloc osint:event généré ci-dessous).
        matched_from = find_from_for_domain(info["domain"], quest_map)
        from_value = matched_from or info["domain"]

        block = render_osint_block(ref["id"], info, quest_map)
        entries.append((from_value, info["date"] or "", block))
        time.sleep(delay)

    if sort_by == "date":
        # Dates normalisées (AAAA-MM-JJ) : l'ordre alphabétique est chronologique ;
        # tri stable, les pages sans date (chaîne vide) finissent en dernier.
        entries.sort(key=lambda entry: entry[1], reverse=True)
    else:
        # Classe les résultats par :from: (insensible à la casse)
        entries.sort(key=lambda entry: entry[0].lower())

    return "\n".join(block for _, _, block in entries)


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

            norm_link = normalize_url(link)
            if norm_link in seen_urls:
                print(f"    [ligne {line_no}] doublon (URL déjà présente dans la liste), ignorée : {link}",
                      file=sys.stderr)
                continue
            seen_urls.add(norm_link)

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


# --------------------------------------------------------------------------
# Recherche Google restreinte à un site (commande `google`)
# --------------------------------------------------------------------------

GOOGLE_SEARCH_URL = "https://www.google.com/search"

# Boutons de la page de consentement Google (UE). On préfère refuser.
CONSENT_BUTTON_LABELS = ["Tout refuser", "Reject all", "Tout accepter", "Accept all"]

CAPTCHA_HINTS = [
    "unusual traffic",
    "trafic exceptionnel",
    "nos systèmes ont détecté",
    "our systems have detected",
    "g-recaptcha",
    "captcha-form",
]

NO_RESULT_HINTS = [
    "did not match any documents",
    "aucun document ne correspond",
    "aucun résultat ne correspond",
]


class GoogleBlocked(Exception):
    """Google affiche un captcha / un blocage qu'on ne peut pas franchir."""


class BrowserSession:
    """Navigateur (Playwright ou Selenium, Chrome/Chromium) gardé ouvert
    pour toute la commande : le consentement Google, un captcha résolu à la
    main et les cookies du profil restent valables d'une page à l'autre.

    Avec `user_data_dir` (et éventuellement `profile`), le navigateur utilise
    un profil persistant : utilisez un dossier dédié, pas votre profil
    quotidien (Chrome verrouille un profil déjà ouvert).
    """

    def __init__(self, engine="playwright", headless=True, user_data_dir=None,
                 profile=None, channel=None, timeout_ms=BROWSER_TIMEOUT_MS):
        self.engine = engine
        self.headless = headless
        self.user_data_dir = os.path.abspath(os.path.expanduser(user_data_dir)) if user_data_dir else None
        self.profile = profile
        self.channel = channel
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._driver = None
        self._html_cache = {}   # url normalisée -> html déjà chargé (cf. resolve_redirect)

    # -- cycle de vie ------------------------------------------------------

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def _chromium_args(self):
        args = ["--disable-blink-features=AutomationControlled", "--disable-infobars", "--no-sandbox"]
        if self.profile and self.user_data_dir:
            args.append(f"--profile-directory={self.profile}")
        elif self.profile:
            print("[!] --profile ignored : it needs --user-data-dir", file=sys.stderr)
        return args

    def start(self):
        if self.engine == "selenium":
            self._start_selenium()
        else:
            self._start_playwright()

    def _start_playwright(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("playwright is not installed : pip install playwright && playwright install chromium")
        self._pw = sync_playwright().start()
        kwargs = {"headless": self.headless, "args": self._chromium_args()}
        if self.channel:
            kwargs["channel"] = self.channel
        ctx_opts = {"locale": "fr-FR", "viewport": {"width": 1366, "height": 768}}
        if self.user_data_dir:
            self._context = self._pw.chromium.launch_persistent_context(
                self.user_data_dir, **kwargs, **ctx_opts)
        else:
            self._browser = self._pw.chromium.launch(**kwargs)
            self._context = self._browser.new_context(**ctx_opts)
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        self._context.set_default_timeout(self.timeout_ms)
        self._page = self._context.new_page()

    def _start_selenium(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            raise RuntimeError("selenium is not installed : pip install selenium webdriver-manager")
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--lang=fr-FR")
        options.add_argument("--disable-dev-shm-usage")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        for arg in self._chromium_args():
            options.add_argument(arg)
        if self.user_data_dir:
            options.add_argument(f"--user-data-dir={self.user_data_dir}")
        self._driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options)
        self._driver.set_page_load_timeout(self.timeout_ms / 1000)

    def close(self):
        for closer in (
            lambda: self._context and self._context.close(),
            lambda: self._browser and self._browser.close(),
            lambda: self._pw and self._pw.stop(),
            lambda: self._driver and self._driver.quit(),
        ):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
        self._context = self._browser = self._pw = self._page = self._driver = None

    # -- actions -----------------------------------------------------------

    def goto(self, url):
        if self._driver is not None:
            self._driver.get(url)
        else:
            self._page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")

    def html(self):
        if self._driver is not None:
            return self._driver.page_source
        # Playwright refuse de lire le contenu pendant une navigation (ex :
        # redirection après un captcha résolu, consentement cliqué...) :
        # on attend la fin du chargement puis on réessaie.
        for _ in range(15):
            try:
                return self._page.content()
            except Exception as exc:  # noqa: BLE001
                if "navigating" not in str(exc) and "context was destroyed" not in str(exc):
                    raise
                try:
                    self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:  # noqa: BLE001
                    pass
                self._page.wait_for_timeout(500)
        return self._page.content()

    def current_url(self):
        if self._driver is not None:
            return self._driver.current_url
        return self._page.url

    def settle(self, ms):
        """Pause (laisse le JS / les redirections se terminer)."""
        if self._driver is not None:
            time.sleep(ms / 1000)
        else:
            self._page.wait_for_timeout(ms)

    def click_any(self, labels):
        """Clique le premier bouton visible dont le texte contient un des
        `labels` (dans l'ordre), dans la page ou dans une de ses iframes (le
        dialogue de consentement de Google est souvent une iframe).
        Renvoie True si un clic a eu lieu."""
        for label in labels:
            try:
                if self._driver is not None:
                    if self._selenium_click(label):
                        return True
                else:
                    for frame in self._page.frames:
                        for loc in (frame.get_by_role("button", name=label),
                                    frame.locator("button", has_text=label)):
                            if loc.count() > 0:
                                loc.first.click(timeout=3000)
                                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _selenium_click(self, label):
        from selenium.webdriver.common.by import By
        driver = self._driver
        xpath = f'//button[contains(normalize-space(.), "{label}")]'
        try:
            driver.switch_to.default_content()
            frames = [None] + driver.find_elements(By.TAG_NAME, "iframe")
            for frame in frames:
                driver.switch_to.default_content()
                if frame is not None:
                    try:
                        driver.switch_to.frame(frame)
                    except Exception:  # noqa: BLE001
                        continue
                elems = [e for e in driver.find_elements(By.XPATH, xpath) if e.is_displayed()]
                if elems:
                    elems[0].click()
                    return True
        finally:
            driver.switch_to.default_content()
        return False

    def wait_for(self, css, timeout_ms=8000):
        """Attend qu'un élément (sélecteur CSS) apparaisse. Renvoie False si
        le délai est dépassé (sans lever d'exception)."""
        try:
            if self._driver is not None:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                WebDriverWait(self._driver, timeout_ms / 1000).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css)))
            else:
                self._page.wait_for_selector(css, timeout=timeout_ms, state="attached")
            return True
        except Exception:  # noqa: BLE001
            return False

    def resolve_redirect(self, url, referer=None):
        """Suit une redirection (ex : lien /goto?url=<jeton> de Google, dont la
        destination n'est pas lisible dans le HTML) et renvoie
        (url finale, html de la page d'arrivée). La page est gardée en cache :
        fetch_soup() ne la recharge pas."""
        if self._driver is not None:
            self._driver.get(url)
        else:
            kwargs = {"referer": referer} if referer else {}
            self._page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded", **kwargs)
        for _ in range(5):  # redirection JS / meta refresh éventuelle
            if "google." not in urlparse(self.current_url()).netloc:
                break
            self.settle(1000)
        final, html = self.current_url(), self.html()
        self._html_cache[normalize_url(clean_url(final))] = html
        return final, html

    def drop_cached(self, url):
        """Oublie la page gardée en cache pour cette URL (inutile, ex : déjà connue)."""
        self._html_cache.pop(normalize_url(url), None)

    def fetch_soup(self, url):
        """Équivalent de fetch_soup() avec ce navigateur (cookies du profil
        inclus) ; laisse un peu de temps aux challenges JS anti-bot."""
        cached = self._html_cache.pop(normalize_url(url), None)
        if cached:
            soup = BeautifulSoup(cached, "lxml")
            if not looks_like_bot_challenge(soup):
                return soup
        self.goto(url)
        html = self.html()
        for _ in range(4):
            soup = BeautifulSoup(html, "lxml")
            if not looks_like_bot_challenge(soup):
                return soup
            self.settle(2500)
            html = self.html()
        return BeautifulSoup(html, "lxml")


def normalize_site(site: str) -> str:
    """'https://www.la-croix.com/monde/' -> 'la-croix.com/monde'"""
    site = re.sub(r"^https?://", "", site.strip(), flags=re.IGNORECASE).rstrip("/")
    return site[4:] if site.lower().startswith("www.") else site


def build_google_query(site: str, term: str, exact: bool = True) -> str:
    """'la-croix.com' + 'Guerre Ukraine-Russie, jour' ->
    site:la-croix.com "Guerre Ukraine-Russie, jour" """
    term = term.strip()
    if exact and '"' not in term:
        term = f'"{term}"'
    return f"site:{normalize_site(site)} {term}"


def google_search_url(query: str, start: int = 0, hl: str = "fr", sort: str = "relevance") -> str:
    """URL de recherche Google. `sort="date"` ajoute tbs=sbd:1 (tri par date) :
    Google ne propose plus ce tri dans son interface, il peut donc être ignoré."""
    params = {"q": query, "hl": hl}
    if sort == "date":
        params["tbs"] = "sbd:1"
    if start:
        params["start"] = start
    return f"{GOOGLE_SEARCH_URL}?{urlencode(params)}"


GOOGLE_ORIGIN = "https://www.google.com"


def _host_matches(dom: str, host: str) -> bool:
    dom = dom.lower()
    return dom == host or dom.endswith("." + host)


def parse_google_results(html: str, site: str, base: str = GOOGLE_ORIGIN) -> list:
    """Extrait [{url, redirect, title}] d'une page de résultats Google, en ne
    gardant que les résultats du site demandé.

    - `url` : URL directe, quand le lien la contient (href http(s) ou /url?q=).
    - `redirect` : sinon, lien Google opaque (/goto?url=<jeton>) à faire suivre
      par le navigateur pour connaître l'URL (la destination n'est pas dans le
      HTML) ; le site est alors vérifié avec le texte du <cite> affiché.

    S'appuie sur la structure la plus stable de Google (un lien contenant un
    titre <h3> ou role="heading"), pas sur ses noms de classes. Si rien n'est
    trouvé ainsi, repli sur les liens directs du site ayant un texte."""
    host = normalize_site(site).split("/")[0].lower()
    soup = BeautifulSoup(html, "lxml")
    results, seen = [], set()

    def _cite_host(a):
        cite = a.find("cite")
        if not cite:
            return None
        m = re.match(r"https?://([^\s/›]+)", cite.get_text(" ", strip=True))
        return m.group(1) if m else None

    def _add(direct, redirect, title):
        if direct is None and redirect is None:
            return
        key = normalize_url(direct) if direct else redirect
        if key in seen:
            return
        seen.add(key)
        results.append({"url": clean_url(direct) if direct else None,
                        "redirect": None if direct else redirect,
                        "title": rst_escape(title)})

    candidates = []  # (direct, redirect, titre, a_un_cite_du_site)
    for a in soup.find_all("a", href=True):
        heading = a.find("h3") or a.find(attrs={"role": "heading"})
        if not heading:
            continue
        href, direct, redirect = a["href"], None, None
        if href.startswith(("http://", "https://")):
            direct = href
        elif href.startswith("/url?"):
            q = (parse_qs(urlparse(href).query).get("q") or [""])[0]
            if q.startswith(("http://", "https://")):
                direct = q
            else:
                redirect = urljoin(base, href)
        elif href.startswith("/goto?"):
            redirect = urljoin(base, href)
        else:
            continue
        cite_ok = False
        if direct:
            if not _host_matches(domain_of(direct), host):
                continue
        else:
            cite_host = _cite_host(a)
            if cite_host:
                if not _host_matches(cite_host, host):
                    continue
                cite_ok = True
        candidates.append((direct, redirect, heading.get_text(" ", strip=True), cite_ok))

    # Lien opaque SANS <cite> : vidéo YouTube, carrousel... pas un résultat du site.
    # On ne les écarte que si la page contient de vrais résultats avec <cite> du
    # site (sinon le balisage a peut-être changé : on garde tout et le suivi du
    # lien vérifiera le site d'arrivée).
    organic = any(cite_ok for _, _, _, cite_ok in candidates)
    for direct, redirect, title, cite_ok in candidates:
        if organic and direct is None and not cite_ok:
            continue
        _add(direct, redirect, title)

    if not results:
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            href = a["href"]
            if (href.startswith(("http://", "https://")) and len(text) >= 15
                    and _host_matches(domain_of(href), host)):
                _add(href, None, text)
    return results


def _is_google_captcha(url: str, html: str) -> bool:
    low = html.lower()
    return "/sorry/" in url or any(hint in low for hint in CAPTCHA_HINTS)


CONSENT_IFRAME_RE = re.compile(r"<iframe[^>]+src=[\"']https://consent\.google\.", re.IGNORECASE)
CONSENT_TEXT_RE = re.compile(r"avant d.acc[ée]der [àa] google|before you continue to google", re.IGNORECASE)


def _is_google_consent(url: str, html: str) -> bool:
    """Page de consentement (redirection) ou dialogue superposé aux résultats
    (iframe consent.google.com, ou texte « Avant d'accéder à Google »)."""
    if urlparse(url).netloc.startswith("consent."):
        return True
    return bool(CONSENT_IFRAME_RE.search(html) or CONSENT_TEXT_RE.search(html))


def google_fetch_results(session: BrowserSession, url: str, site: str,
                         captcha_wait: int = 120, dump_html: str = None) -> list:
    """Charge une page de résultats Google. Gère le consentement (clic
    automatique, page ou dialogue) et, en mode --headed, laisse
    `captcha_wait` secondes pour résoudre un captcha / un consentement à la
    main. Attend l'affichage des résultats avant de les lire.

    Le HTML garde souvent des traces du dialogue de consentement (iframe ou
    texte masqués) même après l'avoir refusé : seule la présence d'un bouton
    cliquable prouve qu'il est encore là."""
    session.goto(url)
    deadline = time.time() + captcha_wait
    warned = False
    stale = 0
    while True:
        cur, html = session.current_url(), session.html()
        consent = _is_google_consent(cur, html)
        on_consent_page = urlparse(cur).netloc.startswith("consent.")

        if consent and session.click_any(CONSENT_BUTTON_LABELS):
            session.settle(1500)   # laisse la page se recharger
            stale = 0
            if time.time() > deadline:
                raise GoogleBlocked("Google consent not passed in time")
            continue

        if _is_google_captcha(cur, html) and not consent:
            if session.headless:
                raise GoogleBlocked("Google asks for a captcha (headless mode) : retry with --headed")
            if not warned:
                print(f"[!] Captcha : solve it in the browser window ({captcha_wait}s max)...",
                      file=sys.stderr)
                warned = True
        elif consent and on_consent_page:
            if not session.headless and not warned:
                print(f"[!] Consent page : click it in the browser window ({captcha_wait}s max)...",
                      file=sys.stderr)
                warned = True
        else:
            # Les résultats sont dessinés par le JS : on les attend
            session.wait_for("a h3, a [role=heading]", 8000)
            html = session.html()
            results = parse_google_results(html, site)
            legit_empty = any(hint in html.lower() for hint in NO_RESULT_HINTS)
            if results or not consent or legit_empty or (session.headless and stale >= 2):
                if not results:
                    _google_no_result_diagnostic(session.current_url(), html, site, dump_html)
                return results
            # Trace de consentement, pas de bouton cliquable, pas de résultat :
            # le dialogue se charge peut-être encore (ou il faut le valider à la main)
            stale += 1
            if not session.headless and not warned:
                print(f"[!] Consent dialog : click it in the browser window ({captcha_wait}s max)...",
                      file=sys.stderr)
                warned = True

        if time.time() > deadline:
            raise GoogleBlocked("Google captcha / consent not passed in time")
        session.settle(2000)


def _google_no_result_diagnostic(url: str, html: str, site: str, dump_html: str = None):
    """Aide à comprendre un « 0 result » : page vide légitime, ou balisage
    Google que le parser ne reconnaît pas."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    host = normalize_site(site).split("/")[0].lower()
    n_links = sum(1 for a in soup.find_all("a", href=True) if host in a["href"])
    print(f"    [diag] no result parsed - title: {title!r}, url: {url[:80]}, "
          f"{len(soup.find_all('h3'))} <h3>, {n_links} link(s) containing {host}", file=sys.stderr)
    if dump_html:
        with open(dump_html, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"    [diag] page saved to {dump_html}", file=sys.stderr)
    else:
        print("    [diag] use --dump-html FILE to save this page", file=sys.stderr)


def google_search_references(session: BrowserSession, site: str, terms: list,
                             exact: bool = True, pages: int = 3, max_refs: int = None,
                             search_delay: float = 2.0, captcha_wait: int = 120,
                             dump_html: str = None, known_sources: set = None,
                             known_urls: set = None, sort: str = "relevance",
                             start_rank: int = 1, retries: int = 5) -> list:
    """Cherche chaque terme sur le site et renvoie
    [{id, cite_text, url, rank, term}] (cite_text = titre du résultat Google,
    utilisé si la page est illisible).

    Les liens opaques de Google (/goto?url=<jeton>) sont suivis par le
    navigateur pour obtenir l'URL réelle ; la page d'arrivée est gardée en
    cache et ne sera pas retéléchargée.

    `known_sources` : URLs normalisées de quest.sources ; `known_urls` : toutes
    les URLs connues du quest (sources + événements). Les résultats déjà
    connus sont signalés et écartés (ils ne comptent pas pour `max_refs`).

    Rang : position du résultat dans la liste Google du terme (1, 2, 3...),
    approximé par 10 * page + position sur la page (Google renvoie ~10
    résultats par page). `start_rank` reprend à ce rang, pour le PREMIER terme
    seulement (les suivants repartent du rang 1) : on saute directement à la
    bonne page de résultats, sans suivre les liens des rangs précédents.

    Pause aléatoire entre deux requêtes à Google (pages de résultats et liens
    /goto) : `search_delay` x un facteur tiré entre 0,5 et 1,5.

    Lien /goto non résolu (erreur réseau, redirection restée sur Google, page
    d'arrivée hors du site) : jusqu'à `retries` nouvelles tentatives, avec un
    délai qui double à chaque fois (`search_delay` x 1, 2, 4, 8... x facteur
    aléatoire 0,5-1,5, plafonné à 60 s)."""
    host = normalize_site(site).split("/")[0].lower()
    known_sources = known_sources or set()
    known_urls = known_urls or set()
    references, seen, seen_redirects = [], set(), set()
    n_known = n_foreign = 0
    last_rank, last_term = 0, None
    first_request = [True]

    def pause():
        """Pause aléatoire avant chaque requête à Google (sauf la première)."""
        if not first_request[0]:
            time.sleep(search_delay * random.uniform(0.5, 1.5))
        first_request[0] = False

    def handle(res, rank, term, search_url):
        """Traite un résultat (suivi du lien, filtres, ajout). Renvoie True
        quand `max_refs` est atteint."""
        nonlocal n_known, n_foreign
        if res["url"] is None:
            if res["redirect"] in seen_redirects:
                return False
            seen_redirects.add(res["redirect"])
            final, foreign, last_error = None, None, ""
            for attempt in range(retries + 1):
                if attempt == 0:
                    pause()
                else:
                    wait = min(search_delay * 2 ** (attempt - 1) * random.uniform(0.5, 1.5), 60)
                    print(f"    #{rank} [~] retry {attempt}/{retries} in {wait:.0f}s ({last_error})",
                          file=sys.stderr)
                    time.sleep(wait)
                try:
                    reached, _ = session.resolve_redirect(res["redirect"], referer=search_url)
                except Exception as exc:  # noqa: BLE001
                    last_error = (str(exc).splitlines() or [type(exc).__name__])[0][:100]
                    continue
                if _host_matches(domain_of(reached), host):
                    final = reached
                    break
                if "google." not in urlparse(reached).netloc:
                    # Arrivé sur un autre site (YouTube, TF1...) : ce n'est pas une
                    # panne passagère, réessayer ne changera rien.
                    foreign = reached
                    break
                last_error = f"ended on {reached[:80]}"   # reste sur Google (/goto, /sorry...) : on réessaie
            if foreign:
                print(f"    #{rank} [=] other site, ignored : {foreign}", file=sys.stderr)
                n_foreign += 1
                if hasattr(session, "drop_cached"):
                    session.drop_cached(foreign)
                return False
            if final is None:
                print(f"    #{rank} [!] link not resolved ({res['title'][:50]!r}) after "
                      f"{retries + 1} attempt(s) : {last_error}", file=sys.stderr)
                return False
            res["url"] = clean_url(final)
        norm = normalize_url(res["url"])
        if norm in seen:
            print(f"    #{rank} [=] duplicate, ignored : {res['url']}", file=sys.stderr)
            return False
        seen.add(norm)
        if norm in known_sources or norm in known_urls:
            where = "quest.sources" if norm in known_sources else "the quest (event)"
            print(f"    #{rank} [=] already in {where}, ignored : {res['url']}", file=sys.stderr)
            n_known += 1
            if hasattr(session, "drop_cached"):
                session.drop_cached(res["url"])
            return False
        print(f"    #{rank} {res['url']}", file=sys.stderr)
        references.append({
            "id": f"google-{len(references) + 1}",
            "cite_text": res["title"],
            "url": res["url"],
            "rank": rank,
            "term": term,
        })
        return bool(max_refs and len(references) >= max_refs)

    try:
        for term_idx, term in enumerate(terms):
            query = build_google_query(site, term, exact=exact)
            term_start = max(1, start_rank) if term_idx == 0 else 1
            first_page = (term_start - 1) // 10
            print(f"[*] Google : {query}" + (f"  (from rank #{term_start})" if term_start > 1 else ""),
                  file=sys.stderr)
            for page_no in range(first_page, first_page + pages):
                pause()
                search_url = google_search_url(query, start=10 * page_no, sort=sort)
                found = google_fetch_results(
                    session, search_url, site,
                    captcha_wait=captcha_wait, dump_html=dump_html)
                print(f"    page {page_no + 1} : {len(found)} result(s)", file=sys.stderr)
                if not found:
                    break
                for pos, res in enumerate(found, 1):
                    rank = 10 * page_no + pos
                    if rank < term_start:
                        continue
                    done = handle(res, rank, term, search_url)
                    # Le rang n'est mémorisé qu'une fois le résultat entièrement traité :
                    # après une interruption, on reprend au rang en cours (non terminé).
                    last_rank, last_term = rank, term
                    if done:
                        return references
    except GoogleBlocked as exc:
        print(f"[!] {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("[!] Interrupted (Ctrl+C) : the URLs already found are processed "
              "(Ctrl+C again to abort)", file=sys.stderr)
    finally:
        if n_known:
            print(f"[*] {n_known} result(s) already in the quest, ignored", file=sys.stderr)
        if n_foreign:
            print(f"[*] {n_foreign} result(s) from other sites, ignored", file=sys.stderr)
        if last_rank:
            print(f"[*] Last rank processed : #{last_rank} for {last_term!r} -> to resume : "
                  f"--start-rank {last_rank + 1} (with this term first)", file=sys.stderr)
    return references


def browser_profile_from_config(app, engine: str):
    """Profil de navigateur défini dans conf.py pour le moteur `engine` :
    (user_data_dir, profile, channel), ou (None, None, None) si aucun.

    Utilise osint_text_<engine>_user_data_dir et osint_text_<engine>_profile
    (les mêmes que le plugin text). Le channel (playwright seulement) vient de
    osint_text_playwright. Ici, selenium ne pilote que Chrome : un profil
    prévu pour un autre navigateur (osint_text_selenium) est ignoré."""
    if engine == "selenium":
        browser = getattr(app.config, "osint_text_selenium", None) or "chrome"
        if browser != "chrome":
            print(f"[!] osint_text_selenium = {browser!r} : harvest only drives Chrome with "
                  "selenium, conf.py profile ignored", file=sys.stderr)
            return None, None, None
    env = SimpleNamespace(config=app.config, srcdir=app.srcdir)
    user_data_dir, profile = BrowserProfileInterface.browser_profile(env, "text", engine)
    if user_data_dir is None:
        return None, None, None
    channel = getattr(app.config, "osint_text_playwright", None) if engine == "playwright" else None
    return user_data_dir, profile, channel


def quest_source_urls(quest) -> set:
    """URLs normalisées des `quest.sources` (osint:source)."""
    sources = getattr(quest, "sources", {}) or {}
    urls = (normalize_url(getattr(src, "url", None)) for src in sources.values())
    return {url for url in urls if url}


def read_terms_file(path: str) -> list:
    """Un terme par ligne ; lignes vides et commençant par '#' ignorées."""
    with open(path, "r", encoding="utf-8") as fh:
        return [l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#")]


@cli.command(name="google")
@click.argument('site')
@click.argument('terms', nargs=-1)
@click.option('--terms-file', type=click.Path(exists=True, dir_okay=False), default=None, help="File with one search term per line (added to TERMS).")
@click.option('--exact/--no-exact', default=True, help="Put each term between double quotes (default: yes, unless it already contains some).")
@click.option('--pages', type=int, default=3, help="Number of Google result pages per term (default: 3).")
@click.option('--max', type=int, default=None, help="Maximum number of URLs to process (useful for testing).")
@click.option('--delay', type=float, default=0.5, help="Delay between article downloads (default: 0.5)")
@click.option('--search-delay', type=float, default=2.0, help="Average pause between two Google requests (result pages and result links), randomized between 0.5x and 1.5x this value (default: 2)")
@click.option('--retries', type=int, default=5, help="Retries when a Google result link cannot be resolved ; the delay doubles each time : --search-delay x 1, 2, 4, 8... (max 60s) (default: 5).")
@click.option('--sort', 'sort_order', type=click.Choice(["relevance", "date"]), default="relevance", help="'date' : asks Google for a date sort (best effort, Google may ignore it) AND sorts the output from the most recent to the oldest page date (default: relevance, output sorted by :from:).")
@click.option('--start-rank', type=int, default=1, help="Resume at this Google result rank (see the #rank shown for each URL and the 'Last rank examined' line). Applies to the first TERM only (default: 1).")
@click.option('--browser-engine', type=click.Choice(["playwright", "selenium"]), default="playwright", help="Browser engine (default: playwright)")
@click.option('--headed', is_flag=True, help="Show the browser window (needed to solve a Google captcha by hand).")
@click.option('--user-data-dir', type=click.Path(file_okay=False), default=None, help="Browser user data directory (persistent profile : keeps Google consent, logins...). Default : osint_text_playwright_user_data_dir or osint_text_selenium_user_data_dir from conf.py. Use a dedicated directory.")
@click.option('--profile', default=None, help="Chrome profile name inside the user data dir (ie 'Default', 'Profile 1'). Default : osint_text_<engine>_profile from conf.py.")
@click.option('--channel', default=None, help="Playwright only : browser channel, ie 'chrome' to use Google Chrome instead of Chromium. Default : osint_text_playwright from conf.py when the profile comes from conf.py.")
@click.option('--captcha-wait', type=int, default=120, help="Seconds to wait for a captcha to be solved in --headed mode (default: 120).")
@click.option('--dump-html', type=click.Path(dir_okay=False), default=None, help="Save the Google page to this file when no result can be parsed (debug).")
@click.option('--urls-only', is_flag=True, help="Only list the URLs found on Google, do not fetch the articles.")
@click.option('--output', '-o', type=click.Path(dir_okay=False), default=None, help="Write the result to this text file instead of stdout.")
@click.pass_obj
def google_cmd(common, site, terms, terms_file, exact, pages, max, delay, search_delay,
               retries, sort_order, start_rank, browser_engine, headed, user_data_dir, profile, channel, captcha_wait,
               dump_html, urls_only, output):
    """Searches Google on a site (site:SITE "TERM") and generates osint:event blocks.

    Each TERM is a separate search ; the title, description and date of every
    result are read from the page (opengraph, JSON-LD, <time>...) with
    Playwright or Selenium.

    The browser profile is read from conf.py (osint_text_playwright_user_data_dir
    or osint_text_selenium_user_data_dir, depending on --browser-engine) unless
    --user-data-dir is given.

    \b
    Example:
      harvest google la-croix.com "Guerre Ukraine-Russie, jour" --headed
    """
    terms = list(terms)
    if terms_file:
        terms.extend(read_terms_file(terms_file))
    if not terms:
        print("[!] No search term given (TERMS or --terms-file).", file=sys.stderr)
        sys.exit(2)

    sourcedir, builddir = parser_makefile(common.docdir)
    data = load_quest(builddir)
    quest_map, quest_existing_urls = load_quest_data(data)

    if user_data_dir is None:
        # Pas de profil en ligne de commande : on prend celui de conf.py
        app = get_app(sourcedir=sourcedir, builddir=builddir)
        user_data_dir, cfg_profile, cfg_channel = browser_profile_from_config(app, browser_engine)
        if user_data_dir is not None:
            print(f"[*] Browser profile from conf.py : {user_data_dir}", file=sys.stderr)
            profile = profile or cfg_profile
            channel = channel or cfg_channel

    try:
        with BrowserSession(browser_engine, headless=not headed, user_data_dir=user_data_dir,
                            profile=profile, channel=channel) as session:
            references = google_search_references(
                session, site, terms, exact=exact, pages=pages, max_refs=max,
                search_delay=search_delay, captcha_wait=captcha_wait, dump_html=dump_html,
                known_sources=quest_source_urls(data), known_urls=quest_existing_urls,
                sort=sort_order, start_rank=start_rank, retries=retries)
            print(f"[*] {len(references)} new URL(s) found.", file=sys.stderr)

            if urls_only:
                output_text = "\n".join(f"{r['rank']}\t{r['url']}\t{r['cite_text']}" for r in references)
            else:
                output_text = process_references(
                    references, quest_map, quest_existing_urls, delay, fetcher=session.fetch_soup,
                    sort_by="date" if sort_order == "date" else "from")
    except RuntimeError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        sys.exit(1)

    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(output_text)
        print(f"[*] Result written to : {output}", file=sys.stderr)
    else:
        print(output_text)
