# -*- encoding: utf-8 -*-
"""
The bsky scripts
------------------------


"""
from __future__ import annotations
import os
import sys
import json
import click

from ..plugins import collect_plugins

from ..osintlib import OSIntQuest

from . import parser_makefile, cli, get_app, load_quest

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

osint_plugins = collect_plugins()

if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)


def _print_diff(diff):
    """Pretty-print the dict returned by OSIntBSkyProfile.update()

    update() returns the flat diff for *this* run only (e.g.
    {'followers_count': 812, 'posts_count': 143, ...}), not the full
    timestamp-keyed history stored in the account's json file.
    """
    print("\n=== Changements detectes ===")
    if not diff:
        print("  (aucun changement)")
        return
    for key, value in diff.items():
        print(f"  - {key}: {value}")


def _print_analyse(analyse):
    """Pretty-print the dict returned by OSIntBSkyProfile.analyse()"""
    print("\n=== Analyse IA / orthographe ===")
    if not analyse:
        print("  (rien a analyser)")
        return
    print(f"  Posts analyses         : {analyse['posts_analysed']}")
    ai = analyse['ai_generated']
    print(f"  Textes scores par l'IA : {ai['posts_scored']}")
    for label, count in sorted(ai['label_counts'].items(), key=lambda kv: kv[1], reverse=True):
        print(f"      - {label}: {count}")
    spelling = analyse['spelling']
    print(f"  Fautes d'orthographe   : {spelling['total_errors']} "
          f"(sur {spelling['posts_with_errors']} posts concernes)")
    rt = analyse['response_time']
    if rt['posts_with_reply_timing']:
        print(f"  Temps de reponse moyen : {rt['average_seconds']:.1f}s "
              f"({rt['posts_with_reply_timing']} reponses)")


def _print_top_words(top_words):
    """Pretty-print the list of (word, count) returned by OSIntBSkyProfile.word_frequency()"""
    print(f"\n=== {len(top_words)} mots les plus frequents ===")
    if not top_words:
        print("  (aucun mot trouve)")
        return
    width = max(len(word) for word, _ in top_words)
    for word, count in top_words:
        print(f"  {word.ljust(width)}  {count}")

@cli.command()
@click.argument('username', default=None)
@click.pass_obj
def did(common, username):
    """Get did from profile url"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    from ..plugins.bskylib import OSIntBSkyProfile

    data = OSIntBSkyProfile.get_profile(
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        url=f"https://bsky.app/profile/{username}")

    print("DID : ", data.did)
    print(data)

@cli.command()
@click.argument('did', default=None)
@click.option('--feed-filter', default='posts_with_replies',
    type=click.Choice(['posts_with_replies', 'posts_no_replies', 'posts_with_media', 'posts_and_author_threads']),
    help="Which posts to fetch: posts_with_replies (default, includes the account's own replies) or posts_no_replies to skip them")
@click.option('--top-words', default=20, type=int, help="How many of the most frequent words to display (0 to disable)")
@click.pass_obj
def profile(common, did, feed_filter, top_words):
    """Import/update profile in store"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    from ..plugins.bskylib import OSIntBSkyProfile

    data = load_quest(builddir)

    did = OSIntBSkyProfile.normalize_did(did)

    store = os.path.join(common.docdir, app.config.osint_bsky_store)
    cache = os.path.join(common.docdir, app.config.osint_bsky_cache)

    profile = OSIntBSkyProfile(did,did, quest=data)
    diff = profile.update(
        did=did,
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        osint_bsky_store=store,
        osint_bsky_cache=cache,
        feed_filter=feed_filter)
    analyse = profile.analyse(
        did=did,
        osint_bsky_store=store,
        osint_bsky_cache=cache,
        osint_text_translate=app.config.osint_text_translate,
        osint_bsky_ai=app.config.osint_bsky_ai,
        )

    print(f"\nCompte : {did}")
    _print_diff(diff)
    _print_analyse(analyse)
    if top_words > 0:
        words = profile.word_frequency(did=did, osint_bsky_store=store, osint_bsky_cache=cache, top_words=top_words)
        _print_top_words(words)

@cli.command()
@click.argument('did', default=None)
@click.option('--top-words', default=None, type=int, help="How many of the most frequent words/hashtags/mentions/entities to keep")
@click.option('--swearword', 'swearwords', multiple=True, help="Extra swearword to detect (repeatable)")
@click.option('--entities/--no-entities', default=True, help="Run named-entity extraction (slower on large accounts)")
@click.option('--rhythm/--no-rhythm', default=True, help="Compute the posting-rhythm histograms")
@click.option('--toxicity/--no-toxicity', default=True, help="Run the huggingface toxicity classifier (slow, downloads a model on first use)")
@click.option('--toxicity-threshold', default=None, type=float, help="Score (0-1) above which a post is flagged as toxic")
@click.option('--network/--no-network', default=True, help="Compute followers/follows ratio history, suspicious growth and common network with other tracked accounts")
@click.pass_obj
def analyse_account(common, did, top_words, swearwords, entities, rhythm, toxicity, toxicity_threshold, network):
    """Analyse the mood, insults and word frequency of an account.

    Reads the feed already collected by the 'profile' command (osint_bscript
    profile <did>) and prints a report: average mood ('humeur'), insults
    found (word list + a huggingface toxicity classifier), most frequent
    words/hashtags/mentions, named entities, an AI-generated ratio (if
    'profile' was run with osint_bsky_ai enabled), the posting rhythm, and
    the followers/follows network (ratio evolution, suspicious growth,
    accounts sharing followers/follows with other bsky profiles already
    tracked in this project).
    """
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    from ..plugins.bskylib import OSIntBSkyProfile

    data = load_quest(builddir)

    did = OSIntBSkyProfile.normalize_did(did)

    profile = OSIntBSkyProfile(did, did, quest=data)
    analysis = profile.analyse_account(
        did=did,
        osint_bsky_store=os.path.join(common.docdir, app.config.osint_bsky_store),
        osint_bsky_cache=os.path.join(common.docdir, app.config.osint_bsky_cache),
        osint_bsky_swearwords=list(swearwords) or None,
        top_words=top_words,
        include_entities=entities,
        include_rhythm=rhythm,
        include_toxicity=toxicity,
        osint_bsky_toxicity_threshold=toxicity_threshold,
        include_network=network,
        quest=data if network else None)

    print(json.dumps(analysis, indent=2, cls=OSIntBSkyProfile.JSONEncoder))


@cli.command()
@click.argument('story', default=None)
@click.option('--dryrun/--no-dryrun', default=True, help="Run in dry mode (not publish but test)")
@click.pass_obj
def story(common, story, dryrun):
    """Publish a story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    from ..plugins.bskylib import OSIntBSkyStory

    data = load_quest(builddir)

    if app.config.osint_bsky_user is None or app.config.osint_bsky_apikey is None:
        print('No user or apikey for bsky defined in conf')
        sys.exit(1)

    bstree = data.bskystories[f"{OSIntBSkyStory.prefix}.{story}"].publish(
        reply_to=None,
        env=app.env,
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        tree=True,
        dryrun=dryrun)
    print(json.dumps(bstree, indent=2, cls=OSIntBSkyStory.JSONEncoder))


@cli.command()
@click.argument('story', default=None)
@click.option('--img', help="URL of the imaage to use")
@click.option('--title', help="The title to use")
@click.option('--desc', help="Description to use")
@click.pass_obj
def story_og(common, story, img, title, desc):
    """Create og data for a story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    import base64
    import json
    from ..plugins.bskylib import OSIntBSkyStory
    from .. import OsintFutureRole, get_external_src_data

    data = load_quest(builddir)

    bskystory = data.bskystories[f"{OSIntBSkyStory.prefix}.{story}"]

    role = OsintFutureRole(app.env, bskystory.embed_url, bskystory.embed_url, None)
    display_text, url = get_external_src_data(app.env, role)

    path = bskystory.json_file(url)
    with open(path, 'r') as f:
         data = json.load(f)

    if img is not None:
        import base64
        import httpx

        img_data = httpx.get(img).content
        data['img'] = base64.b64encode(img_data).decode()

    if title is not None:
        data['title'] = title

    if desc is not None:
        data['description'] = desc

    with open(path, 'w') as f:
         json.dump(data, f, indent=2)


@cli.command()
@click.argument('story', default=None)
@click.pass_obj
def story_stats(common, story):
    """Get shortener stats for a story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    from ..plugins.bskylib import OSIntBSkyStory

    data = load_quest(builddir)

    if app.config.osint_bsky_user is None or app.config.osint_bsky_apikey is None:
        print('No user or apikey for bsky defined in conf')
        sys.exit(1)

    bstree = data.bskystories[f"{OSIntBSkyStory.prefix}.{story}"].short_stats()
    print(json.dumps(bstree, indent=2, cls=OSIntBSkyStory.JSONEncoder))
