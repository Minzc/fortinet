import urllib
import const.consts as consts
import re

from classifiers.uri import UriClassifier
from sqldao import SqlDao
from utils import load_xml_features, if_version, flatten, get_label
from collections import defaultdict, namedtuple
from classifier import AbsClassifer
from const.dataset import DataSetIter as DataSetIter

DEBUG = False
PATH = '[PATH]:'


class Path:
    def __init__(self, scoreT, dbcover):
        self.scoreThreshold = scoreT
        self.name = consts.PATH_MINER
        self.dbcover = dbcover

    def mine_host(self, trainSet, ruleType):
        uriClassifier = UriClassifier(consts.IOS)
        print '[URI] Start Training'
        hostRules, _ = uriClassifier.train(trainSet, ruleType, ifPersist=False)
        print '[URI] Finish Training'
        cHosts = {}
        for ruleType in hostRules:
            for rule, tbls in hostRules[ruleType].items():
                host, _, label = rule
                cHosts[host] = tbls
            print "Total Number of Hosts is", len(cHosts)
        self.cHosts = cHosts

    @staticmethod
    def get_f(package):
        host = re.sub('[0-9]+\.', '[NUM].', package.rawHost)
        tmp = []
        for pathSeg in filter(None, package.path.split('/')):
            key = PATH + '/'.join(tmp)
            tmp.append(pathSeg)
            value = '/'.join(tmp)
            yield (host, key, value)


    def classify_format(self, package):
        host = package.refer_rawHost if package.refer_rawHost else package.rawHost
        host = re.sub('[0-9]+\.', '[NUM].', host)
        path = package.refer_origpath if package.refer_rawHost else package.origPath
        return host, path

    def txt_analysis(self, valueLabelCounter, trainData):
        xmlGenRules = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        xmlSpecificRules = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        return xmlGenRules, xmlSpecificRules

    def prune(self, keys):
        """
        key format Rule(secdomain, key, score, labelNum)
        :param keys:
        :return:
        """
        prunedK = {}
        for secdomain, keys in keys.items():
            keys = [key for key in keys if key.score > self.scoreThreshold or secdomain in self.cHosts]
            prunedK[secdomain] = keys
        return prunedK

    def sort(self, genRules, txtRules):
        def compare(genRule):
            ifTxtRule = 1 if (genRule.secdomain, genRule.key) in txtRules else 0
            length = len(genRule.key.split('/'))
            return (ifTxtRule, genRule.score, length)

        sGenRules = sorted(genRules, key=compare, reverse=True)
        return sGenRules

    def gen_txt_rule(self, xmlSpecificRules, specificRules, trackIds):
        return specificRules


class KV:
    def __init__(self, scoreT, labelT, dbcover):
        self.xmlFeatures = load_xml_features()
        self.scoreThreshold = scoreT
        self.labelThreshold = labelT
        self.dbcover = dbcover
        self.name = consts.KV_MINER

    @staticmethod
    def get_f(package):
        host = re.sub('[0-9]+\.', '[NUM].', package.rawHost)
        queries = package.queries
        for k, vs in queries.items():
            for v in vs:
                yield (host, k, v)

    def classify_format(self, package):
        host = package.refer_rawHost if package.refer_rawHost else package.rawHost
        host = re.sub('[0-9]+\.', '[NUM].', host)
        path = package.refer_origpath if package.refer_rawHost else package.origPath
        return host, path

    def txt_analysis(self, valueLabelCounter, trainData):
        """
        Match xml information in training data
        Output
        :return xmlGenRules : (host, key) -> value -> {app}
        :return xmlSpecificRules
        """
        xmlGenRules = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        xmlSpecificRules = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        for tbl, pkg in DataSetIter.iter_pkg(trainData):
            for host, k, v in self.get_f(pkg):
                if if_version(v) == False and len(valueLabelCounter[consts.APP_RULE][v]) == 1:
                    for fieldName in [name for name, value in self.xmlFeatures[pkg.app] if value == v]:
                        xmlGenRules[(host, k)][v][fieldName] += 1
                        xmlSpecificRules[(host, k)][v][pkg.app].add(tbl)

        return xmlGenRules, xmlSpecificRules

    def prune(self, keys):
        """
        key format Rule(secdomain, key, score, labelNum)
        :param keys:
        :return:
        """
        prunedK = {}
        for secdomain, keys in keys.items():
            keys = [key for key in keys if key.score > self.scoreThreshold and key.labelNum > self.labelThreshold]
            prunedK[secdomain] = keys
        return prunedK

    def sort(self, genRules, txtRules):
        def compare(genRule):
            ifTxtRule = 1 if (genRule.secdomain, genRule.key) in txtRules else 0
            return (ifTxtRule, genRule.score, genRule.labelNum)

        sGenRules = sorted(genRules, key=compare, reverse=True)
        return sGenRules

    def gen_txt_rule(self, xmlSpecificRules, specificRules, trackIds):
        """
        :param trackIds:
        :param xmlSpecificRules:
        :param specificRules : specific rules for apps
             host -> key -> value -> label -> { rule.score, support : { tbl, tbl, tbl } }
        """
        for rule, v, app, tbls in flatten(xmlSpecificRules):
            if v not in trackIds and len(re.sub('[0-9]', '', v)) < 2:
                continue
            host, key = rule
            specificRules[host][key][v][app][consts.SCORE] = 1.0
            specificRules[host][key][v][app][consts.SUPPORT] = tbls
        return specificRules

    def mine_host(self, trainSet, ruleType):
        pass

class KVClassifier(AbsClassifer):
    def __init__(self, appType, minerType):
        def __create_dict():
            return defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(set))))

        self.name = consts.KV_CLASSIFIER
        self.compressedDB = {consts.APP_RULE: __create_dict(), consts.CATEGORY_RULE: __create_dict()}
        self.valueLabelCounter = {consts.APP_RULE: defaultdict(set), consts.CATEGORY_RULE: defaultdict(set)}
        self.rules = {}
        self.appType = appType

        if minerType == consts.PATH_MINER:
            self.miner = Path(scoreT=1, dbcover=1)
        elif minerType == consts.KV_MINER:
            self.miner = KV(scoreT=0.9, labelT=1, dbcover=3)

        self.rules = {consts.APP_RULE: defaultdict(lambda: defaultdict(
            lambda: {'score': 0, 'support': 0, 'regexObj': None, 'label': None})),
                      consts.COMPANY_RULE: defaultdict(lambda: defaultdict(
                          lambda: {'score': 0, 'support': 0, 'regexObj': None, 'label': None})),
                      consts.CATEGORY_RULE: defaultdict(lambda: defaultdict(
                          lambda: {'score': 0, 'support': 0, 'regexObj': None, 'label': None}))}

    def _prune_general_rules(self, generalRules, trainData, xmlGenRules):
        """
        1. PK by coverage
        2. Prune by xml rules
        Input
        :param generalRules : {secdomain : [(secdomain, key, score, labelNum), rule, rule]}
        :param trainData : { tbl : [ packet, packet, ... ] }
        :param xmlGenRules : {( host, key) }
        """
        generalRules = self.miner.prune(generalRules)
        for host in generalRules:
            generalRules[host] = self.miner.sort(generalRules[host], xmlGenRules)

        coverage = defaultdict(int)
        prunedGenRules = defaultdict(set)
        for tbl, pkg in DataSetIter.iter_pkg(trainData):
            kv = {}
            for host, key, value in self.miner.get_f(pkg):
                kv[key] = value

            if pkg.host == 'login.constantcontact.com':
                print '[algo203]', kv, generalRules['login.constantcontact.com']

            if host in generalRules:
                for rule in generalRules[host]:
                    if rule.key in kv and coverage[tbl + '#' + str(pkg.id)] < self.miner.dbcover:
                        coverage[tbl + '#' + str(pkg.id)] += 1
                        prunedGenRules[host].add(rule)

        for host, rules in prunedGenRules.items():
            prunedGenRules[host] = sorted(rules, key=lambda x: x[2], reverse=True)
            tmp = []
            for index, rule in enumerate(prunedGenRules[host]):
                # if counter == 1 or prunedGenRules[host][index-1][2] - rule[2] >= 1:
                if prunedGenRules[host][index - 1][2] - rule[2] >= 1:
                    break
                tmp.append(rule)
            prunedGenRules[host] = tmp
        return prunedGenRules

    @staticmethod
    def _score(featureTbl, valueLabelCounter):
        """
        Give score to every ( secdomain, key ) pairs
        Input
        :param featureTbl :
            Relationships between host, key, value and label(app or company) from training data
            { secdomain : { key : { label : {value} } } }
        :param valueLabelCounter :
            Relationships between labels(app or company)
            { app : {label} }
        """
        # secdomain -> app -> key -> value -> tbls
        # secdomain -> key -> (label, score)
        keyScore = defaultdict(lambda: defaultdict(lambda: {consts.LABEL: set(), consts.SCORE: 0}))
        for host, k, label, v, tbls in flatten(featureTbl):
            if host == 'login.constantcontact.com':
                print '[algo240]', k, featureTbl[host][k][label]
            cleanedK = k.replace("\t", "")
            if len(valueLabelCounter[v]) == 1 and if_version(v) == False:
                numOfValues = len(featureTbl[host][k][label])
                if host == 'login.constantcontact.com':
                    print '[algo237]', numOfValues, cleanedK, featureTbl[host][k][label]
                keyScore[host][cleanedK][consts.SCORE] += \
                    (len(tbls) - 1) / float(numOfValues * numOfValues * len(featureTbl[host][k]))
                keyScore[host][cleanedK][consts.LABEL].add(label)

        return keyScore

    @staticmethod
    def _generate_keys(keyScore, keyApp):
        """
        Find interesting ( secdomain, key ) pairs
        Output
        :return generalRules :
            Rule = ( secdomain, key, score, labelNum ) defined in consts/consts.py
            {secdomain : [Rule, Rule, Rule, ... ]}
        """
        Rule = consts.Rule
        generalRules = defaultdict(list)
        for host in keyScore:
            if host == 'login.constantcontact.com':
                print '[algo261]', keyScore[host]
            for key in keyScore[host]:
                labelNum = len(keyApp[key])
                score = keyScore[host][key][consts.SCORE]
                generalRules[host].append(Rule(host, key, score, labelNum))
            generalRules[host] = sorted(generalRules[host], key=lambda rule: rule.score, reverse=True)
        print '[algo267]', generalRules['login.constantcontact.com']
        return generalRules

    def _generate_rules(self, trainData, generalRules, valueLabelCounter, ruleType):
        """
        Generate specific rules
        Input
        :param trainData : { tbl : [ packet, packet, packet, ... ] }
        :param generalRules :
            Generated in _generate_keys()
            {secdomain : [Rule, Rule, Rule, ... ]}
        :param valueLabelCounter : Relationships between value and labels

        Output
        :return specificRules : specific rules for apps
            { host : { key : { value : { label : { rule.score, support : { tbl, tbl, tbl } } } } } }
        """
        specificRules = defaultdict(lambda: defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: {consts.SCORE: 0, consts.SUPPORT: set()}))))

        for tbl, pkg in DataSetIter.iter_pkg(trainData):
            for host, key, value in self.miner.get_f(pkg):
                for rule in [r for r in generalRules[host] if r.key == key]:
                    value = value.strip()
                    if len(valueLabelCounter[value]) == 1 and len(value) != 1:
                        label = pkg.app if ruleType == consts.APP_RULE else pkg.category
                        specificRules[host][key][value][label][consts.SCORE] = rule.score
                        specificRules[host][key][value][label][consts.SUPPORT].add(tbl)

        return specificRules

    @staticmethod
    def _merge_result(appSpecificRules, categorySpecificRules):
        def __create_dic():
            return defaultdict(lambda: defaultdict(
                lambda: defaultdict(lambda: defaultdict(lambda: {consts.SCORE: 0, consts.SUPPORT: set()}))))

        specificRules = {consts.APP_RULE: __create_dic(), consts.CATEGORY_RULE: __create_dic()}
        for host, key, value, app, scoreType, score in flatten(appSpecificRules):
            specificRules[consts.APP_RULE][host][key][value][app][scoreType] = score
        for host, key, value, app, scoreType, score in flatten(categorySpecificRules):
            specificRules[consts.CATEGORY_RULE][host][key][value][app][scoreType] = score
            # specificRules[consts.COMPANY_RULE][host][key][value][self.appCompanyRelation[app]][scoreType] = score
        # for host in companySpecificRules:
        #   for key in companySpecificRules[host]:
        #     for value in companySpecificRules[host][key]:
        #       for company, scores in companySpecificRules[host][key][value].iteritems():
        #         if len(specificRules[consts.COMPANY_RULE][host][key][value]) == 0:
        #           specificRules[consts.COMPANY_RULE][host][key][value][company] = scores
        #           specificRules[consts.APP_RULE][host][key][value][';'.join(self.companyAppRelation[company])] = scores
        return specificRules

    def _infer_from_xml(self, specificRules, xmlGenRules, rmApps):
        print 'Start Infering'
        xmlFieldValues = defaultdict(lambda: defaultdict(set))
        for app in self.xmlFeatures:
            for k, v in self.xmlFeatures[app]:
                if len(v) != 0 and if_version(v) == False:
                    xmlFieldValues[app][k].add(v)
        interestedXmlRules = defaultdict(set)
        for rule in xmlGenRules:
            host, key = rule
            if len(specificRules[host][key]) != 0:
                for _, fieldName, _ in flatten(xmlGenRules[rule]):
                    interestedXmlRules[fieldName].add((host, key, len(specificRules[host][key])))

        for fieldName, rules in interestedXmlRules.items():
            for app in rmApps:
                if len(xmlFieldValues[app][fieldName]) == 1:
                    for value in xmlFieldValues[app][fieldName]:
                        rules = sorted(rules, key=lambda x: x[2], reverse=True)[:3]
                        for rule in rules:
                            host, key, score = rule
                            specificRules[host][key][value][app][consts.SCORE] = 1.0
                            specificRules[host][key][value][app][consts.SUPPORT] = {1, 2, 3, 4}
        return specificRules

    def train(self, trainData, rule_type):
        """
        Sample Training Data
        :param rule_type:
        :param trainData:
        """
        self.miner.mine_host(trainData, rule_type)
        trackIds = {}
        keyApp = defaultdict(set)
        for tbl, pkg in DataSetIter.iter_pkg(trainData):
            for host, k, v in self.miner.get_f(pkg):
                keyApp[k].add(pkg.app)
                self.compressedDB[consts.APP_RULE][host][k][pkg.app][v].add(tbl)
                self.compressedDB[consts.CATEGORY_RULE][host][k][pkg.category][v].add(tbl)
                self.valueLabelCounter[consts.APP_RULE][v].add(pkg.app)
                self.valueLabelCounter[consts.CATEGORY_RULE][v].add(pkg.category)
                trackIds[pkg.trackId] = pkg.app

        xmlGenRules, xmlSpecificRules = self.miner.txt_analysis(self.valueLabelCounter, trainData)
        ##################
        # Count
        ##################
        appKeyScore = self._score(self.compressedDB[consts.APP_RULE], self.valueLabelCounter[consts.APP_RULE])
        categoryKeyScore = self._score(self.compressedDB[consts.CATEGORY_RULE],
                                      self.valueLabelCounter[consts.CATEGORY_RULE])
        #############################
        # Generate interesting keys
        #############################
        appGeneralRules = self._generate_keys(appKeyScore, keyApp)
        categoryGeneralRules = self._generate_keys(categoryKeyScore, keyApp)
        #############################
        # Pruning general rules
        #############################
        print ">>>[KV] Before pruning appGeneralRules", len(appGeneralRules)
        appGeneralRules = self._prune_general_rules(appGeneralRules, trainData, xmlGenRules)
        categoryGeneralRules = self._prune_general_rules(categoryGeneralRules, trainData, xmlGenRules)
        print ">>>[KV] appGeneralRules", len(appGeneralRules)
        print ">>>[KV] companyGeneralRules", len(categoryGeneralRules)
        #############################
        # Generate specific rules
        #############################
        appSpecificRules = self._generate_rules(trainData, appGeneralRules, self.valueLabelCounter[consts.APP_RULE],
                                                consts.APP_RULE)
        categorySpecifcRules = self._generate_rules(trainData, categoryGeneralRules, self.valueLabelCounter[consts.CATEGORY_RULE],
                                                consts.CATEGORY_RULE)

        # appSpecificRules = self._infer_from_xml(appSpecificRules, xmlGenRules, trainData.rmapp)
        appSpecificRules = self.miner.gen_txt_rule(xmlSpecificRules, appSpecificRules, trackIds)
        specificRules = self._merge_result(appSpecificRules, categorySpecifcRules)
        #############################
        # Persist rules
        #############################
        self.persist(specificRules, rule_type)
        return self

    @staticmethod
    def _clean_db(rule_type):
        print '>>> [KVRULES]', consts.SQL_DELETE_KV_RULES % rule_type
        sqldao = SqlDao()
        sqldao.execute(consts.SQL_DELETE_KV_RULES % rule_type)
        sqldao.commit()
        sqldao.close()

    def load_rules(self):
        sqldao = SqlDao()

        QUERY = consts.SQL_SELECT_KV_RULES
        counter = 0
        for key, value, host, label, confidence, rule_type, support in sqldao.execute(QUERY):
            if len(value.split('\n')) == 1 and ';' not in label:
                if rule_type == consts.APP_RULE:
                    counter += 1
                try:
                    value = urllib.quote(value)
                except:
                    pass

                if PATH not in key:
                    regexObj = re.compile(r'\b' + re.escape(key + '=' + value) + r'\b', re.IGNORECASE)
                else:
                    value = value.replace(PATH, '')
                    regexObj = re.compile(r'\b' + re.escape(value) + r'\b', re.IGNORECASE)

                self.rules[rule_type][host][regexObj][consts.SCORE] = confidence
                self.rules[rule_type][host][regexObj][consts.SUPPORT] = support
                self.rules[rule_type][host][regexObj][consts.LABEL] = label
        print '>>> [KV Rules#Load Rules] total number of rules is', counter
        sqldao.close()

    def c(self, pkg):
        predictRst = {}
        for ruleType in self.rules:
            fatherScore = -1
            rst = consts.NULLPrediction
            host, path = self.miner.classify_format(pkg)
            for regexObj, scores in self.rules[ruleType][host].iteritems():
                if regexObj.search(path):
                    label, support, confidence = scores[consts.LABEL], scores[consts.SUPPORT], scores[consts.SCORE]
                    if support > rst.score or (support == rst.score and confidence > fatherScore):
                        fatherScore = confidence
                        evidence = (host, regexObj.pattern)
                        rst = consts.Prediction(label, support, evidence)
            predictRst[ruleType] = rst
            if rst != consts.NULLPrediction and rst.label != get_label(pkg, ruleType):
                print '[WRONG]', rst, pkg.app, pkg.category, ruleType
                print '=' * 10

        return predictRst

    def persist(self, specificRules, rule_type):
        """
        :param rule_type:
        :param specificRules: specific rules for apps
            ruleType -> host -> key -> value -> label -> { rule.score, support : { tbl, tbl, tbl } }
        """
        # self._clean_db(rule_type)
        QUERY = consts.SQL_INSERT_KV_RULES
        sqldao = SqlDao()
        # Param rules
        params = []
        for ruleType, patterns in specificRules.iteritems():
            for host in patterns:
                for key in patterns[host]:
                    for value in patterns[host][key]:
                        for label in patterns[host][key][value]:
                            confidence = patterns[host][key][value][label][consts.SCORE]
                            support = len(patterns[host][key][value][label][consts.SUPPORT])
                            params.append((label, support, confidence, host, key, value, ruleType))
        sqldao.executeBatch(QUERY, params)
        sqldao.close()
        print ">>> [KVRules] Total Number of Rules is %s Rule type is %s" % (len(params), rule_type)
