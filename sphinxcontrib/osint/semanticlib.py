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
import threading
import time
import uuid

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
class OllamaEmbedder:
    """Embeddings via Ollama (/api/embed). Ex: modèle 'bge-m3'."""

    def __init__(self, model='bge-m3', url=None,
                 batch_size=16, timeout=300, query_prefix='', doc_prefix=''):
        self.model = model
        # URL du serveur: argument, sinon OSINT_OLLAMA_URL, sinon OLLAMA_HOST,
        # sinon localhost. Accepte 'host:port' sans schéma.
        if url:
            self.url_source = 'spécifiée dans la valeur de l\'embedder'
        elif os.environ.get('OSINT_OLLAMA_URL'):
            url = os.environ['OSINT_OLLAMA_URL']
            self.url_source = 'variable OSINT_OLLAMA_URL'
        elif os.environ.get('OLLAMA_HOST'):
            url = os.environ['OLLAMA_HOST']
            self.url_source = 'variable OLLAMA_HOST'
        else:
            url = 'http://127.0.0.1:11434'
            self.url_source = 'valeur par défaut'
        if '://' not in url:
            url = 'http://' + url
        self.url = url.rstrip('/')
        self.batch_size = batch_size
        self.timeout = timeout
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
        self.name = f'ollama:{model}'

    def describe(self):
        """Lignes décrivant la configuration (affichées au début de l'indexation)."""
        return [
            f"Serveur Ollama : {self.url} ({self.url_source})",
            f"Modèle         : {self.model}",
            f"Batch / timeout: {self.batch_size} textes par requête / {self.timeout}s",
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

    def embed(self, texts, kind='doc'):
        import requests
        prefix = self.query_prefix if kind == 'query' else self.doc_prefix
        out = []
        for i in range(0, len(texts), self.batch_size):
            batch = [prefix + t for t in texts[i:i + self.batch_size]]
            resp = requests.post(f'{self.url}/api/embed',
                                 json={'model': self.model, 'input': batch},
                                 timeout=self.timeout)
            resp.raise_for_status()
            out.extend(resp.json()['embeddings'])
        return _normalize(out)


class SentenceTransformerEmbedder:
    """Embeddings locaux via sentence-transformers.
    Ex: 'intfloat/multilingual-e5-base' (préfixes 'query: ' / 'passage: ')."""

    def __init__(self, model='intfloat/multilingual-e5-base', batch_size=32,
                 query_prefix='query: ', doc_prefix='passage: '):
        self.model = model
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


def make_embedder(spec):
    """'ollama:bge-m3[@url]' ou 'st:intfloat/multilingual-e5-base' -> embedder."""
    kind, _, model = spec.partition(':')
    if kind == 'ollama':
        # 'ollama:bge-m3' ou 'ollama:bge-m3@http://192.168.1.10:11434'
        model, _, url = model.partition('@')
        return OllamaEmbedder(model or 'bge-m3', url=url or None)
    if kind == 'st':
        return SentenceTransformerEmbedder(model or 'intfloat/multilingual-e5-base')
    raise ValueError(f"Unknown embedder spec: {spec!r}")


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
