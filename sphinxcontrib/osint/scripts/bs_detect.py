#!/usr/bin/env python3
"""
bs_detect.py — Détection semi-automatisée de contradictions ("bullshit detection")

Adaptation de la méthode décrite par Conspirador Norteño :
https://www.conspirator0.com/p/semi-automated-bullshit-detection

L'article original utilise un modèle propriétaire ("Jev" / typesafe_sdk) auquel
nous n'avons pas accès. Ce script reproduit la même logique en 3 étapes avec
un serveur LLM local (Ollama ou Lemonade) :

    1. download        -> télécharge les posts originaux d'un compte Bluesky
    2. autobio          -> filtre les posts (longueur) puis score la probabilité
                           que chaque post contienne une affirmation autobiographique
    3. contradictions   -> teste toutes les paires de posts autobiographiques
                           restants pour une probabilité de contradiction
    4. report           -> génère un tableau (CSV + Markdown) et des graphiques

    pipeline            -> enchaîne les 4 étapes en une seule commande

Installation :
    pip install click requests pandas matplotlib tabulate

Serveur LLM (Ollama ou Lemonade) :
    Le serveur est lu dans le conf.py du projet Sphinx, avec les mêmes
    paramètres que le plugin flask (recherche sémantique) :
        osint_ollama_url      URL du serveur Ollama
        osint_lemonade_url    URL de l'API du serveur Lemonade
        osint_xapian_embedder 'ollama:<modèle>[@url]' ou 'lemonade:<modèle>[@url]'
                              (sert uniquement à choisir le backend et à
                              récupérer l'URL après '@')
    Le projet est localisé via --docdir (sinon $OSINT_HOME, sinon ./docs).

    Choix du backend (--backend auto|ollama|lemonade) en mode auto :
        1. le type de osint_xapian_embedder ('ollama:' ou 'lemonade:')
        2. sinon osint_ollama_url, puis osint_lemonade_url, s'ils sont définis
        3. sinon Ollama
    Choix de l'URL : --host > '@url' de osint_xapian_embedder > osint_*_url
    > $OLLAMA_HOST (Ollama seulement) > valeur par défaut du backend.

    Ollama   : ollama pull qwen2.5:7b   (modèle par défaut : qwen2.5:7b)
    Lemonade : --model obligatoire (modèle de chat llamacpp/flm déjà
               téléchargé côté Lemonade, ex. Qwen2.5-7B-Instruct-GGUF)

Exemple d'utilisation complète :
    python bs_detect.py pipeline --handle exemple.bsky.social --output-dir resultats/ --docdir docs
    python bs_detect.py pipeline --handle exemple.bsky.social --backend lemonade --model Qwen2.5-7B-Instruct-GGUF

Exemple étape par étape :
    python bs_detect.py download --handle exemple.bsky.social -o posts.csv
    python bs_detect.py autobio --input posts.csv -o posts_auto.csv
    python bs_detect.py contradictions --input posts_auto.csv -o contradictions.csv
    python bs_detect.py report --input contradictions.csv --charts-dir charts/
"""

from __future__ import annotations

import itertools
import json
import os
import re
import sys
import time
from pathlib import Path

import click
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BSKY_PUBLIC_API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
DEFAULT_MODEL = "qwen2.5:7b"  # modèle Ollama ; changer via --model (doit être déjà "pull")
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_LEMONADE_URL = "http://127.0.0.1:13305/v1"  # idem semanticlib.LemonadeEmbedder
BACKENDS = ("auto", "ollama", "lemonade")
MIN_TEXT_LEN_DEFAULT = 100
AUTOBIO_THRESHOLD_DEFAULT = 0.9


# ---------------------------------------------------------------------------
# Helpers Ollama : on force une sortie structurée (probabilité 0-1) via le
# paramètre "format" (JSON schema) de l'API /api/chat d'Ollama, ce qui joue le
# même rôle que les "Noul" de l'article.
# ---------------------------------------------------------------------------

_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "probability": {
            "type": "number",
            "description": "Probabilité entre 0.0 et 1.0",
        }
    },
    "required": ["probability"],
}

_SYSTEM_PROMPT = (
    "Tu es un outil d'analyse. Réponds uniquement par un objet JSON de la forme "
    '{"probability": <nombre entre 0.0 et 1.0>} avec ta meilleure estimation, '
    "sans aucun autre commentaire."
)


def _openai_base_url(url: str) -> str:
    """Normalise l'URL de base d'un serveur compatible OpenAI (comme
    semanticlib._openai_base_url): ajoute http:// si absent et '/v1' si l'URL
    ne se termine pas déjà par une version ('/v1', '/api/v1'...)."""
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = "http://" + url
    if not re.search(r"/v\d+$", url):
        url += "/v1"
    return url


def _extract_json(text: str) -> dict:
    """Extrait l'objet JSON d'une réponse de LLM. Tolère les blocs <think>,
    les clôtures ```json et le texte autour (serveurs sans sortie structurée)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    m = re.search(r"\{.*?\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    m = re.search(r'"?probability"?\s*[:=]\s*([0-9]*\.?[0-9]+)', text)
    if m:
        return {"probability": float(m.group(1))}
    raise ValueError(f"réponse non exploitable : {text[:120]!r}")


class LLMClient:
    """Interface commune des backends (Ollama / Lemonade)."""

    backend = "?"

    def __init__(self, host: str, timeout: int = 300):
        self.host = host
        self.timeout = timeout

    def _unreachable(self, e: Exception, hint: str) -> None:
        click.echo(
            f"Impossible de joindre le serveur {self.backend} sur {self.host} : {e}\n{hint}",
            err=True,
        )
        sys.exit(1)

    def check(self, model: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def chat_json(self, model: str, system: str, user: str, schema: dict) -> dict:  # pragma: no cover
        raise NotImplementedError


class OllamaClient(LLMClient):
    """Mini-client pour l'API HTTP d'Ollama."""

    backend = "Ollama"

    def check(self, model: str) -> None:
        """Vérifie que le serveur répond et que le modèle est disponible."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            self._unreachable(
                e, "Vérifiez qu'il tourne (ollama serve), osint_ollama_url dans conf.py ou utilisez --host.")
        names = {m.get("name", "") for m in r.json().get("models", [])}
        # "qwen2.5:7b" ou "qwen2.5" (équivaut à ":latest")
        candidates = {model, model if ":" in model else f"{model}:latest"}
        if not candidates & names:
            click.echo(
                f"Le modèle '{model}' n'est pas installé sur {self.host}. "
                f"Lancez : ollama pull {model}\n"
                f"Modèles disponibles : {', '.join(sorted(names)) or '(aucun)'}",
                err=True,
            )
            sys.exit(1)

    def chat_json(self, model: str, system: str, user: str, schema: dict) -> dict:
        r = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": schema,
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        return _extract_json(r.json()["message"]["content"])


class LemonadeClient(LLMClient):
    """Client pour un serveur Lemonade (API compatible OpenAI :
    GET <base>/models, POST <base>/chat/completions)."""

    backend = "Lemonade"

    def __init__(self, host: str, timeout: int = 300):
        super().__init__(_openai_base_url(host), timeout)
        # Sortie structurée (response_format json_schema) ; désactivée
        # automatiquement si le serveur la refuse (HTTP 400).
        self._use_schema = True

    def check(self, model: str | None) -> None:
        try:
            r = requests.get(f"{self.host}/models", timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            self._unreachable(
                e, "Vérifiez que Lemonade tourne, osint_lemonade_url dans conf.py ou utilisez --host.")
        ids = sorted(m.get("id", "") for m in r.json().get("data", []))
        if not model:
            click.echo(
                "Avec Lemonade, --model est obligatoire (modèle de chat llamacpp/flm).\n"
                f"Modèles listés par {self.host} : {', '.join(ids) or '(aucun)'}",
                err=True,
            )
            sys.exit(1)
        if model not in ids:
            # Simple avertissement : Lemonade peut charger le modèle à la demande.
            click.echo(
                f"[!] Le modèle '{model}' n'est pas dans la liste de {self.host} "
                f"({', '.join(ids) or 'aucun'}) ; tentative quand même.",
                err=True,
            )

    def chat_json(self, model: str, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "stream": False,
        }
        if self._use_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "probability", "strict": True, "schema": schema},
            }
        r = requests.post(f"{self.host}/chat/completions", json=payload, timeout=self.timeout)
        if r.status_code == 400 and self._use_schema:
            # Backend sans support de json_schema : on se rabat sur le prompt
            # (le système demande déjà un JSON) et sur _extract_json.
            self._use_schema = False
            payload.pop("response_format", None)
            r = requests.post(f"{self.host}/chat/completions", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return _extract_json(r.json()["choices"][0]["message"]["content"])


# ---------------------------------------------------------------------------
# Configuration : même source que le plugin flask (osint_ollama_url,
# osint_lemonade_url, osint_xapian_embedder dans le conf.py du projet Sphinx).
# ---------------------------------------------------------------------------

def _load_osint_conf(docdir: str | None) -> dict:
    """Lit les réglages LLM dans le conf.py du projet Sphinx (via get_app,
    comme les autres scripts). Renvoie {} si le projet est introuvable."""
    explicit = docdir is not None
    docdir = docdir or os.environ.get("OSINT_HOME") or "docs"
    makefile = os.path.join(docdir, "make.bat" if os.name == "nt" else "Makefile")
    if not os.path.isfile(makefile):
        if explicit:
            click.echo(f"[!] Projet Sphinx introuvable dans {docdir} (pas de Makefile) : "
                       "configuration du plugin flask ignorée.", err=True)
        return {}
    try:
        try:
            from . import parser_makefile, get_app
        except ImportError:  # lancé directement : python bs_detect.py
            from sphinxcontrib.osint.scripts import parser_makefile, get_app
        sourcedir, builddir = parser_makefile(docdir)
        config = get_app(sourcedir=sourcedir, builddir=builddir).config
    except Exception as e:  # noqa: BLE001
        click.echo(f"[!] Lecture de la configuration Sphinx impossible ({type(e).__name__}: {e}) : "
                   "configuration du plugin flask ignorée.", err=True)
        return {}
    return {
        "embedder": getattr(config, "osint_xapian_embedder", None),
        "ollama_url": getattr(config, "osint_ollama_url", None),
        "lemonade_url": getattr(config, "osint_lemonade_url", None),
    }


def _split_embedder(spec) -> tuple[str | None, str | None]:
    """'lemonade:modèle@url' -> ('lemonade', 'url') ; 'st:...' -> ('st', None)."""
    if not isinstance(spec, str) or ":" not in spec:
        return None, None
    kind, _, rest = spec.partition(":")
    _, _, url = rest.partition("@")
    return kind.strip().lower(), (url.strip() or None)


def _resolve_backend(backend: str, conf: dict) -> tuple[str, str | None]:
    """Choisit (backend, host) selon --backend et la config du plugin flask."""
    kind, spec_url = _split_embedder(conf.get("embedder"))
    if backend == "auto":
        if kind in ("ollama", "lemonade"):
            backend = kind
        elif conf.get("ollama_url"):
            backend = "ollama"
        elif conf.get("lemonade_url"):
            backend = "lemonade"
        else:
            backend = "ollama"
    # '@url' de l'embedder n'est valable que pour le même backend
    host = (spec_url if kind == backend else None) or conf.get(f"{backend}_url")
    return backend, host


def _get_client(backend: str, host: str | None, model: str | None,
                docdir: str | None) -> tuple[LLMClient, str]:
    conf = _load_osint_conf(docdir)
    backend, conf_host = _resolve_backend(backend, conf)
    if backend == "lemonade":
        client = LemonadeClient(host or conf_host or DEFAULT_LEMONADE_URL)
    else:
        host = host or conf_host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST
        if not host.startswith(("http://", "https://")):
            host = "http://" + host
        client = OllamaClient(host.rstrip("/"))
        model = model or DEFAULT_MODEL
    client.check(model)
    click.echo(f"Serveur {client.backend} : {client.host} — modèle : {model}", err=True)
    return client, model


def llm_options(f):
    """Options communes aux commandes qui interrogent le LLM."""
    options = [
        click.option("--backend", type=click.Choice(BACKENDS), default="auto", show_default=True,
                     help="Serveur LLM. auto : déduit de osint_xapian_embedder / osint_*_url du conf.py."),
        click.option("--model", default=None,
                     help=f"Modèle de chat (Ollama : défaut {DEFAULT_MODEL} ; Lemonade : obligatoire)."),
        click.option("--host", default=None,
                     help="URL du serveur (sinon osint_ollama_url / osint_lemonade_url du conf.py, "
                          "sinon $OLLAMA_HOST, sinon la valeur par défaut du backend)."),
        click.option("--docdir", default=None, type=click.Path(file_okay=False),
                     help="Dossier de la documentation Sphinx (Makefile) pour lire le conf.py "
                          "(sinon $OSINT_HOME, sinon ./docs)."),
    ]
    for opt in reversed(options):
        f = opt(f)
    return f


def _score(client: LLMClient, model: str, question: str, payload: str,
           retries: int = 3) -> float:
    """Envoie `payload` au modèle avec `question`, force une réponse structurée
    {"probability": float} via le JSON schema, et renvoie ce nombre."""
    last_err = None
    for attempt in range(retries):
        try:
            data = client.chat_json(
                model,
                _SYSTEM_PROMPT,
                f"{question}\n\n{payload}",
                _SCORE_SCHEMA,
            )
            prob = float(data.get("probability", 0.0))
            return max(0.0, min(1.0, prob))
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    click.echo(f"  [!] échec après {retries} tentatives : {last_err}", err=True)
    return 0.0


# ---------------------------------------------------------------------------
# Étape 1 : téléchargement (Bluesky, API publique, pas d'auth nécessaire)
# ---------------------------------------------------------------------------

def _fetch_bluesky_posts(handle: str, include_replies: bool, include_reposts: bool,
                          max_posts: int | None) -> list[dict]:
    posts = []
    cursor = None
    while True:
        params = {"actor": handle, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(BSKY_PUBLIC_API, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        feed = data.get("feed", [])
        if not feed:
            break
        for item in feed:
            is_repost = "reason" in item and item["reason"].get("$type", "").endswith(
                "reasonRepost"
            )
            is_reply = item.get("reply") is not None
            if is_repost and not include_reposts:
                continue
            if is_reply and not include_replies:
                continue
            record = item["post"].get("record", {})
            posts.append(
                {
                    "uri": item["post"].get("uri"),
                    "createdAt": record.get("createdAt"),
                    "text": record.get("text", ""),
                    "is_reply": is_reply,
                    "is_repost": is_repost,
                }
            )
            if max_posts and len(posts) >= max_posts:
                return posts
        cursor = data.get("cursor")
        if not cursor:
            break
    return posts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Détection semi-automatisée de contradictions dans les posts d'un compte."""


@cli.command()
@click.option("--handle", required=True, help="Handle Bluesky, ex: exemple.bsky.social")
@click.option("-o", "--output", "output", default="posts.csv", show_default=True,
              type=click.Path(dir_okay=False, writable=True))
@click.option("--include-replies", is_flag=True, help="Inclure les réponses (pas seulement les posts originaux).")
@click.option("--include-reposts", is_flag=True, help="Inclure les reposts.")
@click.option("--max-posts", type=int, default=None, help="Nombre maximum de posts à télécharger.")
def download(handle, output, include_replies, include_reposts, max_posts):
    """Télécharge les posts d'un compte Bluesky vers un CSV."""
    click.echo(f"Téléchargement des posts de @{handle}...")
    posts = _fetch_bluesky_posts(handle, include_replies, include_reposts, max_posts)
    if not posts:
        click.echo("Aucun post trouvé (vérifiez le handle).", err=True)
        sys.exit(1)
    df = pd.DataFrame(posts)
    df.to_csv(output, index=False)
    click.echo(f"{len(df)} posts enregistrés dans {output}")


@cli.command()
@click.option("-i", "--input", "input_file", required=True, type=click.Path(exists=True))
@click.option("-o", "--output", "output", default="posts_auto.csv", show_default=True)
@click.option("--min-length", default=MIN_TEXT_LEN_DEFAULT, show_default=True,
              help="Longueur minimale du texte pour être testé (évite les faux positifs sur phrases courtes).")
@click.option("--threshold", default=AUTOBIO_THRESHOLD_DEFAULT, show_default=True,
              help="Seuil de probabilité au-dessus duquel un post est retenu comme autobiographique.")
@llm_options
@click.option("--keep-all", is_flag=True, help="Écrit tous les scores dans le CSV, même sous le seuil (utile pour inspection).")
def autobio(input_file, output, min_length, threshold, backend, model, host, docdir, keep_all):
    """Trie les posts et note leur probabilité d'être autobiographiques."""
    client, model = _get_client(backend, host, model, docdir)
    df = pd.read_csv(input_file)
    df["text"] = df["text"].fillna("")
    before = len(df)
    df = df[df["text"].str.len() >= min_length].reset_index(drop=True)
    click.echo(f"{len(df)}/{before} posts conservés après filtrage sur la longueur (>= {min_length} caractères).")

    scores = []
    with click.progressbar(df["text"], label="Scoring autobiographique") as bar:
        for text in bar:
            score = _score(
                client, model,
                "Est-ce que ce texte contient une affirmation autobiographique "
                "(un détail sur la vie personnelle, la famille, le métier, la "
                "santé, le passé, etc. de son auteur) ?",
                text,
            )
            scores.append(score)
    df["autobiographical"] = scores
    df = df.sort_values("autobiographical", ascending=False)

    if not keep_all:
        kept = df[df["autobiographical"] >= threshold]
        click.echo(f"{len(kept)} posts au-dessus du seuil {threshold} (sur {len(df)} testés).")
        df_out = kept
    else:
        df_out = df

    df_out.to_csv(output, index=False)
    click.echo(f"Résultats enregistrés dans {output}")


@cli.command()
@click.option("-i", "--input", "input_file", required=True, type=click.Path(exists=True))
@click.option("-o", "--output", "output", default="contradictions.csv", show_default=True)
@llm_options
@click.option("--max-posts", type=int, default=60, show_default=True,
              help="Limite le nombre de posts utilisés pour les paires (le coût croît en O(n^2)).")
def contradictions(input_file, output, backend, model, host, docdir, max_posts):
    """Teste toutes les paires de posts autobiographiques pour des contradictions."""
    client, model = _get_client(backend, host, model, docdir)
    df = pd.read_csv(input_file)
    texts = df["text"].fillna("").tolist()

    if len(texts) > max_posts:
        click.echo(
            f"[!] {len(texts)} posts autobiographiques, limité à {max_posts} "
            f"(les mieux notés) pour éviter O(n^2) trop coûteux. "
            f"Ajustez --max-posts si besoin.",
            err=True,
        )
        texts = texts[:max_posts]

    pairs = list(itertools.combinations(range(len(texts)), 2))
    click.echo(f"{len(pairs)} paires à tester...")

    results = []
    with click.progressbar(pairs, label="Scoring des contradictions") as bar:
        for i, j in bar:
            text1, text2 = texts[i], texts[j]
            score = _score(
                client, model,
                "Voici deux extraits (text1 et text2) d'un même compte. "
                "Est-ce que quelque chose dans text1 contredit quelque chose "
                "dans text2 (dates, chiffres, faits personnels incompatibles) ?",
                f"text1: {text1}\n\ntext2: {text2}",
            )
            results.append({"text1": text1, "text2": text2, "contradiction": score})

    out_df = pd.DataFrame(results).sort_values("contradiction", ascending=False)
    out_df.to_csv(output, index=False)
    click.echo(f"Résultats enregistrés dans {output}")


@cli.command()
@click.option("-i", "--input", "input_file", required=True, type=click.Path(exists=True),
              help="CSV produit par la commande 'contradictions'.")
@click.option("--top", default=20, show_default=True, help="Nombre de paires à afficher dans le tableau.")
@click.option("--charts-dir", default="charts", show_default=True, type=click.Path(file_okay=False))
@click.option("--table-out", default="top_contradictions.md", show_default=True,
              help="Fichier Markdown contenant le tableau des meilleurs résultats.")
def report(input_file, top, charts_dir, table_out):
    """Génère un tableau (Markdown) et des graphiques à partir des scores de contradiction."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    Path(charts_dir).mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(input_file)

    # --- Tableau des meilleurs résultats ---
    top_df = df.head(top).copy()
    top_df["text1"] = top_df["text1"].str.slice(0, 140)
    top_df["text2"] = top_df["text2"].str.slice(0, 140)

    try:
        md_table = top_df.to_markdown(index=False)
    except ImportError:
        md_table = top_df.to_string(index=False)

    with open(table_out, "w", encoding="utf-8") as f:
        f.write(f"# Top {top} contradictions potentielles\n\n")
        f.write(md_table)
        f.write("\n")
    click.echo(f"Tableau écrit dans {table_out}")
    click.echo("\n" + md_table[:3000] + ("\n... (tronqué)" if len(md_table) > 3000 else ""))

    # --- Graphique 1 : distribution des scores de contradiction ---
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(df["contradiction"], bins=20, color="#7c3aed", edgecolor="white")
    ax.set_title("Distribution des scores de contradiction (toutes les paires)")
    ax.set_xlabel("Probabilité de contradiction")
    ax.set_ylabel("Nombre de paires")
    fig.tight_layout()
    fig.savefig(Path(charts_dir) / "distribution_contradictions.png", dpi=150)
    plt.close(fig)

    # --- Graphique 2 : barres horizontales des top N paires ---
    fig, ax = plt.subplots(figsize=(9, max(4, 0.4 * top)))
    labels = [f"#{i+1}" for i in range(len(top_df))]
    ax.barh(labels[::-1], top_df["contradiction"][::-1], color="#dc2626")
    ax.set_xlim(0, 1)
    ax.set_xlabel("Probabilité de contradiction")
    ax.set_title(f"Top {top} paires les plus contradictoires")
    fig.tight_layout()
    fig.savefig(Path(charts_dir) / "top_contradictions.png", dpi=150)
    plt.close(fig)

    click.echo(f"Graphiques enregistrés dans {charts_dir}/")


@cli.command()
@click.option("--handle", required=True, help="Handle Bluesky, ex: exemple.bsky.social")
@click.option("--output-dir", default="resultats", show_default=True, type=click.Path(file_okay=False))
@click.option("--min-length", default=MIN_TEXT_LEN_DEFAULT, show_default=True)
@click.option("--autobio-threshold", default=AUTOBIO_THRESHOLD_DEFAULT, show_default=True)
@click.option("--max-posts-pairs", default=60, show_default=True,
              help="Limite de posts utilisés pour les paires (coût O(n^2)).")
@click.option("--top", default=20, show_default=True)
@llm_options
@click.option("--include-replies", is_flag=True)
@click.option("--include-reposts", is_flag=True)
@click.pass_context
def pipeline(ctx, handle, output_dir, min_length, autobio_threshold, max_posts_pairs,
             top, backend, model, host, docdir, include_replies, include_reposts):
    """Enchaîne download -> autobio -> contradictions -> report en une commande."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    posts_csv = out / "posts.csv"
    auto_csv = out / "posts_auto.csv"
    contra_csv = out / "contradictions.csv"
    charts_dir = out / "charts"
    table_out = out / "top_contradictions.md"

    ctx.invoke(download, handle=handle, output=str(posts_csv),
               include_replies=include_replies, include_reposts=include_reposts,
               max_posts=None)
    ctx.invoke(autobio, input_file=str(posts_csv), output=str(auto_csv),
               min_length=min_length, threshold=autobio_threshold, backend=backend,
               model=model, host=host, docdir=docdir, keep_all=False)
    ctx.invoke(contradictions, input_file=str(auto_csv), output=str(contra_csv),
               backend=backend, model=model, host=host, docdir=docdir,
               max_posts=max_posts_pairs)
    ctx.invoke(report, input_file=str(contra_csv), top=top,
               charts_dir=str(charts_dir), table_out=str(table_out))

    click.echo(f"\nTerminé. Tous les fichiers sont dans {out}/")


if __name__ == "__main__":
    cli()
