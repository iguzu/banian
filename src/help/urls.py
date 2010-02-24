from django.conf.urls.defaults import * #@UnusedWildImport

urlpatterns = patterns('',
    (r'^$', 'help.views.list_entries'),
 )