'''
Various commonly used functions
'''
__author__ = 'Dorik1972'

from gevent import spawn_later

def schedule(delay, func, *args, **kw_args):
    '''
    Run a function at repeated intervals
    '''
    spawn_later(0, func, *args, **kw_args)
    spawn_later(delay, schedule, delay, func, *args, **kw_args)
