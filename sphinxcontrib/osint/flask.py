# -*- encoding: utf-8 -*-
"""
The flask lib
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import hmac
from pathlib import Path
import json
import re
import html
from flask import Flask, render_template, request, send_from_directory, abort
from flask_babel import Babel
from flask_caching import Cache
from jinja2 import ChoiceLoader, FileSystemLoader
import sphinx
from sphinx.builders.html._assets import (
    _CascadingStyleSheet,
    _JavaScript,
)
import pycountry

from .osintlib import OSIntQuest, OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource, OSIntCountry
from .xapianlib import XapianIndexer
from .plugins import collect_plugins
from .flask_chat_routes import chat_bp

osint_plugins = collect_plugins()

if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)


ALLOWED_EXTENSIONS = {'html', 'htm'}

class CascadingTemplateLoader:
    """Gestionnaire de templates en cascade depuis plusieurs répertoires."""

    def __init__(self, template_dirs):
        """
        Args:
            template_dirs: Liste de répertoires ordonnés par priorité (le premier a la priorité)
        """
        template_dirs.insert(1, os.path.join(os.path.dirname(sphinx.__file__), 'themes'))
        # ~ template_dirs.reverse()
        self.template_dirs = template_dirs + [os.path.join(os.path.dirname(__file__), '_templates')]

    def get_loader(self):
        """Crée un ChoiceLoader pour Jinja2."""
        loaders = [FileSystemLoader(d) for d in self.template_dirs if os.path.exists(d)]
        return ChoiceLoader(loaders)

def pathto(
    otheruri: str,
    resource: bool = False,
    baseuri: str = '',
) -> str:
    # ~ print(otheruri, resource, baseuri)
    # ~ if resource is True:
        # ~ return '/' + otheruri
    return '/' + otheruri

def hasdoc(name: str) -> bool:
    return True

def css_tag(css: _CascadingStyleSheet) -> str:
    attrs = [
        f'{key}="{html.escape(value, quote=True)}"'
        for key, value in css.attributes.items()
        if value is not None
    ]
    uri = pathto(os.fspath(css.filename), resource=True)
    return f'<link {" ".join(sorted(attrs))} href="{uri}" />'

def js_tag(js: _JavaScript | str) -> str:
    if not isinstance(js, _JavaScript):
        # str value (old styled)
        return f'<script src="{pathto(js, resource=True)}"></script>'

    body = js.attributes.get('body', '')
    attrs = [
        f'{key}="{html.escape(value, quote=True)}"'
        for key, value in js.attributes.items()
        if key != 'body' and value is not None
    ]

    if not js.filename:
        if attrs:
            return f'<script {" ".join(sorted(attrs))}>{body}</script>'
        return f'<script>{body}</script>'

    js_filename_str = os.fspath(js.filename)
    uri = pathto(js_filename_str, resource=True)
    if 'MathJax.js?' in js_filename_str:
        pass
    if attrs:
        return f'<script {" ".join(sorted(attrs))} src="{uri}"></script>'
    return f'<script src="{uri}"></script>'

# ~ def highlight_filter(text, query):
    # ~ """Surligne les termes de recherche dans le texte"""
    # ~ if not query:
        # ~ return text
    # ~ terms = query.split()
    # ~ for term in terms:
        # ~ text = text.replace(term, f'<mark>{term}</mark>')
    # ~ return text

def highlight_filter(text, query):
    if not query:
        return text
    terms = [re.escape(t) for t in query.split()]
    pattern = re.compile('|'.join(terms), re.IGNORECASE)
    return pattern.sub(lambda m: f'<mark>{m.group()}</mark>', text)

app = Flask(__name__)
app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(os.path.dirname(sphinx.__file__), 'locale')
app.config['CACHE_TYPE'] = "SimpleCache"
app.config['CACHE_DEFAULT_TIMEOUT'] = 60
app.jinja_env.autoescape = False
babel = Babel(app)
cache = Cache(app)
app.register_blueprint(chat_bp)
app.jinja_env.filters['tobool'] = sphinx.jinja2glue._tobool
app.jinja_env.filters['toint'] = sphinx.jinja2glue._toint
app.jinja_env.filters['slice_index'] = sphinx.jinja2glue._slice_index
app.jinja_env.filters['warning'] = sphinx.jinja2glue.warning
app.jinja_env.filters['idgen'] = sphinx.jinja2glue.idgen
app.jinja_env.filters['accesskey'] = sphinx.jinja2glue.accesskey
app.jinja_env.filters['highlight'] = highlight_filter

ctx = {}
ctx["pathto"] = pathto
ctx["hasdoc"] = hasdoc
ctx['accesskey'] = sphinx.jinja2glue.accesskey
ctx['css_tag'] = css_tag
ctx['js_tag'] = js_tag
ctx['js_tag'] = js_tag

# ~ def globalctx(myapp):
    # ~ ret = myapp.config['SPHINX'].builder.globalcontext
    # ~ ret['favicon_url'] = '/_static/favicon.png'
    # ~ return ret
def globalctx(myapp):
    base = dict(myapp.config['SPHINX'].builder.globalcontext)  # copie
    base['favicon_url'] = '/_static/favicon.png'
    return base

indexer = None
def init_xapian(directory, sphinx_app):
    # ~ print(directory)
    if sphinx_app.config.osint_text_translate is None:
        language = None
    else:
        language = pycountry.languages.get(alpha_2=sphinx_app.config.osint_text_translate)
    global indexer
    indexer = XapianIndexer(directory, language=language.name)

# Jeton pour l'endpoint /admin/reload ci-dessous, à définir via la
# variable d'environnement OSINT_ADMIN_TOKEN. Si elle n'est pas définie,
# l'endpoint est désactivé (404) plutôt que laissé ouvert sans
# protection par défaut.
ADMIN_TOKEN = os.environ.get('OSINT_ADMIN_TOKEN')

@app.route('/admin/reload', methods=['POST'])
def admin_reload():
    """Invalide les caches HTTP (résultats de recherche, facettes, listes
    d'idents...) et force une reconnexion immédiate à l'index Xapian.

    À appeler après avoir poussé une nouvelle base Xapian (par ex. par
    SSH) pour la rendre visible tout de suite plutôt que d'attendre
    l'expiration naturelle des caches (jusqu'à 600s selon les routes).

    Ne recharge PAS l'objet Quest en mémoire (app.config['QUEST']): ça
    nécessiterait de refaire tourner le build Sphinx, une opération bien
    plus lourde qu'une simple invalidation de cache — hors de portée de
    cet endpoint. Les libellés dérivés de la Quest (ex: nom des pays
    dans les filtres) peuvent donc rester périmés pour de nouvelles
    entités tant que le process n'est pas redémarré, même si les
    résultats de recherche eux-mêmes (issus de Xapian) sont à jour.

    Protégé par un jeton (en-tête `X-Admin-Token` ou paramètre `token`)
    à faire correspondre à la variable d'environnement OSINT_ADMIN_TOKEN.
    """
    if not ADMIN_TOKEN:
        abort(404)

    supplied = request.headers.get('X-Admin-Token') or request.args.get('token', '')
    if not supplied or not hmac.compare_digest(supplied, ADMIN_TOKEN):
        abort(403)

    cache.clear()

    reopened = False
    if indexer is not None:
        try:
            indexer._get_read_db()
            reopened = True
        except Exception:
            app.logger.exception("Error reopening the Xapian index on /admin/reload")

    return {'status': 'ok', 'cache_cleared': True, 'index_reopened': reopened}

def allowed_file(filename):
    # ~ return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    return True

@cache.memoize(timeout=600)
def get_available_cats():
    """Catégories disponibles pour les filtres de recherche, dérivées des
    termes Xapian plutôt que d'un parcours de toute la quête en mémoire.
    Mis en cache indépendamment de la requête de recherche (contrairement
    au cache posé sur la route elle-même): ça ne change qu'au réindexage,
    pas d'une recherche à l'autre."""
    return indexer.get_facet_terms(indexer.PREFIX_CATS)

@cache.memoize(timeout=600)
def get_available_countries():
    """Pays disponibles pour les filtres de recherche: les codes viennent
    des termes Xapian (source de vérité de ce qui est réellement
    filtrable), le libellé affiché est résolu depuis la quête. Mis en
    cache comme get_available_cats()."""
    result = []
    for code in indexer.get_facet_terms(indexer.PREFIX_COUNTRY):
        key = OSIntCountry.prefix + '.' + code
        try:
            label = app.config['QUEST'].countries[key].slabel
        except KeyError:
            label = code
        result.append((code, label))
    return result

_writing_prepared = False

def ensure_writing_prepared():
    global _writing_prepared
    if not _writing_prepared:
        app.config['SPHINX'].builder.prepare_writing([])
        _writing_prepared = True

def _cache_only_success(rv):
    """Filtre de cache pour searchadv(): Flask-Caching passe ici la valeur
    de retour brute de la vue (avant que Flask ne la transforme en objet
    Response), donc soit une chaîne (rendu direct, statut 200 implicite),
    soit un tuple (corps, statut[, headers]) comme celui qu'on renvoie
    dans la branche d'erreur (`..., 500`). Pas de `.status_code` ici."""
    if isinstance(rv, tuple):
        status = rv[1] if len(rv) > 1 else 200
        return status == 200
    return True

@app.route('/')
def index():
    """Page d'accueil avec liste des fichiers HTML"""
    # ~ app.logger.error(app.config['UPLOAD_FOLDER'] + 'index.html')
    # ~ print(app.config['UPLOAD_FOLDER'] + 'index.html', file=sys.stderr)
    return send_from_directory(app.config['UPLOAD_HTML'], 'index.html')

@app.route('/searchadv.html')
@cache.cached(timeout=120, query_string=True, response_filter=_cache_only_success)
def searchadv():
    args = request.args.to_dict(flat=False)
    # ~ print(args)
    if 'q' in args:
        query = args['q'][0]
    else:
        query = None

    if 'reset' in args:
        reset = True
    else:
        reset = False

    # Fuzzy off par défaut (comme le CLI désormais): la correction
    # orthographique/synonymes natifs de Xapian couvrent déjà la plupart
    # des cas de fautes de frappe à moindre coût. Le rerank RapidFuzz
    # reste disponible en opt-in via la case à cocher du formulaire.
    use_fuzzy = 'f' in args and not reset
    ffuzzy = [('1', 1 if use_fuzzy else 0)]

    if 's' in args and args['s'][0] in ('oldest', 'newest') and not reset:
        sort = args['s'][0]
    else:
        sort = 'relevance'
    fsort = [
        ('relevance', 1 if sort == 'relevance' else 0),
        ('oldest', 1 if sort == 'oldest' else 0),
        ('newest', 1 if sort == 'newest' else 0),
    ]

    ptypes = []
    if 'directive' in osint_plugins:
        for plg in osint_plugins['directive']:
            pdata = plg.xapiansearch()
            if pdata is not None:
                ptypes.append(pdata['types'])
    if 't' in args:
        types = args['t']
    else:
        types = None
    ftypes = []
    for ftyp in ['countries', 'cities', OSIntOrg.prefix+'s', OSIntIdent.prefix+'s', OSIntEvent.prefix+'s', OSIntSource.prefix+'s'] + ptypes:
        if types is None or ftyp not in types or reset:
            ftypes.append((ftyp, 0))
        else:
            ftypes.append((ftyp, 1))

    if 'o' in args:
        operators = args['o']
    else:
        operators = ['OR']
    foperators = []
    for fop in ['OR', 'AND']:
        if operators is None or fop not in operators:
            foperators.append((fop, 0))
        else:
            foperators.append((fop, 1))

    if 'c' in args:
        countries = args['c']
    else:
        countries = None
    fcountries = []
    for fcoun, flabel in get_available_countries():
        if countries is None or fcoun not in countries or reset:
            fcountries.append((fcoun, flabel, 0))
        else:
            fcountries.append((fcoun, flabel, 1))

    if 'a' in args:
        cats = args['a']
    else:
        cats = None
    dcats = get_available_cats()
    fcats = []

    for fcat in dcats:
        if cats is None or fcat not in cats or reset:
            fcats.append((fcat, 0))
        else:
            fcats.append((fcat, 1))

    ensure_writing_prepared()
    # ~ app.config['SPHINX'].builder.prepare_writing([])

    if ((query is None or query == "") and types is None and countries is None and cats is None) or reset:
        return render_template('searchadv.html',
            # ~ error="Type your search",
            results=None,
            ftypes=ftypes,
            fcountries=fcountries,
            fcats=fcats,
            foperators=foperators,
            ffuzzy=ffuzzy,
            fsort=fsort,
            **ctx,
            **globalctx(app))

    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page

    try:
        if query is not None and query != "":
            results = indexer.search(query, use_fuzzy=use_fuzzy, fuzzy_threshold=70,
                cats=cats, types=types, countries=countries,
                offset=offset, limit=per_page, op=operators[0],
                distance=200, load_json=True, highlighted='<span class="highlighted">%s</span>',
                sort=sort)
        else:
            results = app.config['QUEST'].search(
                cats=cats, types=types, countries=countries,
                offset=offset, limit=per_page,
                distance=200, load_json=True, sort=sort)

        # Remplace le code pays par son libellé pour l'affichage (le
        # code reste ce qui est indexé/filtré, seul l'affichage change).
        country_labels = dict(get_available_countries())
        for result in results['results']:
            if result.get('country'):
                result['country'] = country_labels.get(result['country'], result['country'])

        return render_template('searchadv.html',
            query=query,
            types=types,
            countries=countries,
            cats=cats,
            operators=operators,
            f=1 if use_fuzzy else None,
            s=sort,
            results=results,
            page=page,
            per_page=per_page,
            ftypes=ftypes,
            fcountries=fcountries,
            fcats=fcats,
            foperators=foperators,
            ffuzzy=ffuzzy,
            fsort=fsort,
            **ctx,
            **globalctx(app))
    except Exception as e:
        # Le crash original (ex: incompatibilité de version Xapian) ne
        # doit pas être aggravé par un second crash lors du rendu de la
        # page d'erreur elle-même: searchadv.html a besoin de tout le
        # contexte habituel (ftypes/fcountries/fcats/foperators, **ctx
        # pour 'pathto' etc.) pour s'afficher, pas seulement `error`. La
        # première version de ce bloc ne passait que `error`, ce qui
        # faisait planter le template (jinja2.exceptions.UndefinedError:
        # 'pathto' is undefined) et transformait une simple erreur de
        # recherche en crash en cascade côté serveur.
        app.logger.exception("Error in searchadv() while running the search")
        return render_template('searchadv.html',
            error=f"Erreur de recherche: {str(e)}",
            query=query,
            types=types,
            countries=countries,
            cats=cats,
            operators=operators,
            results=None,
            page=page,
            per_page=per_page,
            ftypes=ftypes,
            fcountries=fcountries,
            fcats=fcats,
            foperators=foperators,
            ffuzzy=ffuzzy,
            fsort=fsort,
            **ctx,
            **globalctx(app)), 500

@app.route('/idents')
@cache.cached(timeout=300)
def idents():
    """idents page"""
    temp = {}
    for idt in app.config['QUEST'].idents.items():
        for cat in idt[1].cats:
            if cat not in temp:
                temp[cat] = []
            if idt[1].label not in temp[cat]:
                temp[cat].append(idt)
    data = {}
    for k in sorted(temp.keys()):
        data[k] = sorted(temp[k], key=lambda d: d[1].label)

    ensure_writing_prepared()
    # ~ app.config['SPHINX'].builder.prepare_writing([])
    return render_template('idents.html',
            idents=data,
            **ctx,
            **globalctx(app))

@app.route('/ident/<name>')
@cache.cached(timeout=600)
def ident(name):
    """ident page"""
    # ~ print(ctx)
    # ~ idt = app.config['QUEST'].idents["ident.01net"]
    idt = app.config['QUEST'].idents[name]
    # ~ print(app.config['SPHINX'].config.osint_analyse_enabled)
    if app.config['SPHINX'].config.osint_analyse_enabled:
        idt_file = os.path.join(app.config['SPHINX'].outdir, 'html',app.config['SPHINX'].config.osint_analyse_report, f'{idt.name}.json')
        # ~ print(idt_file)
        if os.path.isfile(idt_file) is True:
            with open(idt_file, 'r') as f:
                idt_data = json.load(f)
        else:
            idt_data = {}
    else:
        idt_data = {}
    # ~ data = app.config['QUEST'].idents.items()
    ensure_writing_prepared()
    # ~ app.config['SPHINX'].builder.prepare_writing([])
    # ~ print(app.config['SPHINX'].builder.globalcontext)
    return render_template('ident.html',
            ident=idt,
            data=idt_data,
            **ctx,
            **globalctx(app))

# ~ @app.route('/<path:my_path>')
# ~ def catch_all(my_path):
    # ~ if '.' not in my_path:
        # ~ my_path += '.html'
    # ~ app.logger.error(app.config['UPLOAD_FOLDER'] + my_path)
    # ~ return send_from_directory(app.config['UPLOAD_HTML'], my_path)
@app.route('/<path:my_path>')
def catch_all(my_path):
    # Bloquer les paths qui ressemblent à des routes app
    if my_path.startswith('app/'):
        from flask import abort
        abort(404)
    if '.' not in my_path:
        my_path += '.html'
    return send_from_directory(app.config['UPLOAD_HTML'], my_path)

def add_quest_css(app):
    """
    """
    from sphinx.util import logging
    logger = logging.getLogger(__name__)

    ext_path = Path(__file__).parent / '_static'

    # NOTE: app.config.html_static_path can be mutated by other Sphinx
    # extensions before 'builder-inited' fires, and entry [0] is not
    # guaranteed to be our own relative '_static' dir. Path(app.srcdir) /
    # candidate silently discards app.srcdir if candidate is absolute,
    # which can point us at unrelated files inside an installed package
    # (e.g. .../sphinx/templates/graphviz/graphviz.css). Always fall back
    # to our own fixed dir name unless the configured value is a safe
    # relative path.
    static_dir = '_static'
    if hasattr(app.config, 'html_static_path') and app.config.html_static_path:
        candidate = app.config.html_static_path[0]
        if candidate and not Path(candidate).is_absolute():
            static_dir = candidate

    static_path = Path(app.srcdir) / static_dir

    css_file = 'quest.css'

    if (ext_path / css_file).exists() and not (static_path / css_file).exists():
        with open((ext_path / css_file), 'r', encoding='utf-8') as f:
            html_content = f.read()

        try:
            static_path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            # Another worker created it concurrently; harmless.
            pass

        sidebar_static = static_path / css_file
        try:
            with open(sidebar_static, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except FileExistsError:
            pass

        logger.info('CSS quest installed')

    app.add_css_file(css_file)


def add_quest_html(app):
    """
    """
    from sphinx.util import logging
    logger = logging.getLogger(__name__)

    ext_path = Path(__file__).parent / '_templates'

    # See add_quest_css() above: app.config.templates_path[0] is not
    # guaranteed to be our own relative '_templates' dir, and joining an
    # absolute candidate would silently discard app.srcdir.
    template_dir = '_templates'
    if hasattr(app.config, 'templates_path') and app.config.templates_path:
        candidate = app.config.templates_path[0]
        if candidate and not Path(candidate).is_absolute():
            template_dir = candidate

    templates_path = Path(app.srcdir) / template_dir

    html_file = 'questbox.html'

    if (ext_path / html_file).exists() and not (templates_path / html_file).exists():
        with open((ext_path / html_file), 'r', encoding='utf-8') as f:
            html_content = f.read()

        try:
            templates_path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass

        sidebar_template = templates_path / html_file
        try:
            with open(sidebar_template, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except FileExistsError:
            pass

        logger.info('Template sidebar installed')

    if app.config.osint_xapian_sidebar_enabled is True:

        if not hasattr(app.config, 'html_sidebars'):
            app.config.html_sidebars = {}

        if '**' not in app.config.html_sidebars:
            app.config.html_sidebars = {
                '**': ['localtoc.html', 'relations.html', 'sourcelink.html', 'searchbox.html']
            }

        if app.config.osint_jssearch_enabled is False and \
          'searchbox.html' in app.config.html_sidebars['**']:
            app.config.html_sidebars['**'].remove('searchbox.html')

        app.config.html_sidebars['**'].append(html_file)

    else:
        logger.info('osint_quest_sidebar disabled. Add it in conf.py')

def flask_app_config(app):
    """
    """
    app.add_config_value('secret_key', 'change-me', 'html')
    app.connect('builder-inited', add_quest_css)
    app.connect('builder-inited', add_quest_html)

def create_flask_app():
    from .scripts import parser_makefile, cli, get_app, load_quest, inject_quest_into_sphinx

    docdir = os.environ.get('OSINT_HOME', '/var/lib/osint')
    sourcedir, builddir = parser_makefile(docdir)
    sourcedir = os.path.join(docdir, sourcedir)
    builddir = os.path.join(docdir, builddir)

    sphinx_app = get_app(sourcedir=sourcedir, builddir=builddir)

    data = load_quest(os.path.realpath(builddir))
    inject_quest_into_sphinx(sphinx_app, data)

    app.secret_key = sphinx_app.config.secret_key
    app.config['SPHINX'] = sphinx_app
    app.config['QUEST'] = data
    app.config['UPLOAD_FOLDER'] = os.path.realpath(builddir)
    app.config['UPLOAD_HTML'] = os.path.join(os.path.realpath(builddir), 'html')
    app.config['UPLOAD_XAPIAN'] = os.path.join(os.path.realpath(builddir), 'xapian')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    cascade_loader = CascadingTemplateLoader(sphinx_app.builder.theme.get_theme_dirs())
    app.jinja_loader = cascade_loader.get_loader()

    xapian_dir = app.config['UPLOAD_XAPIAN']
    if os.path.isdir(xapian_dir):
        init_xapian(xapian_dir, sphinx_app)
    else:
        app.logger.warning("Xapian index not found, search disabled")

    return app
