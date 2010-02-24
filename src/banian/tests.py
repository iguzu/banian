'''
Created on Dec 12, 2009

@author: install
'''
from django.test import TestCase
from banian import models
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse, resolve
from datetime import datetime, timedelta
from banian.forms import ValidateLocation
from google.appengine.ext import db
from google.appengine.api import urlfetch
from banian.utils import ElementExtracter, handle_images
from uuid import uuid4
from google.appengine.api.labs import taskqueue
from django.utils.simplejson import loads, dumps
from banian.views import event_edit_form_list
from banian.paypal import getPreApprovalDetails, processPreApproval,\
    processPayment, processCancelPreApproval, PayPal
import sys
import cgi
import base64
import random
import logging
import urllib
import gaepytz
import banian.paypal #@UnusedImport
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound

cDiv = ElementExtracter('div',{'id':'content'})

paypal_processPayment = None
paypal_processPreApproval = None
paypal_getPreApprovalDetails = None
def StubPaypal():
    global paypal_processPayment, paypal_processPreApproval, paypal_getPreApprovalDetails
    def processPayment(*args,**kwargs):
        return 'Completed'
    def processPreApproval(*args,**kwargs):
        return 'Processing', None
    def getPreApprovalDetails(*args,**kwargs):
        return 'Completed'

    paypal_module = sys.modules['banian.paypal']
    if not paypal_processPayment:
        paypal_processPayment = paypal_module.processPayment
        paypal_module.processPayment = processPayment
    if not paypal_processPreApproval:
        paypal_processPreApproval = paypal_module.processPreApproval
        paypal_module.processPreApproval = processPreApproval
    if not paypal_getPreApprovalDetails:
        paypal_getPreApprovalDetails = paypal_module.getPreApprovalDetails
        paypal_module.getPreApprovalDetails = getPreApprovalDetails

def unStubPaypal():
    global paypal_processPayment, paypal_processPreApproval, paypal_getPreApprovalDetails
    paypal_module = sys.modules['banian.paypal']
    if paypal_processPayment:
        paypal_module.processPayment = paypal_processPayment
        paypal_processPayment = None
    if paypal_processPreApproval:
        paypal_module.processPreApproval = paypal_processPreApproval
        paypal_processPreApproval = None
    if paypal_getPreApprovalDetails:
        paypal_module.processPreApproval = paypal_getPreApprovalDetails
        paypal_getPreApprovalDetails = None

google_urlfetch = None

def StubUrlFetch(function):
    global google_urlfetch
    google_api_module = sys.modules['google.appengine.api']
    if not google_urlfetch:
        google_urlfetch = google_api_module.urlfetch.Fetch
    google_api_module.urlfetch.Fetch = function

def UnStubUrlFetch():
    global google_urlfetch
    if google_urlfetch:
        google_api_module = sys.modules['google.appengine.api']
        google_api_module.urlfetch.Fetch = google_urlfetch
        google_urlfetch = None


def createUser(testcase,username=None,password=None,name=None,paypal_id=None, address=None,login=True):
        username = username or 'sbl@iguzu.com'
        password = password or 'secret'
        paypal_id = paypal_id or 'seller_1259638970_biz@iguzu.com'
        name = name or 'SBL'
        user = User.objects.create_user(username, username, password) #@UndefinedVariable
        user.is_staff = True
        user.name = name
        if not address:
            user.address = '2855 Rue Centre, app 212, Montreal, Quebec, Canada'
            user.location =  db.GeoPt(45.476454,-73.572827)
        else:
            lat, lon, address_name, short_address, country = ValidateLocation(address=address) #@UnusedVariable
            user.location = db.GeoPt(lat,lon)
        user.paypal_id = 'seller_1259638970_biz@iguzu.com'
        user.save()
        if login:
            testcase.assert_(testcase.client.login(username=username, password=password))
        return user


def run_tasks(name=None,url=None,lapse=0):
    '''
    Run all due tasks in the all task queues
    Parameter:
        - name: filters only to run task with that particular name
        - url: filters only to run task with that particular url
        - lapse: number of seconds added to determined if a tasks is due, effectivly allowing to run futur tasks now.
    Returns a list of completed task and a list of failed tasks
    
    ''' 
    from google.appengine.api import apiproxy_stub_map

    stub = apiproxy_stub_map.apiproxy.GetStub('taskqueue')
    tasks = []
    #get all the tasks for all the queues
    completed = []
    failed = []
    for queue in stub.GetQueues():
        tasks = stub.GetTasks(queue['name'])
        #keep only tasks that need to be executed with a certain lapse of time
        now = datetime.now() + timedelta(seconds=lapse)
        tasks = filter(lambda t: datetime.strptime(t['eta'],'%Y/%m/%d %H:%M:%S') <= now, tasks)
        if url:
            tasks = filter(lambda t: t['url'] == url, tasks)
        if name:
            tasks = filter(lambda t: t['name'] == name, tasks)
        # execute django views
        for task in tasks:
            # Find the view to be executed
            view, args, kwargs = resolve(task['url'])
            # create the fake request 
            request = HttpRequest()
            request.method = task['method']
            request.POST = dict(cgi.parse_qsl(base64.decodestring(task['body'])))
            request.GET = dict(cgi.parse_qsl(task['url']))
            kwargs['request'] = request
            # Execute the tasks
            response = view(*args,**kwargs)
            if response.status_code == 200:
                completed.append({'task':'%s-%s' %(task['name'],task['url']),'status':response.status_code,'content':response.content})
                stub.DeleteTask(queue['name'],task['name'])
            else:
                failed.append({'task':'%s-%s' %(task['name'],task['url']),'status':response.status_code,'content':response.content})
    return completed, failed

def buyTickets(testcase,representation,tickets=None):
    tickets = tickets or 3
    if isinstance(tickets,list):
        data = {}; i = 1
        for item in tickets:
            data['tc%d' % i] = item 
        i = i + 1
    else:
        data = {'tc1':tickets,}
    r = testcase.client.post(reverse('banian.views.buy_representation',kwargs={'key':str(representation.key()),}),data, follow=True)
    testcase.assertEqual(r.status_code,200,r.content)
    run_tasks(lapse=60)
    return r
    
def MarkupValidation(testcase,response_content):
    payload = urllib.urlencode({'fragment':response_content,'direct-charset':'(detect automatically)','direct-doctype':'Inline','group':0,'direct_prefill_no':'0','prefill_doctype':'html401'})
    if not models.offline_mode:
        rv = urlfetch.fetch('http://validator.w3.org/check',method=urlfetch.POST,payload=payload)
        if rv.headers['x-w3c-validator-status'] != 'Valid':
            errmsg = ElementExtracter(tag="li",attributes={"class":'msg_err'})
            errmsg.parse(rv.content)
            testcase.fail('Markup Validation failed: error(s): %s, warning(s): %s\n\nErrors:\n%s\n\n\n\nFor page:\n%s' % (rv.headers['x-w3c-validator-errors'],rv.headers['x-w3c-validator-warnings'],errmsg.get_content(),response_content))

def formValidation(testcase,r):
    if r.context:
        if isinstance(r.context,dict) and 'form' in r.context:
            testcase.assertEqual(r.context['form'].errors == None or r.context['form'].errors == {})
        elif isinstance(r.context,list) and 'form' in r.context[0]:
            testcase.assert_(r.context[0]['form'].errors == None or r.context[0]['form'].errors == {},r.context[0]['form'].errors)

def publishEvent(testcase,event,do_run_tasks=True):
    representation = event.first_representation() 
    representation.pre_approval_status = 'Completed'
    job_id = str(uuid4())
    representation.status = 'Generating'
    representation.job_id = job_id
    representation.put()
    if event.status == 'Draft':
        event.status = 'Published'
        event.put()
    ticket_class = models.TicketClass.gql("WHERE event=:1 ORDER BY __key__", event).get()
    seat_group = ticket_class.seat_groups[0]
    taskqueue.add(url='/tasks/generate_seats/', params={'representation':representation.key(), 'ticket_class':ticket_class.key(), 'seat_group':seat_group,'job_id':job_id}, countdown=0)
    if do_run_tasks:
        completed = True
        while(completed):
            completed, failed = run_tasks(url='/tasks/generate_seats/',lapse=60) #@UnusedVariable
    return db.get(event.key())

def addEvent(testcase,owner,name,date=None,onsale_date=None, endsale_date=None,restrict_sale_period=None,
             address=None,timezone=None, venue_name=None,thumbnail=None,poster=None,
             nbr_seat=None,web_site=None,email=None,force_no_image=False,price=None,
             general_admission=None,door_open=None,note=None,max_step=None):

    class _obj(object):
        files = {}
    form = _obj()
    if restrict_sale_period == None:
        restrict_sale_period = True
    testcase.assertFalse(models.Event.all().filter('name =',name))
    max_step = max_step or len(event_edit_form_list)-2

    timezone = timezone or 'America/Montreal'
    if not address:
        address = '59 Sainte-Catherine Street East, Montreal Quebec H2X 1K5'
        location =  db.GeoPt(45.510569,-73.5632057)
        country = 'CA'
    else:
        lat, lon, address_name, short_address, country = ValidateLocation(address=address) #@UnusedVariable
        location = db.GeoPt(lat,lon)
    if date:
        date_inc = (date - datetime.now().replace(tzinfo=gaepytz.timezone(timezone))).days
    else:
        date_inc = random.randint(3,360)
        date = datetime.now().replace(tzinfo=gaepytz.timezone(timezone)) + timedelta(days=date_inc)
    if onsale_date:
        onsale_inc = (date - onsale_date).days
    else:
        onsale_inc = random.randint(2,date_inc-1)
        onsale_date = date - timedelta(days=onsale_inc)
    endsale_inc = random.randint(1,onsale_inc-1)
    endsale_date = endsale_date or onsale_date + timedelta(days=endsale_inc)
    testcase.failIf(onsale_date > endsale_date,"osd: %s, esd: %s,osinc %d, endinc %d, dateinc %d " % (onsale_date,endsale_date,onsale_inc,endsale_inc,date_inc))
    testcase.failIf(onsale_date > date,"osd: %s, date: %s" % (onsale_date,date))
    testcase.failIf(endsale_date > date,"esd: %s, date: %s" % (endsale_date,date))
    venue_name = 'Metropolis' or venue_name
    nbr_seat = nbr_seat or random.randint(10,3000)
    if price == None:
        price = (float(random.randint(1000,30000)) / 100)
    if general_admission == None:
        bool(random.randint(0,1))
    door_open = door_open or 90
    if not force_no_image:
        thumbnail = thumbnail or open('..\\fixtures\\media\\placebo480x480.jpg',mode='rb')
        poster = poster or open('..\\fixtures\\media\\placebo200x300.gif',mode='rb')
        form.files['thumbnail'] = thumbnail
        form.files['poster'] = poster
    v = models.Venue(quick=True,
                     name=venue_name,
                     address=address,
                     country=country,
                     timezone=timezone,
                     owner=owner,
                     location=location)
    v.put()
    sc = models.SeatConfiguration(name='base',venue=v,owner=owner)
    sc.put()
    sg = models.SeatGroup(name='',type='Venue',owner=owner,parent=None,seat_configuration=sc,nbr_seat=nbr_seat)
    sg.put()
    
    
    e = models.Event(quick=True,
                     venue=v,
                     name=name,
                     web_site=web_site,
                     email=email,
                     owner=owner,
                     onsale_date=onsale_date,
                     endsale_date=endsale_date,
                     seat_configuration=sc,
                     restrict_sale_period=restrict_sale_period,
                     door_open=door_open,
                     note=note,
                     max_step=max_step,
                     validators= [owner.key()])
    handle_images(form,e)
    e.put()
    tc = models.TicketClass(name='',owner=owner, event=e,price=price,general_admission=general_admission)
    tc.seat_groups.append(sg.key())
    if general_admission:
        tc.name = 'General Admission'
    tc.put()
    r = models.Representation(owner=owner, event=e,venue=v,date=date)
    r.put()
    return e

class HomeTestCase(TestCase):
    def setUp(self):
        logging.debug('HomeTestCase')

    def testAnonymousShow(self):
        r = self.client.get(reverse('banian.views.default'))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content) 
        
    def testAuthenticatedShow(self): 
        user = User.objects.create_user('test', 'sbl@iguzu.com', 'secret') #@UndefinedVariable
        user.is_staff = True
        user.save()
        self.client.login(username ='test', password='secret')
        r = self.client.get(reverse('banian.views.default'))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content) 


class VADEVenueTestCase(TestCase):
    def setUp(self):
        logging.debug('VADEVenueTestCase')
        self.user = createUser(self)
        self.i = models.Image()
        self.i.filename = 'test.gif'
        self.i.put()
        self.i2 = models.Image()
        self.i2.filename = 'test.gif'
        self.i2.put()

        v = models.Venue(name="Test Venue",
                  address='2855 Rue centre, app 212, Montreal, Qc,Ca, H3K 3C4',
                  country='CA',
                  web_site='http://iguzu.com',
                  timezone='America/Montreal',
                  decription='description',
                  owner=self.user,
                  thumbnail_image=self.i,
                  poster_image=self.i2)
        v.put()
        
        sc = models.SeatConfiguration(name='base',venue=v,owner=self.user)
        sc.put()

        v1 = models.Venue(name="Test Venue No Image",
                  address='2855 Rue centre, app 212, Montreal, Qc,Ca, H3K 3C4',
                  country='CA',
                  web_site='http://iguzu.com',
                  timezone='America/Montreal',
                  decription='description',
                  owner=self.user)
        v1.put()
  
    def testAddNoImage(self):
        r = self.client.post(reverse('banian.venue.views.add_venue'),{'name':'Added Venue',
                                  'address':'2855 Rue centre, app 212, Montreal, Qc,Ca, H3K 3C4',
                                  'country':'CA',
                                  'web_site':'http://iguzu.com',
                                  'timezone':'America/Montreal',
                                  'decription':'description',
                                  }) 
        if r.context:
            self.assertEqual(r.context['form'].errors,None,r.context['form'].errors)
        self.assertEqual(r.status_code,302)
        assert(models.Venue.all().filter('name =','Added Venue').get())

    def testAddWithImage(self):
        f1 = open('..\\fixtures\\media\\placebo200x300.gif',mode='rb')
        f2 = open('..\\fixtures\\media\\placebo200x300.gif',mode='rb')
        r = self.client.post(reverse('banian.venue.views.add_venue'),{'name':'Added Venue',
                                  'address':'2855 Rue centre, app 212, Montreal, Qc,Ca, H3K 3C4',
                                  'country':'CA',
                                  'web_site':'http://iguzu.com',
                                  'timezone':'America/Montreal',
                                  'decription':'description',
                                  'thumbnail':f1,
                                  'poster':f2
                                  })  
        if r.context:
            self.assertEqual(r.context['form'].errors,None,r.context['form'].errors)
        self.assertEqual(r.status_code,302)
        assert(models.Venue.all().filter('name =','Added Venue').get())

    def testShow(self):
        v = models.Venue.all().filter('name =','Test Venue').get()
        r = self.client.get(reverse('banian.venue.views.show_venue',kwargs={'key':v.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
    def testEdit(self):
        v = models.Venue.all().filter('name =','Test Venue').get()
        r = self.client.get(reverse('banian.venue.views.edit_venue',kwargs={'key':v.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)

    def testShowNoImage(self):
        v = models.Venue.all().filter('name =','Test Venue No Image').get()
        r = self.client.get(reverse('banian.venue.views.show_venue',kwargs={'key':v.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        
    def testEditNoImage(self):
        v = models.Venue.all().filter('name =','Test Venue No Image').get()
        r = self.client.get(reverse('banian.venue.views.edit_venue',kwargs={'key':v.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)


    def testDelete(self):
        v = models.Venue.all().filter('name =','Test Venue').get()
        sc_list = models.SeatConfiguration.all(keys_only=True).filter('venue =',v).fetch(1000)
        v.poster_image.key()
        v_k = v.key()
        self.assertTrue(sc_list)
        r = self.client.get(reverse('banian.venue.views.delete_venue',kwargs={'key':v.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        r = self.client.post(reverse('banian.venue.views.delete_venue',kwargs={'key':v.key()}),follow=True)
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        self.assertFalse(models.Venue.get(v_k))
        sc_list = models.SeatConfiguration.get(sc_list)
        if len(sc_list) == 1 and sc_list[0]==None:
            sc_list = None
        self.assertFalse(sc_list)

    def testShowNotOwned(self):
        v = models.Venue.all().filter('owner =',self.user,).get()
        createUser(self,'UserB','secret')
        r = self.client.get(reverse('banian.venue.views.show_venue',kwargs={'key':v.key()}),follow=True)
        self.assertEqual(r.status_code,404)

    def testEditNotOwned(self):
        v = models.Venue.all().filter('owner =',self.user,).get()
        self.assertTrue(v)
        createUser(self,'UserB','secret')
        r = self.client.get(reverse('banian.venue.views.edit_venue',kwargs={'key':v.key()}),follow=True)
        self.assertEqual(r.status_code,404)
        r = self.client.post(reverse('banian.venue.views.edit_venue',kwargs={'key':v.key()}),
                             {'name':'toto',
                              },follow=True)
        self.assertEqual(r.status_code,404)
        v_after = models.Venue.all().filter('name =','toto').get()
        self.assertFalse(v_after)

    def testDeleteNotOwned(self):
        v = models.Venue.all().filter('name =','Test Venue').get()
        createUser(self,'UserB','secret')
        r = self.client.get(reverse('banian.venue.views.delete_venue',kwargs={'key':v.key()}),follow=True)
        self.assertEqual(r.status_code,404)
        v_after = models.Venue.all().filter('name =','Test Venue').get()
        self.assertNotEqual(v_after,None)

    def testEditInvalid(self):
        r = self.client.get(reverse('banian.venue.views.edit_venue',kwargs={'key':'AAAA'}),follow=True)
        self.assertEqual(r.status_code,404)
        r = self.client.post(reverse('banian.venue.views.edit_venue',kwargs={'key':'AAAA'}),
                             {'name':'toto',
                              },follow=True)
        self.assertEqual(r.status_code,404)

    def testDeleteInvalid(self):
        r = self.client.get(reverse('banian.venue.views.delete_venue',kwargs={'key':'AAA'}),follow=True)
        self.assertEqual(r.status_code,404)
    
    def testEditUnmutable(self):
        event = addEvent(self, self.user, 'Test event', nbr_seat=10)
        event = publishEvent(self, event)
        self.assertEqual(event.status,'Published')
        r = self.client.get(reverse('banian.venue.views.edit_venue',kwargs={'key':event.venue.key()}))
        self.assertEqual(r.status_code,403)
        r = self.client.post(reverse('banian.venue.views.edit_venue',kwargs={'key':event.venue.key()}))
        self.assertEqual(r.status_code,403)

    def testDeleteUnmutable(self):
        event = addEvent(self,self.user,"Test Event", nbr_seat=10)
        event = publishEvent(self, event)
        self.assertEqual(event.status,'Published')
        r = self.client.get(reverse('banian.venue.views.delete_venue',kwargs={'key':event.venue.key()}))
        self.assertEqual(r.status_code,403)
        r = self.client.post(reverse('banian.venue.views.delete_venue',kwargs={'key':event.venue.key()}))
        self.assertEqual(r.status_code,403)

    def testShowUnmutable(self):
        event = addEvent(self, self.user, 'test event',nbr_seat=10)
        event = publishEvent(self, event)
        r = self.client.get(reverse('banian.venue.views.show_venue',kwargs={'key':event.venue.key()}))
        self.assertNotContains(r, reverse('banian.venue.views.delete_venue',kwargs={'key':event.venue.key()}))
        self.assertNotContains(r, reverse('banian.venue.views.edit_venue',kwargs={'key':event.venue.key()}))


class VADEEventTestCase(TestCase):
    def setUp(self):
        logging.debug('VADEEventTestCase')
        StubPaypal()
        user = createUser(self)
        addEvent(self,owner=user,name='Test Event',nbr_seat=20)
        addEvent(self,owner=user,name='Test Event (No image)',force_no_image=True,nbr_seat=20)

    def testShow(self):
        v = models.Event.all().filter('name =','Test Event').get()
        r = self.client.get(reverse('banian.views.show_event',kwargs={'key':v.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)

    def addEvent(self):
        ## validate that the validators are in
        pass

    def testPage1(self):
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e)
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=0')
        self.assertEqual(r.status_code,200)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=0',
                             {'name':'name changed',
                              'description':'Description here',
                              'web_site':'www.iguzu.com',
                              'email':'info@iguzu.com',
                              'next':'next'
                              },follow=True)
        formValidation(self,r)   
        self.assertEqual(r.status_code,200)
        e = models.Event.all().filter('name =','name changed').get()
        self.assertTrue(e)
        MarkupValidation(self,r.content)

    def testPage2(self):
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e)
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=1')
        self.assertEqual(r.status_code,200)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=1',
                             {'name':'venue name changed',
                              'country':'CA',
                              'address':'2855 rue centre, app 212, H3K3C4, Canada',
                              },follow=True)   
        formValidation(self,r)
        self.assertEqual(r.status_code,200)
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e.venue.location)
        self.assertEqual(e.venue.name,'venue name changed')
        self.assertTrue(e)
        MarkupValidation(self,r.content)

    def testPage3(self):
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e)
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=2')
        self.assertEqual(r.status_code,200)
        now = datetime.now().replace(tzinfo=gaepytz.timezone(e.venue.timezone),second=0,microsecond=0) + timedelta(days=2)
        date =  '%02d/%02d/%4d' % (now.month,now.day,now.year)
        time = '%02d:%02d' % (now.hour,now.minute)
        
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=2',
                             {'timezone':'America/Montreal',
                              'date':date,
                              'time':time,
                              'duration':'60',
                              'door_open':'90'
                              },follow=True)   
        formValidation(self,r)
        self.assertEqual(r.status_code,200)
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertEqual(e.first_representation().date,now)
        self.assertEqual(e.first_representation().timezone,'America/Montreal')
        self.assertEqual(e.venue.timezone,'America/Montreal')
        self.assertTrue(e)
        MarkupValidation(self,r.content)

    def testPage4(self):
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e)
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=3')
        self.assertEqual(r.status_code,200)        
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=3',
                             {'price':20.99,
                              'nbr_tickets':110,
                              'general_admission':True,
                              'is_free':2
                              },follow=True)   
        formValidation(self,r)
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)

    def testPage5(self):
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e)
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=4')
        self.assertEqual(r.status_code,200)
        date = datetime.now().replace(tzinfo=gaepytz.timezone(e.venue.timezone),second=0,microsecond=0) + timedelta(days=10)
        r = e.first_representation()
        r.date = date
        r.put()
        onsale = date + timedelta(days=-5)
        onsale_date =  '%02d/%02d/%4d' % (onsale.month,onsale.day,onsale.year)
        onsale_time = '%02d:%02d' % (onsale.hour,onsale.minute)
        endsale = onsale + timedelta(days=2)
        endsale_date =  '%02d/%02d/%4d' % (endsale.month,endsale.day,endsale.year)
        endsale_time = '%02d:%02d' % (endsale.hour,endsale.minute)
        
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=4',
                             {'restrict_sale_period':True,
                              'onsale_date':onsale_date,
                              'onsale_time':onsale_time,
                              'endsale_date':endsale_date,
                              'endsale_time':endsale_time,
                              'cancel_fees':19.0,
                              'cancel_delay':10,
                              'cancellable':True,
                              'limit_tickets':True,
                              'max_tickets':10,
                              },follow=True)   
        formValidation(self,r)
        self.assertEqual(r.status_code,200)
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertEqual(e.onsale_date,onsale)
        self.assertEqual(e.endsale_date,endsale)
        self.assertTrue(e)
        MarkupValidation(self,r.content)


    def testEdit6(self):
        f1 = open('..\\fixtures\\media\\placebo100x100.gif',mode='rb')
        f2 = open('..\\fixtures\\media\\placebo200x300.gif',mode='rb')

        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e)
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=5')
        self.assertEqual(r.status_code,200)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=5',
                             {'note':'Alibaba',
                              'thumbnail':f1,
                              'poster':f2,
                              },follow=True)   
        formValidation(self,r)            
        self.assertEqual(r.status_code,200)
        e = models.Event.all().filter('name =','Test Event').get()
        self.assertTrue(e)
        f1.seek(0);f2.seek(0)
        self.assertEqual(e.thumbnail_image.content,f1.read(),'thumbnail mismatch data mismatch')
        MarkupValidation(self,r.content)
#TODO: FInd out why the second attachment in the test is actually passed as the firt. Strange seems a bug from the framework
#        self.assertEqual(e.poster_image.content,f2.read(),'poster content data mismatch')

    def testShowNoImage(self):
        v = models.Event.all().filter('name =','Test Event (No image)').get()
        r = self.client.get(reverse('banian.views.show_event',kwargs={'key':v.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)

    def testEditNoImage(self):
        v = models.Event.all().filter('name =','Test Event (No image)').get()
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':v.key()})+'?step=5')
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)


    def testDelete(self):
        e = models.Event.all().filter('name =','Test Event').get()
        it_k = None; ip_k = None; s_k = None
        e_k = e.key()
        v_k = e.venue.key()
        sc_k = e.seat_configuration.key()
        tc_k = e.ticketclass_set.get().key()
        sg_k = models.SeatGroup.get(e.ticketclass_set.get().seat_groups[0]).key()
        r_k = e.first_representation().key()
        if e.thumbnail_image:
            it_k = e.thumbnail_image.key()
        if e.poster_image:
            ip_k = e.poster_image.key()
        if e.first_representation().status != 'Draft':
            s_k = e.first_representation().seat_set.get().key()

        models.Venue.get(v_k)
        models.SeatConfiguration.get(sc_k)
        models.TicketClass.get(tc_k)
        models.SeatGroup.get(sg_k)
        models.Representation.get(r_k)
        if it_k:
            models.Image.get(it_k)
        if ip_k:
            models.Image.get(ip_k)
        if s_k:
            models.Seat.get(s_k)
     
        r = self.client.get(reverse('banian.views.delete_event',kwargs={'key':e.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        r = self.client.post(reverse('banian.views.delete_event',kwargs={'key':e.key()}),follow=True)
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        self.assertFalse(models.Event.get(e_k))
        self.assertFalse(models.Venue.get(v_k))
        self.assertFalse(models.TicketClass.get(tc_k))
        self.assertFalse(models.SeatGroup.get(sg_k))
        self.assertFalse(models.Representation.get(r_k))
        if it_k:
            self.assertFalse(models.Image.get(it_k))
        if ip_k:
            self.assertFalse(models.Image.get(ip_k))
            
        if s_k:
            self.assertFalse(models.Seat.get(s_k))


    def testDeleteNoImage(self):
        e = models.Event.all().filter('name =','Test Event (No image)').get()
        it_k = None; ip_k = None; s_k = None
        e_k = e.key()
        v_k = e.venue.key()
        sc_k = e.seat_configuration.key()
        tc_k = e.ticketclass_set.get().key()
        sg_k = models.SeatGroup.get(e.ticketclass_set.get().seat_groups[0]).key()
        r_k = e.first_representation().key()
        if e.first_representation().status != 'Draft':
            s_k = e.first_representation().seat_set.get().key()

        models.Venue.get(v_k)
        models.SeatConfiguration.get(sc_k)
        models.TicketClass.get(tc_k)
        models.SeatGroup.get(sg_k)
        models.Representation.get(r_k)
        if it_k:
            models.Image.get(it_k)
        if ip_k:
            models.Image.get(ip_k)
        if s_k:
            models.Seat.get(s_k)
     
        r = self.client.get(reverse('banian.views.delete_event',kwargs={'key':e.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        r = self.client.post(reverse('banian.views.delete_event',kwargs={'key':e.key()}),follow=True)
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        self.assertFalse(models.Event.get(e_k))
        self.assertFalse(models.Venue.get(v_k))
        self.assertFalse(models.TicketClass.get(tc_k))
        self.assertFalse(models.SeatGroup.get(sg_k))
        self.assertFalse(models.Representation.get(r_k))
        if s_k:
            self.assertFalse(models.Seat.get(s_k))

    def testShowNotOwned(self):
        e = models.Event.all().filter('name =','Test Event (No image)').get()
        createUser(self,'UserB','secret')
        r = self.client.get(reverse('banian.views.show_event',kwargs={'key':e.key()}),follow=True)
        self.assertEqual(r.status_code,404)

    def testEditNotOwned(self):
        e = models.Event.all().filter('name =','Test Event (No image)').get()
        createUser(self,'UserB','secret')
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=5',follow=True)
        self.assertEqual(r.status_code,404)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=0',
                             {'name':'toto',
                              'description':'Description here',
                              'web_site':'www.iguzu.com',
                              'email':'info@iguzu.com',
                              'next':'next'
                              },follow=True)
        self.assertEqual(r.status_code,404)
        e_after = models.Event.all().filter('name =','Test Event (No image)').get()
        self.assertNotEqual(e_after.name,'toto')
        

    def testDeleteNotOwned(self):
        e = models.Event.all().filter('name =','Test Event (No image)').get()
        createUser(self,'UserB','secret')
        r = self.client.get(reverse('banian.views.delete_event',kwargs={'key':e.key()}),follow=True)
        self.assertEqual(r.status_code,404)
        e_after = models.Event.all().filter('name =','Test Event (No image)').get()
        self.assertNotEqual(e_after,None)
        
    def testShowInvalid(self):
        r = self.client.get(reverse('banian.views.show_event',kwargs={'key':'AAA'}),follow=True)
        self.assertEqual(r.status_code,404)

    def testEditInvalid(self):
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':'AAAA'})+'?step=5',follow=True)
        self.assertEqual(r.status_code,404)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':'AAAA'})+'?step=0',
                             {'name':'toto',
                              'description':'Description here',
                              'web_site':'www.iguzu.com',
                              'email':'info@iguzu.com',
                              'next':'next'
                              },follow=True)
        self.assertEqual(r.status_code,404)

    def testEditInvalidStep(self):
        e = models.Event.all().filter('name =','Test Event (No image)').get()        
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=-1',follow=True)
        self.assertEqual(r.status_code,404)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=-1',
                             {'name':'toto',
                              'description':'Description here',
                              'web_site':'www.iguzu.com',
                              'email':'info@iguzu.com',
                              'next':'next'
                              },follow=True)
        self.assertEqual(r.status_code,404)
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=7',follow=True)
        self.assertEqual(r.status_code,404)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':e.key()})+'?step=7',
                             {'name':'toto',
                              'description':'Description here',
                              'web_site':'www.iguzu.com',
                              'email':'info@iguzu.com',
                              'next':'next'
                              },follow=True)
        self.assertEqual(r.status_code,404)

    def testDeleteInvalid(self):
        r = self.client.get(reverse('banian.views.delete_event',kwargs={'key':'AAA'}),follow=True)
        self.assertEqual(r.status_code,404)
    
    def testEditUnmutable(self):
        event = models.Event.all().filter('name =','Test Event').get()
        event = publishEvent(self, event)
        self.assertEqual(event.status,'Published')
        r = self.client.get(reverse('banian.views.edit_event',kwargs={'key':event.key()})+'?step=1')
        self.assertEqual(r.status_code,403)
        r = self.client.post(reverse('banian.views.edit_event',kwargs={'key':event.key()})+'?step=1')
        self.assertEqual(r.status_code,403)

    def testDeleteUnmutable(self):
        event = models.Event.all().filter('name =','Test Event').get()
        event = publishEvent(self, event)
        self.assertEqual(event.status,'Published')
        r = self.client.get(reverse('banian.views.delete_event',kwargs={'key':event.key()}))
        self.assertEqual(r.status_code,403)
        r = self.client.post(reverse('banian.views.delete_event',kwargs={'key':event.key()})+'?step=1')
        self.assertEqual(r.status_code,403)

    def testShowUnmutable(self):
        event = models.Event.all().filter('name =','Test Event').get()
        event = publishEvent(self, event)
        r = self.client.get(reverse('banian.views.show_event',kwargs={'key':event.key()}))
        self.assertNotContains(r, reverse('banian.views.delete_event',kwargs={'key':event.key()}))
        self.assertNotContains(r, reverse('banian.views.edit_event',kwargs={'key':event.key()}))

    def testShowSold(self):
        event = models.Event.all().filter('name =','Test Event').get()
        event = publishEvent(self, event)
        buyTickets(self, event.first_representation(), 1)
        r = self.client.get(reverse('banian.views.show_event',kwargs={'key':event.key()}))
        self.assertNotContains(r, reverse('banian.views.delete_event',kwargs={'key':event.key()}))
        self.assertNotContains(r, reverse('banian.views.edit_event',kwargs={'key':event.key()}))

        self.assertTrue(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.unpublish_representation',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content))
        self.assertTrue(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.publish',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content))        
        self.assertFalse(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.cancel_representation',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content),r.content)        
        self.assertFalse(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.validator_list',kwargs={'key':event.key()})},include_tag=True).extract(r.content))        
        self.assertFalse(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.seats',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content))        

    def testShowPublished(self):
        event = models.Event.all().filter('name =','Test Event').get()
        event = publishEvent(self, event)
        r = self.client.get(reverse('banian.views.show_event',kwargs={'key':event.key()}))
        self.assertNotContains(r, reverse('banian.views.delete_event',kwargs={'key':event.key()}))
        self.assertNotContains(r, reverse('banian.views.edit_event',kwargs={'key':event.key()}))
        self.assertFalse(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.unpublish_representation',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content),r.content)
        self.assertTrue(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.publish',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content))        
        self.assertTrue(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.cancel_representation',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content),r.content)        
        self.assertFalse(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.validator_list',kwargs={'key':event.key()})},include_tag=True).extract(r.content))        
        self.assertFalse(ElementExtracter('a',{'style':'display:none','href':reverse('banian.views.seats',kwargs={'key':event.first_representation().key()})},include_tag=True).extract(r.content))        

    def testShowcancelled(self):
        pass


class SearchEventTestCase(TestCase):
    def setUp(self):
        logging.debug('SearchEventTestCase')
        StubPaypal()
        self.user = createUser(self)
        
    def testSearchOneEvent(self):
        e= addEvent(self,self.user,'Test Event',nbr_seat=10)
        e= publishEvent(self,e)
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertContains(r,e.name,2, 200)
        if r.context:
            if isinstance(r.context,dict) and 'form' in r.context:
                self.assertEqual(len(r.context['event_list']),1)
            elif isinstance(r.context,list) and 'form' in r.context[0]:
                self.assertEqual(len(r.context[0]['event_list']),1)
        MarkupValidation(self,r.content)

    def testSearchOneEventNoImage(self):
        e= addEvent(self,self.user,str(uuid4()),nbr_seat=10,force_no_image=True)
        e= publishEvent(self,e)
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertContains(r,e.name,2, 200)
        if r.context:
            if isinstance(r.context,dict) and 'form' in r.context:
                self.assertEqual(len(r.context['event_list']),1)
                self.assertEqual(r.context['event_list'][0],e)
            elif isinstance(r.context,list) and 'form' in r.context[0]:
                self.assertEqual(len(r.context[0]['event_list']),1)
                self.assertEqual(r.context[0]['event_list'][0],e)
        MarkupValidation(self,r.content)

    def testViewEvent(self):
        e= addEvent(self,self.user,str(uuid4()),nbr_seat=10)
        e= publishEvent(self,e)
        r = self.client.get(reverse('banian.views.view_event',kwargs={'key':e.key(),}))
        self.assertContains(r,e.name,2, 200)
        if r.context:
            if isinstance(r.context,dict) and 'form' in r.context:
                self.assertEqual(r.context['object'],e)
            elif isinstance(r.context,list) and 'form' in r.context[0]:
                self.assertEqual(r.context[0]['object'],e)
        MarkupValidation(self,r.content)

    def testViewEventNoImage(self):
        e= addEvent(self,self.user,str(uuid4()),nbr_seat=10,force_no_image=True)
        e= publishEvent(self,e)
        r = self.client.get(reverse('banian.views.view_event',kwargs={'key':e.key(),}))
        self.assertContains(r,e.name,2, 200)
        if r.context:
            if isinstance(r.context,dict) and 'form' in r.context:
                self.assertEqual(r.context['object'],e)
            elif isinstance(r.context,list) and 'form' in r.context[0]:
                self.assertEqual(r.context[0]['object'],e)
        MarkupValidation(self,r.content)

    def testViewInvalidEvent(self):
        r = self.client.get(reverse('banian.views.view_event',kwargs={'key':'AAA',}),follow=True)
        self.assertEqual(r.status_code,404)

    def testSearch30Event(self):
        items=30;list=[];pages=2;paging=24
        i = 0
        while(i < items):
            list.append(str(uuid4()))
            i = i + 1
        for n in list:
            e= addEvent(self,self.user,n,nbr_seat=5)
            publishEvent(self,e)
        i = 0
        events = models.Event.all()
        self.assertEqual(events.count(100),30)
        while(i<pages-1):
            r = self.client.get(reverse('banian.views.search_events') + '?page=%d' % (i+1))
            self.assertEqual(len(r.context['event_list']),paging)
            self.assertEqual(r.context['is_paginated'],True)
            self.assertEqual(r.context['page'],i+1)
            self.assertEqual(r.context['pages'],pages)
            self.assertEqual(r.template[0].name,'banian/search_event.html')
            MarkupValidation(self,r.content)
            i = i + 1
        r = self.client.get(reverse('banian.views.search_events') + '?page=%d' % pages)
        self.assertEqual(len(r.context['event_list']),items-(pages-1)*paging)
        self.assertEqual(r.context['is_paginated'],True)
        self.assertEqual(r.context['page'],pages)
        self.assertEqual(r.context['pages'],pages)
        for n in list[pages*paging:]:
            self.assertContains(r,n,2)
        self.assertEqual(r.template[0].name,'banian/search_event.html')    
        MarkupValidation(self,r.content)

    def testSearchOutsideDistanceMi(self):
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=10,address="475, boulevard de L'Avenir, Laval H7N 5H9")
        e= publishEvent(self,e)
        self.user.distance_units = 1
        self.user.preferred_distance = 10
        self.user.put()

        r = self.client.get(reverse('banian.views.search_events'))
        logging.debug(r.context['event_list'][0].distance)

        self.assertEqual(len(r.context['event_list']),1)
        self.user.preferred_distance = 9
        self.user.put()
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertEqual(len(r.context['event_list']),0)

    def testSearchOutsideDistanceKm(self):
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=10,address="475, boulevard de L'Avenir, Laval H7N 5H9")
        e= publishEvent(self,e)
        self.user.distance_units = 2
        self.user.preferred_distance = 15
        self.user.put()
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertEqual(len(r.context['event_list']),1)
        self.user.preferred_distance = 14
        self.user.put()
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertEqual(len(r.context['event_list']),0)

    def testSearchNotShowDraftEvent(self):
        addEvent(self,self.user,str(uuid4()),nbr_seat=10)
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertEqual(len(r.context['event_list']),0)

        
    def testSearchNotShowGeneratingtEvent(self):
        e= addEvent(self,self.user,str(uuid4()),nbr_seat=10)
        e= publishEvent(self,e,do_run_tasks=False)
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertEqual(e.first_representation().status,'Generating')
        self.assertEqual(len(r.context['event_list']),0)

    def testSearchNotShowClosedtEvent(self):
        pass

    def testSearchShowOnsaletEvent(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=10),
                     onsale_date=now - timedelta(days=2),
                     endsale_date=now + timedelta(days=9))
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'On Sale')
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertEqual(len(r.context['event_list']),1)

    def testSearchShowPublishedtEvent(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=10),
                     onsale_date=now + timedelta(days=2),
                     endsale_date=now + timedelta(days=9))
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'Published')
        r = self.client.get(reverse('banian.views.search_events'))
        self.assertEqual(len(r.context['event_list']),1)

    def testSearchShowCanceltEvent(self):
        pass
        
class PublishTestCase(TestCase):
    def setUp(self):
        logging.debug('PublishTestCase')
        StubPaypal()
        self.user = createUser(self)

    def countSeats(self,representation):
        seats = banian.models.Seat.all(keys_only=True).filter('representation =', representation)
        query_count = seats.count(501)
        count = query_count
        while(query_count>500):
            seat_list = seats.fetch(501,offset=500)
            last_key = seat_list[0]
            seats = banian.models.Seat.all(keys_only=True).filter('__key__ >',last_key).filter('representation =', representation)
            query_count = seats.count(501)
            count = count + query_count
        return count

    def publish(self,number):
        e = addEvent(self,self.user,'Test Event %d' % number,nbr_seat=number)
        key = str(e.first_representation().key())
        r = self.client.get(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200,repr(r.content))
        formValidation(self,r)
        MarkupValidation(self,r.content)
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self,r)
        MarkupValidation(self,r.content)
        r = self.client.get(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self,r)
        MarkupValidation(self,r.content)
        i=0;completed = True
        while(completed or i>40):
            completed, failed = run_tasks(lapse=60) #@UnusedVariable
            i = i+1
        e = models.Event.get(e.key())
        self.assertNotEqual(e.status,'Draft',repr(e))
        self.assertNotEqual(e.first_representation().status,'Draft')
        self.assertNotEqual(e.first_representation().status,'Generating')
        self.assertEqual(number,self.countSeats(e.first_representation()))

    def testPublish(self):
        self.publish(13)
        self.publish(533)

        
    def testOnSale(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=10),
                     onsale_date=now - timedelta(days=2),
                     endsale_date=now + timedelta(days=9))
        key = str(e.first_representation().key())
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self, r)
        MarkupValidation(self,r.content)
        r = self.client.get(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self, r)
        MarkupValidation(self,r.content)
        i=0;completed = True
        while(completed or i>40):
            completed, failed = run_tasks(lapse=60) #@UnusedVariable
            i = i+1
        e = models.Event.get(e.key())
        self.assertEqual(e.status,'Published')
        self.assertEqual(e.first_representation().status,'On Sale')
        self.assertEqual(10,self.countSeats(e.first_representation()))
    
    def testPublished(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=10),
                     onsale_date=now + timedelta(days=2),
                     endsale_date=now + timedelta(days=9))
        key = str(e.first_representation().key())
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self, r)
        self.assertEqual(r.template[0].name,'banian/transfering.html')
        MarkupValidation(self,r.content)
        r = self.client.get(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self, r)
        self.assertEqual(r.template[0].name,'banian/event_detail.html')
        MarkupValidation(self,r.content)
        i=0;completed = True
        while(completed or i>40):
            completed, failed = run_tasks(lapse=60) #@UnusedVariable
            i = i+1
        e = models.Event.get(e.key())
        self.assertEqual(e.status,'Published')
        self.assertEqual(e.first_representation().status,'Published')
        self.assertEqual(10,self.countSeats(e.first_representation()))
    
    def testPastRepresentation(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now - timedelta(days=10),onsale_date=now - timedelta(days=12),endsale_date=now - timedelta(days=11))
        key = str(e.first_representation().key())
        r = self.client.get(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertContains(r, 'Cannot publish an event scheduled in the past')
        MarkupValidation(self,r.content)
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertContains(r, 'Cannot publish an event scheduled in the past')
        MarkupValidation(self,r.content)
        self.assertEqual(e.status,'Draft')
        self.assertEqual(e.first_representation().status,'Draft')
        self.assertEqual(0,self.countSeats(e.first_representation()))

    def testAlreadyPublished(self):
        e = addEvent(self,self.user,'test event',nbr_seat=10)
        e = publishEvent(self,e)
        key = str(e.first_representation().key())
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        MarkupValidation(self, r.content)

        self.assertContains(r, 'is already published')
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertContains(r, 'is already published')
        MarkupValidation(self, r.content)

    def testPastEnddate(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=10),
                     onsale_date=now - timedelta(days=5),
                     endsale_date=now - timedelta(days=1))
        key = str(e.first_representation().key())
        r = self.client.get(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertContains(r, 'Cannot publish an event with an sale end date in the past')
        MarkupValidation(self,r.content)
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertContains(r, 'Cannot publish an event with an sale end date in the past')
        MarkupValidation(self,r.content)
        self.assertEqual(e.status,'Draft')
        self.assertEqual(e.first_representation().status,'Draft')
        self.assertEqual(0,self.countSeats(e.first_representation()))

    def testNoSalePeriodLimit(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)        
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,restrict_sale_period=False,
                     date = now + timedelta(days=12),
                     onsale_date=now + timedelta(days=5),
                     endsale_date=now + timedelta(days=8))
        key = str(e.first_representation().key())
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self, r)
        MarkupValidation(self,r.content)
        r = self.client.get(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 200)
        formValidation(self, r)
        MarkupValidation(self,r.content)
        i=0;completed = True
        while(completed or i>40):
            completed, failed = run_tasks(lapse=60) #@UnusedVariable
            i = i+1
        e = models.Event.get(e.key())
        self.assertEqual(e.status,'Published')
        self.assertEqual(e.first_representation().status,'On Sale')
        self.assertEqual(10,self.countSeats(e.first_representation()))
    
    def testIncompleteSteps(self):
        e = addEvent(self,self.user,'test event',nbr_seat=10)
        e.max_step = 2
        e.put()
        key = str(e.first_representation().key())
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertContains(r, 'Complete all publishing steps before publishing')
        MarkupValidation(self,r.content)
        
    def testNotOwned(self):
        userB = createUser(self,'tata','titi',login=False)
        e = addEvent(self,userB,'test event',nbr_seat=10)
        key = str(e.first_representation().key())
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 404)

    def testInvalid(self):
        key = str('AAA')
        r = self.client.post(reverse('banian.views.publish',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 404)

    def testFreePublish(self):
        unStubPaypal()
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=200,
                     date = now + timedelta(days=10),
                     
                     onsale_date=now + timedelta(days=2),
                     endsale_date=now + timedelta(days=9),
                     price = 0.0)
        self.assertEqual(e.first_representation().publishing_cost(),0)
        self.assertEqual(e.first_representation().commission_cost(),0)
        self.assertEqual(e.first_representation().total_cost(),0)
        r = self.client.get(reverse("banian.views.publish",kwargs={'key':e.first_representation().key(),}),follow=True)
        self.assertNotContains(r, 'for publishing')
        self.assertNotContains(r, 'in comission')
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'Published')

    def testPublishingCost(self):
        StubPaypal()
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=201,
                     date = now + timedelta(days=10),
                     
                     onsale_date=now + timedelta(days=2),
                     endsale_date=now + timedelta(days=9),
                     price = 0.0)
        self.assertAlmostEqual(e.first_representation().publishing_cost(),2.01)
        self.assertEqual(e.first_representation().commission_cost(),0)
        self.assertAlmostEqual(e.first_representation().total_cost(),2.01)
        r = self.client.get(reverse("banian.views.publish",kwargs={'key':e.first_representation().key(),}),follow=True)
        self.assertContains(r, 'for publishing')
        self.assertNotContains(r, 'in comission')
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'Published')


    def testCommissionCost(self):
        StubPaypal()
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=200,
                     date = now + timedelta(days=10),
                     
                     onsale_date=now + timedelta(days=2),
                     endsale_date=now + timedelta(days=9),
                     price = 15.99)
        self.assertEqual(e.first_representation().publishing_cost(),0.0)
        self.assertEqual(e.first_representation().commission_cost(),15.99*200*0.01)
        self.assertEqual(e.first_representation().total_cost(),15.99*200*0.01)
        r = self.client.get(reverse("banian.views.publish",kwargs={'key':e.first_representation().key(),}),follow=True)
        self.assertNotContains(r, 'for publishing')
        self.assertContains(r, 'in comission')        
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'Published')

    def testCompositeCost(self):
        StubPaypal()
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=600,
                     date = now + timedelta(days=10),
                     
                     onsale_date=now + timedelta(days=2),
                     endsale_date=now + timedelta(days=9),
                     price = 15.99)
        self.assertEqual(e.first_representation().publishing_cost(),6.00)
        self.assertEqual(e.first_representation().commission_cost(),15.99*600*0.01)
        self.assertEqual(e.first_representation().total_cost(),(15.99*600*0.01)+6.00)
        r = self.client.get(reverse("banian.views.publish",kwargs={'key':e.first_representation().key(),}),follow=True)
        self.assertContains(r, 'for publishing')
        self.assertContains(r, 'in comission')
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'Published')

        
class UnpublishTestCase(TestCase):
    def setUp(self):
        logging.debug('UnpublishTestCase')
        StubPaypal()
        self.user = createUser(self,username=str(uuid4()))
        self.e = addEvent(self,self.user,str(uuid4()),nbr_seat=20)
        self.e = publishEvent(self, self.e)

    def testUnpublish(self):
        self.assertNotEqual(self.e.status,'Draft')
        r = self.client.get(reverse('banian.views.unpublish_representation', kwargs={'key':str(self.e.first_representation().key())}),follow=True)
        formValidation(self, r)
        self.assertEqual(r.status_code, 200)
        MarkupValidation(self, r.content)
        r = self.client.post(reverse('banian.views.unpublish_representation', kwargs={'key':str(self.e.first_representation().key())}),follow=True)
        self.assertEqual(r.status_code, 200)
        c,f = run_tasks(lapse=60)
        logging.debug(repr(c))
        logging.debug(repr(f))
        event = db.get(self.e.key())
        self.assertEqual(event.status,'Draft',"event:%s\nrepresentation:%s" % (repr(event),repr(event.first_representation())))
        self.assertEqual(models.Seat.all().filter('representation =',event.first_representation()).get(),None)
        self.assertEqual(models.Ticket.all().filter('representation =',event.first_representation()).get(),None)
        MarkupValidation(self, r.content)

    def testUnpublishInvalid(self):
        key = str('AAA')
        r = self.client.post(reverse('banian.views.unpublish_representation',kwargs={'key':key,}),follow=True)
        self.assertEqual(r.status_code, 404)
    
    def testUnpublishAlreadySold(self):
        buyTickets(self, self.e.first_representation(), 1)
        self.assertNotEqual(self.e.status,'Draft')
        self.assertEqual(models.Ticket.all().count(2),1)
        r = self.client.get(reverse('banian.views.unpublish_representation', kwargs={'key':str(self.e.first_representation().key())}),follow=True)
        self.assertContains(r,'already sold')
        MarkupValidation(self,r.content)
        r = self.client.post(reverse('banian.views.unpublish_representation', kwargs={'key':str(self.e.first_representation().key())}),follow=True)
        self.assertContains(r,'already sold')
        MarkupValidation(self, r.content)
        run_tasks(lapse=60)
        event = db.get(self.e.key())
        self.assertNotEqual(event.status,'Draft')
        self.assertEqual(r.status_code, 200)
    def testCancel(self):
        pass

class ListMyEventTestCase(TestCase):
    def setUp(self):
        logging.debug('ListMyEventTestCase')
        StubPaypal()
        self.user = createUser(self)
    
    def testNoEvent(self):
        r = self.client.get(reverse('banian.views.events'))
        self.assertContains(r,'to create an event')
        self.assertEqual(len(r.context['event_list']),0)
        self.assertEqual(r.template[0].name,'banian/event_list.html')
        MarkupValidation(self,r.content)
        
    def testOneEvent(self):
        u = str(uuid4())
        addEvent(self,self.user,u,nbr_seat=20)
        r = self.client.get(reverse('banian.views.events'))
        self.assertContains(r,u)
        self.assertEqual(len(r.context['event_list']),1)
        self.assertEqual(r.context['is_paginated'],0)
        self.assertEqual(r.template[0].name,'banian/event_list.html')
        MarkupValidation(self,r.content)

    def test5Event(self):
        i=5;list= []
        while(i):
            list.append(str(uuid4()))
            i = i - 1
        for n in list:
            addEvent(self,self.user,n,nbr_seat=20)
        r = self.client.get(reverse('banian.views.events'))
        for n in list:
            self.assertContains(r,n)
        self.assertEqual(len(r.context['event_list']),5)
        self.assertEqual(r.context['is_paginated'],0)
        self.assertEqual(r.template[0].name,'banian/event_list.html')
        MarkupValidation(self,r.content)
    
    def test6Event(self):
        i=6;list= []
        while(i):
            list.append(str(uuid4()))
            i = i - 1
        for n in list:
            addEvent(self,self.user,n,nbr_seat=20)
        r = self.client.get(reverse('banian.views.events'))
        for n in list[0:5]:
            self.assertContains(r,n)
        self.assertEqual(len(r.context['event_list']),5)
        self.assertEqual(r.context['is_paginated'],True)
        self.assertEqual(r.context['page'],1)
        self.assertEqual(r.context['pages'],2)
        self.assertEqual(r.template[0].name,'banian/event_list.html')
        MarkupValidation(self,r.content)
        r = self.client.get(reverse('banian.views.events')+ '?page=2')
        self.assertEqual(len(r.context['event_list']),1)
        self.assertEqual(r.context['is_paginated'],True)
        self.assertEqual(r.context['page'],2)
        self.assertEqual(r.context['pages'],2)
        for n in list[5:6]:
            self.assertContains(r,n)
        self.assertEqual(r.template[0].name,'banian/event_list.html')    
        MarkupValidation(self,r.content)

    def test13Event(self):
        items=13;list= [];pages=3;paging=5
        i = 0
        while(i < items):
            list.append(str(uuid4()))
            i = i + 1
        for n in list:
            addEvent(self,self.user,n,nbr_seat=20)
        i = 0
        while(i<pages-1):
            r = self.client.get(reverse('banian.views.events') + '?page=%d' % (i+1))
            for n in list[i*paging:i*paging+paging]:
                self.assertContains(r,n)
            self.assertEqual(len(r.context['event_list']),paging)
            self.assertEqual(r.context['is_paginated'],True)
            self.assertEqual(r.context['page'],i+1)
            self.assertEqual(r.context['pages'],pages)
            self.assertEqual(r.template[0].name,'banian/event_list.html')
            MarkupValidation(self,r.content)
            i = i + 1

        r = self.client.get(reverse('banian.views.events') + '?page=%d' % pages)
        self.assertEqual(len(r.context['event_list']),items-(pages-1)*paging)
        self.assertEqual(r.context['is_paginated'],True)
        self.assertEqual(r.context['page'],pages)
        self.assertEqual(r.context['pages'],pages)
        for n in list[pages*paging:]:
            self.assertContains(r,n)
        self.assertEqual(r.template[0].name,'banian/event_list.html')    
        MarkupValidation(self,r.content)

#    def test600Event(self):
#        items=600;list= [];pages=120;paging=5
#        i = 0
#        while(i < items):
#            list.append(str(uuid4()))
#            i = i + 1
#        for n in list:
#            addEvent(self,self.user,n)
#        r = self.client.get(reverse('banian.views.events'))
#        for n in list[0:5]:
#            self.assertContains(r,n)
#        self.assertEqual(len(r.context['event_list']),paging)
#        self.assertEqual(r.context['is_paginated'],True)
#        self.assertEqual(r.context['page'],1)
#        self.assertEqual(r.context['pages'],101)
#        self.assertEqual(r.template[0].name,'banian/event_list.html')
#        MarkupValidation(self,r.content)
        
    def testEventfromMultipleUsers(self):
        userB = createUser(self,'B',login=False)
        a = str(uuid4())
        b = str(uuid4())
        addEvent(self,self.user,name=a)
        addEvent(self,userB,b)
        r = self.client.get(reverse('banian.views.events'))
        self.assertContains(r,a)
        self.assertNotContains(r,b)
        self.assertEqual(len(r.context['event_list']),1)
        self.assertEqual(r.context['is_paginated'],0)
        self.assertEqual(r.template[0].name,'banian/event_list.html')
        MarkupValidation(self,r.content)
    
    def testNoImage(self):
        u = str(uuid4())
        addEvent(self,self.user,u,force_no_image=True)
        r = self.client.get(reverse('banian.views.events'))
        self.assertContains(r,u)
        self.assertEqual(len(r.context['event_list']),1)
        self.assertEqual(r.context['is_paginated'],0)
        self.assertEqual(r.template[0].name,'banian/event_list.html')
        MarkupValidation(self,r.content)


class DoormansTestCase(TestCase):
    def setUp(self):
        logging.debug('DoormansTestCase')
        StubPaypal()
        self.user = createUser(self,username=str(uuid4()))
        self.e = addEvent(self,self.user,'test',nbr_seat=10)
        self.e = publishEvent(self, self.e)

    def testShowList(self):
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}))
        self.assertContains(r,self.user.username)
        MarkupValidation(self,r.content)

    def testInvalidEvent(self):
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':'A'}),follow=True)
        self.assertEqual(r.status_code, 404)
        MarkupValidation(self,r.content)
    
    def testDeleteOwner(self):
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?del=del&key=%s'% self.user.key(),HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['error'],True)
        self.assertEqual(data['message_html'],'You cannot delete yourself')
    
    def testAddDoormans(self):
        userA = createUser(self,str(uuid4()),login=False)
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=add&username=%s'% userA.username,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['error'],False)
        self.assertEqual(data['message_html'],'Successfully added %s' % userA.username )
        self.assertEqual(data['name'],userA.name )
        self.assertEqual(data['username'],userA.username )

    def testMalformedAjax(self):
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=add&ername=%s'% '',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,500)
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,500)
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?ad=',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,500)

    def testDeleteDoormans(self):
        userA = createUser(self,str(uuid4()),login=False)
        self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=add&username=%s'% userA.username,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}))
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)
        self.assertContains(r,userA.username)
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?del=del&key=%s'% userA.key(),HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['error'],False,data)
        self.assertEqual(data['message_html'],'Successfully removed %s' % userA.username,data)
        self.assertEqual(data['name'],userA.name,data)
        self.assertEqual(data['username'],userA.username,data)        
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}),data)
        self.assertNotContains(r,userA.username)
                
    def testAddListDelete10Doormans(self):
        i=10;list= []
        while(i):
            u = createUser(self,str(uuid4()),name=str(uuid4()),login=False)
            list.append(u)
            self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=add&username=%s'% u.username,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            i = i - 1

        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}))
        for u in list:
            self.assertContains(r,u.username)
            self.assertContains(r,u.name)
        MarkupValidation(self,r.content)    
        for u in list:
            r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?del=del&key=%s'% u.key(),HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            data = loads(r.content)
            self.assertEqual(data['error'],False,data)
            self.assertEqual(data['message_html'],'Successfully removed %s' % u.username,data)
            self.assertEqual(data['name'],u.name,data)
            self.assertEqual(data['username'],u.username,data)        
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}),data)
        for u in list:
            self.assertNotContains(r,u.username)
            self.assertNotContains(r,u.name)
        MarkupValidation(self,r.content)


    def testAddInvalidDoorman(self):
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=add&username=%s'% 'AAA',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['error'],True,data)
        self.assertEqual(data['message_html'],'Invalid unsername',data)
        self.assertEqual(data['name'],'',data)
        self.assertEqual(data['username'],'',data)

    def TestAddAlreadyAdded(self):
        userA = createUser(self,str(uuid4()),login=False)
        self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=add&username=%s'% userA.username,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?add=add&username=%s'% userA.username,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['error'],True,data)
        self.assertEqual(data['message_html'],'Already added %s' % userA.username,data)
        self.assertEqual(data['name'],'',data)
        self.assertEqual(data['username'],'',data)
    
    def testDeleteInvalidID(self):
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?del=del&key=%s'% 'AAA',HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,500)
    
    def testDeleteUserNotInList(self):
        userA = createUser(self,str(uuid4()),login=False)
        r = self.client.get(reverse('banian.views.validator_list',kwargs ={'key':self.e.key()}) + '?del=del&key=%s'% userA.key(),HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['error'],False,data)
        self.assertEqual(data['message_html'],'Nothing to do, user not in the list',data)
        self.assertEqual(data['name'],'',data)
        self.assertEqual(data['username'],'',data)
        self.assertEqual(data['key'],str(userA.key()))

    def testAddDelete3Users(self):
        pass
    
class BuyTestCase(TestCase):
    def setUp(self):
        logging.debug('BuyTestCase')
        StubPaypal()
        self.user = createUser(self,username=str(uuid4()))
        self.e = addEvent(self,self.user,'test',nbr_seat=10)
        self.e = publishEvent(self, self.e)

    def testBuyNotInSaleYet(self):
        pass

    def testBuySoldOut(self):
        pass

    def testBuyClosed(self):
        pass

    def testBuyPast(self):
        pass


    def testBuy(self):
        rep = self.e.first_representation()
        r = buyTickets(self,rep,5)
        self.assertEqual(r.status_code,200)
        formValidation(self, r)
        run_tasks(lapse=60)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),5)
        r = buyTickets(self,rep,3)
        self.assertEqual(r.status_code,200)
        formValidation(self, r)
        run_tasks(lapse=60)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),8)


    def testBuyTooMany(self):
        self.e.limit_tickets = True
        self.e.max_tickets = 6
        self.e.put()
        rep = self.e.first_representation()
        r = buyTickets(self,rep,11)
        self.assertEqual(r.status_code,200)
        self.assertContains(r, 'Cannot complete the purchase, you attempt to purchase too many tickets')
        run_tasks(lapse=60)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),0)

    def testBuyOverLimitSinglePurchase(self):
        self.e.limit_tickets = True
        self.e.max_tickets = 6
        self.e.put()
        rep = self.e.first_representation()
        r = buyTickets(self,rep,7)
        self.assertEqual(r.status_code,200)
        self.assertContains(r, 'Cannot complete the purchase, you attempt to purchase too many tickets')
        run_tasks(lapse=60)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),0)

    def testBuyOverLimitMultiplePurchase(self):
        self.e.limit_tickets = True
        self.e.max_tickets = 6
        self.e.put()
        rep = self.e.first_representation()
        r = buyTickets(self,rep,6)
        self.assertEqual(r.status_code,200)
        formValidation(self, r)
        run_tasks(lapse=60)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),6)
        r = buyTickets(self,rep,1)
        self.assertEqual(r.status_code,200)        
        self.assertContains(r, 'Cannot complete the purchase, you attempt to purchase too many tickets')
        run_tasks(lapse=60)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),6)

    def testAvailableCount(self):
        pass

    def testMultiUserAvailableCount(self):
        pass


class AccountSettingsTestCase(TestCase):
    def setUp(self):
        logging.debug('AccountSettingsTestCase')
        self.user = createUser(self,username=str(uuid4()))

    def testAccountSettingPageRender(self):
        r = self.client.get(reverse('banian.views.settings'))
        self.assertContains(r,self.user.username)
        MarkupValidation(self,r.content)

    def testChangePasswordPageRender(self):
        r = self.client.get("/account/password/reset/")
        self.assertEqual(r.status_code,200)
        MarkupValidation(self,r.content)

    def testSetName(self):
        name = 'SBL'
        r = self.client.post(reverse('banian.views.settings'),{'name':name,'time_format':1},follow=True)
        self.assertEqual(r.status_code,200)
        formValidation(self, r)
        u = models.User.get(self.user.key()) #@UndefinedVariable
        self.assertEqual(u.name,name)
        MarkupValidation(self,r.content)

    def testSetAddress(self):
        address = '2855 rue centre, montreal'
        r = self.client.post(reverse('banian.views.settings'),{'address':address,'time_format':1},follow=True)
        self.assertEqual(r.status_code,200)
        formValidation(self, r)
        u = models.User.get(self.user.key()) #@UndefinedVariable
        self.assertEqual(u.address,address)
        MarkupValidation(self,r.content)

    def testSetPaypalID(self):
        paypal_id = 'seller_1259638970_biz@iguzu.com'
        r = self.client.post(reverse('banian.views.settings'),{'paypal_id':paypal_id,'time_format':1},follow=True)
        self.assertEqual(r.status_code,200)
        formValidation(self, r)
        u = models.User.get(self.user.key()) #@UndefinedVariable
        self.assertEqual(u.paypal_id,paypal_id)    
        MarkupValidation(self,r.content)

    def testSetTimeFormat(self):
        time_format = 2
        r = self.client.post(reverse('banian.views.settings'),{'time_format':2},follow=True)
        self.assertEqual(r.status_code,200)
        formValidation(self, r)
        u = models.User.get(self.user.key()) #@UndefinedVariable
        self.assertEqual(u.time_format,time_format)

    def testSetInvalidAddress(self):
        address = 'tata'
        r = self.client.post(reverse('banian.views.settings'),{'address':address,'time_format':1},follow=True)
        self.assertEqual(r.status_code,200)
        self.assertContains(r, 'Location is not accurate enough')
        u = models.User.get(self.user.key()) #@UndefinedVariable
        self.assertNotEqual(u.address,address)
        MarkupValidation(self,r.content)

    def testSetInaccurateAddress(self):
        address = 'springfield,usa'
        r = self.client.post(reverse('banian.views.settings'),{'address':address,'time_format':1},follow=True)
        self.assertEqual(r.status_code,200)
        self.assertContains(r, 'Location is not accurate enough')
        self.assertContains(r, 'address returned more than one results')
        u = models.User.get(self.user.key()) #@UndefinedVariable
        self.assertNotEqual(u.address,address)
        MarkupValidation(self,r.content)
        
    def testSetInvalidPaypalID(self):
        paypal_id = 'admin'
        r = self.client.post(reverse('banian.views.settings'),{'paypal_id':paypal_id,'time_format':1},follow=True)
        self.assertEqual(r.status_code,200)
        self.assertContains(r, "Enter a valid e-mail address")
        u = models.User.get(self.user.key()) #@UndefinedVariable
        self.assertNotEqual(u.paypal_id,paypal_id)
        MarkupValidation(self,r.content)        

class UserEventTestCase(TestCase):
    def setUp(self):
        logging.debug('UserEventTestCase')
        StubPaypal()
        self.user = createUser(self,username=str(uuid4()))
        self.e = addEvent(self,self.user,str(uuid4()),nbr_seat=20)
        self.e = publishEvent(self, self.e)


    def testUserEvents(self):
        rep = self.e.first_representation()
        buyTickets(self,rep,5)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),5)
        buyTickets(self,rep,3)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),8)
        ue = models.UserEvent.all().filter('representation =',rep).filter('owner = ',self.user)
        self.assertEqual(ue.count(2),1)
        ue = ue.get()
        self.assertEqual(ue.nbr_tickets,8)
        r = self.client.get(reverse('banian.views.user_events'))
        self.assertContains(r,self.e.name)
        self.assertEqual(len(r.context['event_list']),1)
        MarkupValidation(self, r.content)


    def testMultiUserPurchaseUserEvent(self):
        rep = self.e.first_representation()
        userA = self.user
        userB = createUser(self, str(uuid4()), 'secret', login=False)
        ## Buy userA
        buyTickets(self,rep,5)
        buyTickets(self,rep,3)
        ## Buy userB
        self.client.login(username=userB.username,password='secret')
        buyTickets(self,rep,5)
        buyTickets(self,rep,5)
        self.assertEqual(models.Ticket.all().filter('representation =',rep).count(1000),18)
      
        ue = models.UserEvent.all().filter('representation =',rep).filter('owner = ',userA)
        self.assertEqual(ue.count(2),1)
        ue = ue.get()
        self.assertEqual(ue.nbr_tickets,8)

        ue = models.UserEvent.all().filter('representation =',rep).filter('owner = ',userB)
        self.assertEqual(ue.count(2),1)
        ue = ue.get()
        self.assertEqual(ue.nbr_tickets,10)
        
        r = self.client.get(reverse('banian.views.user_events'))
        self.assertContains(r,self.e.name)
        self.assertEqual(len(r.context['event_list']),1)

        self.client.login(username=userA.username,password='secret')
        r = self.client.get(reverse('banian.views.user_events'))
        self.assertContains(r,self.e.name)
        self.assertEqual(len(r.context['event_list']),1)


    def testUserEvent12Events(self):
        items=12;list= [];events = [];pages=2;paging=10
        i =0
        while(i<items):
            list.append(str(i+1))
            i = i + 1
        for n in list:
            e = addEvent(self,self.user,n,nbr_seat=20)
            e = publishEvent(self, e)
            events.append(e)
        for e in events:
            buyTickets(self,e.first_representation(),7)
        self.assertEqual(models.Ticket.all().count(1000),12*7)
        i = 0
        while(i<pages-1):
            r = self.client.get(reverse('banian.views.user_events') + '?page=%d' % (i+1))
            self.assertEqual(len(r.context['event_list']),paging)
            self.assertEqual(r.context['is_paginated'],True)
            self.assertEqual(r.context['page'],i+1)
            self.assertEqual(r.context['pages'],pages)
            self.assertEqual(r.template[0].name,'banian/userevent_list.html')
            MarkupValidation(self,r.content)
            i = i + 1
        r = self.client.get(reverse('banian.views.user_events') + '?page=%d' % pages)
        self.assertEqual(len(r.context['event_list']),items-(pages-1)*paging)
        self.assertEqual(r.context['is_paginated'],True)
        self.assertEqual(r.context['page'],pages)
        self.assertEqual(r.context['pages'],pages)

    def testUserEventDetails(self):
        rep = self.e.first_representation()
        buyTickets(self,rep,5)
        ue = models.UserEvent.all().filter('representation =',rep).filter('owner = ',self.user).get()
        r = self.client.get(reverse('banian.views.show_user_event',kwargs={'key':str(ue.key()),}))
        self.assertContains(r, self.e.name)
        MarkupValidation(self,r.content)


class DownloadTicketTestCase(TestCase):
    def setUp(self):
        logging.debug('DownloadTicketTestCase')
        StubPaypal()
        self.user = createUser(self,username=str(uuid4()))
        self.e = addEvent(self,self.user,str(uuid4()),nbr_seat=20)
        self.e = publishEvent(self, self.e)
        buyTickets(self, self.e.first_representation(), 5)
        buyTickets(self, self.e.first_representation(), 5)
    
    def testDownloadTicket(self):
        tickets = models.Ticket.all().filter('representation =',self.e.first_representation()).filter('owner =',self.user).fetch(1000)
        for ticket in tickets:
            r = self.client.get(reverse('banian.views.download_ticket', kwargs={'key':str(ticket.key()),}))
            self.assertContains(r, ticket.t_id)
            MarkupValidation(self, r.content)

    def testDownloadTicketMultiUE(self):        
        ue = models.UserEvent.all().filter('representation =',self.e.first_representation()).filter('owner = ',self.user).get()
        tickets = models.Ticket.all().filter('representation =',self.e.first_representation()).filter('owner =',self.user).fetch(1000)
        r = self.client.get(reverse('banian.views.download_tickets') + '?user_event_key=%s' % ue.key(),follow=True)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context['ticket_set'].count(1000),10)
        for ticket in tickets:
            self.assertContains(r, ticket.t_id)
        MarkupValidation(self, r.content)

    def testDownloadTicketMultiTr(self):        
        transactions = models.Transaction.all().filter('representation =',self.e.first_representation()).filter('owner = ',self.user).fetch(1000)
        for transaction in transactions:
            r = self.client.get(reverse('banian.views.download_tickets') + '?transaction_key=%s' % transaction.key())
            self.assertEqual(r.context['ticket_set'].count(1000),5)
            tickets = models.Ticket.all().filter('transaction =',transaction).fetch(1000)
            self.assertTrue(tickets)
            for ticket in tickets:
                self.assertContains(r, ticket.t_id)
            MarkupValidation(self, r.content)

    def testDownloadMultiInvalid(self):        
        r = self.client.get(reverse('banian.views.download_tickets') + '?user_event_key=%s' % 'AAA',follow=True)
        self.assertEqual(r.status_code,404)
        MarkupValidation(self, r.content)

    def testDownloadMultiBadParam(self):        
        r = self.client.get(reverse('banian.views.download_tickets') + '?toto=%s' % 'AAA')
        self.assertEqual(r.status_code,404)

    def testDownloadMultiNotOwned(self):
        createUser(self, str(uuid4()), 'secret')  
        transaction = models.Transaction.all().filter('representation =',self.e.first_representation()).filter('owner = ',self.user).get()
        r = self.client.get(reverse('banian.views.download_tickets') + '?transaction_key=%s' % transaction.key(),follow=True)
        self.assertEqual(r.status_code,404)
        MarkupValidation(self, r.content)

    def testDownloadTicketIdentical(self):
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20)
        e = publishEvent(self, e)
        buyTickets(self, e.first_representation(), 1)
        ue = models.UserEvent.all().filter('representation =',e.first_representation()).filter('owner = ',self.user).get()
        tickets = models.Ticket.all().filter('representation =',e.first_representation()).filter('owner =',self.user).fetch(1000)
        r = self.client.get(reverse('banian.views.download_tickets') + '?user_event_key=%s' % ue.key(),follow=True)
        r2 = self.client.get(reverse('banian.views.download_ticket',kwargs={'key':str(tickets[0].key())}),follow=True)
        self.assertEqual(r.status_code,200)
        table = ElementExtracter('table',{'class':'ticket'})
        html_multi = table.extract(r.content)
        html_single = table.extract(r2.content)
        self.assertEqual(html_multi,html_single,'***\n%s\n***\n%s' % (html_multi,html_single))
        self.assertEqual(r.context['ticket_set'].count(1000),1)
    
    def testDownloadTicketInvalidKey(self):
        r = self.client.get(reverse('banian.views.download_ticket', kwargs={'key':'AAA',}),follow=True)
        self.assertEqual(r.status_code,404)
        MarkupValidation(self, r.content)
            
    def testDownloadTicketNotOwned(self):
        ticket = models.Ticket.all().filter('representation =',self.e.first_representation()).filter('owner =',self.user).get()
        createUser(self, str(uuid4()), 'secret')
        r = self.client.get(reverse('banian.views.download_ticket', kwargs={'key':str(ticket.key()),}),follow=True)
        self.assertEqual(r.status_code,404)
        MarkupValidation(self, r.content)
  
    def testDownloadTicketNoImage(self):
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,force_no_image=True)
        eventB = publishEvent(self, eventB)        
        buyTickets(self, eventB.first_representation(), 5)
        ticket = models.Ticket.all().filter('representation =',eventB.first_representation()).filter('owner =',self.user).get()
        r = self.client.get(reverse('banian.views.download_ticket', kwargs={'key':str(ticket.key()),}))
        self.assertContains(r, ticket.t_id)
        MarkupValidation(self, r.content)


    def testDownloadMultiNoImage(self):
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,force_no_image=True)
        eventB = publishEvent(self, eventB)
        buyTickets(self, eventB.first_representation(), 5)
        ue = models.UserEvent.all().filter('representation =',eventB.first_representation()).filter('owner = ',self.user).get()
        tickets = models.Ticket.all().filter('representation =',eventB.first_representation()).filter('owner =',self.user).fetch(1000)
        r = self.client.get(reverse('banian.views.download_tickets') + '?user_event_key=%s' % ue.key(),follow=True)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context['ticket_set'].count(1000),5)
        self.assertTrue(tickets)
        for ticket in tickets:
            self.assertContains(r, ticket.t_id)
        MarkupValidation(self, r.content)
    
    def testGeneralAdmission(self):
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,general_admission=True)
        eventB = publishEvent(self, eventB)
        buyTickets(self, eventB.first_representation(), 5)
        ticket = models.Ticket.all().filter('representation =',eventB.first_representation()).filter('owner =',self.user).get()                
        self.assertTrue(ticket.general_admission)
        r = self.client.get(reverse('banian.views.download_ticket', kwargs={'key':str(ticket.key()),}))
        self.assertContains(r, 'General Admission')
        self.assertNotContains(r, 'Seat Number:')
        MarkupValidation(self, r.content)
        
    
    def testNoGeneralAdmission(self):
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,general_admission=False)
        eventB = publishEvent(self, eventB)
        buyTickets(self, eventB.first_representation(), 5)
        ticket = models.Ticket.all().filter('representation =',eventB.first_representation()).filter('owner =',self.user).get()
        r = self.client.get(reverse('banian.views.download_ticket', kwargs={'key':str(ticket.key()),}))
        self.assertContains(r, 'Seat Number:')
        self.assertNotContains(r, 'General Admission')
        MarkupValidation(self, r.content)

    def testNote(self):
        note = str(uuid4())
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,general_admission=False,note=note)
        eventB = publishEvent(self, eventB)
        buyTickets(self, eventB.first_representation(), 5)
        ticket = models.Ticket.all().filter('representation =',eventB.first_representation()).filter('owner =',self.user).get()        
        r = self.client.get(reverse('banian.views.download_ticket', kwargs={'key':str(ticket.key()),}))
        self.assertContains(r,note)

class TransactionTestCase(TestCase):
    def setUp(self):
        logging.debug('TransactionTestCase')
        StubPaypal()
        self.user = createUser(self,username=str(uuid4()))
        self.e = addEvent(self,self.user,str(uuid4()),nbr_seat=40)
        self.e = publishEvent(self, self.e)
        rep = self.e.first_representation()
        buyTickets(self,rep,5)
        buyTickets(self,rep,5)


    def testTransactions(self):
        logging.debug('testTransactions')
        transaction = models.Transaction.all().filter('owner = ',self.user)
        self.assertEqual(transaction.count(3),2)
        transaction = transaction.get()
        self.assertEqual(transaction.nbr_tickets,5)
        r = self.client.get(reverse('banian.views.transactions'))
        self.assertContains(r,self.e.name)
        self.assertEqual(len(r.context['transaction_list']),2)
        MarkupValidation(self, r.content)

    def testTransactionDetail(self):
        logging.debug('testTransactionDetail')
        transactions = models.Transaction.all().filter('owner = ',self.user)
        self.assertEqual(transactions.count(3),2)
        for transaction in transactions:
            r = self.client.get(reverse('banian.views.show_transaction',kwargs={'key':str(transaction.key()),}))
            self.assertContains(r,self.e.name)
            self.assertEqual(r.context['object'],transaction)
            MarkupValidation(self, r.content)

    def testTransactionNoImage(self):
        logging.debug('testTransactionNoImage')
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,force_no_image=True)
        eventB = publishEvent(self, eventB)
        buyTickets(self, eventB.first_representation(), 5)
        buyTickets(self, eventB.first_representation(), 5)
        r = self.client.get(reverse('banian.views.transactions'))
        self.assertContains(r,self.e.name)
        self.assertEqual(len(r.context['transaction_list']),4)
        MarkupValidation(self, r.content)
        transactions = models.Transaction.all().filter('owner = ',self.user).filter('representation =',eventB.first_representation())
        self.assertEqual(transactions.count(3),2)        
        for transaction in transactions:
            r = self.client.get(reverse('banian.views.show_transaction',kwargs={'key':str(transaction.key()),}))
            self.assertContains(r,eventB.name)
            self.assertEqual(r.context['object'],transaction)
            MarkupValidation(self, r.content)
    
    def testTransactionsFree(self):
        logging.debug('testTransactionsFree')
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,force_no_image=True,price=0.0)
        eventB = publishEvent(self, eventB)
        transaction = models.Transaction.all().filter('owner =',self.user)
        buyTickets(self, eventB.first_representation(), 5)
        buyTickets(self, eventB.first_representation(), 5)
        self.assertEqual(transaction.count(5),4)
        transactions = models.Transaction.all().filter('owner =',self.user).filter('representation =',eventB.first_representation()).fetch(100)
        self.assertEqual(len(transactions),2)
        for transaction in transactions:
            self.assertEqual(transaction.total_amount,0.0)
        r = self.client.get(reverse('banian.views.transactions'))
        self.assertContains(r,'0.00 $',2)
        self.assertEqual(len(r.context['transaction_list']),4)
        MarkupValidation(self, r.content)

    def testTransactionFree(self):
        logging.debug('testTransactionFree')
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20,force_no_image=True,price=0.0)
        eventB = publishEvent(self, eventB)
        buyTickets(self, eventB.first_representation(), 5)
        buyTickets(self, eventB.first_representation(), 5)        
        transactions = models.Transaction.all().filter('owner = ',self.user).filter('representation =',eventB.first_representation()).fetch(1000)
        logging.debug(models.Transaction.all().count(100))        
        self.assertEqual(len(transactions),2)
        for transaction in transactions:
            r = self.client.get(reverse('banian.views.show_transaction',kwargs={'key':str(transaction.key()),}))
            self.assertContains(r,'0.00 $')
            self.assertEqual(r.context['object'],transaction)
            MarkupValidation(self, r.content)
    
    def test22Transactions(self):
        logging.debug('test22Transactions')
        items=22;pages=3;paging=10
        i = items-2
        rep = self.e.first_representation()
        while(i):
            i=i-1
            buyTickets(self,rep,1)
        transactions = models.Transaction.all().filter('owner = ',self.user).fetch(1000)
        self.assertEqual(len(transactions),22)
        i = 0
        while(i<pages-1):
            r = self.client.get(reverse('banian.views.transactions') + '?page=%d' % (i+1))
            for n in transactions[pages*paging:]:
                self.assertContains(r,n)
                self.assertEqual(len(r.context['transaction_list']),paging)
                self.assertEqual(r.context['is_paginated'],True)
                self.assertEqual(r.context['page'],i+1)
                self.assertEqual(r.context['pages'],pages)
                self.assertEqual(r.template[0].name,'banian/transaction_list.html')
                MarkupValidation(self,r.content)
            i = i + 1
        r = self.client.get(reverse('banian.views.transactions') + '?page=%d' % pages)
        self.assertEqual(len(r.context['transaction_list']),items-(pages-1)*paging)
        self.assertEqual(r.context['is_paginated'],True)
        self.assertEqual(r.context['page'],pages)
        self.assertEqual(r.context['pages'],pages)
        for n in transactions[pages*paging:]:
            self.assertContains(r,n)
        self.assertEqual(r.template[0].name,'banian/transaction_list.html')    
        MarkupValidation(self,r.content)

    
    def testTransactionsMultipleUser(self):
        logging.debug('testTransactionsMultipleUser')
        userB = createUser(self,username=str(uuid4()))
        rep = self.e.first_representation()
        buyTickets(self,rep,5)
        buyTickets(self,rep,5)
        transaction = models.Transaction.all().filter('owner = ',userB)
        self.assertEqual(transaction.count(3),2)
        transaction = transaction.get()
        self.assertEqual(transaction.nbr_tickets,5)
        r = self.client.get(reverse('banian.views.transactions'))
        self.assertContains(r,self.e.name)
        self.assertEqual(len(r.context['transaction_list']),2)
        MarkupValidation(self, r.content)
        
    def testMultipleEvents(self):
        logging.debug('testMultipleEvents')
        eventB = addEvent(self,self.user,str(uuid4()),nbr_seat=20)
        eventB = publishEvent(self, eventB)
        rep = eventB.first_representation()
        buyTickets(self,rep,5)
        buyTickets(self,rep,5)
        r = self.client.get(reverse('banian.views.transactions'))
        self.assertContains(r,self.e.name)
        self.assertContains(r,eventB.name)
        self.assertEqual(len(r.context['transaction_list']),4)
        MarkupValidation(self, r.content)

class TasksTestCase(TestCase):
    pass

class ValidationTestCase(TestCase):
    def setUp(self):
        logging.debug('ValidationTestCase')
        StubPaypal()
        self.user = createUser(self,username=str(uuid4()))

    def testEventListEmpty(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=10)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        self.assertTrue(self.user.key() in e.validators,e.validators)
        r = self.client.get(reverse('banian.views.validation_list'))
        self.assertEqual(len(r.context['event_list']),0)
        MarkupValidation(self,r.content)
        
    def testEvent1InList(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validation_list'))
        self.assertContains(r, e.name)
        self.assertEqual(len(r.context['event_list']),1)
        MarkupValidation(self,r.content)

    def testEvent10InList(self):
        i=10;list= []
        while(i):
            list.append(str(uuid4()))
            i = i - 1
        for n in list:
            date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
            onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
            e = addEvent(self,self.user,n,nbr_seat=20,date=date,onsale_date=onsale_date)
            publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validation_list'))
        for n in list:
            self.assertContains(r,n)
        self.assertEqual(len(r.context['event_list']),10)
        self.assertEqual(r.context['is_paginated'],0)
        self.assertEqual(r.template[0].name,'banian/validation_list.html')
        MarkupValidation(self,r.content)
    
    def testList1on2(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=10)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e1 = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e1 = publishEvent(self, e1)
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e2 = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e2 = publishEvent(self, e2)        
        r = self.client.get(reverse('banian.views.validation_list'))
        self.assertNotContains(r, 'e1.name')
        self.assertContains(r, e2.name)
        self.assertEqual(len(r.context['event_list']),1)
        MarkupValidation(self,r.content)


    def testShowValidateRepTickets(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}))
        self.assertContains(r,e.name)
        MarkupValidation(self, r.content)
    
    def testValidateRepNotIn48Hours(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=10)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}),follow=True)
        self.assertEqual(r.status_code,403)

    def testValidateNotOwned(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        createUser(self, 'UserB', 'secret')
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}),follow=True)
        self.assertEqual(r.status_code,404)

    def testInvalidRepresentation(self):
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':'AAA'}),follow=True)
        self.assertEqual(r.status_code,404)

    def testValidateInDoormanList(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        userB = createUser(self, 'UserB', 'secret')
        e.validators.append(userB.key())
        e.put()
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}),follow=True)
        self.assertContains(r,e.name)
        MarkupValidation(self, r.content)
    
    def testLookupTicket(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        buyTickets(self, e.first_representation(),1)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?seat_number=1',follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)        
        s = models.Seat.all().filter('representation =',e.first_representation()).filter('number =',1).get()
        self.assertEqual(data['t_id'],s.current_ticket().t_id)
        self.assertEqual(data['message_html'],'Lookup Sucessful, Validate paper ticket')
        self.assertEqual(data['error'],False)
        self.assertEqual(r.status_code,200)

    def testLookupTicketInvalidSeatValue(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?seat_number=AAA',follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['t_id'],'')
        self.assertEqual(data['message_html'],'Invalid Seat Number')
        self.assertEqual(data['error'],True)
        self.assertEqual(r.status_code,200)



    def testLookupTicketInvalidParam(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?AAA=OOO',follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,404)


    def testLookupOutOfRangeSeat(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?seat_number=21',follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)
        self.assertEqual(data['t_id'],'')
        self.assertEqual(data['message_html'],'Invalid Seat Number')
        self.assertEqual(data['error'],True)
        self.assertEqual(r.status_code,200)
    
    def testLookupNoTicket(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?seat_number=1',follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)        
        s = models.Seat.all().filter('representation =',e.first_representation()).filter('number =',1).get()
        self.assertEqual(data['t_id'],'')
        self.assertEqual(data['message_html'],'No ticket sold for this seat')
        self.assertEqual(data['error'],True)
        self.assertEqual(r.status_code,200)

    def testTicketAlreadyScanned(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        buyTickets(self, e.first_representation(),1)
        s = models.Seat.all().filter('representation =',e.first_representation()).filter('number =',1).get()
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?ticket_id=%s' % s.current_ticket().t_id,follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,200)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?seat_number=1',follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = loads(r.content)        
        self.assertEqual(data['t_id'],s.current_ticket().t_id)
        self.assertEqual(data['message_html'],'Ticket as already been used')
        self.assertEqual(data['error'],True)
        self.assertEqual(r.status_code,200)


    def testValidate(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        buyTickets(self, e.first_representation(),1)
        s = models.Seat.all().filter('representation =',e.first_representation()).filter('number =',1).get()
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?ticket_id=%s' % s.current_ticket().t_id,follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,200)
        data = loads(r.content)
        self.assertEqual(data['message_html'],'Successfully validated ticket')
        
    def testValidateTicketOtherRepresentation(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e1 = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e1 = publishEvent(self, e1)
        buyTickets(self, e1.first_representation(),1)
        userB = createUser(self,username='UserB',password='secret')
        e2 = addEvent(self,userB,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e2 = publishEvent(self, e2)
        buyTickets(self, e2.first_representation(),1)
        s = models.Seat.all().filter('representation =',e1.first_representation()).filter('number =',1).get()
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e2.first_representation().key()}) + '?ticket_id=%s' % s.current_ticket().t_id,follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,200)
        data = loads(r.content)
        self.assertEqual(data['message_html'],'Invalid Ticket ID')
        self.assertEqual(data['error'],True)


    def testValidateAlreadyValidated(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        buyTickets(self, e.first_representation(),1)
        s = models.Seat.all().filter('representation =',e.first_representation()).filter('number =',1).get()
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?ticket_id=%s' % s.current_ticket().t_id,follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,200)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?ticket_id=%s' % s.current_ticket().t_id,follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,200)
        data = loads(r.content)
        self.assertEqual(data['message_html'],'Ticket already used')
        self.assertEqual(data['error'],True)

    def testValidateInvalidTicket(self):
        date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=1)
        onsale_date = datetime.now().replace(tzinfo=gaepytz.utc)+ timedelta(days=-1)
        e = addEvent(self,self.user,str(uuid4()),nbr_seat=20,date=date,onsale_date=onsale_date)
        e = publishEvent(self, e)
        buyTickets(self, e.first_representation(),1)
        r = self.client.get(reverse('banian.views.validate',kwargs={'key':e.first_representation().key()}) + '?ticket_id=%s' % 'AAA',follow=True,HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code,200)
        data = loads(r.content)
        self.assertEqual(data['message_html'],'Invalid Ticket ID')
        self.assertEqual(data['error'],True)


        

class PaypalTestCase(TestCase):
    pastResponse            = {u'responseEnvelope': {u'ack': u'Failure', u'timestamp': u'2010-01-28T01:47:34.703-08:00', u'build': u'1159023', u'correlationId': u'a9b9fb0f44ce4'}, u'error': [{u'category': u'Application', u'domain': u'PLATFORM', u'severity': u'Error', u'message': u'The start date must be in the future', u'parameter': [u'startingDate'], u'errorId': u'580024'}]}
    getDetailsInvalidKey    = {u'responseEnvelope': {u'ack': u'Failure', u'timestamp': u'2010-02-09T09:33:36.0-08:00', u'build': u'1159023', u'correlationId': u'6269520fb9bfb'}, u'error': [{u'category': u'Application', u'domain': u'PLATFORM', u'message': u'The preapproval key AAA is invalid', u'severity': u'Error', u'errorId': u'589019'}]} 
    invalidPaypalID         = {u'responseEnvelope': {u'ack': u'Failure', u'timestamp': u'2010-02-19T13:49:54.233-08:00', u'build': u'1193935', u'correlationId': u'96be9bf855846'}, u'error': [{u'category': u'Application', u'domain': u'PLATFORM', u'message': u'Invalid request: Not a valid email address.', u'severity': u'Error', u'errorId': u'580001'}]}
    invalidPreApprovalKey   = {u'curPayments': u'0', u'responseEnvelope': {u'ack': u'Success', u'timestamp': u'2010-02-19T14:23:27.94-08:00', u'build': u'1193935', u'correlationId': u'94fa2f4d41242'}, u'returnUrl': u'http://www.iguzu.com/events/representations/publish/ag5iYW5pYW4tcHJvamVjdHIcCxIVYmFuaWFuX3JlcHJlc2VudGF0aW9uGPokDA?status=completed', u'memo': u'Payment pre-approval to publish Test, 2010-02-27 20:00:00-05:00\n Total 4.00 $:\n  - 0.00  for publishing 0 tickets (at 0.01$/ticket).\n  -Up to 4.00 $ in comission if the representation solds out (1% of 399.80 $).', u'currencyCode': u'USD', u'maxTotalAmountOfAllPayments': u'4.00', u'dayOfWeek': u'NO_DAY_SPECIFIED', u'senderEmail': u'buyer_1259639092_per@iguzu.com', u'endingDate': u'2010-03-01T13:55:05.0-08:00', u'status': u'ACTIVE', u'curPeriodAttempts': u'0', u'paymentPeriod': u'NO_PERIOD_SPECIFIED', u'cancelUrl': u'http://www.iguzu.com/events/representations/publish/ag5iYW5pYW4tcHJvamVjdHIcCxIVYmFuaWFuX3JlcHJlc2VudGF0aW9uGPokDA?status=cancelled', u'startingDate': u'2010-02-19T13:55:05.0-08:00', u'pinType': u'NOT_REQUIRED', u'dateOfMonth': u'0', u'approved': u'false', u'curPaymentsAmount': u'0.00'}
    def setUp(self):
        pass

    def testgetPreApprovalDetailsFetchRaise(self):
        def f(*args,**kwargs):
            raise AssertionError
        StubUrlFetch(f)
        r = getPreApprovalDetails('AAA')
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testgetPreApprovalDetails404(self):
        def f(*args,**kwargs):
            return HttpResponseNotFound()
        StubUrlFetch(f)
        r = getPreApprovalDetails('AAA')
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testgetPreApprovalDetailsInvalidData(self):
        def f(*args,**kwargs):
            return HttpResponse()
        StubUrlFetch(f)
        r = getPreApprovalDetails('AAA')
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testgetPreApprovalDetailsInvalidKey(self):
        def f(*args,**kwargs):
            raise AssertionError
        r = getPreApprovalDetails('AAA')
        self.assertEqual(r,'invalid_pre_approval_key')


    def testprocessPreApprovalFetchRaise(self):
        def f(*args,**kwargs):
            raise AssertionError
        StubUrlFetch(f)
        enddate = datetime.utcnow().replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('US/Pacific')) + timedelta(days=5)
        r = processPreApproval("memo",19.99,"sbl@iguzu.com","","",enddate)
        self.assertEqual(r,('paypal_unexpected',None))
        UnStubUrlFetch()

    def testprocessPreApproval404(self):
        def f(*args,**kwargs):
            return HttpResponseNotFound()
        StubUrlFetch(f)
        enddate = datetime.utcnow().replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('US/Pacific')) + timedelta(days=5)
        r = processPreApproval("memo",19.99,"sbl@iguzu.com","","",enddate)
        self.assertEqual(r,('paypal_unexpected',None))
        UnStubUrlFetch()

    def testprocessPreApprovalInvalidData(self):
        def f(*args,**kwargs):
            return HttpResponse()
        StubUrlFetch(f)
        enddate = datetime.utcnow().replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('US/Pacific')) + timedelta(days=5)
        r = processPreApproval("memo",19.99,"sbl@iguzu.com","","",enddate)
        self.assertEqual(r,('paypal_unexpected',None))
        UnStubUrlFetch()

    def testprocessPreApprovalMissingJSONProperty(self):
        def f(*args,**kwargs):
            return HttpResponse("{}")
        StubUrlFetch(f)
        enddate = datetime.utcnow().replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('US/Pacific')) + timedelta(days=5)
        r = processPreApproval("memo",19.99,"sbl@iguzu.com","","",enddate)
        self.assertEqual(r,('paypal_unexpected',None))
        UnStubUrlFetch()


    def testprocessPreApprovalPastStartDate(self):
        def f(*args,**kwargs):
            return HttpResponse(dumps(self.pastResponse)) 
        StubUrlFetch(f)
        enddate = datetime.utcnow().replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('US/Pacific')) + timedelta(days=5)
        r = processPreApproval("memo",19.99,"sbl@iguzu.com","","",enddate)
        self.assertEqual(r,('past_start_date',None))
        UnStubUrlFetch()

    def testprocessPaymentFetchRaise(self):
        def f(*args,**kwargs):
            raise AssertionError
        StubUrlFetch(f)
        r = processPayment("memo","sbl@iguzu.com","19.99","")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testprocessPayment404(self):
        def f(*args,**kwargs):
            return HttpResponseNotFound()
        StubUrlFetch(f)
        r = processPayment("memo","sbl@iguzu.com","19.99","")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testprocessPaymentInvalidData(self):
        def f(*args,**kwargs):
            return HttpResponse()
        StubUrlFetch(f)
        r = processPayment("memo","sbl@iguzu.com","19.99","")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testprocessPaymentMissingJSONProperty(self):
        def f(*args,**kwargs):
            return HttpResponse("{}")
        StubUrlFetch(f)
        r = processPayment("memo","sbl@iguzu.com","19.99","")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testprocessCancelPreApprovalFetchRaise(self):
        def f(*args,**kwargs):
            raise AssertionError
        StubUrlFetch(f)
        r = processCancelPreApproval("")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testprocessCancelPreApproval404(self):
        def f(*args,**kwargs):
            return HttpResponseNotFound()
        StubUrlFetch(f)
        r = processCancelPreApproval("")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testprocessCancelPreApprovalInvalidData(self):
        def f(*args,**kwargs):
            return HttpResponse()
        StubUrlFetch(f)
        r = processCancelPreApproval("")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

    def testprocessCancelPreApprovalMissingJSONProperty(self):
        def f(*args,**kwargs):
            return HttpResponse("{}")
        StubUrlFetch(f)
        r = processCancelPreApproval("")
        self.assertEqual(r,'paypal_unexpected')
        UnStubUrlFetch()

class CloseRepresentationTestCase(TestCase):

    def setUp(self):
        logging.debug('CloseRepresentationTestCase')
        StubPaypal()
        self.user = createUser(self)
    
    def testNothingToClose(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=10),
                     
                     onsale_date=now + timedelta(days=2),
                     endsale_date=now + timedelta(days=9),
                     price = 15.99)
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'Published')
        r= self.client.get(reverse('banian.tasks.views.schedule_close_representations'))
        logging.debug(r.content)
        self.assertContains(r,'Nothing to do')
        run_tasks(lapse=30)
        rep = models.Representation.get(e.first_representation().key())
        self.assertEqual(rep.status,'Published')
            
    def testOneToCloseOnSale(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=-2),
                     onsale_date = now + timedelta(days=-4),
                     endsale_date = now + timedelta(days=-3),
                     price = 15.99)
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'On Sale')
        r= self.client.get(reverse('banian.tasks.views.schedule_close_representations'))
        self.assertContains(r,'Completed: 1')
        run_tasks(lapse=30)
        rep = models.Representation.get(e.first_representation().key())
        self.assertEqual(rep.status,'Completed')
        
    def testOneToCloseSoldOut(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=-2),
                     onsale_date = now + timedelta(days=-4),
                     endsale_date = now + timedelta(days=-3),
                     price = 15.99)
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'On Sale')
        buyTickets(self, e.first_representation(), 10)
        rep = models.Representation.get(e.first_representation().key())
        self.assertEqual(rep.status,'Sold Out')
        r= self.client.get(reverse('banian.tasks.views.schedule_close_representations'))
        self.assertContains(r,'Completed: 1')
        run_tasks(lapse=30)
        rep = models.Representation.get(e.first_representation().key())
        self.assertEqual(rep.status,'Completed')

    def testOneToClosePaymentFails(self):
        now = datetime.utcnow().replace(tzinfo=gaepytz.utc)
        e = addEvent(self,self.user,'Test Event',nbr_seat=10,
                     date = now + timedelta(days=-2),
                     onsale_date = now + timedelta(days=-4),
                     endsale_date = now + timedelta(days=-3),
                     price = 15.99)
        e = publishEvent(self, e)
        self.assertEqual(e.first_representation().status,'On Sale')
        buyTickets(self, e.first_representation(), 10)
        rep = models.Representation.get(e.first_representation().key())
        self.assertEqual(rep.status,'Sold Out')
        unStubPaypal()
        r= self.client.get(reverse('banian.tasks.views.schedule_close_representations'))
        self.assertContains(r,'Completed: 1')
        run_tasks(lapse=30)
        rep = models.Representation.get(e.first_representation().key())
        self.assertEqual(rep.status,'Sold Out')
        StubPaypal()