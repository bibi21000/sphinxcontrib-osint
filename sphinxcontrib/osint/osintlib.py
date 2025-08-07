# -*- encoding: utf-8 -*-
"""
The rst extensions
------------------

From https://www.sphinx-doc.org/en/master/development/tutorials/recipe.html

See https://github.com/sphinx-doc/sphinx/blob/c4929d026c8d22ba229b39cfc2250a9eb1476282/sphinx/ext/todo.py

"""
__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

# Python
import os
from datetime import date
import signal
from contextlib import contextmanager
import logging
from collections import defaultdict

from sphinx.domains import Index as _Index
from docutils.parsers.rst.directives.admonitions import BaseAdmonition as _BaseAdmonition
from docutils.statemachine import ViewList

log = logging.getLogger(__name__)
log.setLevel(logging.getLogger().getEffectiveLevel())


class reify:
    """Use as a class method decorator.  It operates almost exactly like the
    Python ``@property`` decorator, but it puts the result of the method it
    decorates into the instance dict after the first call, effectively
    replacing the function it decorates with an instance variable.  It is, in
    Python parlance, a non-data descriptor.  The following is an example and
    its usage:

    .. doctest::

        >>> from sislib.decorator import reify

        >>> class Foo:
        ...     @reify
        ...     def jammy(self):
        ...         print('jammy called')
        ...         return 1

        >>> f = Foo()
        >>> v = f.jammy
        jammy called
        >>> print(v)
        1
        >>> f.jammy
        1
        >>> # jammy func not called the second time; it replaced itself with 1
        >>> # Note: reassignment is possible
        >>> f.jammy = 2
        >>> f.jammy
        2
    """

    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.__name__ = wrapped.__name__
        self.__doc__ = wrapped.__doc__

    def __get__(self, inst, objtype=None):
        if inst is None:
            return self
        try:
            val = self.wrapped(inst)
        except Exception:
            log.exception("Exception while reifying %s" % inst)
            raise
        # reify is a non-data-descriptor which is leveraging the fact
        # that it is not invoked if the equivalent attribute is defined in the
        # object's dict, so the setattr here effectively hides this descriptor
        # from subsequent lookups
        setattr(inst, self.wrapped.__name__, val)
        return val

class Index(_Index):

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.get_datas()
        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class BaseAdmonition(_BaseAdmonition):

    def parse_options(self, optlist=None, docname="fake0.rst",
        mapping=None, null=False, more_options=None, bad_options=None
    ):
        from . import osint_plugins
        if more_options is None:
            more_options = {}
        if bad_options is None:
            bad_options = []
        # ~ if optlist is None:
            # ~ optlist = list(option_main.keys())
        if mapping is None:
            mapping = {}
        params = ViewList()
        params.append('', docname, 0)
        i = 1
        source_name = self.arguments[0] if len(self.arguments) > 0 else None
        for opt in optlist:
            if opt in more_options.keys() or opt in bad_options:
                continue
            optd = opt
            if opt in mapping.keys():
               optd = mapping[opt]
            if null is True:
                val = self.options[opt] if opt in self.options else ''
                params.append(f'* {optd} : {val}', docname, i)
                params.append('', docname, i+1)
                i += 2
            elif opt in self.options:
                if opt == 'url' and len(self.arguments) > 0:
                    if 'source' in self.options and self.options['source'] != '':
                        source_name = self.options['source']
                    else:
                        source_name = self.arguments[0]
                    data = ''
                    for plg in osint_plugins['source']:
                        plg_data = plg.url(self, source_name.replace(f"{OSIntSource.prefix}.", ""))
                        if plg_data is not None:
                            data += plg_data
                    if data == '':
                        data = f'{self.options["url"]}'
                elif opt == 'youtube' and len(self.arguments) > 0:
                    if 'source' in self.options and self.options['source'] != '':
                        source_name = self.options['source']
                    else:
                        source_name = self.arguments[0]
                    data = ''
                    for plg in osint_plugins['source']:
                        plg_data = plg.youtube(self, source_name.replace(f"{OSIntSource.prefix}.", ""))
                        if plg_data is not None:
                            data.extend(plg_data)
                    if data == '':
                        data = f'{self.options["youtube"]}'
                elif opt == 'local' and len(self.arguments) > 0:
                    if 'source' in self.options and self.options['source'] != '':
                        source_name = self.options['source']
                    else:
                        source_name = self.arguments[0]
                    data = f'{self.options["local"]} (:download:`local <{os.path.join("/", self.env.get_domain("osint").quest.local_file(source_name))}>`)'
                else:
                    data = self.options[opt]
                params.append(f'* {optd} : {data}', docname, i)
                params.append('', docname, i+1)
                i += 2
        for opt in more_options:
            data = more_options[opt].replace("\\n",' ')
            params.append(f'* {opt} : {data}', docname, i)
            params.append('', docname, i+1)
            i += 2

        for plg_cat in osint_plugins:
            for plg in osint_plugins[plg_cat]:
                plg.parse_options(self.env, source_name, params, i, optlist, more_options, docname=docname)

        return params


class TimeoutException(Exception):
    pass


class OSIntBase():

    date_begin_min = date(1800,1,1)
    date_end_max = date(2100,1,1)


    @property
    def slabel(self):
        """Return sanitized label"""
        return self.label.replace('\\n', ' ')

    @property
    def domain(self):
        """Return domain"""
        return self.quest.sphinx_env.get_domain("osint")


    @property
    def sdescription(self):
        """Return sanitized description"""
        return self.description.replace('\\n', ' ')

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def split_orgs(self, orgs):
        """Split orgs in an array

        :param orgs: orgs to split.
        :type orgs: None or str or list
        """
        if orgs is None or orgs == '':
            oorgs = []
        elif isinstance(orgs, list):
            oorgs = []
            for o in orgs:
                if o.startswith(f'{OSIntOrg.prefix}.'):
                    oorgs.append(o)
                else:
                    oorgs.append(f"{OSIntOrg.prefix}.{o}")
        else:
            oorgs = [f"{OSIntOrg.prefix}.{o}" for o in orgs.split(',') if o != '']
        return oorgs

    @classmethod
    def split_idents(self, idents):
        """Split idents in an array

        :param idents: idents to split.
        :type idents: None or str or list
        """
        if idents is None or idents == '':
            cidents = []
        elif isinstance(idents, list):
            cidents = idents
        else:
            cidents = [c for c in idents.split(',') if c != '']
        cidents = [ f"{OSIntIdent.prefix}.{idt}" if idt.startswith(f"{OSIntIdent.prefix}.") is False else idt for idt in cidents]
        return cidents

    @classmethod
    def split_cats(self, cats):
        """Split cats in an array

        :param cats: cats to split.
        :type cats: None or str or list
        """
        if cats is None or cats == '':
            ccats = []
        elif isinstance(cats, list):
            ccats = cats
        else:
            ccats = [c for c in cats.split(',') if c != '']
        return ccats

    @classmethod
    def split_countries(self, countries):
        """Split countries in an array

        :param countries: countries to split.
        :type countries: None or str or list
        """
        if countries is None or countries == '':
            ccountries = []
        elif isinstance(countries, list):
            ccountries = countries
        else:
            ccountries = [c for c in countries.split(',') if c != '']
        return ccountries

    @classmethod
    def split_sources(self, sources):
        """Split sources in an array

        :param sources: sources to split.
        :type sources: None or str or list
        """
        if sources is None or sources == '':
            ssources = []
        elif isinstance(sources, list):
            ssources = []
            for s in sources:
                if s.startswith(f'{OSIntSource.prefix}.'):
                    ssources.append(s)
                else:
                    ssources.append(f"{OSIntSource.prefix}.{s}")
        else:
            ssources = [f"{OSIntSource.prefix}.{s}" for s in sources.split(',') if s != '']
        return ssources

    @classmethod
    def init(cls):
        pass

    def parse_dates(self, begin, end):
        if begin is not None:
            begin_defined = True
            if begin == 'now':
                begin = date.today()
            else:
                begin = date.fromisoformat(begin)
        else:
            begin_defined = False
            begin = self.date_begin_min
        if end is not None:
            if end == 'now':
                end = date.today()
            else:
                end = date.fromisoformat(end)
        else:
            if begin_defined:
                end = begin
            else:
                end = self.date_end_max
        return begin, end

    def data_complete(self, data_orgs, data_idents, data_relations,
        data_events, data_links, data_quotes, data_sources,
        cats, orgs, begin, end, countries, idents, borders=True
    ):
        """Add missing links, relations ans quotes

        :param cats: cats to filter on.
        :type cats: None or list
        :param orgs: orgs to filter on.
        :type orgs: None or list
        :param years: years to filter on.
        :type years: None or list
        :param countries: countries to filter on.
        :type countries: None or list
        """
        more_data_links = []
        more_data_idents = []
        more_data_events = []
        more_data_quotes = []
        more_data_relations = []

        if False:
            #Don't work'
            for event in data_events:
                for link in self.quest.links:
                    if self.quest.links[link].lto == self.quest.events[event].name:
                        if link not in data_links and link not in more_data_links:
                            more_data_links.append(link)
                        if self.quest.links[link].lfrom not in data_idents and self.quest.links[link].lfrom not in data_idents:
                            more_data_idents.append(self.quest.links[link].lfrom)
                for quote in self.quest.quotes:
                    if self.quest.quotes[quote].qto == self.quest.events[event].name:
                        if quote not in data_quotes and quote not in more_data_quotes:
                            more_data_quotes.append(quote)
                        if self.quest.quotes[quote].qfrom not in data_events and self.quest.quotes[quote].qfrom not in more_data_events:
                            more_data_events.append(self.quest.quotes[quote].qfrom)
                    if self.quest.quotes[quote].qfrom == self.quest.events[event].name:
                        if quote not in data_quotes and quote not in data_quotes:
                            more_data_quotes.append(quote)
                        if self.quest.quotes[quote].qto not in data_events and self.quest.quotes[quote].qto not in more_data_events:
                            more_data_events.append(self.quest.quotes[quote].qto)
            for ident in data_idents:
                for rel in self.quest.relations:
                    if self.quest.relations[rel].rfrom == self.quest.idents[ident].name:
                        if rel not in data_relations and rel not in more_data_relations:
                            more_data_relations.append(rel)
                        if self.quest.relations[rel].rto not in data_idents and self.quest.relations[rel].rto not in more_data_idents:
                            more_data_idents.append(self.quest.relations[rel].rto)
                    if self.quest.relations[rel].rto == self.quest.idents[ident].name:
                        if rel not in data_relations and rel not in more_data_relations:
                            more_data_relations.append(rel)
                        if self.quest.relations[rel].rfrom not in data_idents and self.quest.relations[rel].rfrom not in more_data_idents:
                            more_data_idents.append(self.quest.relations[rel].rfrom)

        # ~ print(data_orgs, data_idents, data_relations, data_events, data_links, data_quotes, data_sources)
        for rel in data_relations:
            if self.quest.relations[rel].rfrom not in data_idents:
                data_idents.append(self.quest.relations[rel].rfrom)
            if self.quest.relations[rel].rto not in data_idents:
                data_idents.append(self.quest.relations[rel].rto)
        # ~ print(data_orgs, data_idents, data_relations, data_events, data_links, data_quotes, data_sources)
        for link in data_links:
            if self.quest.links[link].lfrom not in data_idents:
                data_idents.append(self.quest.links[link].lfrom)
            if self.quest.links[link].lto not in data_events:
                data_events.append(self.quest.links[link].lto)
        # ~ print(data_orgs, data_idents, data_relations, data_events, data_links, data_quotes, data_sources)
        for quote in data_quotes:
            if self.quest.quotes[quote].qfrom not in data_events:
                data_events.append(self.quest.quotes[quote].qfrom)
            if self.quest.quotes[quote].qto not in data_events:
                data_events.append(self.quest.quotes[quote].qto)
        # ~ print(data_orgs, data_idents, data_relations, data_events, data_links, data_quotes, data_sources)

        return data_orgs, data_idents + more_data_idents, data_relations + more_data_relations,\
            data_events + more_data_events, data_links + more_data_links, data_quotes + more_data_quotes,\
            data_sources

    def data_group_orgs(self, data_orgs, data_idents, data_relations,
        data_events, data_links, data_quotes, data_sources,
        cats, orgs, begin, end, countries):
        """Group data by orgs

        :param cats: cats to filter on.
        :type cats: None or list
        :param orgs: orgs to filter on.
        :type orgs: None or list
        :param years: years to filter on.
        :type years: None or list
        :param countries: countries to filter on.
        :type countries: None or list
        """
        orgs = [self.quest.idents[ident].orgs[0] for ident in data_idents if self.quest.idents[ident].orgs != []]
        orgs += [self.quest.events[event].orgs[0] for event in data_events if self.quest.events[event].orgs != []]
        lonely_idents = [ident for ident in data_idents if self.quest.idents[ident].orgs == [] or \
            self.quest.idents[ident].orgs[0] not in orgs]
        lonely_events = [event for event in data_events if self.quest.events[event].orgs == [] or \
            self.quest.events[event].orgs[0] not in orgs]
        log.debug('all_idents %s', data_idents)
        all_orgs = list(set(data_orgs + orgs))
        # ~ print(orgs)
        all_idents = list(set(data_idents))
        # ~ print(all_idents)
        all_events = list(set(data_events))
        # ~ print(events)
        lonely_events = list(set(lonely_events))
        # ~ print(lonely_events)
        lonely_idents = list(set(lonely_idents))
        # ~ print(lonely_idents)
        all_links = list(set(data_links))
        all_quotes = list(set(data_quotes))
        all_relations = list(set(data_relations))
        all_sources = list(set(data_sources))
        # ~ print(links)
        return all_orgs, all_idents, lonely_idents, all_relations, all_events, lonely_events, all_links, all_quotes, all_sources

    def data_filter(self, cats, orgs, begin, end, countries, idents, borders=True):
        """Filter data to report
        Need to be improved

        :param cats: cats to filter on.
        :type cats: None or list
        :param orgs: orgs to filter on.
        :type orgs: None or list
        :param years: years to filter on.
        :type years: None or list
        :param countries: countries to filter on.
        :type countries: None or list
        """
        log.debug('self.quest.idents %s' % self.quest.idents)
        filtered_orgs = self.quest.get_orgs(cats=cats, orgs=orgs, countries=countries, borders=borders)
        log.debug('orgs %s %s %s : %s' % (cats, orgs, countries, filtered_orgs))
        filtered_idents = self.quest.get_idents(cats=cats, idents=idents, orgs=orgs, countries=countries, borders=borders)
        log.debug('idents %s %s %s : %s' % (cats, orgs, countries, filtered_idents))
        # ~ filtered_relations = self.quest.get_relations(cats=cats, orgs=orgs, countries=countries, borders=borders)
        filtered_events = self.quest.get_events(cats=cats, orgs=orgs, countries=countries, borders=borders)
        log.debug('events %s %s %s : %s' % (cats, orgs, countries, filtered_events))
        # ~ filtered_links = self.quest.get_links(cats=cats, orgs=orgs, countries=countries, borders=borders)
        # ~ filtered_quotes = self.quest.get_quotes(cats=cats, orgs=orgs, countries=countries, borders=borders)
        # ~ log.debug('quotes %s %s %s : %s ' % (cats, orgs, countries, filtered_quotes))

        rel_idents, relations = self.quest.get_idents_relations(filtered_idents, cats=cats, begin=begin, end=end, countries=countries, borders=borders)
        log.debug('rel_idents %s' % rel_idents)
        log.debug('relations %s' % relations)
        link_idents, events, links = self.quest.get_idents_events(filtered_idents, filtered_events, cats=cats, orgs=orgs, begin=begin, end=end, countries=countries, borders=borders)
        log.debug('links %s' % links)
        events, quotes_events = self.quest.get_events_quotes(events, cats=cats, orgs=orgs, begin=begin, end=end, countries=countries, borders=borders)
        log.debug('quotes_events %s' % quotes_events)

        all_idents = list(set(rel_idents + link_idents))

        filtered_sources = self.quest.get_sources(cats=cats, orgs=orgs, countries=countries, borders=borders,
            filtered_orgs=filtered_orgs, filtered_idents=all_idents, filtered_relations=relations,
            filtered_events=events, filtered_links=links, filtered_quotes=quotes_events)
        log.debug('sources %s %s %s : %s ' % (cats, orgs, countries, filtered_sources))
        return filtered_orgs, all_idents, relations, events, links, quotes_events, filtered_sources

    @contextmanager
    def time_limit(self, seconds=30):
        """Get the style of the object

        :param seconds: Number of seconds before timeout.
        :type seconds: int
        """
        def signal_handler(signum, frame):
            raise TimeoutException("Timed out!")
        signal.signal(signal.SIGALRM, signal_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)


class OSIntQuest(OSIntBase):

    def __init__(self, default_cats=None,
        default_org_cats=None, default_ident_cats=None, default_event_cats=None, default_source_cats=None,
        default_relation_cats=None, default_link_cats=None, default_quote_cats=None,
        default_country=None, source_download=None,
        local_store=None, csv_store=None,
        sphinx_env=None, state=None
    ):
        """The quest of the OSInt

        cats = {
            'test1' : {
                'shape' : 'hexagon',
                'style' : 'dashed',
            },
            'test2' : {
                'shape' : 'octogon',
                'style' : 'invis',
            },
        }

        :param default_cats: The default global categories.
        :type default_cats: dict of cats
        :param default_org_cats: The default org categories.
        :type default_cats: dict of cats
        :param default_event_cats: The default event categories.
        :type default_event_cats: dict of cats
        :param default_country: The default country.
        :type default_country: str
        :param local_store: The path where store sources.
        :type local_store: str
        :param cache_store: The path where store sources.
        :type cache_store: str
        """
        self.sphinx_env = sphinx_env
        self.orgs = {}
        self.idents = {}
        self.relations = {}
        self.events = {}
        self.links = {}
        self.quotes = {}
        self.sources = {}
        self.graphs = {}
        self.reports = {}
        self.csvs = {}
        self._default_cats = default_cats
        self._default_org_cats = default_org_cats
        self._default_ident_cats = default_ident_cats
        self._default_event_cats = default_event_cats
        self._default_relation_cats = default_relation_cats
        self._default_link_cats = default_link_cats
        self._default_quote_cats = default_quote_cats
        self._default_quote_cats = default_quote_cats
        self._default_country = default_country
        self._local_store = local_store
        # ~ self._cache_store = cache_store
        # ~ self._csv_store = csv_store
        self._csv_store = csv_store
        self._source_download = source_download

    def get_config(self, name):
        """
        """
        return getattr(self.sphinx_env.config, name)

    @property
    def default_cats(self):
        """
        """
        if self._default_cats is None:
            if self.sphinx_env is not None:
                self._default_cats = self.sphinx_env.config.osint_default_cats
        return self._default_cats

    @property
    def default_org_cats(self):
        """
        """
        if self._default_org_cats is None:
            if self.sphinx_env is not None:
                self._default_org_cats = self.sphinx_env.config.osint_org_cats
            if self._default_org_cats is None:
                self._default_org_cats = self.default_cats
        return self._default_org_cats

    @property
    def default_ident_cats(self):
        """
        """
        if self._default_ident_cats is None:
            if self.sphinx_env is not None:
                self._default_ident_cats = self.sphinx_env.config.osint_ident_cats
            if self._default_ident_cats is None:
                self._default_ident_cats = self.default_cats
        return self._default_ident_cats

    @property
    def default_event_cats(self):
        """
        """
        if self._default_event_cats is None:
            if self.sphinx_env is not None:
                self._default_event_cats = self.sphinx_env.config.osint_event_cats
            if self._default_event_cats is None:
                self._default_event_cats = self.default_cats
        return self._default_event_cats

    @property
    def default_relation_cats(self):
        """
        """
        if self._default_relation_cats is None:
            if self.sphinx_env is not None:
                self._default_relation_cats = self.sphinx_env.config.osint_relation_cats
            if self._default_relation_cats is None:
                self._default_relation_cats = self.default_cats
        return self._default_relation_cats

    @property
    def default_link_cats(self):
        """
        """
        if self._default_link_cats is None:
            if self.sphinx_env is not None:
                self._default_link_cats = self.sphinx_env.config.osint_link_cats
            if self._default_link_cats is None:
                self._default_link_cats = self.default_cats
        return self._default_link_cats

    @property
    def default_quote_cats(self):
        """
        """
        if self._default_quote_cats is None:
            if self.sphinx_env is not None:
                self._default_quote_cats = self.sphinx_env.config.osint_quote_cats
            if self._default_quote_cats is None:
                self._default_quote_cats = self.default_cats
        return self._default_quote_cats

    @property
    def default_country(self):
        """
        """
        if self._default_country is None:
            if self.sphinx_env is not None:
                self._default_country = self.sphinx_env.config.osint_country
        return self._default_country

    @property
    def csv_store(self):
        """
        """
        if self._csv_store is None:
            if self.sphinx_env is not None:
                self._csv_store = self.sphinx_env.config.osint_csv_store
            if self._csv_store is not None and self._csv_store != '':
                os.makedirs(self._csv_store, exist_ok=True)
        return self._csv_store

    @property
    def local_store(self):
        """
        """
        if self._local_store is None:
            if self.sphinx_env is not None:
                self._local_store = self.sphinx_env.config.osint_local_store
            if self._local_store is not None and self._local_store != '':
                os.makedirs(self._local_store, exist_ok=True)
        return self._local_store

    def _filter_cats(self, cats, obj, initial_data, null_ok=False):
        """"Filter by cats"""
        if cats is None or cats == []:
            ret_cats = initial_data
        else:
            ret_cats = []
            cats = self.split_cats(cats)
            for data in initial_data:
                if obj[data].cats == []:
                    if null_ok:
                        ret_cats.append(data)
                else:
                    for cat in cats:
                        if cat in obj[data].cats:
                            ret_cats.append(data)
                            break
        return ret_cats

    def _filter_countries(self, countries, obj, initial_data):
        """"Filter by countries"""
        # ~ print('_filter_countries initial_data', countries, initial_data)
        if countries is None or countries == []:
            ret_countries = initial_data
        else:
            ret_countries = []
            for data in initial_data:
                # ~ print('_filter_countries', countries, obj[data].country, obj[data].label)
                if obj[data].country in countries:
                    ret_countries.append(data)
        return ret_countries

    def _filter_dates(self, begin, end, obj, initial_data):
        """"Filter by dates"""
        if begin is None and end is None:
            ret_dates = initial_data
        else :
            if begin is None:
                begin = self.date_begin_min
            else:
                end = self.date_end_max
            ret_dates = []
            for data in initial_data:
                if obj[data].begin >= begin and obj[data].end < end:
                    ret_dates.append(data)
        return ret_dates

    def _filter_orgs(self, orgs, obj, initial_data, null_ok=False):
        """"Filter by orgs"""
        if orgs is None or orgs == []:
            ret_orgs = initial_data
        else:
            ret_orgs = []
            for data in initial_data:
                if obj[data].orgs == [] or obj[data].orgs == '':
                    if null_ok:
                        ret_orgs.append(data)
                else:
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        # ~ print('oorg', oorg, obj[data].orgs)
                        if oorg in obj[data].orgs:
                            ret_orgs.append(data)
                            # ~ print('ret_orgs', ret_orgs)
                            break
        # ~ print('ret_orgs final', ret_orgs)
        return ret_orgs

    def _filter_idents(self, idents, obj, initial_data):
        """"Filter by idents"""
        # ~ print('_filter_countries initial_data', countries, initial_data)
        if idents is None or idents == []:
            ret_idents = initial_data
        else:
            ret_idents = []
            for data in initial_data:
                # ~ print('_filter_countries', countries, obj[data].country, obj[data].label)
                if data in idents and data not in ret_idents:
                    ret_idents.append(data)
        return ret_idents

    def add_org(self, name, label, **kwargs):
        """Add org to the quest

        :param name: The name of the org.
        :type name: str
        :param label: The label of the org.
        :type label: str
        :param kwargs: The kwargs for the org.
        :type kwargs: kwargs
        """
        org = OSIntOrg(name, label, default_cats=self.default_org_cats, quest=self, **kwargs)
        self.orgs[org.name] = org

    def get_orgs(self, orgs=None, cats=None, countries=None, borders=True):
        """Get orgs from the quest

        :param cats: The cats for filtering orgs.
        :type cats: list of str
        :param countries: The countries for filtering idents.
        :type countries: list of str
        :returns: a list of idents
        :rtype: list of str
        """
        if orgs is not None and len(orgs) != 0:
            ret_orgs = orgs
        else:
            ret_orgs = list(self.orgs.keys())
        log.debug(f"get_orgs {orgs} : {ret_orgs}")
        ret_cats = self._filter_cats(cats, self.orgs, ret_orgs)
        log.debug(f"get_orgs {cats} : {ret_cats}")
        ret_countries = self._filter_countries(countries, self.orgs, ret_cats)
        log.debug(f"get_orgs {cats} {countries} : {ret_countries}")
        return ret_countries

    def add_relation(self, label, rfrom, rto, **kwargs):
        """Add relation to the quest

        :param name: The name of the relation.
        :type name: str
        :param label: The label of the relation.
        :type label: str
        :param kwargs: The kwargs for the relation.
        :type kwargs: kwargs
        """
        relation = OSIntRelation(label, rfrom, rto, default_cats=self.default_relation_cats, quest=self, **kwargs)
        self.relations[relation.name] = relation

    def get_relations(self, orgs=None, cats=None, countries=None, begin=None, end=None, borders=True):
        """Get relations from the quest

        :param cats: The cats for filtering idents.
        :type cats: list of str
        :param countries: The countries for filtering idents.
        :type countries: list of str
        :returns: a list of idents
        :rtype: list of str
        """
        # ~ ret_orgs = self._filter_cats(orgs, self.relations, list(self.relations.keys()))
        # ~ log.debug(f"get_relations {orgs} : {ret_orgs}")
        ret_cats = self._filter_cats(cats, self.relations, self.relations.keys())
        log.debug(f"get_relations {orgs} {cats} : {ret_cats}")
        # ~ ret_countries = self._filter_countries(countries, self.relations, ret_cats)
        # ~ log.debug(f"get_relations {cats} {countries} : {ret_countries}")
        return list(ret_cats)

    def add_ident(self, name, label, **kwargs):
        """Add ident to the quest

        :param name: The name of the ident.
        :type name: str
        :param label: The label of the ident.
        :type label: str
        :param kwargs: The kwargs for the ident.
        :type kwargs: kwargs
        """
        # ~ print("add_ident", label)
        ident = OSIntIdent(name, label, default_cats=self.default_ident_cats, quest=self, **kwargs)
        self.idents[ident.name] = ident

    def get_idents(self, orgs=None, idents=None, cats=None, countries=None, borders=True):
        """Get idents from the quest

        :param orgs: The orgs for filtering idents.
        :type orgs: list of str
        :param cats: The cats for filtering idents.
        :type cats: list of str
        :param countries: The countries for filtering idents.
        :type countries: list of str
        :returns: a list of idents
        :rtype: list of str
        """
        ret_orgs = self._filter_orgs(orgs, self.idents, list(self.idents.keys()))
        log.debug(f"get_idents {orgs} : {ret_orgs}")
        ret_cats = self._filter_cats(cats, self.idents, ret_orgs)
        log.debug(f"get_idents {orgs} {cats} : {ret_cats}")
        ret_countries = self._filter_countries(countries, self.idents, ret_cats)
        log.debug(f"get_idents {orgs} {cats} {countries} : {ret_countries}")
        return ret_countries

    def get_events(self, orgs=None, cats=None, idents=None, countries=None, begin=None, end=None, borders=True):
        """Get events from the quest

        :param orgs: The orgs for filtering idents.
        :type orgs: list of str
        :param cats: The cats for filtering idents.
        :type cats: list of str
        :param countries: The countries for filtering idents.
        :type countries: list of str
        :returns: a list of idents
        :rtype: list of str
        """
        ret_orgs = self._filter_orgs(orgs, self.events, list(self.events.keys()))
        log.debug(f"get_events {orgs} : {ret_orgs}")
        ret_cats = self._filter_cats(cats, self.events, ret_orgs)
        log.debug(f"get_events {orgs} {cats} : {ret_cats}")
        ret_countries = self._filter_countries(countries, self.events, ret_cats)
        log.debug(f"get_events {orgs} {cats} {countries} : {ret_countries}")
        return ret_countries

    def get_idents_relations(self, idents, orgs=None, cats=None, countries=None, begin=None, end=None, borders=True):
        """Get idents and relations from the quest

        :param idents: The idents for searching relations.
        :type idents: list of str
        :param cats: The cats for filtering relations.
        :type cats: list of str
        :param years: The years for filtering relations.
        :type years: list of str
        :returns: a tuple of lists of idents and relations
        :rtype: tupe of lists of str
        """
        rels = self.get_relations(cats=cats, orgs=orgs, countries=countries, borders=borders)
        # ~ rels = self._filter_cats(cats, self.relations, list(self.relations.keys()))
        # ~ log.debug(f"get_idents_relations {cats} : {rels}")
        # ~ rels = self._filter_orgs(orgs, self.relations, rels)
        # ~ log.debug(f"get_idents_relations {cats} {orgs} : {rels}")
        # ~ rels = self._filter_countries(countries, self.relations, rels)
        log.debug(f"get_idents_relations {cats} {orgs} {countries} : {rels}")

        rels_idents = []
        idents_rels = []
        for rel in rels:
            # ~ print(self.relations[rel].rfrom, self.relations[rel].rfrom in idents, self.relations[rel].rto, self.relations[rel].rto not in idents)
            if self.relations[rel].rfrom in idents or self.relations[rel].rto in idents:
                if borders:
                    if rel not in idents_rels:
                        idents_rels.append(rel)
                    if (self.relations[rel].rto not in idents and self.relations[rel].rto not in rels_idents):
                        rels_idents.append(self.relations[rel].rto)
                    if (self.relations[rel].rfrom not in idents and self.relations[rel].rfrom not in rels_idents):
                        rels_idents.append(self.relations[rel].rfrom)
                else:
                    if self.relations[rel].rfrom in idents and self.relations[rel].rto in idents:
                        idents_rels.append(rel)
        # ~ print(rels_idents)
        rels_idents += idents
        log.debug(f"get_idents_relations {cats} : {rels_idents} {rels}")
        return rels_idents, idents_rels

    def add_event(self, name, label, **kwargs):
        """Add ident to the quest

        :param name: The name of the ident.
        :type name: str
        :param label: The label of the ident.
        :type label: str
        :param kwargs: The kwargs for the ident.
        :type kwargs: kwargs
        """
        event = OSIntEvent(name, label, default_cats=self.default_event_cats, quest=self, **kwargs)
        self.events[event.name] = event

    def add_link(self, label, lfrom, lto, **kwargs):
        """Add link to the quest

        :param label: The label of the ident.
        :type label: str
        :param kwargs: The kwargs for the ident.
        :type kwargs: kwargs
        """
        link = OSIntLink(label, lfrom, lto, default_cats=self.default_link_cats, quest=self, **kwargs)
        self.links[link.name] = link

    def get_links(self, orgs=None, cats=None, countries=None, begin=None, end=None, borders=True):
        """Get links from the quest

        :param orgs: The orgs for filtering idents.
        :type orgs: list of str
        :param cats: The cats for filtering idents.
        :type cats: list of str
        :param countries: The countries for filtering idents.
        :type countries: list of str
        :returns: a list of idents
        :rtype: list of str
        """
        # ~ ret_orgs = self._filter_orgs(orgs, self.links, list(self.links.keys()))
        # ~ log.debug(f"get_links {orgs} : {ret_orgs}")
        ret_cats = self._filter_cats(cats, self.links, list(self.links.keys()))
        log.debug(f"get_links {orgs} {cats} : {ret_cats}")
        # ~ ret_countries = self._filter_countries(countries, self.links, ret_cats)
        # ~ log.debug(f"get_links {orgs} {cats} {countries} : {ret_countries}")
        return list(ret_cats)

    def add_quote(self, label, lfrom, lto, **kwargs):
        """Add quote to the quest

        :param label: The label of the ident.
        :type label: str
        :param kwargs: The kwargs for the ident.
        :type kwargs: kwargs
        """
        quote = OSIntQuote(label, lfrom, lto, default_cats=self.default_quote_cats, quest=self, **kwargs)
        self.quotes[quote.name] = quote

    def get_quotes(self, orgs=None, cats=None, countries=None, begin=None, end=None, borders=True):
        """Get quotes from the quest

        :param orgs: The orgs for filtering idents.
        :type orgs: list of str
        :param cats: The cats for filtering idents.
        :type cats: list of str
        :param countries: The countries for filtering idents.
        :type countries: list of str
        :returns: a list of idents
        :rtype: list of str
        """
        # ~ ret_orgs = self._filter_orgs(orgs, self.quotes, list(self.quotes.keys()))
        # ~ log.debug(f"get_quotes {orgs} : {ret_orgs}")
        ret_cats = self._filter_cats(cats, self.quotes, list(self.quotes.keys()))
        log.debug(f"get_quotes {orgs} {cats} : {ret_cats}")
        # ~ ret_countries = self._filter_countries(countries, self.quotes, ret_cats)
        # ~ log.debug(f"get_quotes {orgs} {cats} {countries} : {ret_countries}")
        return list(ret_cats)

    def get_idents_events(self, idents, events, cats=None, orgs=None, countries=None, begin=None, end=None, borders=True):
        """Get idents and events from the quest

        :param idents: The idents for searching events.
        :type idents: list of str
        :param cats: The cats for filtering events.
        :type cats: list of str
        :param orgs: The orgs for filtering events.
        :type orgs: list of str
        :param years: The years for filtering events.
        :type years: list of str
        :returns: a tuple of lists of events and links
        :rtype: tupe of lists of str
        """
        links = self.get_links(cats=cats, orgs=orgs, countries=countries, borders=borders)
        log.debug(f"get_idents_events {cats} {orgs} {countries} : {links}")
        # ~ events = self.quest.get_events(cats=cats, orgs=orgs, countries=countries, borders=borders)
        # ~ ret_orgs = self._filter_orgs(orgs, self.events, list(self.events.keys()))
        # ~ log.debug(f"get_idents_events {orgs} : {ret_orgs}")
        # ~ ret_cats = self._filter_cats(cats, self.events, ret_orgs)
        # ~ log.debug(f"get_idents_events {orgs} {cats} : {ret_cats}")
        # ~ ret_countries = self._filter_countries(countries, self.events, ret_cats)
        # ~ log.debug(f"get_idents_events {orgs} {cats} {countries} : {events}")
        # ~ events = list(set(ret_countries))

        links_events = []
        events_links = []
        idents_links = []
        for link in links:
            if self.links[link].lfrom in idents or self.links[link].lto in events:
                if borders:
                    if self.links[link].lto not in events and self.links[link].lto not in events_links:
                        events_links.append(self.links[link].lto)
                    if self.links[link].lfrom not in idents and self.links[link].lto not in idents_links:
                        idents_links.append(self.links[link].lfrom)
                    links_events.append(self.links[link].name)
                else:
                    if self.links[link].lfrom in idents and self.links[link].lto in events:
                        links_events.append(self.links[link].name)
        events_links += events
        idents_links += idents
        log.debug(f"get_idents_events {cats}/{idents} : {idents_links} {events_links} {links_events}")
        return idents_links, events_links, links_events

    def get_events_quotes(self, events, cats=None, orgs=None, countries=None, begin=None, end=None, borders=True):
        """Get idents and events from the quest

        :param idents: The idents for searching events.
        :type idents: list of str
        :param cats: The cats for filtering events.
        :type cats: list of str
        :param orgs: The orgs for filtering events.
        :type orgs: list of str
        :param years: The years for filtering events.
        :type years: list of str
        :returns: a tuple of lists of events and links
        :rtype: tupe of lists of str
        """
        quotes = self.get_quotes(cats=cats, orgs=orgs, countries=countries, borders=borders)
        log.debug(f"get_events_quotes {cats} {orgs} {countries} : {quotes}")
        # ~ events = self.quest.get_events(cats=cats, orgs=orgs, countries=countries, borders=borders)
        # ~ ret_orgs = self._filter_orgs(orgs, self.events, list(self.events.keys()))
        # ~ log.debug(f"get_idents_events {orgs} : {ret_orgs}")
        # ~ ret_cats = self._filter_cats(cats, self.events, ret_orgs)
        # ~ log.debug(f"get_idents_events {orgs} {cats} : {ret_cats}")
        # ~ ret_countries = self._filter_countries(countries, self.events, ret_cats)
        # ~ log.debug(f"get_idents_events {orgs} {cats} {countries} : {events}")
        # ~ events = list(set(ret_countries))

        quotes_events = []
        events_quotes = []
        for quote in quotes:
            if self.quotes[quote].qfrom in events or self.quotes[quote].qto in events:
                if borders:
                    if self.quotes[quote].qto not in events and self.quotes[quote].qto not in events_quotes:
                        events_quotes.append(self.quotes[quote].qto)
                    if self.quotes[quote].qfrom not in events and self.quotes[quote].qto not in events_quotes:
                        events_quotes.append(self.quotes[quote].qfrom)
                    quotes_events.append(self.quotes[quote].name)
                else:
                    if self.quotes[quote].qfrom in events and self.quotes[quote].qto in events:
                        quotes_events.append(self.quotes[quote].name)
        events_quotes += events
        log.debug(f"get_events_quotes {cats}/{events} : {events_quotes} {quotes_events}")
        log.debug(f"get_events_quotes : {quotes_events}")
        return events_quotes, quotes_events

    def add_graph(self, name, label, **kwargs):
        """Add graph to the quest

        :param name: The name of the graph.
        :type name: str
        :param label: The label of the graph.
        :type label: str
        :param kwargs: The kwargs for the graph.
        :type kwargs: kwargs
        """
        # ~ print('heeeeeeeeeeeeeeeeeeeeeeeeere')
        graph = OSIntGraph(name, label, quest=self, **kwargs)
        self.graphs[graph.name] = graph

    def get_graphs(self, orgs=None, cats=None, countries=None, years=None):
        """Get graphs from the quest

        :param orgs: The orgs for filtering graphs.
        :type orgs: list of str
        :param cats: The cats for filtering graphs.
        :type cats: list of str
        :param countries: The countries for filtering graphs.
        :type countries: list of str
        :returns: a list of graphs
        :rtype: list of str
        """
        if orgs is None or orgs == []:
            ret_orgs = list(self.graphs.keys())
        else:
            ret_orgs = []
            for graph in self.graphs.keys():
                for org in orgs:
                    oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                    if oorg in self.graphs[graph].orgs:
                        ret_orgs.append(graph)
                        break
        log.debug(f"get_graphs {orgs} : {ret_orgs}")

        if cats is None or cats == []:
            ret_cats = ret_orgs
        else:
            ret_cats = []
            cats = self.split_cats(cats)
            for graph in ret_orgs:
                for cat in cats:
                    if cat in self.graphs[graph].cats:
                        ret_cats.append(graph)
                        break
        log.debug(f"get_graphs {orgs} {cats} : {ret_cats}")

        if countries is None or countries == []:
            ret_countries = ret_cats
        else:
            ret_countries = []
            for graph in ret_cats:
                for country in countries:
                    if country == self.graphs[graph].country:
                        ret_countries.append(graph)
                        break

        log.debug(f"get_graphs {orgs} {cats} {countries} : {ret_countries}")
        return ret_countries

    def add_csv(self, name, label, **kwargs):
        """Add csv to the quest

        :param name: The name of the graph.
        :type name: str
        :param label: The label of the graph.
        :type label: str
        :param kwargs: The kwargs for the graph.
        :type kwargs: kwargs
        """
        # ~ print('heeeeeeeeeeeeeeeeeeeeeeeeere')
        csv = OSIntCsv(name, label, quest=self, **kwargs)
        self.csvs[csv.name] = csv

    def get_csvs(self, orgs=None, cats=None, countries=None, begin=None, end=None):
        """Get csvs from the quest

        :param orgs: The orgs for filtering csvs.
        :type orgs: list of str
        :param cats: The cats for filtering csvs.
        :type cats: list of str
        :param countries: The countries for filtering csvs.
        :type countries: list of str
        :returns: a list of csvs
        :rtype: list of str
        """
        if orgs is None or orgs == []:
            ret_orgs = list(self.csvs.keys())
        else:
            ret_orgs = []
            for csv in self.csvs.keys():
                for org in orgs:
                    oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                    if oorg in self.csvs[csv].orgs:
                        ret_orgs.append(csv)
                        break
        log.debug(f"get_csvs {orgs} : {ret_orgs}")

        if cats is None or cats == []:
            ret_cats = ret_orgs
        else:
            ret_cats = []
            cats = self.split_cats(cats)
            for csv in ret_orgs:
                for cat in cats:
                    if cat in self.csvs[csv].cats:
                        ret_cats.append(csv)
                        break
        log.debug(f"get_csvs {orgs} {cats} : {ret_cats}")

        if countries is None or countries == []:
            ret_countries = ret_cats
        else:
            ret_countries = []
            for csv in ret_cats:
                for country in countries:
                    if country == self.csvs[csv].country:
                        ret_countries.append(csv)
                        break

        log.debug(f"get_csvs {orgs} {cats} {countries} : {ret_countries}")
        return ret_countries

    def add_report(self, name, label, **kwargs):
        """Add report data to the quest

        :param name: The name of the graph.
        :type name: str
        :param label: The label of the graph.
        :type label: str
        :param kwargs: The kwargs for the graph.
        :type kwargs: kwargs
        """
        # ~ print('heeeeeeeeeeeeeeeeeeeeeeeeere')
        report = OSIntReport(name, label, quest=self, **kwargs)
        self.reports[report.name] = report

    def get_reports(self, orgs=None, cats=None, countries=None, begin=None, end=None):
        """Get reports from the quest

        :param orgs: The orgs for filtering reports.
        :type orgs: list of str
        :param cats: The cats for filtering reports.
        :type cats: list of str
        :param countries: The countries for filtering reports.
        :type countries: list of str
        :returns: a list of reports
        :rtype: list of str
        """
        if orgs is None or orgs == []:
            ret_orgs = list(self.reports.keys())
        else:
            ret_orgs = []
            for report in self.reports.keys():
                for org in orgs:
                    oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                    if oorg in self.reports[report].orgs:
                        ret_orgs.append(report)
                        break
        log.debug(f"get_reports {orgs} : {ret_orgs}")

        if cats is None or cats == []:
            ret_cats = ret_orgs
        else:
            ret_cats = []
            cats = self.split_cats(cats)
            for report in ret_orgs:
                for cat in cats:
                    if cat in self.reports[report].cats:
                        ret_cats.append(report)
                        break
        log.debug(f"get_reports {orgs} {cats} : {ret_cats}")

        if countries is None or countries == []:
            ret_countries = ret_cats
        else:
            ret_countries = []
            for report in ret_cats:
                for country in countries:
                    if country == self.reports[report].country:
                        ret_countries.append(report)
                        break

        log.debug(f"get_reports {orgs} {cats} {countries} : {ret_countries}")
        return ret_countries

    def add_dashboard(self, name, label, **kwargs):
        """Add grah, csv and report data to the quest

        :param name: The name of the graph.
        :type name: str
        :param label: The label of the graph.
        :type label: str
        :param kwargs: The kwargs for the graph.
        :type kwargs: kwargs
        """
        # ~ print('heeeeeeeeeeeeeeeeeeeeeeeeere')
        graph = OSIntGraph(name, label, quest=self, **kwargs)
        self.graphs[graph.name] = graph

    def add_source(self, name, label, **kwargs):
        """Add source to the quest

        :param name: The name of the ident.
        :type name: str
        :param label: The label of the ident.
        :type label: str
        :param kwargs: The kwargs for the ident.
        :type kwargs: kwargs
        """
        source = OSIntSource(name, label, default_cats=self.default_cats,
            quest=self, **kwargs)
        self.sources[source.name] = source

    def get_sources(self, orgs=None, cats=None, countries=None, borders=True,
        filtered_orgs=None, filtered_idents=None, filtered_relations=None,
        filtered_events=None, filtered_links=None, filtered_quotes=None):
        """Get sources from the quest

        :param orgs: The orgs for filtering sources.
        :type orgs: list of str
        :param cats: The cats for filtering sources.
        :type cats: list of str
        :param countries: The countries for filtering sources.
        :type countries: list of str
        :returns: a list of sources
        :rtype: list of str
        """
        ret = []
        # ~ log.debug('self.quest.idents %s' % self.idents)
        if filtered_orgs is None:
            filtered_orgs = self.get_orgs(cats=cats, orgs=orgs, countries=countries, borders=borders)
        for data in filtered_orgs:
            for lsource in self.orgs[data].linked_sources():
                if lsource not in ret:
                    ret.append(lsource)

        # ~ log.debug('orgs %s %s %s : %s' % (cats, orgs, countries, filtered_orgs))
        if filtered_idents is None:
            filtered_idents = self.get_idents(cats=cats, orgs=orgs, countries=countries, borders=borders)
        for data in filtered_idents:
            for lsource in self.idents[data].linked_sources():
                if lsource not in ret:
                    ret.append(lsource)

        if filtered_relations is None:
            filtered_relations = self.get_relations(cats=cats, orgs=orgs, countries=countries, borders=borders)
        for data in filtered_relations:
            for lsource in self.relations[data].linked_sources():
                if lsource not in ret:
                    ret.append(lsource)

        if filtered_links is None:
            filtered_links = self.get_links(cats=cats, orgs=orgs, countries=countries, borders=borders)
        for data in filtered_links:
            for lsource in self.links[data].linked_sources():
                if lsource not in ret:
                    ret.append(lsource)

        if filtered_quotes is None:
            filtered_quotes = self.get_quotes(cats=cats, orgs=orgs, countries=countries, borders=borders)
        for data in filtered_quotes:
            for lsource in self.quotes[data].linked_sources():
                if lsource not in ret:
                    ret.append(lsource)
        log.debug(f"get_sources {orgs} {cats} {countries} : {ret}")
        return ret

    def clean_docname(self, docname):
        """Clean all items where item.docname = docname
        """
        def _clean(data):
            for key, value in list(data.items()):
                if value.docname == docname:
                    data.pop(key)

        for dd in [self.orgs, self.idents, self.relations, self.events,
                self.links, self.sources, self.graphs, self.reports, self.csvs]:
            _clean(dd)

    def merge_quest(self, docname, quest):
        """Merge quest from parallel build in main quest
        """
        def _merge(quests):
            for main, other in quests:
                main.update(other)

        for dd in [(self.orgs, quest.orgs), (self.idents, quest.idents),
                   (self.relations, quest.relations), (self.events, quest.events),
                   (self.links, quest.links), (self.sources, quest.sources),
                   (self.graphs, quest.graphs), (self.reports, quest.reports),
                   (self.csvs, quest.csvs)]:
            _merge(dd)

    def local_file(self, fname, ext='pdf'):
        """Get the full local filename to store the source

        :param fname: The filename.
        :type fname: str
        :param ext: The extension.
        :type ext: str
        """
        return os.path.join(self.local_store, f"{fname}.{ext}")


class OSIntItem(OSIntBase):

    prefix = 'generic'
    default_style = 'solid'
    default_shape = 'circle'
    default_fillcolor = None
    default_color = None

    def __init__(self, name, label,
        description=None, content=None,
        cats=None, sources=None, country=None,
        default_cats=None, quest=None,
        docname=None, idx_entry=None, ref_entry=None, add_prefix=True,
        ids=None, **kwargs
    ):
        """The base representation in the OSIntQuest

        :param name: The name of the object. Must be unique in the quest.
        :type name: str
        :param label: The label of the object
        :type label: str
        :param description: The desciption of the ident.
            If None, label is used as description
        :type description: str or None
        :param content: The content of the ident.
            For future use.
        :type content: str or None
        :param cats: The categories of the object.
        :type cats: List of str or None
        :param sources: The categories of the object.
        :type sources: List of str or None
        :param default_cats: the categories of object
        :type default_cats: dict of cats
        :param quest: the quest to link to the object
        :type quest: OSIntQuest
        """
        if quest is None:
            raise RuntimeError('A quest must be defined')
        if name.startswith(self.prefix+'.') or not add_prefix:
            self.name = name
        else:
            self.name = f'{self.prefix}.{name}'
        self.label = label
        # ~ print(self.label)
        self.description = description if description is not None else label
        self.content = content
        self._cats = self.split_cats(cats)
        self.sources = self.split_sources(sources)
        self._country = country
        self._style = None
        self._shape = None
        self._fillcolor = None
        self._color = None
        self.default_cats = default_cats
        self.quest = quest
        self.idx_entry = idx_entry
        self.ref_entry = ref_entry
        self.docname = docname
        self.ids = ids
        self._linked_sources = None
        self.plugins_data = {}
        for ext in kwargs:
            self.plugins_data[ext] = kwargs[ext]

    def linked_sources(self, sources=None):
        """Get the links of the object"""
        if self._linked_sources is None:
            if sources is None:
                sources = self.sources
            self._linked_sources = []
            for src in sources:
                if src in self.sources:
                    self._linked_sources.append(src)
        return self._linked_sources

    @property
    def country(self):
        """Get the country of the object"""
        if self._country is None or self._country == '':
            self._country = self.quest.default_country
        return self._country

    @property
    def cats(self):
        """Get the cats of the object"""
        return self._cats

    @property
    def style(self):
        """Get the style of the object"""
        if self._style is None:
            if self.cats != [] and self.cats[0] in self.default_cats:
                self._style = self.default_cats[self.cats[0].replace(f'{OSIntOrg.prefix}.', '')]['style']
            elif 'default' in self.default_cats:
                self._style = self.default_cats['default']['style']
            else:
                self._style = self.default_style
        return self._style

    @property
    def shape(self):
        """Get the shape of the object"""
        if self._shape is None:
            if self.cats != [] and self.cats[0] in self.default_cats:
                self._shape = self.default_cats[self.cats[0].replace(f'{OSIntOrg.prefix}.', '')]['shape']
            elif 'default' in self.default_cats:
                self._shape = self.default_cats['default']['shape']
            else:
                self._shape = self.default_shape
        return self._shape

    @property
    def fillcolor(self):
        """Get the fillcolor of the object"""
        if self._fillcolor is None:
            if self.cats != [] and self.cats[0] in self.default_cats and 'fillcolor' in self.default_cats[self.cats[0]]:
                self._fillcolor = self.default_cats[self.cats[0].replace(f'{OSIntOrg.prefix}.', '')]['fillcolor']
            elif 'default' in self.default_cats and 'fillcolor' in self.default_cats['default']:
                self._fillcolor = self.default_cats['default']['fillcolor']
            else:
                self._fillcolor = self.default_fillcolor
        return self._fillcolor

    @property
    def color(self):
        """Get the color of the object"""
        if self._color is None:
            if self.cats != [] and self.cats[0] in self.default_cats and 'color' in self.default_cats[self.cats[0]]:
                self._color = self.default_cats[self.cats[0].replace(f'{OSIntOrg.prefix}.', '')]['color']
            elif 'default' in self.default_cats and 'color' in self.default_cats['default']:
                self._color = self.default_cats['default']['color']
            else:
                self._color = self.default_color
        return self._color


class OSIntOrg(OSIntItem):

    prefix = 'org'

    def __init__(self, name, label, **kwargs):
        """An organisation in the OSIntQuest

        :param name: The name of the OSIntOrg. Must be unique in the quest.
        :type name: str
        :param label: The label of the OSIntOrg
        :type label: str
        """
        super().__init__(name, label, **kwargs)
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)

    def linked_idents(self):
        """Get the idents of the object"""
        # ~ return [ idt.replace(f'{OSIntIdent.prefix}.', '') for idt in self.quest.get_idents(orgs=[self.name])]
        return self.quest.get_idents(orgs=[self.name])

    def linked_sources(self, sources=None, with_idents=False):
        """Get the links of the object"""
        if self._linked_sources is None:
            if sources is None:
                sources = self.sources
            self._linked_sources = []
            for src in sources:
                if src in self.sources:
                    self._linked_sources.append(src)
            if with_idents:
                idents = self.linked_idents()
                for ident in idents:
                    for src in self.quest.idents[ident].sources:
                        if src in self.sources:
                            self._linked_sources.append(src)
        return self._linked_sources

    def graph(self, idents, events, html_links=None):
        ret = f"""subgraph cluster_{self.name.replace(".", "_")} {{style="{self.style}";\n"""
        for ident in idents:
            if self.name in self.quest.idents[ident].orgs:
                ret += self.quest.idents[ident].graph(html_links=html_links)
        for event in events:
            if self.name in self.quest.events[event].orgs:
                ret += self.quest.events[event].graph(html_links=html_links)
        ret += '}\n\n'
        return ret


class OSIntIdent(OSIntItem):

    prefix = 'ident'

    def __init__(self, name, label, orgs=None, **kwargs):
        """An identitiy in the OSIntQuest

        :param name: The name of the OSIntIdent. Must be unique in the quest.
        :type name: str
        :param label: The label of the OSIntIdent
        :type label: str
        :param orgs: The organisations of the OSIntIdent.
        :type orgs: List of str or None
        """
        super().__init__(name, label, **kwargs)
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        self.orgs = self.split_orgs(orgs)
        self._linked_relations_from = None
        self._linked_relations_to = None
        self._linked_links_to = None

    @property
    def cats(self):
        """Get the cats of the ident"""
        if self._cats == [] and self.orgs != []:
            self._cats = self.quest.orgs[self.orgs[0]].cats
        return self._cats

    @property
    def country(self):
        """Get the country of the object"""
        if self._country is None or self._country == '':
            if self.orgs != []:
                self._country = self.quest.orgs[self.orgs[0]].country
            else:
                self._country = self.quest.default_country
        return self._country

    def linked_relations_from(self, relations=None):
        """Get the relations of the object"""
        if self._linked_relations_from is None:
            if relations is None:
                relations = self.quest.relations
            self._linked_relations_from = []
            for rel in relations:
                if self.quest.relations[rel].rfrom == self.name:
                    self._linked_relations_from.append(rel)
        return self._linked_relations_from

    def linked_relations_to(self, relations=None):
        """Get the relations of the object"""
        if self._linked_relations_to is None:
            if relations is None:
                relations = self.quest.relations
            self._linked_relations_to = []
            for rel in relations:
                if self.quest.relations[rel].rto == self.name:
                    self._linked_relations_to.append(rel)
        return self._linked_relations_to

    def linked_links_to(self, links=None):
        """Get the links of the object"""
        if self._linked_links_to is None:
            if links is None:
                links = self.quest.links
            self._linked_links_to = []
            for rel in links:
                if self.quest.links[rel].lfrom == self.name:
                    self._linked_links_to.append(rel)
        return self._linked_links_to

    def graph(self, html_links=None):
        if self.fillcolor is not None:
            fillcolor = f', fillcolor={self.fillcolor}'
        else:
            fillcolor = ''
        if self.color is not None:
            color = f', color={self.color}'
        else:
            color = ''
        if html_links is not None and self.name in html_links:
            url = f', url="{html_links[self.name]["refuri"]}"'
        else:
            url = ''
        # ~ print('url', self.name, html_links[self.name]["refuri"])
        # ~ link = f':osint:ref:`{self.name}`'
        # ~ fakenode = nodes.paragraph()
        # ~ nested_parse_with_titles(state, link, fakenode)
        # ~ print(fakenode, dir(fakenode))
        # ~ url = f'URL="rrrrrrrrrrr", target="_self", '
        return f"""{self.name.replace(".", "_")} [shape="{self.shape}", label="{self.label}", style="{self.style}"{fillcolor}{color}{url}];\n"""


class OSIntRelation(OSIntItem):

    prefix = 'relation'

    def __init__(self, label, rfrom, rto, begin=None, end=None, **kwargs):
        """A relation between 2 identities in the OSIntQuest

        :param name: The name of the object. Must be unique in the quest.
        :type name: str
        :param label: The label of the object
        :type label: str
        :param begin: The begin of the relation (yyyy/mm/dd)
        :type begin: str
        :param end: The end of the relation (yyyy/mm/dd). If end is None, end = begin
        :type end: str
        """
        if rfrom.startswith(f"{OSIntIdent.prefix}.") is False:
            self.rfrom = f"{OSIntIdent.prefix}.{rfrom}"
        else:
            self.rfrom = rfrom
        if rto.startswith(f"{OSIntIdent.prefix}.") is False:
            self.rto = f"{OSIntIdent.prefix}.{rto}"
        else:
            self.rto = rto
        name = f'{self.rfrom}__{label}__{self.rto}'
        # ~ super().__init__(name, label, add_prefix=False, **kwargs)
        super().__init__(name, label, **kwargs)
        self.begin, self.end = self.parse_dates(begin, end)
        self._linked_idents_from = None
        self._linked_idents_to = None

    @property
    def cats(self):
        """Get the cats of the object"""
        if len(self._cats) != 0:
            return self._cats
        return self.quest.idents[self.rfrom].cats + self.quest.idents[self.rto].cats

    def linked_idents_from(self):
        """Get the relations of the object"""
        if self._linked_idents_from is None:
            self._linked_idents_from = [self.name]
        return self._linked_idents_from

    def linked_idents_to(self):
        """Get the relations of the object"""
        if self._linked_idents_to is None:
            self._linked_idents_to = [self.name]
        return self._linked_idents_to

    def graph(self, html_links=None):
        if self.color is not None:
            color = f', color={self.color}'
        else:
            color = ''
        return f"""{self.rfrom.replace(".", "_")} -> {self.rto.replace(".", "_")} [label="{self.label}"{color}];\n"""


class OSIntEvent(OSIntItem):

    prefix = 'event'
    default_style = 'dashed'
    default_shape = 'folder'

    def __init__(self, name, label, begin=None, end=None, orgs=None, **kwargs):
        """An event in the OSIntQuest

        :param name: The name of the object. Must be unique in the quest.
        :type name: str
        :param label: The label of the object
        :type label: str
        :param begin: The begin of the relation (yyyy/mm/dd)
        :type begin: str
        :param end: The end of the relation (yyyy/mm/dd). If end is None, end = begin
        :type end: str
        """
        super().__init__(name, label, **kwargs)
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        self.begin, self.end = self.parse_dates(begin, end)
        self.orgs = self.split_orgs(orgs)
        self._linked_links_from = None

    def linked_links_from(self, link=None):
        """Get the links of the object"""
        if self._linked_links_from is None:
            if link is None:
                link = self.quest.links
            self._linked_links_from = []
            for rel in link:
                if self.quest.links[rel].lfrom == self.name:
                    self._linked_links_from.append(rel)
        return self._linked_links_from

    def graph(self, html_links=None):
        # ~ print('self.style', self.style)
        if self.fillcolor is not None:
            fillcolor = f', fillcolor={self.fillcolor}'
        else:
            fillcolor = ''
        if self.color is not None:
            color = f', color={self.color}'
        else:
            color = ''
        return f"""{self.name.replace(".", "_")} [shape="{self.shape}", label="{self.label}", style="{self.style}"{fillcolor}{color}];\n"""


class OSIntLink(OSIntItem):

    prefix = 'link'

    def __init__(self, label, lfrom, lto, begin=None, end=None, **kwargs):
        """A link between an identity and an event in the OSIntQuest

        :param name: The name of the object. Must be unique in the quest.
        :type name: str
        :param label: The label of the object
        :type label: str
        :param begin: The begin of the relation (yyyy/mm/dd)
        :type begin: str
        :param end: The end of the relation (yyyy/mm/dd). If end is None, end = begin + 1 day
        :type end: str
        """
        if lfrom.startswith(f"{OSIntIdent.prefix}.") is False:
            self.lfrom = f"{OSIntIdent.prefix}.{lfrom}"
        else:
            self.lfrom = lfrom
        if lto.startswith(f"{OSIntEvent.prefix}.") is False:
            self.lto = f"{OSIntEvent.prefix}.{lto}"
        else:
            self.lto = lto
        self.begin, self.end = self.parse_dates(begin, end)
        name = f'{self.lfrom}__{label}__{self.lto}'
        # ~ super().__init__(name, label, add_prefix=False, **kwargs)
        super().__init__(name, label, **kwargs)
        self._linked_idents_from = None
        self._linked_events_to = None

    @property
    def cats(self):
        """Get the cats of the object"""
        if len(self._cats) != 0:
            return self._cats
        return self.quest.idents[self.lfrom].cats + self.quest.events[self.lto].cats

    def linked_idents_from(self):
        """Get the relations of the object"""
        if self._linked_idents_from is None:
            self._linked_idents_from = [self.name]
        return self._linked_idents_from

    def linked_events_to(self):
        """Get the relations of the object"""
        if self._linked_events_to is None:
            self._linked_events_to = [self.name]
        return self._linked_events_to

    def graph(self, html_links=None):
        if self.color is not None:
            color = f', color={self.color}'
        else:
            color = ''
        return f"""{self.lfrom.replace(".", "_")} -> {self.lto.replace(".", "_")} [label="{self.label}"{color}];\n"""


class OSIntQuote(OSIntItem):

    prefix = 'quote'

    def __init__(self, label, qfrom, qto, **kwargs):
        """A quote between an identity and an event in the OSIntQuest

        :param name: The name of the object. Must be unique in the quest.
        :type name: str
        :param label: The label of the object
        :type label: str
        :param begin: The begin of the relation (yyyy/mm/dd)
        :type begin: str
        :param end: The end of the relation (yyyy/mm/dd). If end is None, end = begin + 1 day
        :type end: str
        """
        if qfrom.startswith(f"{OSIntEvent.prefix}.") is False:
            self.qfrom = f"{OSIntEvent.prefix}.{qfrom}"
        else:
            self.qfrom = qfrom
        if qto.startswith(f"{OSIntEvent.prefix}.") is False:
            self.qto = f"{OSIntEvent.prefix}.{qto}"
        else:
            self.qto = qto
        name = f'{self.qfrom}__{label}__{self.qto}'
        # ~ super().__init__(name, label, add_prefix=False, **kwargs)
        super().__init__(name, label, **kwargs)

    @property
    def cats(self):
        """Get the cats of the object"""
        if len(self._cats) != 0:
            return self._cats
        return self.quest.events[self.qfrom].cats + self.quest.events[self.qto].cats

    def graph(self, html_links=None):
        if self.color is not None:
            color = f', color={self.color}'
        else:
            color = ''
        return f"""{self.qfrom.replace(".", "_")} -> {self.qto.replace(".", "_")} [label="{self.label}"{color}];\n"""


class OSIntSource(OSIntItem):

    prefix = 'source'

    def __init__(self, name, label, orgs=None,
        url=None, link=None, local=None, download=None, scrap=None, youtube=None,
        auto_download=False, **kwargs
    ):
        """A source in the OSIntQuest

        :param name: The name of the object. Must be unique in the quest.
        :type name: str
        :param label: The label of the object
        :type label: str
        :param url: The url of the source. The url will be downloaded and stored locally as pdf.
        :type url: str
        :param local: The link of the source. The link will be linked.
        :type local: str
        :param link: The link of the source. The link will be linked.
        :type link: str
        :param download: The download of the source. The file will be downloaded and stored locally.
        :type download: str
        """
        from . import osint_plugins
        super().__init__(name, label, **kwargs)
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        self.url = url
        self.link = link
        self.local = local
        self.download = download
        self.auto_download = auto_download
        self.scrap = scrap
        self.youtube = youtube
        self.orgs = self.split_orgs(orgs)
        # ~ print('uuuuuuuuuurl', self.url)
        for plg in osint_plugins['source'] + osint_plugins['directive']:
            plg.init_source(self.quest.sphinx_env, self)
        # ~ if self.auto_download and self.url is not None:
            # ~ self.pdf(os.path.join(self.quest.sphinx_env.srcdir, self.quest.cache_file(self.name)), self.url)
        self._linked_orgs = None
        self._linked_idents = None
        self._linked_relations = None
        self._linked_events = None
        self._linked_links = None

    def linked_orgs(self, orgs=None):
        """Get the orgs linked to the object"""
        if self._linked_orgs is None:
            self._linked_orgs = []
            if orgs is None:
                orgs = self.quest.orgs
            for org in orgs:
                if self.name in self.quest.orgs[org].sources:
                    self._linked_orgs.append(org)
        return self._linked_orgs

    def linked_idents(self, idents=None):
        """Get the idents linked to the object"""
        if self._linked_idents is None:
            self._linked_idents = []
            if idents is None:
                idents = self.quest.idents
            for idt in idents:
                if self.name in self.quest.idents[idt].sources:
                    self._linked_idents.append(idt)
        return self._linked_idents

    def linked_relations(self, relations=None):
        """Get the idents linked to the object"""
        if self._linked_relations is None:
            self._linked_relations = []
            if relations is None:
                relations = self.quest.relations
            for idt in relations:
                if self.name in self.quest.relations[idt].sources:
                    self._linked_relations.append(idt)
        return self._linked_relations

    def linked_events(self, events=None):
        """Get the events linked to the object"""
        if self._linked_events is None:
            self._linked_events = []
            if events is None:
                events = self.quest.events
            for idt in events:
                if self.name in self.quest.events[idt].sources:
                    self._linked_events.append(idt)
        return self._linked_events

    def linked_links(self, links=None):
        """Get the idents linked to the object"""
        if self._linked_links is None:
            self._linked_links = []
            if links is None:
                links = self.quest.links
            for idt in links:
                if self.name in self.quest.links[idt].sources:
                    self._linked_links.append(idt)
        return self._linked_links

    def pdf(self, localf, url, timeout=30):
        import pdfkit
        log.debug("osint_source %s to %s" % (url, localf))
        if os.path.isfile(localf):
            return
        try:
            with self.time_limit(timeout):
                pdfkit.from_url(url, localf)
        except Exception:
            log.exception('Exception downloading %s to %s' %(url, localf))

    def scrap(self, sig, url):
        pass
        # ~ import subprocess
        # ~ locald = self.local_site(sig)
        # ~ if os.path.isdir(locald):
            # ~ return
        # ~ os.makedirs(locald, exist_ok=True)
        # ~ try:
            # ~ result = subprocess.run(["httrack", "--mirror", url], capture_output=True, text=True, cwd=locald)
        # ~ except Exception:
            # ~ log.exception('Exception scraping %s to %s' %(url, sig))


class OSIntGraph(OSIntBase):

    prefix = 'graph'
    default_graphviz_dot = 'sfdp'

    def __init__(self, name, label,
        description=None, content=None,
        cats=None, orgs=None, idents=None, begin=None, end=None, countries=None, borders=True,
        alt=None, align=None, style=None, caption=None, layout=None, graphviz_dot=None,
        docname=None, idx_entry=None, quest=None,
        **kwargs
    ):
        """A graph in the OSIntQuest

        Extract and filter data for representation

        :param name: The name of the graph. Must be unique in the quest.
        :type name: str
        :param label: The label of the graph
        :type label: str
        :param description: The desciption of the graph.
            If None, label is used as description
        :type description: str or None
        :param content: The content of the graph.
            For future use.
        :type content: str or None
        :param cats: The categories of the graph.
        :type cats: List of str or None
        :param orgs: The orgs of the graph.
        :type orgs: List of str or None
        :param years: the years of graph
        :type years: list of str or None
        :param quest: the quest to link to the graph
        :type quest: OSIntQuest
        """
        if quest is None:
            raise RuntimeError('A quest must be defined')
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        if name.startswith(self.prefix+'.'):
            self.name = name
        else:
            self.name = f'{self.prefix}.{name}'
        self.label = label
        self.description = description if description is not None else label
        self.content = content
        self.cats = self.split_cats(cats)
        self.idents = self.split_idents(idents)
        self.orgs = self.split_orgs(orgs)
        self.begin, self.end = self.parse_dates(begin, end)
        self.countries = self.split_countries(countries)
        self.quest = quest
        self.alt = alt
        self.align = align
        self.style = style
        self.caption = caption
        self.layout = layout
        self.graphviz_dot = graphviz_dot
        self.idx_entry = idx_entry
        self.docname = docname
        self.borders = borders

    def graph(self, html_links=None):
        """Graph it
        """
        # ~ print('html_links', html_links)
        orgs, all_idents, relations, events, links, quotes, sources = \
            self.data_filter(self.cats, self.orgs, self.begin, self.end,
            self.countries, self.idents, borders=self.borders)
        orgs, all_idents, relations, events, links, quotes, sources = \
            self.data_complete(orgs, all_idents, relations, events, links, quotes,
            sources, self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        orgs, all_idents, lonely_idents, relations, events, lonely_events, links, quotes, sources = \
            self.data_group_orgs(orgs, all_idents, relations, events, links, quotes, sources,
            self.cats, self.orgs, self.begin, self.end, self.countries)
        ret = f'digraph {self.name.replace(".", "_")}' + ' {\n'
        for o in orgs:
            ret += self.quest.orgs[o].graph(all_idents, events, html_links=html_links)
        for e in lonely_events:
            ret += self.quest.events[e].graph(html_links=html_links)
        ret += '\n'
        for i in lonely_idents:
            ret += self.quest.idents[i].graph(html_links=html_links)
        ret += '\n'
        relations = list(set(relations))
        for r in relations:
            ret += self.quest.relations[r].graph(html_links=html_links)
        ret += '\n'
        for ll in links:
            ret += self.quest.links[ll].graph(html_links=html_links)
        ret += '\n'
        for q in quotes:
            ret += self.quest.quotes[q].graph(html_links=html_links)
        ret += '\n}\n'
        # ~ print(ret)
        return ret


class OSIntReport(OSIntBase):

    prefix = 'report'

    def __init__(self, name, label,
        description=None, content=None,
        cats=None, orgs=None, idents=None, begin=None, end=None, countries=None, borders=True,
        caption=None, idx_entry=None, quest=None, docname=None,
        **kwargs
    ):
        """A report in the OSIntQuest

        Extract and filter data for representation

        :param name: The name of the graph. Must be unique in the quest.
        :type name: str
        :param label: The label of the graph
        :type label: str
        :param description: The desciption of the graph.
            If None, label is used as description
        :type description: str or None
        :param content: The content of the graph.
            For future use.
        :type content: str or None
        :param cats: The categories of the graph.
        :type cats: List of str or None
        :param orgs: The orgs of the graph.
        :type orgs: List of str or None
        :param years: the years of graph
        :type years: list of str or None
        :param quest: the quest to link to the graph
        :type quest: OSIntQuest
        """
        if quest is None:
            raise RuntimeError('A quest must be defined')
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        if name.startswith(self.prefix+'.'):
            self.name = name
        else:
            self.name = f'{self.prefix}.{name}'
        self.label = label
        self.description = description if description is not None else label
        self.content = content
        self.cats = self.split_cats(cats)
        self.idents = self.split_idents(idents)
        self.orgs = self.split_orgs(orgs)
        self.begin, self.end = self.parse_dates(begin, end)
        self.countries = self.split_countries(countries)
        self.quest = quest
        self.caption = caption
        self.idx_entry = idx_entry
        self.docname = docname
        self.borders = borders
        self.links = {}

    def add_link(self, docname, key, link):
        if docname not in self.links:
            self.links[docname] = {}
        self.links[docname][key] = link

    def report(self):
        """Report it
        """
        orgs, all_idents, relations, events, links, quotes, sources = self.data_filter(self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        orgs, all_idents, relations, events, links, quotes, sources = self.data_complete(orgs, all_idents, relations, events, links, quotes, sources, self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        return orgs, all_idents, relations, events, links, quotes, sources


class OSIntCsv(OSIntBase):

    prefix = 'csv'

    def __init__(self, name, label,
        description=None, content=None, with_json=False,
        cats=None, orgs=None, idents=None, begin=None, end=None, countries=None, borders=True,
        caption=None, idx_entry=None, quest=None, docname=None,
        csv_store=None, **kwargs
    ):
        """A csv in the OSIntQuest

        Extract and filter data for representation

        :param name: The name of the graph. Must be unique in the quest.
        :type name: str
        :param label: The label of the graph
        :type label: str
        :param description: The desciption of the graph.
            If None, label is used as description
        :type description: str or None
        :param content: The content of the graph.
            For future use.
        :type content: str or None
        :param cats: The categories of the graph.
        :type cats: List of str or None
        :param orgs: The orgs of the graph.
        :type orgs: List of str or None
        :param years: the years of graph
        :type years: list of str or None
        :param quest: the quest to link to the graph
        :type quest: OSIntQuest
        """
        if quest is None:
            raise RuntimeError('A quest must be defined')
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        if name.startswith(self.prefix+'.'):
            self.name = name
        else:
            self.name = f'{self.prefix}.{name}'
        self.label = label
        self.description = description if description is not None else label
        self.content = content
        self.cats = self.split_cats(cats)
        self.idents = self.split_idents(idents)
        self.orgs = self.split_orgs(orgs)
        self.begin, self.end = self.parse_dates(begin, end)
        self.countries = self.split_countries(countries)
        self.quest = quest
        self.caption = caption
        self.idx_entry = idx_entry
        self.docname = docname
        self.csv_store = csv_store
        self.borders = borders
        self.with_json = with_json

    @classmethod
    @reify
    def _imp_csv(cls):
        """Lazy loader for import csv"""
        import importlib
        return importlib.import_module('csv')

    def export(self):
        """Csv it
        """
        from . import osint_plugins, call_plugin, check_plugin

        orgs, all_idents, relations, events, links, quotes, sources = self.data_filter(self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        orgs, all_idents, relations, events, links, quotes, sources = self.data_complete(orgs, all_idents, relations, events, links, quotes, sources, self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)

        orgs_file = os.path.join(self.csv_store, f'{self.name.split(".")[1]}_orgs.csv')
        with open(orgs_file, 'w') as csvfile:
            spamwriter = self._imp_csv.writer(csvfile, quoting=self._imp_csv.QUOTE_ALL)
            spamwriter.writerow(['name', 'label', 'description', 'content', 'cats', 'country'])
            dorgs = self.quest.orgs
            for org in orgs:
                spamwriter.writerow([dorgs[org].name, dorgs[org].label, dorgs[org].description,
                    dorgs[org].content, ','.join(dorgs[org].cats), dorgs[org].country])

        idents_file = os.path.join(self.csv_store, f'{self.name.split(".")[1]}_idents.csv')
        with open(idents_file, 'w') as csvfile:
            spamwriter = self._imp_csv.writer(csvfile, quoting=self._imp_csv.QUOTE_ALL)
            spamwriter.writerow(['name', 'label', 'description', 'content', 'orgs', 'cats', 'country'])
            didents = self.quest.idents
            for ident in all_idents:
                spamwriter.writerow([didents[ident].name, didents[ident].label, didents[ident].description,
                    didents[ident].content, ','.join(didents[ident].orgs), ','.join(didents[ident].cats),
                    didents[ident].country])

        events_file = os.path.join(self.csv_store, f'{self.name.split(".")[1]}_events.csv')
        with open(events_file, 'w') as csvfile:
            spamwriter = self._imp_csv.writer(csvfile, quoting=self._imp_csv.QUOTE_ALL)
            spamwriter.writerow(['name', 'label', 'description', 'content', 'begin', 'end', 'cats', 'country'])
            devents = self.quest.events
            for event in events:
                spamwriter.writerow([devents[event].name, devents[event].label, devents[event].description,
                    devents[event].begin, devents[event].end,
                    devents[event].content, ','.join(devents[event].cats), devents[event].country])

        relations_file = os.path.join(self.csv_store, f'{self.name.split(".")[1]}_relations.csv')
        with open(relations_file, 'w') as csvfile:
            spamwriter = self._imp_csv.writer(csvfile, quoting=self._imp_csv.QUOTE_ALL)
            spamwriter.writerow(['name', 'label', 'description', 'content', 'from', 'to', 'begin', 'end', 'cats'])
            drelations = self.quest.relations
            for relation in relations:
                spamwriter.writerow([drelations[relation].name, drelations[relation].label,
                    drelations[relation].description, drelations[relation].content,
                    drelations[relation].rfrom, drelations[relation].rto,
                    drelations[relation].begin, drelations[relation].end,
                    ','.join(drelations[relation].cats)])

        links_file = os.path.join(self.csv_store, f'{self.name.split(".")[1]}_links.csv')
        with open(links_file, 'w') as csvfile:
            spamwriter = self._imp_csv.writer(csvfile, quoting=self._imp_csv.QUOTE_ALL)
            spamwriter.writerow(['name', 'label', 'description', 'content', 'from', 'to', 'cats'])
            dlinks = self.quest.links
            for link in links:
                spamwriter.writerow([dlinks[link].name, dlinks[link].label,
                    dlinks[link].description, dlinks[link].content,
                    dlinks[link].lfrom, dlinks[link].lto,
                    ','.join(dlinks[link].cats)])

        quotes_file = os.path.join(self.csv_store, f'{self.name.split(".")[1]}_quotes.csv')
        with open(quotes_file, 'w') as csvfile:
            spamwriter = self._imp_csv.writer(csvfile, quoting=self._imp_csv.QUOTE_ALL)
            spamwriter.writerow(['name', 'label', 'description', 'content', 'from', 'to', 'cats'])
            dquotes = self.quest.quotes
            for quote in quotes:
                spamwriter.writerow([dquotes[quote].name, dquotes[quote].label,
                    dquotes[quote].description, dquotes[quote].content,
                    dquotes[quote].qfrom, dquotes[quote].qto,
                    ','.join(dquotes[quote].cats)])

        sources_file = os.path.join(self.csv_store, f'{self.name.split(".")[1]}_sources.csv')
        with open(sources_file, 'w') as csvfile:
            spamwriter = self._imp_csv.writer(csvfile, quoting=self._imp_csv.QUOTE_ALL)

            cols = ['name', 'label', 'description', 'content', 'url', 'link', 'youtube', 'local', 'cats']
            json_plgs = []
            if self.with_json is True:
                if 'directive' in osint_plugins:
                    for plg in osint_plugins['directive'] + osint_plugins['source']:
                        domain = self.quest.sphinx_env.get_domain("osint")
                        if check_plugin(domain, plg, 'load_json_%s_source'):
                            cols += [plg.name]
                            json_plgs += [plg]
            spamwriter.writerow(cols)

            dsources = self.quest.sources
            for source in sources:
                data = [dsources[source].name, dsources[source].label,
                    dsources[source].description, dsources[source].content,
                    dsources[source].url, dsources[source].link, dsources[source].youtube, dsources[source].local,
                    ','.join(dsources[source].cats)]
                if self.with_json is True:
                    for plg in json_plgs:
                        data.append(call_plugin(domain, plg, 'load_json_%s_source', source.replace(f'{OSIntSource.prefix}.', '')))
                spamwriter.writerow(data)

        return orgs_file, idents_file, events_file, relations_file, links_file, quotes_file, sources_file
