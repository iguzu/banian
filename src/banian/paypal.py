#!/usr/bin/env python
from django.utils import simplejson
from google.appengine.api.urlfetch import POST
import sys
import gaepytz
import logging
# PayPal python NVP API wrapper class.
# This is a sample to help others get started on working
# with the PayPal NVP API in Python. 
# This is not a complete reference! Be sure to understand
# what this class is doing before you try it on production servers!
# ...use at your own peril.

## see https://www.paypal.com/IntegrationCenter/ic_nvp.html
## and
## https://www.paypal.com/en_US/ebook/PP_NVPAPI_DeveloperGuide/index.html
## for more information.

# by Mike Atlas / LowSingle.com / MassWrestling.com, September 2007
# No License Expressed. Feel free to distribute, modify, 
#  and use in any open or closed source project without credit to the author

# Example usage: ===============
#    paypal = PayPal()
#    pp_token = paypal.SetExpressCheckout(100)
#    express_token = paypal.GetExpressCheckoutDetails(pp_token)
#    url= paypal.PAYPAL_URL + express_token
#    HttpResponseRedirect(url) ## django specific http redirect call for payment


import urllib, md5, datetime
from google.appengine.api import urlfetch


class PayPal:
    """ #PayPal utility class"""
    signature_values = {}
    API_ENDPOINT = ""
    PAYPAL_URL = ""
    
    def __init__(self):
        ## Sandbox values
        self.signature_values = {
        'USER' : 'broker_1259639312_biz_api1.iguzu.com', # Edit this to your API user name
        'PWD' : '1259639321', # Edit this to your API password
        'SIGNATURE' : 'AZcQUjrNMlC.PkfHpdAkBtgUbncuAzMHN6OQXSH4l-VnT7zH8LIrOoCX', # edit this to your API signature
        'VERSION' : '56.0',
        }
        self.API_ENDPOINT = 'https://api-3t.sandbox.paypal.com/nvp' # Sandbox URL, not production
        self.PAYPAL_URL = 'https://www.sandbox.paypal.com/webscr&cmd=_express-checkout&token=' # Sandbox URL, not production

        """
        ## Sandbox values
        self.signature_values = {
        'USER' : 'merchant_api1.iguzu.com', # Edit this to your API user name
        'PWD' : '2FMW4HYA89PAMMPV', # Edit this to your API password
        'SIGNATURE' : 'AnCtVmyMbodyOc-78mSJbBdSorQEAd3U-mcE8v.i87ZOgatvnRVwYxDS', # edit this to your API signature
        'VERSION' : '56.0',
        }
        self.API_ENDPOINT = 'https://api-3t.paypal.com/nvp' # Sandbox URL, not production
        """
        self.signature = urllib.urlencode(self.signature_values) + "&"

    # API METHODS
    def SetExpressCheckout(self, amount):
        params = {
            'METHOD' : "SetExpressCheckout",
            'NOSHIPPING' : 1,
            'PAYMENTACTION' : 'Authorization',
            'RETURNURL' : 'http://www.yoursite.com/returnurl', #edit this 
            'CANCELURL' : 'http://www.yoursite.com/cancelurl', #edit this 
            'AMT' : amount,
        }

        params_string = self.signature + urllib.urlencode(params)
        response = urllib.urlopen(self.API_ENDPOINT, params_string).read()
        response_token = ""
        for token in response.split('&'):
            if token.find("TOKEN=") != -1:
                response_token = token[ (token.find("TOKEN=")+6):]
        return response_token
    
    def GetExpressCheckoutDetails(self, token):
        params = {
            'METHOD' : "GetExpressCheckoutDetails",
            'RETURNURL' : 'http://www.yoursite.com/returnurl', #edit this 
            'CANCELURL' : 'http://www.yoursite.com/cancelurl', #edit this 
            'TOKEN' : token,
        }
        params_string = self.signature + urllib.urlencode(params)
        response = urllib.urlopen(self.API_ENDPOINT, params_string).read()
        response_tokens = {}
        for token in response.split('&'):
            response_tokens[token.split("=")[0]] = token.split("=")[1]
        return response_tokens
    
    def DoExpressCheckoutPayment(self, token, payer_id, amt):
        params = {
            'METHOD' : "DoExpressCheckoutPayment",
            'PAYMENTACTION' : 'Sale',
            'RETURNURL' : 'http://www.yoursite.com/returnurl', #edit this 
            'CANCELURL' : 'http://www.yoursite.com/cancelurl', #edit this 
            'TOKEN' : token,
            'AMT' : amt,
            'PAYERID' : payer_id,
        }
        params_string = self.signature + urllib.urlencode(params)
        response = urllib.urlopen(self.API_ENDPOINT, params_string).read()
        response_tokens = {}
        for token in response.split('&'):
            response_tokens[token.split("=")[0]] = token.split("=")[1]
        for key in response_tokens.keys():
                response_tokens[key] = urllib.unquote(response_tokens[key])
        return response_tokens
        
    def GetTransactionDetails(self, tx_id):
        params = {
            'METHOD' : "GetTransactionDetails", 
            'TRANSACTIONID' : tx_id,
        }
        params_string = self.signature + urllib.urlencode(params)
        response = urllib.urlopen(self.API_ENDPOINT, params_string).read()
        response_tokens = {}
        for token in response.split('&'):
            response_tokens[token.split("=")[0]] = token.split("=")[1]
        for key in response_tokens.keys():
                response_tokens[key] = urllib.unquote(response_tokens[key])
        return response_tokens
                
    def MassPay(self, email, amt, note, email_subject):
        unique_id = str(md5.new(str(datetime.datetime.now())).hexdigest())
        params = {
            'METHOD' : "MassPay",
            'RECEIVERTYPE' : "EmailAddress",
            'L_AMT0' : amt,
            'CURRENCYCODE' : 'USD',
            'L_EMAIL0' : email,
            'L_UNIQUE0' : unique_id,
            'L_NOTE0' : note,
            'EMAILSUBJECT': email_subject,
        }
        params_string = self.signature + urllib.urlencode(params)
        response = urllib.urlopen(self.API_ENDPOINT, params_string).read()
        response_tokens = {}
        for token in response.split('&'):
            response_tokens[token.split("=")[0]] = token.split("=")[1]
        for key in response_tokens.keys():
                response_tokens[key] = urllib.unquote(response_tokens[key])
        response_tokens['unique_id'] = unique_id
        return response_tokens
                
    def DoDirectPayment(self, amt, ipaddress, acct, expdate, cvv2, firstname, lastname, cctype, street, city, state, zipcode):
        params = {
            'METHOD' : "DoDirectPayment",
            'PAYMENTACTION' : 'Sale',
            'AMT' : amt,
            'IPADDRESS' : ipaddress,
            'ACCT': acct,
            'EXPDATE' : expdate,
            'CVV2' : cvv2,
            'FIRSTNAME' : firstname,
            'LASTNAME': lastname,
            'CREDITCARDTYPE': cctype,
            'STREET': street,
            'CITY': city,
            'STATE': state,
            'ZIP':zipcode,
            'COUNTRY' : 'United States',
            'COUNTRYCODE': 'US',
            'RETURNURL' : 'http://www.yoursite.com/returnurl', #edit this 
            'CANCELURL' : 'http://www.yoursite.com/cancelurl', #edit this 
            'L_DESC0' : "Desc: ",
            'L_NAME0' : "Name: ",
        }
        params_string = self.signature + urllib.urlencode(params)
        response = urllib.urlopen(self.API_ENDPOINT, params_string).read()
        response_tokens = {}
        for token in response.split('&'):
            response_tokens[token.split("=")[0]] = token.split("=")[1]
        for key in response_tokens.keys():
            response_tokens[key] = urllib.unquote(response_tokens[key])
        return response_tokens
    
    def DoAuthorization(self, transactionid, amt, currencycode):
        params = {
            'METHOD' : "DoAuthorization",
            'TRANSACTIONID' : transactionid,
            'AMT' : amt,
            'CURRENCYCODE': currencycode,
        }
        params_string = self.signature + urllib.urlencode(params)
        response = urlfetch.fetch(self.API_ENDPOINT,method=urlfetch.POST, payload=params_string)
        if response.status_code != 200:
            raise AssertionError
        response_tokens = {}
        for token in response.content.split('&'):
            response_tokens[token.split("=")[0]] = token.split("=")[1]
        for key in response_tokens.keys():
            response_tokens[key] = urllib.unquote(response_tokens[key])
        return response_tokens
    
    def AddressVerify(self, paypal_id, street,zip):
        params = {
            'METHOD' : "AddressVerify",
            'EMAIL' : paypal_id,
            'STREET' : street,
            'ZIP' : zip
        }
        params_string = self.signature + urllib.urlencode(params)
        response = urlfetch.fetch(self.API_ENDPOINT,params_string,method=POST)
        if response.status_code == 200:                
            response_tokens = {}
            for token in response.content.split('&'):
                response_tokens[token.split("=")[0]] = token.split("=")[1]
            for key in response_tokens.keys():
                    response_tokens[key] = urllib.unquote(response_tokens[key])
            return response_tokens
        return None


def utcToXsDateTime(datetime):
    return  '%4d-%02d-%02dT%02d:%02d:%02d.000Z' % (datetime.year, datetime.month, datetime.day, datetime.hour, datetime.minute, datetime.second)

    
def getPreApprovalDetails(key):
    try:
        url = 'https://svcs.sandbox.paypal.com/AdaptivePayments/PreapprovalDetails'
        headers = {'X-PAYPAL-SECURITY-USERID':'broker_1259639312_biz_api1.iguzu.com',
                   'X-PAYPAL-SECURITY-PASSWORD':'1259639321',
                   'X-PAYPAL-SECURITY-SIGNATURE':'AZcQUjrNMlC.PkfHpdAkBtgUbncuAzMHN6OQXSH4l-VnT7zH8LIrOoCX',
                   'X-PAYPAL-REQUEST-DATA-FORMAT':'JSON',
                   'X-PAYPAL-RESPONSE-DATA-FORMAT':'JSON',
                   'X-PAYPAL-APPLICATION-ID':'APP-80W284485P519543T',}
        payload = {'preapprovalKey':key,               
                   'requestEnvelope':{'errorLanguage':'en_US',},
                   }
        http_response = urlfetch.Fetch(url=url,headers=headers,method=urlfetch.POST,payload=simplejson.dumps(payload))
        if http_response.status_code != 200:
            logging.critical('Unexpected PayPal http Response: ' + repr(http_response.status_code))
            return 'paypal_unexpected'
        else:
            paypal_response = simplejson.loads(http_response.content)
            logging.debug(repr(paypal_response))
            envelope = paypal_response['responseEnvelope']
            if envelope['ack'] == 'Success':
                if paypal_response['approved'] =='true':
                    return 'Completed'
                elif paypal_response['approved'] =='false':
                    return 'Processing'
            elif envelope['ack'] == 'Failure':
                if paypal_response['error'][0]['errorId'] != '589019': 
                    logging.critical('Unexpected PayPal Response: ' + repr(paypal_response))
                    return 'paypal_unexpected'
                else:
                    logging.critical('Invalid pre-approval key: ' + repr(paypal_response))
                    return 'invalid_pre_approval_key'
    except:
        logging.critical('Unexpected error in processing getPreApprovalDetails' + repr(sys.exc_info()))
        return 'paypal_unexpected'


def processPreApproval(memo,amount,paypal_id,returnURL,cancelURL,endDate,startDate=datetime.datetime.utcnow().replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('US/Pacific'))):
    try:
        url = 'https://svcs.sandbox.paypal.com/AdaptivePayments/Preapproval'
        headers = {'X-PAYPAL-SECURITY-USERID':'broker_1259639312_biz_api1.iguzu.com',
                   'X-PAYPAL-SECURITY-PASSWORD':'1259639321',
                   'X-PAYPAL-SECURITY-SIGNATURE':'AZcQUjrNMlC.PkfHpdAkBtgUbncuAzMHN6OQXSH4l-VnT7zH8LIrOoCX',
                   'X-PAYPAL-REQUEST-DATA-FORMAT':'JSON',
                   'X-PAYPAL-RESPONSE-DATA-FORMAT':'JSON',
                   'X-PAYPAL-APPLICATION-ID':'APP-80W284485P519543T',}
        payload = {'returnUrl':returnURL,
                   'cancelUrl':cancelURL,               
                   'requestEnvelope':{'errorLanguage':'en_US',},
                   'clientDetails':{'ipAddress':'','applicationId':"Iguzu brokerage platform",
                                    'customerId':'iguzu.com',},
                   'senderEmail':paypal_id,
                   'maxTotalAmountOfAllPayments':'%.2f' % amount,
                   'currencyCode':'USD',
                   'startingDate':utcToXsDateTime(startDate),
                   'endingDate':utcToXsDateTime(endDate),
                   'memo':memo,
                   }
        http_response = urlfetch.Fetch(url=url,headers=headers,method=urlfetch.POST,payload=simplejson.dumps(payload))
        if http_response.status_code != 200:
            logging.critical('Unexpected PayPal Response: ' + repr(http_response))
            return 'paypal_unexpected', None
        else:
            paypal_response = simplejson.loads(http_response.content)
            logging.debug(repr(paypal_response))
            envelope = paypal_response['responseEnvelope']       
            if envelope['ack'] == 'Success':
                return 'Processing', paypal_response['preapprovalKey']
            elif envelope['ack'] == 'Failure':
                # Invalid paypal account invalid_account
                if paypal_response['error'][0]['errorId'] == '589039':
                    return 'invalid_account', None
                if paypal_response['error'][0]['errorId'] == '580024':
                    return 'past_start_date', None
                else:
                # pre approval failed.
                    logging.critical('Unexpected PayPal Response: ' + repr(paypal_response))
                    return 'paypal_unexpected', None
    except:
        logging.critical('Unexpected error in processing processPreApproval' + repr(sys.exc_info()))
        return 'paypal_unexpected', None

def processPaymentEx(request,memo,amount, apkey,receiver='broker_1259639312_biz@iguzu.com',receiverName='Iguzu Inc.'):
    paypal_response = None
    try:
        url = 'https://svcs.sandbox.paypal.com/AdaptivePayments/Pay'
        headers = {'X-PAYPAL-SECURITY-USERID':'broker_1259639312_biz_api1.iguzu.com',
                   'X-PAYPAL-SECURITY-PASSWORD':'1259639321',
                   'X-PAYPAL-SECURITY-SIGNATURE':'AZcQUjrNMlC.PkfHpdAkBtgUbncuAzMHN6OQXSH4l-VnT7zH8LIrOoCX',
                   'X-PAYPAL-REQUEST-DATA-FORMAT':'JSON',
                   'X-PAYPAL-RESPONSE-DATA-FORMAT':'JSON',
                   'X-PAYPAL-APPLICATION-ID':'APP-80W284485P519543T',}
        payload = {'returnUrl':'http://www.iguzu.com/',
                   'requestEnvelope':{'errorLanguage':'en_US',},
                   'currencyCode':'USD',
                   'receiverList':{'receiver':[{'email':receiver,'amount':"%.2f" % amount,}]},
                   'clientDetails':{'ipAddress':request.META.get('REMOTE_ADDR',''),'applicationId':"Iguzu brokerage platform",
                                    'customerId':request.user.username,'partnerName':receiverName},
                   'cancelUrl':"http://www.iguzu.com/",
                   'senderEmail':request.user.paypal_id,
                   'actionType':'PAY',
                   'memo':memo
                   }
        if apkey:
            payload['preapprovalKey'] = apkey

        #TODO: add IP adress from META
        http_response = urlfetch.Fetch(url=url,headers=headers,method=urlfetch.POST,payload=simplejson.dumps(payload))
        if http_response.status_code != 200:
            logging.critical(repr(http_response))
            return 'paypal_unexpected',None
        else:
            paypal_response = simplejson.loads(http_response.content)        
            envelope = paypal_response['responseEnvelope']
            if envelope['ack'] == 'Success':
                if paypal_response['paymentExecStatus'] == 'COMPLETED':
                    return 'Completed',None
                elif paypal_response['paymentExecStatus'] == 'CREATED':
                    return 'Created',paypal_response['payKey']
                else:
                    logging.critical('paypal_unexpected Response: ' + repr(paypal_response))
                    return 'paypal_unexpected',None
            elif envelope['ack'] == 'Failure':
                if paypal_response['error'][0]['errorId'] == '569013' or \
                   paypal_response['error'][0]['errorId'] == '569017' or \
                   paypal_response['error'][0]['errorId'] == '569018':
                    return 'Canceled',None
                else:
                    logging.critical('paypal_unexpected Response: ' + repr(paypal_response))
                    return 'paypal_unexpected',None
    except:
        logging.critical('Unexpected error in processing processPayment' + repr(sys.exc_info()))
        return 'paypal_unexpected',None

def processPayment(memo,paypal_id,amount,apkey):
    paypal_response = None
    try:
        url = 'https://svcs.sandbox.paypal.com/AdaptivePayments/Pay'
        headers = {'X-PAYPAL-SECURITY-USERID':'broker_1259639312_biz_api1.iguzu.com',
                   'X-PAYPAL-SECURITY-PASSWORD':'1259639321',
                   'X-PAYPAL-SECURITY-SIGNATURE':'AZcQUjrNMlC.PkfHpdAkBtgUbncuAzMHN6OQXSH4l-VnT7zH8LIrOoCX',
                   'X-PAYPAL-REQUEST-DATA-FORMAT':'JSON',
                   'X-PAYPAL-RESPONSE-DATA-FORMAT':'JSON',
                   'X-PAYPAL-APPLICATION-ID':'APP-80W284485P519543T',}
        payload = {'returnUrl':'http://www.iguzu.com/',
                   'requestEnvelope':{'errorLanguage':'en_US',},
                   'currencyCode':'USD',
                   'receiverList':{'receiver':[{'email':'broker_1259639312_biz@iguzu.com','amount':"%.2f" % amount,}]},
                   'clientDetails':{'ipAddress':'','applicationId':"Iguzu brokerage platform",
                                    'customerId':'Iguzu','partnerName':'Iguzu Inc.'},
                   'cancelUrl':"http://www.iguzu.com/",
                   'preapprovalKey':apkey,
                   'senderEmail':paypal_id,
                   'actionType':'PAY',
                   'memo':memo
                   }
        http_response = urlfetch.Fetch(url=url,headers=headers,method=urlfetch.POST,payload=simplejson.dumps(payload))
        if http_response.status_code != 200:
            logging.critical(repr(http_response))
            return 'paypal_unexpected'
        else:
            paypal_response = simplejson.loads(http_response.content)        
            envelope = paypal_response['responseEnvelope']
            if envelope['ack'] == 'Success':
                if paypal_response['paymentExecStatus'] == 'COMPLETED':
                    return 'Completed'
                else:
                    logging.critical('paypal_unexpected Response: ' + repr(paypal_response))
                    return 'paypal_unexpected'
            elif envelope['ack'] == 'Failure':
                if paypal_response['error'][0]['errorId'] == '569013' or \
                   paypal_response['error'][0]['errorId'] == '569017' or \
                   paypal_response['error'][0]['errorId'] == '569018':
                    return 'Canceled'
                else:
                    logging.critical('paypal_unexpected Response: ' + repr(paypal_response))
                    return 'paypal_unexpected' 
    except:
        logging.critical('Unexpected error in processing processPayment' + repr(sys.exc_info()))
        return 'paypal_unexpected'

    
def processCancelPreApproval(apkey):
    try:
        url = 'https://svcs.sandbox.paypal.com/AdaptivePayments/CancelPreapproval'
        headers = {'X-PAYPAL-SECURITY-USERID':'broker_1259639312_biz_api1.iguzu.com',
                   'X-PAYPAL-SECURITY-PASSWORD':'1259639321',
                   'X-PAYPAL-SECURITY-SIGNATURE':'AZcQUjrNMlC.PkfHpdAkBtgUbncuAzMHN6OQXSH4l-VnT7zH8LIrOoCX',
                   'X-PAYPAL-REQUEST-DATA-FORMAT':'JSON',
                   'X-PAYPAL-RESPONSE-DATA-FORMAT':'JSON',
                   'X-PAYPAL-APPLICATION-ID':'APP-80W284485P519543T',}
        payload = {               
                   'requestEnvelope':{'errorLanguage':'en_US',},
                   'preapprovalKey':apkey,
                   }
        http_response = urlfetch.Fetch(url=url,headers=headers,method=urlfetch.POST,payload=simplejson.dumps(payload))
        if http_response.status_code != 200:
            logging.critical(repr(http_response))
            return 'paypal_unexpected'
        else:
            paypal_response = simplejson.loads(http_response.content)
            envelope = paypal_response['responseEnvelope']
            if envelope['ack'] == 'Success':
                return 'Completed'
            else:
                return 'Failure'
    except:
        logging.critical('Unexpected error in processing processCancelPreApproval' + repr(sys.exc_info()))
        return 'paypal_unexpected'


def processRefund(memo,paypal_id,total_amount,apkey):
    return 'Completed'
