import csv
import cStringIO
import json
from utils import get_contents_of_url

def parseCSVfromURL(page,delimiter):
	csvio = cStringIO.StringIO(page)
	data = csv.reader(csvio, delimiter=delimiter)
	return data

def fetchElectionResults(url):
	response = get_contents_of_url(url)
	if response and response!=None:
		response = parseCSVfromURL(response,',')
		results=[]
		for r in response:
			results.append([r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9],r[10],r[11],r[12],r[13],r[14],r[15]])
		return results
	else:
		return None

def fetchPrecinctTable(url):
	response = get_contents_of_url(url)
	if response and response!=None:
		response = parseCSVfromURL(response,';')
		results=[]
		for r in response:
			results.append([r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9]])
		return results
	else:
		return None
