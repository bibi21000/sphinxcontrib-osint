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
    handle = bskylib.BSkyInterface.profile2atp('https://bsky.app/profile/wsj.com')
    assert handle == 'wsj.com'
    handle, post = bskylib.BSkyInterface.post2atp('https://bsky.app/badprofile')
    assert handle is None
    handle = bskylib.BSkyInterface.profile2atp('https://bsky.app/profile/wsj.com/post/3luuxgt5sye2y')
    assert handle == None

def test_bsky_post(caplog):
    caplog.set_level(logging.DEBUG, logger="osint")
    from sphinxcontrib.osint.plugins import bskylib
    import private_conf
    import json
    bsk_get = bskylib.OSIntBSkyPost('name', 'label', quest='fake',
        url='https://bsky.app/profile/wsj.com/post/3luuxgt5sye2y')
    resp = bsk_get.get_thread(
        user=private_conf.osint_bsky_user, apikey=private_conf.osint_bsky_apikey,
        url='https://bsky.app/profile/wsj.com/post/3luuxgt5sye2y')
    # ~ print(json.dumps(resp.__dict__), indent=4)
    # ~ assert False

