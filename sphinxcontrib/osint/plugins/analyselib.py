# -*- encoding: utf-8 -*-
"""
The analyse plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'
import os
from typing import TYPE_CHECKING, ClassVar, cast
from collections import Counter

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging, texescape

from ..osintlib import OSIntRelated, OSIntSource
from ..interfaces import NltkInterface
from .. import Index, option_reports, option_main, yesno
from . import SphinxDirective
from . import reify

if TYPE_CHECKING:
    from docutils.nodes import Node
    from sphinx.util.typing import OptionSpec
    from sphinx.writers.html5 import HTML5Translator
    from sphinx.writers.latex import LaTeXTranslator

logger = logging.getLogger(__name__)


class IndexAnalyse(Index):
    """An index for graphs."""

    name = 'analyses'
    localname = 'Analyses Index'
    shortname = 'Analyses'

    def get_datas(self):
        datas = self.domain.get_entries_analyses()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class OSIntAnalyse(OSIntRelated):

    prefix = 'analyse'

    def __init__(self, name, label, **kwargs):
        """A report in the OSIntQuest

        Extract and filter data for representation

        """
        super().__init__(name, label, **kwargs)
        self.default_words = []
        self._words_lists = None
        self._words = None

    @classmethod
    def split_engines(self, engines):
        """Split engines in an array

        :param engines: engines to split.
        :type engines: None or str or list
        """
        if engines is None or engines == '':
            global ENGINES
            cengines = ENGINES
        elif isinstance(engines, list):
            cengines = engines
        else:
            cengines = [c for c in engines.split(',') if c != '']
        return cengines

    def analyse(self):
        """Analyse it
        """
        ret_file = os.path.join(self.quest.sphinx_env.config.osint_analyse_report, f'{self.name.replace(self.prefix+".","")}.json')
        ret_filefull = os.path.join(self.quest.sphinx_env.srcdir, ret_file)
        if os.path.isfile(ret_filefull) is True:
            mtime_filefull = os.path.getmtime(ret_filefull)
        else:
            mtime_filefull = 0
        found_new = False
        countries, cities, orgs, all_idents, relations, events, links, quotes, sources = self.data_filter(self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        countries, cities, orgs, all_idents, relations, events, links, quotes, sources = self.data_complete(countries, cities, orgs, all_idents, relations, events, links, quotes, sources, self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        for source in sources:
            source_name = self.quest.sources[source].name.replace(OSIntSource.prefix+".","")
            stat_file = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_analyse_store, f'{source_name}.json')
            if os.path.isfile(stat_file) is False:
                stat_file = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_analyse_cache, f'{source_name}.json')
            # ~ print(stat_file, os.path.getmtime(stat_file) if os.path.isfile(stat_file) else None)
            if os.path.isfile(stat_file) is True and os.path.getmtime(stat_file) > mtime_filefull:
                found_new = True
                break

        # ~ print(found_new, mtime_filefull)
        if (os.path.isfile(ret_filefull) is False) or found_new:
            stats = {}
            for source in sources:
                source_name = self.quest.sources[source].name.replace(OSIntSource.prefix+".","")
                # ~ data = self.domain.load_json_analyse_source(source_name)

                try:
                    # ~ stats1 = self._imp_json.loads(data)
                    stats1 = self.quest.load_json_analyse_source(source_name)
                    if stats == {}:
                        stats = stats1
                    else:
                        _stats = {}

                        for engine in self.quest.sphinx_env.config.osint_analyse_engines:
                            _stats[engine] = ENGINES[engine].merge(stats, stats1)
                        stats = _stats

                except Exception:
                    logger.exception(f"Can't load analyse for {source_name}")

            with open(ret_filefull, 'w') as f:
                f.write(self._imp_json.dumps(stats, indent=2))

        return ret_file, ret_filefull

class analyse_node(nodes.Admonition, nodes.Element):
    pass

def visit_analyse_node(self: HTML5Translator, node: analyse_node) -> None:
    self.visit_admonition(node)

def depart_analyse_node(self: HTML5Translator, node: analyse_node) -> None:
    self.depart_admonition(node)

def latex_visit_analyse_node(self: LaTeXTranslator, node: analyse_node) -> None:
    self.body.append('\n\\begin{osintanalyse}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_analyse_node(self: LaTeXTranslator, node: analyse_node) -> None:
    self.body.append('\\end{osintanalyse}\n')
    self.no_latex_floats -= 1


class Engine():
    name = None

    @classmethod
    @reify
    def _imp_re(cls):
        """Lazy loader for import re"""
        import importlib
        return importlib.import_module('re')

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    def to_dict(self):
        return {}

    def analyse(self, quest, text, day_month=None, countries=None, idents=None, orgs=None, words=None, badwords=None, **kwargs):
        return text

    @classmethod
    def clean_text(self, text):
        return self._imp_re.sub(r'[^\w\s]', ' ', text.lower())

    @classmethod
    def clean_badwords(self, words, badwords=None):
        if badwords is None or len(badwords) == 0:
            return words
        return [x for x in words if x not in badwords]

    # ~ @classmethod
    # ~ def merge_counter(cls, data1, data2):
        # ~ dd2 = { i[0]: i[1] for i in data2}
        # ~ data = []
        # ~ for co in data1:
            # ~ if co[0] in dd2:
                # ~ data.append([co[0],co[1]+ dd2[co[0]]])
                # ~ del dd2[co[0]]
            # ~ else:
                # ~ data.append([co[0],co[1]])
        # ~ for k in dd2:
            # ~ data.append([k,dd2[k]])
        # ~ return data

    @classmethod
    def init(cls, env):
        """
        """
        pass

    def node_process(self, processor, doctree: nodes.document, docname: str, domain, node):
        """ Return a nod to add in container
        """
        return []

    @classmethod
    @reify
    def _imp_matplotlib_pyplot(cls):
        """Lazy loader for import matplotlib.pyplot"""
        import importlib
        return importlib.import_module('matplotlib.pyplot')

    @classmethod
    @reify
    def _imp_matplotlib_patches(cls):
        """Lazy loader for import matplotlib.patches"""
        import importlib
        return importlib.import_module('matplotlib.patches')

    @classmethod
    @reify
    def _imp_matplotlib_font_manager(cls):
        """Lazy loader for import matplotlib.font_manager"""
        import importlib
        return importlib.import_module('matplotlib.font_manager')

    @classmethod
    @reify
    def _imp_wordcloud(cls):
        """Lazy loader for import wordcloud"""
        import importlib
        return importlib.import_module('wordcloud')

    @classmethod
    @reify
    def _imp_pyfonts(cls):
        """Lazy loader for import pyfonts"""
        import importlib
        return importlib.import_module('pyfonts')
    '''
    def wordcloud_generate_old(self, processor, words_counts, width, height, background,
                          colormap, min_font_size, max_font_size, most_commons=20, font_name='Noto Sans'):
        """Génère l'image du nuage de mots"""

        # Configuration de la figure
        fig, ax = self._imp_matplotlib_pyplot.subplots(figsize=(width/100, height/100))
        ax.set_xlim(0, width)
        ax.set_ylim(0, height)
        ax.set_aspect('equal')
        ax.axis('off')
        fig.patch.set_facecolor(background)

        if not words_counts:
            self._imp_matplotlib_pyplot.close(fig)
            return None

        max_count = None
        min_count = None
        local_counts = []
        for wc in words_counts:
            if len(wc) == 0:
                continue
            if len(wc[0]) == 0:
                continue
            wc2 = Counter(dict(wc[0])).most_common(most_commons)
            local_counts.append((wc2, wc[1]))
            if max_count is None:
                max_count = wc2[0][1]
            else:
                max_count = max(max_count, wc2[0][1])
            if min_count is None:
                min_count = min(count for _, count in wc2)
            elif len(wc2) > 0:
                min_count = min(min_count, min(count for _, count in wc2))

        # Positions occupées pour éviter les chevauchements
        occupied_positions = []

        # Couleurs
        colors = self._imp_matplotlib_pyplot.cm.get_cmap(colormap)

        for wc in local_counts:
            for i, (word, count) in enumerate(wc[0]):
                # Calculer la taille de police
                if max_count == min_count:
                    font_size = max_font_size
                else:
                    font_size = min_font_size + (max_font_size - min_font_size) * \
                               ((count - min_count) / (max_count - min_count))

                # Couleur basée sur la fréquence
                color = colors(i / len(wc[0]))

                # Trouver une position libre
                position = self.wordcloud_find_free_position(
                    word, font_size, width, height, occupied_positions
                )

                if position:
                    x, y = position

                    # ~ try:

                        # ~ font = self._imp_pyfonts.load_google_font(font_name, weight="bold")
                    # ~ except Exception:
                        # ~ font = self._imp_pyfonts.load_google_font(font_name)

                    # ~ fp = self._imp_matplotlib_font_manager.FontProperties(family='cursive')
                    ax.text(x, y, word, fontsize=font_size, color=color,
                           ha='center', va='center', weight='bold', fontstyle=wc[1])
                    # ~ ax.text(x, y, word, fontsize=font_size, color=color,
                           # ~ ha='center', va='center', weight='bold', fontstyle=wc[1], font=font)

                    # Marquer la position comme occupée
                    text_width = len(word) * font_size * 0.6
                    text_height = font_size * 1.2
                    occupied_positions.append((x, y, text_width, text_height))

        # Sauvegarder l'image
        output_dir = os.path.join(processor.env.app.outdir, '_images')
        os.makedirs(output_dir, exist_ok=True)

        # Nom de fichier unique
        filename = f'wordcloud_{hash(str(wc[0]))}_{width}x{height}.png'
        image_path = os.path.join(output_dir, filename)

        self._imp_matplotlib_pyplot.savefig(image_path, dpi=100, bbox_inches='tight',
            facecolor=background, edgecolor='none')
        self._imp_matplotlib_pyplot.close(fig)

        return os.path.join('_images', filename)
    '''
    def wordcloud_generate(self, processor, words_counts, width, height, background,
                          colormap, min_font_size, max_font_size, most_commons=20, font_name='Noto Sans'):
        """Génère l'image du nuage de mots"""

        if not words_counts:
            return None

        wcd = {}
        for wc in words_counts:
            if len(wc) == 0:
                continue
            if len(wc[0]) == 0:
                continue
            wc2 = Counter(dict(wc[0])).most_common(most_commons)
            wcd = wcd | {k[0]:k[1] for k in wc2}
        wordcloud = self._imp_wordcloud.WordCloud(
                background_color=background, width=width, height=height
            ).generate_from_frequencies(wcd)
        self._imp_matplotlib_pyplot.imshow(wordcloud, interpolation='bilinear')
        self._imp_matplotlib_pyplot.axis("off")

        output_dir = os.path.join(processor.env.app.outdir, '_images')
        os.makedirs(output_dir, exist_ok=True)

        filename = f'wordcloud_{hash(str(wc[0]))}_{width}x{height}.png'
        image_path = os.path.join(output_dir, filename)

        self._imp_matplotlib_pyplot.savefig(image_path, dpi=100, bbox_inches='tight',
            facecolor=background, edgecolor='none')
        # ~ self._imp_matplotlib_pyplot.close(fig)

        return os.path.join('_images', filename)
    '''
    def wordcloud_find_free_position(self, word, font_size, width, height, occupied):
        """Trouve une position libre pour placer un mot"""
        text_width = len(word) * font_size * 0.6
        if text_width > width:
            text_width = width
        text_height = font_size * 1.2
        if text_height > height:
            text_height = height

        max_attempts = 400
        for _ in range(max_attempts):
            x = random.randint(int(text_width/2), int(width - text_width/2))
            y = random.randint(int(text_height/2), int(height - text_height/2))

            collision = False
            for ox, oy, ow, oh in occupied:
                if (abs(x - ox) < (text_width + ow) / 2 and
                    abs(y - oy) < (text_height + oh) / 2):
                    collision = True
                    break

            if not collision:
                return (x, y)

        # Si aucune position libre, retourner une position aléatoire
        return (random.randint(int(text_width/2), int(width - text_width/2)),
                random.randint(int(text_height/2), int(height - text_height/2)))
    '''
    def wordcloud_node_process(self, processor, words_counts, doctree: nodes.document, docname: str, domain, node, font_name='Noto Sans'):
        width = node.attributes.get('width', 1100)
        height = node.attributes.get('height', 550)
        most_commons = node.attributes.get('most-commons', 20)
        background = node.attributes.get('background', 'white')
        colormap = node.attributes.get('colormap', 'viridis')
        min_font_size = node.attributes.get('min-font-size', 12)
        max_font_size = node.attributes.get('max-font-size', 60)
        description = node.attributes.get('description', 60)

        # Générer l'image
        image_path = self.wordcloud_generate(processor,
            words_counts,
            width, height, background,
            colormap, min_font_size, max_font_size, most_commons=most_commons,
            font_name=font_name
        )
        # Créer le nœud image
        image_node = nodes.image()
        image_node['uri'] = '/' + image_path
        image_node['candidates'] = '?'
        image_node['alt'] = description

        return [image_node]


class NltkEngine(Engine, NltkInterface):
    _setup_nltk = None
    ressources = [
                'punkt', 'stopwords', 'averaged_perceptron_tagger',
                'maxent_ne_chunker', 'words', 'vader_lexicon'
            ]

    @classmethod
    @reify
    def _imp_langdetect(cls):
        """Lazy loader for import langdetect"""
        import importlib
        return importlib.import_module('langdetect')

    @classmethod
    @reify
    def _imp_iso639(cls):
        """Lazy loader for import iso639"""
        import importlib
        return importlib.import_module('iso639')

    @classmethod
    def init(cls, env):
        """
        """
        cls.init_nltk(nltk_download=env.config.osint_analyse_nltk_download)


class SpacyEngine(Engine):

    nlp = None
    mdl_size = "md"  # sm

    @classmethod
    @reify
    def _imp_spacy(cls):
        """Lazy loader for import spacy"""
        import importlib
        return importlib.import_module('spacy')

    @classmethod
    def init(cls, env):
        """
        """
        cls.init_spacy(env)

    @classmethod
    def download_spacy(cls, module):
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "spacy", "download", module])
        cls._imp_spacy.load("module")

    @classmethod
    def init_spacy(cls, env):
        """Configure spaCy pour la reconnaissance d'entités nommées"""
        if cls.nlp is None:
            import subprocess
            try:
                cls.nlp = cls._imp_spacy.load(f"{env.config.osint_text_translate}_core_news_%s"%cls.mdl_size)
            except OSError:
                try:
                    cls.nlp = cls._imp_spacy.load("en_core_web_%s"%cls.mdl_size)
                except OSError:
                    logger.debug("Can't download english language for spacy.")
                    try:
                        cls.download_spacy(f"{env.config.osint_text_translate}_core_news_%s"%cls.mdl_size)
                    except subprocess.CalledProcessError:
                        logger.warning("Language %s for spacy can't be downloaded ... try to install english..."%env.config.osint_text_translate)
                        try:
                            cls.download_spacy("en_core_web_%s"%cls.mdl_size)
                        except subprocess.CalledProcessError:
                            logger.exception("Language %s for spacy can't be downloaded ... install by hand..."%env.config.osint_text_translate)
                            cls.nlp = None


class MoodEngine(NltkEngine):
    name = 'mood'

    @classmethod
    @reify
    def _imp_textblob(cls):
        """Lazy loader for import textblob"""
        import importlib
        return importlib.import_module('textblob')

    @classmethod
    def analyse(self, quest, text, day_month=None, countries=None, idents=None, orgs=None, words=None, badwords=None, **kwargs):
        """Analyse les émotions et sentiments du texte"""
        # Initialisation de l'analyseur de sentiment VADER
        sia = self._imp_nltk_sentiment.SentimentIntensityAnalyzer()

        # Analyse avec VADER (anglais principalement)
        scores_vader = sia.polarity_scores(text)

        # Analyse avec TextBlob
        blob = self._imp_textblob.TextBlob(text)
        polarite_textblob = blob.sentiment.polarity
        subjectivite = blob.sentiment.subjectivity

        # Classification simple
        if polarite_textblob > 0.1:
            sentiment_general = "Positive"
        elif polarite_textblob < -0.1:
            sentiment_general = "Negative"
        else:
            sentiment_general = "Neutral"

        return {
            "sentiment_general": sentiment_general,
            "polarite": round(polarite_textblob, 3),
            "subjectivite": round(subjectivite, 3),
            "scores_vader": {
                "positif": round(scores_vader['pos'], 3),
                "neutre": round(scores_vader['neu'], 3),
                "negatif": round(scores_vader['neg'], 3),
                "compose": round(scores_vader['compound'], 3)
            }
        }

    def node_process(self, processor, doctree: nodes.document, docname: str, domain, node):
        reportf = os.path.join(processor.env.srcdir, processor.env.config.osint_analyse_report, f'{node["osint_name"]}.json')
        with open(reportf, 'r') as f:
            data = self._imp_json.load(f)
        if self.name not in data or 'sentiment_general' not in data[self.name]:
            return []
        moods = []
        if processor.env.config.osint_analyse_moods is not None:
            for m in data[self.name]['sentiment_general']:
                if m == "Positive":
                    m = processor.env.config.osint_analyse_moods[2]
                elif m == "Negative":
                    m = processor.env.config.osint_analyse_moods[0]
                else:
                    m = processor.env.config.osint_analyse_moods[1]
                moods.append(m)
        else :
            moods = data[self.name]['sentiment_general']
        counter = Counter(moods)
        if "caption-%s"%self.name not in node:
            paragraph = nodes.paragraph('Mood :', 'Mood :')
            paragraph += nodes.paragraph('', '')
        else:
            paragraph = nodes.paragraph(f'{node["caption-%s"%self.name]} :', f'{node["caption-%s"%self.name]} :')
            paragraph += nodes.paragraph('', '')
        paragraph += self.wordcloud_node_process(processor,
            [(counter, 'normal')],
            doctree, docname, domain, node, font_name=processor.env.config.osint_analyse_mood_font)
        return paragraph

    @classmethod
    def merge(cls, data1, data2):
        if cls.name not in data1:
            if cls.name not in data2:
                return {}
            else:
                return data2[cls.name]
        if cls.name not in data2:
            return data1[cls.name]
        data = {}
        for key in data1[cls.name].keys():
            if isinstance(data1[cls.name][key], list):
                data[key] = data1[cls.name][key]
                data[key].append(data2[cls.name][key])
            elif isinstance(data1[cls.name][key], dict):
                if key not in data:
                    data[key] = {}
                for kkey in data1[cls.name][key]:
                    if isinstance(data1[cls.name][key][kkey], list):
                        data[key][kkey] = data1[cls.name][key][kkey]
                        data[key][kkey].append(data2[cls.name][key][kkey])
                    else:
                        data[key][kkey] = [data1[cls.name][key][kkey], data2[cls.name][key][kkey]]
            else:
                data[key] = [data1[cls.name][key], data2[cls.name][key]]
        return data

    @classmethod
    def most_common(cls, data):
        return data


class WordsEngine(NltkEngine):
    name = 'words'

    @classmethod
    def analyse(self, quest, text, day_month=None, countries=None, idents=None, orgs=None, words=None, badwords=None, **kwargs):
        words_max = kwargs.pop('words_max', 50)
        text_propre = self._imp_re.sub(r'[^\w\s]', ' ', text.lower())

        lang = self._imp_langdetect.detect(text)
        langf = self._imp_iso639.Language.from_part1(lang)

        # Tokenisation
        all_words = self._imp_nltk_tokenize.word_tokenize(text_propre, language=langf.name.lower())

        try:
            stop_words = self._imp_nltk_corpus.stopwords.words(langf.name.lower())
        except Exception:
            stop_words = list()

        filtered_words = [
            mot for mot in all_words
            if len(mot) > 2 and mot not in stop_words and mot.isalpha()
        ]

        filtered_words = self.clean_badwords(filtered_words, badwords + day_month)

        listed_words = [
            mot for mot in filtered_words
            if mot in words
        ]
        listed_words = self.clean_badwords(listed_words, badwords + day_month)

        compteur = Counter(filtered_words)
        compteur_list = Counter(listed_words)
        return {'commons' : compteur.most_common(words_max), 'lists' : compteur_list.most_common(words_max)}

    def node_process(self, processor, doctree: nodes.document, docname: str, domain, node):
        reportf = os.path.join(processor.env.srcdir, processor.env.config.osint_analyse_report, f'{node["osint_name"]}.json')
        with open(reportf, 'r') as f:
            data = self._imp_json.load(f)
        if self.name not in data or 'commons' not in data[self.name] or 'lists' not in data[self.name]:
            return []
        if "caption-%s"%self.name not in node:
            paragraph = nodes.paragraph('Words :', 'Words :')
            paragraph += nodes.paragraph('', '')
        else:
            paragraph = nodes.paragraph(f'{node["caption-%s"%self.name]} :', f'{node["caption-%s"%self.name]} :')
            paragraph += nodes.paragraph('', '')
        paragraph += self.wordcloud_node_process(processor,
            [(data[self.name]['commons'], 'normal'), (data[self.name]['lists'], 'oblique')],
            doctree, docname, domain, node, font_name=processor.env.config.osint_analyse_font)
        return paragraph

    @classmethod
    def merge(cls, data1, data2):
        if cls.name not in data1:
            if cls.name not in data2:
                return {}
            else:
                return data2[cls.name]
        if cls.name not in data2:
            return data1[cls.name]
        data = {}
        for key in data1[cls.name].keys():
            d1 = {ll[0]: ll[1] for ll in data1[cls.name][key]}
            d2 = {ll[0]: ll[1] for ll in data2[cls.name][key]}
            data[key] = (Counter(d1) + Counter(d2)).most_common()
        return data


class PeopleEngine(SpacyEngine, NltkEngine):
    name = 'people'

    @classmethod
    def init(cls, env):
        """
        """
        cls.init_nltk(nltk_download=env.config.osint_analyse_nltk_download)
        cls.init_spacy(env)

    @classmethod
    def filter_bads(self, people, idents, badpeoples, countries):
        for bad in [']', 'https']:
            if bad in people:
                return True
        if people.lower() in badpeoples:
            return True
        if people.lower() in idents or people in idents:
            return True
        if people.lower() in countries or people in countries:
            return True
        return False

    @classmethod
    def analyse(self, quest, text, idents=None, orgs=None, words=None, **kwargs):
        badpeoples = kwargs.pop('badpeoples', [])
        countries = kwargs.pop('countries', [])
        personnes = Counter()

        if self.nlp:
            doc = self.nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PER" or ent.label_ == "PERSON":
                    nom = ent.text.strip()
                    if len(nom) > 2 and self.filter_bads(nom, idents, badpeoples, countries) is False:
                        personnes[nom] += 1

        try:
            tokens = self._imp_nltk_tokenize.word_tokenize(text)
            pos_tags = self._imp_nltk.tag.pos_tag(tokens)
            chunks = self._imp_nltk.chunk.ne_chunk(pos_tags)

            for chunk in chunks:
                if hasattr(chunk, 'label') and chunk.label() == 'PERSON':
                    nom = ' '.join([token for token, pos in chunk.leaves()])
                    if len(nom) > 2 and self.filter_bads(nom, idents, badpeoples, countries) is False:
                        personnes[nom] += 1
        except Exception:
            logger.exception("Exception in PeopleEngine")

        # Méthode 3: Recherche de motifs de noms (approximative)
        # Recherche de mots commençant par une majuscule
        # ~ pattern_noms = r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'
        # ~ noms_potentiels = self._imp_re.findall(pattern_noms, text)

        # ~ for nom in noms_potentiels:
            # ~ # Filtrage simple pour éviter les faux positifs
            # ~ if not any(mot in nom.lower() for mot in ['le', 'la', 'les', 'un', 'une', 'des']):
                # ~ personnes[nom] += 1
        # ~ clean_text = self.clean_text(text)
        # ~ ident_list = [
            # ~ mot for mot in idents
            # ~ if mot in clean_text
        # ~ ]

        # ~ org_list = [
            # ~ mot for mot in orgs
            # ~ if mot in clean_text
        # ~ ]

        # Comptage des fréquences
        # ~ compteur_ident = Counter(ident_list)
        # ~ compteur_org = Counter(org_list)
        return {
            'commons' : personnes.most_common(),
            # ~ 'idents' : compteur_ident.most_common(),
            # ~ 'orgs' : compteur_org.most_common(),
            }

    def node_process(self, processor, doctree: nodes.document, docname: str, domain, node):
        reportf = os.path.join(processor.env.srcdir, processor.env.config.osint_analyse_report, f'{node["osint_name"]}.json')
        with open(reportf, 'r') as f:
            data = self._imp_json.load(f)
        if self.name not in data or 'commons' not in data[self.name]:
            return []
        # ~ print('noooode', node)
        # ~ print('noooode', node["caption-%s"%self.name])
        if "caption-%s"%self.name not in node:
            paragraph = nodes.paragraph('People :', 'People :')
            paragraph += nodes.paragraph('', '')
        else:
            paragraph = nodes.paragraph(f'{node["caption-%s"%self.name]} :', f'{node["caption-%s"%self.name]} :')
            paragraph += nodes.paragraph('', '')
        paragraph += self.wordcloud_node_process(processor,
            [(data[self.name]['commons'], 'normal')],
            doctree, docname, domain, node, font_name=processor.env.config.osint_analyse_font)
        return paragraph

    @classmethod
    def merge(cls, data1, data2):
        if cls.name not in data1:
            if cls.name not in data2:
                return {}
            else:
                return data2[cls.name]
        if cls.name not in data2:
            return data1[cls.name]
        data = {}
        for key in data1[cls.name].keys():
            d1 = {ll[0]: ll[1] for ll in data1[cls.name][key]}
            d2 = {ll[0]: ll[1] for ll in data2[cls.name][key]}
            data[key] = (Counter(d1) + Counter(d2)).most_common()
        return data

    @classmethod
    def most_common(cls, data):
        if cls.name not in data:
            return {}
        data1 = {}
        for key in data[cls.name].keys():
            data1[key] = data[cls.name].most_common()
        return data1


class IdentEngine(SpacyEngine, NltkEngine):
    name = 'ident'

    @classmethod
    def analyse(cls, quest, text, idents=None, orgs=None, countries=None, cities=None, **kwargs):
        clean_text = cls.clean_text(text).lower()

        try:
            lang = None
            langf = None
            lang = cls._imp_langdetect.detect(clean_text)
            langf = cls._imp_iso639.Language.from_part1(lang)
            all_words = cls._imp_nltk_tokenize.word_tokenize(clean_text, language=langf.name.lower())
        except Exception:
            logger.warning("Exception for lang %s : %s",lang, langf, exc_info=True)
            raise
        clean_text = " ".join(all_words)

        # ~ print(orgs.keys(), idents.keys())
        ident_list = [
            idents[mot] for mot in idents.keys()
            if mot not in orgs.keys() and \
                mot not in countries.keys() and \
                mot not in cities.keys() and \
                f" {mot} " in clean_text
        ]
        # ~ ident_list = [
            # ~ idents[mot] for mot in idents.keys()
            # ~ if f" {mot} " in clean_text
        # ~ ]
        # ~ print('ident_list', ident_list)
        # ~ org_list = [
            # ~ orgs[mot] for mot in orgs.keys()
            # ~ if mot not in countries.keys() and \
            # ~ mot not in cities.keys() and \
            # ~ f" {mot} " in clean_text
        # ~ ]
        org_list = [
            orgs[mot] for mot in orgs.keys()
            if f" {mot} " in clean_text
        ]
        # ~ print('org_list', org_list)

        compteur_ident = Counter(ident_list)
        compteur_org = Counter(org_list)
        return {
            'idents' : compteur_ident.most_common(),
            'orgs' : compteur_org.most_common()
        }

    def node_process(self, processor, doctree: nodes.document, docname: str, domain, node):
        reportf = os.path.join(processor.env.srcdir, processor.env.config.osint_analyse_report, f'{node["osint_name"]}.json')
        with open(reportf, 'r') as f:
            data = self._imp_json.load(f)
        if self.name not in data or 'idents' not in data[self.name] or 'orgs' not in data[self.name]:
            return []

        if "caption-%s"%self.name not in node:
            paragraph = nodes.paragraph('Idents/Orgs :', 'Idents/Orgs :')
            paragraph += nodes.paragraph('', '')
        else:
            paragraph = nodes.paragraph(f'{node["caption-%s"%self.name]} :', f'{node["caption-%s"%self.name]} :')
            paragraph += nodes.paragraph('', '')
        paragraph += self.wordcloud_node_process(processor,
            [([(domain.quest.idents[d[0]].slabel if d[0] in domain.quest.idents else d[0], d[1]) for d in data[self.name]['idents']], 'normal')],
            doctree, docname, domain, node, font_name=processor.env.config.osint_analyse_font)
        paragraph += self.wordcloud_node_process(processor,
            [([(domain.quest.orgs[d[0]].slabel if d[0] in domain.quest.orgs else d[0], d[1]) for d in data[self.name]['orgs']], 'italic')],
            doctree, docname, domain, node, font_name=processor.env.config.osint_analyse_font)
        return paragraph

    @classmethod
    def merge(cls, data1, data2):
        if cls.name not in data1:
            if cls.name not in data2:
                return {}
            else:
                return data2[cls.name]
        if cls.name not in data2:
            return data1[cls.name]
        data = {}
        for key in data1[cls.name].keys():
            d1 = {ll[0]: ll[1] for ll in data1[cls.name][key]}
            d2 = {ll[0]: ll[1] for ll in data2[cls.name][key]}
            data[key] = (Counter(d1) + Counter(d2)).most_common()
        return data

    @classmethod
    def most_common(cls, data):
        if cls.name not in data:
            return {}
        data1 = {}
        for key in data[cls.name].keys():
            data1[key] = data[cls.name].most_common()
        return data1

class CountriesEngine(SpacyEngine, NltkEngine):
    name = 'countries'

    @classmethod
    def analyse(cls, quest, text, countries=None, **kwargs):
        clean_text = cls.clean_text(text).lower()
        countries_list = [
            countries[mot] for mot in countries.keys()
            if mot in clean_text
        ]

        compteur_countries = Counter(countries_list)

        return {
            'countries' : compteur_countries.most_common(),
        }

    def node_process(self, processor, doctree: nodes.document, docname: str, domain, node):
        reportf = os.path.join(processor.env.srcdir, processor.env.config.osint_analyse_report, f'{node["osint_name"]}.json')
        with open(reportf, 'r') as f:
            data = self._imp_json.load(f)
        if self.name not in data or 'countries' not in data[self.name]:
            return []
        if "caption-%s"%self.name not in node:
            paragraph = nodes.paragraph('Countries :', 'Countries :')
            paragraph += nodes.paragraph('', '')
        else:
            paragraph = nodes.paragraph(f'{node["caption-%s"%self.name]} :', f'{node["caption-%s"%self.name]} :')
            paragraph += nodes.paragraph('', '')
        paragraph += self.wordcloud_node_process(processor,
            [([(domain.quest.countries[d[0]].slabel if d[0] in domain.quest.countries else d[0], d[1]) for d in data[self.name]['countries']], 'normal')],
            doctree, docname, domain, node, font_name=processor.env.config.osint_analyse_font)
        return paragraph

    @classmethod
    def merge(cls, data1, data2):
        if cls.name not in data1:
            if cls.name not in data2:
                return {}
            else:
                return data2[cls.name]
        if cls.name not in data2:
            return data1[cls.name]
        data = {}
        for key in data1[cls.name].keys():
            d1 = {ll[0]: ll[1] for ll in data1[cls.name][key]}
            d2 = {ll[0]: ll[1] for ll in data2[cls.name][key]}
            data[key] = (Counter(d1) + Counter(d2)).most_common()
        return data

    @classmethod
    def most_common(cls, data):
        if cls.name not in data:
            return {}
        data1 = {}
        if isinstance(data1[cls.name], list):
            data1['countries'] = data[cls.name]['countries'].most_common()
        else:
            for key in data[cls.name].keys():
                data1[key] = data[cls.name]['countries'].most_common()
        return data1


class CitiesEngine(SpacyEngine, NltkEngine):
    name = 'cities'

    @classmethod
    def analyse(cls, quest, text, cities=None, countries=None, **kwargs):
        clean_text = cls.clean_text(text).lower()

        lang = cls._imp_langdetect.detect(clean_text)
        langf = cls._imp_iso639.Language.from_part1(lang)
        all_words = cls._imp_nltk_tokenize.word_tokenize(clean_text, language=langf.name.lower())
        clean_text = " ".join(all_words)

        city_list = [
            cities[mot] for mot in cities.keys()
            if f" {mot} " in clean_text
        ]

        compteur_city = Counter(city_list)
        return {
            'cities' : compteur_city.most_common(),
        }

    def node_process(self, processor, doctree: nodes.document, docname: str, domain, node):
        reportf = os.path.join(processor.env.srcdir, processor.env.config.osint_analyse_report, f'{node["osint_name"]}.json')
        with open(reportf, 'r') as f:
            data = self._imp_json.load(f)
        if self.name not in data or 'cities' not in data[self.name]:
            return []

        if "caption-%s"%self.name not in node:
            paragraph = nodes.paragraph('Cities :', 'Cities :')
            paragraph += nodes.paragraph('', '')
        else:
            paragraph = nodes.paragraph(f'{node["caption-%s"%self.name]} :', f'{node["caption-%s"%self.name]} :')
            paragraph += nodes.paragraph('', '')
        paragraph += self.wordcloud_node_process(processor,
            [([(domain.quest.cities[d[0]].slabel if d[0] in domain.quest.cities else d[0], d[1]) for d in data[self.name]['cities']], 'normal')],
            doctree, docname, domain, node, font_name=processor.env.config.osint_analyse_font)
        return paragraph

    @classmethod
    def merge(cls, data1, data2):
        if cls.name not in data1:
            if cls.name not in data2:
                return {}
            else:
                return data2[cls.name]
        if cls.name not in data2:
            return data1[cls.name]
        data = {}
        for key in data1[cls.name].keys():
            d1 = {ll[0]: ll[1] for ll in data1[cls.name][key]}
            d2 = {ll[0]: ll[1] for ll in data2[cls.name][key]}
            data[key] = (Counter(d1) + Counter(d2)).most_common()
        return data

    @classmethod
    def most_common(cls, data):
        if cls.name not in data:
            return {}
        data1 = {}
        for key in data[cls.name].keys():
            data1[key] = data[cls.name].most_common()
        return data1


ENGINES = {
    MoodEngine.name: MoodEngine,
    WordsEngine.name: WordsEngine,
    PeopleEngine.name: PeopleEngine,
    IdentEngine.name: IdentEngine,
    CountriesEngine.name: CountriesEngine,
    CitiesEngine.name: CitiesEngine,
}
option_engines = {}
for k in ENGINES.keys():
    option_engines['report-%s'%k] = directives.unchanged
    option_engines['caption-%s'%k] = directives.unchanged

class DirectiveAnalyse(SphinxDirective):
    """
    An OSInt Analyse.
    """
    node_class = analyse_node
    name = 'analyse'
    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'engines': directives.unchanged_required,
        'width': directives.positive_int,
        'height': directives.positive_int,
        'most-commons': directives.positive_int,
        'background': directives.unchanged,
        'colormap': directives.unchanged,
        'min-font-size': directives.positive_int,
        'max-font-size': directives.positive_int,
        'exclude-cats': directives.positive_int,
        'link-json': directives.unchanged,
        'borders': yesno,
    } | option_reports | option_main | option_engines

    def run(self) -> list[Node]:
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
        if not self.options.get('class'):
            self.options['class'] = ['admonition-analyse']

        name = self.arguments[0]
        node = analyse_node()
        node['docname'] = self.env.docname
        node['osint_name'] = name

        if 'exclude-cats' in self.options:
            self.options['exclude_cats'] = self.options['exclude-cats'].split(',')
            del self.options['exclude-cats']
        else:
            self.options['exclude_cats'] = []

        found = False
        for ent in ['report-json', 'link-json'] + [k for k in option_engines.keys() if k.startswith('report-')]:
            if ent in self.options:
                found = True
        if found is False:
            for ent in [k for k in option_engines.keys() if k.startswith('report-')]:
                self.options[ent] = True
        for opt in self.options:
            node[opt] = self.options[opt]
        self.env.get_domain('osint').add_analyse(node['osint_name'],
            self.options.pop('label', node['osint_name']), node, self.options)
        return [node]
