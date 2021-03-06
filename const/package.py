# -*- coding=utf-8 -*-
import urlparse
import urllib
import tldextract

class Package:

    def set_method(self, method):
        self.method = method

    def __init__(self, DB):
        self.json = None
        self.form = None
        self.content = None
        self.tbl = DB

    def set_tbl(self, tbl):
        self.tbl = tbl

    def set_label(self, label):
        self.label = label

    def set_id(self, id):
        self.id = self.tbl + '$' + str(id)

    def set_dst(self, dst):
        self.dst = dst

    def set_appinfo(self, appInfo):
        self.appInfo = appInfo

    @property
    def name(self):
        return self.appInfo.name

    @property
    def app(self):
        return self.app

    @property
    def category(self):
        return self.appInfo.category

    @property
    def company(self):
        return self.appInfo.company

    @property
    def website(self):
        return self.appInfo.website

    @property
    def trackId(self):
        return self.appInfo.trackId

    def set_app(self, app):
        self.app = app.lower()

    def set_refer(self, refer):
        self.refer_origpath = refer
        url = urllib.unquote(refer).lower()
        if '?' in url:
            url = url.replace(';','?', 1)
        url = url.replace(';', '&')
        parsed_url = urlparse.urlparse(url)
        query = urlparse.parse_qs(urlparse.urlparse(url).query, True)
        host = parsed_url.netloc
        # path = parsed_url.path
        self.refer_rawHost = host.replace('http://', '').split('/')[0].split(':')[0]
        self.refer_host = self.refer_rawHost.replace('www.', '')
        self.refer_queries = query

        extracted = tldextract.extract(self.refer_host)
        self.refer_secdomain = None
        if len(extracted.domain) > 0:
            self.refer_secdomain = "{}.{}".format(extracted.domain, extracted.suffix)

    def set_path(self, path):
        self.origPath = path
        path = urllib.unquote(path).lower()
        if '?' not in path:
            path = path.replace(';','?', 1)
        path = path.replace(';', '&')
        self.queries = urlparse.parse_qs(urlparse.urlparse(path).query, True)
        self.path = urlparse.urlparse(path).path

    def set_add_header(self, add_header):
        self.add_header = add_header.lower()

    def set_host(self, host):
        host = host.lower()
        self.rawHost = host.replace(':80', '')
        self.host = host.split(':')[0].replace('www.', '').replace('http://', '')
        extracted = tldextract.extract(host)
        self.secdomain = None

        if len(extracted.domain) > 0:
            self.secdomain = "{}.{}".format(extracted.domain, extracted.suffix)

    def set_agent(self, agent):
        self.agent = agent.lower()

    def set_content(self, content):
        content = content.lower()
        if 'layer json' in content:
            self.json = self._process_json(content)
        if 'layer urlencoded-form' in content:
            self.form = self._process_form(content)
        self.content = content

    def _process_form(self, content):
        """change urlencoded forms to maps"""
        key_values = {}
        for line in filter(None, content.strip().split('\n')):
            if 'form item' in line:
                line = line.replace("\"", '').replace('form item:', '').replace(' ', '')
                if '=' in line:
                    key, value = line.split('=')[:2]
                    key_values[key.strip()] = value.strip()
        return key_values

    def _process_json(self, content):
        """change json content to string items"""
        items = []
        for line in filter(None, content.split('\n')):
            if 'value' in line and ':' in line:
                items.append(':'.join(map(lambda seg: seg.strip(), line.split(':')[1:])))
        return items

    @app.setter
    def app(self, value):
        self._app = value
