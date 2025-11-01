# -*- encoding: utf-8 -*-
"""
The flask lib
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import sys
import html
import contextlib
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_babel import Babel, gettext, lazy_gettext as _l
from werkzeug.utils import secure_filename
from jinja2 import ChoiceLoader, FileSystemLoader
from jinja2.utils import open_if_exists, pass_context
import sphinx
from sphinx.builders.html._assets import (
    _CascadingStyleSheet,
    _file_checksum,
    _JavaScript,
)
import pycountry

from .osintlib import OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource, OSIntCountry
from .xapian import XapianIndexer

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
    # ~ if resource and '://' in otheruri:
        # ~ # allow non-local resources given by scheme
        # ~ return otheruri
    # ~ elif not resource:
        # ~ otheruri = self.get_target_uri(otheruri)
    # ~ uri = relative_uri(baseuri, otheruri) or '#'
    # ~ if uri == '#' and not self.allow_sharp_as_current_path:
        # ~ uri = baseuri
    return otheruri

def hasdoc(name: str) -> bool:
    # ~ if name in self.env.all_docs:
        # ~ return True
    # ~ if name == 'search' and self.search:
        # ~ return True
    # ~ return name == 'genindex' and self.get_builder_config('use_index', 'html')
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
        # MathJax v2 reads a ``?config=...`` query parameter,
        # special case this and just skip adding the checksum.
        # https://docs.mathjax.org/en/v2.7-latest/configuration.html#considerations-for-using-combined-configuration-files
        # https://github.com/sphinx-doc/sphinx/issues/11658
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

# ~ @app.route('/<filename>')
# ~ def view_page(filename):
    # ~ """Afficher une page HTML statique"""
    # ~ app.logger.error(app.config['UPLOAD_FOLDER'] + filename)
    # ~ return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/searchadv.html')
def searchadv():
    # ~ app.logger.error(app.config['UPLOAD_FOLDER'] + my_path)
    # ~ return send_from_directory(app.config['UPLOAD_FOLDER'], my_path)
    # ~ return send_from_directory(app.config['UPLOAD_FOLDER'], 'searchadv.html')
    # ~ return "No0t found", 404
    args = request.args.to_dict(flat=False)
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
    for ftyp in [OSIntOrg.prefix, OSIntIdent.prefix, OSIntEvent.prefix, OSIntSource.prefix]:
        if types is None or ftyp not in types or reset:
            ftypes.append((ftyp, 0))
        else:
            ftypes.append((ftyp, 1))

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

    if (query is None and types is None and countries is None and cats is None) or reset:
        return render_template('searchadv.html',
            # ~ error="Type your search",
            results=None,
            ftypes=ftypes,
            fcountries=fcountries,
            fcats=fcats,
            **ctx,
            **app.config['SPHINX'].builder.globalcontext)

    page = int(request.args.get('page', 1))
    per_page = 25
    offset = (page - 1) * per_page

    try:
        results = indexer.search(query, use_fuzzy=False, fuzzy_threshold=70,
            cats=None, types=types, countries=countries,
            offset=page, limit=per_page,
            distance=200, load_json=True, highlighted='<span class="highlighted">%s</span>')
        return render_template('searchadv.html',
            query=query,
            results=results,
            page=page,
            per_page=per_page,
            ftypes=ftypes,
            fcountries=fcountries,
            fcats=fcats,
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
