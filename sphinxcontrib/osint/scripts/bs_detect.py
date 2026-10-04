#!/usr/bin/env python3
"""
bs_detect.py — Détection semi-automatisée de contradictions ("bullshit detection")

Adaptation de la méthode décrite par Conspirador Norteño :
https://www.conspirator0.com/p/semi-automated-bullshit-detection

L'article original utilise un modèle propriétaire ("Jev" / typesafe_sdk) auquel
nous n'avons pas accès. Ce script reproduit la même logique en 3 étapes avec
un serveur Ollama local :

    1. download        -> télécharge les posts originaux d'un compte Bluesky
    2. autobio          -> filtre les posts (longueur) puis score la probabilité
                           que chaque post contienne une affirmation autobiographique
    3. contradictions   -> teste toutes les paires de posts autobiographiques
                           restants pour une probabilité de contradiction
    4. report           -> génère un tableau (CSV + Markdown) et des graphiques

    pipeline            -> enchaîne les 4 étapes en une seule commande

Installation :
    pip install click requests pandas matplotlib tabulate

Serveur Ollama :
    ollama serve                 # (déjà lancé en général)
    ollama pull qwen2.5:7b       # ou le modèle de votre choix
    Par défaut : http://localhost:11434
    Autre hôte : --host http://IP:11434  ou  export OLLAMA_HOST=http://IP:11434

Exemple d'utilisation complète :
    python bs_detect.py pipeline --handle exemple.bsky.social --output-dir resultats/ --model qwen2.5:7b

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


class OllamaClient:
    """Mini-client pour l'API HTTP d'Ollama."""

    def __init__(self, host: str | None, timeout: int = 300):
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")
        if not self.host.startswith(("http://", "https://")):
            self.host = "http://" + self.host
        self.timeout = timeout

    def check(self, model: str) -> None:
        """Vérifie que le serveur répond et que le modèle est disponible."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            click.echo(
                f"Impossible de joindre le serveur Ollama sur {self.host} : {e}\n"
                "Vérifiez qu'il tourne (ollama serve) ou utilisez --host.",
                err=True,
            )
            sys.exit(1)
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
        return json.loads(r.json()["message"]["content"])


def _get_client(host: str | None, model: str) -> OllamaClient:
    client = OllamaClient(host)
    client.check(model)
    return client


def _score(client: OllamaClient, model: str, question: str, payload: str,
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
@click.option("--model", default=DEFAULT_MODEL, show_default=True)
@click.option("--host", default=None, help="URL du serveur Ollama (sinon OLLAMA_HOST, sinon http://localhost:11434).")
@click.option("--keep-all", is_flag=True, help="Écrit tous les scores dans le CSV, même sous le seuil (utile pour inspection).")
def autobio(input_file, output, min_length, threshold, model, host, keep_all):
    """Trie les posts et note leur probabilité d'être autobiographiques."""
    client = _get_client(host, model)
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
@click.option("--model", default=DEFAULT_MODEL, show_default=True)
@click.option("--host", default=None, help="URL du serveur Ollama (sinon OLLAMA_HOST, sinon http://localhost:11434).")
@click.option("--max-posts", type=int, default=60, show_default=True,
              help="Limite le nombre de posts utilisés pour les paires (le coût croît en O(n^2)).")
def contradictions(input_file, output, model, host, max_posts):
    """Teste toutes les paires de posts autobiographiques pour des contradictions."""
    client = _get_client(host, model)
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
@click.option("--model", default=DEFAULT_MODEL, show_default=True)
@click.option("--host", default=None, help="URL du serveur Ollama.")
@click.option("--include-replies", is_flag=True)
@click.option("--include-reposts", is_flag=True)
@click.pass_context
def pipeline(ctx, handle, output_dir, min_length, autobio_threshold, max_posts_pairs,
             top, model, host, include_replies, include_reposts):
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
               min_length=min_length, threshold=autobio_threshold, model=model,
               host=host, keep_all=False)
    ctx.invoke(contradictions, input_file=str(auto_csv), output=str(contra_csv),
               model=model, host=host, max_posts=max_posts_pairs)
    ctx.invoke(report, input_file=str(contra_csv), top=top,
               charts_dir=str(charts_dir), table_out=str(table_out))

    click.echo(f"\nTerminé. Tous les fichiers sont dans {out}/")


if __name__ == "__main__":
    cli()
