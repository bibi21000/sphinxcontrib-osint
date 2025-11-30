# -*- encoding: utf-8 -*-
"""
The carto plugin
------------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import copy
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.locale import __
from sphinx.util import logging, texescape
from typing import ClassVar, cast
from docutils.nodes import Node
from sphinx.util.nodes import make_id
from sphinx.util.typing import OptionSpec
from sphinx.writers.html5 import HTML5Translator
from sphinx.writers.latex import LaTeXTranslator

from .. import option_main, option_reports, yesno
from ..osintlib import Index, OSIntOrg, OSIntRelated
from . import reify, PluginDirective, SphinxDirective

logger = logging.getLogger(__name__)


class Carto(PluginDirective):
    """
    """
    name = 'carto'
    order = 5

    @classmethod
    def add_events(cls, app):
        app.add_event('carto-defined')

    @classmethod
    def add_nodes(cls, app):
        app.add_node(carto_node,
            html=(visit_carto_node, depart_carto_node),
            latex=(latex_visit_carto_node, latex_depart_carto_node),
            text=(visit_carto_node, depart_carto_node),
            man=(visit_carto_node, depart_carto_node),
            texinfo=(visit_carto_node, depart_carto_node))

    # ~ @classmethod
    # ~ def Indexes(cls):
        # ~ return [IndexCarto]

    @classmethod
    def related(self):
        return ['cartos']

    @classmethod
    def Directives(cls):
        return [DirectiveCarto]

    def process_xref(self, env, osinttyp, target):
        """Get xref data"""
        if osinttyp == 'carto':
            return env.domains['osint'].quest.cartos[target]
        return None

    @classmethod
    def extend_domain(cls, domain):

        global get_entries_cartos
        def get_entries_cartos(domain, orgs=None, idents=None, cats=None, countries=None, related=False):
            logger.debug(f"get_entries_cartos {cats} {countries}")
            ret = []
            for i in domain.quest.get_cartos(cats=cats, countries=countries):
                try:
                    ret.append(domain.quest.cartos[i].idx_entry)
                except Exception as e:
                    logger.warning(__("Can't get_entries_cartos : %s"), str(e))
            return ret
        domain.get_entries_cartos = get_entries_cartos

        global add_carto
        def add_carto(domain, signature, label, node, options):
            """Add a new carto to the domain."""
            prefix = OSIntCarto.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_carto %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            try:
                domain.quest.add_carto(name, label, idx_entry=entry, **options)
            except Exception as e:
                logger.warning(__("Can't add carto %s(%s) : %s"), node["osint_name"], node["docname"], str(e),
                    location=node)
        domain.add_carto = add_carto

        global resolve_xref_carto
        """Resolve reference for index"""
        def resolve_xref_carto(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'carto':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_cartos() if sig == target]
                return match
            return []
        domain.resolve_xref_carto = resolve_xref_carto

        global process_doc_carto
        """Process doc"""
        def process_doc_carto(domain, env, docname, document):
            for carto in document.findall(carto_node):
                env.app.emit('carto-defined', carto)
                options = {key: copy.deepcopy(value) for key, value in carto.attributes.items()}
                osint_name = options.pop('osint_name')
                if 'label' in options:
                    label = options.pop('label')
                else:
                    label = osint_name
                domain.add_carto(osint_name, label, carto, options)
                if env.config.osint_emit_related_warnings:
                    logger.warning(__("TIMELINE entry found: %s"), carto["osint_name"],
                                   location=carto)
        domain.process_doc_carto = process_doc_carto

    @classmethod
    def extend_processor(cls, processor):

        global process_carto
        def process_carto(processor, doctree: nodes.document, docname: str, domain):
            '''Process the node'''

            for node in list(doctree.findall(carto_node)):
                if node["docname"] != docname:
                    continue

                carto_name = node["osint_name"]

                target_id = f'{OSIntCarto.prefix}--{make_id(processor.env, processor.document, "", carto_name)}'
                # ~ target_node = nodes.target('', '', ids=[target_id])
                container = nodes.section(ids=[target_id])

                if 'caption' in node:
                    title_node = nodes.title('carto', node['caption'])
                    container.append(title_node)

                if 'description' in node:
                    description_node = nodes.paragraph(text=node['description'])
                    container.append(description_node)
                    alttext = node['description']
                else:
                    alttext = domain.quest.cartos[ f'{OSIntCarto.prefix}.{carto_name}'].sdescription

                try:

                    output_dir = os.path.join(processor.env.app.outdir, '_images')
                    filename = domain.quest.cartos[ f'{OSIntCarto.prefix}.{carto_name}'].graph(output_dir)

                    paragraph = nodes.paragraph('', '')

                    image_node = nodes.image()
                    image_node['uri'] = f'/_images/{filename}'
                    image_node['candidates'] = '?'
                    image_node['alt'] = alttext
                    paragraph += image_node

                    container.append(paragraph)

                except Exception as e:
                    logger.warning(__("Can't create carto %s : %s"), node["osint_name"], str(e),
                               location=node)

                node.replace_self(container)

        processor.process_carto = process_carto

    @classmethod
    def extend_quest(cls, quest):

        quest._cartos = None
        global cartos
        @property
        def cartos(quest):
            if quest._cartos is None:
                quest._cartos = {}
            return quest._cartos
        quest.cartos = cartos

        global add_carto
        def add_carto(quest, name, label, **kwargs):
            """Add carto data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            carto = OSIntCarto(name, label, quest=quest, **kwargs)
            quest.cartos[carto.name] = carto
        quest.add_carto = add_carto

        global get_cartos
        def get_cartos(quest, orgs=None, cats=None, countries=None, begin=None, end=None):
            """Get cartos from the quest

            :param orgs: The orgs for filtering cartos.
            :type orgs: list of str
            :param cats: The cats for filtering cartos.
            :type cats: list of str
            :param countries: The countries for filtering cartos.
            :type countries: list of str
            :returns: a list of cartos
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.cartos.keys())
            else:
                ret_orgs = []
                for carto in quest.cartos.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.cartos[carto].orgs:
                            ret_orgs.append(carto)
                            break
            logger.debug(f"get_cartos {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for carto in ret_orgs:
                    for cat in cats:
                        if cat in quest.cartos[carto].cats:
                            ret_cats.append(carto)
                            break
            logger.debug(f"get_cartos {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for carto in ret_cats:
                    for country in countries:
                        if country == quest.cartos[carto].country:
                            ret_countries.append(carto)
                            break

            logger.debug(f"get_cartos {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_cartos = get_cartos


class carto_node(nodes.General, nodes.Element):
    pass

def visit_carto_node(self: HTML5Translator, node: carto_node) -> None:
    self.visit_admonition(node)

def depart_carto_node(self: HTML5Translator, node: carto_node) -> None:
    self.depart_admonition(node)

def latex_visit_carto_node(self: LaTeXTranslator, node: carto_node) -> None:
    self.body.append('\n\\begin{osintcarto}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_carto_node(self: LaTeXTranslator, node: carto_node) -> None:
    self.body.append('\\end{osintcarto}\n')
    self.no_latex_floats -= 1


class IndexCarto(Index):
    """An index for cartos."""

    name = 'cartos'
    localname = 'Cartos Index'
    shortname = 'Cartos'

    def get_datas(self):
        datas = self.domain.get_entries_cartos()
        datas = sorted(datas, key=lambda data: data[1])
        return datas

class OSIntCarto(OSIntRelated):

    prefix = 'carto'

    regions = {
        'africa': [-20, 60, -40, 40],
        'europe': [-20, 40, 35, 70],
        'arctic': [-12, 90, 50, 90],
    }

    @classmethod
    @reify
    def _imp_matplotlib_pyplot(cls):
        """Lazy loader for import matplotlib.pyplot"""
        import importlib
        return importlib.import_module('matplotlib.pyplot')

    @classmethod
    @reify
    def _imp_matplotlib_colors(cls):
        """Lazy loader for import matplotlib.colors"""
        import importlib
        return importlib.import_module('matplotlib.colors')

    @classmethod
    @reify
    def _imp_matplotlib_path(cls):
        """Lazy loader for import matplotlib.path"""
        import importlib
        return importlib.import_module('matplotlib.path')

    @classmethod
    @reify
    def _imp_cartopy_crs(cls):
        """Lazy loader for import cartopy.crs"""
        import importlib
        return importlib.import_module('cartopy.crs')

    @classmethod
    @reify
    def _imp_cartopy_feature(cls):
        """Lazy loader for import cartopy.feature"""
        import importlib
        return importlib.import_module('cartopy.feature')

    @classmethod
    @reify
    def _imp_numpy(cls):
        """Lazy loader for import numpy"""
        import importlib
        return importlib.import_module('numpy')

    @classmethod
    @reify
    def _imp_geopy_geocoders(cls):
        """Lazy loader for import geopy.geocoders"""
        import importlib
        return importlib.import_module('geopy.geocoders')

    @classmethod
    @reify
    def _imp_pycountry(cls):
        """Lazy loader for import pycountry"""
        import importlib
        return importlib.import_module('pycountry')

    def __init__(self, name, label, width=900, height=450,
            data_countries=None, data_object=None, data_coordinates=None,
            dpi=300, fontsize=9, color='black', region=None, projection='Robinson',
            marker='o', marker_min_size=10, marker_max_size=100, marker_color='red',
            **kwargs
        ):
        """A carto in the OSIntQuest
        """
        super().__init__(name, label, **kwargs)
        self.data_object = data_object
        self.data_countries = data_countries
        self.data_coordinates = data_coordinates
        if data_object is None and data_countries is None and data_coordinates is None:
            raise RuntimeError("Can't find data for %s"%self.name)
        self.width = width
        self.height = height
        self.dpi = dpi
        self.color = color
        self.projection = projection
        self.region = region
        self.marker = marker
        self.marker_min_size = marker_min_size
        self.marker_max_size = marker_max_size
        self.marker_color = marker_color
        self.marker = marker
        self.fontsize = fontsize
        self.filepath = None

    def graph(self, output_dir):
        """Graph it
        """
        country_data = {}
        if self.data_object is not None:
            dobjs = getattr(self.quest, "get_%s"%self.data_object)(orgs=self.orgs, cats=self.cats, countries=self.countries, idents=self.idents)
            for dobj in dobjs:
                obj = getattr(self.quest, "%s"%self.data_object)[dobj]
                if obj.country not in country_data:
                    country_data[obj.country] = {'value': 1, 'color':self.marker_color}
                else:
                    country_data[obj.country]['value'] += 1
        elif self.data_coordinates is not None:
            # city:latitude:longitude:value:color
            for item in self.data_coordinates.split(','):
                item = item.strip()
                ds = item.split(':')
                if len(ds) < 3:
                    pass
                else:
                    if len(ds) == 3:
                        code = ds[0].strip().upper()
                        latitude = float(ds[1].strip())
                        longitude = float(ds[2].strip())
                        value = float(self.marker_min_size)
                        color = self.marker_color
                    elif len(ds) == 4:
                        code = ds[0].strip().upper()
                        latitude = float(ds[1].strip())
                        longitude = float(ds[2].strip())
                        try:
                            value = float(ds[3].strip())
                            color = self.marker_color
                        except ValueError:
                            value = float(self.marker_min_size)
                            color = ds[3].strip()
                    elif len(ds) == 5:
                        code = ds[0].strip().upper()
                        latitude = float(ds[1].strip())
                        longitude = float(ds[2].strip())
                        value = float(ds[3].strip())
                        color = ds[4].strip()
                    country_data[code] = {'latitude': latitude, 'longitude': longitude, 'value': value, 'color':color}
        else:
            for item in self.data_countries.split(','):
                item = item.strip()
                ds = item.split(':')
                if len(ds) == 1:
                    code = ds[0].strip().upper()
                    value = float(self.marker_min_size)
                    color = self.marker_color
                elif len(ds) == 2:
                    code = ds[0].strip().upper()
                    try:
                        value = float(ds[1].strip())
                        color = self.marker_color
                    except ValueError:
                        value = float(self.marker_min_size)
                        color = ds[1].strip()
                elif len(ds) == 3:
                    code = ds[0].strip().upper()
                    value = float(ds[1].strip())
                    color = ds[2].strip()
                country_data[code] = {'value': value, 'color':color}

        filename = f'{self.prefix}_{hash(self.name)}_{self.width}x{self.height}.jpg'
        filepath = os.path.join(output_dir, filename)

        geolocator = self._imp_geopy_geocoders.Nominatim(user_agent="sphinx_osint")

        coordinates = {}
        values = []

        for code, value in country_data.items():
            if 'latitude' in value:
                coordinates[code] = (value['longitude'], value['latitude'])
                values.append(value['value'])
            else:
                try:
                    country = self._imp_pycountry.countries.get(alpha_2=code)
                    if country:
                        try:
                            location = geolocator.geocode(country.official_name, timeout=10)
                            if location:
                                coordinates[code] = (location.longitude, location.latitude)
                                values.append(value['value'])
                        except AttributeError:
                            try:
                                location = geolocator.geocode(country.common_name, timeout=10)
                                if location:
                                    coordinates[code] = (location.longitude, location.latitude)
                                    values.append(value['value'])
                            except AttributeError:
                                location = geolocator.geocode(country.name, timeout=10)
                                if location:
                                    coordinates[code] = (location.longitude, location.latitude)
                                    values.append(value['value'])
                except Exception:
                    logger.exception(f"Error for {code}")
                    continue

        if not coordinates:
            raise ValueError("No coordinates for countries")

        self._imp_matplotlib_pyplot.figure(figsize=(self.width / self.dpi, self.height / self.dpi))
        # ~ ax = self._imp_matplotlib_pyplot.axes(projection=self._imp_cartopy_crs.Robinson())
        ax = self._imp_matplotlib_pyplot.axes(projection=getattr(self._imp_cartopy_crs, self.projection)())
        ax.add_feature(self._imp_cartopy_feature.LAND, facecolor='lightgray')
        ax.add_feature(self._imp_cartopy_feature.OCEAN, facecolor='lightblue')
        ax.add_feature(self._imp_cartopy_feature.COASTLINE, linewidth=0.3)
        ax.add_feature(self._imp_cartopy_feature.BORDERS, linewidth=0.2, alpha=0.5)
        if self.region is None:
            ax.set_global()
        elif self.region in self.regions:
            ax.set_extent(self.regions[self.region])
        else:
            try:
                x1,x2,x3,x4 = self.region.split(',')
                ax.set_extent([x1,x2,x3,x4], self._imp_cartopy_crs.PlateCarree())
            except ValueError:
                logger.exception("Error in %s carto. region must be x1,x2,x3,x4" %self.name)
                raise

        if self.projection in ['NorthPolarStereo', 'SouthPolarStereo']:
            theta = self._imp_numpy.linspace(0, 2*self._imp_numpy.pi, 200)
            center, radius = [0.5, 0.5], 0.5
            verts = self._imp_numpy.vstack([self._imp_numpy.sin(theta), self._imp_numpy.cos(theta)]).T
            circle = self._imp_matplotlib_path.Path(verts * radius + center)

            ax.set_boundary(circle, transform=ax.transAxes)

        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val if max_val != min_val else 1
        for code, (lon, lat) in coordinates.items():
            value = country_data[code]['value']
            color = country_data[code]['color']

            normalized = (value - min_val) / val_range
            marker_size = self.marker_min_size + (self.marker_max_size - self.marker_min_size) * normalized

            ax.plot(lon, lat, color=color, marker=self.marker, markersize=marker_size**0.5,
                alpha=0.6, transform=self._imp_cartopy_crs.PlateCarree())

            # ~ ax.text(lon, lat, f'{value:.0f}',
                   # ~ fontsize=8, ha='center', va='center',
                   # ~ transform=self._imp_cartopy_crs.PlateCarree(),
                   # ~ fontweight='bold', color='white',
                   # ~ bbox=dict(boxstyle='round,pad=0.3',
                            # ~ facecolor='red', alpha=0.7, edgecolor='none'))

        # ~ plt.title(title, fontsize=14, fontweight='bold', pad=20)
        # ~ if self.projection in ['NorthPolarStereo', 'SouthPolarStereo']:
            # ~ ax.imshow(data.T, origin='lower', extent=[-180,180,-90,90], transform=ccrs.PlateCarree(),cmap='jet',vmin=0, vmax=1.0)
        self._imp_matplotlib_pyplot.savefig(filepath, format='jpg', dpi=self.dpi,
                   bbox_inches='tight', facecolor='white')
        self._imp_matplotlib_pyplot.close()

        self.filepath = filename
        return filename


class DirectiveCarto(SphinxDirective):
    """
    An OSInt carto.

    Countries :

        - FR,DE,...
        - FR:100,DE,...
        - FR:100:blue,DE,...

    Colors : https://matplotlib.org/2.0.2/examples/color/named_colors.html

    """
    name = 'carto'
    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'data-countries': directives.unchanged_required,  # Format: "FR:100, DE:80, US:150"
        'data-object': directives.unchanged_required,
        'data-coordinates': directives.unchanged_required,
        'caption': directives.unchanged_required,
        'borders': yesno,
        'with-table': yesno,
        'width': directives.positive_int,
        'height': directives.positive_int,
        'fontsize': directives.positive_int,
        'dpi': directives.positive_int,
        'marker-min-size': directives.positive_int,
        'marker-max-size': directives.positive_int,
        'marker-color': directives.unchanged,
        'region': directives.unchanged,
        'projection': directives.unchanged,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = carto_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
        if 'borders' not in self.options or self.options['borders'] == 'yes':
            self.options['borders'] = True
        else:
            self.options['borders'] = False
        if 'with-table' not in self.options or self.options['with-table'] == 'yes':
            self.options['with_table'] = True
        else:
            self.options['with_table'] = False
        if 'data-object' in self.options:
            self.options['data_object'] = self.options['data-object']
            del self.options['data-object']
        if 'data-coordinates' in self.options:
            self.options['data_coordinates'] = self.options['data-coordinates']
            del self.options['data-coordinates']
        if 'data-countries' in self.options:
            self.options['data_countries'] = self.options['data-countries']
            del self.options['data-countries']
        if 'marker-min-size' in self.options:
            self.options['marker_min_size'] = self.options['marker-min-size']
            del self.options['marker-min-size']
        if 'marker-max-size' in self.options:
            self.options['marker_max_size'] = self.options['marker-max-size']
            del self.options['marker-max-size']
        if 'marker-color' in self.options:
            self.options['marker_color'] = self.options['marker-color']
            del self.options['marker-color']

        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]

