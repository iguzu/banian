from django.conf.urls.defaults import * #@UnusedWildImport

rootpatterns = patterns('',
    (r'^account/', include('registration.urls')),
)
