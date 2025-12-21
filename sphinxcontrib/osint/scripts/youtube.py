# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import sys
import json
import click

from . import parser_makefile, cli, get_app, load_quest
from ..osintlib import OSIntQuest
from ..plugins import collect_plugins

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

@cli.command()
@click.option('--fix', is_flag=True, help="Fix missing values in channel")
@click.option('--force', is_flag=True, help="Force fixing with blank value in case of exception")
@click.option('--reload', is_flag=True, help="Reload all channel")
@click.argument('channel', default="")
@click.pass_obj
def channel(common, channel, fix, force, reload):
    """Manage yourube channel"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_youtube_enabled is False:
        print('Plugin youtube is not enabled')
        sys.exit(1)

    osint_plugins = collect_plugins()

    if 'directive' in osint_plugins:
        for plg in osint_plugins['directive']:
            plg.extend_quest(OSIntQuest)

    if fix is True:
        from pytubefix import YouTube
        from ..plugins.youtube import OSIntYtChannel


        if channel != "":
            channels = [channel]
        else:
            data = load_quest(builddir)
            channels = [key.replace(OSIntYtChannel.prefix + '.', '') for key in data.ytchannels]

        for channel in channels:
            print(f'Check channel {channel}')
            channelf = os.path.join(sourcedir, app.config.osint_youtube_store, OSIntYtChannel.prefix + '__' + channel + '.json')
            if os.path.isfile(channelf) is False:
                channelf = os.path.join(sourcedir, app.config.osint_youtube_cache, OSIntYtChannel.prefix + '__' + channel + '.json')

            with open(channelf, 'r') as f:
                data = json.load(f)

            i = 0
            updated = False

            for video in data["videos"]:
                message_head = f'Fix {video} :'
                message_tail = []
                vid = None
                if data['videos'][video]["publish_date"] is None:
                    message_tail.append('publish_date')
                    if vid is None:
                        vid = YouTube(video)
                    try:
                        data['videos'][video]["publish_date"] = vid.publish_date
                        updated = True
                    except Exception:
                        import traceback
                        print('Exception in views')
                        print(traceback.format_exc())
                if data['videos'][video]["title"] is None:
                    message_tail.append('title')
                    if vid is None:
                        vid = YouTube(video)
                    try:
                        data['videos'][video]["title"] = vid.title
                        updated = True
                    except Exception:
                        import traceback
                        print('Exception in title')
                        print(traceback.format_exc())
                if "thumbnail_url" not in data['videos'][video] or data['videos'][video]["thumbnail_url"] is None:
                    message_tail.append('thumbnail_url')
                    if vid is None:
                        vid = YouTube(video)
                    try:
                        data['videos'][video]["thumbnail_url"] = vid.thumbnail_url
                        updated = True
                    except Exception:
                        import traceback
                        print('Exception in thumbnail_url')
                        print(traceback.format_exc())
                if "views" not in data['videos'][video] or data['videos'][video]["views"] is None:
                    message_tail.append('views')
                    if vid is None:
                        vid = YouTube(video)
                    try:
                        data['videos'][video]["views"] = vid.views
                        updated = True
                    except Exception:
                        import traceback
                        print('Exception in views')
                        print(traceback.format_exc())
                if "keywords" not in data['videos'][video] or data['videos'][video]["keywords"] is None:
                    message_tail.append('keywords')
                    if vid is None:
                        vid = YouTube(video)
                    try:
                        data['videos'][video]["keywords"] = vid.keywords
                        updated = True
                    except Exception:
                        import traceback
                        print('Exception in keywords')
                        print(traceback.format_exc())
                if "key_moments" not in data['videos'][video] or data['videos'][video]["key_moments"] is None:
                    message_tail.append('key_moments')
                    if vid is None:
                        vid = YouTube(video)
                    try:
                        data['videos'][video]["key_moments"] = vid.key_moments
                    except Exception:
                        import traceback
                        print('Exception in key_moments')
                        print(traceback.format_exc())
                        if force is True:
                            data['videos'][video]["key_moments"] = []
                    updated = True
                if len(message_tail) > 0:
                    print(message_head, ' '.join(message_tail))
                if updated is True and i > 30:
                    with open(channelf, 'w') as f:
                        f.write(json.dumps(data, indent=2, default=str))
                    i = 0
                    updated = False
                else:
                    i += 1
            else:
                if i != 0:
                    with open(channelf, 'w') as f:
                        f.write(json.dumps(data, indent=2, default=str))

    elif reload is True:
        from pytubefix import Channel
        from ..plugins.youtube import OSIntYtChannel

        data = load_quest(builddir)
        osintname = OSIntYtChannel.prefix + '.' + channel
        url = data.ytchannels[osintname].url
        limit = data.ytchannels[osintname].limit

        channelf = os.path.join(sourcedir, app.config.osint_youtube_store, OSIntYtChannel.prefix + '__' + channel + '.json')
        if os.path.isfile(channelf) is False:
            channelf = os.path.join(sourcedir, app.config.osint_youtube_cache, OSIntYtChannel.prefix + '__' + channel + '.json')

        with open(channelf, 'r') as f:
            result = json.load(f)

        c = Channel(url)
        if limit is None:
            videos = c.videos
        else:
            videos = c.videos[:limit]

        i = 0
        updated = False
        for vid in videos:
            if vid.watch_url not in result['videos']:
                updated = True
                result['videos'][vid.watch_url] = {
                    "url": vid.watch_url,
                    "thumbnail_url": vid.thumbnail_url,
                    "publish_date": vid.publish_date,
                }
                try:
                    result['videos'][vid.watch_url]['views'] = vid.views
                except Exception:
                    import traceback
                    print('Exception in %s : views of %s' %(channel, vid.watch_url))
                    print(traceback.format_exc())
                try:
                    result['videos'][vid.watch_url]['title'] = vid.title
                except Exception:
                    import traceback
                    print('Exception in %s : title of %s' %(channel, vid.watch_url))
                    print(traceback.format_exc())
                try:
                    result['videos'][vid.watch_url]['key_moments'] = vid.key_moments
                except Exception:
                    import traceback
                    print('Exception in %s : key_moments of %s' %(channel, vid.watch_url))
                    print(traceback.format_exc())
                try:
                    result['videos'][vid.watch_url]['keywords'] = vid.keywords
                except Exception:
                    import traceback
                    print('Exception in %s : keywords of %s' %(channel, vid.watch_url))
                    print(traceback.format_exc())
            if updated is True and i > 30:
                with open(channelf, 'w') as f:
                    f.write(json.dumps(data, indent=2, default=str))
                i = 0
                updated = False
            else:
                i += 1
        else:
            if i != 0:
                with open(channelf, 'w') as f:
                    f.write(json.dumps(data, indent=2, default=str))


        with open(channelf, 'w') as f:
            f.write(json.dumps(result, indent=2, default=str))
