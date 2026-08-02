# -*- encoding: utf-8 -*-
"""
Mesh CLI commands
------------------

`mesh-sync` synchronise ce serveur avec tous les pairs du mesh (bootstrap
+ pairs découverts au fil des synchros précédentes). Pensé pour être
appelé périodiquement (timer systemd, cron...), pas pour tourner en
tâche de fond dans le process Flask.
"""
from __future__ import annotations

import os
import sys

import click

from . import parser_makefile, cli, get_app
from ..mesh.registry import PeerRegistry
from ..mesh.translation_memory import TranslationMemory


def _build_registry(app, builddir):
    cfg = app.config
    return PeerRegistry(
        self_id=cfg.osint_mesh_peer_id,
        self_url=cfg.osint_mesh_self_url,
        lang=cfg.osint_mesh_lang or getattr(cfg, 'osint_text_translate', None),
        xapian_dir=os.path.join(builddir, 'xapian'),
        keywords_limit=cfg.osint_mesh_keywords_limit,
        keywords_min_length=cfg.osint_mesh_keywords_min_length,
        entities_limit=getattr(cfg, 'osint_mesh_entities_limit', 500),
        secret=cfg.osint_mesh_secret,
        timeout=cfg.osint_mesh_sync_timeout,
        translate_keywords=getattr(cfg, 'osint_mesh_keywords_translate', True),
        translation_memory=TranslationMemory(getattr(cfg, 'osint_mesh_translation_memory', '') or None),
    )


@cli.command(name='mesh-sync')
@click.pass_obj
def mesh_sync(common):
    """Synchronise ce serveur avec tous les pairs du mesh.

    IMPORTANT : cette commande construit son propre PeerRegistry, dans ce
    process CLI éphémère -- elle NE met PAS à jour le registre utilisé
    par l'app Flask en cours d'exécution (qui a le sien, mis en cache par
    requête). Pour rafraîchir CELUI qui sert vraiment les recherches
    mesh, il faut appeler `POST /mesh/v1/admin/sync` sur l'app elle-même
    (cf. INTEGRATION.md, section timer systemd). Cette commande reste
    utile pour du debug/test en ligne de commande (vérifier que le
    bootstrap est joignable, voir `mesh-search` fonctionner sans
    dépendre de l'app Flask), mais ce n'est plus, depuis l'ajout de
    `/mesh/v1/admin/sync`, le mécanisme de rafraîchissement en production.

    Repart du bootstrap à chaque exécution : ce process CLI est
    volontairement sans état persistant entre deux runs -- les pairs
    "appris" pendant un sync (peers-of-peers) ne survivent que le temps
    de ce run-là. Si le mesh grossit ça vaudra le coup de persister le
    carnet quelque part, mais pas la peine tant que le bootstrap reste la
    source de vérité principale.

    Code de sortie 0 si tous les pairs ont répondu, 1 si au moins un a
    échoué (pratique pour qu'un timer systemd/un monitoring externe
    détecte les échecs sans avoir à parser la sortie), 2 si le mesh n'est
    pas configuré.
    """
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_mesh_enabled is False:
        print('Plugin mesh is not enabled')
        sys.exit(2)

    if not app.config.osint_mesh_bootstrap:
        print('osint_mesh_bootstrap is not configured')
        sys.exit(2)

    registry = _build_registry(app, builddir)
    registry.load_bootstrap(app.config.osint_mesh_bootstrap)

    if not registry.known_peers():
        print('No peer in bootstrap, nothing to sync')
        return

    results = registry.sync_all()

    for peer_id, ok in results.items():
        print(f"{peer_id}: {'OK' if ok else 'FAILED'}")

    failed = [peer_id for peer_id, ok in results.items() if not ok]
    if failed:
        print(f'{len(failed)}/{len(results)} peer(s) failed: {", ".join(failed)}')
        sys.exit(1)

    print(f'{len(results)} peer(s) synced successfully')


@cli.command(name='mesh-keywords')
@click.option('--force/--no-force', default=False, help="Force la ré-extraction, en ignorant le cache")
@click.pass_obj
def mesh_keywords(common, force):
    """Affiche les mots-clés que ce serveur publie sur /mesh/v1/keywords.

    Utile pour vérifier localement ce que le serveur va exposer au mesh
    avant de le laisser tourner en prod, sans attendre qu'un pair
    l'interroge pour de vrai.
    """
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_mesh_enabled is False:
        print('Plugin mesh is not enabled')
        sys.exit(2)

    registry = _build_registry(app, builddir)
    keywords, generated_at = registry.local_keywords(force=force)
    entities, entities_generated_at = registry.local_entities(force=force)

    print(f'{len(keywords)} keyword(s) (translated to {registry.PIVOT_LANG}), generated_at={generated_at}')
    for kw in keywords:
        print(f'  {kw}')

    print(f'{len(entities)} canonical entity label(s) (not translated), generated_at={entities_generated_at}')
    for entity in entities:
        print(f'  {entity}')


@cli.command(name='mesh-search')
@click.argument('query')
@click.option('--mode', type=click.Choice(['fast', 'deep']), default='fast',
              help="'fast': pairs dont les mots-clés recoupent la requête. 'deep': tous les pairs connus.")
@click.option('--limit', default=10, help="Résultats max par pair")
@click.option('--total-limit', default=20, help="Résultats max au total, après fusion")
@click.option('--aggregation', type=click.Choice(['minmax', 'rank']), default='minmax')
@click.pass_obj
def mesh_search_cmd(common, query, mode, limit, total_limit, aggregation):
    """Recherche dans le mesh (soi-même + pairs sélectionnés par --mode).

    Synchronise ses propres pairs (via son propre PeerRegistry jetable,
    indépendant de celui de l'app Flask -- cf. note dans `mesh-sync`)
    avant de chercher, pour que le mode 'fast' ait des mots-clés/entités
    à jour pour sélectionner qui interroger. Ça rend chaque appel plus
    lent qu'une vraie recherche interactive (traductions comprises) --
    normal pour un outil de debug en ligne de commande, pas pensé pour
    être l'interface de recherche réelle des utilisateurs (ça, c'est le
    rôle de l'app Flask, avec son registre tenu à jour par
    `/mesh/v1/admin/sync`, cf. INTEGRATION.md).
    """
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_mesh_enabled is False:
        print('Plugin mesh is not enabled')
        sys.exit(2)

    if not app.config.osint_mesh_bootstrap:
        print('osint_mesh_bootstrap is not configured')
        sys.exit(2)

    registry = _build_registry(app, builddir)
    registry.load_bootstrap(app.config.osint_mesh_bootstrap)
    # il faut les mots-clés/entités des pairs pour que le mode 'fast'
    # puisse sélectionner qui interroger -- une seule passe de sync ici,
    # pas la peine de la répéter (cf. mesh-sync pour un rafraîchissement
    # planifié séparément).
    registry.sync_all()

    results = registry.mesh_search(
        query, mode=mode, limit_per_peer=limit,
        total_limit=total_limit, aggregation_method=aggregation,
    )

    if not results:
        print('No results')
        return

    for result in results:
        peer_id = result.get('peer_id', '?')
        score = result.get('normalized_score', 0)
        title = result.get('title', '(no title)')
        url = result.get('url', '')
        print(f'[{peer_id}] ({score:.2f}) {title}')
        if url:
            print(f'    {url}')
@click.argument('term')
@click.argument('translation')
@click.option('--lang', default=None, help="Langue source (défaut: osint_mesh_lang / osint_text_translate)")
@click.pass_obj
def mesh_translation_set(common, term, translation, lang):
    """Corrige/force manuellement une entrée de la mémoire de traduction.

    Exemple : une traduction bancale repérée dans `mesh-keywords` --

        <CLI_ENTRYPOINT> mesh-translation-set guerre war

    L'entrée est écrite immédiatement sur disque (osint_mesh_translation_memory)
    et ne sera plus jamais renvoyée au traducteur externe pour ce terme.
    """
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)
    cfg = app.config

    memory_path = getattr(cfg, 'osint_mesh_translation_memory', '')
    if not memory_path:
        print('osint_mesh_translation_memory is not configured')
        sys.exit(2)

    src_lang = lang or cfg.osint_mesh_lang or getattr(cfg, 'osint_text_translate', None)
    if not src_lang:
        print('No source language configured (--lang, osint_mesh_lang or osint_text_translate)')
        sys.exit(2)

    memory = TranslationMemory(memory_path)
    memory.set(src_lang, term.strip().lower(), translation.strip().lower())
    print(f'[{src_lang}] {term} -> {translation} (saved to {memory_path})')
