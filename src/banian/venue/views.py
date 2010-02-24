# -*- coding: utf-8 -*-

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect #@UnusedImport
from django.template import RequestContext, loader
from django.views.generic.list_detail import object_list, object_detail
from django.views.generic.create_update import delete_object #@UnresolvedImport
from django.contrib.auth.decorators import login_required

from banian.utils import update_seat_config, update_seat_group
from banian.models import Venue, SeatConfiguration, SeatGroup, Event
from banian.venue.forms import VenueForm, SeatConfigurationForm, SeatGroupForm
from banian.utils import update_object, create_object, get_own_object_or_404
from banian.model_utils import construct_timezone_choice  
import logging
@login_required
def venues(request):
    return object_list(request,Venue.all().filter('owner =',request.user),template_object_name='venue')

@login_required
def show_venue(request, key):
    venue = get_own_object_or_404(request.user,Venue,key)
    timezone = ''
    for item in construct_timezone_choice(venue.country):
        if item[0] == venue.timezone:
            if len(item) == 2:
                timezone = item[1]
            else:
                timezone = item[2]
            
    extra = { 'seatconfiguration_set': venue.seatconfiguration_set.order('name'),'venue_key':key,'timezone':timezone,}
    return object_detail(request, Venue.all().filter('owner =',request.user), key, extra_context=extra)
    
@login_required
def add_venue(request):
    return create_object(request,
                         form_class=VenueForm,
                         post_save_redirect=reverse('banian.venue.views.show_venue',kwargs=dict(key='%(key)s')),
                         form_kwargs={'owner':request.user})  

        
@login_required
def edit_venue(request, key):
    venue = get_own_object_or_404(request.user,Venue,key)
    if not venue.mutable():
        return HttpResponseForbidden()    
    return update_object(request, object_id=key, form_class=VenueForm,extra_context=None,
                         post_save_redirect=reverse('banian.venue.views.show_venue',kwargs=dict(key='%(key)s')))

@login_required
def delete_venue(request, key):
    venue = get_own_object_or_404(request.user,Venue,key)
    if not venue.mutable():
        return HttpResponseForbidden()
    logging.debug(venue.poster_image.key())
    logging.debug(venue.thumbnail_image.key())
    return delete_object(request, Venue, object_id=key,
        post_delete_redirect=reverse('banian.venue.views.venues'))


@login_required
def seat_configs(request):
    venue = get_own_object_or_404(request.user,Venue,request.GET['venue'])
    seat_config_list = SeatConfiguration.all().filter('owner =',request.user).filter('venue =',venue).order('name')
    extra = { 'venue_key':venue.key(),'venue':venue,}
    return object_list(request,seat_config_list,template_object_name='seat_config',extra_context = extra)

@login_required
def show_seat_config(request, key):
    seat_config = get_own_object_or_404(request.user,SeatConfiguration,key)
    extra = {'seat_group_list':seat_config.seatgroup_set.filter('seat_group =', None).order('name'), }
    return object_detail(request, SeatConfiguration.all().filter('owner =',request.user), key, extra_context=extra)    

@login_required
def edit_seat_config(request, key):
    seat_config = get_own_object_or_404(request.user,SeatConfiguration,key)
    return update_object(request, object_id=key, form_class=SeatConfigurationForm,
                         extra_context = {'venue_key':seat_config.venue.key(),},
                         post_save_redirect=reverse('banian.venue.views.show_seat_config',kwargs=dict(key='%(key)s')))

@login_required
def add_seat_config(request):
    if 'venue' not in request.GET:
        venues = Venue.all().filter('owner =',request.user)
        if not venues.count():
            t = loader.get_template("banian/venue_confirm_creation.html")
            c = RequestContext(request, {'redirect':reverse('banian.venue.views.add_seat_config')})
            return HttpResponse(t.render(c))
        else:
            url = reverse('banian.views.select_venue') + '?redirect=' + reverse('banian.venue.views.add_seat_config')
            return HttpResponseRedirect(url)
    else:
        venue = get_own_object_or_404(request.user,Venue,request.GET['venue'])
        return create_object(request,
                             form_class=SeatConfigurationForm,
                             post_save_redirect=reverse('banian.venue.views.show_seat_config',kwargs=dict(key='%(key)s')),
                             form_kwargs={'owner':request.user,'venue':venue,},
                             extra_context = {'venue_key':venue.key(),})  
 
@login_required
def delete_seat_config(request, key):
    seat_config = get_own_object_or_404(request.user,SeatConfiguration,key)
    return delete_object(request, seat_config, extra_context=None ,object_id=key,
                         post_delete_redirect=reverse('banian.venue.views.show_venue',
                                                      kwargs={'key':seat_config.venue.key(),}))


@login_required
def seat_groups(request):
    seat_group_list = SeatGroup.all().filter('owner =',request.user).order('name')
    return object_list(request,seat_group_list,template_object_name='seat_group',extra_context = None)

@login_required
def show_seat_group(request, key):
    seat_group = get_own_object_or_404(request.user,SeatGroup,key)
    extra = {'seat_group_list':SeatGroup.all().filter('seat_group =',seat_group).order('name'), }
    return object_detail(request, SeatGroup.all().filter('owner =',request.user), key, extra_context=extra)    

@login_required
def edit_seat_group(request, key):
    get_own_object_or_404(request.user,SeatGroup,key)
    return update_object(request, object_id=key, form_class=SeatGroupForm,extra_context= None,
                         post_save_redirect=reverse('banian.venue.views.show_seat_group',kwargs=dict(key='%(key)s')))

@login_required
def add_seat_group(request):
    parent = None
    extra = {}
    if 'parent' in request.GET: 
        parent = get_own_object_or_404(request.user,SeatGroup,request.GET.get('parent'))
        extra['parent_key'] = parent.key()
    seat_configuration = get_own_object_or_404(request.user,SeatConfiguration,request.GET['seat_configuration'])
    extra['seat_configuration_key'] = request.GET['seat_configuration']
    if parent:
        post_save_redirect = reverse('banian.venue.views.show_seat_group',kwargs=dict(key=parent.key()))
    else:
        post_save_redirect = reverse('banian.venue.views.show_seat_config',kwargs=dict(key=seat_configuration.key()))
    return create_object(request,
                         form_class=SeatGroupForm,
                         post_save_redirect=post_save_redirect,
                         form_kwargs={'owner':request.user,'seat_configuration':seat_configuration,'parent':parent,},
                         extra_context = extra)
   
@login_required
def delete_seat_group(request, key):
    seat_group = get_own_object_or_404(request.user,SeatGroup,key)
    parent = seat_group.parent()
    seat_configuration = seat_group.seat_configuration
    if seat_group.parent():
        post_delete_redirect=reverse('banian.venue.views.show_seat_group',
                                     kwargs= {'key':seat_group.parent().key(),})
    else:
        post_delete_redirect=reverse('banian.venue.views.show_seat_config',
                                     kwargs= {'key':seat_group.seat_configuration.key(), })
    response = delete_object(request, seat_group, extra_context=None ,object_id=key,
                         post_delete_redirect=post_delete_redirect)
    if request.method == 'POST':
        update_seat_config(seat_configuration)
        update_seat_group(parent)
    return response

