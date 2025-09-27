# -*- encoding: utf-8 -*-
"""Test module

"""
import os
import sys
import io
from random import randbytes
import logging

import pytest

from textparser import Token

from sphinxcontrib import osint
from sphinxcontrib.osint.plugins.storyparser import StoryParser

sys.path.append(os.path.abspath(".."))


def test_parser(caplog):
    tree = StoryParser().parse(
        [
            'text 1 :osint:extsrc:`link <event.link1>` and :osint:extsrc:`event.link2` !',
        ])
    assert len(tree[0]) == 5
    assert tree[0][0] == Token(kind='TEXT', value='text 1', offset=0)
    assert tree[0][1] == Token(kind='EXTSRC', value='link <event.link1>', offset=7)
    assert tree[0][2] == Token(kind='TEXT', value='and', offset=42)
    assert tree[0][3] == Token(kind='EXTSRC', value='event.link2', offset=46)
    assert tree[0][4] == Token(kind='TEXT', value='!', offset=74)

    tree = StoryParser().parse(
        [
            'text 1 :osint:exturl:`link <event.link1>` and :osint:exturl:`event.link2` !',
        ])
    assert len(tree[0]) == 5
    assert tree[0][0] == Token(kind='TEXT', value='text 1', offset=0)
    assert tree[0][1] == Token(kind='EXTURL', value='link <event.link1>', offset=7)
    assert tree[0][2] == Token(kind='TEXT', value='and', offset=42)
    assert tree[0][3] == Token(kind='EXTURL', value='event.link2', offset=46)
    assert tree[0][4] == Token(kind='TEXT', value='!', offset=74)

    tree = StoryParser().parse(
        [
            'text 1 `link <link1>`_ and `link2`_ 🇪🇺🇫🇷🇪🇺',
        ])
    assert len(tree[0]) == 5
    assert tree[0][0] == Token(kind='TEXT', value='text 1', offset=0)
    assert tree[0][1] == Token(kind='LINK', value='link <link1>', offset=7)
    assert tree[0][2] == Token(kind='TEXT', value='and', offset=23)
    assert tree[0][3] == Token(kind='LINK', value='link2', offset=27)
    assert tree[0][4] == Token(kind='TEXT', value='🇪🇺🇫🇷🇪🇺', offset=36)

    tree = StoryParser().parse(
        [
            'mention @toto1 and @toto2 !',
            '',
            'tag #toto1 and #toto2 ?',
        ])
    assert len(tree) == 3
    assert len(tree[0]) == 5
    assert len(tree[1]) == 1
    assert len(tree[2]) == 5
    assert tree[0][0] == Token(kind='TEXT', value='mention', offset=0)
    assert tree[0][1] == Token(kind='MENTION', value='toto1', offset=8)
    assert tree[0][2] == Token(kind='TEXT', value='and', offset=15)
    assert tree[0][3] == Token(kind='MENTION', value='toto2', offset=19)
    assert tree[0][4] == Token(kind='TEXT', value='!', offset=26)
    assert tree[1][0] == Token(kind='TEXT', value='', offset=0)
    assert tree[2][0] == Token(kind='TEXT', value='tag', offset=0)
    assert tree[2][1] == Token(kind='TAG', value='toto1', offset=4)
    assert tree[2][2] == Token(kind='TEXT', value='and', offset=11)
    assert tree[2][3] == Token(kind='TAG', value='toto2', offset=15)
    assert tree[2][4] == Token(kind='TEXT', value='?', offset=22)

    tree = StoryParser().parse(
        [
            '#tagit',
        ])
    print(tree)
    assert len(tree[0]) == 1
    assert tree[0][0] == Token(kind='TAG', value='tagit', offset=0)
