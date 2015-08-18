from sklearn.cross_validation import KFold
import datetime
from sqldao import SqlDao
from fp import CMAR
from utils import load_pkgs, load_appinfo
from algo import KVClassifier
from classifier import HeaderClassifier
from host import HostApp
from collections import namedtuple, defaultdict
import consts
import sys
import argparse
from host import HostApp
from rule_manager import RuleManager


LIMIT = None
FOLD = 1
DEBUG = False
DEBUG_CMAR = False

validLabel = {consts.APP_RULE, consts.COMPANY_RULE, consts.CATEGORY_RULE}

def load_trian(size):
    train_set = {int(item.strip()) for item in open('train_id')}
    test_set = {i for i in range(size) if i not in train_set}
    return train_set, test_set

def merge_rst(rst, tmprst):
    for pkg_id, predictions in tmprst.iteritems():
      if pkg_id not in rst:
        rst[pkg_id] = predictions
      else:
        for rule_type in validLabel:
          if rst[pkg_id][rule_type][0] == None:
            rst[pkg_id][rule_type] = tmprst[pkg_id][rule_type]
    return rst


def evaluate(rst, test_set):
    # app_rst, record_id
    correct, wrong, total = 0, 0, 0
    correct_app = set()
    for pkg_id, predictions in rst.items():
      predict_app = predictions[consts.APP_RULE][0] 
      predict_company = predictions[consts.COMPANY_RULE][0] 
      predict_category = predictions[consts.CATEGORY_RULE][0] 
      if predict_app == test_set[pkg_id].app:
          correct += 1
          correct_app.add(test_set[pkg_id].app)
      elif predict_app == None and predict_company == test_set[pkg_id].company:
          correct += 1
          correct_app.add(test_set[pkg_id].app)
      elif predict_app == None and predict_company == None and predict_category == test_set[pkg_id].category:
          correct += 1
          correct_app.add(test_set[pkg_id].app)
      else:
          wrong += 1
      if sum([1 for value in predictions.values() if value[0] != None]) > 0:
        total += 1
      
    print 'Total:', len(test_set), 'Recognized:', total, 'Correct:', correct, 'Wrong:', wrong
    return correct, correct_app



def use_classifier(classifier, test_set):
    rst = defaultdict(dict)
    total = 0
    recall = 0
    for pkg_id, record in test_set.items():
        if len(record.queries) > 0:
          total += 1
        # predict
        labelDists = classifier.classify(record)
        max_confidence = -1
        for labelType, prediction in labelDists.iteritems():
          if labelType in validLabel:
              recall += 1
              rst[pkg_id][labelType] = prediction
    
    return rst


def insert_rst(rst, DB = 'packages'):
    QUERY = 'UPDATE ' + DB + ' SET classified = %s WHERE id = %s'
    print QUERY
    sqldao = SqlDao()
    params = []
    for k, v in rst.items():
      for rule_type in validLabel:
        if v[rule_type][0]:
          params.append((3,k));
          break
    sqldao.executeBatch(QUERY,  params)
    sqldao.close()
    print 'insert', len(rst),"items"



def execute(train_set, test_set, inforTrack):
    sqldao = SqlDao()
    sqldao.execute('DELETE FROM patterns')
    sqldao.close()
    print 'DELETE PREVIOUS RULES'

    print "Train:", train_set.keys(), "Test:", len(test_set)
    correct = 0
    test_apps = set()
    rst = {}
    for record in test_set.values():
        test_apps.add(record.app)

    classifiers = [
             ("Header Rule", HeaderClassifier()),
             ("Host Rule", HostApp()),
             ("CMAR Rule", CMAR(min_cover = 3)),
             ("KV Rule", KVClassifier())
            ]

    
    
    ruleDict = {}
    for rule_type in validLabel:
        for tbl in train_set:
            for pkg in train_set[tbl]:
                if rule_type == consts.APP_RULE:
                    pkg.set_label(pkg.app)
                elif rule_type == consts.COMPANY_RULE:
                    pkg.set_label(pkg.company)
                elif rule_type == consts.CATEGORY_RULE:
                    pkg.set_label(pkg.category)

        for name, classifier in classifiers:
            print ">>> [train#%s] " % (name)
            classifier =  classifier.train(train_set, rule_type)
    train_set = None # To release memory
    

    # ruleManager = RuleManager()
    print '>>> Finish training all classifiers'
    print '>>> Start rule pruning'
    
    # if 'CMAR Rule' in classifiers:
    #     classifiers["CMAR Rule"].rules = ruleManager.pruneCMARRules(ruleDict['CMAR Rule'], ruleDict['Host Rule'])
    #     classifiers["CMAR Rule"].persist()
    # if 'KV Rule' in classifiers:
    #     classifiers["KV Rule"].rules = ruleManager.pruneKVRules(ruleDict['KV Rule'],{1:[],2:[]})
    #     #classifierDict["KV Rule"].rules = ruleManager.pruneKVRules(ruleDict['KV Rule'],ruleDict['Host Rule'] )
    #     #classifierDict["KV Rule"].persist()
    
    for name, classifier in classifiers:
        print ">>> [test#%s] " % (name)
        classifier.load_rules()
        tmprst = use_classifier(classifier, test_set)
        rst = merge_rst(rst, tmprst)
        recall = sum([1 for i in rst.values() if i[consts.APP_RULE][0] or i[consts.COMPANY_RULE][0] or i[consts.CATEGORY_RULE][0]])
        print ">>> Recognized:", recall


    c, correct_app = evaluate(rst, test_set)
    correct += c
    not_cover_app = test_apps - correct_app
    recall = sum([1 for i in rst.values() if i[consts.APP_RULE][0] or i[consts.COMPANY_RULE][0] or i[consts.CATEGORY_RULE][0]])
    print "Discoered App Number:", len(correct_app), "Total Number of App", len(test_apps)
    inforTrack['discoveried_app'] += len(correct_app) * 1.0 / len(test_apps)
    inforTrack['precision'] += correct * 1.0 / recall
    inforTrack['recall'] += recall * 1.0 / len(test_set) * 1.0
    return rst

def loadExpApp():
    expApp=set()
    for app in open("resource/exp_app.txt"):
        expApp.add(app.strip().lower())
    return expApp


def cross_batch_test(train_tbls, test_tbl, app_type):
    expApp = load_exp_app()
    records = {}
    for tbl in train_tbls:
       records[tbl] = load_pkgs(LIMIT, filterFunc = lambda x: x.app in expApp[app_type] , DB = tbl)
    
    apps = set()  
    for pkgs in records.values():
        for pkg in pkgs:
            apps.add(pkg.app)
    print "len of app", len(apps), "len of train set", len(records)

    precision = 0
    recall = 0
    discoveried_app = 0

    set_pair = []
    test_set = {record.id:record for record in load_pkgs(LIMIT, filterFunc = lambda x: x.app in expApp[app_type] , DB = test_tbl)}
    set_pair.append((records, test_set))

    apps = set()
    for k,v in test_set.iteritems():
        apps.add(v.app)
    print "len of apps", len(apps), "len of test set", len(test_set)

    inforTrack = { 'discoveried_app':0.0, 'precision':0.0, 'recall':0.0}

    for train_set, test_set in set_pair:
        correct = 0
        rst = execute(train_set, test_set, inforTrack)
        print "INSERTING"
        insert_rst(rst, test_tbl)

    precision = inforTrack['precision']
    recall = inforTrack['recall']
    app_coverage = inforTrack['discoveried_app']
    f1_score = 2.0 * precision * recall / (precision + recall)
    print 'Precision:', precision, 'Recall:', recall, 'App:', app_coverage, 'F1 Score:', f1_score
    return 'Precision %s, Recall: %s, App: %s, F1 Score: %s' % (precision, recall, app_coverage, f1_score)
######### START ###########

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('-t', metavar='cross/single', help='test type')
    parser.add_argument('-train', metavar='tablename', nargs='+', help='train set')
    parser.add_argument('-test', metavar='tablename', help='test set')
    parser.add_argument('-apptype', metavar='apptype', help='test apptype')
    args = parser.parse_args()

    test_tbl = None
    if args.t == 'cross':
      if args.apptype.lower() == 'ios':
        app_type = consts.IOS
      elif args.apptype.lower() == 'android':
        app_type = consts.ANDROID
      cross_batch_test(args.train, args.test, args.apptype, app_type)
