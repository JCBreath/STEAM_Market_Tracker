# -*- coding: UTF-8 -*-
import urllib3
import os
import shutil
import re
import lxml
import sys
from bs4 import BeautifulSoup

def getHtml(url):
    head = {}
    head['User-Agent'] = 'Mozilla/5.0 (Linux; Android 4.1.1; Nexus 7 Build/JRO03D) AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.166  Safari/535.19'
    http = urllib3.PoolManager()
    response = http.request('GET', url)
    html = response.data.decode('utf-8')
    
    return html

def matching(pat, text, file):
	pat = r"\"normal_price\\\">(.*?)\<\/span\>"
	matches = re.finditer(pat, text)
	matchNum = 0
	for matchNum, match in enumerate(matches):
		matchNum = matchNum + 1
		print(match.group(1))
		file.writelines(match.group(1)+'\n')
		print(matchNum)
	return matchNum


#print ("0. Default Mode")
#print ("1. Parsing Mode")


#my_url = raw_input("URL")
if input("Load new html? (y/n): ") == 'y':
	page = 0
	keyword = input("Keyword=")
	html = getHtml("http://steamcommunity.com/market/search/render/?query="+keyword+"&country=US&currency=1&start="+str(page)+"&count=100&sort_column=price&sort_dir=asc&appid=730&l=english")
	fin = open('html_temp.txt','w+')
	fin.writelines(html)
else:
	try:
		fin = open('html_temp.txt','r')
	except IOError:
		print("No input file, please load new html.")
		sys.exit()
	html = fin.read()
	fin.close()
namePat = r"data-hash-name=\\\"(.*?)\\\">\\"
pricePat = r"sale_price\\\">(\$.*?)<\\/span>"
#print html
names = re.findall(namePat,html)
prices = re.findall(pricePat,html)
if input("Save as .csv? (y/n): ") == 'y':
	fout = open('item_list.csv', 'w+')
else:
	fout = open('item_list.txt', 'w+')
for i in range(len(prices)):
	names[i].replace("\\u2122","(TM)")
	print('{},{}'.format(names[i],prices[i]))
	fout.write('{},{}\n'.format(names[i],prices[i]))
fout.close()

print("\nTotal results found: " + str(len(prices)))

'''
count = 0
while(count<217):
	count += matching(namePat, html, fp)
	page += 100
	html = getHtml("http://steamcommunity.com/market/search/render/?query="+keyword+"&country=US&currency=1&start="+str(page)+"&count=100&sort_column=price&sort_dir=asc&appid=730&l=english")
'''
