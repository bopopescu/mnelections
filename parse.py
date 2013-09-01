import parse_rest
import ConfigParser
#from elections import fetchElectionResults

config = ConfigParser.ConfigParser()
config.read(["etc/boto.cfg"])
i=config.get('Parse','APPLICATION_ID')
k=config.get('Parse','REST_API_KEY')

parse_rest.APPLICATION_ID = i
parse_rest.REST_API_KEY = k

class Precincts(parse_rest.Object):
    @classmethod
    def by_year(cls,year):
        year = Precincts.Query.all().eq(year=year)
        return year

    @classmethod
    def by_office_id(cls,office_id):
        office = Precincts.Query.all().eq(office_id=office_id)
        return office

class Counties(parse_rest.Object):
    @classmethod
    def by_year(cls,year):
        year = Counties.Query.all().eq(year=year)
        return year

    @classmethod
    def by_office_id(cls,office_id):
        office = Counties.Query.all().eq(office_id=office_id)
        return office

class Results(parse_rest.Object):
    @classmethod
    def by_year(cls,year):
        year = Results.Query.all().eq(year=year)
        return year

    @classmethod
    def by_office_id(cls,office_id):
        office = Results.Query.all().eq(office_id=office_id)
        return office

    @classmethod
    def by_year_by_office_id(cls,year,office_id):
        race = Results.Query.all().eq(year=year).eq(office_id=office_id)
        return race

class Primary(parse_rest.Object):
    @classmethod
    def by_year(cls,year):
        year = Primary.Query.all().eq(year=year)
        return year

    @classmethod
    def by_office_id(cls,office_id):
        office = Primary.Query.all().eq(office_id=office_id)
        return office

    @classmethod
    def by_year_by_office_id(cls,year,office_id):
        race = Primary.Query.all().eq(year=year).eq(office_id=office_id)
        return race

    @classmethod
    def get_offices_by_other_office(cls,year,office):
        data=[]
        past={}
        races = Primary.Query.all().eq(year=year).order_by('office_id').limit(500)
        for r in races:
            office_id=int(r.office_id)
            if office=='ushouse':
                if 104 <= office_id <= 111:
                    if r.office_id in past:
                        pass
                    else:
                        data.append((r.office_id,r.district_code))
                        past[r.office_id]=True
            
            elif office=='house':
                if 188 <= office_id <= 321:
                    if r.office_id in past:
                        pass
                    else:
                        data.append((r.office_id,r.district_code))
                        past[r.office_id]=True
            
            elif office=='senate':
                if 121 <= office_id <= 187:
                    if r.office_id in past:
                        pass
                    else:
                        data.append((r.office_id,r.district_code))
                        past[r.office_id]=True
        return data

class PrecinctTable(parse_rest.Object):
    @classmethod
    def get_row(cls,county_id,precinct):
        row = PrecinctTable.Query.all().eq(county_id=county_id).eq(precinct=precinct)
        return row

    @classmethod
    def get_cd(cls,county_id,precinct):
        cd = self.get_row(county_id,precinct)
        return cd[3]

    @classmethod
    def get_hd(cls,county_id,precinct):
        hd = self.get_row(county_id,precinct)
        return hd[4]

    @classmethod
    def get_sd(cls,county_id,precinct):
        sd = self.get_row(county_id,precinct)
        return sd[4][:1]


def getParseParams(year,d):
    params={'year': year,
            'county_id':d[0],
            'precinct_id':d[1],
            'office_id':d[2],
            'office_name':d[3],
            'district_code':d[4],
            'candidate_id':d[5],
            'candidate_name':d[6],
            'suffix':d[7],
            'incumbent_code':d[8],
            'party_id':d[9],
            'precincts_reporting':d[10],
            'total_precincts':d[11],
            'candidate_votes':d[12],
            'percent_votes':d[13],
            'total_votes':d[14],
            }
    return params

def addPrecinctTableToParse(year,data):
    for d in data:
        params={'year': year,
            'county_id':d[0],
            'precinct_id':d[1],
            'precinct_name':d[2],
            'cd':d[3],
            'hd':d[4],
            'county_comish':d[5],
            'judicial':d[6],
            'soil_water':d[7],
            'mcd_code':d[8],
            'school_dist':d[9],
            }
        pt=PrecinctTable(**params)
        pt.save()

def addPrecinctsToParse(year,data):
    for d in data:
        params=getParseParams(year,d)
        p=Precincts(**params)
        p.save()

def addCountiesToParse(year,data):
    for d in data:
        params=getParseParams(year,d)
        c=Counties(**params)
        c.save()

def addResultsToParse(year,data):
    for d in data:
        params=getParseParams(year,d)
        g=Results(**params)
        g.save()

def addPrimaryToParse(year,data):
    for d in data:
        params=getParseParams(year,d)
        # if int(params['office_id'])==250 and params['party_id']=="DFL":
        p=Primary(**params)
        p.save()