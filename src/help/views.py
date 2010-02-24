from django.template import RequestContext, loader
from django.http import HttpResponse


def list_entries(request):
    t = loader.get_template('help/help.html')
    
    h = RequestContext(request, { 'help': t,})
    return HttpResponse(t.render(h))
