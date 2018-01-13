# -*- coding: UTF-8 -*-
import urllib2
import os
import shutil
import re
import lxml
import sys

def getHtml(url):
    head = {}
    head['User-Agent'] = 'Mozilla/5.0 (Linux; Android 4.1.1; Nexus 7 Build/JRO03D) AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.166  Safari/535.19'
    req = urllib2.Request(url, headers=head)
    page = urllib2.urlopen(req)
    html = page.read().encode('UTF-8')
    
    return html

def matching(pat, text, file):
	pat = r"\"normal_price\\\">(.*?)\<\/span\>"
	matches = re.finditer(pat, text)
	matchNum = 0
	for matchNum, match in enumerate(matches):
		matchNum = matchNum + 1
		print (match.group(1))
		file.writelines(match.group(1)+'\n')
		print matchNum
	return matchNum

fp = open('output.txt', 'w')
keyword = raw_input("Keyword=")
page = 0
html = getHtml("http://steamcommunity.com/market/search/render/?query="+keyword+"&country=US&currency=1&start="+str(page)+"&count=100&sort_column=price&sort_dir=asc&appid=730&l=english")
namePat = r"[#FFD700|#CF6A32|#D2D2D2];\\\"\>(.*?)\<\\\/span\>"
pricePat = r"\"normal_price\\\">(.*?)\<\/span\>"
count = 0
while(count<217):
	count += matching(namePat, html, fp)
	page += 100
	html = getHtml("http://steamcommunity.com/market/search/render/?query="+keyword+"&country=US&currency=1&start="+str(page)+"&count=100&sort_column=price&sort_dir=asc&appid=730&l=english")

print ("# Result Count: "+str(count))
    #for groupNum in range(0, len(match.groups())):
    #    groupNum = groupNum + 1
        
    #    print ("Group {groupNum} found at {start}-{end}: {group}".format(groupNum = groupNum, start = match.start(groupNum), end = match.end(groupNum), group = match.group(groupNum)))
#fp.writelines()
