# -*- encoding: utf-8 -*-
"""Test module

"""
import os
import sys
import io
from random import randbytes
import logging

import pytest

from sphinxcontrib import osint
from sphinxcontrib.osint.plugins import collect_plugins

sys.path.append(os.path.abspath(".."))

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

def test_org_and_base(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_org('org1', 'org1', cats=['test3'])
    print(quest.orgs)
    assert quest.orgs['org.org1'].shape == 'circle'
    assert quest.orgs['org.org1'].style == 'solid'
    quest.add_org('org2', 'org2', cats='test1,test2')
    print(quest.orgs['org.org2'].cats)
    assert quest.orgs['org.org2'].shape == 'hexagon'
    assert quest.orgs['org.org2'].style == 'dashed'
    quest.add_org('org3', 'org3', cats='test2')
    assert quest.orgs['org.org3'].shape == 'octogon'
    assert quest.orgs['org.org3'].style == 'invis'
    assert ['org.org1', 'org.org2', 'org.org3'] == quest.get_orgs()
    assert ['org.org2', 'org.org3'] == quest.get_orgs(cats=['test2'])

def test_missing_cat(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_org('org1', 'org1', cats=['test'])
    print(quest.orgs)
    assert quest.orgs['org.org1'].shape == 'circle'
    assert quest.orgs['org.org1'].style == 'solid'

def test_ident(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_org('org1', 'org1', cats=['test1'])
    quest.add_org('org2', 'org2', cats=['test2'])
    quest.add_ident('ident1', 'ident1', orgs='org1', cats=['test1'])
    print(quest.idents)
    assert quest.idents['ident.ident1'].shape == 'hexagon'
    assert quest.idents['ident.ident1'].style == 'dashed'
    assert quest.idents['ident.ident1'].orgs == ['org.org1']
    assert quest.idents['ident.ident1'].cats == ['test1']
    quest.add_ident('ident2', 'ident2', orgs='org2')
    print(quest.idents)
    assert quest.idents['ident.ident2'].shape == 'octogon'
    assert quest.idents['ident.ident2'].style == 'invis'
    assert quest.idents['ident.ident2'].orgs == ['org.org2']
    assert quest.idents['ident.ident2'].cats == ['test2']
    quest.add_relation('rel1', 'ident1', 'ident2')
    print(quest.idents)
    print(quest.relations)
    assert ['ident.ident1', 'ident.ident2'] == quest.get_idents()
    assert ['ident.ident2'] == quest.get_idents(orgs=['org2'])
    assert ['ident.ident1'] == quest.get_idents(cats=['test1'])
    assert ['ident.ident1', 'ident.ident2'] == quest.get_idents(countries=['FR'])

def test_source(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_org('org1', 'org1', cats=['test1'])
    quest.add_org('org2', 'org2', cats=['test2'])
    quest.add_source('source1', 'source1', orgs='org1', cats=['test1'])
    print(quest.sources)
    assert quest.sources['source.source1'].shape == 'hexagon'
    assert quest.sources['source.source1'].style == 'dashed'
    assert quest.sources['source.source1'].orgs == ['org.org1']
    assert quest.sources['source.source1'].cats == ['test1']
    quest.add_source('source2', 'source2', cats='test2')
    print(quest.sources)
    assert quest.sources['source.source2'].shape == 'octogon'
    assert quest.sources['source.source2'].style == 'invis'
    assert quest.sources['source.source2'].orgs == []
    assert quest.sources['source.source2'].cats == ['test2']
    assert ['source.source1', 'source.source2'] == quest.get_sources()
    assert ['source.source1'] == quest.get_sources(orgs=['org1'])
    assert ['source.source2'] == quest.get_sources(cats=['test2'])

def test_ident_relations(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_org('org1', 'org1', cats=['test1'])
    quest.add_org('org2', 'org2', cats=['test2'])
    quest.add_ident('ident1', 'ident1', orgs='org1', cats=['test1'])
    quest.add_ident('ident2', 'ident2', orgs='org2')
    quest.add_relation('rel1', 'ident1', 'ident2')
    print(quest.idents)
    print(quest.relations)
    idents = quest.get_idents(orgs=['org1'])
    assert ['ident.ident1'] == idents
    idents = quest.get_idents(cats=['test1'])
    assert ['ident.ident1'] == idents
    rel_idents, rels = quest.get_idents_relations(idents, cats=None)
    assert ['ident.ident2', 'ident.ident1'] == rel_idents
    rel_idents, rels = quest.get_idents_relations(idents, cats='test1')
    assert ['ident.ident1'] == rel_idents
    idents = quest.get_idents(countries=['FR'])
    assert ['ident.ident1', 'ident.ident2'] == idents
    assert ['relation.ident.ident1__rel1__ident.ident2'] == quest.get_relations()
    assert [] == quest.get_relations(cats=['test2'])

def test_event(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_ident('ident1', 'ident1', orgs='org1')
    quest.add_org('org1', 'org1', cats=['test1'])
    quest.add_event('event1', 'event1', cats=['test1'])
    quest.add_event('event2', 'event2', orgs=['org1'])
    print(quest.events)
    assert quest.events['event.event1'].shape == 'hexagon'
    assert quest.events['event.event1'].style == 'dashed'
    assert quest.events['event.event1'].cats == ['test1']
    print(quest.idents)
    quest.add_link('link1', 'ident1', 'event1')
    print(quest.links)
    idents = quest.get_idents(orgs=['org1'])
    print(idents)
    events = quest.get_events(orgs=['org1'])
    assert ['event.event2'] == events
    events = quest.get_events(cats=['test1'])
    assert ['event.event1'] == events
    events = quest.get_events(countries=['FR'])
    assert ['event.event1', 'event.event2'] == events
    events, links_events = quest.get_idents_events(idents, cats=None)
    assert ['link.ident.ident1__link1__event.event1'] == links_events
    events, links_events = quest.get_idents_events(idents, cats='test1')
    assert ['event.event1'] == events
    assert ['link.ident.ident1__link1__event.event1'] == links_events
    assert ['link.ident.ident1__link1__event.event1'] == quest.get_links()
    assert [] == quest.get_links(cats=['test2'])

def test_ident_relations_links(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_org('org1', 'org1', cats=['test1'])
    quest.add_org('org2', 'org2', cats=['test2'])
    quest.add_ident('ident1', 'ident1', orgs='org1', cats=['test1'])
    quest.add_ident('ident2', 'ident2', orgs='org2')
    quest.add_relation('rel1', 'ident1', 'ident2')
    quest.add_event('event1', 'event1', cats=['test1'])
    quest.add_link('link1', 'ident1', 'event1')
    print(quest.idents)
    print(quest.relations)
    print(quest.events)
    print(quest.links)
    idents = quest.get_idents(orgs=['org1'])
    assert ['ident.ident1'] == idents
    rel_idents, rels = quest.get_idents_relations(idents, cats=None)
    assert ['ident.ident2', 'ident.ident1'] == rel_idents
    idents, links_events = quest.get_idents_events(idents, cats=None)
    assert ['link.ident.ident1__link1__event.event1'] == links_events

def test_org_graph(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_ident('ident1', 'ident1', orgs='org1')
    quest.add_org('org1', 'org1', cats=['test1'])
    quest.add_event('event1', 'event1', cats=['test1'], orgs=['org1'])
    print(quest.events['event.event1'].cats)
    assert quest.events['event.event1'].cats == ['test1']
    quest.add_event('event2', 'event2', orgs=['org1'])
    idents = quest.get_idents(cats=['test1'])
    events = quest.get_events(cats=['test1'])
    ret = quest.orgs['org.org1'].graph(idents, events)
    assert ret == 'subgraph cluster_org_org1 {style="dashed";\nident_ident1 [shape="hexagon", label="ident1", style="dashed"];\nevent_event1 [shape="hexagon", label="event1", style="dashed"];\n}\n\n'
    quest.add_graph('graph1', 'graph1', orgs='org1')

def test_graph(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    quest = osint.OSIntQuest(default_cats=cats)
    quest.add_org('org1', 'org1', cats=['test1'])
    quest.add_org('org2', 'org2', cats=['test2'])
    quest.add_ident('ident1', 'ident1', orgs='org1', cats=['test1'])
    quest.add_ident('ident2', 'ident2', orgs='org2')
    quest.add_ident('ident3', 'ident3')
    quest.add_relation('rel1', 'ident1', 'ident2')
    quest.add_relation('rel2', 'ident1', 'ident3')
    quest.add_event('event1', 'event1', cats=['test1'])
    quest.add_link('link1', 'ident1', 'event1')
    quest.add_link('link2', 'ident2', 'event1')
    # ~ quest.add_graph('graph1', 'graph1', orgs='org1')
    quest.add_graph('graph1', 'graph1')
    print(quest.graphs['graph.graph1'])
    graph = quest.graphs['graph.graph1'].graph()
    assert graph == """digraph graph_graph1 {
subgraph cluster_org_org2 {style="invis";
ident_ident2 [shape="octogon", label="ident2", style="invis"];
}

subgraph cluster_org_org1 {style="dashed";
ident_ident1 [shape="hexagon", label="ident1", style="dashed"];
}

event_event1 [shape="hexagon", label="event1", style="dashed"];

ident_ident3 [shape="circle", label="ident3", style="solid"];

ident_ident1 -> ident_ident3 [label="rel2"];
ident_ident1 -> ident_ident2 [label="rel1"];

ident_ident2 -> event_event1 [label="link2"];
ident_ident1 -> event_event1 [label="link1"];

}
"""

def test_plugins(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    plgs = collect_plugins()
    print(plgs)
    print(plgs['source'])
    print(plgs['source'][0].order)
    # ~ assert False

def test_bsky_regexp(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    from sphinxcontrib.osint.plugins import bskylib
    import private_conf
    handle, post = bskylib.BSkyInterface.post2atp('https://bsky.app/profile/wsj.com/post/3luuxgt5sye2y')
    assert handle == 'wsj.com'
    assert post == '3luuxgt5sye2y'
    handle, post = bskylib.BSkyInterface.post2atp('https://bsky.app/badpost')
    assert handle is None
    assert post is None
    handle = bskylib.BSkyInterface.profile2atp('https://bsky.app/profile/wsj.com/post/3luuxgt5sye2y')
    assert handle == 'wsj.com'
    handle, post = bskylib.BSkyInterface.post2atp('https://bsky.app/badpost')
    assert handle is None

def test_bsky_get(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    from sphinxcontrib.osint.plugins import bskylib
    import private_conf
    import json
    bsk_get = bskylib.OSIntBSkyGet('name', 'label', quest='fake',
        user=private_conf.osint_bsky_user, apikey=private_conf.osint_bsky_apikey,
        url='https://bsky.app/profile/wsj.com/post/3luuxgt5sye2y')
    resp = bsk_get.get()
    print(json.dumps(resp.__dict__), indent=4)
    assert False

