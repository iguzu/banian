'''
Created on Nov 21, 2009

@author: sboire
'''
# -*- coding: utf-8 -*-
from django.conf.urls.defaults import * #@UnusedWildImport


urlpatterns = patterns('banian.tasks.views', #@UndefinedVariable
 (r'^clean_reservation/$', 'clean_reservation'),
 (r'^clean_payment/$', 'clean_payment'),
 (r'^generate_seats/$', 'generate_seats'),
 (r'^delete_seats/$', 'delete_seats'),
 (r'^refund_tickets/$', 'refund_tickets'),
 (r'^generate_tickets/$', 'generate_tickets'),
 (r'^put_on_sale/$', 'put_on_sale'), 
 (r'^update_available_tickets/$', 'update_available_tickets'),
 (r'^update_representation_revenues/$', 'update_representation_revenues'),
 (r'^close_representation/$', 'close_representation'),
 (r'^schedule_close_representations/$', 'schedule_close_representations'),
 (r'^schedule_put_on_sales/$', 'schedule_put_on_sales'),
 (r'^auto_load/$', 'auto_load'), 
 (r'^reverse_transaction/$', 'reverse_transaction'),
(r'^update_representation_history/$', 'update_representation_history'),  
)