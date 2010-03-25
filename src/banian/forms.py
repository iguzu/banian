# -*- coding: utf-8 -*-
from banian.models import Event, TicketClass, Representation, SeatConfiguration,\
    Venue
from django.forms.models import ModelForm
from django import forms
from django.forms.forms import Form, ValidationError
from django.forms.fields import ChoiceField, CharField, FileField, MultipleChoiceField, DateField, TimeField, IntegerField, URLField,\
    BooleanField, EmailField, FloatField
from django.contrib.auth.models import User
from django.utils.simplejson import loads
from django.utils.translation import ugettext_lazy as _ #@UnresolvedImport
from google.appengine.api.urlfetch import fetch
from google.appengine.ext import db
from datetime import datetime, timedelta
from google.appengine.api.labs.taskqueue.taskqueue import Task, Queue
from ragendja.template import render_to_response
from banian.model_utils import construct_timezone_choice, get_country_name,\
    get_currency_code, get_currency_symbol
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.forms.widgets import RadioSelect
from banian import models
import gaepytz
import logging #@UnusedImport
import time


from banian.models import SeatGroup
from banian.utils import handle_images, TextField, find_closest_timezone_choice
from banian.templatetags.istatus import priceformat

def findInLocation(info, items):
    result = {}
    for value_key,value in info.iteritems():
        for item in items:
            if value_key == item:
                result[item] = value
                items.remove(item)
                break
        if isinstance(value,dict):
            result.update(findInLocation(value,items))
    return result

currency_choices = [('EUR', u'\u20ac'),('USD', u'US$'),('GBP', u'\xa3'),('BRL', u'R$'),('JPY', u'\xa5 (JPY)'),('CAD', u'C$'),('AUD', u'A$'), ('MXN', u'$ (MXN)'), ('DKK', u'kr (DKK)'), ('HUF', u'Ft'), ('HKD', u'HK$'), ('NOK', u'kr (NOK)'), ('TWD', u'NT$'), ('THB', u'Thb'), ('PHP', u'Php'), ('PLN', u'Zt'), ('CHF', u'chf'),  ('CZK', u'Kc'), ('SEK', u'kr (SEK)'), ('SGD', u'S$'), ('ILS', u'NIS')]


def ValidateLocation(address=''):
    if models.offline_mode:
        return 0.0,0.0,'','','CA'
    else:
        google_map_key = 'ABQIAAAAmAhTCYAPVCPRJ5WJRudjNhSojUClvdiPvvgRhwnUw8nSXcpHkBQoV6YnIJrZrn3Py7OwWBO61ApV1g'
        if address:
            address = address.replace(' ','+')
        url = 'http://maps.google.com/maps/geo?q=%s&output=json&oe=utf8&sensor=false&key=%s' % (address, google_map_key)
        url = url.encode('utf-8')
        response = fetch(url)
        if response.status_code != 200:
            raise ValidationError(_(u'Geolocation Service unavailable. try to update your address later'))
        try:
            location = loads(response.content)
        except:
            raise ValidationError(_(u'Geolocation Service unavailable. Try to update your address later'))
        if location['Status']['code'] != 200:
            raise ValidationError(_(u'Unable to locate your address'))
        location_info = findInLocation(location['Placemark'][0],
                                       list(('AdministrativeAreaName','LocalityName','ThoroughfareName',
                                        'SubAdministrativeAreaName','CountryNameCode','DependentLocalityName',
                                        'Accuracy',)))
        if location_info.get('Accuracy',0) < 5:
            raise ValidationError(_(u'Location is not accurate enough, provide a more detailled address'))
        longitude  = location['Placemark'][0]['Point']['coordinates'][0]
        latitude = location['Placemark'][0]['Point']['coordinates'][1]
        addressname = location['name']
        short_addressname = ''
        if 'LocalityName' in location_info:
            if 'DependentLocalityName' in location_info:
                short_addressname = short_addressname + location_info['DependentLocalityName'] + ', '
            short_addressname = short_addressname + location_info['LocalityName']
        elif 'SubAdministrativeAreaName' in location_info:
            short_addressname = location_info['SubAdministrativeAreaName']
        elif 'AdministrativeAreaName' in location_info:
            short_addressname = location_info['AdministrativeAreaName']
        elif 'ThoroughfareName' in location_info:
            short_addressname = location_info['ThoroughfareName']
        if 'CountryNameCode' in location_info:
            if short_addressname:
                short_addressname = short_addressname + ', '
                country_code = location_info['CountryNameCode']
                country_code = get_country_name(country_code)
            short_addressname = short_addressname + country_code
        return latitude, longitude, addressname, short_addressname, location_info.get('CountryNameCode','')


class EventForm(ModelForm):
    thumbnail = FileField(required=False,help_text='Image used in the event listing. It should be square\
                                     and exactly 200x200 pixels.')
    poster = FileField(required=False,help_text='Image used when showing the event details. It should be\
                                  200 pixel wide and between 250-400 pixel long')
    
    onsale_time = TimeField()
    onsale_date = DateField()
    class Meta:
        model = Event
        exclude = ['owner','venue',
                   'poster_image', 'thumbnail_image',
                   'onsale_time','onsale_date','firstdate','status','location']
    
    def __init__(self,**kwargs):
        self._venue = kwargs.pop('venue',None)
        self._owner = kwargs.pop('owner',None)
        choices = kwargs.pop('choices',())
        self.max_onsale_date = kwargs.pop('max_onsale_date',None)
        super(EventForm,self).__init__(**kwargs)
        self.fields['onsale_time'].widget.attrs['class'] = 'ui-timepicker'
        self.fields['onsale_date'].widget.attrs['class'] = 'ui-datepicker'
        self.fields['cancel_delay'].widget.attrs['class'] = 'ui-slider'
        self.fields['cancel_fees'].widget.attrs['class'] = 'ui-slider'
        self.fields['door_open'].widget.attrs['class'] = 'ui-slider'
        self.fields['duration'].widget.attrs['class'] = 'ui-slider'
        self.fields['max_tickets'].widget.attrs['class'] = 'ui-slider'
        if self.instance:
            if self.instance.onsale_date:
                self.fields['onsale_time'].initial = self.instance.onsale_date.strftime('%H:%M')
                self.fields['onsale_date'].initial = self.instance.onsale_date.strftime('%m/%d/%Y')
        self.fields['seat_configuration'].choices = choices 

        
        
    def save(self):
        if not self.instance:
            event = Event(name=self.cleaned_data['name'],description=self.cleaned_data['description'],
                      performer=self.cleaned_data['performer'],
                       onsale_date=self.cleaned_data['onsale_date'],
                       cancellable=self.cleaned_data['cancellable'],
                       cancel_fees=self.cleaned_data['cancel_fees'],
                       cancel_delay=self.cleaned_data['cancel_delay'],
                       owner=self._owner,venue=self._venue,
                       seat_configuration=self.cleaned_data['seat_configuration'],
                       duration = self.cleaned_data['duration'],
                       door_open = self.cleaned_data['door_open'],
                       limit_tickets = self.cleaned_data['limit_tickets'],
                       max_tickets = self.cleaned_data['max_tickets'],
                       web_site = self.cleaned_data['web_site'],
                       note = self.cleaned_data['note'])
            handle_images(self,event)
            event.put()
            return event
        else:
            if not self.instance.mutable():
                raise AssertionError 
            handle_images(self,self.instance)
            if 'onsale_date' in self.changed_data or 'onsale_time' in self.changed_data:
                self.instance.onsale_date = self.cleaned_data['onsale_date']
                long_proc_queue = Queue(name='long-term-processing')
                onesaletime = time.mktime(self.instance.onsale_date.timetuple())
                if self.instance.onsale_date < datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(hours=48):
                    task = Task(url='/tasks/put_on_sale/', params={'event':self.instance.key(),'timestamp':onesaletime,}, eta=self.instance.onsale_date)
                    long_proc_queue.add(task)
                else:
                    # Do nothing, a CRON job will handle it 48h before the onsale date
                    pass
            return super(EventForm,self).save()

    def clean(self):
        for (key,value) in self.files.iteritems(): #@UnusedVariable
            try:
                i = value.name.rindex('.')
            except:
                raise ValidationError('invalid file name')
            if value.name[i+1:].lower() not in ['jpg','gif','png']:
                raise ValidationError('Unsuported image file format')
        if 'onsale_date' in self.changed_data or 'onsale_time' in self.changed_data :
            if 'onsale_date' in self.cleaned_data and 'onsale_time' in self.cleaned_data :
                if self.instance:
                    timezone = self.instance.venue.timezone
                else:
                    timezone = self._venue.timezone
                self.cleaned_data['onsale_date'] = datetime.combine(self.cleaned_data['onsale_date'],
                                                   self.cleaned_data['onsale_time']).replace(tzinfo=gaepytz.timezone(timezone))
                if self.instance:
                    first_representation = Representation.all().filter('event = ',self.instance).order('date').get()
                    if first_representation:
                        if self.cleaned_data['onsale_date'] > (first_representation.date):
                            raise ValidationError('onsale date is past the date of the first representation')
        return self.cleaned_data
    
class SelectVenueForm(Form):
    venue = ChoiceField()
    
    def __init__(self,*args,**kwargs):
        choices = kwargs.pop('choices', {})
        super(SelectVenueForm,self).__init__(*args,**kwargs)
        venue = self.fields['venue']
        venue.choices = choices

class SettingsForm(ModelForm):
    _verbose_name = 'Account Settings'
    time_format = ChoiceField(choices=((1,'am/pm'),(2,'24h')),initial=1)
    name = CharField(required=False)
    email = EmailField()
    address = CharField(required=False)
    paypal_id = EmailField(required=False)        

    class Meta:
        model = User
        fields = ['name','address','email','paypal_id','country','distance_units','time_format',]

    def clean_email(self):
        """
        Validate that the supplied email address is unique for the
        site.
        
        """
        email = self.cleaned_data['email'].lower()
        users = User.all().filter('email =', email)
        for user in users:
            if user != self.instance:
                raise forms.ValidationError(_(u'This email address is already in use. Please supply a different email address.'))
        return email


    def clean(self):
        address = self.cleaned_data.get('address')
        if address:
            self.cleaned_data['latitude'], self.cleaned_data['longitude'], self.cleaned_data['addressname'], self.cleaned_data['short_addressname'], self.cleaned_data['country'] = \
                ValidateLocation(address=self.cleaned_data.get('address'))
        else:
            self.cleaned_data['address'] = None
            self.cleaned_data['latitude'] = None
            self.cleaned_data['longitude'] = None
            self.cleaned_data['short_addressname'] = None
            self.cleaned_data['addressname'] = None
        return self.cleaned_data

    def save(self):
        if self.instance:
            if not self.instance.mutable():
                raise AssertionError 
            self.instance.address = self.cleaned_data['address']
            self.instance.addressname = self.cleaned_data['addressname']
            self.instance.short_addressname = self.cleaned_data['short_addressname']
            self.instance.name = self.cleaned_data['name']
            self.instance.email = self.cleaned_data['email']
            self.instance.country = self.cleaned_data['country']
            if self.cleaned_data['latitude'] and self.cleaned_data['longitude']:
                self.instance.location = db.GeoPt(self.cleaned_data['latitude'],self.cleaned_data['longitude'])
            else:
                self.instance.location = None
            self.instance.time_format= int(self.cleaned_data['time_format'])
            self.instance.paypal_id= self.cleaned_data['paypal_id'] or None
            return self.instance.put()
        return None


class TicketClassForm(ModelForm):
    seat_groups = MultipleChoiceField()

    class Meta:
        model = TicketClass
        exclude = ['owner', 'event', 'nbr_seat']

    def __init__(self,*args,**kwargs):
        choices = kwargs.pop('choices', {})
        self._event = kwargs.pop('event',None)
        self._owner = kwargs.pop('owner',None)
        super(TicketClassForm,self).__init__(*args,**kwargs)
        seat_groups = self.fields['seat_groups']
        seat_groups.choices = choices

    def save(self):
        if not self.instance:
            ticket_class = TicketClass(name=self.cleaned_data['name'],
                                       general_admission=self.cleaned_data['general_admission'],
                                       price=self.cleaned_data['price'],
                                       seat_groups = self.cleaned_data['seat_groups'],
                                       owner=self._owner,
                                       event=self._event)
            ticket_class.nbr_seat = 0
            for key in ticket_class.seat_groups:
                try:
                    ticket_class.nbr_seat += SeatGroup.get(key).nbr_seat
                except:
                    pass

            ticket_class.put()
            return ticket_class
        else:
            if not self.instance.mutable():
                raise AssertionError 
            self.instance.nbr_seat = 0
            for key in self.instance.seat_groups:
                try:
                    self.instance.nbr_seat += SeatGroup.get(key).nbr_seat
                except:
                    pass
            return super(TicketClassForm,self).save()

    def clean_seat_groups(self):
        seat_groups = []
        for item in self.cleaned_data['seat_groups']:
            seat_groups.append(db.Key(item))
        return seat_groups


class RepresentationForm(ModelForm):
    time = TimeField()
    date = DateField()
    class Meta:
        model = Representation
        exclude = ['date','time','venue','event','owner','status','last_modified','created',]

    def __init__(self,*args,**kwargs):
        self._event = kwargs.pop('event',None)
        self._owner = kwargs.pop('owner',None)
        self.min_date = kwargs.pop('min_date',None)
        super(RepresentationForm,self).__init__(*args,**kwargs)
        self.fields['time'].widget.attrs['class'] = 'ui-timepicker'
        self.fields['date'].widget.attrs['class'] = 'ui-datepicker'
        if self.instance:
            if self.instance.date:
                self.fields['time'].initial = self.instance.date.strftime('%H:%M')
                self.fields['date'].initial = self.instance.date.strftime('%m/%d/%Y')

    def clean(self):
        if 'date' in self.changed_data or 'time' in self.changed_data :
            if 'date' in self.cleaned_data and 'time' in self.cleaned_data :
                if self.instance:
                    timezone = self.instance.venue.timezone
                else:
                    timezone = self._event.venue.timezone
                self.cleaned_data['date'] = datetime.combine(self.cleaned_data['date'],
                                                             self.cleaned_data['time']).replace(tzinfo=gaepytz.timezone(timezone))
        return self.cleaned_data

    def save(self):
        if not self.instance:
            representation = Representation(date=self.cleaned_data['date'],
                                       owner=self._owner,
                                       location=self._event.location,
                                       event=self._event,
                                       timezone=self._event.venue.timezone,
                                       )
            representation.put()
            return representation
        else:
            if not self.instance.mutable():
                raise AssertionError 
            if 'date' in self.changed_data or 'time' in self.changed_data :
                self.instance.date = self.cleaned_data['date']
            return super(RepresentationForm,self).save()

class SelectSeatConfigForm(Form):
    seat_config = ChoiceField()
    
    def __init__(self,*args,**kwargs):
        choices = kwargs.pop('choices', {})
        super(SelectSeatConfigForm,self).__init__(*args,**kwargs)
        venue = self.fields['seat_config']
        venue.choices = choices

class Slider(object):
    def __init__(self,id,max,price):
        self.id = id
        self.max = max
        self.price = price

class SelectTicketForm(Form):
    class Meta:
        exclude = []
    def __init__(self,*args,**kwargs):
        self._representation = kwargs.pop('representation',None)
        self._ticketclass_list = kwargs.pop('ticketclass_list',None)
        self._already_purchase_tickets = kwargs.pop('already_purchase_tickets',0)
        self._max_tickets = kwargs.pop('max_tickets',0)
        super(SelectTicketForm,self).__init__(*args,**kwargs)
        self.sliders = []
        id = 1
        for ticket_class in self._ticketclass_list:
            if ticket_class.price:
                self.fields['tc' + str(id)] = IntegerField(label=ticket_class.name + ' (%s)' % priceformat(ticket_class.price,self._representation.event.venue.country),initial=0,help_text=ticket_class.total_available_text)
            else:
                self.fields['tc' + str(id)] = IntegerField(label=ticket_class.name + ' (Free)',initial=0,help_text=ticket_class.total_available_text)
            self.fields['tc' + str(id)].widget.attrs['class'] = 'ui-slider'
            self.sliders.append(Slider('id_tc' + str(id),ticket_class.max_tickets,ticket_class.price))
            id += 1
    def extract(self):
        id =1
        data = {}
        for ticket_class in self._ticketclass_list:
            data[ticket_class.key()] = self.cleaned_data['tc' + str(id)]
            id += 1
        return data
    
    def clean(self):
        id =1
        for ticket_class in self._ticketclass_list: #@UnusedVariable
            total = self.cleaned_data['tc' + str(id)]
            if self.cleaned_data['tc' + str(id)] > self._max_tickets:
                raise ValidationError('Cannot complete the purchase, you attempt to purchase too many tickets')
            id += 1
        if total > (self._max_tickets - self._already_purchase_tickets):
            raise ValidationError('Cannot complete the purchase, you attempt to purchase too many tickets')
        if total == 0:
            raise ValidationError('Select to purchase at least one ticket')
        return self.cleaned_data
    
 
class SelectDistanceForm(Form):
    class Meta:
        include = []
    distance_km = ChoiceField(choices=((10,'10 km'),(20,'20 km'),(20,'20 km'),(30,'30 km'),(40,'40 km'),(50,'50 km'),(75,'75 km'),(100,'100 km'),(150,'150 km'),(250,'250 km'),(500,'500 km'),(1000,'1000 km')))
    distance_mi = ChoiceField(choices=((10,'10 mi'),(20,'20 mi'),(20,'20 mi'),(30,'30 mi'),(40,'40 mi'),(50,'50 mi'),(75,'75 mi'),(100,'100 mi'),(150,'150 mi'),(250,'250 mi'),(500,'500 mi'),(1000,'1000 mi')))
    def __init__(self,*args,**kwargs):
        distance_units = self._owner = kwargs.pop('distance_units',None)
        super(SelectDistanceForm,self).__init__(*args,**kwargs)
        if distance_units == 1:
            self.fields['distance_km'].widget.attrs['style'] = 'display:none'
        else:
            self.fields['distance_mi'].widget.attrs['style'] = 'display:none'
        
        
    
    


class QEWhatForm(ModelForm):
    class Meta:
        include = []
    _verbose_name = 'What'
    name = CharField(label='Event Name')
    description = TextField(required=False)
    web_site = URLField(required=False)
    email = EmailField(required=False,label='Contact Email')

    def __init__(self,*args,**kwargs):
        self._owner = kwargs.pop('owner',None)        
        super(QEWhatForm,self).__init__(*args,**kwargs)
        if self.instance:
            self.fields['name'].initial = self.instance.name
            self.fields['description'].initial = self.instance.description
            self.fields['web_site'].initial = self.instance.web_site
            self.fields['email'].initial = self.instance.email

    def save(self):
        if not self.instance:
            venue = Venue(owner=self._owner)
            venue.put()
            try:
                event = Event(owner=self._owner,venue=venue,max_step=-1,quick=True,validators= [self._owner.key()],duration=120)
                event.put()
                self.instance = event
            except:
                db.delete(venue)
                raise

        self.instance.name = self.cleaned_data['name']
        self.instance.description = self.cleaned_data['description']
        if self.cleaned_data['web_site']:
            self.instance.web_site = self.cleaned_data['web_site']
        if self.cleaned_data['email']:
            self.instance.email = self.cleaned_data['email']
        self.instance.put()
        return self.instance

class QEWhereForm(ModelForm):
    class Meta:
        exclude = ['name','country','address','timezone']
    _verbose_name = 'Where'
    name = CharField()
    address = CharField()


    def __init__(self,*args,**kwargs):
        self._owner = kwargs.pop('owner',None)
        super(QEWhereForm,self).__init__(*args,**kwargs)        
        self.fields['address'].initial = self.instance.venue.address
        self.fields['name'].initial = self.instance.venue.name

    def clean(self):
        self.cleaned_data['latitude'], self.cleaned_data['longitude'], self.cleaned_data['addressname'], short_address, self.cleaned_data['country'] =\
            ValidateLocation(address=self.cleaned_data.get('address'))
        return self.cleaned_data

    def save(self):
        self.instance.venue.name = self.cleaned_data['name']
        self.instance.venue.country = self.cleaned_data['country']
        self.instance.venue.address = self.cleaned_data['address']
        self.instance.venue.location = db.GeoPt(self.cleaned_data['latitude'],self.cleaned_data['longitude'])
        self.instance.venue.put()
        self.instance.currency = get_currency_code(self.instance.venue.country)
        self.instance.put()
        return self.instance


class QEWhenForm(ModelForm):
    class Meta:
        include = []
    _verbose_name = 'When'
    time = TimeField()
    date = DateField()
    limit_duration = BooleanField(label='Event has a specific duration',required=False,initial=False)
    duration = IntegerField(required=False)
    door_open = IntegerField(label='Door Opens/Access')
    timezone = ChoiceField()
      
    def __init__(self,*args,**kwargs):
        self._owner = kwargs.pop('owner',None)
        super(QEWhenForm,self).__init__(*args,**kwargs)
        if self.instance.venue.timezone:
            self.fields['timezone'].initial = self.instance.venue.timezone
        else:
            self.fields['timezone'].initial = find_closest_timezone_choice(self.instance.venue.country,self.instance.venue.location)
        self.fields['time'].widget.attrs['class'] = 'ui-timepicker'
        self.fields['date'].widget.attrs['class'] = 'ui-datepicker'
        self.fields['door_open'].widget.attrs['class'] = 'ui-slider'
        self.max_date = datetime.now() + timedelta(days=365)
        self.min_date = datetime.now()  
        self.fields['duration'].widget.attrs['class'] = 'ui-slider'
        if self.instance:
            representation = self.instance.representation_set.get()
            if representation and representation.date:
                self.fields['time'].initial = representation.date.strftime('%H:%M')
                self.fields['date'].initial = representation.date.strftime('%m/%d/%Y')
        if self.instance.venue.country:
            country = self.instance.venue.country
        else:
            if self.is_bound:
                country = self.data['country']
            else:
                country = self.fields['country'].initial
        self.fields['timezone'].choices = construct_timezone_choice(country)


    def save(self):
        representation = self.instance.representation_set.get()
        if not representation:
            representation = Representation(owner=self.instance.owner, event=self.instance,venue=self.instance.venue)
        if 'date' in self.changed_data or 'time' in self.changed_data :
            representation.date = self.cleaned_data['date']
        self.instance.duration = self.cleaned_data['duration']
        self.instance.limit_duration = self.cleaned_data['limit_duration']
        self.instance.door_open = self.cleaned_data['door_open']
        self.instance.venue.timezone = self.cleaned_data['timezone']
        representation.timezone = self.cleaned_data['timezone']
        self.instance.venue.put()        
        self.instance.put()
        representation.put()
        return self.instance

    def clean(self):
        if 'date' in self.changed_data or 'time' in self.changed_data :
            if 'date' in self.cleaned_data and 'time' in self.cleaned_data :
                logging.debug(repr(self.cleaned_data['date']))
                logging.debug(repr(self.cleaned_data['time']))
                self.cleaned_data['date'] = datetime.combine(self.cleaned_data['date'],
                                                             self.cleaned_data['time']).replace(tzinfo=gaepytz.timezone(self.cleaned_data['timezone']))
                logging.debug(repr(self.cleaned_data['date']))
        if self.cleaned_data['limit_duration'] == True and self.cleaned_data['duration'] == 0:
            raise ValidationError('Event duration cannot be zero')
        return self.cleaned_data

class QEHowManyForm(ModelForm):

    _verbose_name= 'Tickets'

    nbr_tickets = IntegerField()
    is_free = ChoiceField(widget=RadioSelect,choices= [(1,'Tickets are free'),(2,'Tickets are sold for a fee')],label='Pricing Model')
    price = FloatField(required=False)

    def save(self):
        tc = self.instance.ticketclass_set.get()
        if not tc:
            tc = TicketClass(name='',owner=self.instance.owner, event=self.instance)
            sc = SeatConfiguration(name='Quick Event Generated',owner=self.instance.owner,venue=self.instance.venue)
            sc.put()
            sg = SeatGroup(name='',type='Venue',owner=self.instance.owner,parent=None,seat_configuration=sc)
            sg.put()
            self.instance.seat_configuration = sc
            self.instance.put()
            tc.seat_groups.append(sg.key())
        tc.general_admission = True
        if tc.general_admission:
            tc.name = 'General Admission'
        else:
            tc.name = None
        tc.price = self.cleaned_data['price']
        tc.put()
        sg = db.get(tc.seat_groups[0])
        sg.nbr_seat = self.cleaned_data['nbr_tickets']
        self.instance.seat_configuration.nbr_seat = sg.nbr_seat
        self.instance.seat_configuration.put()
        sg.put()
        return self.instance

    def clean(self):
        if 'is_free' not in self.cleaned_data or 'price' not in self.cleaned_data:
            raise ValidationError('Internal error, invalid form')
        if self.cleaned_data['is_free'] == "2" and (self.cleaned_data['price'] == None or self.cleaned_data['price'] == None):
            raise ValidationError('Price cannot be zero if you sell them for a fee')
        if self.cleaned_data['price'] == None:
            self.cleaned_data['price'] = 0.0
        return self.cleaned_data
    
    def __init__(self,*args,**kwargs):        
        self._owner = kwargs.pop('owner',None)
        super(QEHowManyForm,self).__init__(*args,**kwargs)
        tc = TicketClass.all().filter('event =',self.instance).get()
        self.fields['is_free'].initial = 1
        if tc:
            sg = db.get(tc.seat_groups[0])
            self.fields['nbr_tickets'].initial = sg.nbr_seat
            self.fields['price'].initial = tc.price
            if tc.price:
                self.fields['is_free'].initial = 2
            else:
                self.fields['is_free'].initial = 1
                self.fields['price'].initial = None
        self.currency = get_currency_symbol(self.instance.venue.country)

class QEOptionsForm(ModelForm):
    class Meta:
        include = ['onsale_date','endsale_date']
    _verbose_name = 'Options'

    limit_tickets = BooleanField(required=False,label='Number of Ticket purchased is limited')
    max_tickets = IntegerField(required=False,initial=6)
    cancellable = BooleanField(required=False,label='Ticket purchased can be cancelled')
    cancel_fees = FloatField(required=False,initial=30)
    cancel_delay = IntegerField(required=False,initial=7,label='Cancellation period runs out')
    restrict_sale_period = BooleanField(required=False)
    private = BooleanField(required=False,label='Make this event private (not searchable)')
    onsale_time = TimeField(required=False)
    onsale_date = DateField(required=False)
    endsale_time = TimeField(required=False)
    endsale_date = DateField(required=False)



    def __init__(self,*args,**kwargs):
        self._owner = kwargs.pop('owner',None)
        super(QEOptionsForm,self).__init__(*args,**kwargs)
        self.representation = Representation.all().filter('event =',self.instance).get()
        self.fields['max_tickets'].widget.attrs['class'] = 'ui-slider'
        self.fields['cancel_delay'].widget.attrs['class'] = 'ui-slider'
        self.fields['cancel_fees'].widget.attrs['class'] = 'ui-slider'
        self.fields['onsale_time'].widget.attrs['class'] = 'ui-timepicker'
        self.fields['onsale_date'].widget.attrs['class'] = 'ui-datepicker'
        self.fields['endsale_time'].widget.attrs['class'] = 'ui-timepicker'
        self.fields['endsale_date'].widget.attrs['class'] = 'ui-datepicker'
        self.max_onsale_date = self.representation.date 
        if self.instance.onsale_date:
            self.fields['onsale_time'].initial = self.instance.onsale_date.strftime('%H:%M')
            self.fields['onsale_date'].initial = self.instance.onsale_date.strftime('%m/%d/%Y')
        else:
            self.fields['onsale_time'].initial = '00:00'            
        if self.instance.endsale_date:
            self.fields['endsale_time'].initial = self.instance.endsale_date.strftime('%H:%M')
            self.fields['endsale_date'].initial = self.instance.endsale_date.strftime('%m/%d/%Y')
        else:
            self.fields['endsale_time'].initial = '00:00'

    def save(self):
        self.instance.limit_tickets = self.cleaned_data['limit_tickets']
        self.instance.max_tickets = self.cleaned_data['max_tickets']
        self.instance.cancellable = self.cleaned_data['cancellable']
        self.instance.cancel_fees = float(self.cleaned_data['cancel_fees'])
        self.instance.cancel_delay = self.cleaned_data['cancel_delay']
        if 'onsale_date' in self.changed_data or 'onsale_time' in self.changed_data :
            self.instance.onsale_date = self.cleaned_data['onsale_date']
        if 'endsale_date' in self.changed_data or 'endsale_time' in self.changed_data :    
            self.instance.endsale_date = self.cleaned_data['endsale_date']
        self.instance.restrict_sale_period =  self.cleaned_data['restrict_sale_period']
        self.instance.private = self.cleaned_data['private']
        self.instance.put()        
        return self.instance

    def clean(self):
        if 'onsale_date' in self.changed_data or 'onsale_time' in self.changed_data :
            if 'onsale_date' in self.cleaned_data and 'onsale_time' in self.cleaned_data :
                timezone = self.instance.venue.timezone
                self.cleaned_data['onsale_date'] = datetime.combine(self.cleaned_data['onsale_date'],
                                                             self.cleaned_data['onsale_time']).replace(tzinfo=gaepytz.timezone(timezone))

        if 'endsale_date' in self.changed_data or 'endsale_time' in self.changed_data :
            if 'endsale_date' in self.cleaned_data and 'endsale_time' in self.cleaned_data :
                timezone = self.instance.venue.timezone
                self.cleaned_data['endsale_date'] = datetime.combine(self.cleaned_data['endsale_date'],
                                                             self.cleaned_data['endsale_time']).replace(tzinfo=gaepytz.timezone(timezone))
        return self.cleaned_data


class QEImagesNoteForm(ModelForm):
    class Meta:
        include = []
    
    _verbose_name = 'Images and Notes'

    thumbnail = FileField(required=False,help_text='Image used in the event listing and on the tickets. It should be square\
                                     and exactly 200x200 pixels.',label='Ticket Image')
    poster = FileField(required=False,help_text='Image used when showing the event details. It should be\
                                  200 pixel wide and between 250-400 pixel long',label="Even's Page Image")    

    note = TextField(required=False)

    def save(self):
        self.instance.note = self.cleaned_data['note']
        handle_images(self,self.instance)
        self.instance.put()
        return self.instance
    def __init__(self,*args,**kwargs):
        self._owner = kwargs.pop('owner',None)
        super(QEImagesNoteForm,self).__init__(*args,**kwargs)
        self.fields['thumbnail'].initial = self.instance.thumbnail_image
        self.fields['poster'].initial = self.instance.poster_image
    
    
class QEPreviewForm(ModelForm):
    class Meta:
        include = []
    
    _verbose_name = 'Review & Publish'

    def save(self):
        #TODO call publishing Task
        self.instance.status = 'Published'
        self.instance.put()
        return self.instance

    def __init__(self,*args,**kwargs):
        self._owner = kwargs.pop('owner',None)
        super(QEPreviewForm,self).__init__(*args,**kwargs)
        self.representation = Representation.all().filter('event =',self.instance).get()
        self.ticket_class = TicketClass.all().filter('event =',self.instance).get()
        self.sg = db.get(self.ticket_class.seat_groups[0])
        
class QuickEventWizard(object):
    
    def __init__(self,form_list,view,redirect,step=0,instance=None,files=None,data=None,owner=None):
        self.form_list = form_list
        self.instance = instance
        self.current_step = step
        self.files = files
        self.data = data
        self.redirect = redirect
        self.view = view
        self.owner = owner
        if not instance:
            self.max_step = -1
        else:
            if not hasattr(self.instance,'max_step'):
                raise AttributeError
            if self.instance.max_step == None:
                self.max_step = 0
            self.max_step = self.instance.max_step
             

    def is_valid(self):
        step = self.current_step
        if not hasattr(self,'form-%d' % step):
            setattr(self,'form-%d' % step,self.form_list[step](instance=self.instance,files=self.files,data=self.data,owner=self.owner))
        return getattr(self,'form-%d' % step).is_valid()

    def save(self):
        step = self.current_step
        if not hasattr(self,'form-%d' % step):
            if self.instance:
                self.instance.max_step = step
            setattr(self,'form-%d' % step,self.form_list[step](instance=self.instance,files=self.files,data=self.data,owner=self.owner))
        qe =  getattr(self,'form-%d' % step).save()
        if qe.max_step < self.current_step:
            qe.max_step = self.current_step
            qe.put()
        return qe

    def _render(self,request,step):   
        form = self.form_list[step](instance=self.instance,data=self.data,files=self.files,owner=self.owner)
        template_name = self.get_template_name(step)
        steps = []; index = 0
        for item in self.form_list:
            class info(object):
                name = ''
                url = ''
            a = info()
            a.name = item._verbose_name    
            if index <= self.max_step+1:
                if self.instance:
                    a.url = reverse(self.view,kwargs={'key':str(self.instance.key()),}) + '?step=%d' % (index)
                else:
                    a.url = reverse(self.view) + '?step=%d' % index
            index = index + 1
            steps.append(a)
        
        self.previous_step_url = None
        if step > 0:
            self.previous_step_url = reverse(self.view,kwargs={'key':str(self.instance.key()),}) + '?step=%d' % (step-1)
        c = {'form':form,'step':step,
             'step_info':steps,'max_step':self.max_step,
             'total_step':len(self.form_list),'previous_step_url':self.previous_step_url}
        return render_to_response(request,template_name, c)


    def render(self,request):
        if self.current_step > len(self.form_list)-1:
            return HttpResponseRedirect(self.redirect)
        return self._render(request,self.current_step)
    
    def get_template_name(self, step):
        return 'banian/QE/wizard_%s.html' % step


class ValidationForm(Form):
        
    ticket_id = CharField(required=False)
    ticket_number = IntegerField(required=False)


    def __init__(self,*args,**kwargs):
        self._validator = kwargs.pop('validator',None)
        super(ValidationForm,self).__init__(*args,**kwargs)
        self.fields['ticket_id'].widget.attrs['style'] = 'width:250px'

