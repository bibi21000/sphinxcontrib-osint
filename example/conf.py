# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
sys.path.append(os.path.abspath("../sphinxcontrib"))

if os.path.isfile('../../private_conf.py') is True:
    sys.path.append(os.path.abspath("../.."))
    from private_conf import *

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'quest_example'
copyright = '2025, bibi21000'
author = 'bibi21000'
release = '0.0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions =[
    'sphinx.ext.graphviz',
    'sphinx.ext.todo',
    'sphinxcontrib.osint',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

language = 'EN'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'bizstyle'
html_static_path = ['_static']

# -- OSInt configuration ---------------------------------------------------
# Look at graphviz for all possible values
# https://graphviz.org/doc/info/shapes.html#polygon
# https://graphviz.org/doc/info/shapes.html#styles-for-nodes
# https://graphviz.org/doc/info/colors.html
osint_default_cats = {
        'media' : {
            'shape' : 'egg',
            'style' : 'solid',
        },
        'financial' : {
            'shape' : 'hexagon',
            'style' : 'solid',
        },
        'other' : {
            'shape' : 'octogon',
            'style' : 'dashed',
        },
    }
osint_org_cats = None
osint_ident_cats = None
osint_event_cats = None
osint_source_cats = None
osint_country = 'US'
osint_local_store = 'store_local'
osint_csv_store = 'store_csv'
osint_emit_warnings = False

osint_text_enabled = True
osint_text_translate = 'en'
osint_text_original = True

osint_pdf_enabled = True
os.environ["XDG_SESSION_TYPE"] = "xcb"

osint_analyse_enabled = True
osint_analyse_countries = ['UK', "United Kingdom", 'US', 'USA']
osint_analyse_engines = ['mood', 'words', 'people', 'countries', 'ident']
osint_analyse_update = 2

osint_whois_enabled = True

osint_bsky_enabled = False

# -- Todos configuration ---------------------------------------------------
todo_include_todos = True
todo_link_only = True
todo_emit_warnings = False
