# -*- coding: utf-8 -*-
from django.forms.models import ModelForm
from django.forms.fields import FileField, ChoiceField
from django.forms.forms import ValidationError
from banian.models import Venue, SeatConfiguration, SeatGroup

from google.appengine.ext import db
from banian.forms import ValidateLocation, cctld

from banian.utils import update_seat_config, update_seat_group, handle_images

from banian.model_utils import construct_timezone_choice 


class VenueForm(ModelForm):
    thumbnail = FileField(required=False,help_text='Image used in the venue listing. It should be square\
                                     and exactly 100x100 pixels.')
    poster = FileField(required=False,help_text='Image used when showing the venue details. It should be\
                                  200 pixel wide and between 250-400 pixel long')
    timezone = ChoiceField(choices=construct_timezone_choice('US'))
    
    class Meta:
        model = Venue
        exclude = ['owner','poster', 'thumbnail', 'poster_image', 'thumbnail_image','location','status']

    def __init__(self,**kwargs):
        self._owner = kwargs.pop('owner',None)
        super(VenueForm,self).__init__(**kwargs)
        timezone = self.fields['timezone']
        if self.instance:
            country = self.instance.country
            timezone.choices = construct_timezone_choice(country)
            timezone.initial = self.instance.timezone
        else:
            if self.is_bound:
                country = self.data['country']
            else:
                country = 'US'
            timezone.choices = construct_timezone_choice(country)

    def save(self):
        if not self.instance:
            venue = Venue(name=self.cleaned_data['name'],
                          description=self.cleaned_data['description'],
                          web_site=self.cleaned_data['web_site'],
                          address=self.cleaned_data['address'],
                          country=self.cleaned_data['country'],
                          timezone= self.cleaned_data['timezone'],
                          owner=self._owner)
            handle_images(self,venue)
            venue.addressname = self.cleaned_data['addressname']
            venue.location = db.GeoPt(self.cleaned_data['latitude'],self.cleaned_data['longitude'])
            try:
                venue.put()
            except Exception:
                if(venue.thumbnail_image):
                    db.delete(venue.thumbnail_image)
                if(venue.poster_image):
                    db.delete(venue.poster_image)
                raise Exception
            return venue
        else:
            if not self.instance.mutable():
                raise AssertionError             
            self.instance.addressname = self.cleaned_data['addressname']
            self.instance.location = db.GeoPt(self.cleaned_data['latitude'],self.cleaned_data['longitude'])
            handle_images(self,self.instance)
            return super(VenueForm,self).save()

    def clean(self):
        self.cleaned_data['latitude'], self.cleaned_data['longitude'], self.cleaned_data['addressname'], short_address, self.cleaned_data['country'] =\
            ValidateLocation(address=self.cleaned_data.get('address'))
        for (key,value) in self.files.iteritems(): #@UnusedVariable
            try:
                i = value.name.rindex('.')
            except:
                raise ValidationError('invalid file name')
            if value.name[i+1:].lower() not in ['jpg','gif','png']:
                raise ValidationError('Unsuported image file format')
        return self.cleaned_data


  
class SeatConfigurationForm(ModelForm):
    class Meta:
        model = SeatConfiguration
        exclude = ['owner','venue','last_modified','created','nbr_seat',]

    def __init__(self,**kwargs):
        self._owner = kwargs.pop('owner',None)
        self._venue = kwargs.pop('venue',None)
        super(SeatConfigurationForm,self).__init__(**kwargs)
        
    def save(self):
        if not self.instance:
            seat_config = SeatConfiguration(name=self.cleaned_data['name'],
                                            description=self.cleaned_data['description'],
                                            venue=self._venue,
                                            owner=self._owner)
            seat_config.put()
            return seat_config
        else:
            if not self.instance.mutable():
                raise AssertionError             
            return super(SeatConfigurationForm,self).save()


class SeatGroupForm(ModelForm):
    class Meta:
        model = SeatGroup
        exclude = ['owner','seat_configuration', 'parent','last_modified','created','seat_group','total_nbr_seat',]

    def __init__(self,**kwargs):
        self._owner = kwargs.pop('owner',None)
        self._seat_configuration = kwargs.pop('seat_configuration',None)
        self._parent = kwargs.pop('parent',None)
        super(SeatGroupForm,self).__init__(**kwargs)      

    
    def save(self):
        if not self.instance:
            seat_group = SeatGroup(name=self.cleaned_data['name'],
                               type=self.cleaned_data['type'],
                               priority=self.cleaned_data['priority'],
                               nbr_seat=self.cleaned_data['nbr_seat'],
                               owner=self._owner,
                               seat_configuration=self._seat_configuration,
                               parent = self._parent,
                               seat_group = self._parent,
                               )

            seat_group.put()
            update_seat_config(self._seat_configuration)
            update_seat_group(seat_group)
            return seat_group
        else:
            if not self.instance.mutable():
                raise AssertionError             
            sg = super(SeatGroupForm,self).save()
            update_seat_config(self.instance.seat_configuration)
            update_seat_group(self.instance)
            super(SeatGroupForm,self).save()
            return sg

