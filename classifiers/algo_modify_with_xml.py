import const.consts as consts
import re
from sqldao import SqlDao
from utils import load_exp_app, load_xml_features, if_version, flatten
from collections import defaultdict
from classifier import AbsClassifer
import collections


DEBUG = False

class KVClassifier(AbsClassifer):
  def __init__(self, appType):
    self.name = consts.KV_CLASSIFIER
    self.featureAppTbl = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(set))))
    self.featureCompanyTbl = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(set))))
    self.valueAppCounter = defaultdict(set)
    self.valueCompanyCounter = defaultdict(set)
    self.appCompanyRelation = {}
    self.companyAppRelation = defaultdict(set)
    self.rules = {}
    self.appType = appType
    self.xmlFeatures = load_xml_features()


  def _prune_general_rules(self, generalRules, trainData, highConfRules):
    '''
    PK by coverage
    Input
    - generalRules : {secdomain : [(secdomain, key, score, labelNum), rule, rule]}
    - trainData : { tbl : [ packet, packet, ... ] }
    - highConfRules : {( host, key) }
    '''
    ruleCoverage = defaultdict(lambda : defaultdict(set))
    ruleScores = {}
    ruleLabelNum = {}
    for tbl, pkg, key, value in self.iterate_traindata(trainData):
      for rule in [r for r in generalRules[pkg.host] if r.key == key]:
        ruleCoverage[pkg.host][rule.key].add(tbl + '#' + str(pkg.id))
        ruleScores[ (pkg.host, rule.key) ] = rule.score
        ruleLabelNum[ (pkg.host, rule.key) ] = rule.labelNum

    # for tbl, pkgs in trainData.iteritems():
    #   for pkg in filter(lambda pkg : pkg.secdomain in generalRules, pkgs):
    #     for rule in filter(lambda rule : rule.key in pkg.queries, generalRules[pkg.secdomain]):
    #       for value in pkg.queries[rule.key]:
    #         value = value.strip()

    PKG_IDS= 1
    prunedGenRules = defaultdict(list)
    for host, keyNcoveredIds in ruleCoverage.iteritems():
      keyNcoveredIds = sorted(keyNcoveredIds.items(), key=lambda keyNid : len(keyNid[PKG_IDS]))
      for i in range(len(keyNcoveredIds)):
        ifKeepRule = (True, None)
        iKey, iCoveredIds = keyNcoveredIds[i]
        ''' Prune by coverage '''
        for j in range(i + 1, len(keyNcoveredIds)):
          jKey, jCoveredIds = keyNcoveredIds[j]
          if ruleScores[ (host, iKey) ] < ruleScores[ (host, jKey) ]:
            if iCoveredIds.issubset(jCoveredIds) and (host, iKey) not in highConfRules:
              ifKeepRule = (False, jKey, '1')
        ''' Prune by assuming host should has only one identifier '''
        for jKey, _ in keyNcoveredIds:
          if (host, jKey) in highConfRules and (host, iKey) not in highConfRules:
            ifKeepRule = (False, jKey, '2')

        if ifKeepRule[0]:
          rule = consts.Rule(host, iKey, ruleScores[ (host, iKey) ],  ruleLabelNum[ (host, iKey) ])
          prunedGenRules[host].append(rule)
          # print 'Keep', host, ruleI[0], ruleScores[ (host, ruleI[0]) ]
        else:
          print 'Pruned'
          print host, iKey, ruleScores[(host, iKey)], 'pruned by:', ifKeepRule
          print '-' * 10

      # print '='*10
    return prunedGenRules


  def _count(self, featureTbl, valueLabelCounter):
    '''
    Give score to very ( secdomain, key ) pairs
    Input
    - featureTbl :
        Relationships between host, key, value and label(app or company) from training data
        { secdomain : { key : { label : {value} } } }
    - valueLabelCounter :
        Relationships between labels(app or company)
        { app : {label} }
    '''
    # secdomain -> app -> key -> value -> tbls
    # secdomain -> key -> (label, score)
    keyScore = defaultdict(lambda : defaultdict(lambda : {consts.LABEL:set(), consts.SCORE:0 }))
    for secdomain, k, label, v, tbls in flatten(featureTbl):
      cleanedK = k.replace("\t", "")
      if len(valueLabelCounter[v]) == 1 and if_version(v) == False:
        keyScore[secdomain][cleanedK][consts.SCORE] += \
            (len(tbls) - 1) / float(len(featureTbl[secdomain][k][label]) * len(featureTbl[secdomain][k]))
        keyScore[secdomain][cleanedK][consts.LABEL].add(label)

    # for secdomain in featureTbl:
    #   for k in featureTbl[secdomain]:
    #     cleanedK = k.replace("\t", "")
    #     for label in featureTbl[secdomain][k]:
    #       for v, tbls in featureTbl[secdomain][k][label].iteritems():
    #         if len(valueLabelCounter[v]) == 1 and if_version(v) == False:
    #           keyScore[secdomain][cleanedK][consts.SCORE] += \
    #               (len(tbls) - 1) / float(len(featureTbl[secdomain][k][label]) * len(featureTbl[secdomain][k]))
    #           keyScore[secdomain][cleanedK][consts.LABEL].add(label)
    return keyScore

  def _check_high_confrule(self, valueApps):
    ifValid = True
    for value, apps in valueApps.items():
      if len(apps) > 1:
        ifValid = False
    return ifValid

  def _generate_keys(self, keyScore, highConfRules):
    '''
    Find interesting ( secdomain, key ) pairs
    Input
    - keyScore : scores for ( secdomain, key ) pairs
    Output
    - generalRules :
        Rule = ( secdomain, key, score, labelNum ) defined in consts/consts.py
        {secdomain : [Rule, Rule, Rule, ... ]}
    '''
    Rule = consts.Rule
    generalRules = defaultdict(list)
    for secdomain in keyScore:
      for key in keyScore[secdomain]:
        labelNum = len(keyScore[secdomain][key][consts.LABEL])
        score = keyScore[secdomain][key][consts.SCORE]
        if key == 'utme':
          print 'score is', score
        if labelNum == 1 or score <= 0.5:
          if (secdomain, key) in highConfRules:
            print '[LOST]', (secdomain, key), labelNum, score, highConfRules[(secdomain, key)]
          continue
        generalRules[secdomain].append(Rule(secdomain, key, score, labelNum))
    for secdomain in generalRules:
      generalRules[secdomain] = sorted(generalRules[secdomain], key=lambda rule: rule.score, reverse = True)
    return generalRules

  def _generate_rules(self, trainData, generalRules, valueLabelCounter, ruleType):
    '''
    Generate specific rules
    Input
    - trainData : { tbl : [ packet, packet, packet, ... ] }
    - generalRules :
        Generated in _generate_keys()
        {secdomain : [Rule, Rule, Rule, ... ]}
    - valueLabelCounter : Relationships between value and labels
    Output
    - specificRules : specific rules for apps
        { host : { key : { value : { label : { rule.score, support : { tbl, tbl, tbl } } } } } }
    '''
    specificRules = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(lambda : {consts.SCORE:0,consts.SUPPORT:set()}))))
    
    for tbl, pkg, key, value in self.iterate_traindata(trainData):
      for rule in [r for r in generalRules[pkg.host] if r.key == key]:
        value = value.strip()
        if len(valueLabelCounter[value]) == 1 and len(value) != 1:
          label = pkg.app if ruleType == consts.APP_RULE else pkg.company
          specificRules[pkg.host][key][value][label][consts.SCORE] = rule.score
          specificRules[pkg.host][key][value][label][consts.SUPPORT].add(tbl)

    # for tbl, pkgs in trainData.iteritems():
    #   for pkg in filter(lambda pkg : pkg.host in generalRules, pkgs):
    #     for rule in filter(lambda rule : rule.key in pkg.queries, generalRules[pkg.host]):
    #       for value in pkg.queries[rule.key]:
    #         value = value.strip()
    #         if len(valueLabelCounter[value]) == 1 and len(value) != 1:
    #           if ruleType == consts.APP_RULE:
    #             label = pkg.app
    #           else:
    #             label = pkg.company
    #           specificRules[pkg.host][rule.key][value][label][consts.SCORE] = rule.score
    #           specificRules[pkg.host][rule.key][value][label][consts.SUPPORT].add(tbl)
    return specificRules

  def _merge_result(self, appSpecificRules, companySpecificRules):
    specificRules = {}
    specificRules[consts.APP_RULE] = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(lambda : {consts.SCORE:0,consts.SUPPORT:set()}))))
    specificRules[consts.COMPANY_RULE] = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(lambda : {consts.SCORE:0,consts.SUPPORT:set()}))))
    for host, key, value, app, scoreType, score in flatten(appSpecificRules):
      specificRules[consts.APP_RULE][host][key][value][app][scoreType] = score
      specificRules[consts.COMPANY_RULE][host][key][value][self.appCompanyRelation[app]][scoreType] = score

    # for host in appSpecificRules:
    #   for key in appSpecificRules[host]:
    #     for value in appSpecificRules[host][key]:
    #       for app, scores in appSpecificRules[host][key][value].iteritems():
    #         specificRules[consts.APP_RULE][host][key][value][app] = scores
    #         specificRules[consts.COMPANY_RULE][host][key][value][self.appCompanyRelation[app]] = scores
    # for host in companySpecificRules:
    #   for key in companySpecificRules[host]:
    #     for value in companySpecificRules[host][key]:
    #       for company, scores in companySpecificRules[host][key][value].iteritems():
    #         if len(specificRules[consts.COMPANY_RULE][host][key][value]) == 0:
    #           specificRules[consts.COMPANY_RULE][host][key][value][company] = scores
    #           specificRules[consts.APP_RULE][host][key][value][';'.join(self.companyAppRelation[company])] = scores
    return specificRules

  def _compare(self, trainData, specificRules):
    tmpRules = set()
    for tbl, pkg, k, v in self.iterate_traindata(trainData):
      if v in self.xmlFeatures[pkg.app] and len(v) > 2:
        tmpRules.add((pkg.host, k, v, pkg.app))

    # for tbl in trainData.keys():
    #   for pkg in trainData[tbl]:
    #     for k,vs in pkg.queries.items():
    #       for v in vs:
    #         if v in self.xmlFeatures[pkg.app] and len(v) > 2:
    #           tmpRules.add((pkg.host, k, v, pkg.app))
    for host, key, value, app in tmpRules:
      if app not in specificRules[consts.APP_RULE][host][key][value]:
        print host, key, value, app

  def iterate_traindata(self, trainData):
    for tbl in trainData.keys():
      for pkg in trainData[tbl]:
        for k,vs in pkg.queries.items():
          for v in vs:
            yield (tbl, pkg, k, v)


  def _gen_high_confrules(self, trainData):
    highConfRules = defaultdict(lambda : defaultdict(set))
    for tbl, pkg, k, v in self.iterate_traindata(trainData):
      if v in self.xmlFeatures[pkg.app] and if_version(v) == False:
        highConfRules[(pkg.host, k)][v].add(pkg.app)
        highConfRules[(pkg.secdomain, k)][v].add(pkg.app)
    return highConfRules

  def train(self, trainData, rule_type):
    highConfRules = set()
    for tbl, pkg, k, v in self.iterate_traindata(trainData):
      self.featureAppTbl[pkg.secdomain][k][pkg.label][v].add(tbl)
      self.featureCompanyTbl[pkg.secdomain][k][pkg.company][v].add(tbl)
      self.valueAppCounter[v].add(pkg.label)
      self.valueCompanyCounter[v].add(pkg.company)
      self.appCompanyRelation[pkg.app] = pkg.company
      self.companyAppRelation[pkg.company].add(pkg.app)

    highConfRules = self._gen_high_confrules(trainData)
    ##################
    # Count
    ##################
    appKeyScore = self._count(self.featureAppTbl, self.valueAppCounter)
    companyKeyScore = self._count(self.featureCompanyTbl, self.valueCompanyCounter)
    #############################
    # Generate interesting keys
    #############################
    appGeneralRules = self._generate_keys(appKeyScore, highConfRules)
    companyGeneralRules = self._generate_keys(companyKeyScore, highConfRules)
    #############################
    # Pruning general rules
    #############################
    appGeneralRules = self._prune_general_rules(appGeneralRules, trainData, highConfRules)
    companyGeneralRules = self._prune_general_rules(companyGeneralRules, trainData, highConfRules)
    print ">>>[KV] appGeneralRules", len(appGeneralRules)
    print ">>>[KV] companyGeneralRules", len(companyGeneralRules)
    #############################
    # Generate specific rules
    #############################
    appSpecificRules = self._generate_rules(trainData, appGeneralRules, self.valueAppCounter, consts.APP_RULE)
    companySpecificRules = self._generate_rules(trainData, companyGeneralRules, self.valueCompanyCounter, consts.COMPANY_RULE)
    specificRules = self._merge_result(appSpecificRules, companySpecificRules)
    #############################
    # Persist rules
    #############################
    self.persist(specificRules, rule_type)
    self._compare(trainData, specificRules)
    self.__init__(self.appType)
    return self

  def _clean_db(self, rule_type):
    print '>>> [KVRULES]', consts.SQL_DELETE_KV_RULES % rule_type
    sqldao = SqlDao()
    sqldao.execute(consts.SQL_DELETE_KV_RULES % rule_type)
    sqldao.commit()
    sqldao.close()

  def load_rules(self):
    self.rules = {}
    sqldao = SqlDao()
    self.rules[consts.APP_RULE] = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(lambda : {'score':0, 'support':0, 'regexObj': None}))))
    self.rules[consts.COMPANY_RULE] = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(lambda : {'score':0, 'support':0, 'regexObj': None}))))
    self.rules[consts.CATEGORY_RULE] = defaultdict(lambda : defaultdict( lambda : defaultdict( lambda : defaultdict(lambda : {'score':0, 'support':0, 'regexObj': None}))))
    QUERY = consts.SQL_SELECT_KV_RULES
    counter = 0
    for key, value, host, label, confidence, rule_type, support in sqldao.execute(QUERY):
      if len(value.split('\n')) == 1 and ';' not in label:
        if rule_type == consts.APP_RULE:
          counter += 1
        self.rules[rule_type][host][key][value][label][consts.SCORE] = confidence
        self.rules[rule_type][host][key][value][label][consts.SUPPORT] = support
        self.rules[rule_type][host][key][value][label][consts.REGEX_OBJ] = re.compile(re.escape(key+'='+value))
    print '>>> [KV Rules#Load Rules] total number of rules is', counter
    sqldao.close()

  def classify(self, pkg):
    predictRst = {}
    for ruleType in self.rules:
      for host, queries in [(pkg.host, pkg.queries)]:
        fatherScore = -1
        rst = consts.NULLPrediction

        for k, kRules in self.rules[ruleType].get(host, {}).iteritems():
          for v in queries.get(k, []):
            for label, scoreNcount in kRules.get(v, {}).iteritems():
              score, support, regexObj = scoreNcount[consts.SCORE], scoreNcount[consts.SUPPORT], scoreNcount[consts.REGEX_OBJ]
              match = regexObj.search(pkg.host)

              if support > rst.score or (support == rst.score and score > fatherScore):
                fatherScore = score
                evidence = (k, v)
                rst = consts.Prediction(label, support, evidence)

        predictRst[ruleType] = rst

    if predictRst[consts.APP_RULE] != consts.NULLPrediction and predictRst[consts.APP_RULE].label != pkg.app:
      print predictRst[consts.APP_RULE].evidence, predictRst[consts.APP_RULE].label, pkg.app
      print '=' * 10
    return predictRst


  def persist(self, specificRules, rule_type):
    '''
    - specificRules : specific rules for apps
        {ruleType: { host : { key : { value : { label : { rule.score, support : { tbl, tbl, tbl } } } } } }}
    '''
    self._clean_db(rule_type)
    QUERY = consts.SQL_INSERT_KV_RULES
    sqldao = SqlDao()
    # Param rules
    params = []
    for ruleType, patterns in specificRules.iteritems():
      for host in patterns:
        for key in patterns[host]:
          for value in patterns[host][key]:
            max_confidence = -1
            max_support = -1
            max_label = None
            for label in patterns[host][key][value]:
              confidence = patterns[host][key][value][label][consts.SCORE]
              support = len(patterns[host][key][value][label][consts.SUPPORT])
              params.append((label, support, confidence, host, key, value, ruleType))
    sqldao.executeBatch(QUERY, params)
    sqldao.close()
    print ">>> [KVRules] Total Number of Rules is %s Rule type is %s" % (len(params), rule_type)