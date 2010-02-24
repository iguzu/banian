# -*- coding: utf-8 -*-
from django.conf.urls.defaults import * #@UnusedWildImport


urlpatterns = patterns('banian.venue.views', #@UndefinedVariable
 (r'^$','venues'),
 (r'^create/$', 'add_venue'),
 (r'^show/(?P<key>.+)$', 'show_venue'),
 (r'^edit/(?P<key>.+)$', 'edit_venue'),
 (r'^delete/(?P<key>.+)$', 'delete_venue'),
 (r'^seat_configs/$','seat_configs'),
 (r'^seat_configs/create/$', 'add_seat_config'),
 (r'^seat_configs/show/(?P<key>.+)$', 'show_seat_config'),
 (r'^seat_configs/edit/(?P<key>.+)$', 'edit_seat_config'),
 (r'^seat_configs/delete/(?P<key>.+)$', 'delete_seat_config'),
(r'^seat_groups/$','seat_groups'),
 (r'^seat_groups/create/$', 'add_seat_group'),
 (r'^seat_groups/show/(?P<key>.+)$', 'show_seat_group'),
 (r'^seat_groups/edit/(?P<key>.+)$', 'edit_seat_group'),
 (r'^seat_groups/delete/(?P<key>.+)$', 'delete_seat_group'),
)
