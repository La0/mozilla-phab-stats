import requests
from urllib.parse import urlencode
import json
import hashlib
import os
import re
import csv

CACHE = os.path.join(os.path.dirname(__file__), 'cache')
BASE_URL = 'https://phabricator.services.mozilla.com/api/'
TOKEN = os.environ['PHABRICATOR_TOKEN']
REGEX_TOTAL = re.compile(r'found (\d+) defects?')
REGEX_ANALYZER = re.compile(r'(\d+) defects? found by ([\w\-]+)')
FIELDS = ('revision', 'comment', 'created', 'clang-tidy', 'clang-format', 'infer', 'mozlint', 'total')



def request(method, **params):
    '''
    Make a request with cache management
    '''
    assert TOKEN.startswith('api-')
    assert isinstance(params, dict)
    url = BASE_URL + method
    params['__conduit__'] = {
        'token': TOKEN,
    }

    # Build request hash
    payload = url + json.dumps(params, sort_keys=True)
    h = hashlib.md5(payload.encode('utf-8')).hexdigest()
    cache = os.path.join(CACHE, '{}.json'.format(h))
    if os.path.exists(cache):
        return json.load(open(cache))

    # Make the request
    data = urlencode({
        'params': json.dumps(params),
        'output': 'json',
    })
    resp = requests.post(url, data=data)
    resp.raise_for_status()

    # Check reponse data
    data = json.loads(resp.content.decode('utf-8'))
    assert data['error_code'] is None, 'Invalid response: {}'.format(data['error_info'])

    # Save response in cache
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)

    with open(cache, 'wb') as f:
        f.write(resp.content)
        print('Saved {}'.format(cache))

    return data


def feed(user_phid):
    '''
    List all transactions for a user
    '''
    assert user_phid.startswith('PHID-USER')

    key = None
    while True:

        # Request transactions
        data = request('feed.query', filterPHIDs=[user_phid, ], after=key)

        results = data['result']
        if not results:
            break
        results = sorted(results.values(), key=lambda x: x['chronologicalKey'])

        for story in results:
            yield story['data']

        # Next page
        key = results[0]['chronologicalKey']

def comments(object_phid, author_phid):
    '''
    Get all comments for an object, from a specific author
    '''

    after = None
    while True:

        data = request('transaction.search', objectIdentifier=object_phid, after=after)
        results = data['result']['data']
        if not results:
            break
        transactions = filter(lambda x: x['type'] == 'comment' and x['authorPHID'] == author_phid, results)

        for tr in transactions:
            for comment in tr['comments']:
                yield comment

        # next page ?
        after = data['result']['cursor']['after']
        if after is None:
            break

def parse_comment(comment):
    '''
    Extract stats from a code review comment
    '''
    total = REGEX_TOTAL.search(comment)
    assert total is not None, 'Parser failure: {}'.format(comment)

    out = {
        name: int(nb)
        for nb, name in REGEX_ANALYZER.findall(comment)
    }
    out['total'] = int(total.group(1))

    return out


if __name__ == '__main__':
    bot = 'PHID-USER-cje4weq32o3xyuegalpj'

    # Get all distinct objects
    objects = {
        transaction['objectPHID']
        for transaction in feed(bot)
    }
    print('Got {} phabricator objects to analyze'.format(len(objects)))

    # Setup csv output
    writer = csv.DictWriter(open('stats.csv', 'w'), fieldnames=FIELDS)
    writer.writeheader()

    # List comments for each object
    for obj_phid in objects:
        for comment in comments(obj_phid, bot):
            item = {
                'revision': obj_phid,
                'created': comment['dateCreated'],
                'comment': comment['id']
            }
            item.update(parse_comment(comment['content']['raw']))
            writer.writerow(item)

    print('All done.')
