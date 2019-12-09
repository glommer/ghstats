#!/usr/bin/env python3

import requests
import sys
import datetime
from dateutil.parser import parse
import argparse

class User:
    cache = {}
    def __init__(self, userurl, token):
        headers = {'Authorization': 'token {}'.format(token)}
        if userurl in User.cache:
            self.info = User.cache[userurl]
        else:
            self.info = requests.get(userurl, headers=headers).json()

    def __str__(self):
        try:
            if not self.info['name']:
                return self.info['login']
            return self.info['name']
        except:
            return "None"

class ScyllaPR:
    def __init__(self, json, token):
        self.token = token
        self.created_at = parse(json['created_at']).date()
        self.url = json['html_url']

        try:
            self.closed_at = parse(json['closed_at']).date()
        except TypeError:
            self.closed_at = None
        try:
            self.merged_at = parse(json['merged_at']).date()
        except TypeError:
            self.merged_at = None

        self.title = json['title']
        self.user = User(json['user']['url'], self.token)
        self.reviewers = [ User(x['url'], self.token) for x in json['requested_reviewers'] ]

    def timeToClose(self):
        return (self.closed_at - self.created_at).days

    def openFor(self):
        return (datetime.date.today() - self.created_at).days

    def isOpen(self):
        return not self.closed_at

    def isAbandoned(self):
        return self.closed_at and not self.merged_at

    def isMerged(self):
        return self.merged_at

    def needsAttention(self, days=15):
        return self.isOpen() and datetime.date.today() - datetime.timedelta(days=days) > self.created_at

    def __str__(self):
        s = ""
        s += "\tAuthor      : {}\n".format(self.user)
        s += "\tTitle       : {}\n".format(self.title)
        s += "\tURL         : {}\n".format(self.url)
        if self.isOpen():
            s += "\tCreated  at : {} ({} days ago)\n".format(self.created_at, self.openFor())
        else:
            s += "\tCreated  at : {} and Closed at {} ({} after days)\n".format(self.created_at, self.closed_at, self.timeToClose())
        return s

def read_all(dummy):
    return True

def getGithubData(url, token, add_criteria = read_all):
    ret = []

    headers = {'Authorization': 'token {}'.format(token)}

    while True:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print("Can't contact github API", file=sys.stderr)
            sys.exit(-1)

        json = resp.json()

        ret += [ ScyllaPR(x, token) for x in json if add_criteria(x) ]

        if 'next' in resp.links:
            url = resp.links['next']['url']
        else:
            return ret


def printHistogram(closedPR, action = "merge", actor=True):
    bins = { 0 : 0,
             1 : 0,
             2 : 0,
             3 : 0,
             4 : 0,
             5 : 0,
             6 : 0,
             7 : 0,
             15 : 0,
             21 : 0,
             30 : 0,
             60 : 0,
             120 : 0
            }

    sorted_keys = sorted(bins.keys())

    data = [ x.timeToClose() for x in closedPR ]
    for x in data:
        for k in sorted_keys:
            if x <= k:
                bins[k] += 1
                break
    print("\tAverage time to {}: {:d} days".format(action, int(sum(data) / len(data))))
    print("\tPeak time to {}: {:d} days".format(action, int(max(data))))
    print("\tHistogram of {} time: in days".format(action))

    while bins[sorted_keys[-1]] == 0:
        sorted_keys.pop()

    for k in sorted_keys:
        print("\t\t{:3d}: {}".format(k, bins[k] * '@'))


def printStats(days, openPR, abandonedPR = None, mergedPR = None):
    if days:
        period = "for the past {days} days".format(days)
    else:
        period = "For the entire life of the repository"

    if mergedPR:
        print("Merged Pull Requests {period}: {m}\n".format(period=period, m=len(mergedPR)))
        printHistogram(mergedPR, "merge")

    if abandonedPR:
        print("\nAbandoned Pull Requests {period}: {m}\n".format(period=period, m=len(abandonedPR)))
        printHistogram(abandonedPR, "abandon")

    print("\nCurrently Open Pull Requests: {m}\n".format(m=len(openPR)))

    attDay = 15

    openPR.sort(key=lambda x: x.openFor(), reverse=True)
    needsAttention = [ str(x) for x in openPR if x.needsAttention(attDay) ]

    if len(needsAttention) > 0:
        print("Pull Requests needing attention: (open for more than {} days):".format(attDay))
        [ print(x) for x in needsAttention ]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parse github statistics about our repos')
    parser.add_argument('--repo', type=str, default='scylla', help='Repository')
    parser.add_argument('--period', type=int, help='days to look back')
    parser.add_argument('--token', type=str, required=True, help='github authentication token. Without it, this will be rate limited and fail anyway')
    parser.add_argument('--open-only', action='store_true', help='Only look at open PRs')

    args = parser.parse_args()

    open_pr_url  = 'https://api.github.com/repos/scylladb/{}/pulls?state=open?sort=created_at?direction=desc'
    closed_pr_url  = 'https://api.github.com/repos/scylladb/{}/pulls?state=closed?sort=closed_at?direction=desc'

    openPR = getGithubData(open_pr_url.format(args.repo), args.token)
    abandonedPR = []
    mergedPR = []

    if not args.open_only:
        def shouldIncludePR(data):
            days = args.period
            if not days:
                return True
            return datetime.date.today() - datetime.timedelta(days=days) < parse(data['closed_at']).date()

        closedPR = getGithubData(closed_pr_url.format(args.repo), args.token, shouldIncludePR)

        for x in closedPR:
            if x.isOpen():
                raise Exception("Not expecting an open PR")

            if x.isAbandoned():
                abandonedPR.append(x)
            elif x.isMerged():
                mergedPR.append(x)

    printStats(args.period, openPR, abandonedPR, mergedPR)
