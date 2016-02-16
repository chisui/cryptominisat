#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
import sqlite3
import optparse
import operator
import numpy
import time
import functools
import glob
import os
import add_lemma_ind as myquery

from sklearn.preprocessing import StandardScaler
from sklearn.cross_validation import train_test_split
import sklearn.tree
from sklearn.externals.six import StringIO
import pydot
from IPython.display import Image


def mypow(to, base):
    return base**to


class Query2 (myquery.Query):
    def get_max_clauseID(self):
        q = """
        SELECT max(clauseID)
        FROM clauseStats
        WHERE runID = %d
        """ % self.runID

        max_clID = None
        for row in self.c.execute(q):
            max_clID = int(row[0])

        return max_clID

    def get_restarts(self):
        q = """
        select
            restart.restarts,
            numgood.cnt,
            restart.clauseIDendExclusive-restart.clauseIDstartInclusive as total
        from
            restart,
            (SELECT clauseStats.restarts as restarts, count(clauseStats.clauseID) as cnt
            FROM ClauseStats, goodClauses
            WHERE clauseStats.clauseID = goodClauses.clauseID
            and clauseStats.runID = goodClauses.runID
            and clauseStats.runID = {0}
            group by clauseStats.restarts) as numgood
        where
            restart.runID = {0}
            and restart.restarts = numgood.restarts
        """.format(self.runID)

        for row in self.c.execute(q):
            r = list(row)
            rest = r[0]
            good = r[1]
            total = r[2]
            print("rest num %-6d  conflicts %-6d good %-3.2f%%" %
                  (rest, total, float(good)/total*100.0))

    def get_all(self):
        ret = []

        q = """
        SELECT clauseStats.*
        FROM clauseStats, goodClauses
        WHERE clauseStats.clauseID = goodClauses.clauseID
        and clauseStats.runID = goodClauses.runID
        and clauseStats.runID = {0}
        order by RANDOM()
        """.format(self.runID)
        for row, _ in zip(self.c.execute(q), xrange(options.limit)):
            #first 5 are not useful, such as restarts and clauseID
            r = self.transform_row(row)
            ret.append([r, 1])

        bads = []
        q = """
        SELECT clauseStats.*
        FROM clauseStats left join goodClauses
        on clauseStats.clauseID = goodClauses.clauseID
        and clauseStats.runID = goodClauses.runID
        where goodClauses.clauseID is NULL
        and goodClauses.runID is NULL
        and clauseStats.runID = {0}
        order by RANDOM()
        """.format(self.runID)
        for row, _ in zip(self.c.execute(q), xrange(options.limit)):
            #first 5 are not useful, such as restarts and clauseID
            r = self.transform_row(row)
            ret.append([r, 0])

        numpy.random.shuffle(ret)
        X = [x[0] for x in ret]
        y = [x[1] for x in ret]
        return X, y

    def transform_row(self, row):
        row = list(row[5:])
        row[1] = row[1]/row[4]
        row[4] = 0
        row[5] = 0

        return row


def get_one_file(dbfname):
    print("Using sqlite3db file %s" % dbfname)
    col_names = None

    with Query2(dbfname) as q:
        col_names = q.col_names
        X, y = q.get_all()
        assert len(X) == len(y)

    return X, y, col_names


class Classify:
    def predict(self, X, y):
        print("number of features:", len(X[0]))
        print("total samples: %5d   percentage of good ones %-3.2f" %
              (len(X), sum(y)/float(len(X))*100.0))
        X = StandardScaler().fit_transform(X)

        print("Training....")
        t = time.time()
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

        #clf = KNeighborsClassifier(5)
        self.clf = sklearn.tree.DecisionTreeClassifier(
            max_depth=options.max_depth)
        self.clf.fit(X_train, y_train)
        print("Training finished. T: %-3.2f" % (time.time()-t))

        print("Calculating score....")
        t = time.time()
        score = self.clf.score(X_test, y_test)
        print("score: %s T: %-3.2f" % (score, (time.time()-t)))

    def output_to_pdf(self, col_names):
        dot_data = StringIO()
        sklearn.tree.export_graphviz(self.clf, out_file=dot_data,
                                     feature_names=col_names,
                                     class_names=["BAD", "GOOD"],
                                     filled=True, rounded=True,
                                     special_characters=True,
                                     proportion=True
                                     )
        graph = pydot.graph_from_dot_data(dot_data.getvalue())
        #Image(graph.create_png())

        outf = "tree.pdf"
        graph.write_pdf(outf)
        print("Wrote final tree to %s" % outf)


if __name__ == "__main__":

    usage = "usage: %prog [options] dir1 [dir2...]"
    parser = optparse.OptionParser(usage=usage)

    parser.add_option("--verbose", "-v", action="store_true", default=False,
                      dest="verbose", help="Print more output")

    parser.add_option("--limit", "-l", default=10**9, type=int,
                      dest="limit", help="Max number of good/bad clauses")

    parser.add_option("--depth", default=6, type=int,
                      dest="max_depth", help="Max depth")

    (options, args) = parser.parse_args()

    if len(args) < 1:
        print("ERROR: You must give at least one directory")
        exit(-1)

    X = []
    y = []
    col_names = None
    for dbfname in args:
        print("----- INTERMEDIATE predictor -------\n")
        a, b, col_names = get_one_file(dbfname)
        X.extend(a)
        y.extend(b)
        clf = Classify()
        clf.predict(a, b)

    print("----- FINAL predictor -------\n")
    clf = Classify()
    clf.predict(X, y)
    print("Columns used were:")
    for i, name in zip(xrange(100), col_names):
        print("%-3d  %s" % (i, name))

    clf.output_to_pdf(col_names)






