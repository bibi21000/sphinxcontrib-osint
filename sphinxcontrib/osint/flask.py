# -*- encoding: utf-8 -*-
"""
The flask lib
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import html
from flask import Flask, render_template, request, send_from_directory
from flask_babel import Babel
from jinja2 import ChoiceLoader, FileSystemLoader
import sphinx
from sphinx.builders.html._assets import (
    _CascadingStyleSheet,
    _JavaScript,
)
import pycountry

from .osintlib import OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource, OSIntCountry
from .xapianlib import XapianIndexer

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
    return otheruri

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

def highlight_filter(text, query):
    """Surligne les termes de recherche dans le texte"""
    if not query:
        return text
    terms = query.split()
    for term in terms:
        text = text.replace(term, f'<mark>{term}</mark>')
    return text

app = Flask(__name__)
app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(os.path.dirname(sphinx.__file__), 'locale')
app.jinja_env.autoescape = False
babel = Babel(app)
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

indexer = None
def init_xapian(directory, sphinx_app):
    print(directory)
    if sphinx_app.config.osint_text_translate is None:
        language = None
    else:
        language = pycountry.languages.get(alpha_2=sphinx_app.config.osint_text_translate)
    global indexer
    indexer = XapianIndexer(directory, language=language.name)

def allowed_file(filename):
    # ~ return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    return True

@app.route('/')
def index():
    """Page d'accueil avec liste des fichiers HTML"""
    # ~ app.logger.error(app.config['UPLOAD_FOLDER'] + 'index.html')
    # ~ print(app.config['UPLOAD_FOLDER'] + 'index.html', file=sys.stderr)
    return send_from_directory(app.config['UPLOAD_HTML'], 'index.html')

@app.route('/searchadv.html')
def searchadv():
    args = request.args.to_dict(flat=False)
    print(args)
    if 'q' in args:
        query = args['q'][0]
    else:
        query = None

    if 'reset' in args:
        reset = True
    else:
        reset = False

    if 't' in args:
        types = args['t']
    else:
        types = None
    ftypes = []
    for ftyp in ['countries', 'cities', OSIntOrg.prefix+'s', OSIntIdent.prefix+'s', OSIntEvent.prefix+'s', OSIntSource.prefix+'s']:
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
    for fcoun in sorted(app.config['QUEST'].get_countries()):
        fcouns = fcoun.replace(OSIntCountry.prefix+'.', '')
        if countries is None or fcouns not in countries or reset:
            fcountries.append((fcouns, app.config['QUEST'].countries[fcoun].slabel, 0))
        else:
            fcountries.append((fcouns, app.config['QUEST'].countries[fcoun].slabel, 1))

    if 'a' in args:
        cats = args['a']
    else:
        cats = None
    dcats = []
    fcats = []
    dicts = app.config['QUEST'].get_data_dicts()
    for i in dicts:
        # ~ print(i)
        for k in i[1]:
            for c in i[1][k].cats:
                if c not in dcats:
                    dcats.append(c)
    dcats= sorted(dcats)

    for fcat in dcats:
        if cats is None or fcat not in cats or reset:
            fcats.append((fcat, 0))
        else:
            fcats.append((fcat, 1))

    app.config['SPHINX'].builder.prepare_writing([])

    if ((query is None or query == "") and types is None and countries is None and cats is None) or reset:
        return render_template('searchadv.html',
            # ~ error="Type your search",
            results=None,
            ftypes=ftypes,
            fcountries=fcountries,
            fcats=fcats,
            foperators=foperators,
            **ctx,
            **app.config['SPHINX'].builder.globalcontext)

    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page

    try:
        if query is not None and query != "":
            results = indexer.search(query, use_fuzzy=False, fuzzy_threshold=70,
                cats=cats, types=types, countries=countries,
                offset=offset, limit=per_page, op=operators[0],
                distance=200, load_json=True, highlighted='<span class="highlighted">%s</span>')
        else:
            results = app.config['QUEST'].search(
                cats=cats, types=types, countries=countries,
                offset=offset, limit=per_page,
                distance=200, load_json=True)
        return render_template('searchadv.html',
            query=query,
            types=types,
            countries=countries,
            cats=cats,
            operators=operators,
            results=results,
            page=page,
            per_page=per_page,
            ftypes=ftypes,
            fcountries=fcountries,
            fcats=fcats,
            foperators=foperators,
            **ctx,
            **app.config['SPHINX'].builder.globalcontext)
    except Exception as e:
        return render_template('searchadv.html', error=f"Erreur de recherche: {str(e)}")

@app.route('/<path:my_path>')
def catch_all(my_path):
    if '.' not in my_path:
        my_path += '.html'
    # ~ app.logger.error(app.config['UPLOAD_FOLDER'] + my_path)
    return send_from_directory(app.config['UPLOAD_HTML'], my_path)
