# -*- coding: utf-8 -*-

#@PydevCodeAnalysisIgnore
## popo
import array
import time
import datetime
import gaepytz
import locale

country_info =    {'AU':{'country_name':'Australia','currency_code':'AUD','currency_symbol':u'A$'},
            'BR':{'country_name':'Brasil','currency_code':'BRL','currency_symbol':u'R$'},
            'CA':{'country_name':'Canada','currency_code':'CAD','currency_symbol':u'C$'},
            'CZ':{'country_name':'Czech Republic','currency_code':'CZK','currency_symbol':u'Kc'},
            'DK':{'country_name':'Denmark','currency_code':'DKK','currency_symbol':u'kr (DKK)'},
            'FR':{'country_name':'France','currency_code':'EUR','currency_symbol':u'€'},
            'AT':{'country_name':'Austria','currency_code':'EUR','currency_symbol':u'€'},
            'BE':{'country_name':'Belgium','currency_code':'EUR','currency_symbol':u'€'},
            'CY':{'country_name':'Cyprus','currency_code':'EUR','currency_symbol':u'€'},
            'FI':{'country_name':'Finland','currency_code':'EUR','currency_symbol':u'€'},
            'DE':{'country_name':'Germany','currency_code':'EUR','currency_symbol':u'€'},
            'GR':{'country_name':'Greece','currency_code':'EUR','currency_symbol':u'€'},
            'IE':{'country_name':'Ireland','currency_code':'EUR','currency_symbol':u'€'},
            'IT':{'country_name':'Italy','currency_code':'EUR','currency_symbol':u'€'},
            'LU':{'country_name':'Luxembourg','currency_code':'EUR','currency_symbol':u'€'},
            'MT':{'country_name':'Malta','currency_code':'EUR','currency_symbol':u'€'},
            'NL':{'country_name':'Netherlands','currency_code':'EUR','currency_symbol':u'€'},
            'AN':{'country_name':'Netherlands Antilles','currency_code':'EUR','currency_symbol':u'€'},
            'PT':{'country_name':'Portugal','currency_code':'EUR','currency_symbol':u'€'},
            'SK':{'country_name':'Slovakia','currency_code':'EUR','currency_symbol':u'€'},
            'SI':{'country_name':'Slovenia','currency_code':'EUR','currency_symbol':u'€'},
            'ES':{'country_name':'Spain','currency_code':'EUR','currency_symbol':u'€'},
            'MC':{'country_name':'Monaco','currency_code':'EUR','currency_symbol':u'€'},
            'AD':{'country_name':'Andorra','currency_code':'EUR','currency_symbol':u'€'},
            'SM':{'country_name':'San Marino','currency_code':'EUR','currency_symbol':u'€'},
            'GF':{'country_name':'French Guiana','currency_code':'EUR','currency_symbol':u'€'},
            'HK':{'country_name':'Hong Kong','currency_code':'HKD','currency_symbol':u'HK$'},
            'HU':{'country_name':'Hungary','currency_code':'HUF','currency_symbol':u'Ft'},
            'IL':{'country_name':'Israel','currency_code':'ILS','currency_symbol':u'NIS'},
            'JP':{'country_name':'Japan','currency_code':'JPY','currency_symbol':u'¥ (JPY)'},
            'MX':{'country_name':'Mexico','currency_code':'MXN','currency_symbol':u'$ (MXN)'},
            'NO':{'country_name':'Norway','currency_code':'NOK','currency_symbol':u'kr (NOK)'},
            'PH':{'country_name':'Philippines','currency_code':'PHP','currency_symbol':u'Php'},
            'PL':{'country_name':'Poland','currency_code':'PLN','currency_symbol':u'Zt'},
            'GB':{'country_name':'United Kingdom','currency_code':'GBP','currency_symbol':u'£'},
            'UK':{'country_name':'United Kingdom','currency_code':'GBP','currency_symbol':u'£'},
            'SG':{'country_name':'Singapore','currency_code':'SGD','currency_symbol':u'$'},
            'SE':{'country_name':'Sweden','currency_code':'SEK','currency_symbol':u'kr (SEK)'},
            'CH':{'country_name':'Switzerland','currency_code':'CHF','currency_symbol':u'chf'},
            'TW':{'country_name':'Taiwan','currency_code':'TWD','currency_symbol':u'NT$'},
            'TH':{'country_name':'Thailand','currency_code':'THB','currency_symbol':u'Thb'},
            'US':{'country_name':'United States','currency_code':'USD','currency_symbol':u'US$'},
            'EC':{'country_name':'Ecuador','currency_code':'USD','currency_symbol':u'US$'},
            'SV':{'country_name':'El Salvador','currency_code':'USD','currency_symbol':u'US$'},
            'MH':{'country_name':'Marshall Islands','currency_code':'USD','currency_symbol':u'US$'},
            'FM':{'country_name':'Federated States of Micronesia','currency_code':'USD','currency_symbol':u'US$'},
            'PW':{'country_name':'Palau','currency_code':'USD','currency_symbol':u'US$'},
            'PA':{'country_name':'Panama','currency_code':'USD','currency_symbol':u'US$'},
            'TC':{'country_name':'Turks and Caicos Islands','currency_code':'USD','currency_symbol':u'US$'},
            'ZW':{'country_name':'Zimbabwe','currency_code':'USD','currency_symbol':u'US$'},
            'LR':{'country_name':'Liberia','currency_code':'USD','currency_symbol':u'US$'},
            'VG':{'country_name':'British Virgin Islands','currency_code':'USD','currency_symbol':u'US$'},
            'VI':{'country_name':'United States Virgin Islands','currency_code':'USD','currency_symbol':u'US$'}}


class Foo:
  x = 0
  y = 1
  def foo(cls):
    print "classmethod: hello"
    print cls.x
  foo = classmethod(foo)
  def bar():
    print "staticmethod: hello"
    print Foo.x
  bar = staticmethod(bar)
# haha



class tata(object):
    x = 10
    y = 11

def f(tata):
    tata.x= 20
    return tata

if __name__ == "__madin__":
    currency_code = []
    currency_symbol = []
    for item in country_info.itervalues():
        print item
        if not item['currency_code'] in currency_code:
            currency_code.append(item['currency_code'])
            currency_symbol.append(item['currency_symbol'])
    
    currencies = []
    for index,item in enumerate(currency_code):
        currencies.append((currency_code[index],currency_symbol[index]))
    print currencies


class _UTCTimeZone(datetime.tzinfo):
  """UTC timezone."""

  ZERO = datetime.timedelta(0)

  def utcoffset(self, dt):
    return self.ZERO

  def dst(self, dt):
    return self.ZERO

  def tzname(self, dt):
    return 'UTC'

_UTC = _UTCTimeZone()


if __name__ == "__main__":

    ## Task with no ETA, api uses now.
    eta = datetime.datetime.now()
    print eta

    # If eta as no timezone use UTC
    eta = eta.replace(tzinfo=_UTC)
    eta = eta.astimezone(_UTC)
    print eta

    # Convert to unix ctime
    eta_sec = time.mktime(eta.timetuple())
    
    # convert back from ctime to python
    eta = datetime.datetime.fromtimestamp(eta_sec)
    print eta

    """
    Output:
    2010-05-08 07:15:40.375000
    2010-05-08 07:15:40.375000+00:00
    2010-05-08 08:15:40
    """