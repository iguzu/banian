# -*- coding: utf-8 -*-
from django.conf.urls.defaults import * #@UnusedWildImport
from ragendja.urlsauto import urlpatterns #@UnresolvedImport
from django.contrib import admin

admin.autodiscover() #@UndefinedVariable

handler500 = 'ragendja.views.server_error'
# auth_patterns +
urlpatterns =  patterns('',
    ('^C5jCnPsm8ixSMXxEdd/(.*)', admin.site.root), #@UndefinedVariable
    (r'^help/', include('help.urls')),    
    (r'^', include('banian.urls')),
) + urlpatterns
