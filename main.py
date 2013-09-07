#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import webapp2
import datetime
import os
import jinja2
from google.appengine.api import memcache
from boto.s3.key import Key
import boto
import ConfigParser
from links import results_links,p_results_links,county_links,precinct_table_links
from elections import (fetchElectionResults,fetchPrecinctTable,getAllMNLegDistrictShapesbyChamber,
                    getMNLegDistrictShape,fetchDistrictDemoData,getFECData)
from parse import (addPrecinctTableToParse,addPrecinctsToParse,addCountiesToParse,
					addResultsToParse,Results,addPrimaryToParse,Primary,)
from utils import (check_secure_val,make_secure_val,check_valid_signup,escape_html,
                    clear_cache,getFromCache,putInCache,get_contents_of_url,)

# define template pages
main_page="front.html"
statewide_page='statewide.html'
statewide_house_page='statewide-house.html'
statewide_district_page='statewide-district.html'
primary_page='primary.html'
history_page='history.html'
graph_page='elections-graph.html'
maps_page='maps.html'
maps_district_page='maps-district.html'
maps_ushouse_district_page='maps-ushouse-district.html'
cong_bubble='cong-bubble-chart.html'
cong_money='money.html'
about_page='about.html'
feedback_page='feedback.html'
feedback_response_page='feedback-response.html'
e404_page='404.html'

#environment loader, load template from aws
class MyLoader(jinja2.BaseLoader):
    def __init__(self, path):
        self.path = path

    def get_source(self, environment, template):
        path = self.path+template
        page=get_contents_of_url(path)
        if not page:
            raise jinja2.TemplateNotFound(template)
        source = page.decode('utf-8')
        return source, path, lambda: False #lambda: mtime == os.path.getmtime(path)

# set up jinja templates
aws_templates='https://s3.amazonaws.com/mnelections/templates/' # aws template location
aws_output='https://s3.amazonaws.com/mnelections/output/' # aws 'cache' location
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
# jinja_env = jinja2.Environment(loader = MyLoader(aws_templates),
#                                autoescape = True,
#                                extensions=['jinja2.ext.autoescape'])
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

# misc functions
def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def connectToAWS():
    try:
        config = ConfigParser.ConfigParser()
        config.read(["etc/boto.cfg"])
        k=config.get('Credentials','aws_access_key_id')
        s=config.get('Credentials','aws_secret_access_key')
        c=boto.connect_s3(k,s)
        return c
    except:
        pass

def getAWSKey(key):
    c=connectToAWS()
    if c:
        b=c.get_bucket('mnelections')
        k=Key(b)
        k.key=key
        return k
    return None

def getKeyFromAWS(key):
    c=connectToAWS()
    if c:
        b=c.get_bucket('mnleginfo')
        k=b.get_key(key)
        if k:
            return k
    return None

# generic page handler
class GenericHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def cache_render(self,key,template, **kw):
        page=self.render_str(template, **kw)
        putInCache(key,page)
        self.write(page)

    def set_secure_cookie(self,name,val):
        cookie_val=make_secure_val(val)
        self.response.set_cookie(name, cookie_val, path="/")

    def read_secure_cookie(self,name):
        cookie_val=self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
    	user_id=str(user.key().id())
        self.set_secure_cookie('user_id',user_id)
        return user_id

    def logout(self):
        self.response.set_cookie('user_id', '', path="/")

    def check_login(self,path):
    	params=dict(path=path)
        params['loggedin_user']="Guest"
    	return params

    # def initialize(self,*a,**kw):
    #     webapp2.RequestHandler.initialize(self,*a,**kw)
    #     uid=self.read_secure_cookie('user_id')
    #     self.user = uid and User.by_id(int(uid))

office_id_key={'0101':'President',
			   '0102':'US Senator',
               '0103':'US Senator',
               '0100':'US House',
               '0331':'Governor',
               '0332':'Secretary of State',
               '0333':'Auditor',
               '0335':'Attorney General',
			   '0351':'Amendment 1',
			   '0352':'Amendment 2',
				}

office_link_key={'president':'0101',
               'ussenator1':'0102',
               'ussenator2':'0103',
               'governor':'0331',
               'secretaryofstate':'0332',
               'auditor':'0333',
               'attorneygeneral':'0335',
               'amendment1':'0351',
               'amendment2':'0352',
                }

office_key_link={'0101':'president',
               '0102':'ussenator1',
               '0103':'ussenator2',
               '0331':'governor',
               '0332':'secretaryofstate',
               '0333':'auditor',
               '0335':'attorneygeneral',
               '0351':'amendment1',
               '0352':'amendment2',
                }

us_rep_id_key=[('0104','1'),
			   ('0105','2'),
			   ('0106','3'),
			   ('0107','4'),
			   ('0108','5'),
			   ('0109','6'),
			   ('0110','7'),
			   ('0111','8')]

ushouse_district_names={
    '1':'one',
    '2':'two',
    '3':'three',
    '4':'four',
    '5':'five',
    '6':'six',
    '7':'seven',
    '8':'eight',
}

ushouse_range=range(104,112)#[104,111]
state_senate_range=range(121,188)#[121,187]
state_house_range=range(188,322)#[188,321]

state_leg_ranges={'house':state_house_range,
                    'senate':state_senate_range}

def formatStateLegNum(n):
	return '0'+str(n)

election_years=['2012','2010','2008','2006','2004','2002','2000']
office_link_names=['president','ussenator1','ussenator2','governor','secretaryofstate','auditor','attorneygeneral','amendment1','amendment2']
other_office_link_names=['ushouse','senate','house']

offices_2012={'offices':['0101','0102','0351','0352'],'senate':True}
offices_2010={'offices':['0331','0332','0333','0335'],'senate':True}
offices_2008={'offices':['0101','0103','0351'],'senate':False}
offices_2006={'offices':['0102','0331','0332','0333','0335','0351'],'senate':True}
offices_2004={'offices':['0101'],'senate':False}
offices_2002={'offices':['0103','0331','0332','0333','0335'],'senate':True}
offices_2000={'offices':['0101','0102'],'senate':True}

p_offices_2012={'offices':['0102'],'senate':True}
p_offices_2010={'offices':['0331','0332','0335'],'senate':True}
p_offices_2008={'offices':['0103'],'senate':False}
p_offices_2006={'offices':['0102','0331','0332','0335'],'senate':True}
p_offices_2004={'offices':[],'senate':False}
p_offices_2002={'offices':['0103','0331','0332','0333','0335'],'senate':True}
p_offices_2000={'offices':['0102'],'senate':True}

p_ushouse_offices_2012=[('0104','1'),('0105','2'),('0106','3'),('0107','4'),('0108','5'),('0109','6'),('0111','8')]
p_ushouse_offices_2010=[('0105','2'),('0107','4'),('0108','5'),('0109','6'),('0110','7'),('0111','8')]
p_ushouse_offices_2008=[('0104','1'),('0106','3'),('0108','5'),('0109','6'),('0110','7')]
p_ushouse_offices_2006=[('0104','1'),('0106','3'),('0107','4'),('0108','5'),('0110','7')]
p_ushouse_offices_2004=[('0104','1'),('0105','2'),('0106','3'),('0107','4'),('0108','5'),('0109','6'),('0110','7'),('0111','8')]
p_ushouse_offices_2002=[('0104','1'),('0105','2'),('0106','3'),('0107','4'),('0108','5'),('0109','6'),('0110','7'),('0111','8')]
p_ushouse_offices_2000=[('0104','1'),('0105','2'),('0106','3'),('0107','4'),('0108','5'),('0109','6'),('0110','7'),('0111','8')]


p_ushouse_offices={
    '2012':p_ushouse_offices_2012,
    '2010':p_ushouse_offices_2010,
    '2008':p_ushouse_offices_2008,
    '2006':p_ushouse_offices_2006,
    '2004':p_ushouse_offices_2004,
    '2002':p_ushouse_offices_2002,
    '2000':p_ushouse_offices_2000,
}

p_ushouse_list_2012=[1,2,3,4,5,6,8]
p_ushouse_list_2010=[2,4,5,6,7,8]
p_ushouse_list_2008=[1,3,5,6,7]
p_ushouse_list_2006=[1,3,4,5,7]
p_ushouse_list_2004=[1,2,3,4,5,6,7,8]
p_ushouse_list_2002=[1,2,3,4,5,6,7,8]
p_ushouse_list_2000=[1,2,3,4,5,6,7,8]

p_ushouse_lists={
    '2012':p_ushouse_list_2012,
    '2010':p_ushouse_list_2010,
    '2008':p_ushouse_list_2008,
    '2006':p_ushouse_list_2006,
    '2004':p_ushouse_list_2004,
    '2002':p_ushouse_list_2002,
    '2000':p_ushouse_list_2000,
}

all_office_ids_by_year={
	'2012':offices_2012,
	'2010':offices_2010,
	'2008':offices_2008,
	'2006':offices_2006,
	'2004':offices_2004,
	'2002':offices_2002,
	'2000':offices_2000
}

p_all_office_ids_by_year={
    '2012':p_offices_2012,
    '2010':p_offices_2010,
    '2008':p_offices_2008,
    '2006':p_offices_2006,
    '2004':p_offices_2004,
    '2002':p_offices_2002,
    '2000':p_offices_2000
}

amendment_text_2012={
    'amendment1':'Recognition of Marriage Solely Between One Man and One Woman',
    'amendment2':'Photo Identification Required for Voting'
}

amendment_text_2008={
    'amendment1':'Clean Water, Wildlife, Cultural Heritage, and Natural Areas'
}

amendment_text_2006={
    'amendment1':'Phased In Dedication of the Motor Vehicle Sales Tax to Highways and Public Transit'
}

all_amendment_text={
    '2012':amendment_text_2012,
    '2008':amendment_text_2008,
    '2006':amendment_text_2006
}

history_years=['1979','1949','1919','1890','1850']

polling_title={
    'governor':'Mark Dayton Approvals',
    'senator':'Al Franken Approvals',
}

graph_page_style_names={
    'raw':'raw votes',
    'percent':'vote %',
}

def getChamberName(name):
    if name=='house':
        return 'lower'
    elif name=='senate':
        return 'upper'
    else:
        return name

def formatProperName(data):
    results=[]
    for d in data:
        d.percent_votes=str((float(d.candidate_votes)/int(d.total_votes))*100)
        d.candidate_name=d.candidate_name.replace('"', '')
        d.candidate_name=d.candidate_name.title()
        results.append(d)
    return sorted(results, key=lambda results: int(results.candidate_votes),reverse=True)

def setStatewideParams(params):
    office_names=[]
    results=[]
    params['years']=election_years
    params['offices']=all_office_ids_by_year[params['year']]
    for o in params['offices']['offices']:
        office_names.append((office_key_link[o],office_id_key[o]))
    params['office_names']=office_names
    return params

def setPrimaryParams(params):
    office_names=[]
    results=[]
    params['years']=election_years
    params['offices']=p_all_office_ids_by_year[params['year']]
    for o in params['offices']['offices']:
        office_names.append((office_key_link[o],office_id_key[o]))
    params['office_names']=office_names
    return params

def primaryDistrictAdd(districts,d):
    office=int(d.office_id)
    if office in ushouse_range:
        if d.office_id not in districts['ushouse']:
            districts['ushouse'].append(d.office_id)
    elif office in state_house_range:
        if d.office_id not in districts['house']:
            districts['house'].append(d.office_id)
    elif office in state_senate_range:
        if d.office_id not in districts['senate']:
            districts['senate'].append(d.office_id)
    return districts

def formatPrimaryResults(results,params):
    params['dfl_data']=[]
    params['gop_data']=[]
    params['ip_data']=[]
    for r in results:
        if r.party_id=='DFL':
            params['dfl_data'].append(r)
        elif r.party_id=='R' or r.party_id=='R  ':
            params['gop_data'].append(r)
        elif r.party_id=='IP' or r.party_id=='I  ':
            params['ip_data'].append(r)
    return params

def getOfficeCodefromDistrict(district):
    if district.isdigit():
        n=int(district)
        if n<68 and n>0:
            n+=120
            return '0'+str(n)
    else:
        n=int(district[:-1])*2
        if n<135 and n>0:
            if district.find('B') == -1 and district.find('A') > 0:
                n-=1
            n+=187
            return '0'+str(n)
    return None

def formatChartOfficeData(data,style):
    dfl_table={}
    gop_table={}
    ip_table={}
    ip_present='0'
    for d in data:
        if d.party_id=="DFL":
            if style == 'raw':
                dfl_table[d.year]=d.candidate_votes
            else:
                dfl_table[d.year]=d.percent_votes
        elif d.party_id=="R" or d.party_id=="R  ":
            if style == 'raw':
                gop_table[d.year]=d.candidate_votes
            else:
                gop_table[d.year]=d.percent_votes
        elif d.party_id=="IP" or d.party_id=="I  ":
            ip_present='1'
            if style == 'raw':
                ip_table[d.year]=d.candidate_votes
            else:
                ip_table[d.year]=d.percent_votes
    results=[]
    for year in dfl_table:
        if year in gop_table:
            if ip_present=='1':
                if year in ip_table:
                    results.append([year,dfl_table[year],gop_table[year],ip_table[year]])
                else:
                    results.append([year,dfl_table[year],gop_table[year],'0'])
            else:
                results.append([year,dfl_table[year],gop_table[year]])
        else:
            if ip_present=='1':
                if year in ip_table:
                    results.append([year,dfl_table[year],'0',ip_table[year]])
                else:
                    results.append([year,dfl_table[year],'0','0'])
            else:
                results.append([year,dfl_table[year],'0'])
    for year in gop_table:
        if year not in dfl_table:
            if ip_present=='1':
                if year in ip_table:
                    results.append([year,'0',gop_table[year],ip_table[year]])
                else:
                    results.append([year,'0',gop_table[year],'0'])
            else:
                results.append([year,'0',gop_table[year]])
    return ip_present,sorted(results, key=lambda results: int(results[0]),reverse=False)

# page handlers
class MainHandler(GenericHandler):
    def get(self):
        params=self.check_login("/")
        params['title']="MN Elections Info | 2014 Elections Polling"
        params['description']=default_meta_description
        params['years']=election_years
        office=self.request.get("polls")
        if office in polling_title:
            params['active']=office
        else:
            params['active']='governor'
        params['graph_title']=polling_title[params['active']]
        self.render(main_page,**params)

class HistoryHandler(GenericHandler):
    def get(self):
        params=self.check_login('/history')
        params['title']="MN Elections Info | Elections History 1858-Present"
        params['description']=default_meta_description
        params['year']=history_years[0]
        self.render(history_page,**params)

class HistoryYearHandler(GenericHandler):
    def get(self,year):
        params=self.check_login('/history/'+year)
        params['title']="MN Elections Info | Elections History 1858-Present"
        params['description']=default_meta_description
        if year in history_years:
            params['year']=year
            self.render(history_page,**params)
        else:
            self.redirect('/history')

class StatewideHandler(GenericHandler):
    def get(self):
        params=self.check_login('/general')
        params['description']=default_meta_description
        params['year']='2012'
        params=setStatewideParams(params)
        previous=self.request.get("office")
        params['office']=params['office_names'][0][1]
        params['active']=params['office_names'][0][0]
        params['title']="MN Elections Info | " + params['year'] + " General Elections Results, " + params['office']
        data=Results.by_year_by_office_id(params['year'],office_link_key[params['active']])
        if data:
            results=formatProperName(data)
            params['data']=results
        self.render(statewide_page,**params)
        # else:
        #     self.redirect('/')

class StatewideYearHandler(GenericHandler):
    def get(self,year):
        params=self.check_login("/general/"+year)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params=setStatewideParams(params)
            previous=self.request.get("office")
            dist_id=self.request.get("dist_id")
            if len(previous)>0:
                if previous=='house':
                    if len(dist_id)>0:
                        office_code=getOfficeCodefromDistrict(dist_id)
                        if office_code!=None:
                            self.redirect('/general/'+year+'/'+previous+'/'+dist_id)
                        else:
                            self.redirect('/general/'+year+'/'+previous)
                    else:
                        self.redirect('/general/'+year+'/'+previous)
                elif previous=='ushouse':
                    if len(dist_id)>0:
                        if int(dist_id)>0 and int(dist_id)<9:
                            self.redirect('/general/'+year+'/'+previous+'/'+dist_id)
                        else:
                            self.redirect('/general/'+year+'/'+previous)
                    else:
                        self.redirect('/general/'+year+'/'+previous)
                elif previous=='senate':
                    if all_office_ids_by_year[year]['senate']==True:
                        if len(dist_id)>0:
                            office_code=getOfficeCodefromDistrict(dist_id)
                            if office_code!=None:
                                self.redirect('/general/'+year+'/'+previous+'/'+dist_id)
                            else:
                                self.redirect('/general/'+year+'/'+previous)
                        else:
                            self.redirect('/general/'+year+'/'+previous)
                    else:
                        self.redirect('/general/'+year)
                else:
                    for o in params['office_names']:
                        if previous == o[0]:
                            self.redirect('/general/'+year+'/'+previous)
            params['office']=params['office_names'][0][1]
            params['active']=params['office_names'][0][0]
            params['title']="MN Elections Info | " + params['year'] + " General Elections Results, " + params['office']
            data=Results.by_year_by_office_id(params['year'],office_link_key[params['active']])
            if data:
                results=formatProperName(data)
                params['data']=results
            self.render(statewide_page,**params)
            # else:
            #     self.redirect('/general/'+year)
        else:
            self.redirect('/general')

class StatewideYearOfficeHandler(GenericHandler):
    def get(self,year,office):
        params=self.check_login("/general/"+year+'/'+office)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params=setStatewideParams(params)
            if office in other_office_link_names:
                if office=='ushouse':
                    params['active']='ushouse'
                    params['office']='1'
                    params['district_key']=us_rep_id_key
                    params['title']="MN Elections Info | " + params['year'] + " General Elections Results, US House " + params['office']
                    data=Results.by_year_by_office_id(params['year'],us_rep_id_key[int(params['office'])-1][0])
                    if data:
                        results=formatProperName(data)
                        params['data']=results
                    self.render(statewide_page,**params)
                else:
                    if office=='senate':
                        params['active']='senate'
                        params['office']='State Senate'
                        params['active_id']='0121'
                        params['district_id']='1'
                    else:
                        params['active']='house'
                        params['office']='State House'
                        params['active_id']='0188'
                        params['district_id']='1A'
                    params['title']="MN Elections Info | " + params['year'] + " General Elections Results, " + params['office'] + " " + params['district_id']
                    data=Results.by_year_by_office_id(params['year'],params['active_id'])
                    if data:
                        results=formatProperName(data)
                        params['data']=results
                    params['range']=state_leg_ranges[params['active']]
                    self.render(statewide_district_page,**params)
            elif office in office_link_key:
                if office_link_key[office] in all_office_ids_by_year[year]['offices']:
                    params['active']=office
                    if year in all_amendment_text:
                        if office in all_amendment_text[year]:
                            params['amendment_text']=all_amendment_text[year][office]
                    params['office']=office_id_key[office_link_key[office]]
                    params['title']="MN Elections Info | " + params['year'] + " General Elections Results, " + params['office']
                    data=Results.by_year_by_office_id(params['year'],office_link_key[office])
                    if data:
                        results=formatProperName(data)
                        params['data']=results
                    self.render(statewide_page,**params)
                else:
                    self.redirect('/general/'+year)
            else:
                self.redirect('/general/'+year)
        else:
            self.redirect('/general')

class StatewideYearUSHouseHandler(GenericHandler):
    def get(self,year,office):
        params=self.check_login("/general/"+year+'/ushouse/'+office)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params['active']='ushouse'
            params=setStatewideParams(params) 
            if int(office) < 9 and int(office) > 0:
                params['office']=office
                params['district_key']=us_rep_id_key
                params['title']="MN Elections Info | " + params['year'] + " General Elections Results, US House " + params['office']
                data=Results.by_year_by_office_id(params['year'],us_rep_id_key[int(params['office'])-1][0])
                if data:
                    results=formatProperName(data)
                    params['data']=results
                self.render(statewide_page,**params)
            else:
                self.redirect('/general/'+year+'/ushouse')
                
        else:
            self.redirect('/general')

class StatewideYearLegHandler(GenericHandler):
    def get(self,year,office,office_id):
        params=self.check_login("/general/"+year+'/'+office+'/'+office_id)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params['active']=office
            params=setStatewideParams(params) 
            params['office']='State House'
            if office=='senate':
                params['office']='State Senate'
            office_code=getOfficeCodefromDistrict(office_id)
            if office_code!=None:
                params['district_id']=office_id
                params['active_id']=office_code
                params['title']="MN Elections Info | " + params['year'] + " General Elections Results, " + params['office'] + " " + params['district_id']
                data=Results.by_year_by_office_id(params['year'],params['active_id'])
                if data:
                    results=formatProperName(data)
                    params['data']=results
                params['range']=state_leg_ranges[params['active']]
                self.render(statewide_district_page,**params)
                # else:
                #     self.redirect('/general/'+year+'/'+office) 
            else:
                self.redirect('/general/'+year+'/'+office)  
        else:
            self.redirect('/general')

class PrimaryHandler(GenericHandler):
    def get(self):
        params=self.check_login('/primary')
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        params['year']='2012'
        params=setPrimaryParams(params)
        params['office']=params['office_names'][0][1]
        params['active']=params['office_names'][0][0]
        params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, " + params['office']
        data=Primary.by_year_by_office_id(params['year'],office_link_key[params['active']])
        if data:
            results=formatProperName(data)
            params=formatPrimaryResults(results,params)
        self.render(primary_page,**params)
        # else:
        #     self.redirect('/')

class PrimaryYearHandler(GenericHandler):
    def get(self,year):
        params=self.check_login("/primary/"+year)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params=setPrimaryParams(params)
            previous=self.request.get("office")
            dist_id=self.request.get("dist_id")
            if len(previous)>0:
                if previous=='house':
                    if len(dist_id)>0:
                        office_code=getOfficeCodefromDistrict(dist_id)
                        if office_code!=None:
                            self.redirect('/primary/'+year+'/'+previous+'/'+dist_id)
                        else:
                            self.redirect('/primary/'+year+'/'+previous)
                    else:
                        self.redirect('/primary/'+year+'/'+previous)
                elif previous=='ushouse':
                    if len(dist_id)>0:
                        if int(dist_id)>0 and int(dist_id)<9:
                            self.redirect('/primary/'+year+'/'+previous+'/'+dist_id)
                        else:
                            self.redirect('/primary/'+year+'/'+previous)
                    else:
                        self.redirect('/primary/'+year+'/'+previous)
                elif previous=='senate':
                    if all_office_ids_by_year[year]['senate']==True:
                        if len(dist_id)>0:
                            office_code=getOfficeCodefromDistrict(dist_id)
                            if office_code!=None:
                                self.redirect('/primary/'+year+'/'+previous+'/'+dist_id)
                            else:
                                self.redirect('/primary/'+year+'/'+previous)
                        else:
                            self.redirect('/primary/'+year+'/'+previous)
                    else:
                        self.redirect('/primary/'+year)
                else:
                    for o in params['office_names']:
                        if previous == o[0]:
                            self.redirect('/primary/'+year+'/'+previous)
            if year!='2004':
                params['office']=params['office_names'][0][1]
                params['active']=params['office_names'][0][0]
                params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, " + params['office']
                data=Primary.by_year_by_office_id(params['year'],office_link_key[params['active']])
            else:
                params['active']='ushouse'
                params['districts']=p_ushouse_offices[params['year']]
                params['active_id']=us_rep_id_key[0][0]
                params['district_id']=us_rep_id_key[0][1]
                params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, US House " + params['district_id']
                data=Primary.by_year_by_office_id(params['year'],'0104')
            if data:
                results=formatProperName(data)
                params=formatPrimaryResults(results,params)
            self.render(primary_page,**params)
            # else:
            #     self.redirect('/primary/'+year)
        else:
            self.redirect('/primary')

class PrimaryYearOfficeHandler(GenericHandler):
    def get(self,year,office):
        params=self.check_login("/primary/"+year+'/'+office)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params=setPrimaryParams(params)
            if office in other_office_link_names:
                if office=='ushouse':
                    params['active']='ushouse'
                    params['districts']=p_ushouse_offices[params['year']]
                    params['active_id']=params['districts'][0][0]
                    params['district_id']=params['districts'][0][1]
                    params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, US House " + params['district_id']
                    data=Primary.by_year_by_office_id(params['year'],params['active_id'])
                    if data:
                        results=formatProperName(data)
                        params=formatPrimaryResults(results,params)
                    self.render(primary_page,**params)
                else:
                    if office=='senate':
                        params['active']='senate'
                        params['office']='State Senate'
                    else:
                        params['active']='house'
                        params['office']='State House'
                    params['districts']=Primary.get_offices_by_other_office(params['year'],params['active'])
                    params['active_id']=params['districts'][0][0]
                    params['district_id']=params['districts'][0][1]
                    params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, " + params['office'] + " " + params['district_id']
                    data=Primary.by_year_by_office_id(params['year'],params['active_id'])
                    if data:
                        results=formatProperName(data)
                        params=formatPrimaryResults(results,params)
                    self.render(primary_page,**params)
            elif office in office_link_names:
                params['active']=office
                if year in all_amendment_text:
                    if office in all_amendment_text[year]:
                        params['amendment_text']=all_amendment_text[year][office]
                params['office']=office_id_key[office_link_key[office]]
                params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, " + params['office']
                data=Primary.by_year_by_office_id(params['year'],office_link_key[office])
                if data:
                    results=formatProperName(data)
                    params=formatPrimaryResults(results,params)
                self.render(primary_page,**params)
                # else:
                #     self.redirect('/primary/'+year)
            else:
                self.redirect('/primary/'+year)
        else:
            self.redirect('/primary')

class PrimaryYearUSHouseHandler(GenericHandler):
    def get(self,year,office):
        params=self.check_login("/primary/"+year+'/ushouse/'+office)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params['active']='ushouse'
            params=setPrimaryParams(params)
            params['districts']=p_ushouse_offices[params['year']]
            office_int=int(office)
            if office_int in p_ushouse_lists[params['year']]:
                params['active_id']=us_rep_id_key[office_int-1][0]
                params['district_id']=us_rep_id_key[office_int-1][1]
                params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, US House  " + params['district_id']
                data=Primary.by_year_by_office_id(params['year'],params['active_id'])
                if data:
                    results=formatProperName(data)
                    params=formatPrimaryResults(results,params)
                self.render(primary_page,**params)
                # else:
                #     self.redirect('/primary/'+year)
            else:
                self.redirect('/primary/'+year+'/ushouse')      
        else:
            self.redirect('/primary')

class PrimaryYearLegHandler(GenericHandler):
    def get(self,year,office,office_id):
        params=self.check_login("/primary/"+year+'/'+office+'/'+office_id)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if year in election_years:
            params['year']=year
            params['active']=office
            params=setPrimaryParams(params) 
            if office=='senate':
                params['active']='senate'
                params['office']='State Senate'
            else:
                params['active']='house'
                params['office']='State House'
            params['districts']=Primary.get_offices_by_other_office(params['year'],params['active'])
            data=None
            for d in params['districts']:
                if d[1] == office_id:
                    params['district_id']=office_id
                    params['active_id']=getOfficeCodefromDistrict(office_id)
                    params['title']="MN Elections Info | " + params['year'] + " Primary Elections Results, " + params['office'] + " " + params['district_id']
                    data=Primary.by_year_by_office_id(params['year'],params['active_id'])
                    break
            if data!=None:
                results=formatProperName(data)
                params=formatPrimaryResults(results,params)
                self.render(primary_page,**params)
            else:
                self.redirect('/primary/'+year+'/'+office)
        else:
            self.redirect('/primary')

class GraphPageHandler(GenericHandler):
    def get(self):
        params=self.check_login("/graph")
        params['title']="MN Elections Info | General Elections Graph, President, vote %"
        params['description']=default_meta_description
        style=self.request.get("style")
        office=self.request.get("office")
        params['office']='president'
        params['style']='percent'
        params['ushouse_dist_id']='0'
        params['senate_dist_id']='0'
        params['house_dist_id']='0'
        params['senate_range']=state_leg_ranges['senate']
        params['house_range']=state_leg_ranges['house']
        params['graph_title']=office_id_key[office_link_key[params['office']]] + ', ' + graph_page_style_names[params['style']]
        data=Results.by_office_id(office_link_key[params['office']])
        if data:
            params['ip_present'],params['results']=formatChartOfficeData(data,params['style'])
        self.render(graph_page,**params)

class CustomGraphPageHandler(GenericHandler):
    def get(self): 
        params=self.check_login("/graph")
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        style=self.request.get("style")
        office=self.request.get("office")
        params['ushouse_dist_id']=self.request.get("ushouse")
        params['senate_dist_id']=self.request.get("senate")
        params['house_dist_id']=self.request.get("house")
        if style!=None and (style != 'raw' and style != 'percent'):
            params['style']='percent'
        else:
            params['style']=style
        params['senate_range']=state_leg_ranges['senate']
        params['house_range']=state_leg_ranges['house']
        if office in office_link_names:
            params['office']=office
            params['graph_title']=office_id_key[office_link_key[params['office']]] + ', ' + graph_page_style_names[params['style']]
            params['title']="MN Elections Info | General Elections Graph, " + office_id_key[office_link_key[params['office']]] + ', ' + graph_page_style_names[params['style']]
            data=Results.by_office_id(office_link_key[params['office']])
            if data:
                params['ip_present'],params['results']=formatChartOfficeData(data,style)
                self.render(graph_page,**params)
        elif office=='ushouse':
            params['office']=office
            dist_id=self.request.get("ushouse")
            if dist_id.isdigit():
                dist_num=int(dist_id)
                if dist_num>0 and dist_num<9:
                    params['ushouse_dist_id']=dist_id
                    params['graph_title']='US House ' + dist_id + ', ' + graph_page_style_names[params['style']]
                    params['title']="MN Elections Info | General Elections Graph, " + 'US House ' + dist_id + ', ' + graph_page_style_names[params['style']]
                    data=Results.by_office_id(us_rep_id_key[dist_num-1][0])
                    if data:
                        params['ip_present'],params['results']=formatChartOfficeData(data,style)
                        self.render(graph_page,**params)
                else:
                    self.redirect('/graph')
            else:
                self.redirect('/graph')
        elif office=='senate':
            params['office']=office
            dist_id=self.request.get("senate")
            if dist_id.isdigit():
                dist_num=int(dist_id)
                if dist_num>0 and dist_num<68:
                    params['senate_dist_id']=dist_id
                    params['graph_title']='State Senate ' + dist_id + ', ' + graph_page_style_names[params['style']]
                    params['title']="MN Elections Info | General Elections Graph, " + 'State Senate ' + dist_id + ', ' + graph_page_style_names[params['style']]
                    data=Results.by_office_id('0'+str(dist_num+120))
                    if data:
                        params['ip_present'],params['results']=formatChartOfficeData(data,params['style'])
                        self.render(graph_page,**params)
                else:
                    self.redirect('/graph')
            else:
                self.redirect('/graph')
        elif office=='house':
            params['office']=office
            dist_id=self.request.get("house")
            try:
                n=int(dist_id[:-1])*2
                if n<135 and n>0:
                    if dist_id.find('B') == -1 and dist_id.find('A') > 0:
                        n-=1
                    dist_num=n
                    params['house_dist_id']=str(n)
                    params['graph_title']='State House ' + dist_id + ', ' + graph_page_style_names[params['style']]
                    params['title']="MN Elections Info | General Elections Graph, " + 'State House ' + dist_id + ', ' + graph_page_style_names[params['style']]
                    data=Results.by_office_id('0'+str(dist_num+187))
                    if data:
                        params['ip_present'],params['results']=formatChartOfficeData(data,style)
                        self.render(graph_page,**params)
                else:
                    self.redirect('/graph')
            except:
                self.redirect('/graph')
        else:
            self.redirect('/graph')

class MapsPageHandler(GenericHandler):
    def get(self): 
        params=self.check_login('/maps')
        params['title']="MN Elections Info | District Maps, US House"
        params['description']=default_meta_description
        params['range']=range(1,9)
        params['district_map']='ushouse'
        params['office']="US House"
        self.render(maps_ushouse_district_page,**params)

class MapsChamberPageHandler(GenericHandler):
    def get(self,chamber): 
        params=self.check_login('/maps/'+chamber)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        if chamber=='ushouse':
            params['district_map']=chamber
            params['range']=range(1,9)
            params['office']="US House"
            params['districts']=[]
            params['title']="MN Elections Info | District Maps, US House"
            self.render(maps_ushouse_district_page,**params)
            # k = getAWSKey('output/maps/'+chamber)
            # k.set_contents_from_string(render_str(maps_ushouse_district_page, **params))
            # k.set_acl('public-read')
            # self.write(k.get_contents_as_string())
        else:
            params['district_map']=chamber
            page=get_contents_of_url(aws_output+'maps/'+chamber+'_map')
            if page:
                self.write(page)
            else:
                params['office']="State " + chamber.title()
                if chamber=='house':
                    params['range']=range(1,135)
                else:
                    params['range']=range(1,68)
                params['title']="MN Elections Info | District Maps, " + params['office']
                params['districts']=getAllMNLegDistrictShapesbyChamber(getChamberName(chamber))
                k = getAWSKey('output/maps/'+chamber+'_map')
                k.set_contents_from_string(render_str(maps_page, **params))
                k.set_acl('public-read')
                self.write(k.get_contents_as_string())

class MapsChamberDistrictPageHandler(GenericHandler):
    def get(self,chamber,dist_id): 
        params=self.check_login('/maps/'+chamber+'/'+dist_id)
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        params['district_map']=chamber
        if chamber=='ushouse':
            params['range']=range(1,9)
            params['office']="US House"
            try:
                params['dist_num']=int(dist_id)
                if params['dist_num']<9 and params['dist_num']>0:
                    params['demo'],params['demo_url']=fetchDistrictDemoData('0'+str(params['dist_num']),'ushouse')
                    params['district']=dist_id
                    params['data']=[]
                    params['title']="MN Elections Info | District Maps, US House " + dist_id
                    #self.write('0'+str(params['dist_num']))
                    self.render(maps_ushouse_district_page,**params)
                else:
                    self.redirect('/maps/'+chamber)
            except:
                self.redirect('/maps/'+chamber)
        else:
            params['office']="State " + chamber.title()
            if chamber=='senate':
                if dist_id.isdigit():
                    params['dist_num']=int(dist_id)
                    if params['dist_num']<68 and params['dist_num']>0:
                        params['range']=range(1,68)
                        params['title']="MN Elections Info | District Maps, " + params['office'] + " " + dist_id
                        params['district']=getMNLegDistrictShape(getChamberName(chamber),dist_id)
                        data=Results.by_year_by_office_id('2012','0'+str(params['dist_num']+120))
                        if data:
                            results=formatProperName(data)
                            params['data']=results
                        self.render(maps_district_page,**params)
                    else:
                        self.redirect('/maps/'+chamber)
                else:
                    self.redirect('/maps/'+chamber)
            else:
                try:
                    n=int(dist_id[:-1])*2
                    if n<135 and n>0:
                        if dist_id.find('B') == -1 and dist_id.find('A') > 0:
                            n-=1
                        params['dist_num']=n
                        params['range']=range(1,135)
                        params['title']="MN Elections Info | District Maps, " + params['office'] + " " + dist_id
                        params['district']=getMNLegDistrictShape(getChamberName(chamber),dist_id)
                        data=Results.by_year_by_office_id('2012','0'+str(params['dist_num']+187))
                        if data:
                            results=formatProperName(data)
                            params['data']=results
                        self.render(maps_district_page,**params)
                    else:
                        self.redirect('/graph')
                except:
                    self.redirect('/graph')

class BubblePageHandler(GenericHandler):
    def get(self):
        params=self.check_login('/bubble')
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        self.render(cong_bubble,**params)  

# def getFECDataForDisplay(district):
#     data=getFECData(ushouse_district_names[district])
#     for d in data:
#         results={
#             'name':data[d]['cand_nm'],
#             'party':data[d]['party'],
#             'description':data[d]['description'],
#             'copyright':data[d]['copyright'],
#             #'candidate_id':data[d]['cand_id'],
#             'money':{
#                 'Total Individual':data[d]['summary']['Total Individual Contributions'],
#                 'Party Committees':data[d]['summary']['Party Committees Contributions'],
#                 'Other Committees':data[d]['summary']['Other Committees Contributions'],
#                 'Candidates':data[d]['summary']['Candidate Contributions'],
#                 'Total Contributions':data[d]['summary']['TOTAL CONTRIBUTIONS'],
#                 'Total Loans':data[d]['summary']['TOTAL LOANS'],
#                 'Total Receipts':data[d]['summary']['TOTAL RECEIPTS'],

#             },
#         }
#         return results

def getFECSummeryDataForDisplay(district):
    data=getFECData(district)
    for d in data:
        first=data[d]['cand_nm'][data[d]['cand_nm'].find(',')+2:].split()
        name = first[0] + ' ' + data[d]['cand_nm'][:data[d]['cand_nm'].find(',')]
        results={
            'name':name.title(),
            'party':data[d]['party'],
            'description':data[d]['description'],
            'copyright':data[d]['copyright'],
            #'candidate_id':data[d]['cand_id'],
            'money':{
                'Beginning Cash On Hand':int(data[d]['summary']['Beginning Cash On Hand'][1:-3].replace(',', '')),
                'Ending Cash On Hand':int(data[d]['summary']['Ending Cash On Hand'][1:-3].replace(',', '')),
                'Net Contributions':int(data[d]['summary']['Net Contributions'][1:-3].replace(',', '')),
                'Net Operating Expenditures':int(data[d]['summary']['Net Operating Expenditures'][1:-3].replace(',', '')),
                'Debts/Loans Owed By':int(data[d]['summary']['Debts/Loans Owed By'][1:-3].replace(',', '')),
                'Debts/Loans Owed To':int(data[d]['summary']['Debts/Loans Owed To'][1:-3].replace(',', '')),
            },
        }
        return results

class MemberPageHandler(GenericHandler):
    def get(self):
        params=self.check_login('/member')
        params['title']="MN Elections Info"
        params['description']=default_meta_description
        r=range(1,9)
        params['data']=[]
        for d in r:
            params['district']=str(d)
            params['data'].append(getFECSummeryDataForDisplay(ushouse_district_names[params['district']]))
        #self.write(params['data'])
        self.render(cong_money,**params)

class ParseResultsHandler(GenericHandler):
    def get(self,year):
        params=self.check_login("/parse/results/"+year)
        all_results=[]
        if year in results_links:
            for l in results_links[year]:
                results=fetchElectionResults(l)
                if results:
                    addResultsToParse(year,results)
            self.redirect('/')
        else:
            self.redirect('/history')

class ParsePrimaryHandler(GenericHandler):
    def get(self,year):
        params=self.check_login("/parse/primary/"+year)
        all_results=[]
        if year in p_results_links:
            for l in p_results_links[year]:
                results=fetchElectionResults(l)
                if results:
                    addPrimaryToParse(year,results)
            self.redirect('/')
        else:
            self.redirect('/history')

class ParseCountyHandler(GenericHandler):
	def get(self,year):
		params=self.check_login("/parse/county/"+year)
		if year in county_links:
			results=fetchElectionResults(county_links[year])
			if results:
				addCountiesToParse(year,results)
				self.write('data added')
			else:
				self.write('no data')

class ParsePrecinctTableHandler(GenericHandler):
	def get(self,year):
		params=self.check_login("/parse/precincttable/"+year)
		if year in precinct_table_links:
			results=fetchPrecinctTable(precinct_table_links[year])
			if results:
				addPrecinctTableToParse(year,results)
				self.write('data added')
			else:
				self.write('no data')

class AboutPageHandler(GenericHandler):
    def get(self):
        params=self.check_login('/about')
        params['title']="MN Elections Info | About the Minnesota Elections Info site"
        params['description']=default_meta_description
        self.render(about_page,**params)  

class FeedbackPageHandler(GenericHandler):
    def get(self):
        params=self.check_login('/feedback')
        params['title']="MN Elections Info | Send us your feedback"
        params['description']=default_meta_description
        self.render(feedback_page,**params)  

class FeedbackResponsePageHandler(GenericHandler):
    def get(self):
        params=self.check_login('/feedback-response')
        params['title']="MN Elections Info | Thanks for your feedback!"
        params['description']=default_meta_description
        self.render(feedback_response_page,**params)  

class NotFoundPageHandler(GenericHandler):
    def get(self):
        params=self.check_login('404')
        params['title']="MN Elections Info | 404 Error, page not found"
        params['description']=default_meta_description
        self.error(404)
        #self.response.out.write('<Your 404 error html page>')
        self.render(e404_page,**params)	  

class AWSMainHandler(GenericHandler):
    def get(self):
        params=self.check_login("/aws")
        c=connectToAWS()
        if c:
            self.write('<b>Connected</b><br><br>')
            buckets=c.get_all_buckets()
            self.write('Searching AWS Buckets...<br>')
            for b in buckets:
                if b.name=='mnelections':
                    self.write('Found "'+b.name+'" bucket!')
        else:
            self.write('<b>Not connected</b>')

default_meta_description="""The Minnesota Elections Info site contains; General and Primary elections results from 2000-2012, Maps and Demographic Info of every Congressional and Legislative district and more."""  	

app = webapp2.WSGIApplication([
    ('/?', MainHandler),
    #('/parse/results/([0-9]+)/?', ParseResultsHandler),
    #('/parse/primary/([0-9]+)/?', ParsePrimaryHandler),
    #('/parse/county/([0-9]+)/?', ParseCountyHandler),
    #('/parse/precincttable/([0-9]+)/?', ParsePrecinctTableHandler),
    ('/history/?', HistoryHandler),
    ('/history/([0-9]+)/?', HistoryYearHandler),
    ('/general/?', StatewideHandler),
    ('/general/([0-9]+)/?', StatewideYearHandler),
    ('/general/([0-9]+)/([A-Za-z0-9]+)?/?', StatewideYearOfficeHandler),
    ('/general/([0-9]+)/ushouse/([0-9])/?', StatewideYearUSHouseHandler),
    ('/general/([0-9]+)/(house|senate)/([0-9]+[A|B]?)/?', StatewideYearLegHandler),
    ('/primary/?', PrimaryHandler),
    ('/primary/([0-9]+)/?', PrimaryYearHandler),
    ('/primary/([0-9]+)/([A-Za-z0-9]+)?/?', PrimaryYearOfficeHandler),
    ('/primary/([0-9]+)/ushouse/([0-9])/?', PrimaryYearUSHouseHandler),
    ('/primary/([0-9]+)/(house|senate)/([0-9]+[A|B]?)/?', PrimaryYearLegHandler),
    ('/graph/?', GraphPageHandler),
    ('/graph/c', CustomGraphPageHandler),
    ('/maps/?', MapsPageHandler),
    ('/maps/(ushouse|house|senate)/?', MapsChamberPageHandler),
    ('/maps/(ushouse|house|senate)/([0-9][0-9]?[A|B]?)/?', MapsChamberDistrictPageHandler),
    # ('/bubble/?', BubblePageHandler),
    # ('/member/?', MemberPageHandler),
    ('/about/?', AboutPageHandler),
    ('/feedback/?', FeedbackPageHandler),
    ('/feedback-response/?', FeedbackResponsePageHandler),
    # ('/aws/?', AWSMainHandler),
    ('/.*', NotFoundPageHandler),
], debug=True)