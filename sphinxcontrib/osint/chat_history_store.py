# -*- encoding: utf-8 -*-
"""
Ephemeral, per-visitor chat history storage - no login required.

Two backends, same interface (get/set/delete):

- RedisHistoryStore: recommended for production / multi-worker deployments
  (gunicorn -w N>1, several app instances behind a load balancer...).
  Each key carries a TTL, refreshed on every write, so Redis itself purges
  stale conversations - no cron job or cleanup thread needed, and it's
  shared across all your workers/instances.

- MemoryHistoryStore: zero-dependency fallback for a single-process setup
  (dev server, or a single gunicorn worker). Keeps everything in a plain
  dict guarded by a lock, with a background thread periodically dropping
  expired entries. NOT safe across multiple worker processes: each process
  has its own memory, so a user could land on a worker that never saw
  their history.
"""
import json
import time
import threading
import logging

logger = logging.getLogger(__name__)


class MemoryHistoryStore:

    def __init__(self, ttl=7200, sweep_interval=300):
        self.ttl = ttl
        self._data = {}  # key -> (expires_at, history)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sweeper = threading.Thread(target=self._sweep_loop, args=(sweep_interval,), daemon=True)
        self._sweeper.start()

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return []
            expires_at, history = entry
            if expires_at < time.monotonic():
                del self._data[key]
                return []
            return history

    def set(self, key, history):
        with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, history)

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def _sweep_loop(self, interval):
        while not self._stop.wait(interval):
            now = time.monotonic()
            with self._lock:
                expired = [k for k, (exp, _) in self._data.items() if exp < now]
                for k in expired:
                    del self._data[k]
            if expired:
                logger.debug('Purged %d expired chat histor%s', len(expired), 'y' if len(expired) == 1 else 'ies')

    def close(self):
        self._stop.set()


class RedisHistoryStore:
    """Requires a `redis.Redis` client (redis-py), passed in already
    configured (host/port/db/auth is your app's business, not this one's).
    """

    def __init__(self, redis_client, ttl=7200, prefix='osint_chat_history:'):
        self.redis = redis_client
        self.ttl = ttl
        self.prefix = prefix

    def _k(self, key):
        return f'{self.prefix}{key}'

    def get(self, key):
        try:
            raw = self.redis.get(self._k(key))
        except Exception:
            # Redis hiccup: degrade to "no history" rather than a 500 -
            # a chat with amnesia is better than a chat that's down.
            logger.exception('Redis unavailable, returning empty history for %s', key)
            return []
        if raw is None:
            return []
        return json.loads(raw)

    def set(self, key, history):
        try:
            # `ex=` refreshes the TTL on every write: an active conversation
            # never expires mid-use, an abandoned one is auto-purged by
            # Redis itself `ttl` seconds after the last message - no
            # sweeping needed.
            self.redis.set(self._k(key), json.dumps(history), ex=self.ttl)
        except Exception:
            logger.exception('Redis unavailable, could not persist history for %s', key)

    def delete(self, key):
        try:
            self.redis.delete(self._k(key))
        except Exception:
            logger.exception('Redis unavailable, could not delete history for %s', key)
