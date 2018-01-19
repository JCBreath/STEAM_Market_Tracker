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

def matching(pat, text, result):
	regex = pat

	test_str = text

	matchNum = 0

	matches = re.finditer(regex, test_str)

	for matchNum, match in enumerate(matches):
		matchNum = matchNum + 1

		result.append("Match {matchNum} was found at {start}-{end}: {match}\n".format(matchNum = matchNum, start = match.start(), end = match.end(), match = match.group()))

		for groupNum in range(0, len(match.groups())):
			groupNum = groupNum + 1
			result.append("Group {groupNum} found at {start}-{end}: {group}".format(groupNum = groupNum, start = match.start(groupNum), end = match.end(groupNum), group = match.group(groupNum)))
	
	return matchNum

def textMatching():
	print "Text = "
	raw_data = raw_input()
	print
	pat = raw_input("RegEx = ")
	fp = open('output.txt', 'w')
	result = []
	matchNum = matching(pat, raw_data, result)
	
	if matchNum == 1:
		print "1 match found."
	else:
		print str(matchNum) + " matches found."

	if matchNum > 0:
		if_view = raw_input('View result? (y/n)')
		if if_view == 'y' or if_view == 'Y' or if_view == '':
			print ''.join(result)
	

def webCrawling():
	my_url = raw_input("URL = ")
	raw_data = getHtml(my_url)
	show_raw = raw_input("Show raw data? (y/n) ")
	if show_raw == "y" or show_raw == "Y":
		print raw_data
	pat = raw_input("RegEx = ")
	result = []
	matchNum = matching(pat, raw_data, result)
	
	if matchNum == 1:
		print "1 match found."
	else:
		print str(matchNum) + " matches found."

	if matchNum > 0:
		if_view = raw_input('View result? (y/n)')
		if if_view == 'y' or if_view == 'Y' or if_view == '':
			print ''.join(result)


def setting():
	print "No Settings"


print "  Regular Expression Tester  "
print ("0: Use Input Text")
print ("1: Use HttpRequest")
print ("2: Setting")
print ("3: Help")
print ("")

op = raw_input("Press Enter or enter a number: ")

if op == '0' or op == '':
	textMatching()
elif op == '1':
	webCrawling()