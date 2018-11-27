import requests
from urllib.parse import urlencode
import json
import hashlib
import os

CACHE = os.path.join(os.path.dirname(__file__), 'cache')
BASE_URL = 'https://phabricator.services.mozilla.com/api/'
TOKEN = os.environ['PHABRICATOR_TOKEN']



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
        print('Reuse {}'.format(cache))
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

    return data


def feed(user_phid):
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


if __name__ == '__main__':
    for transaction in feed('PHID-USER-cje4weq32o3xyuegalpj'):
        print(transaction['objectPHID'])

    print('All done.')
