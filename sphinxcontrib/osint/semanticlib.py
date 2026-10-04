# -*- encoding: utf-8 -*-
"""
Couche de recherche sémantique pour XapianIndexer.

Principe
--------
* Les vecteurs sont stockés DANS la base Xapian (valeur SLOT_EMBED de chaque
  document, float16 normalisés, un ou plusieurs chunks concaténés). Un seul
  artefact à déployer, et ils survivent au compactage (Database.compact()
  copie les valeurs) et à la purge (delete_document les emporte).
* Incrémental: un second slot (SLOT_EMBHASH) contient blake2b(modèle + texte).
  Seuls les documents dont le texte ou le modèle a changé sont ré-embeddés.
* Recherche: produit scalaire (= cosinus, vecteurs normalisés) par numpy sur
  une matrice float16 chargée en mémoire une fois par génération d'index,
  puis max-pooling par document. Fusion avec BM25 via Reciprocal Rank Fusion.

Dépendances: numpy (obligatoire), requests (Ollama) ou sentence-transformers.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import numpy as np

logger = logging.getLogger(__name__)

SLOT_EMBED = 12      # vecteurs (float16, chunks concaténés)
SLOT_EMBHASH = 13    # blake2b(modèle + texte embeddé)

META_MODEL = 'embed_model'
META_DIM = 'embed_dim'
META_GENERATION = 'embed_generation'


# --------------------------------------------------------------------------
# Découpage / (dé)sérialisation
# --------------------------------------------------------------------------
def chunk_text(text, max_chars=1200, overlap=150, max_chunks=12):
    """Découpe `text` en chunks d'environ `max_chars` caractères, en coupant
    de préférence sur une fin de phrase ou un espace. Le nombre de chunks est
    plafonné pour borner la taille de la valeur Xapian."""
    text = ' '.join((text or '').split())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks, start = [], 0
    while start < len(text) and len(chunks) < max_chunks:
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = max(text.rfind('. ', start, end), text.rfind(' ', start, end))
            if cut > start + max_chars // 2:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def pack_vectors(vectors):
    """(n, dim) float -> bytes float16."""
    return np.ascontiguousarray(vectors, dtype=np.float16).tobytes()


def unpack_vectors(blob, dim):
    arr = np.frombuffer(blob, dtype=np.float16)
    if dim <= 0 or arr.size % dim:
        return np.empty((0, max(dim, 1)), dtype=np.float16)
    return arr.reshape(-1, dim)


def _normalize(m):
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


# --------------------------------------------------------------------------
# Embedders
# --------------------------------------------------------------------------
def default_prefixes(model):
    """Préfixes de tâche (requête, document) recommandés pour `model`.
    Certains modèles donnent de bien meilleurs résultats avec: nomic-embed-text
    ('search_query: ' / 'search_document: '), la famille e5 ('query: ' /
    'passage: '). Aucun pour les autres (bge-m3...)."""
    m = (model or '').lower()
    if 'nomic-embed' in m:
        return 'search_query: ', 'search_document: '
    if re.search(r'(^|[^a-z0-9])e5([^a-z0-9]|$)', m):
        return 'query: ', 'passage: '
    return '', ''


def _openai_base_url(url):
    """Normalise l'URL de base d'un serveur compatible OpenAI: ajoute le
    schéma http:// si absent et '/v1' si l'URL ne se termine pas déjà par une
    version ('/v1', '/api/v1', '/api/v0'...)."""
    url = url.strip().rstrip('/')
    if '://' not in url:
        url = 'http://' + url
    if not re.search(r'/v\d+$', url):
        url += '/v1'
    return url


#: Valeurs par défaut des embedders HTTP (Ollama / Lemonade), surchargeables
#: par osint_xapian_embed_batch / osint_xapian_embed_workers dans conf.py.
DEFAULT_EMBED_BATCH = 32
DEFAULT_EMBED_WORKERS = 2
#: Durée pendant laquelle Ollama garde le modèle d'embedding en mémoire après
#: la dernière requête (paramètre `keep_alive` de /api/embed; son défaut côté
#: serveur est 5 min). Surchargeable par osint_ollama_keep_alive.
DEFAULT_OLLAMA_KEEP_ALIVE = '30m'


class _HTTPBatchEmbedder:
    """Socle commun des embedders HTTP (Ollama, Lemonade).

    Optimisations de `embed()` pour un serveur distant:
    * les textes sont triés par longueur décroissante avant d'être découpés
      en lots (moins de padding par lot, les lots les plus lourds partent
      en premier), puis l'ordre d'origine est restauré;
    * les lots sont envoyés en parallèle (`workers` requêtes simultanées) -
      le serveur doit pouvoir les traiter en parallèle (OLLAMA_NUM_PARALLEL
      pour Ollama, `--parallel` pour llama.cpp/Lemonade), sinon elles
      s'empilent sans gain ni perte notable;
    * une `requests.Session` partagée réutilise les connexions (keep-alive).
    Les sous-classes fournissent `_embed_batch(batch)` -> liste de vecteurs.
    """

    def _init_http(self, batch_size, workers):
        self.batch_size = max(1, int(batch_size or DEFAULT_EMBED_BATCH))
        self.workers = max(1, int(workers or DEFAULT_EMBED_WORKERS))
        self._session = None
        self._session_lock = threading.Lock()

    def _http(self):
        """Session requests partagée entre les threads (créée à la demande,
        pool de connexions dimensionné sur le nombre de workers)."""
        if self._session is None:
            with self._session_lock:
                if self._session is None:
                    import requests
                    from requests.adapters import HTTPAdapter
                    session = requests.Session()
                    adapter = HTTPAdapter(pool_connections=1, pool_maxsize=self.workers)
                    session.mount('http://', adapter)
                    session.mount('https://', adapter)
                    self._session = session
        return self._session

    def _embed_batch(self, batch):  # pragma: no cover - interface
        raise NotImplementedError

    def embed(self, texts, kind='doc'):
        prefix = self.query_prefix if kind == 'query' else self.doc_prefix
        texts = [prefix + t for t in texts]
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        # Tri par longueur décroissante (proxy du nombre de tokens).
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]), reverse=True)
        batches = [[texts[i] for i in order[start:start + self.batch_size]]
                   for start in range(0, len(order), self.batch_size)]
        if self.workers > 1 and len(batches) > 1:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(batches))) as pool:
                results = list(pool.map(self._embed_batch, batches))   # garde l'ordre
        else:
            results = [self._embed_batch(batch) for batch in batches]
        vecs = _normalize([v for result in results for v in result])
        out = np.empty_like(vecs)
        out[order] = vecs          # restaure l'ordre d'origine
        return out


class OllamaEmbedder(_HTTPBatchEmbedder):
    """Embeddings via Ollama (/api/embed). Ex: modèle 'bge-m3'."""

    def __init__(self, model='bge-m3', url=None,
                 batch_size=None, timeout=300, query_prefix=None, doc_prefix=None,
                 url_source=None, workers=None, keep_alive=None):
        self.model = model
        # '30m', '1h', 3600 (secondes) ou -1 (jamais déchargé)
        self.keep_alive = keep_alive if keep_alive not in (None, '') else DEFAULT_OLLAMA_KEEP_ALIVE
        dq, dd = default_prefixes(model)
        query_prefix = dq if query_prefix is None else query_prefix
        doc_prefix = dd if doc_prefix is None else doc_prefix
        # URL du serveur (osint_ollama_url dans conf.py, ou après '@' dans
        # osint_xapian_embedder); à défaut localhost. Accepte 'host:port'
        # sans schéma.
        if url:
            self.url_source = url_source or 'argument'
        else:
            url = 'http://127.0.0.1:11434'
            self.url_source = 'valeur par défaut (osint_ollama_url non défini)'
        if '://' not in url:
            url = 'http://' + url
        self.url = url.rstrip('/')
        self._init_http(batch_size, workers)
        self.timeout = timeout
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
        self.name = f'ollama:{model}'

    def describe(self):
        """Lignes décrivant la configuration (affichées au début de l'indexation)."""
        return [
            f"Serveur Ollama : {self.url} ({self.url_source})",
            f"Modèle         : {self.model} (gardé en mémoire {self.keep_alive} après usage)",
            f"Batch / timeout: {self.batch_size} textes par requête x {self.workers} "
            f"requête(s) en parallèle / {self.timeout}s",
            f"Préfixes       : requête={self.query_prefix!r}, document={self.doc_prefix!r}",
        ]

    def ping(self, timeout=2):
        """(ok, détail): le serveur Ollama répond-il? Appel léger, sans
        embedding. `détail` explique l'échec (module absent, URL, erreur)."""
        try:
            import requests
        except ImportError:
            return False, "module Python 'requests' absent de cette installation (pip install requests)"
        try:
            requests.get(f'{self.url}/api/version', timeout=timeout).raise_for_status()
            return True, ''
        except Exception as e:
            return False, f"{self.url} : {type(e).__name__}"

    def check(self, timeout=5):
        """Vérifie (sans jamais lever) que le serveur répond, que le modèle y
        est présent et qu'un embedding de test fonctionne.
        Retourne (ok, [lignes])."""
        import requests
        lines = []
        try:
            r = requests.get(f'{self.url}/api/version', timeout=timeout)
            r.raise_for_status()
            lines.append(f"Serveur joignable (Ollama {r.json().get('version', '?')})")
        except Exception as e:
            return False, [f"Serveur INJOIGNABLE: {type(e).__name__}: {str(e)[:120]}"]
        try:
            r = requests.get(f'{self.url}/api/tags', timeout=timeout)
            r.raise_for_status()
            names = [m.get('name', '') for m in r.json().get('models', [])]
            wanted = self.model if ':' in self.model else self.model + ':latest'
            if wanted not in names:
                lines.append(
                    f"Modèle '{self.model}' ABSENT du serveur "
                    f"(disponibles: {', '.join(names) or 'aucun'}) — "
                    f"à installer: ollama pull {self.model}")
                return False, lines
            lines.append(f"Modèle '{self.model}' présent")
        except Exception as e:
            lines.append(f"Liste des modèles indisponible ({type(e).__name__}: {e})")
        try:
            vec = self.embed(['test'])
            lines.append(f"Embedding de test OK (dimension {vec.shape[1]})")
        except Exception as e:
            lines.append(f"Embedding de test ÉCHOUÉ: {type(e).__name__}: {e}")
            return False, lines
        return True, lines

    def _embed_batch(self, batch):
        resp = self._http().post(f'{self.url}/api/embed',
                                 json={'model': self.model, 'input': batch,
                                       'keep_alive': self.keep_alive},
                                 timeout=self.timeout)
        resp.raise_for_status()
        vectors = resp.json()['embeddings']
        if len(vectors) != len(batch):
            raise ValueError(f"Ollama a renvoyé {len(vectors)} vecteurs pour {len(batch)} textes")
        return vectors


class LemonadeEmbedder(_HTTPBatchEmbedder):
    """Embeddings via un serveur Lemonade (API compatible OpenAI,
    POST <base>/embeddings). Ex: 'lemonade:nomic-embed-text-v1-GGUF'.

    Seuls les modèles des recettes llamacpp et flm gèrent les embeddings
    (pas les modèles ONNX/OGA). L'URL de base doit désigner l'API, par exemple
    http://127.0.0.1:13305/v1 ou http://127.0.0.1:8000/api/v1 selon la version
    de Lemonade; sans suffixe de version, '/v1' est ajouté."""

    DEFAULT_URL = 'http://127.0.0.1:13305/v1'

    def __init__(self, model='nomic-embed-text-v1-GGUF', url=None,
                 batch_size=None, timeout=300, query_prefix=None, doc_prefix=None,
                 url_source=None, workers=None):
        self.model = model
        dq, dd = default_prefixes(model)
        self.query_prefix = dq if query_prefix is None else query_prefix
        self.doc_prefix = dd if doc_prefix is None else doc_prefix
        if url:
            self.url_source = url_source or 'argument'
        else:
            url = self.DEFAULT_URL
            self.url_source = 'valeur par défaut (osint_lemonade_url non défini)'
        self.url = _openai_base_url(url)
        self._init_http(batch_size, workers)
        self.timeout = timeout
        self.name = f'lemonade:{model}'

    def describe(self):
        return [
            f"Serveur Lemonade: {self.url} ({self.url_source})",
            f"Modèle         : {self.model}",
            f"Batch / timeout: {self.batch_size} textes par requête x {self.workers} "
            f"requête(s) en parallèle / {self.timeout}s",
            f"Préfixes       : requête={self.query_prefix!r}, document={self.doc_prefix!r}",
        ]

    def ping(self, timeout=2):
        """(ok, détail): le serveur répond-il? (GET <base>/models, léger)."""
        try:
            import requests
        except ImportError:
            return False, "module Python 'requests' absent de cette installation (pip install requests)"
        try:
            requests.get(f'{self.url}/models', timeout=timeout).raise_for_status()
            return True, ''
        except Exception as e:
            return False, f"{self.url} : {type(e).__name__}"

    def check(self, timeout=5):
        """Vérifie (sans jamais lever) que le serveur répond et qu'un embedding
        de test fonctionne. Retourne (ok, [lignes]). Un modèle absent de la
        liste n'est qu'un avertissement: Lemonade peut le charger à la demande,
        c'est l'embedding de test qui tranche."""
        import requests
        lines = []
        try:
            r = requests.get(f'{self.url}/models', timeout=timeout)
            r.raise_for_status()
            ids = [m.get('id', '') for m in r.json().get('data', [])]
            lines.append(f"Serveur joignable ({len(ids)} modèle(s) listé(s))")
            if self.model in ids:
                lines.append(f"Modèle '{self.model}' présent")
            else:
                lines.append(
                    f"Modèle '{self.model}' absent de la liste du serveur "
                    f"(listés: {', '.join(ids[:8]) or 'aucun'}) — "
                    "à télécharger côté Lemonade; embeddings: modèles llamacpp/flm seulement")
        except Exception as e:
            return False, [f"Serveur INJOIGNABLE: {type(e).__name__}: {str(e)[:120]}"]
        try:
            vec = self.embed(['test'])
            lines.append(f"Embedding de test OK (dimension {vec.shape[1]})")
        except Exception as e:
            lines.append(f"Embedding de test ÉCHOUÉ: {type(e).__name__}: {str(e)[:200]}")
            return False, lines
        return True, lines

    def _embed_batch(self, batch):
        resp = self._http().post(f'{self.url}/embeddings',
                                 json={'model': self.model, 'input': batch,
                                       'encoding_format': 'float'},
                                 timeout=self.timeout)
        resp.raise_for_status()
        data = sorted(resp.json()['data'], key=lambda d: d.get('index', 0))
        if len(data) != len(batch):
            raise ValueError(f"Lemonade a renvoyé {len(data)} vecteurs pour {len(batch)} textes")
        return [d['embedding'] for d in data]


class SentenceTransformerEmbedder:
    """Embeddings locaux via sentence-transformers.
    Ex: 'intfloat/multilingual-e5-base' (préfixes 'query: ' / 'passage: ')."""

    def __init__(self, model='intfloat/multilingual-e5-base', batch_size=32,
                 query_prefix=None, doc_prefix=None):
        self.model = model
        dq, dd = default_prefixes(model)
        query_prefix = dq if query_prefix is None else query_prefix
        doc_prefix = dd if doc_prefix is None else doc_prefix
        self.batch_size = batch_size
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
        self.name = f'st:{model}'
        self._st = None
        self._lock = threading.Lock()

    def describe(self):
        return [
            f"Modèle local sentence-transformers : {self.model}",
            f"Batch          : {self.batch_size} textes",
            f"Préfixes       : requête={self.query_prefix!r}, document={self.doc_prefix!r}",
        ]

    def embed(self, texts, kind='doc'):
        with self._lock:
            if self._st is None:
                from sentence_transformers import SentenceTransformer
                self._st = SentenceTransformer(self.model)
        prefix = self.query_prefix if kind == 'query' else self.doc_prefix
        vecs = self._st.encode([prefix + t for t in texts],
                               batch_size=self.batch_size,
                               normalize_embeddings=True)
        return _normalize(vecs)


def make_embedder(spec, url=None, lemonade_url=None, batch_size=None, workers=None,
                  keep_alive=None):
    """'ollama:bge-m3[@url]', 'lemonade:nomic-embed-text-v1-GGUF[@url]' ou
    'st:intfloat/multilingual-e5-base' -> embedder. `url` (osint_ollama_url) et
    `lemonade_url` (osint_lemonade_url) servent si la valeur ne contient pas
    déjà '@url'. `batch_size` (osint_xapian_embed_batch) et `workers`
    (osint_xapian_embed_workers) règlent la taille des lots et le nombre de requêtes
    parallèles (None = défauts, cf. DEFAULT_EMBED_BATCH/WORKERS; `workers`
    est sans effet pour 'st:', local). `keep_alive` (osint_ollama_keep_alive)
    n'a d'effet que pour Ollama."""
    kind, _, model = spec.partition(':')
    http_opts = {'batch_size': batch_size, 'workers': workers}
    if kind == 'lemonade':
        model, _, spec_url = model.partition('@')
        if spec_url:
            return LemonadeEmbedder(model or 'nomic-embed-text-v1-GGUF', url=spec_url,
                                    url_source="valeur de osint_xapian_embedder (après '@')",
                                    **http_opts)
        return LemonadeEmbedder(model or 'nomic-embed-text-v1-GGUF', url=lemonade_url or None,
                                url_source='osint_lemonade_url (conf.py)', **http_opts)
    if kind == 'ollama':
        # 'ollama:bge-m3' ou 'ollama:bge-m3@http://192.168.1.10:11434'
        model, _, spec_url = model.partition('@')
        if spec_url:
            return OllamaEmbedder(model or 'bge-m3', url=spec_url,
                                  url_source="valeur de osint_xapian_embedder (après '@')",
                                  keep_alive=keep_alive, **http_opts)
        return OllamaEmbedder(model or 'bge-m3', url=url or None,
                              url_source='osint_ollama_url (conf.py)',
                              keep_alive=keep_alive, **http_opts)
    if kind == 'st':
        return SentenceTransformerEmbedder(model or 'intfloat/multilingual-e5-base',
                                           **({'batch_size': batch_size} if batch_size else {}))
    raise ValueError(f"Unknown embedder spec: {spec!r} (attendu: 'ollama:<modèle>', "
                     "'lemonade:<modèle>' ou 'st:<modèle>')")


# --------------------------------------------------------------------------
# Fusion
# --------------------------------------------------------------------------
def rrf_fuse(rankings, weights=None, k=60):
    """Reciprocal Rank Fusion. `rankings`: listes d'ids triées du meilleur au
    moins bon. Retourne [(id, score)] trié par score décroissant."""
    weights = weights or [1.0] * len(rankings)
    scores = {}
    for ranking, w in zip(rankings, weights):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + w / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


# --------------------------------------------------------------------------
# Index sémantique
# --------------------------------------------------------------------------
class SemanticIndex:
    def __init__(self, embedder, max_chars=1200, max_chunks=12, group_size=128):
        self.embedder = embedder
        self.max_chars = max_chars
        self.max_chunks = max_chunks
        self.group_size = group_size
        self._lock = threading.Lock()
        self._generation = None
        self._status_cache = (0.0, None)   # (horodatage, (ok, raison))
        self._docids = None      # (n_vecteurs,) docid de chaque ligne
        self._matrix = None      # (n_vecteurs, dim) float16

    def report(self, progress_callback=print, check=True):
        """Affiche la configuration de l'embedder et vérifie sa disponibilité.
        N'interrompt jamais l'indexation: un problème est signalé seulement."""
        progress_callback("✓ Recherche sémantique activée")
        for line in self.embedder.describe():
            progress_callback(f"    {line}")
        progress_callback(
            f"    Découpage      : chunks de {self.max_chars} caractères, {self.max_chunks} max par document")
        if check and hasattr(self.embedder, 'check'):
            ok, lines = self.embedder.check()
            for line in lines:
                progress_callback(f"    {line}")
            if not ok:
                progress_callback(
                    "✗ Embedder indisponible: l'indexation lexicale se poursuit, "
                    "les vecteurs seront (re)calculés au prochain passage réussi")
        return None

    # ---- indexation ------------------------------------------------------
    def _text_for(self, doc, slot_title, slot_desc, slot_content):
        def val(slot):
            v = doc.get_value(slot)
            return v.decode('utf-8') if v else ''
        parts = [val(slot_title), val(slot_desc), val(slot_content)]
        return ' '.join(p for p in parts if p)

    def _emb_hash(self, text):
        h = hashlib.blake2b(digest_size=16)
        h.update(self.embedder.name.encode('utf-8'))
        h.update(b'\x1f')
        h.update(f'{self.max_chars}/{self.max_chunks}'.encode('utf-8'))
        h.update(b'\x1f')
        doc_prefix = getattr(self.embedder, 'doc_prefix', '')
        if doc_prefix:   # hash inchangé (pas de recalcul) quand il n'y en a pas
            h.update(doc_prefix.encode('utf-8'))
            h.update(b'\x1f')
        h.update(text.encode('utf-8'))
        return h.hexdigest()

    def index_embeddings(self, db, slot_title, slot_desc, slot_content,
                         progress_callback=print):
        """Calcule/rafraîchit les vecteurs des documents dont le texte ou le
        modèle a changé. À appeler sur une WritableDatabase, avant commit().
        Retourne le nombre de documents (ré)embeddés."""
        stored_model = self._meta(db, META_MODEL)
        if stored_model and stored_model != self.embedder.name:
            progress_callback(
                f"  modèle d'embedding changé ({stored_model} -> {self.embedder.name}): "
                "tous les vecteurs sont recalculés")
        done = 0
        pending = []   # (docid, doc, chunks, emb_hash)
        dim = None

        def flush():
            nonlocal done, dim
            if not pending:
                return
            flat = [c for _, _, chunks, _ in pending for c in chunks]
            vecs = self.embedder.embed(flat, kind='doc') if flat else np.empty((0, 0))
            pos = 0
            for docid, doc, chunks, emb_hash in pending:
                n = len(chunks)
                if n:
                    block = vecs[pos:pos + n]
                    dim = block.shape[1]
                    doc.add_value(SLOT_EMBED, pack_vectors(block))
                else:
                    doc.add_value(SLOT_EMBED, b'')
                pos += n
                doc.add_value(SLOT_EMBHASH, emb_hash)
                db.replace_document(docid, doc)
                done += 1
            pending.clear()

        total = db.get_doccount()
        seen = 0
        for posting in db.postlist(''):
            docid = posting.docid
            doc = db.get_document(docid)
            seen += 1
            text = self._text_for(doc, slot_title, slot_desc, slot_content)
            emb_hash = self._emb_hash(text)
            stored = doc.get_value(SLOT_EMBHASH)
            if stored and stored.decode('utf-8') == emb_hash:
                continue
            chunks = chunk_text(text, self.max_chars, overlap=150,
                                max_chunks=self.max_chunks)
            pending.append((docid, doc, chunks, emb_hash))
            if len(pending) >= self.group_size:
                flush()
                progress_callback(f"  embeddings: {done} updated ({seen}/{total} scanned)")
        flush()

        if done:
            if dim:
                db.set_metadata(META_DIM, str(dim))
            db.set_metadata(META_MODEL, self.embedder.name)
            db.set_metadata(META_GENERATION, uuid.uuid4().hex)
        return done

    # ---- recherche ---------------------------------------------------------
    @staticmethod
    def _meta(db, key):
        v = db.get_metadata(key)
        return v.decode('utf-8') if isinstance(v, bytes) else (v or '')

    def available(self, db):
        """True si la base contient des vecteurs produits par CE modèle."""
        return (self._meta(db, META_MODEL) == self.embedder.name
                and int(self._meta(db, META_DIM) or 0) > 0)

    def status(self, db, ttl=30):
        """(ok, raison) — la recherche sémantique est-elle utilisable
        MAINTENANT? Vérifie que l'index contient des vecteurs produits par ce
        modèle et que l'embedder répond (ping léger, mis en cache `ttl`
        secondes pour ne pas ralentir chaque affichage de la page).
        `raison` est vide si ok, sinon une explication affichable."""
        now = time.monotonic()
        ts, cached = self._status_cache
        if cached is not None and now - ts < ttl:
            return cached
        if not self.available(db):
            stored = self._meta(db, META_MODEL)
            if not stored:
                result = (False, "l'index ne contient pas encore de vecteurs (relancer l'indexation)")
            else:
                result = (False, f"l'index a été vectorisé avec un autre modèle ({stored}), "
                                 f"relancer l'indexation avec {self.embedder.name}")
        else:
            result = (True, '')
            if hasattr(self.embedder, 'ping'):
                ok, detail = self.embedder.ping()
                if not ok:
                    result = (False, f"serveur d'embeddings injoignable ({detail})")
        self._status_cache = (now, result)
        return result

    def _ensure_loaded(self, db):
        gen = self._meta(db, META_GENERATION)
        with self._lock:
            if self._matrix is not None and self._generation == gen:
                return
            dim = int(self._meta(db, META_DIM) or 0)
            docids, blocks = [], []
            for item in db.valuestream(SLOT_EMBED):
                blob = item.value
                if not blob:
                    continue
                block = unpack_vectors(blob, dim)
                if len(block):
                    blocks.append(block)
                    docids.extend([item.docid] * len(block))
            if blocks:
                self._matrix = np.concatenate(blocks, axis=0)
                self._docids = np.asarray(docids, dtype=np.int64)
            else:
                self._matrix = np.empty((0, max(dim, 1)), dtype=np.float16)
                self._docids = np.empty((0,), dtype=np.int64)
            self._generation = gen
            logger.info("Semantic index loaded: %d vectors, dim %d",
                        len(self._docids), dim)

    def search(self, db, query, k=200, allowed_docids=None, min_score=0.0):
        """Retourne [(docid, cosinus)] trié par score décroissant, un seul
        résultat par document (meilleur chunk). `allowed_docids`: ensemble de
        docids autorisés (filtres cats/types/countries), ou None."""
        if not self.available(db):
            return []
        self._ensure_loaded(db)
        matrix, docids = self._matrix, self._docids
        if matrix is None or not len(docids):
            return []
        q = self.embedder.embed([query], kind='query')[0].astype(np.float32)

        if allowed_docids is not None:
            mask = np.isin(docids, np.fromiter(allowed_docids, dtype=np.int64))
            idx = np.nonzero(mask)[0]
            if not len(idx):
                return []
        else:
            idx = None

        # produit scalaire par blocs: évite de convertir toute la matrice
        # float16 en float32 d'un coup
        sims = np.empty(len(docids) if idx is None else len(idx), dtype=np.float32)
        step = 20000
        n = len(sims)
        for start in range(0, n, step):
            if idx is None:
                part = matrix[start:start + step]
            else:
                part = matrix[idx[start:start + step]]
            sims[start:start + step] = part.astype(np.float32) @ q
        ids = docids if idx is None else docids[idx]

        best = {}
        top = np.argsort(-sims)[:k * 4]   # marge pour le max-pooling par doc
        for i in top:
            s = float(sims[i])
            if s < min_score:
                break
            d = int(ids[i])
            if d not in best:
                best[d] = s
                if len(best) >= k:
                    break
        return list(best.items())
