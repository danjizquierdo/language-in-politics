import requests
import pandas as pd
import numpy as np
import json
import re
import time
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from py2neo import Graph, Node, Relationship

import credentials

def get_bill_ids(limit=76,target='https://www.congress.gov/quick-search/legislation?wordsPhrases=&wordVariants=on&congresses%5B0%5D=115&legislationNumbers=&legislativeAction=&sponsor=on&representative=&senator=&searchResultViewType=expanded&pageSize=250&page='):
	# Scrape the bill ids from congress.gov
	bill_ids=[]
	amdt_ids=[]
	for page in range(1,limit):
		page = requests.get(target+str(page))
		soup =BeautifulSoup(page.content,'html.parser')
		results = soup.find_all('span','result-heading')
		for result in results:
			bill_id = result.find('a').get_text()
			if 'Amdt' in bill_id and bill_id not in amdt_ids:
				amdt_ids.append(bill_id)
			elif bill_id not in bill_ids:
				bill_ids.append(bill_id)
	return bill_ids, amdt_ids

def populate_bills(bill_ids,amdt_ids,graph=Graph("bolt://localhost:7687", auth=("Admin", "P@ssw0rd")),key=credentials.XAPIKey,target='https://api.propublica.org/congress/v1/115/bills/'):

	# Scrape bills with their committees and link them to their sponsors in the graph
	params = {'X-API-Key': key}
	errors=[]
	for bill in bill_ids:
		if bill not in amdt_ids:
			response=requests.get(target+bill.lower().replace('.','')+'.json',headers=params)
			text = json.loads(response.text)
			if text['status']=='OK':
				try:
					# Bill results
					results = text['results'][0]
					b_params = {'slug': results['bill_slug'],
								'source': results['bill_type'],
								'title': results['short_title'],
								'url': results['congressdotgov_url'],
								'introduced': results['introduced_date'],
								'subject': results['primary_subject'],
								'committees': results['committees'],
								'summary': results['summary'],
								'house_vote': results['house_passage_vote'],
								'senate_vote': results['senate_passage_vote'],
								'enacted': results['enacted'],
								'vetoed': results['vetoed'],
								'cosponsors': results['cosponsors'],
								'active': results['active'],
								'withdrawn': results['withdrawn_cosponsors']
							   }

					b_query='''
					MERGE (b:Bill { id:$slug, chamber:$source, title:$title,
									url:$url, introduced:$introduced, subject:$subject,
									summary:$summary, cosponsors:$cosponsors, active:$active, 
									withdrawn_cosponsors:$withdrawn })
					SET b.committees = $committees, b.vetoed=$vetoed, b.house_vote=$house_vote,
								b.senate_vote=$senate_vote, b.enacted=$enacted
					'''
					graph.run(b_query,b_params)
				except:
					errors.append((bill,'bill'))
					print(f'Something went wrong with Bill {bill}')

				# Sponsor results
				try:
					if results['sponsor_title']=='Rep.':
						source = 'hr'
					elif results['sponsor_title']=='Sen.':
						source= 's'
					s_params = { 'name': results['sponsor'],
								'source': source,
								'party': results['sponsor_party'],
								'state': results['sponsor_state'],
								'bill': results['bill_slug']
							   }
					s_query='''
					MERGE (r:Rep { name:$name, chamber:$source, party:$party, state:$state })
					WITH r
					MATCH (b:Bill { id:$bill })
					WITH r, b
					MERGE (r)-[:SPONSORS]->(b)
					'''
					graph.run(s_query,s_params)
				except:
					errors.append((bill,'sponsor'))
					print(f'Something went wrong with the Sponsor of Bill {bill}')

				# Commitee results
				try:
					codes = results['committee_codes']
					for code in codes:
						c_params = {
							'bill': results['bill_slug'],
							'id': code
						}
						c_query = '''
						MERGE (c:Com { id:$id })
						WITH c
						MATCH (b:Bill { id:$bill })
						WITH c, b 
						MERGE (b)-[:REFERS]->(c)
						'''
						graph.run(c_query,c_params)
				except:
					errors.append((bill,'com'))
					print(f'Something went wrong with the Committee of Bill {bill}')
				print('Another one in the graph!')
			else:
				errors.append((bill,'request'))
				print(f'Oops! Gotta grab {bill} later, maybe.')
	return errors

def write_bills(bill_ids,amdt_ids, graph = Graph("bolt://localhost:7687", auth=("Admin", "P@ssw0rd"))):

	# Scraper for bill text
	for count,bill in enumerate(bill_ids):
		if bill not in amdt_ids:
			try:
				bill=bill.lower().replace('.','')
				if bill[0]=='h':
					congress='house'
				elif bill[0]=='s':
					congress='senate'
				bill_id=re.search(r'(?<=[A-z])\d+',bill).group(0)	
				if 'con' in bill:
					bill_type='con'
					page = requests.get(f'https://www.congress.gov/bill/115th-congress/{congress}-concurrent-bill/{bill_id}/text?format=txt')	
				elif 'j' in bill:
					bill_type='joint'
					page = requests.get(f'https://www.congress.gov/bill/115th-congress/{congress}-joint-resolution/{bill_id}/text?format=txt')
				else:  
					page = requests.get(f'https://www.congress.gov/bill/115th-congress/{congress}-bill/{bill_id}/text?format=txt')
				soup =BeautifulSoup(page.content,'html.parser')
				result = soup.find(id='billTextContainer').string
				text = re.sub(r'(\[.*\])|(\((\w+|\s|\.|\;)\)*)|\n|\<.*\>',' ',result)
				text = re.sub(r'\s{2,}|\-+|\`+',' ',text)
				param = {
					'slug': bill,
					'text': text
				}
				if bill_type == 'con':
					query='''
					MATCH (b:Bill:ConRes)
					WHERE b.id = $slug
					SET b.text = $text
					'''
					graph.run(query,param)
				elif bill_type == 'joint':
					query='''
					MATCH (b:Bill:JointRes)
					WHERE b.id = $slug
					SET b.text = $text
					'''
					graph.run(query,param)
				else:
					query='''
					MATCH (b:Bill)
					WHERE b.id = $slug
					SET b.text = $text
					'''
					graph.run(query,param)

				if count%1000==0:
					time.sleep(2)
					print(f'{count} and counting!')
			except:
				errors_text.append(bill)
				print(f'Ruh-roh, better go back and get {bill}')
	sum_query = '''
	MATCH (b:Bill)
	WHERE NOT EXISTS(b.text)
	SET b.text=b.summary
	'''
	graph.run(sum_query)
	return(errors_text)

def collect_votes(rootdir='/Users/flatironschool/congress/congress/data/115/votes/'):
	import os
	graph = Graph("bolt://localhost:7687", auth=("neo4j", "P@ssw0rd"))
	# helper function to convert strings to floats
	# credit: https://stackoverflow.com/questions/1806278/convert-fraction-to-float
	def convert_to_float(frac_str):
		try:
			return float(frac_str)
		except ValueError:
			try:
				num, denom = frac_str.split('/')
			except ValueError:
				return None
			try:
				leading, num = num.split(' ')
			except ValueError:
				return float(num) / float(denom)        
			if float(leading) < 0:
				sign_mult = -1
			else:
				sign_mult = 1
			return float(leading) + sign_mult * (float(num) / float(denom))

	# loop through files taken from 
	# https://github.com/unitedstates/congress/wiki/votes for vote info
	# create vote relationship with cypher query and add voted on params to Bill
	count=0
	for subdir, dirs, files in os.walk(rootdir):
		for file in files:
			count+=1
			if file[-5:]=='.json':
				with open(subdir+'/'+file,'r') as f:
					vote = json.loads(f.read())
					if 'bill' in vote.keys() and 'passage' in vote['category']:
						par = {}
						par['bill'] = vote['bill']['type']+str(vote['bill']['number'])
						par['requires'] = convert_to_float(vote['requires'])
						print(par['bill'])
						par['house']=vote['chamber']	
						house = par['house']
						if vote['result']=='Passed':
							par['result']= 1
							if 'res' in par['bill'] and 'con' not in par['bill']:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.result=$result,b.requires=$requires
								'''
								graph.run(r_query,par)
							else:
								if par['house']=='h':
									r_query = '''
									MATCH (b:Bill {id:$bill})
									SET b.h_result=$result,b.requires=$requires
									'''
									graph.run(r_query,par)
								elif par['house']=='s':
									r_query = '''
									MATCH (b:Bill {id:$bill})
									SET b.s_result=$result,b.requires=$requires
									'''
									graph.run(r_query,par)
							print(f'{house} passed.')
						else:
							par['result']=0
							if 'res' in par['bill'] and 'con' not in par['bill']:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.result=$result,b.requires=$requires
								'''
								graph.run(r_query,par)
							if par['house']=='h':
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.h_result=$result,b.requires=$requires
								'''
								graph.run(r_query,par)
							elif par['house']=='s':
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.s_result=$result,b.requires=$requires
								'''
								graph.run(r_query,par)
							print(f'{house} failed.')
						# for key in vote['votes'].keys():
						#     if key == 'Nay' or key =='No':
						#         nays=[]
						#         for rep in vote['votes'][key]:  
						#             if isinstance(rep,dict):
						#                 name = unidecode.unidecode(rep['display_name']) 
						#                 name = re.search(r'([A-z\'\-]*)',name).group(1)
						#                 nays.append( {  'surname':name,
						#                                 'party':rep['party'],
						#                                 'state':rep['state'] } ) 
						#         par['nays']=nays
						#         n_query = '''
						#         MATCH( b:Bill { id:$bill })
						#         WITH b
						#         UNWIND $nays as nay
						#         MERGE (n:Rep { party:nay.party, state:nay.state, surname:nay.surname })
						#         WITH n, b
						#         MERGE (n)-[v:VOTES]->(b)
						#         SET v.vote=-1
						#         '''
						#         graph.run(n_query,par)
						#     elif key == 'Present':                          
						#         ehs=[]
						#         for rep in vote['votes'][key]:
						#             if isinstance(rep,dict):
						#                 name = unidecode.unidecode(rep['display_name']) 
						#                 name = re.search(r'([A-z\'\-]*)',name).group(1)                                 
						#                 ehs.append( {   'surname':name,
						#                                 'party':rep['party'],
						#                                 'state':rep['state'] } ) 
						#         par['ehs']=ehs
						#         n_query = '''
						#         MATCH( b:Bill { id:$bill })
						#         WITH b
						#         UNWIND $ehs as eh
						#         MERGE (n:Rep { party:eh.party, state:eh.state, surname:eh.surname })
						#         WITH n, b
						#         MERGE (n)-[v:VOTES]->(b)
						#         SET v.vote=0
						#         '''
						#         graph.run(n_query,par)
						#     elif key == 'Aye' or key =='Yes' or key == 'Yea':
					
						#         yays=[]
						#         for rep in vote['votes'][key]:
						#             if isinstance(rep,dict):
						#                 name = unidecode.unidecode(rep['display_name']) 
						#                 name = re.search(r'([A-z\'\-]*)',name).group(1)                             
						#                 yays.append( {  'surname':name,
						#                                 'party':rep['party'],
						#                                 'state':rep['state'] } ) 
						#         par['yays']=yays
						#         n_query = '''
						#         MATCH( b:Bill { id:$bill })
						#         WITH b
						#         UNWIND $yays as yay
						#         MERGE (n:Rep { party:yay.party, state:yay.state, surname:yay.surname })
						#         WITH n, b
						#         MERGE (n)-[v:VOTES]->(b)
						#         SET v.vote=1
						#         '''
						#         graph.run(n_query,par)
	print(count)
	tally_query = '''
	MATCH (b:Bill)
	WHERE EXISTS(b.house_vote) AND EXISTS(b.senate_vote)
	SET b.result = b.h_result * b.s_result
	'''
	graph.run(tally_query)

def collect_votes_bills(rootdir='/Users/flatironschool/congress/congress/data/115/bills/'):
	import os
	graph = Graph("bolt://localhost:7687", auth=("Admin", "P@ssw0rd"))
	# helper function to convert strings to floats
	# credit: https://stackoverflow.com/questions/1806278/convert-fraction-to-float
	def convert_to_float(frac_str):
		try:
			return float(frac_str)
		except ValueError:
			try:
				num, denom = frac_str.split('/')
			except ValueError:
				return None
			try:
				leading, num = num.split(' ')
			except ValueError:
				return float(num) / float(denom)        
			if float(leading) < 0:
				sign_mult = -1
			else:
				sign_mult = 1
			return float(leading) + sign_mult * (float(num) / float(denom))

	# loop through files taken from 
	# https://github.com/unitedstates/congress/wiki/votes for vote info
	# create vote relationship with cypher query and add voted on params to Bill
	count=0
	for subdir, dirs, files in os.walk(rootdir):
		for file in files:
			count+=1
			if file[-5:]=='.json':
				with open(subdir+'/'+file,'r') as f:
					vote = json.loads(f.read())
					bill = vote['bill_id'][:-4]
					par = {}
					par['bill']=bill
					print(par['bill'])

					if 'house_passage_result' in vote['history'].keys():
						par['house']='h'
						house = par['house']
						if vote['history']['house_passage_result']=='pass':
							par['result']= 1
							if 'res' in par['bill'] and 'con' not in par['bill']:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.result=$result
								'''
								graph.run(r_query,par)
							else:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.h_result=$result
								'''
								graph.run(r_query,par)
							print(f'{house} passed.')
						else:
							par['result']=0
							if 'res' in par['bill'] and 'con' not in par['bill']:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.result=$result
								'''
								graph.run(r_query,par)
							else:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.h_result=$result
								'''
								graph.run(r_query,par)
							print(f'{house} failed.')
					if 'senate_passage_result' in vote['history'].keys():
						par['house']='s'
						house = par['house']
						if vote['history']['senate_passage_result']=='pass':
							par['result']= 1
							if 'res' in par['bill'] and 'con' not in par['bill']:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.result=$result
								'''
								graph.run(r_query,par)
							else:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.s_result=$result
								'''
								graph.run(r_query,par)
							print(f'{house} passed.')
						else:
							par['result']=0
							if 'res' in par['bill'] and 'con' not in par['bill']:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.result=$result
								'''
								graph.run(r_query,par)
							else:
								r_query = '''
								MATCH (b:Bill {id:$bill})
								SET b.s_result=$result
								'''
								graph.run(r_query,par)
							print(f'{house} failed.')
						# for key in vote['votes'].keys():
						#     if key == 'Nay' or key =='No':
						#         nays=[]
						#         for rep in vote['votes'][key]:  
						#             if isinstance(rep,dict):
						#                 name = unidecode.unidecode(rep['display_name']) 
						#                 name = re.search(r'([A-z\'\-]*)',name).group(1)
						#                 nays.append( {  'surname':name,
						#                                 'party':rep['party'],
						#                                 'state':rep['state'] } ) 
						#         par['nays']=nays
						#         n_query = '''
						#         MATCH( b:Bill { id:$bill })
						#         WITH b
						#         UNWIND $nays as nay
						#         MERGE (n:Rep { party:nay.party, state:nay.state, surname:nay.surname })
						#         WITH n, b
						#         MERGE (n)-[v:VOTES]->(b)
						#         SET v.vote=-1
						#         '''
						#         graph.run(n_query,par)
						#     elif key == 'Present':                          
						#         ehs=[]
						#         for rep in vote['votes'][key]:
						#             if isinstance(rep,dict):
						#                 name = unidecode.unidecode(rep['display_name']) 
						#                 name = re.search(r'([A-z\'\-]*)',name).group(1)                                 
						#                 ehs.append( {   'surname':name,
						#                                 'party':rep['party'],
						#                                 'state':rep['state'] } ) 
						#         par['ehs']=ehs
						#         n_query = '''
						#         MATCH( b:Bill { id:$bill })
						#         WITH b
						#         UNWIND $ehs as eh
						#         MERGE (n:Rep { party:eh.party, state:eh.state, surname:eh.surname })
						#         WITH n, b
						#         MERGE (n)-[v:VOTES]->(b)
						#         SET v.vote=0
						#         '''
						#         graph.run(n_query,par)
						#     elif key == 'Aye' or key =='Yes' or key == 'Yea':
					
						#         yays=[]
						#         for rep in vote['votes'][key]:
						#             if isinstance(rep,dict):
						#                 name = unidecode.unidecode(rep['display_name']) 
						#                 name = re.search(r'([A-z\'\-]*)',name).group(1)                             
						#                 yays.append( {  'surname':name,
						#                                 'party':rep['party'],
						#                                 'state':rep['state'] } ) 
						#         par['yays']=yays
						#         n_query = '''
						#         MATCH( b:Bill { id:$bill })
						#         WITH b
						#         UNWIND $yays as yay
						#         MERGE (n:Rep { party:yay.party, state:yay.state, surname:yay.surname })
						#         WITH n, b
						#         MERGE (n)-[v:VOTES]->(b)
						#         SET v.vote=1
						#         '''
						#         graph.run(n_query,par)
	print(count)
	tally_query = '''
	MATCH (b:Bill)
	WHERE EXISTS(b.s_result) AND EXISTS(b.h_result)
	SET b.result = b.h_result * b.s_result
	'''
	graph.run(tally_query)

def write_surname(graph=Graph("bolt://localhost:7687", auth=("Admin", "P@ssw0rd"))):
	import unidecode
	ln_query='MATCH (r:Rep) RETURN r.name'
	names=graph.run(ln_query).to_data_frame()
	# helper function to find last name
	def last_name(name,pattern):
		print(name)
		print(pattern)
		name = unidecode.unidecode(name)
		return re.search(pattern,name).group(1)

	names['last_name']=names['r.name'].apply(last_name,pattern=r'(?<= )([A-z\-\']*)( Jr\.| III | II)?\Z')
	ln_write='MATCH (r:Rep {}) WHERE r.name=$name SET r.surname=$last_name'
	for name,surname in zip(names['r.name'],names['last_name']):
		par={'name':name,'last_name':surname}
		graph.run(ln_write,par)
	return names.head()

def get_df(graph=Graph("bolt://localhost:7687", auth=("Admin", "P@ssw0rd"))):
	# query for all bills
	t_query ='''
	MATCH (n:Bill)
	OPTIONAL MATCH p1 = (n)<-[s:COSPONSORS]-(r1:Rep {party: 'D'})
	WITH n, count(r1) as d_cosponsors
	OPTIONAL MATCH p2 = (n)<-[c:COSPONSORS]-(r2:Rep {party: 'R'})
	WITH n, d_cosponsors, count(r2) as r_cosponsors
	RETURN n.title as bill, n.chamber as chamber, n.subject as subject, n.committees as committees, d_cosponsors, r_cosponsors, n.withdrawn_cosponsors as withdrawn, n.text as text, n.requires as bar, n.result as target
	'''
	return graph.run(t_query).to_data_frame()

def get_df_votes(graph):
	# query for all bills with votes
	b_query ='''
	MATCH (n:Bill) 
	WHERE EXISTS(n.result) 
	OPTIONAL MATCH p1 = (n)<-[s:SPONSORS]-(r1:Rep {party: 'D'})
	WITH n, count(r1) as d_cosponsors
	OPTIONAL MATCH p2 = (n)<-[c:COSPONSORS]-(r2:Rep {party: 'R'})
	WITH n, d_cosponsors, count(r2) as r_cosponsors
	RETURN n.title as bill, n.subject as subject, n.chamber as chamber, n.committees as committees, d_cosponsors, r_cosponsors, n.text as text, n.requires as bar, n.result as target
	'''
	return graph.run(b_query).to_data_frame()

def prepare_bills(t_df):
	import spacy
	nlp = spacy.load("en_core_web_lg")

	t_df['target'].fillna(-1,inplace=True)
	t_df=t_df.drop('bar',axis=1)
	ch_df = pd.get_dummies(t_df['chamber'],drop_first=True)
	co_df = pd.get_dummies(t_df['committees'],drop_first=True)
	s_df = pd.get_dummies(t_df['subject'],drop_first=True)
	joined_df=pd.concat([t_df.drop(['subject','chamber','committees'],axis=1),ch_df,co_df,s_df],axis=1)

	try:
		for count,doc in enumerate(nlp.pipe(joined_df['text'], batch_size=100)):
			vector.append(doc.vector)
			if count%100==0:
				print(f'{count/100+1} batch done!')
	except:
		print('Whoops!')
		whoops=['REPLACE']*100
		vector.extend(whoops)
	v_df = pd.concat([joined_df.drop('text',axis=1),joined_df['vector'].apply(pd.Series)],axis=1).drop('vector',axis=1,inplace=True)
	target = v_df['target']
	data = v_df.drop(['target','bill'],axis=1)
	return data, target

