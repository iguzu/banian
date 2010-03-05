# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from uuid import uuid4
from google.appengine.api import images
from google.appengine.ext import db
from google.appengine.api.labs.taskqueue import taskqueue
from google.appengine.api import memcache

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, HttpResponseServerError, HttpResponseNotFound
from django.views.generic.list_detail import object_list, object_detail
from django.views.generic.create_update import delete_object, redirect
from django.contrib.auth.decorators import login_required
from django.template import RequestContext, loader
from django.contrib.auth.models import Message
from django.utils.translation import ugettext #@UnresolvedImport
from django.utils.simplejson import dumps
from django.forms.forms import ValidationError
from ragendja.template import render_to_response #@UnresolvedImport
from ragendja.dbutils import get_object_or_404 #@UnresolvedImport
from django.contrib.auth.models import User
import banian.paypal
from geo.geotypes import Box
from recaptcha.client import captcha
from registration.forms import RegistrationForm
from banian.models import Venue, Event, TicketClass, Seat, Image, Representation, fetch_limit,\
                          Ticket, Transaction, UserEvent, max_ticket_limit,\
    TicketScan
from banian.utils import update_object, create_object, get_own_object_or_404, points2distance, \
                         location_window, reserve_seats, preparePayment, \
                         take_seats, calc_ticket_class_available, ElementExtracter,\
    transfer_to_paypal, generate_tickets
from banian.model_utils import construct_timezone_choice  
from banian.forms import EventForm, SelectVenueForm, SettingsForm, TicketClassForm, \
                         SelectSeatConfigForm, RepresentationForm, SelectTicketForm, SelectDistanceForm, QuickEventWizard,\
    QEHowManyForm, QEImagesNoteForm, QEOptionsForm, QEPreviewForm, QEWhatForm,\
    QEWhenForm, QEWhereForm, ValidationForm
from banian.models import google_images
import sys
import urllib
import gaepytz
import logging
import gviz_api

event_edit_form_list = [QEWhatForm,QEWhereForm,QEWhenForm,QEHowManyForm,QEOptionsForm,QEImagesNoteForm,QEPreviewForm]

def default(request):
    t = loader.get_template('main.html')
    chtml = captcha.displayhtml(public_key="6LcoxQcAAAAAAHdG6W6ojYccJckkkMLg5myaLUw9", use_ssl=False, error=None)
    c = RequestContext(request)
    c['form'] = RegistrationForm()
    c['captchahtml'] = chtml
    return HttpResponse(t.render(c))

@login_required
def events(request):
    extra = {}
    
    if 'venue' in request.GET:
        venue = get_own_object_or_404(request.user, Venue, request.GET['venue'])
        event_list = venue.event_set
        extra['venue'] = venue
    else:
        event_list = Event.all().filter('owner =', request.user).order('-firstdate')
    return object_list(request, event_list, paginate_by=5, template_object_name='event', extra_context=extra)

@login_required
def show_event(request, key):
    event = get_own_object_or_404(request.user, Event, key)
    representation = event.first_representation()
    job_id = None; progress = 0; message = 'Not Started'
    if representation:
        job_id = representation.job_id        
    if job_id:
        job_info = memcache.get_multi([job_id + "-count",job_id + "-message",job_id + "-total"]) #@UndefinedVariable
        if job_id + "-message" in job_info:
            message = job_info[job_id + "-message"]
        if job_id + "-total" in job_info and job_id + "-count" in job_info:
            progress = (float(job_info[job_id + "-count"]) / float(job_info[job_id + "-total"])) * 100.0
    context = {'representation':representation,'progress':progress, 'message':message,}
    if representation and representation.pre_approval_status == "Processing":
        context['display_unpublish'] = True
    if representation and representation.status in ('On Sale', 'Published'):
        if Ticket.all().filter('representation =',event.first_representation()).get():
            context['display_cancel'] = True
        else:
            context['display_unpublish'] = True
        context['display_doorman'] = True
        context['display_link_message'] = True
    return object_detail(request, Event.all(), key, extra_context=context)    

@login_required
def edit_event_pro(request, key):
    event = get_own_object_or_404(request.user, Event, key)
    venue = get_own_object_or_404(request.user, Venue, event.venue.key())
    first_representation = Representation.all().filter('event =',event).order('date').get()
    max_onsale_date = None
    if first_representation:
        max_onsale_date = first_representation.date+timedelta(days=-1)
    seat_configurations = []
    for seat_configuration in venue.seatconfiguration_set.order('name'):
        seat_configurations.append((seat_configuration.key(), seat_configuration.name))
    timezone = ''
    for item in construct_timezone_choice(venue.country):
        if item[0] == venue.timezone:
            if len(item) == 2:
                timezone = item[1]
            else:
                timezone = item[2]

    return update_object(request, object_id=key,
                         form_class=EventForm,
                         form_kwargs={'owner':request.user, 'venue':venue, 'choices':seat_configurations,
                                      'max_onsale_date':max_onsale_date,},
                         extra_context={ 'venue_key':venue.key(),'timezone':timezone, },
                         post_save_redirect=reverse('banian.views.show_event', kwargs=dict(key='%(key)s')))

@login_required
def add_event_pro(request):
    if 'venue' not in request.GET:
        venues = Venue.all().filter('owner =', request.user)
        if  venues.count() == 0:
            t = loader.get_template("banian/venue_confirm_creation.html")
            c = RequestContext(request, {'redirect':reverse('banian.views.add_event')})
            return HttpResponse(t.render(c))
        elif venues.count() == 1:
            venue = venues.get()
            return HttpResponseRedirect(reverse('banian.views.add_event') + '?venue=' + str(venue.key()))
        elif venues.count() > 1:
            url = reverse('banian.views.select_venue') + '?redirect=' + reverse('banian.views.add_event')
            return HttpResponseRedirect(url)
    else:
        if request.method == 'POST':
            pass
        venue = get_own_object_or_404(request.user, Venue, request.GET['venue'])
        timezone = ''
        for item in construct_timezone_choice(venue.country):
            if item[0] == venue.timezone:
                if len(item) == 2:
                    timezone = item[1]
                else:
                    timezone = item[2]
        seat_configurations = []
        for seat_configuration in venue.seatconfiguration_set.order('name'):
            seat_configurations.append((seat_configuration.key(), seat_configuration.name))
        initial = {'cancel_delay':7, 'door_open':120.0, 'duration':0.0, 'cancel_fees':30.0}
        return create_object(request,
                             form_class=EventForm,
                             post_save_redirect=reverse('banian.views.show_event', kwargs=dict(key='%(key)s')),
                             extra_context={'venue_key':venue.key(),'timezone':timezone},
                             form_kwargs={'owner':request.user, 'venue':venue,
                                          'choices':seat_configurations, 'initial':initial,})  

@login_required
def representation_ticket_history(request,key):
    representation = get_own_object_or_404(request.user, Representation, key)
    format = request.GET.get('format','JSON')
    description = { 'date':'date', 'tickets':'number' }
    assert(len(representation.histo_ticket) == len(representation.histo_time))
    data = []
    for index,item in enumerate(representation.histo_ticket):
        data.append({'date':datetime.utcfromtimestamp(representation.histo_time[index]).replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone(representation.event.venue.timezone)),'tickets':item})      
    dataTable = gviz_api.DataTable(description)
    dataTable.LoadData(data)
    if format == 'JSON':
        reqId = request.GET.get('reqID',None)
        response = dataTable.ToJSonResponse(reqId)
        return HttpResponse(response)
    else:
        return HttpResponseNotFound()

@login_required
def delete_event(request, key):
    event = get_own_object_or_404(request.user, Event, key)
    if not event.mutable():
        return HttpResponseForbidden()
    return delete_object(request, event, extra_context=None , object_id=key,
        post_delete_redirect=reverse('banian.views.events'))


def view_event(request, key):
    event = get_object_or_404(Event, key)
    if event.visibility == 'Draft':
        return HttpResponseNotFound()
    rep_list = Representation.gql("WHERE event = :1 AND status IN :2 ORDER BY date", event, ['Published', 'Sold Out', 'On Sale','Sale Closed']).fetch(fetch_limit)
    extra = {'representation_set':rep_list,}
    return object_detail(request, Event.all(), key, extra_context=extra, template_name='banian/event_view.html')    


@login_required
def select_venue(request):
    venue_list = []
    for venue in Venue.all().filter('owner =', request.user):
        venue_list.append((venue.key(), venue.name))
        
    if request.method == 'POST':
        form = SelectVenueForm(data=request.POST, files=request.FILES, choices=venue_list)
        if form.is_valid():
            venue_key = form.cleaned_data['venue']
            if 'redirect'in request.GET:
                return HttpResponseRedirect(request.GET.get('redirect') + '?venue=' + venue_key)
            else:
                return redirect(reverse('banian.venue.views.show_venue'), venue_key)
    else:
        form = SelectVenueForm(choices=venue_list)
    return render_to_response(request, 'banian/select_venue.html', { 'form': form, })

@login_required
def view_venue(request, key):
    venue = get_own_object_or_404(request.user, Venue, key)
    rep_list = venue.representation_set.order('-date')
    extra = {'representation_set':rep_list}
    return object_detail(request, Venue.all().filter('owner =', request.user), key, extra_context=extra, template_name='banian/venue_view.html')    

@login_required
def settings(request):
    user = request.user
    if request.method == 'POST':
        form = SettingsForm(data=request.POST, files=request.FILES, instance=user,empty_permitted=True)
        if form.is_valid():
            form.save()
            if request.user.is_authenticated():
                Message(user=request.user, message=ugettext("%(verbose_name)s was updated successfully.") % {"verbose_name": form._verbose_name}).put()
            if 'redirect'in request.GET:
                return HttpResponseRedirect(request.GET.get('redirect'))
            else:
                return HttpResponseRedirect(reverse('banian.views.default'))
    else:
        form = SettingsForm(instance=user)
    return render_to_response(request, 'banian/settings_form.html', { 'form': form,'username':request.user.username, })


def image(request, key):
    suffix = ''
    image = get_object_or_404(Image, key)
    if 'small' in request.GET:
        suffix = '-small'
        response = memcache.get(key+suffix) #@UndefinedVariable
        if response:
            return response
        img = images.Image(image.content)
        if img.width > 50 or img.height > 50:
            img.resize(50, 50)
            response = HttpResponse(img.execute_transforms(google_images[image.content_type]))
        else:
            response = HttpResponse(image.content)
    elif 'medium' in request.GET:
        suffix = '-medium'
        response = memcache.get(key+suffix) #@UndefinedVariable
        if response:
            return response
        img = images.Image(image.content)
        if img.width > 100 or img.height > 100:
            img.resize(100, 100)        
            response = HttpResponse(img.execute_transforms(google_images[image.content_type]))
        else:
            response = HttpResponse(image.content)
    else:
        response = memcache.get(key+suffix) #@UndefinedVariable
        if response:
            return response        
        response = HttpResponse(image.content)
    response['content-type'] = "image/" + image.content_type
    memcache.set(key + suffix, response) #@UndefinedVariable
    return response

@login_required
def add_class(request):
    event = get_own_object_or_404(request.user, Event, request.GET['event'])
    if not event.mutable():
        return HttpResponseForbidden("Ticket Class cannot be modified after seats were created")
    if not event.seat_configuration:
        url = reverse('banian.views.select_seat_config') + '?event=%s' % event.key()
        return HttpResponseRedirect(url)
    
    choices = []
    for seat_group in event.seat_configuration.seatgroup_set:
        choices.append((seat_group.key(), seat_group.name))
        
    return create_object(request,
                     form_class=TicketClassForm,
                     post_save_redirect=reverse('banian.views.show_class', kwargs=dict(key='%(key)s')),
                     extra_context={'event_key':event.key(), },
                     form_kwargs={'choices':choices, 'owner':request.user, 'event':event})

@login_required
def show_class(request, key):
    ticket_class = get_own_object_or_404(request.user, TicketClass, key)
    seat_groups = []
    total_nbr_seat = 0
    for item in ticket_class.seat_groups:
        try:
            seat_groups.append(db.get(item).name)
            total_nbr_seat += db.get(item).nbr_seat
        except:
            pass 
        total_revenue = total_nbr_seat * ticket_class.price
    return object_detail(request, TicketClass.all().filter('owner =', request.user), key,
                         extra_context={'seat_groups':seat_groups, 'total_revenue':total_revenue,
                                        'total_nbr_seat':total_nbr_seat, })   

@login_required
def edit_class(request, key):
    ticket_class = get_own_object_or_404(request.user, TicketClass, key)
    event = get_own_object_or_404(request.user, Event, ticket_class.event.key())
    if not event.mutable():
        return HttpResponseForbidden("Ticket Class cannot be modified after seats were created")
    event_key = ticket_class.event.key()
    if ticket_class.event.seat_configuration:
        choices = []
        for seat_group in ticket_class.event.seat_configuration.seatgroup_set:
            choices.append((seat_group.key(), seat_group.name))

    return update_object(request,
                         object_id=key,
                         form_class=TicketClassForm, extra_context={ 'event_key':event_key, },
                         post_save_redirect=reverse('banian.views.show_class', kwargs=dict(key='%(key)s')),
                         form_kwargs={'choices':choices, })

@login_required
def delete_class(request, key):
    ticket_class = get_own_object_or_404(request.user, TicketClass, key)
    event = get_own_object_or_404(request.user, Event, ticket_class.event.key())
    if not event.mutable():
        return HttpResponseForbidden("Ticket Class cannot be modified after seats were created")

    if ticket_class.owner != request.user:
        return HttpResponseForbidden('It is not allowed to delete an event you do not own.')    
    return delete_object(request, ticket_class, extra_context=None , object_id=key,
        post_delete_redirect=reverse('banian.views.show_event', kwargs={'key':ticket_class.event.key(), }))


@login_required
def select_seat_config(request):
    event = get_own_object_or_404(request.user, Event, request.GET.get('event'))
    seat_configurations = []
    for seat_configuration in event.venue.seatconfiguration_set.order('name'):
        seat_configurations.append((seat_configuration.key(), seat_configuration.name))
    if request.method == 'POST':
        form = SelectSeatConfigForm(data=request.POST, files=request.FILES, choices=seat_configurations)
        if form.is_valid():
            event.seat_configuration = db.Key(form.cleaned_data['seat_config'])
            event.put()
            return HttpResponseRedirect(reverse('banian.views.add_class') + '?event=%s' % event.key())
    else:
        form = SelectSeatConfigForm(choices=seat_configurations)
    return render_to_response(request, 'banian/select_seat_config.html', { 'form': form, })


@login_required
def publish(request, key):
    representation = get_own_object_or_404(request.user,Representation, key)
    event = get_own_object_or_404(request.user, Event, representation.event.key())
    context = { 'representation':representation, } 

    # Validate publication
    if representation.status != 'Draft' and representation.status != 'Processing Payment':
        Message(user=request.user, message='Event is already published').put()
        return HttpResponseRedirect(reverse('banian.views.show_event',kwargs={'key':event.key(),}))            
    if representation.total_cost() and (request.user.paypal_id == '' or request.user.paypal_id == None):
        Message(user=request.user, message='Invalid PayPal account. Change your PayPal account in "My account" settings').put()
        return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6')
    if representation.date < datetime.utcnow().replace(tzinfo=gaepytz.utc):
        # if representation is in that past, do not allow to put in sale 
        Message(user=request.user, message='Cannot publish an event scheduled in the past. Is the event date is correct?').put()
        return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6')
    if event.restrict_sale_period and event.endsale_date and event.endsale_date < datetime.utcnow().replace(tzinfo=gaepytz.utc):
        # if sale period is in the that past, do not allow to put in sale 
        Message(user=request.user, message='Cannot publish an event with an sale end date in the past. Is the event endsale date is correct?').put()
        return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6')        
    if event.max_step < len(event_edit_form_list)-2:
        # if the user didn't through alls steps, one by one. 
        Message(user=request.user, message='Complete all publishing steps before publishing').put()
        return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6')        

    # Do publishing
    publish = False
    if request.method == 'POST':
        if representation.total_cost() == 0:
            publish = True
        else:
            # Create a paypal preapproval
            memo = "Payment pre-approval to publish %s\n Total %.2f $:\n  - %.2f  for publishing %d tickets (at 0.01$/ticket)." % (representation.event.name + ', ' + str(representation.date),representation.total_cost(),representation.publishing_cost(),0)
            startDate = datetime.utcnow().replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('US/Pacific'))
            if representation.commission_cost():
                memo = memo + '\n  -Up to %.2f $ in comission if the representation solds out (1%% of %.2f $).' % (representation.commission_cost(),representation.event.representation_value())
            preApprovalStatus, preApprovalKey = banian.paypal.processPreApproval(memo = memo,
                                                   amount = representation.total_cost(),
                                                   paypal_id= request.user.paypal_id,
                                                   returnURL = 'http://www.iguzu.com' + reverse('banian.views.publish',kwargs={'key':representation.key(),})+'?status=completed',
                                                   cancelURL = 'http://www.iguzu.com' + reverse('banian.views.publish',kwargs={'key':representation.key(),})+'?status=cancelled',
                                                   startDate = startDate,
                                                   endDate = representation.date + timedelta(days=2))
            if preApprovalStatus == 'past_start_date':
                startDate = startDate + timedelta(days=1)
                preApprovalStatus, preApprovalKey = banian.paypal.processPreApproval(memo = memo,
                                                       amount = representation.total_cost(),
                                                       paypal_id= request.user.paypal_id,
                                                       returnURL = 'http://www.iguzu.com' + reverse('banian.views.publish',kwargs={'key':representation.key(),})+'?status=completed',
                                                       cancelURL = 'http://www.iguzu.com' + reverse('banian.views.publish',kwargs={'key':representation.key(),})+'?status=cancelled',
                                                       startDate = startDate,
                                                       endDate = representation.date + timedelta(days=2))
                
            if preApprovalStatus == 'Processing':             
                # pre approval we created, tranfert to paypal
                representation.pre_approval_status = 'Processing'
                representation.pre_approval_key = preApprovalKey
                representation.paypal_id = request.user.paypal_id
                representation.status = 'Processing Payment'
                representation.put()
                return transfer_to_paypal(request,"https://www.sandbox.paypal.com/webscr?cmd=_ap-preapproval&preapprovalkey=%s" % preApprovalKey)
            elif preApprovalStatus == 'invalid_account':
                Message(user=request.user, message='Invalid PayPal account. Change your PayPal account in "My account" settings').put()
                return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6')
            else:
                Message(user=request.user, message='An error has occured with paypal. Try again later').put()
                return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6')            
    else:
        # Is it a tranfer back from paypal?
        if 'status' in request.GET:
            status = request.GET['status']
            if status == 'Canceled':
                # user elect to approve later, simply redirect
                return HttpResponseRedirect(reverse('banian.views.show_event', kwargs={'key':event.key(), }))
        # Was pre approval previously attempted?
        if representation.pre_approval_status == 'Processing':
            preApprovalStatus = banian.paypal.getPreApprovalDetails(representation.pre_approval_key)
            if preApprovalStatus == 'Completed':
                publish = True
            elif preApprovalStatus == 'Processing':
                # oups still not approved... redirect to paypal 
                return transfer_to_paypal(request,"https://www.sandbox.paypal.com/webscr?cmd=_ap-preapproval&preapprovalkey=%s" % representation.pre_approval_key)
    if publish:
        # Yeah we have pre approved payment, lets publish the event
        representation.pre_approval_status = 'Completed'
        total_seats = 0
        for ticket_class in representation.event.ticketclass_set:
            for seat_group_key in ticket_class.seat_groups:
                seat_group = db.get(seat_group_key)
                total_seats = total_seats + seat_group.nbr_seat
        job_id = str(uuid4())
        representation.status = 'Generating'
        representation.job_id = job_id
        representation.put()
        if event.visibility == 'Draft':
            event.visibility = 'Published'
            event.put()
        ticket_class = TicketClass.gql("WHERE event=:1 ORDER BY __key__", event).get()
        seat_group = ticket_class.seat_groups[0]
        taskqueue.add(url='/tasks/generate_seats/', params={'representation':representation.key(), 'ticket_class':ticket_class.key(), 'seat_group':seat_group,'job_id':job_id}, countdown=0)
        memcache.set(job_id + '-count', 0) #@UndefinedVariable
        memcache.set(job_id + '-message', 'Not Started') #@UndefinedVariable
        memcache.set(job_id + '-total', total_seats) #@UndefinedVariable
        return HttpResponseRedirect(reverse('banian.views.show_event', kwargs={'key':event.key(), }))
    return render_to_response(request, 'banian/publish_confirm.html', context)

@login_required
def show_seat(request, key):
    seat = get_object_or_404(Seat, key)  ## Not owned!!!!
    representation = get_own_object_or_404(request.user, Representation, seat.representation.key())
    event = get_own_object_or_404(request.user, Event, representation.event.key())
    extra = {'event':event, 'representation':representation, }
    if 'redirect_page' in request.GET:
        extra['redirect_page'] = request.GET['redirect_page']
    page = request.GET.get('page', None)
    if page:
        extra['page'] = page
    return object_detail(request, Seat.all(), key, extra_context=extra)    

@login_required
def seats(request,key):
    representation = get_own_object_or_404(request.user, Representation, key)
    event = representation.event
    extra = {'event':event, 'representation':representation}
    page = request.GET.get('page', None)
    if page:
        extra['page'] = page
    seat_list = Seat.all().filter('representation =', representation)
    return object_list(request, seat_list, paginate_by=50, template_object_name='seat', extra_context=extra)


@login_required
def unpublish_representation(request, key):
    representation = get_own_object_or_404(request.user,Representation, key)
    event = get_own_object_or_404(request.user, Event, representation.event.key())
    if Seat.all().filter('representation =', representation).filter('availability !=', 0).count() :
        Message(user=request.user, message=ugettext("You cannot unpublish an event for which some tickets were already sold.")).put()
        return HttpResponseRedirect(reverse('banian.views.show_event',kwargs={'key':representation.event.key(),}))
    if representation.status != 'Published' and representation.status !='On Sale' and representation.pre_approval_status != 'Processing':
        Message(user=request.user, message=ugettext("You cannot unpublish an event that was not published first")).put()
        return HttpResponseRedirect(reverse('banian.views.show_event',kwargs={'key':representation.event.key(),}))        
    if request.method == 'POST':
        job_id = str(uuid4())
        representation.job_id = job_id
        representation.status = 'Canceling'
        cancelStatus = banian.paypal.processCancelPreApproval(representation.pre_approval_key)
        if cancelStatus == 'paypal_unexpected':
            logging.critical(repr(representation))
        representation.pre_approval_status = None
        representation.pre_approval_key = None
        representation.paypal_id = None
        representation.put()
        total_seats = 0
        for ticket_class in representation.event.ticketclass_set:
            total_seats = total_seats + ticket_class.nbr_seats()
        taskqueue.add(url='/tasks/delete_seats/', params={'representation':representation.key(),'job_id':job_id}, countdown=0)
        memcache.set(job_id + '-count', 0) #@UndefinedVariable
        memcache.set(job_id + '-message', 'Not Started') #@UndefinedVariable
        memcache.set(job_id + '-total', total_seats) #@UndefinedVariable
        return HttpResponseRedirect(reverse('banian.views.show_event', kwargs={'key':event.key(), }))
    else:
        return render_to_response(request, 'banian/unpublish_confirm.html', { 'representation':representation})

@login_required
def search_events(request):
    
    distance = int(request.GET.get('distance',request.user.preferred_distance))
    units = int(request.GET.get('units',request.user.distance_units))

    ## update account last search preference
    dirty = False
    if request.user.distance_units != units:
        request.user.distance_units = units
        dirty = True
    if request.user.preferred_distance != distance:
        request.user.preferred_distance = distance
        dirty = True
    if dirty:
        request.user.put()

    form = SelectDistanceForm(initial={'distance_km':request.user.preferred_distance,'distance_mi':request.user.preferred_distance,},distance_units=request.user.distance_units)


    if request.user.location:
        user_loc = ((request.user.location.lon, 0, 0), (request.user.location.lat, 0, 0))
        # add a little more to the distance due to the imprecision of the technique and then remove the results that exeeeds manually
        west, south, east, north = location_window(request.user.location.lat, request.user.location.lon, distance+2, 'km')
        event_list = Event.bounding_box_fetch(Event.all().filter('firstdate >', datetime.utcnow().replace(tzinfo=gaepytz.utc)).filter('visibility =', 'Published').filter('private =',False).order('firstdate'),
                                          Box(north, east, south, west), max_results=fetch_limit,)
        for index, item in enumerate(event_list):
            venue_loc = ((item.venue.location.lon, 0, 0), (item.venue.location.lat, 0, 0))
            event_list[index].distance = points2distance(user_loc, venue_loc)
            if units == 1:
                event_list[index].distance = event_list[index].distance / 1.609344
            if event_list[index].distance > float(request.user.preferred_distance):
                del(event_list[index])
    else:
        event_list = []
        user_loc = None
    response = object_list(request, event_list,
                           paginate_by=24, template_name='banian/search_event.html',
                           template_object_name='event',
                           extra_context={'location':request.user.short_addressname,
                                          'units':units,'form':form,'user_loc':user_loc,})
    if 'results_only' in request.GET:
        parser = ElementExtracter(tag="table",attributes={"id":"id_search_results"})
        parser.parse(response.content)
        response.content = parser.get_content() 
        return response

    return response 

@login_required
def add_representation(request):
    event = get_own_object_or_404(request.user, Event, request.GET['event'])
    min_date = event.onsale_date + timedelta(days=+1)
    timezone = ''
    for item in construct_timezone_choice(event.venue.country):
        if item[0] == event.venue.timezone:
            if len(item) == 2:
                timezone = item[1]
            else:
                timezone = item[2]

    return create_object(request,
                     form_class=RepresentationForm,
                     post_save_redirect=reverse('banian.views.show_representation', kwargs=dict(key='%(key)s')),
                     extra_context={'event':event,'timezone':timezone},
                     form_kwargs={'owner':request.user, 'event':event,'min_date':min_date,})

@login_required
def edit_representation(request, key):
    representation = get_object_or_404(Representation, key)
    event = get_own_object_or_404(request.user, Event, representation.event.key())
    min_date = event.onsale_date + timedelta(days=+1)
    timezone = ''
    for item in construct_timezone_choice(event.venue.country):
        if item[0] == event.venue.timezone:
            if len(item) == 2:
                timezone = item[1]
            else:
                timezone = item[2]
    if representation.status == 'Published':
        return HttpResponseForbidden("Representation cannot be modified after event was published")
    return update_object(request,
                         object_id=key,
                         form_class=RepresentationForm, extra_context={ 'event':event,'timezone':timezone},
                         post_save_redirect=reverse('banian.views.show_representation', kwargs=dict(key='%(key)s')),
                         form_kwargs={'min_date':min_date})

@login_required
def show_representation(request, key):
    representation = get_object_or_404(Representation, key)
    event = get_own_object_or_404(request.user, Event, representation.event.key())
    job_id = representation.job_id
    progress = 0
    message = 'Not Started'        
    if job_id:
        job_info = memcache.get_multi([job_id + "-count",job_id + "-message",job_id + "-total"]) #@UndefinedVariable
        if job_id + "-message" in job_info:
            message = job_info[job_id + "-message"]
        if job_id + "-total" in job_info and job_id + "-count" in job_info:
            progress = (float(job_info[job_id + "-count"]) / float(job_info[job_id + "-total"])) * 100.0
    context = {'event':event,'progress':progress, 'message':message,}
    return object_detail(request, Representation.all().filter('owner =', request.user), key,
                         extra_context=context)   

@login_required
def delete_representation(request, key):
    representation = get_object_or_404(Representation, key)
    event = get_own_object_or_404(request.user, Event, representation.event.key())
    if representation.status == 'Published':
        return HttpResponseForbidden("Representations cannot be modified after event was published")
    return delete_object(request, representation, extra_context=None , object_id=key,
        post_delete_redirect=reverse('banian.views.show_event', kwargs={'key':event.key(), }))

@login_required
def cancel_representation(request,key):
    representation = get_object_or_404(Representation, key)
    event = get_own_object_or_404(request.user, Event, representation.event.key())
    if request.method == 'POST':
        representation.status = 'Cancelled'
        representation.put()
        Message(user=request.user, message=ugettext("Event has been cancelled")).put()
        return HttpResponseRedirect(reverse('banian.views.show_event',kwargs={'key':str(event.key()),}))
    return render_to_response(request, 'banian/representation_cancel_confirm.html', { 'representation':representation})

@login_required
def buy_representation(request, key):
    representation = get_object_or_404(Representation, key)
    event = get_object_or_404(Event, representation.event.key())
    ticketclass_list = event.ticketclass_set.fetch(fetch_limit)
    for index, item in enumerate(ticketclass_list):
        ticketclass_list[index].total_available_text, \
        ticketclass_list[index].total_available, \
        ticketclass_list[index].max_tickets = calc_ticket_class_available(request.user,item,representation)

    max_tickets = max_ticket_limit
    already_purchase_tickets = 0
    if event.limit_tickets:
        max_tickets = event.max_tickets
    user_event = UserEvent.all().filter('representation =',representation).get()
    if user_event:
        if event.limit_tickets:
            if user_event.nbr_tickets < max_tickets:
                max_tickets = max_tickets - user_event.nbr_tickets
            else:
                max_tickets = 0
        already_purchase_tickets = user_event.nbr_tickets

    if request.method == 'POST':
        #TODO: Add an optional Captcha for each purchase to prevent robots from buying tickets
        form = SelectTicketForm(data=request.POST, files=request.FILES, representation=representation,
                                ticketclass_list=ticketclass_list,already_purchase_tickets=already_purchase_tickets,
                                max_tickets=max_tickets)
        if form.is_valid():
            data = form.extract()
            reservation = str(uuid4())
            total = 0; total_amount = 0.0 ; index = 0
            for key, item in data.iteritems():                
                total_amount = total_amount + ticketclass_list[index].price * item
                total = total + item
                index = index + 1

            ## Phase 1, Create the transaction
            if event.limit_duration:
                door_date = representation.date - timedelta(minutes=representation.event.door_open)
            else:
                door_date = representation.date
            event_thumbnail_image = event.thumbnail_image or None
            event_poster_image = event.poster_image or None
            transaction = Transaction(owner=request.user,type='Purchase',
                                      event=event,representation=representation,t_id=reservation,venue_name=event.venue.name,
                                      venue_address=event.venue.address,event_name=event.name,
                                      venue_timezone=event.venue.timezone,
                                      representation_date=representation.date,event_performer = event.performer,
                                      event_note=event.note,event_web_site=event.web_site,
                                      venue_web_site=event.venue.web_site,representation_door_date=door_date,
                                      event_thumbnail_image = event_thumbnail_image,status="Processing Payment",
                                      total_amount=total_amount,event_poster_image = event_poster_image, nbr_tickets=total,
                                      reservation=reservation)
            transaction.put()

            ## Phase 2, request payment key if the payment is required
            paykey = None
            if total_amount and representation.owner != request.user:
                status,paykey = preparePayment(request, representation, data, transaction)
                if status != 'Created':
                    taskqueue.add(url='/tasks/reverse_transaction/', params={'transaction':transaction.key()}, countdown=300)
                    Message(user=request.user, message=ugettext("An error occured while preparing your payment")).put()
                    return HttpResponseRedirect(reverse('banian.views.purchase_failure') + '?errorcode=' + str(status))
                else:
                    transaction.payment_key = paykey
                    transaction.payment_status = 'Processing'
                    transaction.put()
            else:
                transaction.payment_status = 'Completed'
                transaction.payment_key = None
                transaction.put()
            
            ## Phase 3 reserve seat
            try:
                db.run_in_transaction(reserve_seats, representation, reservation, data)
                taskqueue.add(url='/tasks/clean_reservation/', params={'reservation':reservation, 'representation':representation.key()}, countdown=300)
                taskqueue.add(url='/tasks/reverse_transaction/', params={'transaction':transaction.key()}, countdown=300)
                if not memcache.get(str(representation.key()) + '-ticket_timestamp'): #@UndefinedVariable
                    taskqueue.add(url='/tasks/update_available_tickets/',params={'representation':representation.key(),}, countdown=30)
                memcache.set(str(representation.key()) + '-ticket_timestamp',datetime.utcnow().replace(tzinfo=gaepytz.utc)) #@UndefinedVariable
            except:
                taskqueue.add(url='/tasks/reverse_transaction/', params={'transaction':transaction.key()}, countdown=0)
                logging.critical(repr(sys.exc_info()))
                Message(user=request.user, message=ugettext("Seat could not be reserved try again in few minutes...")).put()
                return HttpResponseRedirect(reverse('banian.views.buy_representation',kwargs={'key':representation.key(),}))
            
            ## Phase 4, if payment required, transfer the user to paypal to execute the payment
            if transaction.payment_status == 'Processing':
                return transfer_to_paypal(request,"https://www.sandbox.paypal.com/webscr?cmd=_ap-payment&paykey=%s" % paykey )
            
            ## Phase 5, if no payment is required, take the seats
            elif transaction.payment_status == 'Completed':
                status = generate_tickets(request,transaction)
                if status != 'success':
                    return HttpResponseRedirect(reverse('banian.views.purchase_failure') + '?errorcode=' + status)
                else:
                    return HttpResponseRedirect(reverse('banian.views.show_transaction', kwargs={'key':str(transaction.key()),})+ "?new=True")
            else:
                logging.critical('Unexpected Payment Status Code')
                return HttpResponseRedirect(reverse('banian.views.purchase_failure') + '?errorcode=' + 'unexpected_payment_error')
    else:
        form = SelectTicketForm(representation=representation, ticketclass_list=ticketclass_list,
                                already_purchase_tickets=already_purchase_tickets, max_tickets=max_tickets)
    template_name = "select_tickets.html"
    t = loader.get_template(template_name)
    c = RequestContext(request, {'form':form, 'event':event,'object':event, 'representation':representation,'max_tickets':max_tickets,'already_purchase_tickets':already_purchase_tickets })
    response = HttpResponse(t.render(c))
    return response    

def show_representation_job_progess(request, key):
    if 'ajax' in request.GET:
        job_id = key
        progress = 0; available = 0; value = 0.0; message = 'Not Started'
        job_info = memcache.get_multi([job_id + "-count",job_id + "-message",job_id + "-total"]) #@UndefinedVariable
        if job_id + "-message" in job_info:
            message = job_info[job_id + "-message"]
        if job_id + "-total" in job_info and job_id + "-count" in job_info:
            progress = (float(job_info[job_id + "-count"]) / float(job_info[job_id + "-total"])) * 100.0
            if progress == 100:
                representation = get_object_or_404(Representation, request.GET.get('representation',None))
                if representation:
                    available = representation.available_tickets
                    value = representation.value
        data = dumps({"progress": progress, "message":message,'available':available,'value':value,})
        return HttpResponse(data, mimetype="application/javascript")
    else:
        return HttpResponseServerError('Not implemented')

def purchase_failure(request):
    return HttpResponseServerError('Not implemented')

def purchase_success(request):
    transaction = db.get(request.GET['transaction'])
    tickets = Ticket.all().filter('owner =',request.user).filter('transaction =',transaction)
    return object_list(request, tickets, paginate_by=10, template_object_name='ticket', extra_context=None)


def timezonelist(request):
    cctld = request.GET['cctld']
    return HttpResponse(dumps({'choices':construct_timezone_choice(cctld)}), mimetype="application/javascript")

@login_required
def transactions(request):
    extra = {}
    transactions = Transaction.all().filter('owner =', request.user).order('-date')
    return object_list(request, transactions, paginate_by=10, template_object_name='transaction', extra_context=extra)

@login_required
def show_transaction(request, key):
    extra = {}
    transaction = get_own_object_or_404(request.user, Transaction, key)
    if transaction.payment_status == 'Processing':
        status = banian.paypal.getPaymentDetail(transaction.payment_key)
        logging.debug(repr(status))
        if status == 'Completed':
            transaction.payment_status = 'Completed'
            transaction.put()
            generate_tickets(request, transaction)
        elif 'Processing':
            extra['paypal_transfer_url'] = reverse('banian.views.transfering',kwargs={'url':urllib.quote("https://www.sandbox.paypal.com/webscr?cmd=_ap-payment&paykey=%s" % transaction.payment_key)})
            
    ticket_set = db.get(transaction.ticket_keys)
    extra['ticket_set'] = ticket_set
    if 'new' in request.GET:
        extra['new'] = True
    if 'ajax' in request.GET:
        if len(ticket_set) == transaction.nbr_tickets:
            response = object_detail(request, Transaction.all(), key, extra_context=extra)
            HTMLparser = ElementExtracter(tag="table",attributes={"id":"id_ticket_list"})
            HTMLparser.parse(response.content)
            data = dumps({"status": 1, "html":HTMLparser.get_content(),})
        else:
            data = dumps({"status": 0, "html":'',})
        return HttpResponse(data, mimetype="application/javascript")
    else: 
        return object_detail(request, Transaction.all(), key, extra_context=extra)    

@login_required
def user_events(request):
    extra = {}
    events = UserEvent.all().filter('owner =',request.user).order('-representation_date')
    return object_list(request, events, paginate_by=10, template_object_name='event', extra_context=extra)

@login_required
def show_user_event(request, key):
    extra = {}
    user_event = get_own_object_or_404(request.user, UserEvent, key)
    ticket_set = db.get(user_event.ticket_keys)
    extra['ticket_set'] = ticket_set
    return object_detail(request, UserEvent.all(), key, extra_context=extra)    
@login_required
def download_tickets(request):
    extra = {}
    ticket_set = None
    if 'transaction_key' in request.GET:
        transaction = get_own_object_or_404(request.user, Transaction, request.GET['transaction_key'])
        extra['transaction_key'] = request.GET['transaction_key']
        ticket_set = Ticket.gql("WHERE __key__ IN :1 AND status = 'Valid'",transaction.ticket_keys)
        extra['ticket_set'] = ticket_set
    if 'user_event_key' in request.GET:
        user_event = get_own_object_or_404(request.user, UserEvent, request.GET['user_event_key'])
        extra['user_event_key'] =  request.GET['user_event_key']
        ticket_set = Ticket.gql("WHERE __key__ IN :1 AND status = 'Valid'",user_event.ticket_keys)
        extra['ticket_set'] = ticket_set
    if ticket_set == None:
        return HttpResponseNotFound()
    return render_to_response(request, 'banian/ticket_multi_download.html', extra)

@login_required
def download_ticket(request,key):
    extra = {}
    ticket = get_own_object_or_404(request.user, Ticket, key)
    user_event_key = request.GET.get('user_event',None)
    transaction_key = request.GET.get('transaction',None)
    seat_key = request.GET.get('seat',None)
    extra['user_event_key'] = user_event_key
    extra['transaction_key'] = transaction_key
    extra['seat_key'] = seat_key
    if ticket.status != 'Valid':
        return HttpResponseForbidden('Ticket is not valid')
    return object_detail(request, Ticket.all(), key, extra_context=extra,template_name='banian/ticket_download.html')

@login_required
def add_event(request):
    form_list = [QEWhatForm,QEWhereForm,QEWhenForm,QEHowManyForm,QEOptionsForm,QEImagesNoteForm,QEPreviewForm]
    step = 0
    kwargs = {'redirect':'','view':'banian.views.add_event','step':step,'instance':None,'owner':request.user}
    if request.method == 'POST':
        kwargs['files'] = request.FILES
        kwargs['data'] = request.POST
        wiz = QuickEventWizard(form_list=form_list,**kwargs)        
        if wiz.is_valid():
            event = wiz.save()
            if 'next' in request.POST:
                step = step + 1
            return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':str(event.key()),})+'?step=%d' % step)
        else:
            return wiz.render(request)
    wiz = QuickEventWizard(form_list=form_list,**kwargs)
    return wiz.render(request)

@login_required
def edit_event(request,key):
    form_list = event_edit_form_list
    event = get_own_object_or_404(request.user, Event, key)
    if not event.mutable():
        return HttpResponseForbidden()
    if 'step'in request.GET:
        step = int(request.GET['step'])
        if step < 0 or step > len(form_list)-1:
            return HttpResponseNotFound()    
    else:
        if event.max_step == len(form_list)-2:
            step = 0
        else:
            step = event.max_step+1
    kwargs = {'redirect':'','view':'banian.views.edit_event','step':step,'instance':event,'owner':request.user}
    if request.method == 'POST':
        kwargs['files'] = request.FILES
        kwargs['data'] = request.POST
        wiz = QuickEventWizard(form_list=form_list,**kwargs)        
        if wiz.is_valid():
            event = wiz.save()
            if 'next' in request.POST:
                step = step + 1
            return HttpResponseRedirect(reverse('banian.views.edit_event',kwargs={'key':event.key()})+'?step=%d' % step)
        else:
            return wiz.render(request)
    wiz = QuickEventWizard(form_list=form_list,**kwargs)
    return wiz.render(request)

def redirect_url(request):
    redirect = request.GET['redirect']
    logging.debug(repr(redirect))
    url = urllib.unquote(redirect)
    return HttpResponseRedirect(url)

def transfering(request,url):
    url = urllib.quote(url)
    return render_to_response(request, "banian/transfering.html", {'redirect':url,})

@login_required
def preview_sale_page(request,key):
    event = get_object_or_404(Event, key)
    rep_list = Representation.gql("WHERE event = :1 ORDER BY date", event).fetch(fetch_limit)
    for r in rep_list:
        r.available_tickets_preview_text = '%d ticket left' % event.seat_configuration.nbr_seat
        r.status = 'On Sale'
    extra = {'representation_set':rep_list,'preview':True,
             'preview_redirect':reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6'}
    return object_detail(request, Event.all(), key, extra_context=extra, template_name='banian/event_view.html')    

class Obj(object):
    test = ''

@login_required
def preview_ticket(request,key):
    event = get_own_object_or_404(request.user,Event, key)
    representation = Representation.all().filter('event =',event).get()
    tc = TicketClass.all().filter('event =',event).get()
    door_date = representation.date - timedelta(minutes=event.door_open)
    t_id = str(uuid4())
    seat_group = None
    location = []
    if len(tc.seat_groups):
        key = tc.seat_groups[0]
        seat_group = db.get(key)
    while(seat_group):
        if seat_group.name:
            location.insert(0, seat_group.name)
        seat_group = seat_group.seat_group
    object = Obj()
    object.event_name = event.name
    object.date = representation.date
    object.venue_name = event.venue.name
    object.door_date = door_date
    object.onsale_date = event.onsale_date
    object.endsale_date = event.endsale_date
    object.restrict_sale_period = event.restrict_sale_period
    object.address = event.venue.address
    object.note = event.note
    object.location = location
    object.general_admission = tc.general_admission
    object.number = 1
    object.t_id = t_id
    object.price = tc.price
    object.event_image = event.thumbnail_image
    object.ticket_class_name = tc.name

    return render_to_response(request, 'banian/ticket_download.html',
                              {'object':object,'preview':True,
                               'preview_redirect':reverse('banian.views.edit_event',kwargs={'key':event.key(),})+'?step=6'})

@login_required
def validation_list(request):
    now_minus_48 = datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(hours=48)
    
    event_list = Event.gql("WHERE firstdate < :1 AND validators =:2",now_minus_48,request.user)
    return object_list(request, event_list,template_name='banian/validation_list.html',template_object_name='event', extra_context={'read_only':True,})


def validateTicket(ticket_key,seat,validator):
    ticket = Ticket.get(ticket_key)
    #TODO: find the hell why in the transaction the ticket retreive from the DB doesn't contains the Seat Reference but do contain all others...
    if ticket.used == False and ticket.status == 'Valid':
        ticket.seat = seat
        ticket.used = True
        ticket.put()
        return ticket
    if ticket.used:
        raise ValidationError('Ticket already used')
    else:
        raise ValidationError('Ticket is invalid, current status is: ' % ticket.status)


@login_required
def validate(request,key):
    representation = get_object_or_404(Representation, key)
    now_plus_48 = datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(hours=48)
    if request.user.key() not in representation.event.validators:
        return HttpResponseNotFound()
    if representation.date > now_plus_48:
        return HttpResponseForbidden()    
    if request.is_ajax():
        data = None
        if 'seat_number' in request.GET:
            try:
                seat_number = int(request.GET['seat_number'])
            except:
                seat_number = 0
            seat = Seat.all().filter('representation =',representation).filter('number =',seat_number).get()
            if not seat:
                data = dumps({"t_id": '','error':True, "message_html":'Invalid Seat Number',})
            else:
                ticket = seat.current_ticket()
                if not ticket:
                    data = dumps({"t_id":'','error':True, "message_html":'No ticket sold for this seat',})
                elif ticket.used:
                    data = dumps({"t_id":ticket.t_id,'error':True, "message_html":'Ticket as already been used',})
                else:
                    data = dumps({"t_id": ticket.t_id,'error':False, "message_html":'Lookup Sucessful, Validate paper ticket',})
        elif 'ticket_id' in request.GET:
            ticket_id = request.GET['ticket_id']
            ticket = Ticket.all().filter('representation =',representation).filter('t_id =',ticket_id).get()
            if not ticket:
                data = dumps({'error':True,"message_html":'Invalid Ticket ID','scan_html':"",})
            else:
                try:
                    ticket = db.run_in_transaction(validateTicket, ticket_key=ticket.key(),seat=ticket.seat,validator=request.user)
                    scan = TicketScan(t_id=ticket.t_id,seat=ticket.seat,representation=representation,date=datetime.utcnow().replace(tzinfo=gaepytz.utc),validator=request.user,result='Successful')

                    data = dumps({'error':False,"message_html":'Successfully validated ticket',
                                  'scan_html':'<tr><td class="row">%s</td><td class="row">%s</td><td class="row">Successful</td><td class="row">%s</td>' % (scan.t_id, scan.date,scan.validator)})
                except ValidationError, e:                    
                    scan = TicketScan(t_id=ticket.t_id,seat=ticket.seat,representation=representation,date=datetime.utcnow().replace(tzinfo=gaepytz.utc),validator=request.user,result='Failure')
                    data = dumps({'error':True,"message_html":str(e.messages[0]),
                                  'scan_html':'<tr><td class="row">%s</td><td class="row">%s</td><td class="row">Failure</td><td class="row">%s</td>' % (scan.t_id, scan.date,scan.validator)})
                scan.put()
                
        elif 'cticket_id' in request.GET:
            ticket_id = request.GET['cticket_id']
            ticket = Ticket.all().filter('t_id =',ticket_id).get()
            if not ticket:
                data = dumps({'error':True,"message_html":'Invalid Ticket ID','scan_html':""})
            else:
                request.user.karma = request.user.karma - 1
                scan = TicketScan(t_id=ticket.t_id,seat=ticket.seat,representation=representation,date=datetime.utcnow().replace(tzinfo=gaepytz.utc),validator=request.user,result='Counterfeit')
                data = dumps({'error':False,"message_html":'Ticket reported as counterfeit',
                              'scan_html':'<tr><td class="row">%s</td><td class="row">%s</td><td class="row">Counterfeit</td><td class="row">%s</td>' % (scan.t_id, scan.date,scan.validator)})
                scan.put()
        if data:
            return HttpResponse(data, mimetype="application/javascript")
        else:
            return HttpResponseNotFound()        
    else:
        form = ValidationForm()
        scan_list = TicketScan.all().filter('representation =',representation).filter('validator =',request.user).order('-date').fetch(20)
        return render_to_response(request, 'banian/validate_ticket.html',{'object':representation,'form':form,'recent_scan':scan_list})

@login_required
def validator_list(request,key):
    event = get_own_object_or_404(request.user,Event, key)
    if request.is_ajax():
        if 'add' in request.GET and 'username' in request.GET:
            username = request.GET['username']
            user = User.all().filter('username =',username).get() #@UndefinedVariable
            if not user:
                data = dumps({'name':'','username':'','error':True, "message_html":'Invalid unsername',})
            else:
                try:
                    event.validators.index(user.key())
                    data = dumps({'key':user.key(),'name':user.name,'username':user.username,'error':True, "message_html":'User %s already in the list' % user.username,})
                except:                    
                    event.validators.append(user.key())
                    event.put()
                    data = dumps({'key':str(user.key()),'name':user.name,'username':user.username,'error':False, "message_html":'Successfully added %s' % user.username,})
            return HttpResponse(data, mimetype="application/javascript")
        if 'del' in request.GET and 'key' in request.GET:
            try:
                key = request.GET['key']
                user = User.get(key)    #@UndefinedVariable
            except:
                return HttpResponseServerError()            
            if user == request.user:
                data = dumps({'name':'','username':'','error':True, "message_html":'You cannot delete yourself',})
            else:
                if user.key() not in event.validators:
                    data = dumps({'key':str(user.key()),'name':'','username':'','error':False, "message_html":'Nothing to do, user not in the list',})
                else:
                    event.validators.remove(user.key())
                    event.put()
                    data = dumps({'key':str(user.key()),'name':user.name,'username':user.username,'error':False, "message_html":'Successfully removed %s' % user.username,})
            return HttpResponse(data, mimetype="application/javascript")
        return HttpResponseServerError()       
    else:
        dirty = False
        doorman_list = []
        for key in event.validators:
            user = User.get(key) #@UndefinedVariable
            if not user:
                event.validators.remove(key)
                dirty = True
            else:
                doorman_list.append(user)
        if dirty:
            event.put()            
        return render_to_response(request, 'banian/validator_list.html',{'object':event,'doorman_list':doorman_list})
