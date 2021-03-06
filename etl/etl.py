import pyshark
import sys

import const.consts as consts
from const import sql
from const.app_info import AppInfos
from sqldao import SqlDao


class ETLConsts:
    APP = 'app'
    SOURCE = 'src'
    DESTINATION = 'dst'
    TIME = 'time'
    ADD_HEADER = 'add_header'
    HOST = 'hst'
    PATH = 'path'
    ACCEPT = 'accpt'
    AGENT = 'agent'
    REFER = 'refer'
    AUTHOR = 'author'
    CONTENT_LENGTH = 'cntlength'
    CONTENT_TYPE = 'cnttype'
    METHOD = 'method'
    SIZE = 'size'
    HTTP_TYPE = 'httptype'  # 0 is GET 1 is POST
    RAW = 'raw'


class ETL:
    def __init__(self, tablename, app_type, exp_apps_path = None):
        self.INSERT_PACKAGES = ("INSERT INTO " + tablename + " "
                                "(app,src,dst,time,add_header,hst, path, accpt, agent, refer, author, cntlength, cnttype, method, size, httptype, name, category, company, raw)"
                                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")
        self.INSERT_HOST = 'INSERT INTO host (app, host) VALUES(%s, %s)'
        exp_apps = []
        for ln in open(exp_apps_path):
            if ln.startswith('#'):
                continue
            exp_apps.append(ln.strip())
        self._get_app_info(exp_apps)
        self.app_type = app_type

    def _get_app_info(self, exp_apps):
        self.apps = AppInfos
        tmp_apps = {}
        for exp_app in exp_apps:
          exp_app = exp_app.split(':')[1]
          appInfo = self.apps.get(app_type, exp_app)
          tmp_apps[exp_app] = appInfo
        self.apps = tmp_apps


    def upload_packages(self, folder, app_type):
        """
        Insert pcap information into db
        """
        from os import listdir
        from os.path import isfile, join

        startFlag = False
        counter = 0
        for f in listdir(folder):
            file_path = join(folder, f)
            if isfile(file_path):
                app_name = f[0:-5]
                self._insert_msql(join(folder, f), app_name, app_type)
                counter += 1
                print 'Have instered', counter, 'pcaps'


    def _insert_msql(self, file_path, app_package, app_type):
        import time
        startTime = time.time()
        print "Start inserting", app_package, file_path
        dbdao = SqlDao()

        appInfo = self.apps.get(app_package, None)
        if appInfo == None:
            if app_type == consts.IOS:
                print 'Error!! Can not find', app_package
        packages = pyshark.FileCapture(file_path, display_filter='http')
        timeStampTwo = time.time()
        print 'Get appInfo', timeStampTwo - startTime

        dns_info = {}
        comunicate_host = set()

        if appInfo is not None:
            app_package = appInfo.package
            app_name = appInfo.name
            app_category = appInfo.category
            app_company = appInfo.company
        else:
            app_name = None
            app_category = None
            app_company = None


        pkgInfos = []
        while True:
            try:
                p = packages.next()
                if hasattr(p, 'http'):
                    pkgInfo = self._parse_http_package(p)
                    if pkgInfo[ETLConsts.HOST] == None or len(pkgInfo[ETLConsts.HOST]) == 0 or '.' not in pkgInfo[ETLConsts.HOST]:
                        ip = pkgInfo[ETLConsts.DESTINATION]
                        if ip in dns_info and len(dns_info[ip]) == 1:
                            host = dns_info[ip].pop()
                            pkgInfo[ETLConsts.HOST] = host
                            dns_info[ip].add(host)
                    pkgInfo['app_name'] = app_name
                    pkgInfo['app_category'] = app_category
                    pkgInfo['app_company'] = app_company
                    pkgInfos.append(pkgInfo)
                    if len(pkgInfos) > 500:
                        break
                    if time.time() - timeStampTwo > 5:
                        print "Spent more than 10s. Stop"
                        break
                else:
                  print app_name, app_category, app_company
                  print 'ERROR WRONG PACKAGE TYPE'

            except StopIteration:
                break
            except:
                 print 'ERROR', sys.exc_info()[0]
        try:
            packages.close()
        except:
            pass
        timeStampThree = time.time()
        print 'Parsing pcaps', timeStampThree - timeStampTwo
        params = []
        for pkgInfo in pkgInfos:
            app_name = pkgInfo['app_name'] 
            app_category = pkgInfo['app_category'] 
            app_company = pkgInfo['app_company'] 
            params.append((app_package, 
                pkgInfo[ETLConsts.SOURCE], 
                pkgInfo[ETLConsts.DESTINATION], 
                pkgInfo[ETLConsts.TIME], 
                pkgInfo[ETLConsts.ADD_HEADER], 
                pkgInfo[ETLConsts.HOST], 
                pkgInfo[ETLConsts.PATH], 
                pkgInfo[ETLConsts.ACCEPT], 
                pkgInfo[ETLConsts.AGENT], 
                pkgInfo[ETLConsts.REFER], 
                pkgInfo[ETLConsts.AUTHOR], 
                pkgInfo[ETLConsts.CONTENT_LENGTH], 
                pkgInfo[ETLConsts.CONTENT_TYPE], 
                pkgInfo[ETLConsts.METHOD], 
                pkgInfo[ETLConsts.SIZE], 
                pkgInfo[ETLConsts.HTTP_TYPE], 
                app_name, 
                app_category, 
                app_company, 
                pkgInfo[ETLConsts.RAW]))
            comunicate_host.add(pkgInfo[ETLConsts.HOST])
        dbdao.executeBatch(self.INSERT_PACKAGES,params)
        dbdao.close()
        print 'inserting', time.time() - timeStampThree
        print "Finish", app_package, "Package:", len(params), len(pkgInfos)

    # def _parse_dns_package(self, package, dns_info):
    #     amount = package[DNS].ancount
    #     for i in range(amount):
    #         dnsrr = package[DNSRR][i]
    #         host = dnsrr.rrname
    #         ip = dnsrr.rdata
    #         dns_info.setdefault(ip, set())
    #         dns_info[ip].add(package.qd.qname[:-1])


    def _parse_http_package(self, package):
        known_fileds = {'Host',
                        'Connection',
                        'Accept-Encoding',
                        'Accept',
                        'User-Agent',
                        'Referer',
                        'Accept-Language',
                        'Content-Type',
                        'Content-Length',
                        'Date',
                        'Content-Encoding',
                        'Transfer-Encoding',
                        'Cache-Control',
                        'Pragma',
                        'Accept-Ranges',
                        'Full request URI',
                        'Message',
                        'Request Method',
                        'Request URI',
                        'POST',
                        'GET'}
        pkgInfo = {}
        #src = package.ip.src
        #dst = package.ip.dst
        src = ''
        dst = ''
        time = package.sniff_timestamp
        add_header = '\n'.join([i.strip().replace('\\r\\n', '')
                                for i in package.http._get_all_field_lines()
                                if i.split(':')[0].strip() not in known_fileds])
        
        # if hasattr(package.http, 'response_line'):
        #     add_header = '\n'.join([i.showname.replace('\\r\\n', '')
        #                             for i in package.http.response_line.alternate_fields
        #                             if i.showname.split(':')[0].strip() not in known_fileds])
        #     print add_header
        # elif hasattr(package.http, 'request_line'):
        #     print add_header
        #     add_header = '\n'.join([i.showname.replace('\\r\\n', '')
        #                             for i in package.http.request_line.alternate_fields
        #                             if i.showname.split(':')[0].strip() not in known_fileds])
        add_header = add_header.replace('[truncated]', '')

        hst = getattr(package.http, "host", None)
        path = getattr(package.http, "request_uri", None)
        accpt = getattr(package.http, "Accept", None)
        agent = getattr(package.http, "user_agent", None)
        refer = getattr(package.http, "referer", None)
        author = getattr(package.http, "Authorization", None)
        cntlength = getattr(package.http, "content_length", None)
        cnttpe = getattr(package.http, "content_type", None)
        method = getattr(package.http, "request_method", None)
        size = package.length
        raw = None
        if package[-1] != package.http:
            raw = str(package[-1])
        pkgInfo[ETLConsts.SOURCE] = str(src)
        pkgInfo[ETLConsts.DESTINATION] = str(dst)
        pkgInfo[ETLConsts.TIME] = time
        pkgInfo[ETLConsts.ADD_HEADER] = add_header
        pkgInfo[ETLConsts.HOST] = str(hst)
        pkgInfo[ETLConsts.PATH] = str(path)
        pkgInfo[ETLConsts.ACCEPT] = str(accpt)
        pkgInfo[ETLConsts.AGENT] = str(agent)
        pkgInfo[ETLConsts.REFER] = str(refer)
        pkgInfo[ETLConsts.AUTHOR] = str(author).replace('\\"', '')
        pkgInfo[ETLConsts.CONTENT_LENGTH] = str(cntlength)
        pkgInfo[ETLConsts.CONTENT_TYPE] = str(cnttpe)
        pkgInfo[ETLConsts.METHOD] = str(method)
        pkgInfo[ETLConsts.SIZE] = str(size)
        pkgInfo[ETLConsts.RAW] = raw
        if hasattr(package.http, 'request'):
            pkgInfo[ETLConsts.HTTP_TYPE] = 0
        elif hasattr(package.http, 'response'):
            pkgInfo[ETLConsts.HTTP_TYPE] = 1
            if raw and len(raw) >= 3000:
              pkgInfo[ETLConsts.RAW] = None
        else:
            pkgInfo[ETLConsts.HTTP_TYPE] = None

        for k, v in pkgInfo.items():
            if v == None:
                pkgInfo[k] = ""
        return pkgInfo

def create_tbl(tableName):
    sqldao = SqlDao()
    sqldao.execute(sql.SQL_CREATE_PACKAGE % tableName)
    sqldao.close()

if __name__ == '__main__':
    if len(sys.argv) < 4:
      print 'python etl.py <path> <tablename> [ios|android] [exp_app_file]'
      sys.exit()
    path = sys.argv[1]
    tablename = sys.argv[2]

    create_tbl(tablename)

    app_type = sys.argv[3]
    if app_type == 'ios':
      app_type = consts.IOS
    else:
      app_type = consts.ANDROID

    exp_app_path = None

    if len(sys.argv) == 5:
      exp_app_path = sys.argv[4]

    etl = ETL(tablename, app_type, exp_app_path)
    etl.upload_packages(path, app_type)
