from twarc import Twarc
import csv
import re
from fastai.text import *

import credentials
import unidecode

# find last_name of user
def last_name(name,pattern=r'(?<= )([A-z\-\']*)([ ,]+Jr\.?| III| II|[ ,]+M\.?D\.?|[ ,]+D\.?D\.?S\.?| \([A-z]*\)|\)*| Press| Office)*\Z'):
    name = unidecode.unidecode(name)
    if re.search(pattern,name):
        result = re.search(pattern,name).group(1)
    elif re.search(r'(?<=[a-z.])[A-Z][a-z]*(\Z|,)',name):
        result = re.search(r'(?<=[a-z.])[A-Z][a-z]*(\Z|,)',name).group(0)
        print(result)
    return result

t = Twarc(credentials.CONSUMER_KEY,credentials.CONSUMER_SECRET, credentials.ACCESS_TOKEN,credentials.ACCESS_TOKEN_SECRET)
USERS_PATH = Path('data/users/')
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