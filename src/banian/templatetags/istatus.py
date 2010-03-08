from banian.models import Seat
from django import template

'''
Created on Sep 26, 2009

@author: install
'''
from banian.model_utils import get_currency_code, get_currency_symbol
import logging

def availabilitystatus(object):
    '''
    filter that resolve the status of a seat
    '''
    return Seat._status[object]
 
def priceformat(price,country):
    '''
    filter to format a price
    '''
    if price == 0:
        return 'Free'
    elif price == '':
            return ''
    else:
        return '%.2f %s' % (price,get_currency_symbol(country))

def amountformat(amount,country):
    '''
    filter to format a total amount
    '''
    if amount == '':
            return ''
    else:
        return '%.2f %s' % (amount,get_currency_symbol(country))
 
register = template.Library()
register.filter('availabilitystatus', availabilitystatus)
register.filter('priceformat', priceformat) 
register.filter('amountformat', amountformat) 