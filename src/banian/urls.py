# -*- coding: utf-8 -*-
from django.conf.urls.defaults import * #@UnusedWildImport


urlpatterns = patterns('banian.views', #@UndefinedVariable
 (r'^venues/', include('banian.venue.urls')), #@UndefinedVariable
 (r'^tasks/', include('banian.tasks.urls')), #@UndefinedVariable
 (r'^events$','events'),
 (r'^events/create/$', 'add_event'),
 (r'^events/show/(?P<key>.+)$', 'show_event'),
 (r'^events/edit/(?P<key>.+)$', 'edit_event'),
 (r'^events/delete/(?P<key>.+)$', 'delete_event'),
 (r'^events/view/(?P<key>.+)$', 'view_event'),
 (r'^events/representations/validation_list/$', 'validation_list'),
 (r'^events/representations/validate/(?P<key>.+)$', 'validate'),
 (r'^events/representations/validators/(?P<key>.+)$', 'validator_list'), 
 (r'^events/venues/view/(?P<key>.+)$', 'view_venue'),
 (r'^events/class/create/$', 'add_class'),
 (r'^events/class/show/(?P<key>.+)$', 'show_class'),
 (r'^events/class/edit/(?P<key>.+)$', 'edit_class'),
 (r'^events/class/delete/(?P<key>.+)$', 'delete_class'),
 (r'^events/representations/show/(?P<key>.+)$', 'show_representation'),
 (r'^events/representations/edit/(?P<key>.+)$', 'edit_representation'),
 (r'^events/representations/create/$', 'add_representation'),
 (r'^events/representations/delete/(?P<key>.+)$', 'delete_representation'),
 (r'^events/representations/unpublish/(?P<key>.+)$', 'unpublish_representation'),
 (r'^events/representations/publish/(?P<key>.+)$', 'publish'),
 (r'^events/representations/buy/(?P<key>.+)$', 'buy_representation'),
 (r'^events/representations/purchase_sucess/$', 'purchase_success'),
 (r'^events/representations/purchase_failure/$', 'purchase_failure'),
 (r'^events/representations/seats/(?P<key>.+)$', 'seats'), 
 (r'^events/representations/seat/show/(?P<key>.+)$', 'show_seat'),
 (r'^events/representations/cancel/(?P<key>.+)$', 'cancel_representation'),
 (r'^events/select_seatconfig/$', 'select_seat_config'),
 (r'^events/show_representation_job_progess/(?P<key>.+)$', 'show_representation_job_progess'),
 (r'^events/select_venue/$', 'select_venue'),
 (r'^search/events/$', 'search_events'),
 (r'^timezonelist/$', 'timezonelist'),
 (r'^transactions/$', 'transactions'),
 (r'^transactions/show/(?P<key>.+)$', 'show_transaction'),
 (r'^user_events/$', 'user_events'),
 (r'^user_events/show/(?P<key>.+)$', 'show_user_event'),
 (r'^tickets/download/(?P<key>.+)$', 'download_ticket'),
 (r'^tickets/download/$', 'download_tickets'),
 (r'^image/(?P<key>.+)$', 'image'),
 (r'^redirect_url/$', 'redirect_url'),
 (r'^settings/$', 'settings'),
 (r'^$', 'default'),
# (r'^events/quick_event/$', 'quick_event'), 
 (r'^events/preview_sale_page/(?P<key>.+)$', 'preview_sale_page'),
 (r'^events/preview_ticket/(?P<key>.+)$', 'preview_ticket'),
 (r'^transfering/(?P<url>.+)$', 'transfering'), 
 (r'^events/representation/ticket_history/(?P<key>.+)$', 'representation_ticket_history'),
)
