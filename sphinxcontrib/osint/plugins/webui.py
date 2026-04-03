# -*- encoding: utf-8 -*-
"""
The open webui lib
-----------------------

From https://github.com/Koesn/openwebui-knowledge

API key : https://docs.openwebui.com/reference/monitoring/#authentication-setup-for-api-key-

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import sys
import requests
import argparse
import json
import time
import magic
import io
from pathlib import Path
from datetime import datetime

from ..osintlib import OSIntQuest, OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource, OSIntCountry
from . import Plugin
from ..owebuilib import OwebuiAPI

class WebUI(Plugin):
    name = "webui"
    connect_timeout = 60
    read_timeout = 600

    @classmethod
    def config_values(cls):
        return [
            ('osint_webui_url', 'http://127.0.0.1:8080', 'html'),
            ('osint_webui_token', None, 'html'),
            ('osint_webui_store', 'webui_store', 'html'),
            ('osint_webui_knowledge', {}, 'html'),
        ]

    @classmethod
    def init(cls, env):
        """
        """
        if env.config.osint_webui_enabled:
            storef = os.path.join(env.srcdir, env.config.osint_webui_store)
            os.makedirs(storef, exist_ok=True)


    def __init__(self, app=None):
        super().__init__()
        self.session = None
        self.app = app
        self.owebui = None

    def sanitize(self, data):
        # ~ return unidecode(data)
        return data

    # ~ def logfile(self, env, knowledge_id):
        # ~ return os.path.join(env.srcdir, env.config.osint_webui_store, "%s.json" % knowledge_id)

    # ~ def write_to_log(self, env, knowledge_id, file_path, file_id):
        # ~ logf = self.logfile(env, knowledge_id)

        # ~ log_entry = {
            # ~ "file_id": file_id,
            # ~ "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # ~ "file_name": Path(file_path).name,
            # ~ "file_extension": Path(file_path).suffix,
            # ~ "file_size": os.path.getsize(file_path),
            # ~ "file_path": file_path,
            # ~ "file_mtime": Path(file_path).stats().st_mtime,
        # ~ }

        # ~ if os.path.exists(logf):
            # ~ with open(logf, mode='r') as file:
                # ~ log_data = json.load(file)
        # ~ else:
            # ~ log_data = {}

        # ~ log_data[file_id] = log_entry

        # ~ with open(logf, mode='w') as file:
            # ~ json.dump(log_data, file, indent=2)

    # ~ def remove_from_log(self, env, knowledge_id, file_id):
        # ~ logf = self.logfile(env, knowledge_id)
        # ~ if not os.path.exists(logf):
            # ~ print(f"Record file '{logf}' not found.")
            # ~ return

        # ~ with open(logf, mode='r') as file:
            # ~ log_data = json.load(file)

        # ~ if file_id not in log_data:
            # ~ return

        # ~ del log_data[file_id]

        # ~ with open(logf, mode='w') as file:
            # ~ json.dump(log_data, file, indent=4)

    # ~ def remove_file_from_knowledge(self, env, knowledge_id, file_id, file_path):
        # ~ url = f'{env.config.osint_webui_url}/api/v1/knowledge/{knowledge_id}/file/remove'
        # ~ headers = {
            # ~ 'Authorization': f'Bearer {env.config.osint_webui_token}',
            # ~ 'Content-Type': 'application/json'
        # ~ }
        # ~ data = {'file_id': file_id}
        # ~ response = requests.post(url, headers=headers, json=data)

        # ~ if response.status_code == 200:
            # ~ print(f"File '{file_path}' successfully removed from knowledge.")
            # ~ return True
        # ~ else:
            # ~ print(f"Failed to remove file '{file_path}'. Status code: {response.status_code}, Response: {response.text}")
            # ~ return False

    # ~ def api_files(self, quest):
        # ~ if self.session is None:
            # ~ self.session = requests.Session()

        # ~ files_url = f'{quest.sphinx_env.config.osint_webui_url}/api/v1/files/'
        # ~ headers = {
            # ~ 'Authorization': f'Bearer {quest.sphinx_env.config.osint_webui_token}',
            # ~ 'Accept': 'application/json'
        # ~ }

        # ~ response = self.session.get(
            # ~ files_url,
            # ~ headers=headers,
            # ~ timeout=(self.connect_timeout, self.read_timeout)
        # ~ )
        # ~ return response.json()

    def stats(self, quest, knowledge_id=None):
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url)
        files = self.owebui.list_files(knowledgeid=knowledge_id)
        return {
            'nbfiles' : files['total']
        }

    def dump(self, quest, knowledge=None):
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url)
        if knowledge is not None:
            knowledge_id = quest.sphinx_env.config.osint_webui_knowledge[knowledge]['id']
        else:
            knowledge_id = knowledge
        files = self.owebui.list_files(knowledgeid=knowledge_id, content=False)
        return files

    def clean(self, quest, progress_callback=sys.stdout.write, progress_bar=None):
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url)
        ret = self.owebui.clean_all()
        return ret

    def clean_knowlegde(self, quest, knowledge_id):
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url)
        ret = self.owebui.clean_knowledge(knowledge_id, delete_files=True)
        return ret

    def create_knowlegde(self, quest, name, desription):
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url)
        ret = self.owebui.create_knowledge(name, desription)
        return ret

    def create_model(self, quest, name, description, knowledgeid, prompt, base_model, num_ctx):
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url)
        ret = self.owebui.create_model(name, description, knowledgeid, prompt, base_model, num_ctx)
        return ret

    def clean_orphans(self, quest):
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url)
        ret = self.owebui.clean_orphans()
        return ret

    # ~ def upload_file(self, env, filename, fileobj, sleep=0.5):
        # ~ if self.session is None:
            # ~ self.session = requests.Session()

        # ~ url = f'{env.config.osint_webui_url}/api/v1/files/'
        # ~ headers = {
            # ~ 'Authorization': f'Bearer {env.config.osint_webui_token}',
            # ~ 'Accept': 'application/json'
        # ~ }

        # ~ fileobj.seek(0)
        # ~ mime_type = magic.from_buffer(fileobj.read(2048), mime=True)
        # ~ if mime_type is None:
            # ~ mime_type = 'application/octet-stream'

        # ~ fileobj.seek(0)
        # ~ try:
            # ~ response = self.session.post(
                # ~ url,
                # ~ headers=headers,
                # ~ files={'file': (filename, fileobj, mime_type)},
                # ~ timeout=(self.connect_timeout, self.read_timeout)
            # ~ )
            # ~ time.sleep(sleep)
            # ~ print(response)
            # ~ print(response.reason)
            # ~ print(response.json())
            # ~ return response.json()
        # ~ except requests.exceptions.RequestException as e:
            # ~ print(f"Connection error when uploading file '{filename}': {e}")
            # ~ return {"error": str(e)}
        # ~ except Exception as e:
            # ~ print(f"Error uploading file '{filename}': {e}")
            # ~ return {"error": str(e)}

    # ~ def add_file_to_knowledge(self, env, knowledge_id, file_id):
        # ~ url = f'{env.config.osint_webui_url}/api/v1/knowledge/{knowledge_id}/file/add'
        # ~ headers = {
            # ~ 'Authorization': f'Bearer {env.config.osint_webui_token}',
            # ~ 'Content-Type': 'application/json'
        # ~ }
        # ~ data = {'file_id': file_id}
        # ~ response = requests.post(url, headers=headers, json=data)
        # ~ return response.json()

    # ~ def find_file_ids_by_path(self, file_path):
        # ~ if not os.path.exists(LOG_FILE):
            # ~ print("Record file not found.")
            # ~ return []

        # ~ file_ids = []
        # ~ with open(LOG_FILE, mode='r') as file:
            # ~ reader = csv.reader(file)
            # ~ next(reader)  # Lewati header
            # ~ for row in reader:
                # ~ if len(row) >= 6 and row[5] == file_path:
                    # ~ file_ids.append(row[0])  # Kolom pertama adalah file ID

        # ~ if not file_ids:
            # ~ print(f"No ID file found for path '{file_path}' in record.")

        # ~ return file_ids

    # ~ # Fungsi untuk memproses file atau folder
    # ~ def process_files(self, knowledge_id, path, action):
        # ~ # Baca log yang sudah ada
        # ~ if os.path.exists(LOG_FILE):
            # ~ with open(LOG_FILE, mode='r') as file:
                # ~ log_data = json.load(file)
        # ~ else:
            # ~ log_data = []

        # ~ # Buat set dari file_path yang sudah ada di log
        # ~ existing_files = {entry["file_path"] for entry in log_data}

        # ~ if action == "add":
            # ~ if os.path.isfile(path):
                # ~ # Cek apakah file sudah ada di log
                # ~ if path in existing_files:
                    # ~ print(f"File '{path}' already exist in the knowledge.")
                # ~ else:
                    # ~ uploaded_file = upload_file(path)
                    # ~ if 'id' in uploaded_file:
                        # ~ file_id = uploaded_file['id']
                        # ~ add_file_to_knowledge(knowledge_id, file_id)
                        # ~ write_to_log(path, file_id)
                        # ~ print(f"File '{path}' succesfully added to knowledge with ID '{file_id}'.")
                    # ~ else:
                        # ~ print(f"Failed to upload file '{path}'. Response: {uploaded_file}")
            # ~ elif os.path.isdir(path):
                # ~ for root, _, files in os.walk(path):
                    # ~ for file_name in files:
                        # ~ file_path = os.path.join(root, file_name)
                        # ~ # Cek apakah file sudah ada di log
                        # ~ if file_path in existing_files:
                            # ~ print(f"File '{file_path}' already exist in the knowledge.")
                        # ~ else:
                            # ~ uploaded_file = upload_file(file_path)
                            # ~ if 'id' in uploaded_file:
                                # ~ file_id = uploaded_file['id']
                                # ~ add_file_to_knowledge(knowledge_id, file_id)
                                # ~ write_to_log(file_path, file_id)
                                # ~ print(f"File '{file_path}' succesfully added to knowledge with ID '{file_id}'.")
                            # ~ else:
                                # ~ print(f"Failed to upload file '{file_path}'. Response: {uploaded_file}")
            # ~ else:
                # ~ print(f"Path '{path}' invalid.")
        # ~ elif action == "remove":
            # ~ process_removal(knowledge_id)

    def osint_to_filename(self, obj, obj_src):
        objname = obj.name.replace(obj.prefix + '.', obj.prefix + '##')
        srcname = obj_src.name.replace(obj_src.prefix + '.','')
        return srcname, obj.prefix + '##' + srcname

    def _upload_sources(self, quest, knowledge_id, obj, sources, initial,
            remove=True, sleep=0.5):
        from ..osintlib import OSIntSource

        # ~ logf = self.logfile(quest.sphinx_env, knowledge_id)

        # ~ if os.path.exists(logf):
            # ~ with open(logf, mode='r') as file:
                # ~ log_data = json.load(file)
        # ~ else:
            # ~ log_data = {}

        files_id = []

        for src in obj.linked_sources():

            if remove is True:
                if src in sources:
                    sources.remove(src)
            obj_src = quest.sources[src]
            # ~ srcname = obj_src.name.replace(OSIntSource.prefix + '.','')
            # ~ filename = obj_src.docname.replace('/','__') + '##' + obj.prefix + '__' + srcname + '.txt'
            srcname, filename = self.osint_to_filename(obj, obj_src)

            fileobj = io.StringIO()
            for initi in initial:
                fileobj.write(self.sanitize(initi + '\n'))

            filetext = None
            fileanal = None

            metadata = {
                'docname': obj.docname,
                'prefix': obj.prefix,
                'name': obj.name,
                'title': obj.label,
                'src_name': obj_src.name,
                'src_url': obj_src.url,
                'src_link': obj_src.link,
                'src_local': obj_src.local,
                'src_youtube': obj_src.youtube,
                'src_bsky': obj_src.bsky,
            }
            if obj.description is not None:
                metadata['description'] = obj.description
            if hasattr(obj, 'altlabels') and obj.altlabels is not None:
                metadata['altlabels'] = obj.altlabels

            if self.app.config.osint_text_enabled is True:

                cachefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_text_cache, f'{srcname}.json'))
                storefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_text_store, f'{srcname}.json'))

                data = None
                if os.path.isfile(storefull) is True:
                    filetext = storefull
                    try:
                        with open(storefull, 'r') as f:
                            data = json.load(f)
                    except Exception:
                        logger.exception('Exception loading %s', storefull)
                        raise
                elif os.path.isfile(cachefull) is True:
                    filetext = cachefull
                    try:
                        with open(cachefull, 'r') as f:
                            data = json.load(f)
                    except Exception:
                        logger.exception('Exception loading %s', cachefull)
                        raise
                if data is not None:
                    if 'yt_text' in data:
                        if data['yt_title'] is not None:
                            fileobj.write(self.sanitize(data['yt_title'] + '\n'))
                        if data['yt_text'] is not None:
                            fileobj.write(self.sanitize(data['yt_text'] + '\n'))
                    if 'text' in data and data['text'] is not None:
                            fileobj.write(self.sanitize(data['text'] + '\n'))
                    if 'title' in data and data['title'] is not None:
                            metadata['title'] = data['title']
                            fileobj.write(self.sanitize(data['title'] + '\n'))
                    if 'excerpt' in data and data['excerpt'] is not None:
                            metadata['excerpt'] = data['excerpt']
                            fileobj.write(self.sanitize(data['excerpt'] + '\n'))

            if self.app.config.osint_analyse_enabled is True:

                cachefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_analyse_cache, f'{srcname}.json'))
                storefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_analyse_store, f'{srcname}.json'))

                data = None
                if os.path.isfile(storefull) is True:
                    fileanal = storefull
                    with open(storefull, 'r') as f:
                        data = json.load(f)
                elif os.path.isfile(cachefull) is True:
                    fileanal = cachefull
                    with open(cachefull, 'r') as f:
                        data = json.load(f)
                if data is not None:
                    if 'ident' in data and data['ident'] is not None and data['ident'] !={}:
                        fileobj.write(self.sanitize(json.dumps(data['ident'], ensure_ascii=False) + '\n'))
                        if 'idents' in data['ident']:
                            metadata['idents'] = ''
                            idents = data['ident']['idents']
                            for idt in idents:
                                try:
                                    oidt = quest.idents[idt[0]]
                                    metadata['idents'] += f'{oidt.label},'
                                    fileobj.write(oidt.label + '\n')
                                    if oidt.altlabels is not None:
                                        for midt in oidt.altlabels.split('|'):
                                            metadata['idents'] += f'{midt},'
                                            fileobj.write(midt + '\n')
                                except Exception:
                                    logger.exception("Error in ident %s for source %s" % (idt, src))
                    if 'countries' in data and data['countries'] is not None and data['countries'] != '':
                        fileobj.write(self.sanitize(json.dumps(data['countries'], ensure_ascii=False) + '\n'))
                        if 'countries' in data['countries']:
                            metadata['countries'] = ''
                            idents = data['countries']['countries']
                            for idt in idents:
                                try:
                                    oidt = quest.countries[idt[0]]
                                    metadata['countries'] += f'{oidt.label},'
                                    fileobj.write(oidt.label + '\n')
                                    if oidt.altlabels is not None:
                                        for midt in oidt.altlabels.split('|'):
                                            metadata['countries'] += f'{midt},'
                                            fileobj.write(midt + '\n')
                                except Exception:
                                    logger.exception("Error in country %s for source %s" % (idt, src))
                    if 'cities' in data and data['cities'] is not None and data['cities'] != '':
                        fileobj.write(self.sanitize(json.dumps(data['cities'], ensure_ascii=False) + '\n'))
                        if 'cities' in data['cities']:
                            idents = data['cities']['cities']
                            metadata['cities'] = ''
                            for idt in idents:
                                try:
                                    oidt = quest.cities[idt[0]]
                                    metadata['cities'] += f'{oidt.label},'
                                    fileobj.write(oidt.label + '\n')
                                    if oidt.altlabels is not None:
                                        for midt in oidt.altlabels.split('|'):
                                            metadata['cities'] += f'{midt},'
                                            fileobj.write(midt + '\n')
                                except Exception:
                                    logger.exception("Error in city %s for source %s" % (idt, src))

            # ~ ret = self.upload_file(quest.sphinx_env, filename, fileobj, sleep=sleep)
            status, ret = self.owebui.upload_file(fileobj=fileobj, filename=filename,
                metadata=metadata)
            if status is True:
                files_id.append(ret['id'])
            else:
                print('Error in filename %s : %s' % (filename, ret))
            # ~ time.sleep(sleep)
            # ~ file_id = ret['id']
            # ~ files_id.append(file_id)
            # ~ fileobj.seek(0, os.SEEK_END)
            # ~ size = fileobj.tell()
            # ~ time.sleep(0.5)
            # ~ self.add_file_to_knowledge(quest.sphinx_env, knowledge_id, file_id)
            # ~ log_entry = {
                # ~ "file_id": file_id,
                # ~ "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                # ~ "prefix": prefix,
                # ~ "name": obj_src.name,
                # ~ "size": size,
                # ~ "filename": filename,
                # ~ "text_mtime": Path(filetext).stat().st_mtime,
                # ~ "anal_mtime": Path(fileanal).stat().st_mtime if fileanal is not None else None,
            # ~ }

            # ~ log_data[file_id] = log_entry

        # ~ with open(logf, mode='w') as file:
            # ~ json.dump(log_data, file, indent=2)
        return files_id

    def upload_quest(self, quest, knowledge, progress_callback=sys.stdout.write, progress_bar=None, sleep=0.15):
        """Index data from quest"""
        from ..osintlib import OSIntCountry, OSIntCity, OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource
        if self.owebui is None:
            self.owebui = OwebuiAPI(apikey=quest.sphinx_env.config.osint_webui_token,
                url_base=quest.sphinx_env.config.osint_webui_url,
                connect_timeout=None, read_timeout=None)
        uploaded_count = 0
        uploaded_total_time = time.time()

        knowledge_id = quest.sphinx_env.config.osint_webui_knowledge[knowledge]['id']
        cats = None
        if 'only-cats' in quest.sphinx_env.config.osint_webui_knowledge[knowledge]:
            cats = quest.sphinx_env.config.osint_webui_knowledge[knowledge]['only-cats']
        exclude_cats = None
        if 'exclude-cats' in quest.sphinx_env.config.osint_webui_knowledge[knowledge]:
            exclude_cats = quest.sphinx_env.config.osint_webui_knowledge[knowledge]['exclude-cats']

        sources = quest.get_sources(cats=cats,exclude_cats=exclude_cats)
        orgs = quest.get_orgs(cats=cats,exclude_cats=exclude_cats)
        idents = quest.get_idents(cats=cats,exclude_cats=exclude_cats)
        events = quest.get_events(cats=cats,exclude_cats=exclude_cats)
        countries = quest.get_countries(cats=cats,exclude_cats=exclude_cats)
        cities = quest.get_cities(cats=cats,exclude_cats=exclude_cats)

        # ~ progress_callback("✓ Start uploading" + '\n')

        uploaded_time = time.time()
        uploaded_local = 0
        uploaded_sources = 0
        files_id = []
        if progress_bar is not None:
            pbar = progress_bar(total=len(countries), desc="Upload countries")
        for country in countries:
            obj_country = quest.countries[country]
            name = quest.countries[country].name.replace(OSIntCountry.prefix + '.', '')
            if OSIntIdent.prefix + '.' + name in idents:
                #Found an ident ... delete it
                idents.remove(OSIntIdent.prefix + '.' + name)

            initial = [obj_country.label]
            if obj_country.description is not None:
                initial.append(obj_country.description)
            files_id_local = self._upload_sources(quest, knowledge_id, obj_country, sources,
                initial, sleep=sleep)
            files_id.extend(files_id_local)
            uploaded_local += 1
            uploaded_sources += len(files_id_local)
            if progress_bar is not None:
                pbar.update(1)

        if progress_bar is not None:
            pbar.close()
        if progress_bar is not None:
            pbar = progress_bar(total=len(files_id), desc="Add countries to knowlegde")
        for file_id in files_id:
            status, ret = self.owebui.add_file_to_knowledge(file_id, knowledge_id)
            if progress_bar is not None:
                pbar.update(1)
        if progress_bar is not None:
            pbar.close()
        elapsed_time = time.time() - uploaded_time
        uploaded_count += uploaded_local
        time.sleep(0.5)
        sys.stdout.flush()
        # ~ progress_callback(f"✓ Countries uploaded ({uploaded_local} / {uploaded_sources} - {uploaded_sources / (elapsed_time / 60)} sources/minute" + '\n')

        uploaded_time = time.time()
        uploaded_local = 0
        uploaded_sources = 0
        files_id = []
        if progress_bar is not None:
            pbar = progress_bar(total=len(cities), desc="Upload cities")
        for city in cities:
            obj_city = quest.cities[city]
            name = quest.cities[city].name.replace(OSIntCity.prefix + '.', '')
            if OSIntIdent.prefix + '.' + name in idents:
                #Found an ident ... delete it
                idents.remove(OSIntIdent.prefix + '.' + name)

            initial = [obj_city.label]
            if obj_city.description is not None:
                initial.append(obj_city.description)
            files_id_local = self._upload_sources(quest, knowledge_id, obj_city, sources,
                initial, sleep=sleep)
            files_id.extend(files_id_local)
            uploaded_local += 1
            uploaded_sources += len(files_id_local)
            if progress_bar is not None:
                pbar.update(1)

        if progress_bar is not None:
            pbar.close()
        if progress_bar is not None:
            pbar = progress_bar(total=len(files_id), desc="Add cities to knowlegde")
        for file_id in files_id:
            status, ret = self.owebui.add_file_to_knowledge(file_id, knowledge_id)
            if progress_bar is not None:
                pbar.update(1)
        if progress_bar is not None:
            pbar.close()
        elapsed_time = time.time() - uploaded_time
        uploaded_count += uploaded_local
        time.sleep(0.5)
        sys.stdout.flush()
        # ~ progress_callback(f"✓ Cities uploaded ({uploaded_local} / {uploaded_sources} - {uploaded_sources / (elapsed_time / 60)} sources/minute" + '\n')


        uploaded_time = time.time()
        uploaded_local = 0
        uploaded_sources = 0
        files_id = []
        if progress_bar is not None:
            pbar = progress_bar(total=len(orgs), desc="Upload orgs")
        for org in orgs:
            obj_org = quest.orgs[org]
            name = quest.orgs[org].name.replace(OSIntOrg.prefix + '.', '')
            if OSIntIdent.prefix + '.' + name in idents:
                #Found an org ... continue
                continue

            initial = [obj_org.label]
            if obj_org.description is not None:
                initial.append(obj_org.description)
            files_id_local = self._upload_sources(quest, knowledge_id, obj_org, sources,
                initial, sleep=sleep)
            files_id.extend(files_id_local)
            uploaded_local += 1
            uploaded_sources += len(files_id_local)
            if progress_bar is not None:
                pbar.update(1)

        if progress_bar is not None:
            pbar.close()
        if progress_bar is not None:
            pbar = progress_bar(total=len(files_id), desc="Add orgs to knowlegde")
        for file_id in files_id:
            status, ret = self.owebui.add_file_to_knowledge(file_id, knowledge_id)
            if progress_bar is not None:
                pbar.update(1)
        if progress_bar is not None:
            pbar.close()
        elapsed_time = time.time() - uploaded_time
        uploaded_count += uploaded_local
        time.sleep(0.5)
        sys.stdout.flush()
        # ~ progress_callback(f"✓ Orgs uploaded ({uploaded_local} / {uploaded_sources} - {uploaded_sources / (elapsed_time / 60)} sources/minute" + '\n')


        uploaded_time = time.time()
        uploaded_local = 0
        uploaded_sources = 0
        files_id = []
        if progress_bar is not None:
            pbar = progress_bar(total=len(idents), desc="Upload idents")
        for ident in idents:
            obj_ident = quest.idents[ident]
            name = obj_ident.name.replace(OSIntIdent.prefix + '.', '')

            initial = [obj_ident.label]
            if obj_ident.description is not None:
                initial.append(obj_ident.description)
            files_id_local = self._upload_sources(quest, knowledge_id, obj_ident, sources,
                initial, sleep=sleep)
            files_id.extend(files_id_local)
            uploaded_local += 1
            uploaded_sources += len(files_id_local)
            if progress_bar is not None:
                pbar.update(1)

        if progress_bar is not None:
            pbar.close()
        if progress_bar is not None:
            pbar = progress_bar(total=len(files_id), desc="Add idents to knowlegde")
        for file_id in files_id:
            status, ret = self.owebui.add_file_to_knowledge(file_id, knowledge_id)
            if progress_bar is not None:
                pbar.update(1)
        if progress_bar is not None:
            pbar.close()
        elapsed_time = time.time() - uploaded_time
        uploaded_count += uploaded_local
        time.sleep(0.5)
        sys.stdout.flush()
        # ~ progress_callback(f"✓ Idents uploaded ({uploaded_local} / {uploaded_sources} - {uploaded_sources / (elapsed_time / 60)} sources/minute" + '\n')


        uploaded_time = time.time()
        uploaded_local = 0
        uploaded_sources = 0
        files_id = []
        if progress_bar is not None:
            pbar = progress_bar(total=len(events), desc="Upload events")
        for event in events:
            obj_event = quest.events[event]
            name = obj_event.name.replace(OSIntEvent.prefix + '.', '')

            initial = [obj_event.label]
            if obj_event.description is not None:
                initial.append(obj_event.description)
            files_id_local = self._upload_sources(quest, knowledge_id, obj_event, sources,
                initial, sleep=sleep)
            files_id.extend(files_id_local)
            uploaded_local += 1
            uploaded_sources += len(files_id_local)
            if progress_bar is not None:
                pbar.update(1)

        if progress_bar is not None:
            pbar.close()
        if progress_bar is not None:
            pbar = progress_bar(total=len(files_id), desc="Add events to knowlegde")
        for file_id in files_id:
            status, ret = self.owebui.add_file_to_knowledge(file_id, knowledge_id)
            if progress_bar is not None:
                pbar.update(1)
        if progress_bar is not None:
            pbar.close()
        elapsed_time = time.time() - uploaded_time
        uploaded_count += uploaded_local
        time.sleep(0.5)
        sys.stdout.flush()
        # ~ progress_callback(f"✓ Events uploaded ({uploaded_local} / {uploaded_sources} - {uploaded_sources / (elapsed_time / 60)} sources/minute" + '\n')


        # ~ if 'directive' in osint_plugins:
            # ~ for plg in osint_plugins['directive']:
                # ~ uploaded_count += plg.xapian(self, db, quest, progress_callback, indexer, sources)

        # ~ uploaded_local = 0
        # ~ for source in sources:
            # ~ obj_source = quest.sources[source]
            # ~ name = obj_source.name.replace(OSIntSource.prefix + '.','')
            # ~ doc = xapian.Document()
            # ~ doc.set_data(obj_source.docname + '.html#' + obj_source.ids[0])

            # ~ # Ajouter le titre avec poids supérieur
            # ~ indexer.set_document(doc)
            # ~ indexer.set_document(doc)
            # ~ indexer.index_text(self.sanitize(obj_source.slabel), 2, self.PREFIX_TITLE)
            # ~ indexer.index_text(self.sanitize(obj_source.slabel))
            # ~ indexer.increase_termpos()
            # ~ if obj_source.description is not None:
                # ~ indexer.index_text(self.sanitize(obj_source.sdescription), 2, self.PREFIX_DESCRIPTION)
                # ~ indexer.index_text(self.sanitize(obj_source.sdescription))
            # ~ indexer.increase_termpos()
            # ~ indexer.index_text(obj_source.prefix + 's', 1, self.PREFIX_TYPE)
            # ~ indexer.increase_termpos()
            # ~ indexer.index_text(','.join(obj_source.cats), 1, self.PREFIX_CATS)
            # ~ indexer.increase_termpos()
            # ~ indexer.index_text(self.sanitize(' '.join(obj_source.content)), 1, self.PREFIX_CONTENT)
            # ~ indexer.index_text(self.sanitize(' '.join(obj_source.content)))
            # ~ indexer.increase_termpos()
            # ~ indexer.index_text(obj_source.country, 1, self.PREFIX_COUNTRY)
            # ~ indexer.increase_termpos()
            # ~ indexer.index_text(name, 1, self.PREFIX_NAME)
            # ~ indexer.index_text(name)

            # ~ self._index_sources(quest, indexer, doc, sources, [source], remove=False)

            # ~ doc.add_value(self.SLOT_TITLE, obj_source.slabel)
            # ~ if obj_source.description is not None:
                # ~ doc.add_value(self.SLOT_DESCRIPTION, obj_source.sdescription)
            # ~ doc.add_value(self.SLOT_TYPE, obj_source.prefix + 's')
            # ~ doc.add_value(self.SLOT_CATS, ','.join(obj_source.cats))
            # ~ doc.add_value(self.SLOT_CONTENT, ' '.join(obj_source.content))
            # ~ doc.add_value(self.SLOT_COUNTRY, obj_source.country)
            # ~ doc.add_value(self.SLOT_NAME, name)

            # ~ identifier = f"P{obj_source.name}"
            # ~ doc.add_term(identifier)

            # ~ db.replace_document(identifier, doc)
            # ~ uploaded_local += 1

        # ~ progress_callback(f"✓ Remaining sources uploaded ({uploaded_local})")
        # ~ uploaded_count += uploaded_local
        time.sleep(0.5)
        print("Files uploaded :")
        print(json.dumps(self.owebui.cache_uploaded, indent=2))
        print("Files still in cache :")
        print(json.dumps(self.owebui.cache_sync, indent=2))
        print("Errors found :")
        print(json.dumps(self.owebui.cache_failed, indent=2))
        sys.stdout.flush()
        # ~ progress_callback(f"✓ Upload terminated: {uploaded_count} entries added in {time.time() - uploaded_total_time} seconds" + '\n')

# Main script
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to add/remove knowledge from Open WebUI.")

    # Tambahkan argumen opsional untuk --add dan --remove
    parser.add_argument('--add', help='File(s) to upload and added to knowledge')
    parser.add_argument('--remove', help='File(s) to remove from knowledge')
    parser.add_argument('--id', required=True, help='Knowledge ID')

    args = parser.parse_args()

    # Validasi argumen
    if args.add and args.remove:
        print("Error: Choose only one action (--add or --remove).")
        exit(1)
    elif not args.add and not args.remove:
        print("Error: Choose only one action (--add atau --remove).")
        exit(1)

    # Tentukan aksi dan target
    if args.add:
        action = "add"
        target = args.add
    elif args.remove:
        action = "remove"
        target = args.remove

    # Proses file
    process_files(args.id, target, action)
