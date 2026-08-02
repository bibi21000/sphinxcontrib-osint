# -*- encoding: utf-8 -*-
"""
PeerRegistry -- ce que ce serveur sait du mesh
-------------------------------------------------

Mesh à plat, un saut : ce serveur connaît directement chacun de ses pairs
(pas de relais/gossip, pas de TTL, pas de dédoublonnage de requêtes
transitives -- inutile tant que le mesh reste de taille modeste et piloté
par un bootstrap JSON plutôt que par une découverte P2P ouverte).

Trois responsabilités :
  1. charger la liste de pairs de départ depuis un fichier bootstrap JSON ;
  2. maintenir en mémoire les mots-clés que CE serveur publie (extraits de
     son propre index Xapian, avec cache) ;
  3. aller chercher, en HTTP, les infos/mots-clés/pairs de chaque pair
     connu -- et apprendre au passage l'existence de nouveaux pairs via
     ce que chaque pair rapporte de son propre carnet d'adresses (un léger
     auto-complètement, pas un vrai gossip).
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import time

import requests

from .aggregation import aggregate_results
from .keywords import extract_canonical_labels, extract_top_terms

logger = logging.getLogger(__name__)

#: en-tête HTTP utilisé pour authentifier les appels entre pairs (secret
#: partagé -- volontairement simple pour un premier jet ; un schéma par
#: pair avec sa propre clé est une amélioration possible plus tard).
MESH_TOKEN_HEADER = 'X-Mesh-Token'


class PeerRegistry:
    """État mesh d'un serveur : qui il est, qui il connaît, ce qu'il publie."""

    #: langue pivot du mesh : toutes les listes de mots-clés échangées
    #: entre pairs sont dans cette langue, quelle que soit la langue de
    #: l'index Xapian local de chaque serveur -- même principe que pour
    #: les requêtes de recherche (cf. discussion initiale).
    PIVOT_LANG = 'en'

    def __init__(self, self_id, self_url, lang=None, xapian_dir=None,
                 keywords_limit=300, keywords_min_length=3, secret='',
                 timeout=5, keywords_ttl=3600, session=None,
                 translate_keywords=True, translate_fn=None,
                 translation_memory=None, entities_limit=500,
                 local_search_fn=None):
        if not self_id:
            raise ValueError('osint_mesh_peer_id doit être configuré pour activer le mesh')

        self.self_id = self_id
        self.self_url = (self_url or '').rstrip('/')
        self.lang = lang
        self.xapian_dir = xapian_dir
        self.keywords_limit = keywords_limit
        self.keywords_min_length = keywords_min_length
        self.entities_limit = entities_limit
        self.secret = secret or ''
        self.timeout = timeout
        self.keywords_ttl = keywords_ttl
        self.session = session or requests.Session()
        #: si True (défaut), les termes extraits en langue locale sont
        #: traduits vers PIVOT_LANG avant d'être mis en cache/publiés.
        #: `translate_fn` est injectable (signature: (text, dest, src_lang)
        #: -> (ok: bool, translated_text: str)) -- pour les tests, et pour
        #: pouvoir brancher un autre moteur que celui du plugin `text`
        #: sans dépendance dure dessus dans ce module.
        self.translate_keywords = translate_keywords
        self.translate_fn = translate_fn or self._default_translate_fn
        #: TranslationMemory optionnelle -- si absente, on retraduit tout
        #: à chaque cycle (comportement précédent, toujours valide pour
        #: les tests ou un usage sans persistance).
        self.translation_memory = translation_memory
        #: fonction de recherche locale injectable (signature: (query,
        #: limit) -> list[dict]) -- si absente, utilise l'implémentation
        #: Xapian réelle (`_xapian_local_search`). Comme `translate_fn`,
        #: ça permet de tester tout le fan-out mesh_search()/aggregation
        #: sans base Xapian réelle.
        self.local_search_fn = local_search_fn

        self._lock = threading.Lock()
        #: peer_id -> {'url', 'lang', 'keywords': set(), 'keywords_at',
        #:              'entities': set(), 'entities_at', 'source'}
        self._peers = {}
        #: (keywords_list, generated_at) | None -- vocabulaire traduit
        self._local_keywords_cache = None
        #: (entities_list, generated_at) | None -- libellés canoniques,
        #: volontairement non traduits (cf. local_entities)
        self._local_entities_cache = None

    @staticmethod
    def _default_translate_fn(text, dest, src_lang):
        """Traducteur par défaut : réutilise le plugin `text` déjà présent
        dans le projet (import différé -- ce module n'a pas besoin du
        paquet `translators` tant que la traduction des mots-clés n'est
        pas réellement utilisée, ex: PIVOT_LANG == lang local).
        """
        from ..plugins.text import Text
        ok, translated, _src_lang = Text.translate(text, dest=dest, src_lang=src_lang)
        return ok, translated

    # -- bootstrap / carnet d'adresses ----------------------------------

    def load_bootstrap(self, path):
        """Charge la liste de pairs de départ.

        Format attendu (voir bootstrap.example.json) ::

            {"peers": [{"id": "osint-fr", "url": "https://...", "lang": "fr"}]}
        """
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        for entry in data.get('peers', []):
            self.add_peer(entry['id'], entry['url'], entry.get('lang'), source='bootstrap')

    def add_peer(self, peer_id, url, lang=None, source='peer'):
        """Ajoute ou met à jour un pair. Ne touche jamais aux mots-clés déjà
        en cache pour ce pair (seul sync_peer les rafraîchit) : ça évite
        qu'un ré-appel de load_bootstrap ou un merge de peers-of-peers
        efface un cache encore valide.
        """
        if peer_id == self.self_id:
            return
        url = (url or '').rstrip('/')
        with self._lock:
            existing = self._peers.get(peer_id)
            if existing is not None:
                existing['url'] = url
                if lang is not None:
                    existing['lang'] = lang
                return
            self._peers[peer_id] = {
                'url': url, 'lang': lang, 'keywords': set(), 'keywords_at': None,
                'entities': set(), 'entities_at': None, 'source': source,
            }

    def known_peers(self):
        """Copie du carnet d'adresses (sûre à itérer hors du lock)."""
        with self._lock:
            return {
                pid: dict(info, keywords=set(info['keywords']), entities=set(info.get('entities', set())))
                for pid, info in self._peers.items()
            }

    def known_peers_public(self):
        """Ce qu'on expose sur notre propre /mesh/v1/peers : juste de quoi
        qu'un pair puisse nous ajouter à son carnet (id/url/lang) -- pas
        les mots-clés, chaque serveur restant la source de vérité de son
        propre vocabulaire (récupérable via /mesh/v1/keywords).
        """
        peers = [
            {'id': pid, 'url': info['url'], 'lang': info['lang']}
            for pid, info in self.known_peers().items()
        ]
        peers.append({'id': self.self_id, 'url': self.self_url, 'lang': self.lang})
        return peers

    # -- mots-clés publiés par CE serveur --------------------------------

    def local_keywords(self, force=False):
        """(keywords_list, generated_at) pour ce serveur, avec cache de
        `keywords_ttl` secondes -- l'extraction est bon marché (un seul
        passage sur allterms()) mais pas la peine de la refaire à chaque
        requête entrante sur /mesh/v1/keywords.
        """
        with self._lock:
            cached = self._local_keywords_cache

        if not force and cached is not None and (time.time() - cached[1]) < self.keywords_ttl:
            return cached

        if not self.xapian_dir:
            result = ([], time.time())
        else:
            try:
                terms = extract_top_terms(
                    self.xapian_dir,
                    limit=self.keywords_limit,
                    min_length=self.keywords_min_length,
                )
                if self.translate_keywords and self.lang and self.lang != self.PIVOT_LANG:
                    terms = self._translate_terms(terms)
                result = (terms, time.time())
            except Exception:
                logger.exception('Extraction des mots-clés mesh depuis %s en échec', self.xapian_dir)
                # on garde l'ancien cache plutôt que de publier une liste
                # vide suite à un pépin ponctuel (base momentanément verrouillée...)
                result = (list(cached[0]), time.time()) if cached else ([], time.time())

        with self._lock:
            self._local_keywords_cache = result
        return result

    def _translate_terms(self, terms):
        """Traduit une liste de termes en langue locale vers PIVOT_LANG, en
        consultant d'abord la mémoire de traduction (si configurée) : seuls
        les termes jamais vus partent réellement vers le traducteur.

        Un mot par ligne plutôt qu'un appel par mot pour les termes
        manquants : ça reste UN appel de traduction par cycle pour tout ce
        qui est nouveau (donc pas 300 requêtes vers un service externe à
        chaque sync), au prix d'une hypothèse -- que le moteur de
        traduction préserve le nombre de lignes. On vérifie cette
        hypothèse après coup et, si elle est fausse, on renonce à traduire
        ce lot de termes manquants plutôt que de désynchroniser
        silencieusement mot/traduction (ils restent en langue locale pour
        ce cycle ; les termes déjà en cache, eux, restent traduits).
        """
        if not terms:
            return terms

        translated_by_term = {}
        missing = []
        for term in terms:
            cached = self.translation_memory.get(self.lang, term) if self.translation_memory else None
            if cached is not None:
                translated_by_term[term] = cached
            else:
                missing.append(term)

        if missing:
            try:
                ok, translated_blob = self.translate_fn('\n'.join(missing), self.PIVOT_LANG, self.lang)
            except Exception:
                logger.exception(
                    'Traduction des mots-clés mesh en échec pour %d terme(s), publication en langue locale (%s)',
                    len(missing), self.lang,
                )
                ok = False

            if ok:
                translated = [t.strip().lower() for t in translated_blob.split('\n') if t.strip()]
                if len(translated) == len(missing):
                    fresh = dict(zip(missing, translated))
                    translated_by_term.update(fresh)
                    if self.translation_memory:
                        self.translation_memory.update(self.lang, fresh)
                else:
                    logger.warning(
                        'Traduction des mots-clés mesh: nombre de lignes différent '
                        '(%d termes -> %d lignes traduites), ces %d terme(s) restent en langue locale',
                        len(missing), len(translated), len(missing),
                    )

        # un terme resté sans traduction (échec, mismatch...) est publié
        # tel quel plutôt que d'être perdu -- un pair peut toujours
        # traduire lui-même côté requête.
        return [translated_by_term.get(term, term) for term in terms]

    def set_local_keywords(self, keywords, generated_at=None):
        """Fixe manuellement les mots-clés publiés, en court-circuitant
        l'extraction Xapian -- utile pour un serveur qui préfère publier
        sa taxonomie cats/countries déjà structurée plutôt que (ou en plus
        de) la fréquence brute des termes, ou pour les tests.
        """
        with self._lock:
            self._local_keywords_cache = (list(keywords), generated_at or time.time())

    def local_entities(self, force=False):
        """(entities_list, generated_at) : libellés canoniques (titres +
        altlabels) des entités de l'index local -- cf. docstring de
        `extract_canonical_labels` pour pourquoi ils ne sont PAS traduits
        ici, contrairement à `local_keywords()`. Même politique de cache
        (`keywords_ttl`) que pour les mots-clés.
        """
        with self._lock:
            cached = self._local_entities_cache

        if not force and cached is not None and (time.time() - cached[1]) < self.keywords_ttl:
            return cached

        if not self.xapian_dir:
            result = ([], time.time())
        else:
            try:
                labels = extract_canonical_labels(self.xapian_dir, limit=self.entities_limit)
                result = (labels, time.time())
            except Exception:
                logger.exception('Extraction des entités mesh depuis %s en échec', self.xapian_dir)
                result = (list(cached[0]), time.time()) if cached else ([], time.time())

        with self._lock:
            self._local_entities_cache = result
        return result

    def set_local_entities(self, entities, generated_at=None):
        """Équivalent de `set_local_keywords` pour les libellés canoniques
        -- override manuel ou tests.
        """
        with self._lock:
            self._local_entities_cache = (list(entities), generated_at or time.time())

    # -- synchronisation avec les pairs -----------------------------------

    def _headers(self):
        headers = {}
        if self.secret:
            headers[MESH_TOKEN_HEADER] = self.secret
        return headers

    def sync_peer(self, peer_id):
        """Va chercher /info, /keywords et /peers chez un pair connu et
        met à jour notre vue locale de ce pair.

        Ne lève jamais d'exception réseau : un pair injoignable est loggé
        et compté en échec, mais ne doit pas interrompre la synchro des
        autres (cf. sync_all). Retourne True/False.
        """
        with self._lock:
            peer = self._peers.get(peer_id)
        if peer is None:
            logger.warning('sync_peer appelé pour un pair inconnu: %s', peer_id)
            return False

        base = peer['url']
        try:
            r_info = self.session.get(f'{base}/mesh/v1/info', headers=self._headers(), timeout=self.timeout)
            r_info.raise_for_status()
            info = r_info.json()

            r_kws = self.session.get(f'{base}/mesh/v1/keywords', headers=self._headers(), timeout=self.timeout)
            r_kws.raise_for_status()
            kws = r_kws.json()

            r_others = self.session.get(f'{base}/mesh/v1/peers', headers=self._headers(), timeout=self.timeout)
            r_others.raise_for_status()
            others = r_others.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Synchro mesh avec %s (%s) en échec: %s', peer_id, base, exc)
            return False

        with self._lock:
            peer['lang'] = info.get('lang', peer['lang'])
            peer['keywords'] = set(kws.get('keywords', []))
            peer['keywords_at'] = kws.get('generated_at')
            # les entités publiées ne sont pas forcément déjà en
            # minuscules (elles gardent leur casse d'origine, cf.
            # extract_canonical_labels) -- on normalise à la lecture
            # côté pair pour un matching insensible à la casse plus tard.
            peer['entities'] = {e.lower() for e in kws.get('entities', [])}
            peer['entities_at'] = kws.get('entities_generated_at')

        for entry in others.get('peers', []):
            entry_id = entry.get('id')
            if entry_id and entry_id != self.self_id:
                self.add_peer(entry_id, entry.get('url'), entry.get('lang'), source='peer')

        return True

    def sync_all(self):
        """Synchronise tous les pairs connus, un par un.

        Returns:
            {peer_id: True|False} -- pour que l'appelant (une commande CLI
            ou une tâche planifiée) puisse voir/logger ce qui a échoué.
        """
        results = {}
        for peer_id in list(self.known_peers().keys()):
            results[peer_id] = self.sync_peer(peer_id)
        return results

    # -- recherche locale ---------------------------------------------------

    def local_search(self, query, limit=10, translate_results=True):
        """Recherche dans l'index local. `query` est en anglais (pivot du
        mesh) -- traduite vers la langue locale avant la recherche
        Xapian, puis les titres des résultats sont retraduits vers
        l'anglais avant d'être retournés (sauf si `translate_results`
        est False, utile en debug pour voir le résultat brut).

        Utilise `local_search_fn` si injecté au constructeur (tests),
        sinon l'implémentation Xapian réelle.
        """
        if self.local_search_fn is not None:
            return self.local_search_fn(query, limit)
        return self._xapian_local_search(query, limit=limit, translate_results=translate_results)

    def _stemmer_language_name(self):
        """Nom complet du stemmer Xapian (ex: "french") à partir du code
        ISO stocké dans `self.lang` (ex: "fr") -- même correspondance que
        celle déjà utilisée pour l'indexation (cf. flask.py: init_xapian).
        None si `self.lang` n'est pas configuré ou pas reconnu -- l'appelant
        (XapianIndexer) retombe alors sur l'anglais par défaut.
        """
        if not self.lang:
            return None
        try:
            import pycountry
            entry = pycountry.languages.get(alpha_2=self.lang)
            return entry.name if entry else None
        except Exception:
            logger.exception('Résolution de la langue du stemmer mesh en échec pour %r', self.lang)
            return None

    def _xapian_local_search(self, query, limit=10, translate_results=True):
        if not self.xapian_dir:
            return []

        local_query = query
        if self.lang and self.lang != self.PIVOT_LANG:
            try:
                ok, translated = self.translate_fn(query, self.lang, self.PIVOT_LANG)
            except Exception:
                logger.exception('Traduction de la requête mesh en échec, recherche avec la requête originale')
                ok, translated = False, query
            if ok and translated and translated.strip():
                local_query = translated

        from ..xapianlib import XapianIndexer  # import différé, cf. keywords.py
        indexer = XapianIndexer(self.xapian_dir, language=self._stemmer_language_name())
        try:
            raw_results = indexer.search(local_query, limit=limit)
        except Exception:
            logger.exception('Recherche mesh locale en échec pour la requête %r', local_query)
            return []

        results = [
            {
                'title': r.get('title', ''),
                'description': r.get('description', ''),
                'url': r.get('url', ''),
                'type': r.get('type', ''),
                'country': r.get('country', ''),
                'score': r.get('score', 0),
            }
            for r in raw_results
        ]

        if translate_results and self.lang and self.lang != self.PIVOT_LANG:
            results = self._translate_result_titles(results)

        return results

    def _translate_result_titles(self, results):
        """Traduit les titres des résultats (langue locale -> PIVOT_LANG),
        un appel groupé plutôt qu'un par résultat -- même logique que
        `_translate_terms`, sans mémoire de traduction cette fois (les
        titres de résultats, contrairement aux mots-clés, ne sont pas les
        mêmes chaînes récurrentes d'une requête à l'autre : le cache
        n'apporterait pas grand-chose ici).
        """
        titles = [r['title'] for r in results if r.get('title')]
        if not titles:
            return results
        try:
            ok, blob = self.translate_fn('\n'.join(titles), self.PIVOT_LANG, self.lang)
        except Exception:
            logger.exception('Traduction des titres de résultats mesh en échec, titres en langue locale')
            return results
        if not ok:
            return results
        translated_titles = blob.split('\n')
        if len(translated_titles) != len(titles):
            logger.warning(
                'Traduction des titres de résultats mesh: nombre de lignes différent '
                '(%d titres -> %d lignes traduites), titres en langue locale',
                len(titles), len(translated_titles),
            )
            return results
        translated_iter = iter(translated_titles)
        return [
            dict(r, title=next(translated_iter)) if r.get('title') else r
            for r in results
        ]

    # -- recherche à travers le mesh -----------------------------------------

    def _select_peers_for_query(self, query):
        """Pairs à interroger pour une recherche rapide : ceux dont les
        mots-clés OU entités publiés recoupent au moins un mot de la
        requête. Les entités multi-mots ("volodymyr zelensky") sont
        éclatées en mots individuels pour ce matching -- un simple filtre
        de routage, volontairement approximatif (cf. discussion initiale
        sur les faux positifs acceptables en fast search).
        """
        words = {w.lower() for w in query.split() if w.strip()}
        if not words:
            return []
        selected = []
        for peer_id, info in self.known_peers().items():
            vocabulary = set(info.get('keywords', set()))
            for entity in info.get('entities', set()):
                vocabulary.update(entity.split())
            if words & vocabulary:
                selected.append(peer_id)
        return selected

    def _search_peer(self, peer_id, query, limit):
        with self._lock:
            peer = self._peers.get(peer_id)
        if peer is None:
            return []
        base = peer['url']
        try:
            resp = self.session.post(
                f'{base}/mesh/v1/search',
                json={'q': query, 'limit': limit},
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Recherche mesh chez %s (%s) en échec: %s', peer_id, base, exc)
            return []
        return [self._sanitize_remote_result(r) for r in payload.get('results', [])]

    @staticmethod
    def _sanitize_remote_result(result):
        """Un résultat vient d'un AUTRE serveur -- avant d'atterrir dans un
        template HTML (ex: /searchmesh.html), on ne fait pas confiance à
        `url` telle quelle : un pair malveillant ou compromis pourrait y
        glisser un `javascript:...` ou autre schéma dangereux. On ne garde
        `url` que si elle commence par http:// ou https://, sinon on la
        vide plutôt que de la laisser passer telle quelle.

        Ne touche pas au reste (`title`, `description`...) -- ces champs
        doivent être échappés à l'affichage (côté template), pas ici :
        ce n'est pas à cette couche de décider du contexte de rendu.
        """
        url = result.get('url', '')
        if url and not (url.startswith('http://') or url.startswith('https://')):
            result = dict(result, url='')
        return result

    def mesh_search(self, query, mode='fast', limit_per_peer=10,
                     total_limit=None, aggregation_method='minmax', max_workers=None):
        """Recherche à travers le mesh.

        `mode`:
          - 'fast' (défaut) : interroge seulement les pairs dont les
            mots-clés/entités publiés recoupent la requête (+ toujours
            soi-même en local).
          - 'deep' : interroge tous les pairs connus.

        Tous les pairs sélectionnés (soi-même compris) sont interrogés EN
        PARALLÈLE via un pool de threads, pas les uns après les autres :
        le temps de réponse total est donc borné par le pair le plus
        lent, pas par la somme de tous -- important dès qu'on branche ça
        sur une recherche interactive, où le nombre de pairs en mode
        'deep' peut être significatif. `local_search()` (traduction +
        recherche Xapian) tourne dans ce même pool, pas séparément avant
        -- une recherche locale lente ne retarde plus le lancement des
        appels aux pairs.

        Chaque pair est interrogé indépendamment -- pas de relais/gossip,
        cohérent avec le mesh à un saut (cf. registry.py). Un pair
        injoignable, en erreur, ou dont la recherche locale lève une
        exception inattendue est simplement absent du résultat final,
        jamais une exception qui ferait échouer toute la recherche (même
        politique de tolérance aux pannes que sync_peer/sync_all).

        `max_workers` : taille du pool de threads (défaut : une taille
        raisonnable en fonction du nombre de pairs interrogés, plafonnée
        pour éviter d'ouvrir un nombre de threads déraisonnable si le
        mesh devient très grand).

        Returns:
            Liste de résultats fusionnée et triée (cf. aggregate_results),
            chacun annoté de `peer_id`.
        """
        if mode not in ('fast', 'deep'):
            raise ValueError(f"mode inconnu: {mode!r} (attendu: 'fast' ou 'deep')")

        target_peer_ids = (
            self._select_peers_for_query(query) if mode == 'fast'
            else list(self.known_peers().keys())
        )

        # dict plutôt que liste : garantit un seul job par peer_id (et par
        # soi-même), même si _select_peers_for_query renvoyait un jour un
        # doublon.
        jobs = {self.self_id: lambda: self.local_search(query, limit=limit_per_peer)}
        for peer_id in target_peer_ids:
            jobs[peer_id] = lambda peer_id=peer_id: self._search_peer(peer_id, query, limit_per_peer)

        results_by_peer = {}
        pool_size = max_workers or min(32, max(1, len(jobs)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as executor:
            future_to_peer = {executor.submit(job): peer_id for peer_id, job in jobs.items()}
            for future in concurrent.futures.as_completed(future_to_peer):
                peer_id = future_to_peer[future]
                try:
                    results = future.result()
                except Exception:
                    # filet de sécurité : local_search()/_search_peer() ne
                    # sont pas censés lever (elles capturent déjà leurs
                    # erreurs respectives), mais un pair de moins ne doit
                    # jamais faire échouer toute la recherche.
                    logger.exception('Recherche mesh chez %s a levé une exception inattendue', peer_id)
                    results = []
                if results:
                    results_by_peer[peer_id] = results

        return aggregate_results(results_by_peer, method=aggregation_method, limit=total_limit)
