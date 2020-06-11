'''
Various commonly used functions
'''
__author__ = 'Dorik1972'

from gevent import spawn_later
from urllib3.packages.six.moves.urllib.parse import parse_qs

def schedule(delay, func, *args, **kw_args):
    '''
    Run a function at repeated intervals
    '''
    spawn_later(0, func, *args, **kw_args)
    spawn_later(delay, schedule, delay, func, *args, **kw_args)

def query_get(query, key, default=''):
    '''
    Helper for getting values from a pre-parsed query string
    '''
    return parse_qs(query).get(key, [default])[0]
