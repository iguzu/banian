from banian.models import Seat
from django import template

'''
Created on Sep 26, 2009

@author: install
'''

def availabilitystatus(object):
    '''
    filter that resolve the status of a seat
    '''
    return Seat._status[object]
 
register = template.Library()
register.filter('availabilitystatus', availabilitystatus) 