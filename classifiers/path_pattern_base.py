from __future__ import absolute_import, division, print_function, unicode_literals

import random
import re
from collections import defaultdict
import utils
from classifiers.classifier import AbsClassifer
from const.dataset import DataSetIter, DataSetFactory
from const import consts, conf
import math
import datetime

def print(*args, **kwargs):
    return __builtins__.print(*tuple(['[%s]' % str(datetime.datetime.now())] + list(args)), **kwargs)

SPLITTER = re.compile("[" + r'''"#$%&*+,:<=>?@[\]^`{|}~ \-''' + "]")

class ContextsTree:
    def __init__(self):
        class Node:
            def __init__(self, item, clss, score):
                self.i, self.clss, self.score, self.child = item, clss, score, {}

            def add(self, item, clss, score):
                self.child[item] = Node(item, clss, score)

        self.root = Node(None, None, 0)

    def add_rule(self, rule):
        n = self.root
        r, clss, score = rule
        for i, w in enumerate(r):
            if w not in n.child:
                if i == len(r) - 1:
                    n.add(w, clss, score)
                else:
                    n.add(w, None, 0)
            n = n.child[w]

    def search(self, ws):
        rst = consts.NULLPrediction
        for i in range(len(ws)):
            n = self.root
            for j, w in enumerate(ws[i:]):
                if w in n.child:
                    n = n.child[w]
                    if n.score > rst[1]:
                        rst = consts.Prediction(n.clss, n.score, ws[i:i + j + 1])
                else:
                    break
        return rst

Contexts = set()
SPLITTER = re.compile("[" + r'''/''' + "]")

class AgentBoundary():
    def __init__(self):
        self.rules = {}
        #self.support_t = conf.agent_support
        self.support_t = 0.2
        #self.conf_t = conf.agent_score
        self.conf_t = 0.2
        self.K = conf.agent_K
        self.HDB = []
        print('Support', self.support_t, 'Score', self.conf_t, 'K', self.K)

    def train(self, trainSet, ruleType, datasize):
        counter = defaultdict(set); totalApps = set()
        for tbl, pkg in DataSetIter.iter_pkg(trainSet):
            if pkg.path == 'None':
                continue
            path = pkg.path.replace('/', ' / ')
            map(lambda w: counter[w].add(pkg.app), filter(None, path.split(' ')))
            segPath = tuple(['^'] + filter(None, path.split(' ')) + ['$'])
            host = re.sub('[0-9]+\.', '[0-9]+.', pkg.rawHost)
            self.HDB.append((segPath, pkg.app, len(segPath), host))
            totalApps.add(pkg.app)

        self.omega = len(totalApps) * self.support_t
        self.totalApp = len(totalApps) * 1.0

        #self.HDB = list(set(self.HDB))
        self.HDB = [self.HDB[i] for i in sorted(random.sample(xrange(len(self.HDB)), datasize)) ]
        print("Data Size", len(self.HDB))

        groups = defaultdict(list)
        for (t, c, l, host) in self.HDB:
            groups[host].append((t,c,l))

        for host in groups:
            omega = set()
            for (t, c, l) in groups[host]:
                omega.add(c)
            if len(omega) == 1:
                groups[host] = []
                print('skipped', omega, host)

        for host in groups:
            self.host = host
            self.HDB = groups[host]

            for (t, c, l) in self.HDB:
                map(lambda w: counter[w].add(c), t)
            self.IDF = utils.cal_idf(counter)
            self.mine_context()


        self.HDB = groups


    def mine_context(self):
        print('[%s] Start Mining Context' % str(datetime.datetime.now()))
        occurs = defaultdict(list)
        support = defaultdict(set)
        for i in range(len(self.HDB)):
            seq, app, length = self.HDB[i]
            for j in xrange(length):
                occurs[seq[j]].append((i, j))
                support[seq[j]].add(app)

        for item, apps in support.items():
            if len(apps)  > self.omega:
                self.mine_head([item], occurs[item])

    def mine_head(self, prefix, mdb):
        occurs = defaultdict(list)
        support = defaultdict(set)
        for (i, startpos) in mdb:
            if startpos + 1 < self.HDB[i][2]:
                e = self.HDB[i][0][startpos + 1]
                occurs[e].append((i, startpos + 1))
                support[e].add(self.HDB[i][1])
        self.mine_tail(mdb, prefix)
        for e, newmdb in occurs.items():
            if len(support[e])  > self.omega:
                self.mine_head(prefix + [e], newmdb)

    def mine_tail(self, mdb, prefix):
        occurs = defaultdict(list)
        support = defaultdict(set)
        for (i, startpos) in mdb:
            if startpos + 2 < len(self.HDB[i][0]):
                for j in xrange(startpos + 2, self.HDB[i][2]):
                    e = self.HDB[i][0][j]
                    occurs[e].append((i, j))
                    support[e].add(self.HDB[i][1])
        for item, apps in support.items():
            if len(apps)  > self.omega:
                self.mine_tail_rec([item], occurs[item], prefix)

    def mine_tail_rec(self, suffix, mdb, prefix):
        occurs = defaultdict(list)
        support = defaultdict(set)
        for (i, startpos) in mdb:
            if startpos + 1 < self.HDB[i][2]:
                e = self.HDB[i][0][startpos + 1]
                occurs[e].append((i, startpos + 1))
                support[e].add(self.HDB[i][1])
        print('Find a Context', tuple(prefix), tuple(suffix))
        Contexts.add((tuple(prefix), tuple(suffix), self.host))

        for e, newmdb in occurs.items():
            if len(support[e])  > self.omega:
                self.mine_tail_rec(suffix + [e], newmdb, prefix)

    def idf(self, signature):
            return sum([self.IDF.get(i, 0) for i in signature]) / len(signature)

    def rel(self, signature, appSigMap, sigAppMap):
        return math.sqrt(1 / len(appSigMap[list(sigAppMap[signature])[0]]))

    def build_rules(self):
        def context_quality(s, e):
            return 2 * s * e / (s + e)

        contexts = dict()
        Rules = defaultdict(list)

        for context in Contexts:
            head, tail, host = context
            head, tail = map(lambda lst : ''.join(lst), [head, tail])
            print("Head:", head, "Tail:", tail)
            contexts[re.compile('(?=(' + re.escape(head) + '(.*?)' + re.escape(tail) + '))')] = (head, tail, host)

        for reg in contexts:
            appSigMap = defaultdict(set); seqAppMap = defaultdict(set)
            SC = defaultdict(set)
            head, tail, host = contexts[reg]
            support = set()

            for i in range(len(self.HDB[host])):
                dataset = self.HDB[host]
                (t, app, l) = dataset[i]
                t = ''.join(t)
                if head in t and tail in t:
                    print(t, head, tail, reg.pattern)
                    print(reg.findall(t))
                    for seqStr in map(lambda x:x[1], reg.findall(t)):
                        support.add(app); SC[seqStr].add(i)
                        seqAppMap[seqStr].add(app); appSigMap[app].add(seqStr)


            effective = 0
            for app, seqs in appSigMap.items():
                for seq in seqs:
                    if len(seqAppMap[seq]) == 1:
                        effective += self.idf(seq.split('/')) * self.rel(seq, appSigMap, seqAppMap)


            contextQuality = context_quality(len(support) / self.totalApp, effective * 1.0 / len(seqAppMap))

            if contextQuality > self.conf_t:
                for seqStr in SC.keys():
                    if len(seqAppMap[seqStr]) == 1:
                        for i in SC[seqStr]:
                            sigQuality = self.idf(seqStr.split('/')) * self.rel(seqStr, appSigMap, seqAppMap)
                            currentLen = len(head.split('/')) + len(tail.split('/')) + len(seqStr.split('/'))
                            Rules[host+str(i)].append((head, tail, seqStr, contextQuality, sigQuality, currentLen, self.HDB[i][1]))
                            Rules[host+str(i)] = sorted(Rules[host+str(i)], key=lambda x: (x[3], x[4], 10000 - x[5]), reverse=True)[:self.K]
                        # print('Find a signature', seqStr, 'HEAD:', head, 'TAIL:', tail, 'Score:', contextQuality)
        # for i, rules in Rules.items():
        #     for rule in rules:
        #         print("Find a rule", rule, "Origin:", self.HDB[i][0])


if __name__ == '__main__':
    tbls = ['ca_ios_packages_2015_12_10', 'ca_ios_packages_2015_05_29', 'ca_ios_packages_2016_02_22',
            'chi_ios_packages_2015_07_20', 'chi_ios_packages_2015_09_24', 'chi_ios_packages_2015_09_24']

    trainSet = DataSetFactory.get_traindata(tbls=tbls, appType=consts.IOS)
    for size  in [300000]:
        a = AgentBoundary()
        a.train(trainSet, consts.IOS, size)
        print('Find Contexts', len(Contexts))
        print('Start Building Rule')
        a.build_rules()