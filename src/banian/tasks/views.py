'''
Created on Nov 21, 2009

@author: sboire
'''
from uuid import uuid4
from google.appengine.api import urlfetch, memcache
from google.appengine.api.labs.taskqueue import taskqueue, Queue, Task
from google.appengine.ext import db
from django.http import HttpResponseServerError, HttpResponse
from banian.utils import unreserve_seats
from banian.models import Transaction, Seat, UserEvent, Event, Representation, Image, \
    batch_delete_limit, fetch_limit, Ticket, put_limit, delete_limit, \
    TicketClass, SeatGroup, batch_put_limit, RepresentationPayment
from registration.models import User
import banian.paypal
from banian.views import unpublish_representation
from banian import models
from google.appengine.api.urlfetch_errors import DownloadError
from google.appengine.api.labs.taskqueue.taskqueue import UnknownQueueError
import time

import logging #@UnusedImport
import gaepytz
from datetime import datetime, timedelta



def generate_tickets(request):
    reservation = request.POST['reservation']
    key = request.POST['transaction']
    transaction = Transaction.get(key)
    owner = User.get(request.POST['owner']) #@UndefinedVariable
    tickets = []
    seats = Seat.all().filter('reservation =', reservation).fetch(fetch_limit)
    total_amount = 0.0
    nbr_tickets = len(seats)
    for seat in seats:
        t_id = str(uuid4())
        seat_group = seat.seat_group; location = []        
        while(seat_group):
            location.insert(0, seat_group.name)
            seat_group = seat_group.seat_group
        if not models.offline_mode:
            url = "http://chart.apis.google.com/chart?cht=qr&chl=%s&chs=200x200" % t_id
            try:
                response = urlfetch.fetch(url)
            except DownloadError:
                HttpResponseServerError("Cannot generate bar Code")
            if response.status_code == 200:
                image = Image()
                image.filename = t_id + '.png'
                image.content_type = 'png'
                image.caption = t_id
                image.content = response.content
                image.put()
            else:
                HttpResponseServerError("Cannot generate bar Code")
        else:
            image = None
        total_amount = total_amount + seat.ticket_class.price
        door_date = seat.representation.date - timedelta(minutes=seat.representation.event.door_open)
        #TODO: Handle transaction timestamp timzone (javascript to get timezone?)
        event_thumbnail_image = None
        if seat.representation.event.thumbnail_image:
                event_thumbnail_image = seat.representation.event.thumbnail_image
        tickets.append(Ticket(t_id=t_id,
                              barcode=image,
                              owner=owner,
                              seat=seat,
                              representation=seat.representation,
                              transaction=transaction,
                              date=seat.representation.date,
                              door_date=door_date,
                              timezone=seat.representation.venue.timezone,
                              address=seat.representation.venue.address,
                              venue_name=seat.representation.venue.name,
                              performer=seat.representation.event.performer,
                              event_name=seat.representation.event.name,
                              note=seat.representation.event.note,
                              web_site_event=seat.representation.event.web_site,
                              web_site_venue=seat.representation.venue.web_site,
                              number=seat.number,
                              price=seat.ticket_class.price,
                              general_admission=seat.ticket_class.general_admission,
                              location=location,
                              ticket_class_name=seat.ticket_class.name,
                              event_image=event_thumbnail_image,
                              status='Valid'))
    slice = 0
    batch = put_limit / 10
    ticket_keys = []
    while (len(tickets[slice:slice + batch])):
        ticket_keys.extend(db.put(tickets[slice:slice + batch]))
        memcache.incr(reservation + '-count', len(tickets[slice:slice + batch]), initial_value=0) #@UndefinedVariable
        slice = slice + batch
        transaction.ticket_keys = ticket_keys
    #TODO: transaction update and user_event update in a transaction to prevent clashes
    transaction.total_amount = total_amount
    transaction.nbr_tickets = nbr_tickets
    transaction.status = 'Completed'
    transaction.put()
    user_event = UserEvent.all().filter('owner =', owner).filter('representation =', transaction.representation).get()
    if not user_event:
        user_event = UserEvent(event=transaction.event, representation=transaction.representation,
                               name=transaction.event_name,
                  representation_date=transaction.representation_date, owner=owner,
                  venue_name=transaction.venue_name, venue_address=transaction.venue_address,
                  venue_timezone=transaction.venue_timezone, thumbnail_image=transaction.event_thumbnail_image,
                  performer=transaction.event_performer, note=transaction.event_note,
                  web_site=transaction.event_web_site, venue_web_site=transaction.venue_web_site,
                  representation_door_date=transaction.representation_door_date, ticket_keys=transaction.ticket_keys,
                  total_amount=transaction.total_amount, nbr_tickets=transaction.nbr_tickets,
                  poster_image=transaction.event_poster_image)
        user_event.put()
    else:
        user_event.nbr_tickets = user_event.nbr_tickets + transaction.nbr_tickets
        user_event.total_amount = user_event.total_amount + transaction.total_amount
        user_event.ticket_keys.extend(transaction.ticket_keys)
        user_event.put()
    return HttpResponse("Completed")

def put_on_sale(request):
    logging.info('Task put_on_sale - Start')
    event = Event.get(request.POST['event'])
    logging.info(repr(event))
    if event.status == 'Published' or event.status == 'On Sale':
        onsale_date = datetime.utcfromtimestamp(float(request.POST['timestamp']),).replace(tzinfo=gaepytz.utc)
        if not event or onsale_date != event.onsale_date:
            logging.info('Task put_on_sale - Nothing to do')
            return HttpResponse("Nothing to do")
        representations = Representation.all().filter('event =', event).filter('status =', 'Published').fetch(fetch_limit)
        for index, item in enumerate(representations): #@UnusedVariable
            representations[index].status = "On Sale"
        slice = 0
        while (len(representations[slice:slice + put_limit])):
            db.put(representations[slice:slice + put_limit])
            slice = slice + put_limit
        #TODO: put that back once geomodel supports GQL
        #event.status = 'On Sale'
        #event.put()
    logging.info('Task put_on_sale - Completed')    
    return HttpResponse("Completed")

def refund_tickets(request):
    logging.info('Task refund_tickets - Start')
    representation = Representation.get(request.POST['representation'])
    if not representation:
        logging.critical('Invalid representation key %s' % request.POST['representation'])
        logging.info('Task refund_tickets - Invalid representation')
        return HttpResponse("Invalid representation")
    logging.info(repr(representation))
   
    memo = '%s was cancelled. Your tickets purchase is refunded' % representation.event.name
    done = False
    query = Transaction.all().filter('representation =',representation).filter('status !=','Refunded')
    if query.count(put_limit) < put_limit:
        done = True
    transactions = query.fetch(put_limit)
    for transaction in transactions:
        status = banian.paypal.processRefund(memo,transaction.paypal_id,transaction.total_amount,transaction.apkey)
        if status == 'Completed':
            refund_transaction = Transaction(owner=transaction.owner,type='Refund',
                                      event=transaction.event,representation=transaction.representation,t_id=str(uuid4()),venue_name=transaction.venue_name,
                                      venue_address=transaction.venue_address,event_name=transaction.event_name,
                                      venue_timezone=transaction.venue_timezone,
                                      representation_date=transaction.representation_date,event_performer = transaction.event_performer,
                                      event_note=transaction.event_note,event_web_site=transaction.event_web_site,
                                      venue_web_site=transaction.venue_web_site,representation_door_date=transaction.representation_door_date,
                                      event_thumbnail_image = transaction.event_thumbnail_image,status="Completed",
                                      total_amount=(-1 * transaction.total_amount),event_poster_image = transaction.event_poster_image, nbr_tickets=transaction.nbr_tickets,
                                      parent=transaction)
            refund_transaction.put()
            for ticket in transaction.ticket_set:
                ticket.status = 'Refunded'
                ticket.put()
    if not done:     
        taskqueue.add(url='/tasks/refund_tickets/', params={'representation':representation.key(),}, countdown=2)
    else:
        tickets = Ticket.all().filter('representation =',representation).filter('status !=', 'Refunded').fetch(batch_put_limit)
        if tickets:
            logging.critical('Un "refunded" tickets lingering, correcting the problem...')
            for ticket in tickets:
                ticket.status = 'Refunded'
                ticket.put()
            taskqueue.add(url='/tasks/refund_tickets/', params={'representation':representation.key(),}, countdown=2) 
    logging.info('Task refund_tickets - Completed')
    return HttpResponse("Completed")

def delete_seats(request):
    logging.info('Task delete_seats - Start')
    representation = Representation.get(request.POST['representation'])
    job_id = request.POST['job_id']
    if not representation:
        logging.critical('Invalid representation key %s' % request.POST['representation'])
        logging.info('Task delete_seats - Invalid representation')
        return HttpResponse("Invalid representation")
    logging.info(repr(representation))
    if job_id != representation.job_id or representation.status != 'Canceling':
        logging.info('Task delete_seats - Finished')
        return HttpResponse("Finished")
    else:
        if memcache.get(job_id + '-message') != 'Canceling': #@UndefinedVariable
            memcache.set(job_id + '-message', 'Canceling') #@UndefinedVariable
    countdown = batch_delete_limit
    done = False   
    try:
        while countdown > 0 and not done:
            seats = Seat.all(keys_only=True).filter('representation =', representation).fetch(delete_limit)
            lenght = len(seats) 
            if lenght:
                countdown = countdown - lenght
                memcache.incr(job_id + '-count', lenght, initial_value=0) #@UndefinedVariable
                db.delete(seats)
            else:
                done = True
    except:
        logging.info('Task delete_seats - Store error')
        return HttpResponseServerError()

    if not done:     
        taskqueue.add(url='/tasks/delete_seats/', params={'representation':representation.key(), 'job_id':job_id}, countdown=2)
    else:
        memcache.set(job_id + '-count', memcache.get(job_id + '-total')) #@UndefinedVariable
        memcache.set(job_id + '-message', 'Finished') #@UndefinedVariable
        representation.status = 'Draft'
        representation.available_tickets = 0
        representation.nbr_tickets = 0
        representation.value = 0.0
        representation.revenues = 0.0
        #TODO: handle properly cancelled representation revenues
        representation.timestamp = None
        representation.job_id = None
        representation.put()
    logging.info('Task delete_seats - Completed')
    return HttpResponse("Completed")


def generate_seats(request):
    logging.info('Task generate_seats - Start')
    representation = Representation.get(request.POST['representation'])
    ticket_class = TicketClass.get(request.POST['ticket_class'])
    seat_group = SeatGroup.get(request.POST['seat_group'])
    job_id = request.POST['job_id']        
    if not representation or not ticket_class or not seat_group or not representation.job_id:
        logging.info('Task generate_seats - Invalid input')
        return HttpResponse("Invalid input")
    event = representation.event
    if job_id != representation.job_id or representation.status != 'Generating':
        logging.info('Task generate_seats - Nothing to do')
        return HttpResponse("Nothing to do")
    else:
        if memcache.get(job_id + '-message') != 'Generating': #@UndefinedVariable
            memcache.set(job_id + '-message', 'Generating') #@UndefinedVariable

    last_seat = Seat.all().filter('representation =', representation).filter('ticket_class =', ticket_class).filter('seat_group =', seat_group).order('-number').get()
    if last_seat:
        last_number = last_seat.number
    else:
        last_number = 0
    countdown = batch_put_limit
    done = False
    seat_list = []        
    while(countdown and not done):
        seat_left = seat_group.nbr_seat - last_number
        if seat_left > countdown:
            seat_left = countdown
        while(seat_left):
            last_number = last_number + 1
            seat_left = seat_left - 1
            countdown = countdown - 1
            seat = Seat(representation=representation,
                                number=last_number, ticket_class=ticket_class, status=1,
                                seat_group=seat_group, priority=seat_group.priority,
                                parent=representation)
            seat_list.append(seat)
        if last_number == seat_group.nbr_seat:
            current_index = ticket_class.seat_groups.index(seat_group.key())
            if current_index < len(ticket_class.seat_groups) - 1:
                seat_group = SeatGroup.get(ticket_class.seat_groups[current_index + 1])
                last_number = 0
            else:
                ticket_class = TicketClass.gql("WHERE event=:1 AND __key__ >:2 ORDER BY __key__", event, ticket_class.key()).get()
                if not ticket_class:
                    done = True
                else:
                    seat_group = SeatGroup.get(ticket_class.seat_groups[0])
                    last_number = 0
    slice = 0
    while (len(seat_list[slice:slice + put_limit])):
        db.put(seat_list[slice:slice + put_limit])
        memcache.incr(job_id + '-count', len(seat_list[slice:slice + put_limit]), initial_value=0) #@UndefinedVariable
        slice = slice + put_limit
    if done:
        paymentStatus = None
        if representation.publishing_cost() == 0:
            paymentStatus = 'Completed'
        else:
            memo = "Payment of %.2f for publishing %d tickets (at 0.01$/ticket) for %s" % (representation.publishing_cost(),representation.event.nbr_assigned_seats(),representation.event.name + ', ' + str(representation.date))
            #TODO: must protect the payment in a transaction so it cannot be processed twice, see close representation for example    
            paymentStatus = banian.paypal.processPayment(memo,
                                           representation.paypal_id,
                                           representation.publishing_cost(),
                                           representation.pre_approval_key)        
        if paymentStatus == 'Completed':
            if event.restrict_sale_period and event.onsale_date > datetime.utcnow().replace(tzinfo=gaepytz.utc):
                representation.status = 'Published'
            else:
                representation.status = 'On Sale'
            representation.published_date = datetime.utcnow().replace(tzinfo=gaepytz.utc)
            representation.value = 0.0
            for tc in representation.event.ticketclass_set:
                representation.value = representation.value + tc.value()
            representation.nbr_tickets = representation.event.nbr_assigned_seats()
            representation.timestamp_available = datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(seconds= -1)
            representation.timestamp_revenues = datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(seconds= -1)
            representation.calc_available_tickets(datetime.utcnow().replace(tzinfo=gaepytz.utc))
            representation.revenues = 0.0
            representation.job_id = None
            representation.put()
            memcache.set(job_id + '-count', memcache.get(job_id + '-total')) #@UndefinedVariable
            memcache.set(job_id + '-message', 'Finished') #@UndefinedVariable
            logging.info('Task generate_seats - Completed')
            return HttpResponse("Completed")
        elif paymentStatus == 'Canceled':
            #TODO: Do some lock out of accounts that actually do this
            #TODO: send a message to the user to this affect
            memcache.set(job_id + '-count',0) #@UndefinedVariable
            memcache.set(job_id + '-message', 'Cancelled') #@UndefinedVariable
            request.method = 'POST'
            unpublish_representation(request,str(representation.key()))
            logging.info('Task generate_seats - Canceled')
            return HttpResponse("Canceled")
        elif paymentStatus == 'paypal_unexpected':
            logging.info('Task generate_seats - Paypal Error')
            return HttpResponseServerError("Paypal Error")
        else:
            logging.critical('Unexpected Status code from processing publishing payment of representation: ' + paymentStatus)
            logging.info('Task generate_seats - Unexpected Status code')
            return HttpResponseServerError("Unexpected Status code")
    else:
        taskqueue.add(url='/tasks/generate_seats/', params={'representation':representation.key(), 'ticket_class':ticket_class.key(), 'seat_group':seat_group.key(), 'job_id':job_id}, countdown=2)
        logging.info('Task generate_seats - Completed')
        return HttpResponse("Completed")

def clean_reservation(request):
    logging.info('Task clean_reservation - Start')
    representation = Representation.get(request.POST['representation'])
    reservation = request.POST['reservation']
    if representation:
        db.run_in_transaction(unreserve_seats, representation, reservation)
        if not memcache.get(str(representation.key()) + '-ticket_timestamp'): #@UndefinedVariable
            taskqueue.add(url='/tasks/update_available_tickets/', params={'representation':representation.key(), }, countdown=10)
        memcache.set(str(representation.key()) + '-ticket_timestamp', datetime.utcnow().replace(tzinfo=gaepytz.utc)) #@UndefinedVariable
    logging.info('Task clean_reservation - Done') 
    return HttpResponse()

def reverse_transaction(request):
    logging.info('Task reverse_transaction - Start')
    transaction = Transaction.get(request.POST['transaction'])
    #TODO: Reverse transaction
    logging.info('Task reverse_transaction - Done')
    return HttpResponse()



def clean_payment(request):
    return HttpResponseServerError('Not implemented')


def update_available_tickets(request):
    logging.info('Task update_available_tickets - Start')
    representation = Representation.get(request.POST['representation'])
    if representation:
        timestamp = memcache.get(str(representation.key()) + '-ticket_timestamp') #@UndefinedVariable
        representation.calc_available_tickets(timestamp)
        if representation.available_tickets == 0:
            representation.status = 'Sold Out'
        else:
            if representation.status == 'Sold Out':
                representation.status = 'On Sale'
        memcache.delete(str(representation.key()) + '-ticket_timestamp') #@UndefinedVariable
        try:
            representation.put()
        except:
            memcache.set(str(representation.key()) + '-ticket_timestamp',timestamp) #@UndefinedVariable
    logging.info('Task update_available_tickets - End')
    return HttpResponse()

def update_representation_revenues(request):
    representation = Representation.get(request.POST['representation'])
    if representation:
        timestamp = memcache.get(str(representation.key()) + '-ticket_sold_timestamp') #@UndefinedVariable
        representation.calc_revenues(timestamp)
        memcache.delete(str(representation.key()) + '-ticket_sold_timestamp') #@UndefinedVariable
        try:            
            representation.put()
        except:
            memcache.set(str(representation.key()) + '-ticket_sold_timestamp',timestamp) #@UndefinedVariable
            raise
    return HttpResponse()


def acquirePayment(representation,type):
    payments = RepresentationPayment.all().filter('status =','Acquiring').ancestor(representation).get()
    if not payments:
        payment = RepresentationPayment(status='Acquiring',
                                        type=type,
                                        date=datetime.utcnow().replace(tzinfo=gaepytz.utc),
                                        parent=representation)
        payment.put()
        return payment
    else:
        return None     

def close_representation(request):
    logging.info('Task close_representation - Start')
    representation = None
    rep_key = request.POST.get('representation',None)
    if rep_key:
        representation = Representation.get(rep_key)
    if not representation:
        logging.critical('Invalid representation key: %s' % rep_key)
        logging.info('Task close_representation - Invalid representation')
        return HttpResponse("Invalid representation")
    logging.info(repr(representation))
    try:
        representation.event.key()
    except:
        logging.critical('Invalid event reference')
        logging.info('Task close_representation - Invalid Invalid event reference')
        return HttpResponse("Invalid event reference")
    try:
        if representation.event.limit_duration:
            duration = representation.event.duration
        else:
            duration = 360
    except:
        duration = 360
 
    rep_close_date = representation.date + timedelta(minutes=duration)
    if rep_close_date < datetime.utcnow().replace(tzinfo=gaepytz.utc):
        payment = db.run_in_transaction(acquirePayment,
                                              representation=representation,
                                              type='Commission')
        if payment:
            memo = "Payment of %.2f, 1%% of %.2f in ticket sales for %s" % (representation.commission_cost(),representation.revenues,representation.event.name + ', ' + str(representation.date))
            total_commission = representation.commission_cost()
            total_commission_already_billed = 0
            for payment in RepresentationPayment.all().ancestor(representation).filter('status =','Completed').filter('type =','Commission'):
                total_commission_already_billed = total_commission_already_billed + payment.amount
            payment_amount = total_commission - total_commission_already_billed
            if payment_amount > 0:
                paymentStatus = banian.paypal.processPayment(memo,representation.paypal_id,payment_amount,representation.pre_approval_key)
                payment.amount = payment_amount            
                if paymentStatus == 'Completed':
                    payment.status = 'Completed'
                    payment.put()
                    banian.paypal.processCancelPreApproval(representation.pre_approval_key)
                    if representation.status != 'Completed':
                        #TODO: Schedule ticket updates once the representation is close
                        #T0DO: CRON job to delete representation seats after xyz months
                        representation.status = 'Completed'
                        representation.put()
                    logging.info('Task close_representation - Completed')
                    return HttpResponse("Completed")
                elif paymentStatus == 'Canceled':
                    payment.status = 'Failed'
                    payment.put()
                    logging.critical('Task close_representation - Pre-Aproval Cancelled')
                    #TODO: do something when I get fucked and pre-approcal are cancelled before final payment.
                    return HttpResponse("Pre-Approval Cancelled")
                elif paymentStatus == 'paypal_unexpected':
                    payment.status = 'Failed'
                    payment.put()
                    logging.info('Task close_representation - paypal_unexpected')
                    return HttpResponseServerError('No payments collected')
                else:
                    logging.critical('Task close_representation - error in routine logic for %s' %  repr(representation))
                    return HttpResponseServerError('error in routine logic')
            else:
                if representation.status != 'Completed':
                    #TODO: Schedule ticket updates once the representation is close
                    #T0DO: CRON job to delete representation seats after xyz months                
                    representation.status = 'Completed'
                    representation.put()
                logging.info('Task close_representation - Completed')
                return HttpResponse("Completed")
        else:
            #TODO: if the acquisition date more than few minutes, need to process it anyway. Probably need to check the balance of approval vs what was billed and figure out a proper reconcilation
            logging.info('Task close_representation - Concurrency issue')
            return HttpResponseServerError('Concurrency issue')
    else:
        logging.critical('Cannot collect final payment on representation:\n %s' % repr(representation))
        logging.info('Task close_representation - No payments collected')
        return HttpResponseServerError('No payments collected')

def schedule_close_representations(request): 
    logging.info('schedule_close_representations - Start')
    representations = Representation.gql("WHERE date < :1 AND status IN :2",
                                         datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(hours=48),
                                         ['Published', 'On Sale', 'Sold Out'])
    if not representations.count(1):
        logging.info('schedule_close_representations - End')
        return HttpResponse("Nothing to do")
    if representations.count(fetch_limit) == fetch_limit:
        task = taskqueue.add(url='/tasks/schedule_close_representations/',countdown=7200)
    for representation in representations:
        try:
            if representation.event.limit_duration:
                duration = representation.event.duration
            else:
                duration = 360
        except:
            duration = 360
        close_date = representation.date + timedelta(minutes=duration)
        task = Task(url='/tasks/close_representation/', params={'representation':representation.key()},eta=close_date)
        try:
            task.add(queue_name='long-term-processing')
        except UnknownQueueError:
            ## In test cases the long-term-processing queue doesn't seems to be available. Since the dev server 
            ## is not running it is concevable that the queue.yaml was not read... not sure. In anycase this a 
            ## fallback if enqueueing fails with that error.
            task.add()
    #TODO: Change all tickets status
    logging.info('schedule_close_representations - End')
    return HttpResponse("Completed: %d" % representations.count(fetch_limit)) 

def schedule_put_on_sales(request):
    logging.info('schedule_put_on_sales - Start') 
    events = Event.gql("WHERE onsale_date < :1 AND status = :2",
                                         datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(hours=48),
                                         'Published')
    for event in events: 
        onesaletime = time.mktime(event.onsale_date.timetuple())
        task = Task(url='/tasks/put_on_sale/', params={'event':event.key(),'timestamp':onesaletime,}, eta=event.onsale_date)
        try:
            task.add(queue_name='long-term-processing')
        except UnknownQueueError:
            ## In test cases the long-term-processing queue doesn't seems to be available. Since the dev server 
            ## is not running it is concevable that the queue.yaml was not read... not sure. In anycase this a 
            ## fallback if enqueueing fails with that error.
            task.add()
    logging.info('schedule_put_on_sales - End') 
    return HttpResponse("Completed") 


def update_representation_history(request):
    logging.info('update_representation_history - Start') 
    representations = Representation.gql("WHERE timestamp_available < :1 AND status IN :2",
                                         datetime.utcnow().replace(tzinfo=gaepytz.utc) + timedelta(hours=-24),
                                         ['Published','On Sale']).fetch(put_limit)
    to_commit = []
    for representation in representations: 
        representation.histo_ticket.append(representation.event.nbr_seats() - representation.available_tickets)
        representation.histo_time.append(time.time())
        to_commit.append(representation)
    db.put(to_commit)
    if representations.count(put_limit) == put_limit:
        task = Task(url='/tasks/update_representation_history/', countdown=0)
        try:
            task.add(queue_name='long-term-processing')
        except UnknownQueueError:
            ## In test cases the long-term-processing queue doesn't seems to be available. Since the dev server 
            ## is not running it is concevable that the queue.yaml was not read... not sure. In anycase this a 
            ## fallback if enqueueing fails with that error.
            task.add()
    
    logging.info('update_representation_history - End') 
    return HttpResponse("Completed") 



def auto_load(request):
    taskqueue.add(url='/tasks/auto_load/', countdown=60)
    return HttpResponse("Completed")
