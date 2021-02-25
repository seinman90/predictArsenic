#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import socket
import requests, json
import numpy as np
from datetime import datetime
import os
import urllib.request
import time

external_ip = urllib.request.urlopen('https://ident.me').read().decode('utf8')

wd = '/home/beeb/Insync/sei2112@columbia.edu/Google Drive/Columbia SusDev PhD/Research/My work/predictArsenic/'
os.chdir(wd)
datInpath = 'data/intermediate/bamwsp/villages.csv'
keyInpath = 'data/raw/googlePlaces/apiKey.txt'
usageInpath = 'data/intermediate/googlePlaces/logging/usage.csv'
outpath = 'data/intermediate/googlePlaces/{}.txt'
errorsName = 'errors'
resultsName = 'results'
# url variable store url 
url = "https://maps.googleapis.com/maps/api/geocode/json?address={query}&key={key}"
MAXUSAGEMONTHLY = 30000
MAXUSAGEDAILY = 1333


# In[2]:


# set up API key
api_key = pd.read_csv(keyInpath, header = None, squeeze = True)[0]


# In[3]:


def main():
    queries = listQueries(datInpath)
    results, errors = resultsErrors(outpath, resultsName, errorsName, queries)
    usage, currentMonthlyUsage, currentDailyUsage = setUpLog(usageInpath, external_ip)
    queryAPI(queries, results, errors, usage, currentMonthlyUsage, currentDailyUsage, MAXUSAGEMONTHLY, MAXUSAGEDAILY)


# # Read in BAMWSP data, create a list of queries to send to Google
# The data consist of a list of Bangladeshi villages, the number of wells in each one, and the proportion of those that are 'safe'. The geographics given are District, Upazila, Union, Mouza and Village. However, it is raw for Google to correctly geocode a Bangladeshi village, so instead we create a query at the Mouza level. This leaves us with ~22,600 unique obs.

# In[4]:


# read in BAMWSP village data and create list of queries
def listQueries(datInpath):
    dat = pd.read_csv(datInpath )
    dat['query'] = dat['Mouza'] + ',+' + dat['Union']+ ',+Bangladesh'
    queries = dat['query'].unique()
    return queries


# In[5]:


## PREPARE OUTPUT - successful and unsuccessful attempts at geocoding
def resultsErrors(outpath, resultsName, errorsName, queries):
    # if we already have results, load them and exclude already-run queries; else create a new empty list
    if os.path.exists(outpath.format(resultsName)):
        with open(outpath.format(resultsName)) as f:
            results = json.load(f)
        queries = [i for i in queries if i not in results.keys()]
    else:
        results = dict()


    # do the same for errors
    if os.path.exists(outpath.format(errorsName)):
        with open(outpath.format(errorsName)) as f:
            errors = json.load(f)
        queries = [i for i in queries if i not in errors]   
    else:
        errors = []
    return results, errors


# In[6]:


# this function exists because I have a dyamic IP address
# GCP is limited by IP address, so need to update whenever my IP changes
# then wait 5 mins for GCP to update
def updateIP(external_ip, usage):
    input('check GCP IP address is set to {} then hit enter'.format(external_ip))
    usage.loc[usage.month == max(usage.month), 'ipv6'] = external_ip
    usage.to_csv(usageInpath, index = False)
    time.sleep(300)


# # Usage handling
# Google charges if you use their services too much. Therefore, it's important to limit your monthly usage. If you use more than 40k hits on the Geocode API you start getting charged 5USD per 1000 hits, so this bit of code makes sure that I'm using less than that.

# In[7]:


def setUpLog(usageInpath, external_ip):

    today = datetime.today()
    if len(str(today.month)) == 1:
        m = '0' + str(today.month)
    month = int(str(today.year) + m)
    

    # check if we already have usage stats, if not create a new one
    try:
        usage = pd.read_csv(usageInpath)
    except FileNotFoundError:
        usage = pd.DataFrame(data = {'month' : [month], 'hits' : [0], 'ipv6': [external_ip]})
        usage.to_csv(usageInpath)
        updateIP(external_ip, usage)

    mostRecentIP = usage.ipv6[usage.month == max(usage.month)].iloc[0]
    if mostRecentIP != external_ip:
        print(usage)
        print(external_ip)
        updateIP(external_ip, usage)

    # check if we have any usage for the current month, if not add it in
    if max(usage.month) < month:
        newUsage = pd.DataFrame(data = {'month' : [month], 'hits' : [0], 'ipv6': [external_ip]})
        usage = pd.concat([usage, newUsage])

    currentMonthlyUsage = usage.hits[usage.month == month].iloc[0]
    currentDailyUsage = 0
    
    return usage, currentMonthlyUsage, currentDailyUsage


# In[8]:


def queryAPI(queries, results, errors, usage, currentMonthlyUsage, currentDailyUsage, MAXUSAGEMONTHLY, MAXUSAGEDAILY):
    month = datetime.today().month
    for query in queries[(len(results) + len(errors)):len(queries)]:
        # only query if we're not past max usage per day/month
        if (currentMonthlyUsage < MAXUSAGEMONTHLY) and (currentDailyUsage < MAXUSAGEDAILY):

            # keep track of how many iterations we've had
            # print the current status
            # save the current # of queries carried out
            if currentMonthlyUsage % 100 == 0:
                print('Iteration ' + str(currentDailyUsage) + ' at ' 
                          + str(datetime.now()) + ' for query ' + query)
                usage = updateLog(usage, month, currentMonthlyUsage)
            # start iterating through remaining 
            try:

                # get method of requests module 
                # return response object 
                r = requests.get(url.format(query=query, key = api_key)) 

                # json method of response object convert 
                #  json format data into python format data 
                x = r.json()
                if x['status'] == 'OK':
                    x['query'] = query
                    results[query] = x
                elif x['status'] == 'OVER_QUERY_LIMIT':
                    errors.append(query)
                    break
                elif x['status'] == '':
                    updateIP(external_ip)
                    errors.append(query)
                else:
                    errors.append(query)
            except:
                errors.append(query)

            currentMonthlyUsage += 1
            currentDailyUsage += 1
    
    usage = updateLog(usage, month, currentMonthlyUsage)

    # save the new results
    with open(outpath.format(resultsName), 'w') as f:
        json.dump(results, f)


# In[9]:


# record the extra usage that took place today        
def updateLog(usage, month, currentMonthlyUsage):
    usage.loc[usage.month == month, 'hits'] = currentMonthlyUsage
    usage.to_csv(usageInpath, index = False)
    return usage


# In[10]:


if __name__ == "__main__":
    main()


# In[ ]:




