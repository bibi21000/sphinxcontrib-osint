#!/usr/bin/env python3
"""Create osint app."""
import os
import importlib.util

from .flask import create_flask_app
# ~ from .flask import app, CascadingTemplateLoader, init_xapian
# ~ from .scripts import parser_makefile, cli, get_app, load_quest
"""
docdir = os.environ.get('OSINT_HOME', '/var/lib/osint')
print("docdir", docdir)

sourcedir, builddir = parser_makefile(docdir)
sourcedir = os.path.join(docdir, sourcedir)
builddir = os.path.join(docdir, builddir)
sphinx_app = get_app(sourcedir=sourcedir, builddir=builddir)
print("sourcedir", sourcedir)
print("builddir", builddir)
print("sphinx_app", dir(sphinx_app))

# ~ file_path = os.path.join(sourcedir, 'conf.py')
# ~ module_name = 'conf'

# ~ spec = importlib.util.spec_from_file_location(module_name, file_path)
# ~ module = importlib.util.module_from_spec(spec)
# ~ spec.loader.exec_module(module)

data = load_quest(os.path.realpath(builddir))
print(data)
# ~ app.secret_key = module.secret_key
app.secret_key = sphinx_app.config.secret_key
app.config['SPHINX'] = sphinx_app
app.config['QUEST'] = data
app.config['UPLOAD_FOLDER'] = os.path.realpath(builddir)
app.config['UPLOAD_HTML'] = os.path.join(os.path.realpath(builddir),'html')
app.config['UPLOAD_XAPIAN'] = os.path.join(os.path.realpath(builddir),'xapian')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max
cascade_loader = CascadingTemplateLoader(sphinx_app.builder.theme.get_theme_dirs())
app.jinja_loader = cascade_loader.get_loader()
init_xapian(app.config['UPLOAD_XAPIAN'], sphinx_app)
"""

# ~ def create_flask_app():
    # ~ docdir = os.environ.get('OSINT_HOME', '/var/lib/osint')
    # ~ sourcedir, builddir = parser_makefile(docdir)
    # ~ sourcedir = os.path.join(docdir, sourcedir)
    # ~ builddir = os.path.join(docdir, builddir)

    # ~ sphinx_app = get_app(sourcedir=sourcedir, builddir=builddir)

    # ~ data = load_quest(os.path.realpath(builddir))

    # ~ app.secret_key = sphinx_app.config.secret_key
    # ~ app.config['SPHINX'] = sphinx_app
    # ~ app.config['QUEST'] = data
    # ~ app.config['UPLOAD_FOLDER'] = os.path.realpath(builddir)
    # ~ app.config['UPLOAD_HTML'] = os.path.join(os.path.realpath(builddir), 'html')
    # ~ app.config['UPLOAD_XAPIAN'] = os.path.join(os.path.realpath(builddir), 'xapian')
    # ~ app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # ~ cascade_loader = CascadingTemplateLoader(sphinx_app.builder.theme.get_theme_dirs())
    # ~ app.jinja_loader = cascade_loader.get_loader()

    # ~ xapian_dir = app.config['UPLOAD_XAPIAN']
    # ~ if os.path.isdir(xapian_dir):
        # ~ init_xapian(xapian_dir, sphinx_app)
    # ~ else:
        # ~ app.logger.warning("Xapian index not found, search disabled")

    # ~ return app

app = create_flask_app()
