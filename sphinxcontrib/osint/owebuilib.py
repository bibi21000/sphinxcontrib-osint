# -*- encoding: utf-8 -*-
"""
owebui enhanced API
--------------------------------------

"""
import os
import json
import hashlib
import requests
import magic

class OwebuiAPI:

    def __init__(self, apikey, url_base='http://127.0.0.1:8080',
            connect_timeout=120, read_timeout=600):
        self.apikey = apikey
        self.url_base = url_base
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.session = None
        self.cache_uploaded = {}
        self.cache_failed = {}
        self.cache_sync = None

    @property
    def headers(self):
        return {
            'Authorization': f'Bearer {self.apikey}',
            'Accept': 'application/json'
        }

    def _get_session(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = self.headers

    def app_version(self):
        self._get_session()

        url = f'{self.url_base}/_app/version.json'

        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_list_files(self, content=True):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/'
        params = [('content', content)]

        response = self.session.get(
            url,
            params=params,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_delete_files(self):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/all'

        response = self.session.delete(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_delete_file(self, fileid):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/{fileid}'

        response = self.session.delete(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_upload_file(self, fileobj=None, filename=None, metadata=None):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/'

        need_close = False
        if fileobj is None:
            fileobj = os.open(filename, 'rb', mode=0o444)
            need_close = True
        fileobj.seek(0)
        mime_type = magic.from_buffer(fileobj.read(2048), mime=True)
        if mime_type is None:
            mime_type = 'application/octet-stream'

        if metadata is None:
            data = {}
        else:
            data = { "metadata": json.dumps(metadata)}

        fileobj.seek(0)
        response = self.session.post(
            url,
            files={'file': (filename, fileobj, mime_type)},
            data=data,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        if need_close is True:
            fileobj.close()
        return response.json()

    def api_get_file(self, fileid):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/{fileid}'

        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_status_file(self, fileid):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/{fileid}/process/status'

        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_wait_file(self, fileid):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/{fileid}/process/status?stream=true'
        with self.session.get(url, stream=True) as response:
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        status = data.get('status')

                        if status == 'completed':
                            return True, data
                        elif status == 'failed':
                            return False, data

        raise Exception("Stream ended unexpectedly")

    def api_know_add_file(self, fileid, knowledgeid):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/file/add'
        payload = {'file_id': fileid}
        response = self.session.post(url, json=payload)
        return response.json()

    def api_know_remove_file(self, fileid, knowledgeid, delete_file=False):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/file/remove'
        payload = {'file_id': fileid, 'delete_file': delete_file}
        response = self.session.post(url, json=payload)
        return response.json()

    def api_know_update_file(self, fileid, knowledgeid):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/file/update'
        payload = {'file_id': fileid}
        response = self.session.post(url, json=payload)
        return response.json()

    def api_know_list_files(self, knowledgeid, content=True):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/files'
        ret = {'total':0, 'items':[]}
        page = 1
        while True:
            params = [('page', page)]
            response = self.session.get(url, params=params)
            rep = response.json()
            ret['total'] = rep['total']
            if content is False:
                for r in rep['items']:
                    del r['data']['content']
            ret['items'].extend(rep['items'])
            page += 1
            if len(rep['items']) < 30:
                break
        return ret

    def api_know_create(self, payload):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/create'
        response = self.session.post(url, json=payload)
        return response.json()

    def api_model_create(self, payload):
        self._get_session()

        url = f'{self.url_base}/api/v1/models/create'
        response = self.session.post(url, json=payload)
        return response.json()

    def api_models(self, knowledgeid=None):
        self._get_session()

        url = f'{self.url_base}/api/v1/models/list'
        response = self.session.get(url)
        mdls = response.json()
        if knowledgeid is None:
            return mdls
        ret = {'items': [], 'total': 0}
        for mdl in mdls['items']:
            if 'knowledge' in mdl['meta']:
                for kld in mdl['meta']['knowledge']:
                    if kld["id"] == knowledgeid:
                        ret['items'].append(mdl)
                        break
        ret["total"] = len(ret["items"])
        return ret

    def api_ollama_satus(self):
        self._get_session()

        url = f'{self.url_base}/ollama/'
        response = self.session.get(url)
        return response.json()

    def add_model_for_knowledge(self, knowledgeid):
        try:
            retw = self.api_wait_file(fileid)
        except Exception:
            import traceback
            self.cache_failed[fileid] = {
                "detail" : traceback.format_exc().splitlines(),
                "knowledgeid" : knowledgeid,
                "fileid" : fileid,
            }
            return False, self.cache_failed[fileid]
        if retw[0] is False:
            return retw
        ret = self.api_know_add_file(fileid, knowledgeid)
        return True, ret

    def upload_file(self, fileobj=None, filename=None, metadata=None,
            knowledgeid=None, wait=False, retries=3, retry_wait=1):
        # ~ current = retries
        # ~ while current > 0:
        try:
            ret = self.api_upload_file(fileobj=fileobj, filename=filename, metadata=metadata)
        except Exception:
            import traceback
            self.cache_failed[filename] = {
                "detail" : traceback.format_exc().splitlines(),
                "filename" : filename,
            }
        # ~ print(ret)
        if knowledgeid is None and wait is False:
            return True, ret
        fileid = ret['id']
        self.cache_uploaded[fileid] = ret
        retw = self.api_wait_file(fileid)
        if retw[0] is False:
            self.cache_failed[fileid] = {
                "error" : retw[1],
                "file" : self.api_get_file(fileid),
            }
            return retw
        if knowledgeid is not None:
            self.api_know_add_file(fileid, knowledgeid)
        ret = self.api_get_file(fileid)
        return True, ret

    def add_file_to_knowledge(self, fileid, knowledgeid):
        try:
            retw = self.api_wait_file(fileid)
        except Exception:
            import traceback
            self.cache_failed[fileid] = {
                "detail" : traceback.format_exc().splitlines(),
                "knowledgeid" : knowledgeid,
                "fileid" : fileid,
            }
            return False, self.cache_failed[fileid]
        if retw[0] is False:
            return retw
        ret = self.api_know_add_file(fileid, knowledgeid)
        return True, ret

    def clean_all(self):
        return self.api_delete_files()

    def clean_orphans(self):
        for f in self.list_files(orphans=True)['items']:
            self.api_delete_file(f['id'])
        return self.list_files(orphans=True)

    def create_knowledge(self, name: str, description: str) -> dict:
        payload = {
            "name": name,
            "description": description,
            "data": {},
            "access_control": {},
        }
        return self.api_know_create(payload)

    def clean_knowledge(self, knowledgeid, delete_files=False):
        ret = self.api_know_list_files(knowledgeid)
        for f in ret['items']:
            ret = self.api_know_remove_file(f['id'], knowledgeid, delete_file=delete_files)
        return self.api_know_list_files(knowledgeid)

    def list_files(self, knowledgeid=None, orphans=False, content=True):
        if orphans is True:
            rep = self.api_list_files(content=content)
            ret = [f for f in rep['items'] if 'collection_name' not in f['meta']]
            return {'items': ret, 'total': len(ret)}
        if knowledgeid is None:
            rep = self.api_list_files(content=content)
            return {'items': rep, 'total': len(rep)}
        return self.api_know_list_files(knowledgeid, content=content)

    def search_files(self, pattern, knowledgeid=None, content=False, limit=0, skip=0):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers = self.headers

        url = f'{self.url_base}/api/v1/files/search'

        if limit != 0:
            params = [('filename', pattern), ('content', content), ('limit', limit), ('skip', skip)]
            response = self.session.get(
                url,
                params=params,
                timeout=(self.connect_timeout, self.read_timeout)
            )
            ret = response.json()
            if knowledgeid is not None:
                ret = [r for r in ret if 'collection_name' in r['meta'] and r['meta']['collection_name']==knowledgeid]
            return {"items": ret, "total": len(ret)}
        else:
            more = True
            skip = 0
            limit = 500
            ret = []
            while more is True:
                params = [('filename', pattern), ('content', content), ('limit', limit), ('skip', skip)]
                response = self.session.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=(self.connect_timeout, self.read_timeout)
                )
                rep = response.json()
                ret += rep
                if len(rep) == limit:
                    skip += limit
                else:
                    more = False
            if knowledgeid is not None:
                ret = [r for r in ret if 'collection_name' in r['meta'] and r['meta']['collection_name']==knowledgeid]
            return {"items": ret, "total": len(ret)}

    def create_model(self, name: str, description: str, knowledgeid: str,
            prompt: str, base_model: str, num_ctx: int = 16000) -> dict:
        payload = {
            "id": name,
            "name": name,
            "base_model_id": base_model,
            "meta": {
                "description": description,
               "knowledge": [
                    {
                        "id": knowledgeid,
                        "type": "collection",
                    }
                ],
            },
            "params": {
                "system": prompt,
                "num_ctx": num_ctx,
            },
        }
        return self.api_model_create(payload)

    def status(self) -> dict:
        ok = True
        ret = {}
        rep = self.api_ollama_satus()
        if 'status' in rep and rep['status'] is True:
            ret['ollama'] = True
        else:
            ok = False
        rep = self.app_version()
        if 'version' in rep:
            ret['app'] = True
        else:
            ok = False
        return ok, ret

    def hash(self,data):
        return hashlib.sha256(data.encode()).hexdigest()

    def hash_meta_data(self,data):
        return hashlib.sha256(str(data).encode()).hexdigest()

    def sync_begin(self, cid="id"):
        self.cache_sync = {}
        data = self.list_files(self, content=False)
        for d in data['items']:
            self.cache_sync[d[cid]] = d
            self.cache_sync[d[cid]]['hash_meta_data'] = self.hash_meta_data(d['meta']['data'])

    def sync_finish(self, knowledgeid=None, cid="id"):
        for f in self.cache_sync:
            if 'collection_name' not in f or f['meta']['collection_name'] != knowledgeid:
                del self.cache_sync[f[cid]]

    def sync_delete(self, knowledgeid=None, cid="id"):
        for f in self.cache_sync:
            self.api_delete_file(self.cache_sync[f][cid])
        self.cache_sync = {}

    def sync_file(self, fileobj=None, filename=None, metadata=None,
            knowledgeid=None, cid="filename",
            wait=False, retries=3, retry_wait=1):
        if self.cache_sync is None:
            self.sync_begin(knowledgeid=knowledgeid, cid=cid)
        if filename not in self.cache_sync:
            return self.upload_file(fileobj=fileobj, filename=filename, metadata=metadata,
                knowledgeid=knowledgeid, wait=wait, retries=retries, retry_wait=retry_wait)

        hash_content = self.hash(fileobj.read())
        hash_meta_data = self.hash_meta_data(metadata)
        fileobj.seek(0)

        if hash_content == self.cache_sync[filename]["hash"] and \
          hash_meta_data == self.cache_sync[filename]["hash_meta_data"]:
            file_id = self.cache_sync[filename]["id"]
            if wait is True and ('collection_name' not in self.cache_sync[filename] or self.cache_sync[filename]['meta']['collection_name'] != knowledgeid):
                self.api_know_add_file(file_id, knowledgeid)
            del self.cache_sync[filename]
            return True, self.api_get_file(file_id)

        self.api_delete_file(self.cache_sync[filename]["id"])
        del self.cache_sync[filename]
        return self.upload_file(fileobj=fileobj, filename=filename, metadata=metadata,
            knowledgeid=knowledgeid, wait=wait, retries=retries, retry_wait=retry_wait)

    def sync_knowledge(self, fileid, knowledgeid, cid="filename",
            fileobj=None, filename=None, metadata=None,
            wait=False, retries=3, retry_wait=1):
        if self.cache_sync is None:
            self.sync_begin(knowledgeid=knowledgeid, cid=cid)
        if filename not in self.cache_sync:
            return self.upload_file(fileobj=fileobj, filename=filename, metadata=metadata,
                knowledgeid=knowledgeid, wait=wait, retries=retries, retry_wait=retry_wait)

        hash_content = self.hash(fileobj.read())
        hash_meta_data = self.hash_meta_data(metadata)
        fileobj.seek(0)

        if hash_content == self.cache_sync[filename]["hash"] and \
          hash_meta_data == self.cache_sync[filename]["hash_meta_data"]:
            file_id = self.cache_sync[filename]["id"]
            if wait is True and ('collection_name' not in self.cache_sync[filename] or self.cache_sync[filename]['meta']['collection_name'] != knowledgeid):
                self.api_know_add_file(file_id, knowledgeid)
            del self.cache_sync[filename]
            return True, self.api_get_file(file_id)

        self.api_delete_file(self.cache_sync[filename]["id"])
        del self.cache_sync[filename]
        return self.upload_file(fileobj=fileobj, filename=filename, metadata=metadata,
            knowledgeid=knowledgeid, wait=wait, retries=retries, retry_wait=retry_wait)
