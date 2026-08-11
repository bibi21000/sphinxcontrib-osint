"""
remotesync.py — Bibliothèque de synchronisation de fichiers vers un serveur distant.
Protocoles supportés : FTP, FTPS, FTP/TLS, SFTP (SSH).
Configuration via fichier INI.
"""

from __future__ import annotations

import configparser
import ftplib
import hashlib
import logging
import os
import stat
import threading
from abc import ABC, abstractmethod
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & dataclasses
# ---------------------------------------------------------------------------

class Protocol(str, Enum):
    FTP   = "ftp"
    FTPS  = "ftps"
    FTPTLS = "ftptls"
    SFTP  = "sftp"


@dataclass
class SyncConfig:
    """Paramètres lus depuis le fichier INI."""
    protocol: Protocol
    host: str
    port: int
    username: str
    password: str = ""
    ssh_key_path: str = ""
    remote_base_dir: str = "/"
    passive_mode: bool = True
    compression: bool = True       # active la compression du transport (SFTP/SSH)
    timeout: int = 30
    delete_orphans: bool = False   # supprimer les fichiers distants absents en local
    dry_run: bool = False          # simuler sans transférer
    logdir: str = ""               # répertoire de stockage des logs de session
    max_workers: int = 5           # transferts simultanés lors de sync_directory
    lock_suffix: str = ".lck"      # suffixe du fichier verrou (fetch_locked)
    lock_poll_interval: float = 2.0  # secondes entre deux sondages du verrou
    lock_timeout: float = 60.0      # secondes avant LockTimeoutError

    @classmethod
    def from_ini(cls, path: str | Path, section: str = "remotesync") -> "SyncConfig":
        cfg = configparser.ConfigParser()
        cfg.read(str(path))
        if section not in cfg:
            raise ValueError(f"Section [{section}] introuvable dans {path}")
        s = cfg[section]
        proto_str = s.get("protocol", "ftp").lower()
        try:
            protocol = Protocol(proto_str)
        except ValueError:
            raise ValueError(f"Protocole inconnu : {proto_str!r}. Valeurs acceptées : {[p.value for p in Protocol]}")

        default_ports = {Protocol.FTP: 21, Protocol.FTPS: 990,
                         Protocol.FTPTLS: 21, Protocol.SFTP: 22}
        port = int(s.get("port", default_ports[protocol]))

        return cls(
            protocol=protocol,
            host=s.get("host", ""),
            port=port,
            username=s.get("username", ""),
            password=s.get("password", ""),
            ssh_key_path=s.get("ssh_key_path", ""),
            remote_base_dir=s.get("remote_base_dir", "/"),
            passive_mode=s.getboolean("passive_mode", True),
            compression=s.getboolean("compression", True),
            timeout=int(s.get("timeout", 30)),
            delete_orphans=s.getboolean("delete_orphans", False),
            dry_run=s.getboolean("dry_run", False),
            # logdir est dans [DEFAULT] (hérité par toutes les sections)
            logdir=s.get("logdir", ""),
            max_workers=int(s.get("max_workers", 5)),
            lock_suffix=s.get("lock_suffix", ".lck"),
            lock_poll_interval=float(s.get("lock_poll_interval", 2.0)),
            lock_timeout=float(s.get("lock_timeout", 60.0)),
        )


# ---------------------------------------------------------------------------
# Entrée de log d'une opération au sein d'une session
# ---------------------------------------------------------------------------

@dataclass
class _SyncEntry:
    """Une opération (fichier ou répertoire) effectuée pendant la session."""
    label: str          # chemin local ou libellé fourni par l'appelant
    remote: str         # cible distante
    kind: str           # "file" | "directory"
    started_at: datetime
    ended_at: datetime
    result: "SyncResult"


# ---------------------------------------------------------------------------
# SyncResult
# ---------------------------------------------------------------------------

@dataclass
class SyncResult:
    """
    Résultat d'une opération de synchronisation (fichier ou répertoire).

    Peut être agrégé dans une :class:`SyncSession` pour suivre plusieurs
    opérations au sein d'une même session de travail.
    """
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def __str__(self) -> str:
        return (
            f"SyncResult(uploaded={len(self.uploaded)}, skipped={len(self.skipped)}, "
            f"deleted={len(self.deleted)}, errors={len(self.errors)})"
        )


# ---------------------------------------------------------------------------
# SyncSession — agrégation de plusieurs SyncResult
# ---------------------------------------------------------------------------

class SyncSession:
    """
    Regroupe plusieurs opérations de synchronisation effectuées lors d'une
    même session de travail et permet de sauvegarder un rapport lisible.

    Exemple d'utilisation ::

        session = SyncSession(config)

        r1 = sync.sync_file("dist/app.js", "/public_html/app.js")
        session.add(r1, local="dist/app.js", remote="/public_html/app.js", kind="file")

        r2 = sync.sync_directory("dist/", "/public_html")
        session.add(r2, local="dist/", remote="/public_html", kind="directory")

        session.save()          # écrit le rapport dans logdir
        print(session.summary())
    """

    def __init__(self, config: "SyncConfig", label: str = ""):
        self.config = config
        self.label = label or "session"
        self.started_at: datetime = datetime.now(tz=timezone.utc)
        self._entries: list[_SyncEntry] = []

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def add(
        self,
        result: SyncResult,
        *,
        local: str,
        remote: str,
        kind: str = "file",
    ) -> None:
        """
        Enregistre le résultat d'une opération dans la session.

        :param result: :class:`SyncResult` retourné par ``sync_file`` ou
                       ``sync_directory``.
        :param local:  Chemin local utilisé (pour le rapport).
        :param remote: Chemin distant cible (pour le rapport).
        :param kind:   ``"file"`` ou ``"directory"``.
        """
        now = datetime.now(tz=timezone.utc)
        # started_at estimé : heure courante moins durée implicite (inconnue) —
        # on conserve l'heure d'ajout comme timestamp de fin.
        entry = _SyncEntry(
            label=local,
            remote=remote,
            kind=kind,
            started_at=now,
            ended_at=now,
            result=result,
        )
        self._entries.append(entry)

    @property
    def total_uploaded(self) -> int:
        return sum(len(e.result.uploaded) for e in self._entries)

    @property
    def total_skipped(self) -> int:
        return sum(len(e.result.skipped) for e in self._entries)

    @property
    def total_deleted(self) -> int:
        return sum(len(e.result.deleted) for e in self._entries)

    @property
    def total_errors(self) -> int:
        return sum(len(e.result.errors) for e in self._entries)

    @property
    def success(self) -> bool:
        return self.total_errors == 0

    def summary(self) -> str:
        """Retourne un résumé compact sur une ligne."""
        status = "OK" if self.success else "ERREURS"
        return (
            f"[{status}] Session «{self.label}» — "
            f"{len(self._entries)} opération(s) : "
            f"↑{self.total_uploaded} uploadé(s), "
            f"↷{self.total_skipped} ignoré(s), "
            f"✗{self.total_deleted} supprimé(s), "
            f"⚠{self.total_errors} erreur(s)"
        )

    def save(self, logdir: Optional[str] = None) -> Path:
        """
        Écrit le rapport de session dans un fichier texte lisible.

        Le nom du fichier est ``<label>_<YYYYMMDD_HHMMSS>.log``.

        :param logdir: Répertoire de destination. Si omis, utilise
                       ``config.logdir``. Si les deux sont vides, écrit dans
                       le répertoire courant.
        :returns: Chemin du fichier créé.
        :raises OSError: Si le répertoire ne peut pas être créé ou le fichier
                         ne peut pas être écrit.
        """
        dest_dir = Path(logdir or self.config.logdir or ".")
        dest_dir.mkdir(parents=True, exist_ok=True)

        ts = self.started_at.strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.label)
        filename = f"{safe_label}_{ts}.log"
        log_path = dest_dir / filename

        log_path.write_text(self._render_report(), encoding="utf-8")
        logger.info("Rapport de session écrit dans %s", log_path)
        return log_path

    # ------------------------------------------------------------------
    # Rendu interne
    # ------------------------------------------------------------------

    def _render_report(self) -> str:
        now = datetime.now(tz=timezone.utc)
        lines: list[str] = []

        def sep(char: str = "─", width: int = 72) -> str:
            return char * width

        lines += [
            sep("═"),
            f"  RAPPORT DE SYNCHRONISATION — {self.label.upper()}",
            sep("═"),
            f"  Début de session : {self.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"  Fin de session   : {now.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"  Serveur          : {self.config.host}:{self.config.port}"
            f"  [{self.config.protocol.value.upper()}]",
            f"  Répertoire base  : {self.config.remote_base_dir}",
            f"  Mode simulation  : {'OUI' if self.config.dry_run else 'NON'}",
            sep(),
            f"  RÉSUMÉ : {len(self._entries)} opération(s) | "
            f"↑{self.total_uploaded} uploadé(s) | "
            f"↷{self.total_skipped} ignoré(s) | "
            f"✗{self.total_deleted} supprimé(s) | "
            f"⚠{self.total_errors} erreur(s)",
            sep("═"),
            "",
        ]

        for i, entry in enumerate(self._entries, 1):
            r = entry.result
            status = "✔ OK" if r.success else "✘ ERREUR(S)"
            kind_label = "Fichier" if entry.kind == "file" else "Répertoire"
            lines += [
                f"  [{i}/{len(self._entries)}] {kind_label} — {status}",
                f"  Local  : {entry.label}",
                f"  Distant: {entry.remote}",
                sep("·"),
            ]

            if r.uploaded:
                lines.append(f"  Uploadé(s) [{len(r.uploaded)}] :")
                lines += [f"    + {f}" for f in r.uploaded]

            if r.skipped:
                lines.append(f"  Ignoré(s)  [{len(r.skipped)}] (déjà à jour) :")
                lines += [f"    = {f}" for f in r.skipped]

            if r.deleted:
                lines.append(f"  Supprimé(s)[{len(r.deleted)}] :")
                lines += [f"    - {f}" for f in r.deleted]

            if r.errors:
                lines.append(f"  Erreur(s)  [{len(r.errors)}] :")
                lines += [f"    ! {e}" for e in r.errors]

            lines.append("")

        lines += [
            sep("═"),
            f"  Statut final : {'SUCCÈS' if self.success else 'ÉCHEC (voir erreurs ci-dessus)'}",
            sep("═"),
        ]

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Inventaire local rapide (scan parallèle)
# ---------------------------------------------------------------------------

def _walk_relative(root: Path, base: Path) -> list[str]:
    """
    Parcourt récursivement ``root`` et retourne les chemins de fichiers
    relatifs à ``base`` (format posix).

    Utilise ``os.walk`` (basé sur ``os.scandir``) plutôt que
    ``Path.rglob()`` : chaque entrée de répertoire est déjà typée par le
    ``readdir`` du système (fichier / dossier) sur la plupart des OS, ce qui
    évite un appel ``stat`` supplémentaire par entrée et la création d'un
    objet ``Path`` par fichier — un gain net quand il y a des dizaines de
    milliers de fichiers, et encore plus sensible sur un partage réseau où
    chaque appel système coûte une latence.
    """
    out: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, base)
        prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/"
        out.extend(prefix + name for name in filenames)
    return out


def _scan_local_files(local: Path, max_workers: int = 8) -> set[str]:
    """
    Construit l'ensemble des chemins relatifs (posix) de tous les fichiers
    sous ``local``, en parallélisant le parcours par sous-répertoire de
    premier niveau.

    Chaque appel ``os.walk``/``os.scandir`` libère le GIL le temps de
    l'appel système : répartir le parcours sur plusieurs threads accélère
    donc réellement l'inventaire dès que les fichiers sont répartis sur
    plusieurs répertoires (cas courant), et plus encore si ``local`` est un
    montage réseau où la latence par appel domine.
    """
    try:
        entries = list(os.scandir(local))
    except OSError as exc:
        logger.error("Impossible de lister %s : %s", local, exc)
        return set()

    top_dirs = [e.path for e in entries if e.is_dir(follow_symlinks=False)]
    local_files: set[str] = {
        e.name for e in entries if e.is_file(follow_symlinks=False)
    }

    if not top_dirs:
        return local_files

    workers = max(1, min(max_workers, len(top_dirs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_walk_relative, Path(d), local) for d in top_dirs]
        for future in as_completed(futures):
            local_files.update(future.result())

    return local_files


def _expand_dir_closure(dirs: set[str], root: str) -> list[set[str]]:
    """
    Calcule l'ensemble complet des répertoires distants à créer sous
    ``root`` — chaque répertoire ET tous ses ancêtres jusqu'à ``root``,
    chacun une seule fois quel que soit le nombre de fichiers qui le
    référencent — puis les regroupe par palier de profondeur relative à
    ``root`` (palier 1 = enfants directs de ``root``, palier 2 =
    petits-enfants, etc.).

    Ce regroupement permet de créer les répertoires palier par palier
    (les parents d'un palier sont garantis créés avant de passer au
    suivant) tout en parallélisant la création à l'intérieur d'un même
    palier — sans jamais revérifier deux fois le même ancêtre.
    """
    root = root.rstrip("/")
    all_dirs: set[str] = set()
    for d in dirs:
        d = d.rstrip("/")
        if not d or d == root or not d.startswith(root + "/"):
            continue
        cur = d
        while cur and cur != root and cur not in all_dirs:
            all_dirs.add(cur)
            if "/" not in cur:
                break
            parent = cur.rsplit("/", 1)[0]
            if len(parent) < len(root):
                break
            cur = parent

    by_depth: dict[int, set[str]] = {}
    for d in all_dirs:
        depth = d[len(root):].count("/")
        by_depth.setdefault(depth, set()).add(d)

    return [by_depth[k] for k in sorted(by_depth)]


# ---------------------------------------------------------------------------
# Backend abstrait
# ---------------------------------------------------------------------------

class _BaseBackend(ABC):
    def __init__(self, cfg: SyncConfig):
        self.cfg = cfg

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def upload_file(self, local_path: Path, remote_path: str, ensure_dir: bool = True) -> None:
        """
        :param ensure_dir: Si True (défaut), vérifie/crée le répertoire
            parent avant l'upload (comportement historique, nécessaire pour
            un usage isolé comme sync_file()). Si False, suppose que
            l'appelant a déjà garanti l'existence du répertoire (cas de
            sync_directory(), qui pré-crée tout en amont) — évite un
            aller-retour réseau par fichier rien que pour re-vérifier un
            répertoire déjà connu comme existant.
        """
        ...

    @abstractmethod
    def remote_mtime(self, remote_path: str) -> Optional[float]:
        """Retourne le timestamp de modification distant, ou None si inconnu."""
        ...

    @abstractmethod
    def makedirs(self, remote_dir: str) -> None: ...

    @abstractmethod
    def mkdir_leaf(self, remote_dir: str) -> None:
        """
        Crée UN SEUL répertoire — le parent est supposé déjà exister
        (garanti par l'appelant, voir RemoteSync._ensure_remote_dirs_parallel).
        Contrairement à makedirs(), ne revérifie pas toute la chaîne
        d'ancêtres : un aller-retour réseau si le répertoire existe déjà,
        deux s'il faut le créer.
        """
        ...

    @abstractmethod
    def list_remote(self, remote_dir: str) -> list[str]:
        """Liste récursive des fichiers sous remote_dir (chemins relatifs à remote_dir)."""
        ...

    @abstractmethod
    def list_dir_entries(self, remote_dir: str) -> list[tuple[str, bool, Optional[float]]]:
        """
        Liste le contenu DIRECT (non récursif) de ``remote_dir`` — un seul
        aller-retour réseau.

        :returns: liste de ``(nom, est_un_repertoire, mtime_ou_None)``.
                  ``mtime`` vaut ``None`` pour les répertoires, et aussi pour
                  les fichiers si le mtime n'a pas pu être obtenu en même
                  temps que le listing (ex : serveur FTP sans MLSD).
        """
        ...

    def list_remote_with_mtimes(self, remote_dir: str) -> dict[str, Optional[float]]:
        """
        Liste récursive des fichiers sous ``remote_dir`` avec leur mtime, sur
        UNE connexion, en s'appuyant sur :meth:`list_dir_entries`.

        Utile pour un usage simple/séquentiel. Pour de gros volumes sur
        SSH/SFTP où la latence par aller-retour domine, préférer le
        parcours parallèle de :meth:`RemoteSync._scan_remote_parallel`, qui
        répartit les répertoires sur plusieurs connexions simultanées au
        lieu d'attendre chaque réponse l'une après l'autre.
        """
        result: dict[str, Optional[float]] = {}
        self._list_dir_recursive(remote_dir, "", result)
        return result

    def _list_dir_recursive(self, remote_dir: str, prefix: str, result: dict) -> None:
        for name, is_dir, mtime in self.list_dir_entries(remote_dir):
            full = remote_dir.rstrip("/") + "/" + name
            rel = prefix + name
            if is_dir:
                self._list_dir_recursive(full, rel + "/", result)
            else:
                result[rel] = mtime

    @abstractmethod
    def remote_exists(self, remote_path: str) -> bool:
        """Retourne True si le chemin distant existe (fichier ou répertoire)."""
        ...

    @abstractmethod
    def create_empty_file(self, remote_path: str) -> None:
        """Crée un fichier vide sur le serveur distant (utilisé pour les locks)."""
        ...

    @abstractmethod
    def download_file(self, remote_path: str, local_path: Path) -> None:
        """Télécharge un fichier distant vers local_path."""
        ...

    @abstractmethod
    def delete_remote(self, remote_path: str) -> None: ...

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()


# ---------------------------------------------------------------------------
# Backend FTP / FTPS / FTP+TLS
# ---------------------------------------------------------------------------

class _FTPBackend(_BaseBackend):
    def __init__(self, cfg: SyncConfig):
        super().__init__(cfg)
        self._ftp: Optional[ftplib.FTP] = None

    def connect(self) -> None:
        p = self.cfg.protocol
        if p == Protocol.FTPS:
            self._ftp = ftplib.FTP_TLS()
            self._ftp.connect(self.cfg.host, self.cfg.port, timeout=self.cfg.timeout)
            self._ftp.auth()
            self._ftp.prot_p()
        elif p == Protocol.FTPTLS:
            self._ftp = ftplib.FTP_TLS()
            self._ftp.connect(self.cfg.host, self.cfg.port, timeout=self.cfg.timeout)
            self._ftp.login(self.cfg.username, self.cfg.password)
            self._ftp.prot_p()
        else:  # plain FTP
            self._ftp = ftplib.FTP()
            self._ftp.connect(self.cfg.host, self.cfg.port, timeout=self.cfg.timeout)

        if p != Protocol.FTPTLS:
            self._ftp.login(self.cfg.username, self.cfg.password)

        if self.cfg.passive_mode:
            self._ftp.set_pasv(True)

        logger.info("FTP connecté à %s:%s", self.cfg.host, self.cfg.port)

    def disconnect(self) -> None:
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                self._ftp.close()
            self._ftp = None

    def upload_file(self, local_path: Path, remote_path: str, ensure_dir: bool = True) -> None:
        if ensure_dir:
            self.makedirs(os.path.dirname(remote_path))
        with open(local_path, "rb") as fh:
            self._ftp.storbinary(f"STOR {remote_path}", fh)

    def remote_mtime(self, remote_path: str) -> Optional[float]:
        try:
            resp = self._ftp.sendcmd(f"MDTM {remote_path}")
            # Format : "213 YYYYMMDDHHMMSS"
            ts_str = resp[4:].strip()
            dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None

    def makedirs(self, remote_dir: str) -> None:
        if not remote_dir or remote_dir == "/":
            return
        parts = remote_dir.replace("\\", "/").split("/")
        path = ""
        for part in parts:
            if not part:
                continue
            path += "/" + part
            try:
                self._ftp.mkd(path)
            except ftplib.error_perm as e:
                if "550" not in str(e):  # 550 = déjà existant
                    raise

    def mkdir_leaf(self, remote_dir: str) -> None:
        try:
            self._ftp.mkd(remote_dir)
        except ftplib.error_perm as e:
            if "550" not in str(e):  # 550 = déjà existant
                raise

    def list_remote(self, remote_dir: str) -> list[str]:
        result: list[str] = []
        try:
            items = self._ftp.nlst(remote_dir)
        except ftplib.error_temp:
            return result
        for item in items:
            try:
                # Essayer d'entrer dedans → c'est un répertoire
                self._ftp.cwd(item)
                self._ftp.cwd("/")
                sub = self.list_remote(item)
                result.extend(sub)
            except ftplib.error_perm:
                result.append(item)
        return result

    def list_dir_entries(self, remote_dir: str) -> list[tuple[str, bool, Optional[float]]]:
        """
        Contenu direct de remote_dir via MLSD (RFC 3659) — un aller-retour
        pour les noms ET les attributs (dont le mtime). Repli sur
        NLST/CWD (sans mtime) si le serveur ne supporte pas MLSD.
        """
        out: list[tuple[str, bool, Optional[float]]] = []
        try:
            entries = list(self._ftp.mlsd(remote_dir))
        except Exception:
            try:
                items = self._ftp.nlst(remote_dir)
            except ftplib.error_temp:
                return out
            for item in items:
                name = item.rsplit("/", 1)[-1]
                try:
                    self._ftp.cwd(item)
                    self._ftp.cwd("/")
                    out.append((name, True, None))
                except ftplib.error_perm:
                    out.append((name, False, None))
            return out

        for name, facts in entries:
            type_ = facts.get("type", "")
            if name in (".", "..") or type_ in ("cdir", "pdir"):
                continue
            is_dir = type_ == "dir"
            mtime = None
            if not is_dir:
                modify = facts.get("modify")
                if modify:
                    try:
                        dt = datetime.strptime(modify[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                        mtime = dt.timestamp()
                    except ValueError:
                        mtime = None
            out.append((name, is_dir, mtime))
        return out

    def remote_exists(self, remote_path: str) -> bool:
        try:
            self._ftp.sendcmd(f"MDTM {remote_path}")
            return True
        except ftplib.error_perm:
            return False

    def create_empty_file(self, remote_path: str) -> None:
        """
        Crée un fichier vide en mode pseudo-exclusif via FTP.

        FTP ne supporte pas O_CREAT|O_EXCL nativement. On simule l'atomicité
        avec un fichier temporaire unique puis un RNFR/RNTO (rename) :
        si le fichier cible existe déjà, le rename échoue avec une erreur 550.
        """
        import io
        import uuid
        tmp_path = remote_path + f".tmp_{uuid.uuid4().hex}"
        try:
            # 1. Upload du fichier temporaire (nom unique → pas de collision)
            self._ftp.storbinary(f"STOR {tmp_path}", io.BytesIO(b""))
            # 2. Rename atomique : échoue si la cible existe déjà
            self._ftp.rename(tmp_path, remote_path)
        except ftplib.error_perm as exc:
            # Nettoyage du temporaire en cas d'échec du rename
            try:
                self._ftp.delete(tmp_path)
            except Exception:
                pass
            raise FileExistsError(
                f"Le verrou {remote_path!r} existe déjà (ou rename refusé) : {exc}"
            ) from exc

    def download_file(self, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as fh:
            self._ftp.retrbinary(f"RETR {remote_path}", fh.write)

    def delete_remote(self, remote_path: str) -> None:
        self._ftp.delete(remote_path)


# ---------------------------------------------------------------------------
# Backend SFTP (SSH)
# ---------------------------------------------------------------------------

class _SFTPBackend(_BaseBackend):
    def __init__(self, cfg: SyncConfig):
        super().__init__(cfg)
        self._ssh = None
        self._sftp = None

    def connect(self) -> None:
        try:
            import paramiko  # type: ignore
        except ImportError:
            raise ImportError(
                "Le module 'paramiko' est requis pour le protocole SFTP.\n"
                "Installez-le avec : pip install paramiko"
            )

        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = dict(
            hostname=self.cfg.host,
            port=self.cfg.port,
            username=self.cfg.username,
            timeout=self.cfg.timeout,
            compress=self.cfg.compression,
        )
        if self.cfg.ssh_key_path:
            connect_kwargs["key_filename"] = self.cfg.ssh_key_path
        else:
            connect_kwargs["password"] = self.cfg.password

        self._ssh.connect(**connect_kwargs)
        if self.cfg.compression:
            # Sécurité supplémentaire : force explicitement la compression sur le
            # transport déjà négocié (utile si connect() ne l'a pas activée en
            # amont, p.ex. anciennes versions de paramiko).
            transport = self._ssh.get_transport()
            if transport is not None:
                transport.use_compression(True)
        logger.debug(
            "Compression SFTP : %s", "activée" if self.cfg.compression else "désactivée"
        )
        self._sftp = self._ssh.open_sftp()
        logger.info("SFTP connecté à %s:%s", self.cfg.host, self.cfg.port)

    def disconnect(self) -> None:
        if self._sftp:
            self._sftp.close()
        if self._ssh:
            self._ssh.close()
        self._sftp = self._ssh = None

    def upload_file(self, local_path: Path, remote_path: str, ensure_dir: bool = True) -> None:
        if ensure_dir:
            self.makedirs(os.path.dirname(remote_path))
        self._sftp.put(str(local_path), remote_path)

    def remote_mtime(self, remote_path: str) -> Optional[float]:
        try:
            attrs = self._sftp.stat(remote_path)
            return float(attrs.st_mtime)
        except Exception:
            return None

    def makedirs(self, remote_dir: str) -> None:
        if not remote_dir:
            return
        parts = remote_dir.replace("\\", "/").split("/")
        path = ""
        for part in parts:
            if not part:
                continue
            path += "/" + part
            try:
                self._sftp.stat(path)
            except FileNotFoundError:
                self._sftp.mkdir(path)

    def mkdir_leaf(self, remote_dir: str) -> None:
        try:
            self._sftp.stat(remote_dir)
        except FileNotFoundError:
            self._sftp.mkdir(remote_dir)

    def list_remote(self, remote_dir: str) -> list[str]:
        result: list[str] = []
        try:
            attrs_list = self._sftp.listdir_attr(remote_dir)
        except Exception:
            return result
        for attr in attrs_list:
            full = remote_dir.rstrip("/") + "/" + attr.filename
            if stat.S_ISDIR(attr.st_mode):
                result.extend(self.list_remote(full))
            else:
                result.append(full)
        return result

    def list_dir_entries(self, remote_dir: str) -> list[tuple[str, bool, Optional[float]]]:
        """
        Contenu direct de remote_dir via listdir_attr() — un seul
        aller-retour SSH pour les noms ET les attributs (dont st_mtime).
        """
        try:
            attrs_list = self._sftp.listdir_attr(remote_dir)
        except Exception:
            return []
        out: list[tuple[str, bool, Optional[float]]] = []
        for attr in attrs_list:
            is_dir = stat.S_ISDIR(attr.st_mode)
            mtime = None if is_dir else (
                float(attr.st_mtime) if attr.st_mtime is not None else None
            )
            out.append((attr.filename, is_dir, mtime))
        return out

    def remote_exists(self, remote_path: str) -> bool:
        try:
            self._sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False

    def create_empty_file(self, remote_path: str) -> None:
        """
        Crée un fichier vide en mode exclusif (O_CREAT | O_EXCL) via SFTP.

        Si le fichier existe déjà, paramiko lève OSError(EEXIST) et on
        convertit en FileExistsError pour uniformiser avec le backend FTP.
        """
        import os as _os
        O_CREAT = _os.O_CREAT
        O_EXCL  = _os.O_EXCL
        O_WRONLY = _os.O_WRONLY
        try:
            f = self._sftp.open(remote_path, mode="x")  # 'x' = O_CREAT|O_EXCL|O_WRONLY
            f.close()
        except OSError as exc:
            raise FileExistsError(
                f"Le verrou {remote_path!r} existe déjà : {exc}"
            ) from exc

    def download_file(self, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._sftp.get(remote_path, str(local_path))

    def delete_remote(self, remote_path: str) -> None:
        self._sftp.remove(remote_path)


# ---------------------------------------------------------------------------
# Exceptions publiques
# ---------------------------------------------------------------------------

class LockTimeoutError(TimeoutError):
    """
    Levée par :class:`LockedFetch` lorsque le verrou distant n'a pas disparu
    avant l'expiration du délai ``lock_timeout``.

    Attributs
    ---------
    lock_path   : chemin du fichier verrou qui bloque.
    timeout     : durée d'attente maximale configurée (secondes).
    elapsed     : durée réellement attendue avant l'abandon (secondes).
    """

    def __init__(self, lock_path: str, timeout: float, elapsed: float):
        self.lock_path = lock_path
        self.timeout = timeout
        self.elapsed = elapsed
        super().__init__(
            f"Le verrou {lock_path!r} existe toujours après {elapsed:.1f}s "
            f"(timeout={timeout:.1f}s). Abandon sans suppression du verrou."
        )


# ---------------------------------------------------------------------------
# Context manager — téléchargement avec verrou distant
# ---------------------------------------------------------------------------

class LockedFetch:
    """
    Context manager retourné par :meth:`RemoteSync.fetch_locked`.

    Cycle de vie
    ------------
    ``__enter__``
        1. Ouvre une connexion unique au serveur.
        2. **Attend** que ``<remote_path><lock_suffix>`` disparaisse si présent,
           en sondant toutes les ``lock_poll_interval`` secondes.
           Lève :class:`LockTimeoutError` si ``lock_timeout`` est dépassé
           (le verrou existant n'est **pas** supprimé).
        3. Crée ``<remote_path><lock_suffix>`` (marque notre propre verrou).
        4. Télécharge ``<remote_path>`` vers la destination locale.

    ``__exit__`` (succès OU exception OU interruption)
        5. Si le téléchargement a réussi : supprime ``<remote_path>`` du serveur.
        6. Supprime notre ``<remote_path><lock_suffix>`` dans **tous les cas**.
        7. Ferme la connexion.

    La suppression du lock (étape 6) est protégée par un ``try/except``
    indépendant afin de ne jamais masquer une exception métier.

    Attributs exposés dans le bloc ``with``
    ----------------------------------------
    ``result``  :class:`SyncResult` — résultat du téléchargement.
    """

    def __init__(
        self,
        sync: "RemoteSync",
        remote_path: str,
        local_path: Optional[str | Path],
        lock_suffix: str,
        poll_interval: float,
        timeout: float,
    ):
        self._sync = sync
        self._remote_path = sync._resolve_remote(remote_path)
        self._lock_path = self._remote_path + lock_suffix
        self._local_path = local_path
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._backend: Optional[_BaseBackend] = None
        self._lock_created: bool = False   # True uniquement si C'EST NOUS qui avons créé le lock
        self.result: SyncResult = SyncResult()

    # ------------------------------------------------------------------

    def __enter__(self) -> "LockedFetch":
        import time
        cfg = self._sync.config

        remote_name = self._remote_path.rstrip("/").split("/")[-1]

        # Résolution destination locale
        if self._local_path is None:
            dest = Path.cwd() / remote_name
        else:
            dest = Path(self._local_path)
            if dest.is_dir():
                dest = dest / remote_name
        self._dest = dest

        # Connexion unique pour toute la durée du contexte
        self._backend = self._sync._build_backend()
        self._backend.connect()

        # ── 1. Attente si un verrou existe déjà ──────────────────────────
        deadline = time.monotonic() + self._timeout
        elapsed = 0.0
        while self._backend.remote_exists(self._lock_path):
            elapsed = time.monotonic() - (deadline - self._timeout)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # Timeout : on ferme la connexion et on lève sans supprimer le lock
                try:
                    self._backend.disconnect()
                except Exception:
                    pass
                self._backend = None
                raise LockTimeoutError(self._lock_path, self._timeout, elapsed)

            wait = min(self._poll_interval, remaining)
            logger.info(
                "[LOCK-WAIT] %s présent, nouvel essai dans %.1fs (%.1f/%.1fs écoulées)",
                self._lock_path, wait, elapsed, self._timeout,
            )
            time.sleep(wait)

        # ── 2. Création de notre verrou (mode exclusif) ───────────────────
        # On reste dans une boucle car deux processus peuvent passer le
        # remote_exists() simultanément et tenter le create en même temps.
        # Celui qui perd obtient FileExistsError et retourne attendre.
        while True:
            try:
                self._backend.create_empty_file(self._lock_path)
                self._lock_created = True
                logger.info("[LOCK]     créé   : %s", self._lock_path)
                break
            except FileExistsError:
                # Un autre processus nous a devancés : on retourne attendre
                elapsed = time.monotonic() - (deadline - self._timeout)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    try:
                        self._backend.disconnect()
                    except Exception:
                        pass
                    self._backend = None
                    raise LockTimeoutError(self._lock_path, self._timeout, elapsed)
                wait = min(self._poll_interval, remaining)
                logger.info(
                    "[LOCK-RACE] %s pris par un concurrent, attente %.1fs",
                    self._lock_path, wait,
                )
                time.sleep(wait)
                # Re-vérification : attendre que le verrou concurrent disparaisse
                while self._backend.remote_exists(self._lock_path):
                    elapsed = time.monotonic() - (deadline - self._timeout)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        try:
                            self._backend.disconnect()
                        except Exception:
                            pass
                        self._backend = None
                        raise LockTimeoutError(self._lock_path, self._timeout, elapsed)
                    wait = min(self._poll_interval, remaining)
                    logger.info(
                        "[LOCK-WAIT] %s présent, nouvel essai dans %.1fs (%.1f/%.1fs écoulées)",
                        self._lock_path, wait, elapsed, self._timeout,
                    )
                    time.sleep(wait)
            except Exception as exc:
                try:
                    self._backend.disconnect()
                except Exception:
                    pass
                self._backend = None
                raise RuntimeError(
                    f"Impossible de créer le verrou {self._lock_path!r} : {exc}"
                ) from exc

        # ── 3. Téléchargement ─────────────────────────────────────────────
        try:
            if cfg.dry_run:
                logger.info("[DRY-RUN] %s ← %s", dest, self._remote_path)
                self.result.uploaded.append(str(dest))
            else:
                logger.info("[DOWNLOAD] %s ← %s", dest, self._remote_path)
                self._backend.download_file(self._remote_path, dest)
                self.result.uploaded.append(str(dest))

        except Exception as exc:
            msg = f"{self._remote_path} → {dest} : {exc}"
            self.result.errors.append(msg)
            logger.error("[ERROR]    %s", msg)
            if dest.exists() and dest.stat().st_size == 0:
                try:
                    dest.unlink()
                except OSError:
                    pass

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Nettoyage garanti :
          - supprime le fichier distant si le téléchargement a réussi
          - supprime notre .lck dans tous les cas (sauf LockTimeoutError)
          - ferme la connexion
        Retourne toujours ``False`` : les exceptions du bloc ``with`` se propagent.
        """
        if self._backend is None:
            # Connexion déjà fermée (LockTimeoutError ou échec de connexion)
            return False

        # ── 4. Suppression du fichier distant si téléchargement réussi ────
        if self.result.success and not self._sync.config.dry_run:
            try:
                self._backend.delete_remote(self._remote_path)
                logger.info("[DELETE]   distant : %s", self._remote_path)
            except Exception as exc:
                msg = f"Impossible de supprimer {self._remote_path!r} : {exc}"
                self.result.errors.append(msg)
                logger.error("[ERROR]    %s", msg)

        # ── 5. Suppression de notre verrou (toujours, sauf si on ne l'a pas créé)
        if self._lock_created:
            try:
                self._backend.delete_remote(self._lock_path)
                logger.info("[UNLOCK]   supprimé : %s", self._lock_path)
            except Exception as exc:
                logger.warning(
                    "[WARN] Impossible de supprimer le verrou %s : %s",
                    self._lock_path, exc,
                )

        # ── 6. Fermeture de la connexion ─────────────────────────────────
        try:
            self._backend.disconnect()
        except Exception:
            pass
        self._backend = None

        return False


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class RemoteSync:
    """
    Synchronise des fichiers locaux vers un serveur distant.

    Exemple d'utilisation ::

        sync = RemoteSync("config.ini")
        result = sync.sync_directory("/var/www/html", "/public_html")
        result = sync.sync_file("/var/www/html/index.html", "/public_html/index.html")
        print(result)
    """

    def __init__(self, config_path: str | Path, section: str = "remotesync"):
        self.config = SyncConfig.from_ini(config_path, section)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def sync_file(
        self,
        local_path: str | Path,
        remote_path: Optional[str] = None,
    ) -> SyncResult:
        """
        Synchronise un fichier unique.

        :param local_path:  Chemin local du fichier source.
        :param remote_path: Chemin distant du fichier cible.
                            - Si omis : ``remote_base_dir/<nom_du_fichier>``
                            - Si relatif (ne commence pas par «/») :
                              ``remote_base_dir/<remote_path>``
                            - Si absolu : utilisé tel quel.
        """
        result = SyncResult()
        local = Path(local_path)
        if not local.is_file():
            result.errors.append(f"Fichier local introuvable : {local}")
            return result

        if remote_path is None:
            remote_path = self.config.remote_base_dir.rstrip("/") + "/" + local.name
        else:
            remote_path = self._resolve_remote(remote_path)

        try:
            with self._build_backend() as backend:
                self._sync_single(backend, local, remote_path, result)
        except Exception as exc:
            logger.exception("Erreur de connexion")
            result.errors.append(str(exc))
        return result

    def sync_directory(
        self,
        local_dir: str | Path,
        remote_dir: Optional[str] = None,
        max_workers: Optional[int] = None,
    ) -> SyncResult:
        """
        Synchronise récursivement un répertoire local vers le serveur distant
        en utilisant des transferts simultanés.

        Chaque worker maintient sa propre connexion au serveur pour garantir
        la thread-safety (les connexions FTP/SFTP ne sont pas partagées).

        :param local_dir:   Répertoire local source.
        :param remote_dir:  Répertoire distant cible.
                            - Si omis : ``remote_base_dir``
                            - Si relatif : ``remote_base_dir/<remote_dir>``
                            - Si absolu : utilisé tel quel.
        :param max_workers: Nombre de connexions/transferts simultanés.
                            Priorité : argument > ``config.max_workers`` (défaut 5).
        """
        result = SyncResult()
        lock = threading.Lock()
        local = Path(local_dir)

        if not local.is_dir():
            result.errors.append(f"Répertoire local introuvable : {local}")
            return result

        if remote_dir is None:
            remote_dir = self.config.remote_base_dir
        else:
            remote_dir = self._resolve_remote(remote_dir)

        workers = max_workers if max_workers is not None else self.config.max_workers
        workers = max(1, workers)

        # ── 1. Inventaire local (parcours parallèle par sous-répertoire) ──────
        # local.rglob() est monothread et devient très lent avec des dizaines
        # de milliers de fichiers. On répartit le parcours sur plusieurs
        # threads (un par sous-répertoire de premier niveau), ce qui accélère
        # nettement l'inventaire puisque les fichiers sont répartis sur
        # plusieurs répertoires.
        local_files = _scan_local_files(local, max_workers=max(workers * 2, 8))

        # ── 2. Pré-création des répertoires distants (sérialisée) ─────────────
        # On crée l'arborescence avant le lancement des workers pour éviter
        # les conditions de course sur makedirs entre threads.
        remote_dirs_needed = {
            remote_dir.rstrip("/") + "/" + os.path.dirname(rel)
            for rel in local_files
        }
        try:
            self._ensure_remote_dirs_parallel(remote_dirs_needed, remote_dir, workers)
        except Exception as exc:
            logger.exception("Erreur lors de la préparation des répertoires distants")
            result.errors.append(f"Préparation distante : {exc}")
            return result

        # ── 2bis. Balayage distant EN PARALLÈLE (listing + mtimes) ────────────
        # Sur SSH/SFTP, une seule connexion qui liste les répertoires un par
        # un paie la latence réseau complète à chaque fois : c'est souvent le
        # vrai goulot, avant même les uploads. On répartit donc le parcours
        # de l'arborescence distante sur plusieurs connexions simultanées
        # (voir _scan_remote_parallel), ce qui remplace aussi l'ancien
        # MDTM/stat interrogé un par un pour chaque fichier pendant les
        # transferts. Même nombre de connexions que pour les uploads
        # (``max_workers``), pour rester cohérent avec ce que le serveur
        # accepte déjà.
        try:
            remote_mtimes: dict[str, Optional[float]] = self._scan_remote_parallel(
                remote_dir, workers
            )
        except Exception as exc:
            logger.exception("Erreur lors du balayage distant")
            result.errors.append(f"Balayage distant : {exc}")
            return result

        # Liste des fichiers distants (pour la suppression des orphelins),
        # dérivée du même balayage — pas d'appel réseau supplémentaire.
        remote_files_list: list[str] = (
            [remote_dir.rstrip("/") + "/" + rel for rel in remote_mtimes]
            if self.config.delete_orphans else []
        )

        # ── 3. Transferts parallèles — connexion persistante par worker ──────────
        #
        # ARCHITECTURE CORRIGÉE :
        # Avant : _worker(fichier) → 1 connexion SSH par fichier  ← bug (avalanche)
        # Après : _worker(lot)    → 1 connexion SSH pour N fichiers du lot
        #
        # On distribue les fichiers en lots équilibrés (round-robin), puis chaque
        # worker ouvre UNE connexion pour traiter tous les fichiers de son lot.

        sorted_files = sorted(local_files)
        # Découpage en lots : chaque worker reçoit un sous-ensemble de fichiers
        # distribué de façon interleaved pour équilibrer la charge (pas de split
        # en tranches consécutives qui favoriserait les gros répertoires uniques).
        batches: list[list[str]] = [[] for _ in range(workers)]
        for i, rel in enumerate(sorted_files):
            batches[i % workers].append(rel)

        def _worker_batch(batch: list[str]) -> None:
            """
            Traite un lot de fichiers sur UNE connexion persistante.
            Ouvre la connexion une seule fois, itère sur les fichiers, ferme.
            """
            if not batch:
                return
            try:
                with self._build_backend() as backend:
                    for rel in batch:
                        local_file = local / rel
                        remote_file = remote_dir.rstrip("/") + "/" + rel
                        try:
                            if rel in remote_mtimes:
                                remote_mtime = remote_mtimes[rel]
                                if remote_mtime is None:
                                    # mtime non obtenu lors du balayage groupé
                                    # (ex : serveur FTP sans MLSD) → on retombe
                                    # sur l'appel individuel, uniquement pour
                                    # ce fichier.
                                    remote_mtime = backend.remote_mtime(remote_file)
                            else:
                                # Absent du balayage initial → n'existe pas
                                # encore côté distant, upload direct.
                                remote_mtime = None
                            local_mtime = local_file.stat().st_mtime

                            if remote_mtime is not None and local_mtime <= remote_mtime:
                                with lock:
                                    result.skipped.append(remote_file)
                                logger.debug("[SKIP]   %s (déjà à jour)", remote_file)
                                continue

                            action = "[DRY-RUN]" if self.config.dry_run else "[UPLOAD]"
                            logger.info("%s %s → %s", action, local_file, remote_file)

                            if not self.config.dry_run:
                                # ensure_dir=False : sync_directory a déjà
                                # pré-créé tous les répertoires en amont
                                # (_ensure_remote_dirs_parallel) — inutile
                                # de revérifier à chaque fichier.
                                backend.upload_file(local_file, remote_file, ensure_dir=False)

                            with lock:
                                result.uploaded.append(remote_file)

                        except Exception as exc:
                            msg = f"{remote_file}: {exc}"
                            logger.error("[ERROR]  %s", msg)
                            with lock:
                                result.errors.append(msg)

            except Exception as exc:
                # Erreur de connexion : tous les fichiers du lot échouent
                for rel in batch:
                    remote_file = remote_dir.rstrip("/") + "/" + rel
                    msg = f"{remote_file}: erreur de connexion : {exc}"
                    logger.error("[ERROR]  %s", msg)
                    with lock:
                        result.errors.append(msg)

        try:
            # On ne soumet que les lots non vides (si workers > nb fichiers)
            non_empty_batches = [b for b in batches if b]
            with ThreadPoolExecutor(max_workers=len(non_empty_batches) or 1) as pool:
                futures = {pool.submit(_worker_batch, batch): batch
                           for batch in non_empty_batches}
                for future in as_completed(futures):
                    exc = future.exception()
                    if exc:
                        batch = futures[future]
                        msg = f"Lot [{batch[0]}…]: erreur inattendue : {exc}"
                        logger.error("[ERROR]  %s", msg)
                        with lock:
                            result.errors.append(msg)
        except Exception as exc:
            logger.exception("Erreur du pool de threads")
            result.errors.append(str(exc))
            return result

        # ── 4. Suppression des orphelins distants (sérialisée) ────────────────
        if self.config.delete_orphans and remote_files_list:
            try:
                with self._build_backend() as backend:
                    for rf in remote_files_list:
                        rel = rf[len(remote_dir):].lstrip("/")
                        if rel not in local_files:
                            if not self.config.dry_run:
                                backend.delete_remote(rf)
                            with lock:
                                result.deleted.append(rf)
                            logger.info("[DELETED] %s", rf)
            except Exception as exc:
                logger.exception("Erreur lors de la suppression des orphelins")
                result.errors.append(f"Suppression orphelins : {exc}")

        logger.info(
            "sync_directory terminé — workers=%d | ↑%d uploadé(s) | ↷%d ignoré(s) | "
            "✗%d supprimé(s) | ⚠%d erreur(s)",
            workers,
            len(result.uploaded), len(result.skipped),
            len(result.deleted), len(result.errors),
        )
        return result

    def fetch_file(
        self,
        remote_path: str,
        local_path: Optional[str | Path] = None,
        overwrite: bool = True,
    ) -> SyncResult:
        """
        Télécharge un fichier depuis le serveur distant vers le système local.

        :param remote_path: Chemin du fichier sur le serveur.
                            - Si relatif : ``remote_base_dir/<remote_path>``
                            - Si absolu  : utilisé tel quel.
        :param local_path:  Destination locale.
                            - Si omis : le fichier est déposé dans le répertoire
                              courant avec le même nom que le fichier distant.
                            - Si un répertoire : le fichier y est déposé avec
                              son nom d'origine.
                            - Si un chemin de fichier : utilisé tel quel.
        :param overwrite:   Si ``False`` et que le fichier local existe déjà et
                            est plus récent que le fichier distant, le téléchar-
                            gement est ignoré (comportement miroir de sync_file).
                            Par défaut ``True`` (téléchargement systématique).
        :returns: :class:`SyncResult` —
                  ``uploaded`` contient le chemin local du fichier téléchargé,
                  ``skipped`` contient le chemin local si ignoré.
        """
        result = SyncResult()
        remote_path = self._resolve_remote(remote_path)
        remote_name = remote_path.rstrip("/").split("/")[-1]

        # Résolution de la destination locale
        if local_path is None:
            dest = Path.cwd() / remote_name
        else:
            dest = Path(local_path)
            if dest.is_dir():
                dest = dest / remote_name

        try:
            with self._build_backend() as backend:
                # Vérification overwrite / mtime
                if not overwrite and dest.exists():
                    remote_mtime = backend.remote_mtime(remote_path)
                    local_mtime = dest.stat().st_mtime
                    if remote_mtime is None or local_mtime >= remote_mtime:
                        result.skipped.append(str(dest))
                        logger.debug(
                            "[SKIP] %s (local déjà à jour)", dest
                        )
                        return result

                if self.config.dry_run:
                    logger.info("[DRY-RUN] %s ← %s", dest, remote_path)
                    result.uploaded.append(str(dest))
                    return result

                logger.info("[DOWNLOAD] %s ← %s", dest, remote_path)
                backend.download_file(remote_path, dest)
                result.uploaded.append(str(dest))

        except Exception as exc:
            msg = f"{remote_path} → {dest} : {exc}"
            result.errors.append(msg)
            logger.error("[ERROR] %s", msg)
            # Nettoyer un fichier partiellement téléchargé
            if dest.exists() and dest.stat().st_size == 0:
                try:
                    dest.unlink()
                except OSError:
                    pass

        return result

    def fetch_locked(
        self,
        remote_path: str,
        local_path: Optional[str | Path] = None,
        lock_suffix: Optional[str] = None,
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> "LockedFetch":
        """
        Context manager pour télécharger un fichier distant avec verrou.

        Si un verrou ``<remote_path><lock_suffix>`` existe déjà sur le serveur,
        attend qu'il disparaisse en sondant toutes les ``poll_interval`` secondes.
        Lève :class:`LockTimeoutError` si ``timeout`` est dépassé (le verrou
        existant n'est **pas** supprimé — il appartient à un autre processus).

        Séquence garantie ::

            with sync.fetch_locked("/data/export.csv", "/tmp/export.csv") as ctx:
                # export.csv.lck existe sur le serveur (notre verrou)
                # export.csv a été téléchargé localement
                if ctx.result.success:
                    process(ctx.result)
            # À la sortie (succès OU exception) :
            #   - export.csv supprimé du serveur  si téléchargement réussi
            #   - export.csv.lck supprimé du serveur dans tous les cas

        :param remote_path:    Chemin du fichier distant (absolu ou relatif à
                               ``remote_base_dir``).
        :param local_path:     Destination locale (voir :meth:`fetch_file`).
        :param lock_suffix:    Suffixe du verrou. Défaut : ``config.lock_suffix``
                               (``".lck"`` par défaut dans la config).
        :param poll_interval:  Secondes entre deux sondages. Défaut :
                               ``config.lock_poll_interval`` (2s).
        :param timeout:        Secondes avant :class:`LockTimeoutError`. Défaut :
                               ``config.lock_timeout`` (60s).
        :raises LockTimeoutError: Si le verrou existant ne disparaît pas à temps.
        :raises RuntimeError:     Si la création de notre propre verrou échoue.
        :returns:              :class:`LockedFetch` (context manager).
        """
        return LockedFetch(
            sync=self,
            remote_path=remote_path,
            local_path=local_path,
            lock_suffix=lock_suffix if lock_suffix is not None else self.config.lock_suffix,
            poll_interval=poll_interval if poll_interval is not None else self.config.lock_poll_interval,
            timeout=timeout if timeout is not None else self.config.lock_timeout,
        )

    # ------------------------------------------------------------------
    # Méthodes internes
    # ------------------------------------------------------------------

    def _resolve_remote(self, remote: str) -> str:
        """
        Résout un chemin distant :
        - chemin absolu (commence par «/») → retourné inchangé
        - chemin relatif → ``remote_base_dir/remote``
        """
        if remote.startswith("/"):
            return remote
        return self.config.remote_base_dir.rstrip("/") + "/" + remote

    def _build_backend(self) -> _BaseBackend:
        """Instancie un nouveau backend (nouvelle connexion) à chaque appel."""
        if self.config.protocol == Protocol.SFTP:
            return _SFTPBackend(self.config)
        return _FTPBackend(self.config)

    def _scan_remote_parallel(self, remote_dir: str, max_workers: int) -> dict[str, Optional[float]]:
        """
        Parcourt récursivement ``remote_dir`` sur le serveur distant EN
        PARALLÈLE et retourne ``{chemin relatif : mtime}``.

        Sur SSH/SFTP, chaque ``listdir_attr()`` attend l'aller-retour réseau
        complet avant le suivant : avec une seule connexion, un parcours
        récursif séquentiel coûte donc ``(nb de répertoires) × latence``,
        ce qui domine largement dès que l'arborescence est large ou
        profonde — indépendamment du nombre de fichiers.

        Ici, plusieurs connexions sont ouvertes (comme pour les uploads) et
        se partagent les répertoires à lister via un pool de threads, en
        largeur d'abord (BFS) : chaque connexion reste ouverte et sert pour
        plusieurs répertoires successifs (pas de nouvelle poignée de main
        SSH par répertoire), et plusieurs répertoires sont listés en même
        temps au lieu d'attendre chacun son tour.
        """
        result: dict[str, Optional[float]] = {}
        result_lock = threading.Lock()
        thread_local = threading.local()
        connections: list[_BaseBackend] = []
        connections_lock = threading.Lock()

        def get_backend() -> _BaseBackend:
            backend = getattr(thread_local, "backend", None)
            if backend is None:
                backend = self._build_backend()
                backend.connect()
                thread_local.backend = backend
                with connections_lock:
                    connections.append(backend)
            return backend

        def list_one(remote_path: str, prefix: str) -> list[tuple[str, str]]:
            """Liste UN répertoire, enregistre ses fichiers, retourne ses sous-répertoires à explorer."""
            backend = get_backend()
            subdirs: list[tuple[str, str]] = []
            try:
                entries = backend.list_dir_entries(remote_path)
            except Exception as exc:
                logger.warning("[SCAN] échec listing %s : %s", remote_path, exc)
                return subdirs
            for name, is_dir, mtime in entries:
                rel = prefix + name
                full = remote_path.rstrip("/") + "/" + name
                if is_dir:
                    subdirs.append((full, rel + "/"))
                else:
                    with result_lock:
                        result[rel] = mtime
            return subdirs

        workers = max(1, max_workers)
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending = {pool.submit(list_one, remote_dir, "")}
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        for full, prefix in future.result():
                            pending.add(pool.submit(list_one, full, prefix))
        finally:
            for backend in connections:
                try:
                    backend.disconnect()
                except Exception:
                    pass

        return result

    def _ensure_remote_dirs_parallel(
        self, dirs_needed: set[str], remote_root: str, max_workers: int
    ) -> None:
        """
        Pré-crée tous les répertoires distants nécessaires, en parallèle et
        sans redondance.

        L'ancienne approche appelait ``makedirs()`` (qui revérifie toute la
        chaîne d'ancêtres depuis la racine) une fois par répertoire
        FEUILLE, sur UNE seule connexion : avec des milliers de
        répertoires partageant des préfixes communs, ça se traduit par des
        dizaines de milliers d'allers-retours redondants, tous sérialisés
        — le principal facteur observé de blocage avant même le début des
        transferts.

        Ici, :func:`_expand_dir_closure` calcule d'abord la fermeture
        complète (chaque ancêtre une seule fois, quel que soit le nombre
        de répertoires qui le partagent) regroupée par palier de
        profondeur, puis chaque palier est créé en parallèle sur
        plusieurs connexions via :meth:`_BaseBackend.mkdir_leaf` (un seul
        segment, pas de revérification des ancêtres) — le palier suivant
        ne démarre qu'une fois le précédent terminé, garantissant que les
        parents existent avant les enfants.
        """
        levels = _expand_dir_closure(dirs_needed, remote_root)

        # La racine elle-même (remote_root) n'est jamais incluse dans la
        # fermeture (on ne veut pas la recréer/revérifier à chaque palier),
        # donc on la garantit à part, une seule fois, sur une connexion
        # dédiée : c'est le seul endroit où l'ancienne chaîne complète
        # d'ancêtres (makedirs) reste nécessaire.
        try:
            with self._build_backend() as probe:
                probe.makedirs(remote_root)
        except Exception as exc:
            raise RuntimeError(f"racine {remote_root!r} : {exc}") from exc

        if not levels:
            return

        thread_local = threading.local()
        connections: list[_BaseBackend] = []
        connections_lock = threading.Lock()

        def get_backend() -> _BaseBackend:
            backend = getattr(thread_local, "backend", None)
            if backend is None:
                backend = self._build_backend()
                backend.connect()
                thread_local.backend = backend
                with connections_lock:
                    connections.append(backend)
            return backend

        def create_one(d: str) -> Optional[str]:
            try:
                get_backend().mkdir_leaf(d)
                return None
            except Exception as exc:
                return f"{d}: {exc}"

        errors: list[str] = []
        workers = max(1, max_workers)
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for level_dirs in levels:  # paliers dans l'ordre croissant de profondeur
                    for err in pool.map(create_one, sorted(level_dirs)):
                        if err:
                            errors.append(err)
        finally:
            for backend in connections:
                try:
                    backend.disconnect()
                except Exception:
                    pass

        if errors:
            shown = "; ".join(errors[:5])
            more = f" (+{len(errors) - 5} autres)" if len(errors) > 5 else ""
            raise RuntimeError(f"{len(errors)} répertoire(s) en échec : {shown}{more}")

    def _sync_single(
        self,
        backend: _BaseBackend,
        local: Path,
        remote: str,
        result: SyncResult,
        lock: Optional[threading.Lock] = None,
    ) -> None:
        """Décide d'uploader ou de sauter un fichier, met à jour result.

        Peut être appelé depuis un thread (passer lock) ou en mode séquentiel.
        """
        def _append(lst: list, value: str) -> None:
            if lock:
                with lock:
                    lst.append(value)
            else:
                lst.append(value)

        remote_mtime = backend.remote_mtime(remote)
        local_mtime = local.stat().st_mtime

        if remote_mtime is not None and local_mtime <= remote_mtime:
            _append(result.skipped, remote)
            logger.debug("[SKIP]   %s (distant plus récent ou identique)", remote)
            return

        action = "[DRY-RUN]" if self.config.dry_run else "[UPLOAD]"
        logger.info("%s %s → %s", action, local, remote)

        if not self.config.dry_run:
            try:
                backend.upload_file(local, remote)
                _append(result.uploaded, remote)
            except Exception as exc:
                msg = f"{remote}: {exc}"
                _append(result.errors, msg)
                logger.error("[ERROR]  %s", msg)
        else:
            _append(result.uploaded, remote)
