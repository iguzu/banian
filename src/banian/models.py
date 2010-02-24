# -*- coding: utf-8 -*-
from google.appengine.ext import db
from google.appengine.api import images, memcache
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_delete
from google.appengine.ext.db import GqlQuery
import gaepytz #@UnresolvedImport

from django.utils import simplejson
from geo.geomodel import GeoModel
google_images = {'jpeg':images.JPEG,'png':images.PNG, 'jpg':images.JPEG }

import banian.model_utils
import logging #@UnusedImport
fetch_limit = 501
put_limit = 50
batch_put_limit = 250
delete_limit = 100
batch_delete_limit = 500
max_ticket_limit = 30
offline_mode = False
commission_rate = 0.01 # 1 percent
seat_publish_cost = 0.01 # 1 cents
publishing_free_threshold = 2.00 # 2$ (200 seats)

class Image(db.Model):
    filename = db.StringProperty(indexed=False) 
    content = db.BlobProperty(indexed=False)
    content_type = db.StringProperty(indexed=False)
    caption = db.StringProperty(indexed=False)

    def __unicode__(self):
        return self.filename

    def put(self,*args,**kwargs):
        super(Image,self).put(*args,**kwargs)
        memcache.delete(str(self.key())) #@UndefinedVariable
        memcache.delete(str(self.key()) + '-small') #@UndefinedVariable
        memcache.delete(str(self.key()) + '-medium') #@UndefinedVariable

class Venue(db.Model):
    name = db.StringProperty()
    quick = db.BooleanProperty()
    description = db.TextProperty()
    web_site = db.LinkProperty(indexed=False)
    address = db.PostalAddressProperty()
    country = db.StringProperty()
    owner = db.ReferenceProperty(User, required=True)
    poster_image = db.ReferenceProperty(Image,collection_name='venue_poster_set')
    thumbnail_image = db.ReferenceProperty(Image,collection_name='venuet_humbnail_set')
    last_modified = db.DateTimeProperty(auto_now=True)
    created = db.DateTimeProperty(auto_now_add=True)
    location = db.GeoPtProperty()
    status = db.StringProperty(default='Unused', choices=set(['Used', 'Unused',]))
    timezone = db.StringProperty(indexed=False)
    def __unicode__(self):
        return '%s - %s' % (self.key(),self.name)

    class Meta:
        ordering = ['name']

    def mutable(self):
        if GqlQuery("SELECT * FROM banian_event WHERE venue =:1",self).get(): 
            return False
        else:
            return True
    def delete(self):
        if not self.mutable():
            raise AssertionError
        for seat_config in self.seatconfiguration_set:
            seat_config.delete()      
        if self.thumbnail_image:
            db.delete(self.thumbnail_image)
        if self.poster_image:
            db.delete(self.poster_image)      
        super(Venue,self).delete()


class SeatConfiguration(db.Model):
    ''' Venue seat configuration class '''
    name = db.StringProperty(required=True)
    description = db.TextProperty()
    nbr_seat = db.IntegerProperty(default=0)
    venue = db.ReferenceProperty(Venue, required=True)
    owner = db.ReferenceProperty(User)
    last_modified = db.DateTimeProperty(auto_now=True,indexed=False)
    created = db.DateTimeProperty(auto_now_add=True,indexed=False)
    def __unicode__(self):
        return self.name

    def mutable(self):
        return True

    def delete(self):
        if not self.mutable():
            raise AssertionError
        seat_groups = self.seatgroup_set
        db.delete(seat_groups)
        super(SeatConfiguration,self).delete()

    def put(self):
        if not self.mutable():
            raise AssertionError
        super(SeatConfiguration,self).put()

    class Meta:
        ordering = ['name']
    


class SeatGroup(db.Model):
    ''' Meta Seat Group class'''
    type = db.StringProperty(required=True, choices=set(['Venue', 'Level', 'Section', 'Row', 'Table']))
    name = db.StringProperty()
    priority = db.IntegerProperty(default=1)
    nbr_seat = db.IntegerProperty(default=0,indexed=False)
    total_nbr_seat = db.IntegerProperty(default=0,indexed=False)
    seat_configuration = db.ReferenceProperty(SeatConfiguration) 
    owner = db.ReferenceProperty(User, required=True)
    last_modified = db.DateTimeProperty(auto_now=True,indexed=False)
    created = db.DateTimeProperty(auto_now_add=True,indexed=False)
    seat_group = db.SelfReference()
    class Meta:
        ordering = ['name']

    def mutable(self):
        return True

    def delete(self):
        if not self.mutable():
            raise AssertionError                    
        seat_groups = SeatGroup.all().ancestor(self)
        db.delete(seat_groups)
        super(SeatGroup,self).put()

    def put(self):
        if not self.mutable():
            raise AssertionError
        super(SeatGroup,self).put()

   
    def __unicode__(self):
        return '%s - %s' % (self.key(),self.name)

class Event(GeoModel):
    name = db.StringProperty()
    performer = db.StringProperty()
    description = db.TextProperty()
    status = db.StringProperty(default='Draft', choices=set(['Draft', 'Published','Sold Out','On Sale','Completed','Cancelled']))
    quick = db.BooleanProperty()
    max_step = db.IntegerProperty(indexed=False,default=-1)
    venue = db.ReferenceProperty(Venue, required=True)
    seat_configuration = db.ReferenceProperty(SeatConfiguration, default=None)
    onsale_date = db.DateTimeProperty()
    endsale_date = db.DateTimeProperty()
    owner = db.ReferenceProperty(User,required=True)
    duration = db.IntegerProperty(indexed=False)
    door_open = db.IntegerProperty(indexed=False)
    cancellable = db.BooleanProperty(default=False,indexed=False)
    cancel_fees = db.FloatProperty(default=10.0,indexed=False)
    cancel_delay = db.IntegerProperty(indexed=False)
    thumbnail_image = db.ReferenceProperty(Image,collection_name='event_poster_set')
    poster_image = db.ReferenceProperty(Image,collection_name='event_thumbnail_set')
    last_modified = db.DateTimeProperty(auto_now=True,indexed=False)
    created = db.DateTimeProperty(auto_now_add=True,indexed=False)
    firstdate = db.DateTimeProperty()
    web_site = db.LinkProperty(indexed=False)
    email = db.EmailProperty(indexed=False)
    note = db.TextProperty(indexed=False)
    limit_tickets = db.BooleanProperty(indexed=False)
    max_tickets = db.IntegerProperty(indexed=False)
    restrict_sale_period = db.BooleanProperty(indexed=False)
    validators = db.ListProperty(db.Key)
    limit_duration = db.BooleanProperty(indexed=False,default=False)

    def __unicode__(self):
        return '%s - %s' % (self.key(),self.name)
    class Meta:
        ordering = ['name']

    def mutable(self):
        if self.status == 'Published' or self.status == 'On sales' or self.status == 'Sold Out' or self.status == 'Cancelled':
            return False
        else:
            return True

    def __init__(self,*args,**kwargs):
        super(Event,self).__init__(*args,**kwargs)
        try:
            self.seat_configuration.key()
        except:
            self.seat_configuration = None
        if self.onsale_date and not self.onsale_date.tzinfo:
            if self.venue.timezone:
                self.onsale_date = self.onsale_date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.venue.timezone))
            else:
                self.onsale_date = self.onsale_date.replace(tzinfo=gaepytz.utc)

        if self.endsale_date and not self.endsale_date.tzinfo:
            if self.venue.timezone:
                self.endsale_date = self.endsale_date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.venue.timezone))
            else:
                self.endsale_date = self.endsale_date.replace(tzinfo=gaepytz.utc)     
   
        if self.firstdate and not self.firstdate.tzinfo:
            if self.venue.timezone:
                self.firstdate = self.firstdate.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.venue.timezone))
            else:
                self.firstdate = self.firstdate.replace(tzinfo=gaepytz.utc)

    def delete(self):
        if not self.mutable():
            raise AssertionError
        db.delete(self.representation_set)
        db.delete(self.ticketclass_set)
        if self.thumbnail_image:
            db.delete(self.thumbnail_image)
        if self.poster_image:
            db.delete(self.poster_image)
        super(Event,self).delete()
        if self.quick:
            if self.venue:
                self.venue.delete()        

    def put(self,*args,**kwargs):
        if self.location != self.venue.location:
            self.location = self.venue.location
        if self.location:
            self.update_location()
        super(Event,self).put(*args,**kwargs)

    def representations(self):
        if hasattr(self,'_representations'):
            return self._representations
        self._representations = self.representation_set.order('-date').fetch(fetch_limit)
        return self._representations

    def first_representation(self):
        representations = self.representations()
        if len(representations):
            return representations[0]
        return None


    def value(self):
        if not hasattr(self,'_value'):
            self._value = 0.0
            for rep in self.representations():
                self._value = self._value + rep.value
        return self._value 

    def representation_value(self):
        if not hasattr(self,'_representation_value'):
            self._representation_value = 0.0
            for tc in self.ticket_classes():
                self._representation_value = self._representation_value + tc.value()
        return self._representation_value
        
        
        return self.value()/len(self.representations())

    def revenues(self):
        if not hasattr(self,'_revenues'):
            self._revenues = 0.0
            for rep in self.representations():
                self._revenues = self._revenues + rep.revenues
        return self._revenues

    def nbr_tickets(self):
        if not hasattr(self,'_nbr_tickets'):
            self._nbr_tickets = 0
            for rep in self.representations():
                self._nbr_tickets = self._nbr_tickets + rep.nbr_tickets
        return self._nbr_tickets

    def timezone_name(self):
        if hasattr(self,'_timezone_name'):
            return self._timezone_name
        self._timezone_name = ''
        for item in banian.model_utils.construct_timezone_choice(self.venue.country):
            if item[0] == self.venue.timezone:
                if len(item) == 2:
                    self._timezone_name = item[1]
                else:
                    self._timezone_name = item[2]
        return self._timezone_name    

    def ticket_classes(self):
        if hasattr(self,'_ticket_classes'):
            return self._ticket_classes
        self._ticket_classes = self.ticketclass_set.order('name').fetch(fetch_limit)
        return self._ticket_classes


    def available_tickets(self):
        if not hasattr(self,'_available_tickets'):            
            self._available_tickets = 0
            if not hasattr(self,'_representations'):
                self.representations()
            for rep in self.representations():
                self._available_tickets = self._available_tickets + rep.available_tickets
        return self._available_tickets

    def nbr_seats(self):
        if self.seat_configuration:
            return self.seat_configuration.nbr_seat
        return 0

    def nbr_unassigned_seats(self):
        if self.seat_configuration:
            total = 0
            for tc in self.ticket_classes():
                total = total + tc.nbr_seats()
            return self.seat_configuration.nbr_seat - total
        return 0
    
    def nbr_assigned_seats(self):
        if self.seat_configuration:
            total = 0
            for tc in self.ticket_classes():
                total = total + tc.nbr_seats()
            return total
        return 0
            

class Representation(GeoModel):
    event = db.ReferenceProperty(Event)
    venue = db.ReferenceProperty(Venue)
    owner = db.ReferenceProperty(User)
    status = db.StringProperty(default='Draft', choices=set(['Draft','Processing Payment','Generating', 'Canceling','Published','Sold Out','On Sale','Sale Closed','Completed','Cancelled']))
    date = db.DateTimeProperty()
    event_name = db.StringProperty(indexed=False)
    job_id = db.StringProperty(indexed=False)
    available_tickets = db.IntegerProperty(default=0,indexed=False)
    nbr_tickets = db.IntegerProperty(default=0,indexed=False)
    revenues = db.FloatProperty(default=0.0,indexed=False)
    value = db.FloatProperty(default=0.0,indexed=False)
    tc_available = db.TextProperty()
    timestamp_available = db.DateTimeProperty(indexed=False)
    timestamp_revenues = db.DateTimeProperty(indexed=False)
    last_modified = db.DateTimeProperty(auto_now=True,indexed=False)
    created = db.DateTimeProperty(auto_now_add=True,indexed=False)
    pre_approval_status = db.StringProperty(choices=set(['Processing','Completed','Canceled']))
    pre_approval_key = db.StringProperty(indexed=False)
    paypal_id = db.StringProperty(indexed=False)
    timezone = db.StringProperty(indexed=False)

    def __init__(self,*args,**kwargs):
        super(Representation,self).__init__(*args,**kwargs)
        if self.date and not self.date.tzinfo:
            if self.timezone:
                self.date = self.date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.timezone))
            else:
                self.date = self.date.replace(tzinfo=gaepytz.utc)
        if self.timestamp_available:
            self.timestamp_available = self.timestamp_available.replace(tzinfo=gaepytz.utc)
        if self.timestamp_revenues:
            self.timestamp_revenues = self.timestamp_revenues.replace(tzinfo=gaepytz.utc)
    def __unicode__(self):
        return '%s - %s - %s' % (self.key(), self.event_name,str(self.date))
    class Meta:
        ordering = ['date']

    def mutable(self):
        if self.status != 'Draft':
            return False
        else:
            return True

    def delete(self):
        if not self.mutable():
            raise AssertionError             
        super(Representation,self).delete()

    def put(self,*args,**kwargs):
        self.venue = self.event.venue
        self.location = self.event.location
        self.event_name = self.event.name
        if self.location: 
            self.update_location()
        super(Representation,self).put(*args,**kwargs)

    def calc_available_tickets(self,timestamp):
        if timestamp > self.timestamp_available:
            self.available_tickets, ticket_class_available = banian.model_utils.calc_representation_available(self)
            self.set_ticketclass_available(ticket_class_available)
            self.timestamp_available = timestamp

    def calc_revenues(self,timestamp):
        if timestamp > self.timestamp_revenues:
            self.revenues = banian.model_utils.calc_representation_revenues(self)
            self.timestamp_revenues = timestamp

        if not hasattr(self,'_revenues'):
            self._revenues = banian.model_utils.calc_representation_revenues(self)
        return self._revenues

    def get_ticketclass_available(self):
        data = simplejson.loads(self.tc_available)
        return data
    
    def set_ticketclass_available(self,data):
        self.tc_available = simplejson.dumps(data)

    def timezone_name(self):
        if not hasattr(self,'_timezone_name'):
            self._timezone_name = ''
            for item in banian.model_utils.construct_timezone_choice(self.event.venue.country):
                if item[0] == self.event.venue.timezone:
                    if len(item) == 2:
                        self._timezone_name = item[1]
                    else:
                        self._timezone_name = item[2]
        return self._timezone_name    

    def available_tickets_text(self):
        count = self.available_tickets
        if count == 1:
            return '1 ticket left'
        elif count == 0:
            return 'No ticket left'
        else:
            return '%d ticket left' % count
        
    def commission_cost(self):
        if not hasattr(self,'_commission_cost'):
            self._commission_cost = self.event.representation_value() * commission_rate
        return self._commission_cost
        
    
    def publishing_cost(self):
        if not hasattr(self,'_publishing_cost'):
            self._publishing_cost = self.event.nbr_assigned_seats() * seat_publish_cost
            if self._publishing_cost <= publishing_free_threshold:
                self._publishing_cost = 0
        return self._publishing_cost
    
    def total_cost(self):
        return self.publishing_cost() + self.commission_cost()


class Transaction(db.Model):
    event = db.ReferenceProperty(Event)
    representation = db.ReferenceProperty(Representation)
    date = db.DateTimeProperty(auto_now_add=True)
    type = db.StringProperty(choices=set(['Purchase', 'Refund', 'Cancellation', 'Transfer In', 'Transfer To']))
    status = db.StringProperty(choices=set(['Processing', 'Completed', 'Cancelled','Refunded']))
    t_id = db.StringProperty(required=True)
    owner = db.ReferenceProperty(User, required=True)
    representation_date = db.DateTimeProperty()
    representation_door_date = db.DateTimeProperty(indexed=False)
    venue_name = db.StringProperty(indexed=False)
    venue_address = db.StringProperty(indexed=False)
    venue_timezone = db.StringProperty(indexed=False)
    venue_web_site = db.LinkProperty(indexed=False)
    event_name = db.StringProperty(indexed=False)
    event_performer = db.StringProperty(indexed=False)
    event_note = db.TextProperty(indexed=False)
    event_web_site = db.LinkProperty(indexed=False)
    event_thumbnail_image = db.ReferenceProperty(Image,indexed=False,collection_name='transaction_thumbnail_set')
    event_poster_image = db.ReferenceProperty(Image,indexed=False,collection_name='transaction_poster_set')
    total_amount = db.FloatProperty(indexed=False)
    nbr_tickets = db.IntegerProperty(indexed=False)
    ticket_keys = db.ListProperty(db.Key,indexed=False)
    apkey = db.StringProperty(indexed=False)
    paypal_id = db.StringProperty(indexed=False)
    

    last_modified = db.DateTimeProperty(auto_now=True,indexed=False)
    created = db.DateTimeProperty(auto_now_add=True,indexed=False)
    
    
    def __init__(self,*args,**kwargs):
        super(Transaction,self).__init__(*args,**kwargs)
        try:
            self.representation.key()
        except:
            self.representation = None
        try: 
            self.event_poster_image.key()
        except:
            self.event_poster_image = None
        try:
            self.event_thumbnail_image.key()
        except:
            self.event_thumbnail_image = None
                    
        self.tickets = db.get(self.ticket_keys)
        if self.representation_date and not self.representation_date.tzinfo:
            if self.venue_timezone:
                self.representation_date = self.representation_date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.venue_timezone))
            else:
                self.representation_date = self.representation_date.replace(tzinfo=gaepytz.utc)

        if self.representation_door_date and not self.representation_door_date.tzinfo:
            if self.venue_timezone:
                self.representation_door_date = self.representation_door_date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.venue_timezone))
            else:
                self.representation_door_date = self.representation_door_date.replace(tzinfo=gaepytz.utc)


    def __unicode__(self):
        return '%s - %s - %s - %s' % (self.key(),self.owner,self.type, self.date)





    

class TicketClass(db.Model):
    """ Seat Class """
    name = db.StringProperty()
    general_admission = db.BooleanProperty(default=True)
    price = db.FloatProperty(default=0.0)  
    event = db.ReferenceProperty(Event, required=True)
    owner = db.ReferenceProperty(User, required=True)
    seat_groups = db.ListProperty(db.Key)
    seat_available = db.IntegerProperty()
    last_modified = db.DateTimeProperty(auto_now=True)
    created = db.DateTimeProperty(auto_now_add=True)

    def __unicode__(self):
        return '%s - %s' % (str(self.key()),self.name)

    class Meta:
        ordering = ['name']

    def mutable(self):
        if self.event.status == 'Published' or self.event.status == 'On sales' or self.event.status == 'Sold Out':
            return False
        else:
            return True

    def delete(self):
        if not self.mutable():
            raise AssertionError
        super(TicketClass,self).delete()             

    def nbr_seats(self):
        if not hasattr(self,'_nbr_seat'):
            self._nbr_seat = banian.model_utils.calc_ticket_class_nbr_seat(self)
        return self._nbr_seat

    def value(self):
        if not hasattr(self,'_value'):
            self._value = self.price * self.nbr_seats()
        return self._value

class Seat(db.Model):
    class Meta:
        verbose_name = 'Seat'
    _status = ('Available','Pending','Sold/Taken')
    representation = db.ReferenceProperty(Representation)
    location = db.StringListProperty(indexed=False,default=[])
    ticket_class = db.ReferenceProperty(TicketClass, required=True)
    number = db.IntegerProperty(required=True)
    availability = db.IntegerProperty(default=0, choices=(0,1,2))
    seat_group = db.ReferenceProperty(SeatGroup)
    priority = db.IntegerProperty()
    reservation = db.StringProperty()
    def __unicode__(self):
        return 'Seat number: ' + str(self.number)

    def mutable(self):
        if self.representation.status == 'Published' or self.representation.status == 'On sales' or self.representation.status == 'Sold Out':
            return False
        else:
            return True


    def delete(self):
        if not self.mutable():
            raise AssertionError
        super(Seat,self).delete()             

    def current_ticket(self):        
        if not hasattr(self,'_current_ticket'):
            tickets = self.ticket_set.filter('status =','Valid')
            assert(tickets.count(2) == 1 or tickets.count(2) == 0 )
            self._current_ticket = tickets.get()
        return self._current_ticket


class Ticket(db.Model):
    seat = db.ReferenceProperty(Seat)
    representation = db.ReferenceProperty(Representation)
    owner = db.ReferenceProperty(User,required=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    created = db.DateTimeProperty(auto_now_add=True)
    transaction = db.ReferenceProperty(Transaction)
    t_id = db.StringProperty()
    event_image = db.ReferenceProperty(Image,indexed=False)
    venue_name = db.StringProperty(indexed=False)
    performer = db.StringProperty(indexed=False)
    event_name = db.StringProperty(indexed=False)
    note = db.TextProperty()
    web_site_event = db.LinkProperty(indexed=False)
    web_site_venue = db.LinkProperty(indexed=False)
    number = db.IntegerProperty(indexed=False)
    price = db.FloatProperty(indexed=False)
    location = db.StringListProperty(indexed=False)
    barcode = db.ReferenceProperty(Image,collection_name='ticket_barcode_set')
    timezone = db.StringProperty(indexed=False)
    date = db.DateTimeProperty()
    general_admission = db.BooleanProperty(indexed=False)
    door_date = db.DateTimeProperty(indexed=False)
    address = db.StringProperty(indexed=False)
    ticket_class_name = db.StringProperty(indexed=False)
    status = db.StringProperty(choices=set(['Valid', 'Refunded', 'Cancelled','Transfered']))
    used = db.BooleanProperty(indexed=False,default=False)
    def __init__(self,*args,**kwargs):
        super(Ticket,self).__init__(*args,**kwargs)
        try:
            self.event_image.key()
        except:
            self.event_image = None
        
        if self.date and not self.date.tzinfo:
            if self.timezone:
                self.date = self.date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.timezone))
            else:
                self.date = self.date.replace(tzinfo=gaepytz.utc)
        try:
            self.seat.key()
        except:
            self.seat = None

    def __str__(self):
        if self.t_id:
            return self.t_id
        else:
            return str(self.key())

    def __unicode__(self):
        if self.t_id:
            return self.t_id
        else:
            return str(self.key())

    def location_str(self):
        loc_str = ''
        for item in self.location:
            if loc_str:
                buffer = loc_str + ', ' + str(item)
            else:
                loc_str = str(item)
            return loc_str


class TicketScan(db.Model):
    seat = db.ReferenceProperty(Seat)
    representation = db.ReferenceProperty(Representation)
    t_id = db.StringProperty()
    result = db.StringProperty(choices=set(['Successful','Failure','Counterfeit']))
    validator = db.ReferenceProperty(User)
    date = db.DateTimeProperty()
        
class Transfer(db.Model):
    t_from = db.ReferenceProperty(User, collection_name='transferfrom_set', required=True)
    to = db.ReferenceProperty(User, collection_name='transferto_set', required=True)
    sent_date = db.DateTimeProperty()
    seat = db.ReferenceProperty(Seat, required=True)
    status = db.StringProperty(required=True, choices=set(['Sent', 'Recalled', 'Accepted', 'Refused']))
    accepted_date = db.DateTimeProperty()


class UserEvent(db.Model):
    event = db.ReferenceProperty(Event)
    representation = db.ReferenceProperty()
    owner = db.ReferenceProperty(User, required=True)
    representation_date = db.DateTimeProperty()
    representation_door_date = db.DateTimeProperty(indexed=False)
    thumbnail_image = db.ReferenceProperty(Image,indexed=False,collection_name='userevent_thumbnail_set')
    poster_image = db.ReferenceProperty(Image,indexed=False,collection_name='userevent_poster_set')
    name = db.StringProperty(indexed=False)
    performer = db.StringProperty(indexed=False)
    note = db.TextProperty(indexed=False)
    web_site = db.LinkProperty(indexed=False)
    email = db.EmailProperty(indexed=False)
    venue_name = db.StringProperty(indexed=False)
    venue_address = db.StringProperty(indexed=False)
    venue_timezone = db.StringProperty(indexed=False)
    venue_web_site = db.LinkProperty(indexed=False)
    total_amount = db.FloatProperty(indexed=False)
    nbr_tickets = db.IntegerProperty(indexed=False)
    ticket_keys = db.ListProperty(db.Key,indexed=False)

    last_modified = db.DateTimeProperty(auto_now=True,indexed=False)
    created = db.DateTimeProperty(auto_now_add=True,indexed=False)


    def __init__(self,*args,**kwargs):
        super(UserEvent,self).__init__(*args,**kwargs)
        try:
            self.representation.key()
        except:
            self.representation = None
        try:
            self.thumbnail_image.key()
        except:
            self.thumbnail_image = None
        try:
            self.poster_image.key()
        except:
            self.poster_image = None
        if self.representation_date and not self.representation_date.tzinfo:
            if self.venue_timezone:
                self.representation_date = self.representation_date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.venue_timezone))
            else:
                self.representation_date = self.representation_date.replace(tzinfo=gaepytz.utc)

        if self.representation_door_date and not self.representation_door_date.tzinfo:
            if self.venue_timezone:
                self.representation_door_date = self.representation_door_date.replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(self.venue_timezone))
            else:
                self.representation_door_date = self.representation_door_date.replace(tzinfo=gaepytz.utc)

    def __unicode__(self):
        return '%s - %s - %s' % (self.key(),self.name,self.representation_date)

class RepresentationPayment(db.Model):
    status = db.StringProperty(choices=set(['Acquiring','Completed','Failed',]))
    type = db.StringProperty(choices=set(['Commission','Publishing']))
    amount = db.FloatProperty()
    date = db.DateTimeProperty()
    
    
class TicketPayment(db.Model):
    pass

def update_representations(sender,**kwargs):
    instance = kwargs['instance']
    representations = Representation.all().filter('event =', instance)
    for representation in representations:
        if representation.location != instance.location:
            representation.location = instance.location 
            representation.put()

def update_events_firstdate(sender,**kwargs):
    instance = kwargs['instance']
    event = Event.get(instance.event.key())
    representation = Representation.gql("WHERE event =:1 AND status IN :2 ORDER BY date",event,['Published','On Sale','Sold Out']).get()
    dirty = False
    if representation:
        if event.firstdate != representation.date:
            event.firstdate = representation.date
            dirty = True
        if event.status == 'Draft':
            event.status = 'Published'
            dirty = True
    else:
        if event.firstdate:
            event.firstdate = None
            dirty = True
        if event.status != 'Draft':
            event.status = 'Draft'
            dirty = True
    if dirty:
        event.put()

def update_events_location(sender,**kwargs):
    instance = kwargs['instance']
    events = Event.all().filter('venue =', instance)
    for event in events:
        if event.location != instance.location:
            event.location = instance.location
            event.put()
            
def update_venues(sender,**kwargs):
    instance = kwargs['instance']
    
    if db.GqlQuery("SELECT * FROM banian_event WHERE venue = :1 AND status IN :2",instance.venue,['Published','On Sales','Sold Out','Sale Closed']).count():
        if instance.venue.status != 'Used':
            instance.venue.status = 'Used'
            instance.venue.put()
    else:
        if instance.venue.status != 'Unused':
            instance.venue.status = 'Unused'
            instance.venue.put()

def update_events_seat_groups(sender,**kwargs):
    instance = kwargs['instance']
    events = instance.seat_configuration.event_set
    for event in events:
        for ticket_class in event.ticket_class:
            dirty = False
            for index,item in enumerate(ticket_class.seat_groups):
                if item == instance.key():
                    del ticket_class.seat_groups[index]
                    dirty = True
            if dirty:
                ticket_class.put()


post_save.connect(update_representations,sender=Event) #@UndefinedVariable
post_save.connect(update_venues,sender=Event) #@UndefinedVariable
post_save.connect(update_events_location,sender=Venue) #@UndefinedVariable
post_save.connect(update_events_firstdate,sender=Representation) #@UndefinedVariable
pre_delete.connect(update_events_seat_groups,sender=SeatGroup) #@UndefinedVariable

