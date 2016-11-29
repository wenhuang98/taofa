# -*- coding: utf-8 -*-
import sys  

reload(sys)  
sys.setdefaultencoding('utf8')

from flask import Flask
from flask import render_template
from flask import request
import json
import requests
import datetime

from elasticsearch import Elasticsearch
es = Elasticsearch()

index_name = 'cases'
type_name = 'case'
query_name = 'query_history'

def store_query(query):
  query['timestamp'] = datetime.datetime.now()
  del query['highlight']

  res = es.index(index=query_name, doc_type='query', body=query)
  return

def handle_digit(digitStr):
  if int(digitStr) < 10:
    return '0'+ digitStr
  else:
    return digitStr

def handle_pagination(data):
  data['maxPage'] = data['count']/20 + 1
  if data['count']%20 > 0:
    data['maxPage'] +=1

  data['paginationWidth'] = 550;


  if data['pageNumber'] <= 100:
    data['paginationWidth'] -= 70
  if data['pageNumber'] >= data['maxPage'] - 100:
    data['paginationWidth'] -= 50

  if data['pageNumber'] <= 10:
    data['paginationWidth'] -= 50
  if data['pageNumber'] >= data['maxPage'] - 10:
    data['paginationWidth'] -= 70



  data['pageOptions'] = [data['pageNumber']-100,data['pageNumber']-10]

  if data['pageNumber'] < 3:
    data['pageOptions'].extend(range(1,6))

  elif data['pageNumber'] > data['maxPage'] - 3:
    data['pageOptions'].extend(range(data['maxPage']-5,data['maxPage']+1))
  else:
    data['pageOptions'].extend(range(data['pageNumber']-2,data['pageNumber']+3))

  data['pageOptions'].extend([data['pageNumber']+10,data['pageNumber']+100])

  return data

def handle_should(key,arr):
  newShould = {"bool": {"should": [], "minimum_should_match": 1}}
  for item in arr:
    newCondition = {'match_phrase':{}}
    if item == '判例':
      newCondition['match_phrase']['long_case_id'] = item
    elif item == '高等法院台北本院':
      newCondition =  {
          "bool": {
            "must": [
              {
                "match_phrase": {
                  "court": "高等法院"
                }
              }
            ],
            "must_not": [
              {
                "match_phrase": {
                  "court": "臺中"
                }
              },
              {
                "match_phrase": {
                  "court": "臺南"
                }
              },
              {
                "match_phrase": {
                  "court": "高雄"
                }
              },
              {
                "match_phrase": {
                  "court": "花蓮"
                }
              },
              {
                "match_phrase": {
                  "court": "金門"
                }
              }
            ]
          }
        }  
    else:
      newCondition['match_phrase'][key] = item
    newShould['bool']['should'].append(newCondition)

  return newShould

def retrieve_results(response, analyzingCriteria):

  results = []

  for item in response:
    result = item['_source']
    result['id'] = item['_id']
    if 'highlight' in item:
      result['highlight'] = item['highlight']['content'][0]
    else:
      result['highlight'] = result['content'][:150]
    result['wordCount'] = len(unicode(result['content']))
    result['keywordCount'] = 0
    for criterion in analyzingCriteria:
      if 'content' in criterion:
        keyword = criterion.split('：')[1]
        result['keywordCount'] += result['content'].count(keyword)

    if 'citation_count' not in result:
      result['citation_count'] = 0

    result['month'] = int(result['date'].split('-')[1])
    result['day'] = int(result['date'].split('-')[2])

    if '判例' in result['long_case_id']:
      result['example'] = True
    else:
      result['example'] = False
    results.append(result)

  return results

def get_citations(caseId,sorting,pageNumber):

  if sorting == 'time':
    sortCondition = 'date'
  else:
    sortCondition = 'citation_count'

  payload = {

    "query":{
      "bool": {
        "must": [
          {
            "match_phrase": {
              "supreme_court_cases": caseId
            }
          }
        ]
      }   
    },
    "sort": [ {sortCondition : {"order" : "desc"}}],
    "from": (pageNumber-1)*20,
    "size": 20
  }

  r = requests.post('http://localhost:9200/%s/_search' % (index_name), data=json.dumps(payload))

  count = r.json()['hits']['total']
  results = retrieve_results(r.json()['hits']['hits'],[])
  
  return count, results
    

def get_results(analyzingCriteria, sorting, pageNumber,duration):

  if sorting == 'time':
    sortCondition = 'date'
  elif sorting == 'importance':
    sortCondition = 'citation_count'
  else:
    sortCondition = '_score'

  payload = {

    "query":{
      "bool": {
        "must": [],
        "must_not": []
      }   
    },
    "filter":{},
    "sort": [ {sortCondition : {"order" : "desc"}}],
    "highlight" : {
      "pre_tags" : ["<span class='highlight-text'>"],
      "post_tags" : ["</span class='highlight-text'>"],
        "fields" : {
            "content" : {"fragment_size" : 150}
        }
    },
    "from": (pageNumber-1)*20,
    "size": 20
  }

  if '-' in duration[0]:
    payload["filter"]["range"] = {
      "date": {}
    }
    startDateList = duration[0].split('-')
    startDateList[0] = str(int(startDateList[0])+1911)

    startDateList[1] = handle_digit(startDateList[1])
    startDateList[2] = handle_digit(startDateList[2])

    startDate = '-'.join(startDateList)

    #print startDate

    endDateList = duration[1].split('-')
    endDateList[0] = str(int(endDateList[0])+1911)

    endDateList[1] = handle_digit(endDateList[1])
    endDateList[2] = handle_digit(endDateList[2])

    endDate = '-'.join(endDateList)

    #print endDate

    payload["filter"]["range"]["date"]["gte"] = startDate
    payload["filter"]["range"]["date"]["lte"] = endDate
  else:    
    duration[0] = int(duration[0])

    duration[1] = int(duration[1])

    if duration[0] > 88 or duration[1] < 105:
      payload["filter"]["range"] = {
        "year": {}
      }
      if duration[0] > 88:
        payload["filter"]["range"]["year"]["gte"] = duration[0]
      if duration[1] < 105:
        payload["filter"]["range"]["year"]["lte"] = duration[1]

  courts = []
  categories = []

  for criterion in analyzingCriteria:
    
    newCondition = {'match_phrase':{}}
    if 'court' in criterion:
      courts.append(criterion.split('：')[1])
    elif 'category' in criterion:
      categories.append(criterion.split('：')[1])
    else:
      if criterion.split('：')[1][0] == '-':
        newCondition['match_phrase'][criterion.split('：')[0]] = criterion.split('：')[1][1:]
        payload['query']['bool']['must_not'].append(newCondition)
      else:
        newCondition['match_phrase'][criterion.split('：')[0]] = criterion.split('：')[1]
        payload['query']['bool']['must'].append(newCondition)

  if len(courts) > 0:
    newShould = handle_should('court',courts)
    payload['query']['bool']['must'].append(newShould)
  if len(categories) > 0:
    newShould = handle_should('category',categories)
    payload['query']['bool']['must'].append(newShould)

  #print repr(payload).decode("unicode-escape")

  r = requests.post('http://localhost:9200/%s/_search' % (index_name), data=json.dumps(payload))


  #print repr(r.json()).decode("unicode-escape")
  results = retrieve_results(r.json()['hits']['hits'], analyzingCriteria)
  
  store_query(payload)

  count = r.json()['hits']['total']
  return count, results



application = Flask(__name__)

@application.route('/judgement')
def judgement():

  data = {}

  data['noResult'] = False

  data['highlightPosition'] = request.args.get('highlight_position')

  if data['highlightPosition']:
    data['highlightPosition'] = int(data['highlightPosition'])
  else:
    data['highlightPosition'] = -1


  print data['highlightPosition']

  id = request.args.get('id')

  #criteria_url = '&'.join(request.url.split('&')[1:])

  data['criteria'] = request.args.getlist('criteria')

  criteria_url = ''

  for criteria in data['criteria']:
    criteria_url += '&criteria=' + criteria

  if id:
    r = requests.get('http://localhost:9200/%s/%s/%s' % (index_name, type_name, id))
    try:
      result = r.json()['_source']
    except:
      data['noResult'] = True
  else:
    case_id = request.args.get('case_id')
    court = request.args.get('court')
    typeQuery = request.args.get('type')
    #print case_id
    payload = {
      "query":{
        "bool": {
          "must": [
            {
              "match_phrase":{
                "case_id": case_id
              }
            },
            {
              "match_phrase":{
                "court": court
              }
            },
            {
              "match_phrase":{
                "type": typeQuery
              }
            }
          ]
        }   
      }
    }

    r = requests.post('http://localhost:9200/%s/_search' % (index_name), data=json.dumps(payload))

    count = r.json()['hits']['total']
    #print count
    #print repr(r.json()['hits']['hits'][0]['_source']).decode("unicode-escape")
    if count > 0:
      result = r.json()['hits']['hits'][0]['_source']
    else:
      data['noResult'] = True
      # send to db to record no result

  if not data['noResult']:

    result['content'] = result['content'].replace('\n','<div class="line"></div>')


    items = ['content','previous_trials','long_case_id','date','case_id','supreme_court_cases','reason','related_law']

    for item in items:
      if item in result:
        data[item] = result[item]
      else:
        data[item] = []

    for i in range(len(data['related_law'])):
      data['related_law'][i] = data['related_law'][i].replace(' ','第').replace('-','之')+'條'


    if len(data['supreme_court_cases']) > 0:
      data['has_supreme'] = True
    else:
      data['has_supreme'] = False

    if len(data['previous_trials']) > 0:
      data['has_previous'] = True
    else:
      data['has_previous'] = False

    data['display_supreme'] = []

    for trial in data['supreme_court_cases']:
      instance = {}
      instance['display'] = trial
      trialType = ''
      
      if '裁判' in trial:
        trialType = '判決'
      elif '判例' in trial:
        trialType = '判例'
      elif '裁定' in trial:
        trialType = '裁定'

      instance['link'] = trial.split(' ')[0] + '&court=最高法院&type=' + trialType +  criteria_url
      data['display_supreme'].append(instance)


    data['display_previous_trials'] = []

    for trial in data['previous_trials']:
      instance = {}
      instance['display'] = trial
      instance['link'] = trial.split(' ')[1].replace('年','年度').replace('字','字第')[:-2] + '&court=' + trial.split(' ')[0] + '&type=' + trial.split('號')[1] + criteria_url 
      data['display_previous_trials'].append(instance)

    if len(data['related_law']) > 0:
      data['has_related'] = True
    else:
      data['has_related'] = False

    for criteria in data['criteria']:
      if criteria.split('：')[0] == '全文':
        keyword = criteria.split('：')[1]
        data['content'] =data['content'].replace(keyword,'<span class="highlight-text">'+keyword+'</span>')


    #data['content'] = data['content'].replace('\n','<br>')

    #print repr(result).decode("unicode-escape")

    #print repr(r.json()['_source']['content']).decode("unicode-escape")

  return render_template('judgement.html',data=data)

@application.route('/citation')
def citation():
  data = {}

  data['caseId'] = request.args.get('id')

  data['pageNumber'] = request.args.get('page_number')  

  if not data['pageNumber']:
    data['pageNumber'] = 1
  
  data['pageNumber'] = int(data['pageNumber'])
  data['sorting'] = request.args.get('sorting')

  if not data['sorting']:
    data['sorting'] = 'importance'

  if data['sorting'] == 'time':
    data['sortByTime'] = True
  else:
    data['sortByTime'] = False

  data['count'], data['results'] = get_citations(data['caseId'],data['sorting'],data['pageNumber'])

  data = handle_pagination(data)
    
  return render_template('citation.html',data=data)

@application.route('/')
def index():


  data = {}

  data['count'] = 0
  data['hasCriteria'] = False

  data['criteria'] = request.args.getlist('criteria')

  data['pageNumber'] = request.args.get('page_number')

  if not data['pageNumber']:
    data['pageNumber'] = 1

  data['pageNumber'] = int(data['pageNumber'])

  data['sorting'] = request.args.get('sorting')

  if not data['sorting']:
    data['sorting'] = 'time'

  if data['sorting'] == 'time':
    data['sortByTime'] = True
  elif data['sorting'] == 'relevance':
    data['sortByRelevance'] = True


  data['startDate'] = request.args.get('start_date')

  if not data['startDate']:
    data['startDate'] = '88'

  data['startYear'] = int(data['startDate'].split('-')[0])

  data['endDate'] = request.args.get('end_date')

  if not data['endDate']:
    data['endDate'] = '105'

  data['endYear'] = int(data['endDate'].split('-')[0])

  #print data['endYear']

  replace_dict = {
    '全文': 'content',
    '法官': 'judges',
    '字號': 'case_id',
    '案由': 'reason',
    '律師': 'lawyers',
    '法條': 'related_law',
    '主文': 'main_result',
    '判決類型': 'category',
    '法院層級': 'court'
  }

  highLocations = ['台北本院','臺中分院','臺南分院','高雄分院','花蓮分院','金門分院']

  locations = ['台北','士林','新北','宜蘭','基隆','桃園','新竹','苗栗','臺中','彰化','南投','雲林','嘉義','臺南','高雄','花蓮','臺東','屏東','澎湖','金門','連江']

  otherLocations = ['智慧財產法院','高雄少年及家事法院']

  data['locations'] = []

  data['highLocations'] = highLocations

  data['otherLocations'] = otherLocations

  for i in range(len(locations)):
    if i > 0 and i%8 == 0:
      data['locations'].append('-')
    data['locations'].append(locations[i])

  data['analyzingCriteria'] = []

  for item in request.args.getlist('criteria'):
    for key in replace_dict:
      item = item.replace(key, replace_dict[key])
    data['analyzingCriteria'].append(item)


  duration = [data['startDate'], data['endDate']]

  if len(data['criteria']) > 0:
    data['count'], data['results'] = get_results(data['analyzingCriteria'],data['sorting'],data['pageNumber'],duration)
    data['hasCriteria'] = True

  #def handle_pagination(data):
  data = handle_pagination(data)

  return render_template('index.html',data=data)


if __name__ == "__main__":
    application.run(host='0.0.0.0')