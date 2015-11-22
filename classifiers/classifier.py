from abc import ABCMeta, abstractmethod
from sqldao import SqlDao
import const.consts as consts
from const.dataset import DataSetIter as DataSetIter

class AbsClassifer:
    __metaclass__ = ABCMeta

    def classify(self, testSet):
        batchPredicts = {}
        for tbl, pkg in DataSetIter.iter_pkg(testSet):
            predictRst = self.__classify(pkg)
            batchPredicts[pkg.id] = predictRst

        for tbl, pkg in DataSetIter.iter_pkg(testSet):
            predict = batchPredicts[pkg.id][consts.APP_RULE]
            if predict.label  and predict.label != pkg.app:
                print predict.evidence, predict.label, pkg.app
                print '=' * 10
        return batchPredicts
  
    @abstractmethod
    def train(self, train_set, rule_type): pass

    @abstractmethod
    def load_rules(self): pass

    def __classify(self, pkg): pass

    def set_name(self, name):
      self.name = name

    def clean_db(self, ruleType, QUERY):
        print ">>> [%s Classifier]" % (self.name), QUERY
        sqldao = SqlDao()
        sqldao.execute(QUERY % (ruleType))
        sqldao.close()

