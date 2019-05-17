from twarc import Twarc
import re
from collections import Counter
from fastai.text import *
import html
import csv
import time
from py2neo import Graph, Node, Relationship
import unidecode

import credentials

def fixup(x):
	'''
	Taken from fast.ai Deep Learning Part 2: Lesson 10
	'''
	x = x.replace('#39;', "'").replace('amp;', '&').replace('#146;', "'").replace(
	    'nbsp;', ' ').replace('#36;', '$').replace('\\n', "\n").replace('quot;', "'").replace(
	    '<br />', "\n").replace('\\"', '"').replace('<unk>', 'u_n').replace(' @.@ ', '.').replace(
	    ' @-@ ', '-').replace('\\', ' \\ ')
	link = r'^(http:\/\/www\.|https:\/\/www\.|http:\/\/|https:\/\/)?[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]{2,5}(:[0-9]{1,5})?(\/.*)?$'
	x= re.sub(link,'',x)
	link = r'https:\/\/t\.co\/\w+|http:\/\/t\.co\/\w+'
	x=re.sub(link,'',x)	
	link = r'http\S+'
	x=re.sub(link,'',x)

	return x

def process_tweet(tweet):
	user = tweet['user']['screen_name']
	engage='0'
	try:
		if 'user_mentions' in tweet['entities'].keys():
			for mention in tweet['entities']['user_mentions']:
				if mention['screen_name'] in users and mention['screen_name'] != user:
					engage = mention['screen_name']
	except:
		print('Exception!')
	tweet_text = fixup(tweet['full_text'])
	update_doc(user,tweet_text,engage)

def update_doc(user,text,engage):
	with open(LM_PATH/str(user),'a+') as csvfile:
		writer = csv.writer(csvfile, delimiter='|')
		writer.writerow([user,text,engage])

def engage_discourse(TID_PATH = Path('data/tweets_ids/'), 
		LM_PATH = Path('data/tweets/'),
		USERS_PATH = Path('data/users/')):
	t = Twarc(credentials.CONSUMER_KEY,credentials.CONSUMER_SECRET, credentials.ACCESS_TOKEN,credentials.ACCESS_TOKEN_SECRET)
	chunksize = 24000

	users=[]
	for doc in (USERS_PATH).glob('*.*'):
		with open(doc) as csv_file:
			csv_reader = csv.reader(csv_file, delimiter=',')
			next(csv_reader)
			for row in csv_reader:
				users.append(row[0])
	print(f'{len(users)} users in the corpus.')
	for doc in (TID_PATH).glob('*.*'):
		start=time.time()
		for count,tweet in enumerate(t.hydrate(open(doc))):
			process_tweet(tweet)	
			if count%1000 ==0:
				print(f'{time.time()-start} seconds for {count} tweets.')
		print('Document done!')
	print('Files written!')

# find last_name of representative
def last_name(name,pattern=r'(?<= )([A-z\-\']*)([ ,]+Jr\.?| III| II|[ ,]+M\.?D\.?|[ ,]+D\.?D\.?S\.?| \([A-z]*\)|\)*| Press| Office)*\Z'):
    name = unidecode.unidecode(name)
    if re.search(pattern,name):
        result = re.search(pattern,name).group(1)
    elif re.search(r'(?<=[a-z.])[A-Z][a-z]*(\Z|,)',name):
        result = re.search(r'(?<=[a-z.])[A-Z][a-z]*(\Z|,)',name).group(0)
        print(result)
    return result

def overhear_conversation(graph=Graph("bolt://localhost:7687", auth=("neo4j", "P@ssw0rd")), USERS_PATH = Path('data/users/')):
	t = Twarc(credentials.CONSUMER_KEY,credentials.CONSUMER_SECRET, credentials.ACCESS_TOKEN,credentials.ACCESS_TOKEN_SECRET)
	user_ids=[]
	# loop through csvs of usernames and grab them
	for doc in (USERS_PATH).glob('*.*'):
	    with open(doc) as csv_file:
	        csv_reader = csv.reader(csv_file, delimiter=',')
	        next(csv_reader)
	        for row in csv_reader:
	            user_ids.append(row[1])

	# use twarc to call those usernames and grab their stats
	for user in t.user_lookup(user_ids):
	    with open(USERS_PATH/'user_stats.csv','a+') as csv_file:
	        writer = csv.writer(csv_file,delimiter='|')
	        writer.writerow([user['name'],user['screen_name'],user['followers_count'],user['statuses_count']])

	# loop through the stats and store them in the graph
	with open(USERS_PATH/'user_stats.csv','r') as file:
	    csv_reader = csv.reader(file, delimiter='|')
	    for row in csv_reader:
	        u_param = {
	            'surname': last_name(row[0]),
	            'user_name': row[1],
	            'follower_count': row[2],
	            'statuses_count': row[3]
	        }
	        print(u_param)
	        u_query = '''
	        MATCH (r:Rep {surname: $surname})
	        SET r.user_name=$user_name, r.followers=$follower_count, r.statuses=$statuses_count
	        '''
	        graph.run(u_query,u_param)


