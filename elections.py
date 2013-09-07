import csv
import cStringIO
import json
from utils import get_contents_of_url,substitute_char

API_KEY='4a26c19c3cae4f6c843c3e7816475fae'
base_url='http://openstates.org/api/v1/'
apikey_url="apikey="
mnleg_district_demo_info='http://www.gis.leg.mn/redist2010/Legislative/L2012/text/'
mncong_district_demo_info='http://www.gis.leg.mn/redist2010/Congressional/C2012/text/'

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

def sendGetRequest(url):
    url=substitute_char(url,' ','%20')
    response = get_contents_of_url(url)
    if response:
        data=json.loads(response)
        return data
    else:
        return None

def fetchDistrictDemoData(district,chamber):
    if district.find('u')>0: # senate district
        district=district[-2:]
    else: # house district
        district=district[-3:].upper()
    if chamber=='ushouse':
        url=mncong_district_demo_info+district+'.txt'
    else:
        url=mnleg_district_demo_info+district+'.txt'
    page = get_contents_of_url(url)
    demographics={}
    if page:
        loop=True
        while loop:
            w,page=page[:page.find('\n')],page[page.find('\n')+1:]
            v,page=page[:page.find('\n')],page[page.find('\n')+1:]
            # y,page=page[:page.find('\n')],page[page.find('\n')+1:]
            # z,page=page[:page.find('\n')],page[page.find('\n')+1:]
            # results.append((w+': '+v,y+': '+z))
            demographics[w]=v
            if len(page)<=0:
                loop=False
    return demographics,url

def getMNLegDistrictShape(chamber,dist_id):
    if chamber=='upper':
        if len(dist_id)!=2:
            dist_id='0'+dist_id
        dist_string='sldu/mn-'+dist_id
    else:
        if len(dist_id)!=3:
            dist_id='0'+dist_id
        dist_string='sldl/mn-'+dist_id.lower()
    data=getMNLegDistrictById(dist_string)
    if data != None:
        demo_data,demo_url=fetchDistrictDemoData(data.get('boundary_id'),'stateleg')
        results={'name': data.get('name'),
            'chamber': data.get('chamber'),
            'lon_delta': data['region']['lon_delta'],
            'center_lon': data['region']['center_lon'],
            'lat_delta': data['region']['lat_delta'],
            'center_lat': data['region']['center_lat'],
            'alt_id': data.get('id'),
            'dist_id': data.get('boundary_id'),
            'bbox': data.get('bbox'),
            'shape': data.get('shape'), # add members as parse leg objects
            'legislator': getMNLegislatorByDistrict(data.get('name')),
            'demographics': demo_data,
            'demographics_url': demo_url,
            # 'leg_elec_results': ,
        }
        return results
    else:
        return None

def getAllMNLegDistrictShapesbyChamber(chamber):
    districts=getMNLegAllDistricts()
    if districts != None:
        results=[]
        for d in districts:
            if d['chamber']==chamber:
                data=getMNLegDistrictById(d['boundary_id'])
                if data != None:
                    params={'name': data.get('name'),
                        'chamber': data.get('chamber'),
                        'lon_delta': data['region']['lon_delta'],
                        'center_lon': data['region']['center_lon'],
                        'lat_delta': data['region']['lat_delta'],
                        'center_lat': data['region']['center_lat'],
                        'alt_id': data.get('id'),
                        'dist_id': data.get('boundary_id'),
                        'bbox': data.get('bbox'),
                        'shape': data.get('shape'), # add members as parse leg objects
                        'legislator': getMNLegislatorByDistrict(data.get('name')),
                        # 'demographics': fetchDistrictDemoData(data.get('boundary_id')),
                        # 'leg_elec_results': ,
                    }
                    results.append(params)
        return results
    else:
        return None

def getMNLegAllDistricts():
    #http://openstates.org/api/v1/districts/mn/?apikey=4a26c19c3cae4f6c843c3e7816475fae
    url=base_url+'districts/mn/?'+apikey_url+API_KEY
    return sendGetRequest(url)

def getMNLegislatorByDistrict(district):
    #http://openstates.org/api/v1/legislators/?state=mn&district=6A&apikey=4a26c19c3cae4f6c843c3e7816475fae
    url=base_url+'legislators/?state=mn&district='+district+'&'+apikey_url+API_KEY
    return sendGetRequest(url)

def getMNLegDistrictById(district_id):
    #http://openstates.org/api/v1/districts/boundary/sldu/mn-11/?apikey=4a26c19c3cae4f6c843c3e7816475fae
    url=base_url+'districts/boundary/'+district_id+'/?'+apikey_url+API_KEY
    return sendGetRequest(url)
