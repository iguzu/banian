'''
Created on Sep 14, 2009

@author: install
'''
from ragendja.template import render_to_response
from django.forms.fields import Field
from django.forms.widgets import Textarea
from google.appengine.api.labs import taskqueue
from banian.paypal import processPaymentEx
from django.forms.forms import ValidationError
import urllib

import math
import logging #@UnusedImport
import HTMLParser

from google.appengine.api import images
from google.appengine.ext import db


from django.template import RequestContext, loader
from django.http import HttpResponse
from django.core.xheaders import populate_xheaders
from django.utils.translation import ugettext #@UnresolvedImport
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.contrib.auth.models import Message
from django.views.generic.create_update import lookup_object, get_model_and_form_class, redirect, apply_extra_context
from ragendja.dbutils import get_object #@UnresolvedImport
from banian.models import google_images, Image, Seat, SeatGroup, fetch_limit,\
    UserEvent, max_ticket_limit, TicketClass
        


def auto_loader():
    logging.debug('adding task')
    taskqueue.add(url='/tasks/auto_load/', countdown=0)
    logging.debug('adding task done')
    

def transfer_to_paypal(request,url):
    logging.debug(repr(url))
    url = urllib.quote(url)
    return render_to_response(request, "banian/transfering.html", {'redirect':url,})

def create_object(request, model=None, template_name=None,
        template_loader=loader, extra_context=None, post_save_redirect=None,
        login_required=False, context_processors=None, form_class=None, form_kwargs={}):
    """
    Generic object-creation function.

    Templates: ``<app_label>/<model_name>_form.html``
    Context:
        form
            the form for the object
    """
    if extra_context is None: extra_context = {}
    if login_required and not request.user.is_authenticated():
        return redirect_to_login(request.path)

    model, form_class = get_model_and_form_class(model, form_class)
    kwargs = {}
    for (key, value) in form_kwargs.iteritems():
        kwargs[key] = value
    if request.method == 'POST':
        kwargs['files'] = request.FILES
        kwargs['data'] = request.POST
        form = form_class(**kwargs)
        if form.is_valid():
            new_object = form.save()
            if request.user.is_authenticated():
                Message(user=request.user, message=ugettext("The %(verbose_name)s was created successfully.") % {"verbose_name": model._meta.verbose_name}).put()
            return redirect(post_save_redirect, new_object)
    else:
        form = form_class(**kwargs)

    # Create the template, context, response
    if not template_name:
        template_name = "%s/%s_form.html" % (model._meta.app_label, model._meta.object_name.lower())
    t = template_loader.get_template(template_name)
    c = RequestContext(request, {
        'form': form,
    }, context_processors)
    apply_extra_context(extra_context, c)
    return HttpResponse(t.render(c))


def update_object(request, model=None, object_id=None, slug=None,
        slug_field='slug', template_name=None, template_loader=loader,
        extra_context=None, post_save_redirect=None, login_required=False,
        context_processors=None, template_object_name='object',
        form_class=None, form_kwargs={}):
    """
    Generic object-update function.

    Templates: ``<app_label>/<model_name>_form.html``
    Context:
        form
            the form for the object
        object
            the original object being edited
    """
    if extra_context is None: extra_context = {}
    if login_required and not request.user.is_authenticated():
        return redirect_to_login(request.path)

    model, form_class = get_model_and_form_class(model, form_class)
    obj = lookup_object(model, object_id, slug, slug_field)
    kwargs = dict(instance=obj)
    for (key, value) in form_kwargs.iteritems():
        kwargs[key] = value
    if request.method == 'POST':
        kwargs['files'] = request.FILES
        kwargs['data'] = request.POST
        form = form_class(**kwargs)
        if form.is_valid():
            obj = form.save()
            if request.user.is_authenticated():
                Message(user=request.user, message=ugettext("The %(verbose_name)s was updated successfully.") % {"verbose_name": model._meta.verbose_name}).put()
            return redirect(post_save_redirect, obj)
    else:
        form = form_class(**kwargs)

    if not template_name:
        template_name = "%s/%s_form.html" % (model._meta.app_label, model._meta.object_name.lower())
    t = template_loader.get_template(template_name)
    c = RequestContext(request, {
        'form': form,
        template_object_name: obj,
    }, context_processors)
    apply_extra_context(extra_context, c)
    response = HttpResponse(t.render(c))
    populate_xheaders(request, response, model, obj.key())
    return response

def update_seat_config(seat_configuration):
    seat_configuration.nbr_seat = 0
    seat_groups = seat_configuration.seatgroup_set
    for item in seat_groups:
        seat_configuration.nbr_seat += item.nbr_seat
    seat_configuration.put()        

def update_seat_group(seat_group):
    while(seat_group):
        seat_group.total_nbr_seat = 0
        seat_groups = SeatGroup.all().ancestor(seat_group)
        for item in seat_groups:
            seat_group.total_nbr_seat += item.nbr_seat
            sg_iter = item; location = []
            while(sg_iter):
                location.insert(0,sg_iter.name)
                sg_iter = sg_iter.seat_group
            item.location = location
            item.put()
        seat_group.put()
        seat_group = seat_group.parent()

def get_own_object_or_404(user, model, *filters_or_key, **kwargs):
    item = get_object(model, *filters_or_key, **kwargs)
    if not item:
        raise Http404('Object does not exist! or cannot be accessed')
    try:
        if user != item.owner:
            raise Http404('Object does not exist! or cannot be accessed')
    except:
        raise Http404('Object does not exist! or cannot be accessed')
    return item




"""
  Python implementation of Haversine formula
  Copyright (C) <2009>  Bartek <bartek@gorny.edu.pl>

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

def recalculate_coordinate(val, _as=None):
    """
    Accepts a coordinate as a tuple (degree, minutes, seconds)
    You can give only one of them (e.g. only minutes as a floating point number) and it will be duly
    recalculated into degrees, minutes and seconds.
    Return value can be specified as 'deg', 'min' or 'sec'; default return value is a proper coordinate tuple.
    """
    deg, min, sec = val
    # pass outstanding values from right to left
    min = (min or 0) + int(sec) / 60
    sec = sec % 60
    deg = (deg or 0) + int(min) / 60
    min = min % 60
    # pass decimal part from left to right
    dfrac, dint = math.modf(deg)
    min = min + dfrac * 60
    deg = dint
    mfrac, mint = math.modf(min)
    sec = sec + mfrac * 60
    min = mint
    if _as:
        sec = sec + min * 60 + deg * 3600
        if _as == 'sec': return sec
        if _as == 'min': return sec / 60
        if _as == 'deg': return sec / 3600
    return deg, min, sec
      

def points2distance(start, end):
    """
    Calculate distance (in kilometers) between two points given as (long, latt) pairs
    based on Haversine formula (http://en.wikipedia.org/wiki/Haversine_formula).
    Implementation inspired by JavaScript implementation from http://www.movable-type.co.uk/scripts/latlong.html
    Accepts coordinates as tuples (deg, min, sec), but coordinates can be given in any form - e.g.
    can specify only minutes:
    (0, 3133.9333, 0) 
    is interpreted as 
    (52.0, 13.0, 55.998000000008687)
    which, not accidentally, is the lattitude of Warsaw, Poland.
    """
    start_long = math.radians(recalculate_coordinate(start[0], 'deg'))
    start_latt = math.radians(recalculate_coordinate(start[1], 'deg'))
    end_long = math.radians(recalculate_coordinate(end[0], 'deg'))
    end_latt = math.radians(recalculate_coordinate(end[1], 'deg'))
    d_latt = end_latt - start_latt
    d_long = end_long - start_long
    a = math.sin(d_latt / 2) ** 2 + math.cos(start_latt) * math.cos(end_latt) * math.sin(d_long / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6371 * c


def handle_images  (form, object):
    for (key, value) in form.files.iteritems():
        if key == 'thumbnail':
            if object.thumbnail_image:
                image = object.thumbnail_image
            else:
                image = Image()
            image.filename = value.name
            index = image.filename.rindex('.')
            image.content_type = image.filename[index + 1:].lower()
            if image.content_type not in google_images.keys():
                image.content_type = 'png'
                image.filename = image.filename[:index + 1] + image.content_type
            file = value.read()
            img = images.Image(file)
            if img.width > 200 and img.height > 200:
                img.resize(200, 200)
                image.content = img.execute_transforms(google_images[image.content_type])
            else:
                image.content = file
            image.put()
            object.thumbnail_image = image
        elif key == 'poster':
            if object.poster_image:
                image = object.poster_image
            else:
                image = Image()
            image.filename = value.name
            index = image.filename.rindex('.')
            image.content_type = image.filename[index + 1:].lower()
            if image.content_type not in google_images.keys():
                image.content_type = 'png'
                image.filename = image.filename[:index + 1] + image.content_type
            file = value.read()
            img = images.Image(file)
            if img.width != 200 or img.height > 400:
                width = 200
                if img.height > 400: height = 400
                else: height = img.height
                img.resize(width, height)
                image.content = img.execute_transforms(google_images[image.content_type])
            else:
                image.content = file
            image.put()
            object.poster_image = image

def reserve_seats(representation, reservation, data):
    for key, item in data.iteritems():
        seats = Seat.all().filter('representation =', representation).filter('ticket_class =', key).filter('availability =', 0).ancestor(representation).fetch(item)
        for index, item in enumerate(seats):
            seats[index].availability = 1
            seats[index].reservation = reservation
        db.put(seats)  

def unreserve_seats(representation, reservation):
    while(1):
        seats = Seat.all().filter('reservation =', reservation).filter('availability =', 1).ancestor(representation).fetch(fetch_limit)
        for index, item in enumerate(seats): #@UnusedVariable
            seats[index].availability = 0
            seats[index].reservation = None
        db.put(seats)
        if seats.count(501) < 501:
            break
        
def location_window(latitude, longitude, radius, units):
    if units == 'km':
        radius = radius * 0.621371192
    lng_min = longitude - radius / abs(math.cos(math.radians(latitude)) * 69)
    lng_max = longitude + radius / abs(math.cos(math.radians(latitude)) * 69)
    lat_min = latitude - (radius / 69)
    lat_max = latitude + (radius / 69)
    if lng_min > lng_max:
        temp = lng_min
        lng_min = lng_max
        lng_max = temp
    if lat_min > lat_max:
        temp = lat_min
        lat_min = lat_max
        lat_max = temp
    return lng_min, lat_min, lng_max, lat_max 


def preparePayment(request, representation, data):
    memo = "Tickets for %s on %s at %s:\n"
    total = 0
    for key,value in data.iteritems():
        ticket_class = TicketClass.get(key)
        memo = memo + " - %d tickets at %.2f\n" % (value,ticket_class.price)
        total = total + ticket_class.price * value
    memo = memo + " - For a total of %.2f\n" % total
    return processPaymentEx(request=request,memo=memo, amount=total, apkey=None,receiver=representation.owner.paypal_id)

def take_seats(representation, reservation, data):
    seats = Seat.all().filter('reservation =', reservation).ancestor(representation).fetch(fetch_limit)
    for index, item in enumerate(seats): #@UnusedVariable
        seats[index].availability = 2
    db.put(seats)

def generate_error_report(user, representation, reservation, data):
        raise AssertionError('Not Implemented')
    
def calc_ticket_class_available(owner,ticketclass, representation):
    count = representation.get_ticketclass_available()[str(ticketclass.key())]
    if count == 1:
        total_available_text = '(1 ticket left)'
    elif count == 0:
        total_available_text = '(No ticket left)'
    elif count > 1:
        total_available_text = '(%d tickets left)' % count
    total_available = count
    if representation.event.limit_tickets:
        max_tickets = representation.event.max_tickets
        #TODO: use valid tickets to calculate the number of tickets one can take
        user_event = UserEvent.all().filter('owner =',owner).filter('representation =', representation).filter('status =','Valid').get()
        if user_event:
            if user_event.nbr_tickets < max_tickets:
                max_tickets = max_tickets - user_event.nbr_tickets
            else:
                max_tickets = 0
        if max_tickets > count:
            max_tickets = count
    else:
        max_tickets = count
    if max_tickets > max_ticket_limit:
        max_tickets = max_ticket_limit
    return total_available_text, total_available, max_tickets

class ElementExtracter(HTMLParser.HTMLParser):
    "A simple parser class."

    def parse(self, s):
        self.feed(s)
        self.close()

    def __init__(self,tag,attributes,include_tag=False):
        self.include_tag = include_tag
        self.attributes = attributes
        self.tag = tag
        HTMLParser.HTMLParser.__init__(self)
        self.content = ''
        self.record = False
        self.nested = 0

    def handle_starttag(self, tag, attributes):
        if tag == self.tag:
            if self.record == False:
                for key,value in self.attributes.iteritems():
                    self.record = False
                    for param_name, param_value in attributes:
                        if key  == param_name and value == param_value:
                            self.record = True
                    if self.record == False:
                        break
                if self.record == True and self.include_tag:
                    attrib = ''
                    for name,value in attributes:
                        attrib = attrib + ' ' + name + '="' + value + '"' 
                    self.content = self.content + '<' + tag + attrib + '>'
            else:
                self.nested = self.nested + 1
                attrib = ''
                for name,value in attributes:
                    attrib = attrib + ' ' + name + '="' + value + '"' 
                self.content = self.content + '<' + tag + attrib + '>'
        elif self.record == True:
            attrib = ''
            for name,value in attributes:
                attrib = attrib + ' ' + name + '="' + value + '"' 
            self.content = self.content + '<' + tag + attrib + '>'

    def handle_endtag(self,tag):
        if tag == self.tag :
            if self.record:
                if self.nested > 1:
                    self.nested = self.nested - 1
                    self.content = self.content + '</' + tag + '>'
                else:
                    self.record = False
                    if self.include_tag:
                        self.content = self.content + '</' + tag + '>'
        elif self.record == True:
            self.content = self.content + '</' + tag + '>'

    def handle_data(self,data):
        if self.record == True:
            self.content = self.content + data

    def get_content(self):
        return self.content

    def extract(self, s):
        self.content = ''
        self.nested = 0
        self.record = False
        self.feed(s)
        self.close()
        return self.content


class TextField(Field):
    widget = Textarea

    def __init__(self, required=True, widget=None,*args, **kwargs):
        super(TextField, self).__init__(required, widget,*args, **kwargs)

def convertTimezonePosition(position):
    point = ([],[])
    i = position.find('+',1)
    if(i<0):
        i = position.find('-',1)
    assert i>0
    lon_sign = 1; lat_sign = 1
    if position[0] == '-':
        lat_sign = -1    
    if position[i] == '-':
        lon_sign = -1

    lat = position[1:i]
    lon = position[i+1:]
    if(len(lat)==4):
        point[1].append(int(lat[0:2]))
        point[1].append(int(lat[2:]))
        point[1].append(0)
    else:
        point[1].append(int(lat[0:2]))
        point[1].append(int(lat[2:4]))
        point[1].append(int(lat[4:]))
        
    if(len(lon)==5):
        point[0].append(int(lon[0:3]))
        point[0].append(int(lon[3:]))
        point[0].append(0)
    else:
        point[0].append(int(lon[0:3]))
        point[0].append(int(lon[3:5]))
        point[0].append(int(lon[5:]))

    point[0][0] =  point[0][0] * lon_sign
    point[1][0] =  point[1][0] * lat_sign

    return point

cctld_tz = {'BD': [['+2343+09025', 'Asia/Dhaka']], 'BE': [['+5050+00420', 'Europe/Brussels']], 'BF': [['+1222-00131', 'Africa/Ouagadougou']], 'BG': [['+4241+02319', 'Europe/Sofia']], 'BA': [['+4352+01825', 'Europe/Sarajevo']], 'BB': [['+1306-05937', 'America/Barbados']], 'WF': [['-1318-17610', 'Pacific/Wallis']], 'BL': [['+1753-06251', 'America/St_Barthelemy']], 'BM': [['+3217-06446', 'Atlantic/Bermuda']], 'BN': [['+0456+11455', 'Asia/Brunei']], 'BO': [['-1630-06809', 'America/La_Paz']], 'BH': [['+2623+05035', 'Asia/Bahrain']], 'BI': [['-0323+02922', 'Africa/Bujumbura']], 'BJ': [['+0629+00237', 'Africa/Porto-Novo']], 'BT': [['+2728+08939', 'Asia/Thimphu']], 'JM': [['+1800-07648', 'America/Jamaica']], 'BW': [['-2439+02555', 'Africa/Gaborone']], 'WS': [['-1350-17144', 'Pacific/Apia']], 'BR': [['-0351-03225', 'America/Noronha', 'Atlantic islands'], ['-0127-04829', 'America/Belem', 'Amapa, E Para'], ['-0343-03830', 'America/Fortaleza', 'NE Brazil (MA, PI, CE, RN, PB)'], ['-0803-03454', 'America/Recife', 'Pernambuco'], ['-0712-04812', 'America/Araguaina', 'Tocantins'], ['-0940-03543', 'America/Maceio', 'Alagoas, Sergipe'], ['-1259-03831', 'America/Bahia', 'Bahia'], ['-2332-04637', 'America/Sao_Paulo', 'S & SE Brazil (GO, DF, MG, ES, RJ, SP, PR, SC, RS)'], ['-2027-05437', 'America/Campo_Grande', 'Mato Grosso do Sul'], ['-1535-05605', 'America/Cuiaba', 'Mato Grosso'], ['-0226-05452', 'America/Santarem', 'W Para'], ['-0846-06354', 'America/Porto_Velho', 'Rondonia'], ['+0249-06040', 'America/Boa_Vista', 'Roraima'], ['-0308-06001', 'America/Manaus', 'E Amazonas'], ['-0640-06952', 'America/Eirunepe', 'W Amazonas'], ['-0958-06748', 'America/Rio_Branco', 'Acre']], 'BS': [['+2505-07721', 'America/Nassau']], 'JE': [['+4912-00207', 'Europe/Jersey']], 'BY': [['+5354+02734', 'Europe/Minsk']], 'BZ': [['+1730-08812', 'America/Belize']], 'RU': [['+5443+02030', 'Europe/Kaliningrad', 'Moscow-01 - Kaliningrad'], ['+5545+03735', 'Europe/Moscow', 'Moscow+00 - west Russia'], ['+4844+04425', 'Europe/Volgograd', 'Moscow+00 - Caspian Sea'], ['+5312+05009', 'Europe/Samara', 'Moscow+01 - Samara, Udmurtia'], ['+5651+06036', 'Asia/Yekaterinburg', 'Moscow+02 - Urals'], ['+5500+07324', 'Asia/Omsk', 'Moscow+03 - west Siberia'], ['+5502+08255', 'Asia/Novosibirsk', 'Moscow+03 - Novosibirsk'], ['+5601+09250', 'Asia/Krasnoyarsk', 'Moscow+04 - Yenisei River'], ['+5216+10420', 'Asia/Irkutsk', 'Moscow+05 - Lake Baikal'], ['+6200+12940', 'Asia/Yakutsk', 'Moscow+06 - Lena River'], ['+4310+13156', 'Asia/Vladivostok', 'Moscow+07 - Amur River'], ['+4658+14242', 'Asia/Sakhalin', 'Moscow+07 - Sakhalin Island'], ['+5934+15048', 'Asia/Magadan', 'Moscow+08 - Magadan'], ['+5301+15839', 'Asia/Kamchatka', 'Moscow+09 - Kamchatka'], ['+6445+17729', 'Asia/Anadyr', 'Moscow+10 - Bering Sea']], 'RW': [['-0157+03004', 'Africa/Kigali']], 'RS': [['+4450+02030', 'Europe/Belgrade']], 'TL': [['-0833+12535', 'Asia/Dili']], 'RE': [['-2052+05528', 'Indian/Reunion']], 'TM': [['+3757+05823', 'Asia/Ashgabat']], 'TJ': [['+3835+06848', 'Asia/Dushanbe']], 'RO': [['+4426+02606', 'Europe/Bucharest']], 'TK': [['-0922-17114', 'Pacific/Fakaofo']], 'GW': [['+1151-01535', 'Africa/Bissau']], 'GU': [['+1328+14445', 'Pacific/Guam']], 'GT': [['+1438-09031', 'America/Guatemala']], 'GS': [['-5416-03632', 'Atlantic/South_Georgia']], 'GR': [['+3758+02343', 'Europe/Athens']], 'GQ': [['+0345+00847', 'Africa/Malabo']], 'GP': [['+1614-06132', 'America/Guadeloupe']], 'JP': [['+353916+1394441', 'Asia/Tokyo']], 'GY': [['+0648-05810', 'America/Guyana']], 'GG': [['+4927-00232', 'Europe/Guernsey']], 'GF': [['+0456-05220', 'America/Cayenne']], 'GE': [['+4143+04449', 'Asia/Tbilisi']], 'GD': [['+1203-06145', 'America/Grenada']], 'GB': [['+513030-0000731', 'Europe/London']], 'GA': [['+0023+00927', 'Africa/Libreville']], 'SV': [['+1342-08912', 'America/El_Salvador']], 'GN': [['+0931-01343', 'Africa/Conakry']], 'GM': [['+1328-01639', 'Africa/Banjul']], 'GL': [['+6411-05144', 'America/Godthab', 'most locations'], ['+7646-01840', 'America/Danmarkshavn', 'east coast, north of Scoresbysund'], ['+7029-02158', 'America/Scoresbysund', 'Scoresbysund / Ittoqqortoormiit'], ['+7634-06847', 'America/Thule', 'Thule / Pituffik']], 'GI': [['+3608-00521', 'Europe/Gibraltar']], 'GH': [['+0533-00013', 'Africa/Accra']], 'OM': [['+2336+05835', 'Asia/Muscat']], 'TN': [['+3648+01011', 'Africa/Tunis']], 'JO': [['+3157+03556', 'Asia/Amman']], 'HR': [['+4548+01558', 'Europe/Zagreb']], 'HT': [['+1832-07220', 'America/Port-au-Prince']], 'HU': [['+4730+01905', 'Europe/Budapest']], 'HK': [['+2217+11409', 'Asia/Hong_Kong']], 'HN': [['+1406-08713', 'America/Tegucigalpa']], 'VE': [['+1030-06656', 'America/Caracas']], 'PR': [['+182806-0660622', 'America/Puerto_Rico']], 'PS': [['+3130+03428', 'Asia/Gaza']], 'PW': [['+0720+13429', 'Pacific/Palau']], 'PT': [['+3843-00908', 'Europe/Lisbon', 'mainland'], ['+3238-01654', 'Atlantic/Madeira', 'Madeira Islands'], ['+3744-02540', 'Atlantic/Azores', 'Azores']], 'SJ': [['+7800+01600', 'Arctic/Longyearbyen']], 'PY': [['-2516-05740', 'America/Asuncion']], 'IQ': [['+3321+04425', 'Asia/Baghdad']], 'PA': [['+0858-07932', 'America/Panama']], 'PF': [['-1732-14934', 'Pacific/Tahiti', 'Society Islands'], ['-0900-13930', 'Pacific/Marquesas', 'Marquesas Islands'], ['-2308-13457', 'Pacific/Gambier', 'Gambier Islands']], 'PG': [['-0930+14710', 'Pacific/Port_Moresby']], 'PE': [['-1203-07703', 'America/Lima']], 'PK': [['+2452+06703', 'Asia/Karachi']], 'PH': [['+1435+12100', 'Asia/Manila']], 'PN': [['-2504-13005', 'Pacific/Pitcairn']], 'PL': [['+5215+02100', 'Europe/Warsaw']], 'PM': [['+4703-05620', 'America/Miquelon']], 'ZM': [['-1525+02817', 'Africa/Lusaka']], 'EH': [['+2709-01312', 'Africa/El_Aaiun']], 'EE': [['+5925+02445', 'Europe/Tallinn']], 'EG': [['+3003+03115', 'Africa/Cairo']], 'ZA': [['-2615+02800', 'Africa/Johannesburg']], 'EC': [['-0210-07950', 'America/Guayaquil', 'mainland'], ['-0054-08936', 'Pacific/Galapagos', 'Galapagos Islands']], 'IT': [['+4154+01229', 'Europe/Rome']], 'VN': [['+1045+10640', 'Asia/Ho_Chi_Minh']], 'SB': [['-0932+16012', 'Pacific/Guadalcanal']], 'ET': [['+0902+03842', 'Africa/Addis_Ababa']], 'SO': [['+0204+04522', 'Africa/Mogadishu']], 'SA': [['+2438+04643', 'Asia/Riyadh']], 'ES': [['+4024-00341', 'Europe/Madrid', 'mainland'], ['+3553-00519', 'Africa/Ceuta', 'Ceuta & Melilla'], ['+2806-01524', 'Atlantic/Canary', 'Canary Islands']], 'ER': [['+1520+03853', 'Africa/Asmara']], 'ME': [['+4226+01916', 'Europe/Podgorica']], 'MD': [['+4700+02850', 'Europe/Chisinau']], 'MG': [['-1855+04731', 'Indian/Antananarivo']], 'MF': [['+1804-06305', 'America/Marigot']], 'MA': [['+3339-00735', 'Africa/Casablanca']], 'MC': [['+4342+00723', 'Europe/Monaco']], 'UZ': [['+3940+06648', 'Asia/Samarkand', 'west Uzbekistan'], ['+4120+06918', 'Asia/Tashkent', 'east Uzbekistan']], 'MM': [['+1647+09610', 'Asia/Rangoon']], 'ML': [['+1239-00800', 'Africa/Bamako']], 'MO': [['+2214+11335', 'Asia/Macau']], 'MN': [['+4755+10653', 'Asia/Ulaanbaatar', 'most locations'], ['+4801+09139', 'Asia/Hovd', 'Bayan-Olgiy, Govi-Altai, Hovd, Uvs, Zavkhan'], ['+4804+11430', 'Asia/Choibalsan', 'Dornod, Sukhbaatar']], 'MH': [['+0709+17112', 'Pacific/Majuro', 'most locations'], ['+0905+16720', 'Pacific/Kwajalein', 'Kwajalein']], 'MK': [['+4159+02126', 'Europe/Skopje']], 'MU': [['-2010+05730', 'Indian/Mauritius']], 'MT': [['+3554+01431', 'Europe/Malta']], 'MW': [['-1547+03500', 'Africa/Blantyre']], 'MV': [['+0410+07330', 'Indian/Maldives']], 'MQ': [['+1436-06105', 'America/Martinique']], 'MP': [['+1512+14545', 'Pacific/Saipan']], 'MS': [['+1643-06213', 'America/Montserrat']], 'MR': [['+1806-01557', 'Africa/Nouakchott']], 'IM': [['+5409-00428', 'Europe/Isle_of_Man']], 'UG': [['+0019+03225', 'Africa/Kampala']], 'TZ': [['-0648+03917', 'Africa/Dar_es_Salaam']], 'MY': [['+0310+10142', 'Asia/Kuala_Lumpur', 'peninsular Malaysia'], ['+0133+11020', 'Asia/Kuching', 'Sabah & Sarawak']], 'MX': [['+1924-09909', 'America/Mexico_City', 'Central Time - most locations'], ['+2105-08646', 'America/Cancun', 'Central Time - Quintana Roo'], ['+2058-08937', 'America/Merida', 'Central Time - Campeche, Yucatan'], ['+2540-10019', 'America/Monterrey', 'Central Time - Coahuila, Durango, Nuevo Leon, Tamaulipas'], ['+2313-10625', 'America/Mazatlan', 'Mountain Time - S Baja, Nayarit, Sinaloa'], ['+2838-10605', 'America/Chihuahua', 'Mountain Time - Chihuahua'], ['+2904-11058', 'America/Hermosillo', 'Mountain Standard Time - Sonora'], ['+3232-11701', 'America/Tijuana', 'Pacific Time']], 'IL': [['+3146+03514', 'Asia/Jerusalem']], 'FR': [['+4852+00220', 'Europe/Paris']], 'IO': [['-0720+07225', 'Indian/Chagos']], 'SH': [['-1555-00542', 'Atlantic/St_Helena']], 'FI': [['+6010+02458', 'Europe/Helsinki']], 'FJ': [['-1808+17825', 'Pacific/Fiji']], 'FK': [['-5142-05751', 'Atlantic/Stanley']], 'FM': [['+0725+15147', 'Pacific/Truk', 'Truk (Chuuk) and Yap'], ['+0658+15813', 'Pacific/Ponape', 'Ponape (Pohnpei)'], ['+0519+16259', 'Pacific/Kosrae', 'Kosrae']], 'FO': [['+6201-00646', 'Atlantic/Faroe']], 'NI': [['+1209-08617', 'America/Managua']], 'NL': [['+5222+00454', 'Europe/Amsterdam']], 'NO': [['+5955+01045', 'Europe/Oslo']], 'NA': [['-2234+01706', 'Africa/Windhoek']], 'VU': [['-1740+16825', 'Pacific/Efate']], 'NC': [['-2216+16627', 'Pacific/Noumea']], 'NE': [['+1331+00207', 'Africa/Niamey']], 'NF': [['-2903+16758', 'Pacific/Norfolk']], 'NG': [['+0627+00324', 'Africa/Lagos']], 'NZ': [['-3652+17446', 'Pacific/Auckland', 'most locations'], ['-4357-17633', 'Pacific/Chatham', 'Chatham Islands']], 'NP': [['+2743+08519', 'Asia/Kathmandu']], 'NR': [['-0031+16655', 'Pacific/Nauru']], 'NU': [['-1901-16955', 'Pacific/Niue']], 'CK': [['-2114-15946', 'Pacific/Rarotonga']], 'CI': [['+0519-00402', 'Africa/Abidjan']], 'CH': [['+4723+00832', 'Europe/Zurich']], 'CO': [['+0436-07405', 'America/Bogota']], 'CN': [['+3114+12128', 'Asia/Shanghai', 'east China - Beijing, Guangdong, Shanghai, etc.'], ['+4545+12641', 'Asia/Harbin', 'Heilongjiang (except Mohe), Jilin'], ['+2934+10635', 'Asia/Chongqing', 'central China - Sichuan, Yunnan, Guangxi, Shaanxi, Guizhou, etc.'], ['+4348+08735', 'Asia/Urumqi', 'most of Tibet & Xinjiang'], ['+3929+07559', 'Asia/Kashgar', 'west Tibet & Xinjiang']], 'CM': [['+0403+00942', 'Africa/Douala']], 'CL': [['-3327-07040', 'America/Santiago', 'most locations'], ['-2709-10926', 'Pacific/Easter', 'Easter Island & Sala y Gomez']], 'CC': [['-1210+09655', 'Indian/Cocos']], 'CA': [['+4734-05243', 'America/St_Johns', 'Newfoundland Time, including SE Labrador'], ['+4439-06336', 'America/Halifax', 'Atlantic Time - Nova Scotia (most places), PEI'], ['+4612-05957', 'America/Glace_Bay', 'Atlantic Time - Nova Scotia - places that did not observe DST 1966-1971'], ['+4606-06447', 'America/Moncton', 'Atlantic Time - New Brunswick'], ['+5320-06025', 'America/Goose_Bay', 'Atlantic Time - Labrador - most locations'], ['+5125-05707', 'America/Blanc-Sablon', 'Atlantic Standard Time - Quebec - Lower North Shore'], ['+4531-07334', 'America/Montreal', 'Eastern Time - Quebec - most locations'], ['+4339-07923', 'America/Toronto', 'Eastern Time - Ontario - most locations'], ['+4901-08816', 'America/Nipigon', 'Eastern Time - Ontario & Quebec - places that did not observe DST 1967-1973'], ['+4823-08915', 'America/Thunder_Bay', 'Eastern Time - Thunder Bay, Ontario'], ['+6344-06828', 'America/Iqaluit', 'Eastern Time - east Nunavut - most locations'], ['+6608-06544', 'America/Pangnirtung', 'Eastern Time - Pangnirtung, Nunavut'], ['+744144-0944945', 'America/Resolute', 'Eastern Standard Time - Resolute, Nunavut'], ['+484531-0913718', 'America/Atikokan', 'Eastern Standard Time - Atikokan, Ontario and Southampton I, Nunavut'], ['+624900-0920459', 'America/Rankin_Inlet', 'Central Time - central Nunavut'], ['+4953-09709', 'America/Winnipeg', 'Central Time - Manitoba & west Ontario'], ['+4843-09434', 'America/Rainy_River', 'Central Time - Rainy River & Fort Frances, Ontario'], ['+5024-10439', 'America/Regina', 'Central Standard Time - Saskatchewan - most locations'], ['+5017-10750', 'America/Swift_Current', 'Central Standard Time - Saskatchewan - midwest'], ['+5333-11328', 'America/Edmonton', 'Mountain Time - Alberta, east British Columbia & west Saskatchewan'], ['+690650-1050310', 'America/Cambridge_Bay', 'Mountain Time - west Nunavut'], ['+6227-11421', 'America/Yellowknife', 'Mountain Time - central Northwest Territories'], ['+682059-1334300', 'America/Inuvik', 'Mountain Time - west Northwest Territories'], ['+5946-12014', 'America/Dawson_Creek', 'Mountain Standard Time - Dawson Creek & Fort Saint John, British Columbia'], ['+4916-12307', 'America/Vancouver', 'Pacific Time - west British Columbia'], ['+6043-13503', 'America/Whitehorse', 'Pacific Time - south Yukon'], ['+6404-13925', 'America/Dawson', 'Pacific Time - north Yukon']], 'CG': [['-0416+01517', 'Africa/Brazzaville']], 'CF': [['+0422+01835', 'Africa/Bangui']], 'CD': [['-0418+01518', 'Africa/Kinshasa', 'west Dem. Rep. of Congo'], ['-1140+02728', 'Africa/Lubumbashi', 'east Dem. Rep. of Congo']], 'CZ': [['+5005+01426', 'Europe/Prague']], 'CY': [['+3510+03322', 'Asia/Nicosia']], 'CX': [['-1025+10543', 'Indian/Christmas']], 'CR': [['+0956-08405', 'America/Costa_Rica']], 'CV': [['+1455-02331', 'Atlantic/Cape_Verde']], 'CU': [['+2308-08222', 'America/Havana']], 'SZ': [['-2618+03106', 'Africa/Mbabane']], 'SY': [['+3330+03618', 'Asia/Damascus']], 'KG': [['+4254+07436', 'Asia/Bishkek']], 'KE': [['-0117+03649', 'Africa/Nairobi']], 'SR': [['+0550-05510', 'America/Paramaribo']], 'KI': [['+0125+17300', 'Pacific/Tarawa', 'Gilbert Islands'], ['-0308-17105', 'Pacific/Enderbury', 'Phoenix Islands'], ['+0152-15720', 'Pacific/Kiritimati', 'Line Islands']], 'KH': [['+1133+10455', 'Asia/Phnom_Penh']], 'KN': [['+1718-06243', 'America/St_Kitts']], 'KM': [['-1141+04316', 'Indian/Comoro']], 'ST': [['+0020+00644', 'Africa/Sao_Tome']], 'SK': [['+4809+01707', 'Europe/Bratislava']], 'KR': [['+3733+12658', 'Asia/Seoul']], 'SI': [['+4603+01431', 'Europe/Ljubljana']], 'KP': [['+3901+12545', 'Asia/Pyongyang']], 'KW': [['+2920+04759', 'Asia/Kuwait']], 'SN': [['+1440-01726', 'Africa/Dakar']], 'SM': [['+4355+01228', 'Europe/San_Marino']], 'SL': [['+0830-01315', 'Africa/Freetown']], 'SC': [['-0440+05528', 'Indian/Mahe']], 'KZ': [['+4315+07657', 'Asia/Almaty', 'most locations'], ['+4448+06528', 'Asia/Qyzylorda', 'Qyzylorda (Kyzylorda, Kzyl-Orda)'], ['+5017+05710', 'Asia/Aqtobe', 'Aqtobe (Aktobe)'], ['+4431+05016', 'Asia/Aqtau', "Atyrau (Atirau, Gur'yev), Mangghystau (Mankistau)"], ['+5113+05121', 'Asia/Oral', 'West Kazakhstan']], 'KY': [['+1918-08123', 'America/Cayman']], 'SG': [['+0117+10351', 'Asia/Singapore']], 'SE': [['+5920+01803', 'Europe/Stockholm']], 'SD': [['+1536+03232', 'Africa/Khartoum']], 'DO': [['+1828-06954', 'America/Santo_Domingo']], 'DM': [['+1518-06124', 'America/Dominica']], 'DJ': [['+1136+04309', 'Africa/Djibouti']], 'DK': [['+5540+01235', 'Europe/Copenhagen']], 'VG': [['+1827-06437', 'America/Tortola']], 'DE': [['+5230+01322', 'Europe/Berlin']], 'YE': [['+1245+04512', 'Asia/Aden']], 'DZ': [['+3647+00303', 'Africa/Algiers']], 'US': [['+404251-0740023', 'America/New_York', 'Eastern Time'], ['+421953-0830245', 'America/Detroit', 'Eastern Time - Michigan - most locations'], ['+381515-0854534', 'America/Kentucky/Louisville', 'Eastern Time - Kentucky - Louisville area'], ['+364947-0845057', 'America/Kentucky/Monticello', 'Eastern Time - Kentucky - Wayne County'], ['+394606-0860929', 'America/Indiana/Indianapolis', 'Eastern Time - Indiana - most locations'], ['+384038-0873143', 'America/Indiana/Vincennes', 'Eastern Time - Indiana - Daviess, Dubois, Knox & Martin Counties'], ['+410305-0863611', 'America/Indiana/Winamac', 'Eastern Time - Indiana - Pulaski County'], ['+382232-0862041', 'America/Indiana/Marengo', 'Eastern Time - Indiana - Crawford County'], ['+382931-0871643', 'America/Indiana/Petersburg', 'Eastern Time - Indiana - Pike County'], ['+384452-0850402', 'America/Indiana/Vevay', 'Eastern Time - Indiana - Switzerland County'], ['+415100-0873900', 'America/Chicago', 'Central Time'], ['+375711-0864541', 'America/Indiana/Tell_City', 'Central Time - Indiana - Perry County'], ['+411745-0863730', 'America/Indiana/Knox', 'Central Time - Indiana - Starke County'], ['+450628-0873651', 'America/Menominee', 'Central Time - Michigan - Dickinson, Gogebic, Iron & Menominee Counties'], ['+470659-1011757', 'America/North_Dakota/Center', 'Central Time - North Dakota - Oliver County'], ['+465042-1012439', 'America/North_Dakota/New_Salem', 'Central Time - North Dakota - Morton County (except Mandan area)'], ['+394421-1045903', 'America/Denver', 'Mountain Time'], ['+433649-1161209', 'America/Boise', 'Mountain Time - south Idaho & east Oregon'], ['+364708-1084111', 'America/Shiprock', 'Mountain Time - Navajo'], ['+332654-1120424', 'America/Phoenix', 'Mountain Standard Time - Arizona'], ['+340308-1181434', 'America/Los_Angeles', 'Pacific Time'], ['+611305-1495401', 'America/Anchorage', 'Alaska Time'], ['+581807-1342511', 'America/Juneau', 'Alaska Time - Alaska panhandle'], ['+593249-1394338', 'America/Yakutat', 'Alaska Time - Alaska panhandle neck'], ['+643004-1652423', 'America/Nome', 'Alaska Time - west Alaska'], ['+515248-1763929', 'America/Adak', 'Aleutian Islands'], ['+211825-1575130', 'Pacific/Honolulu', 'Hawaii']], 'UY': [['-3453-05611', 'America/Montevideo']], 'YT': [['-1247+04514', 'Indian/Mayotte']], 'UM': [['+1645-16931', 'Pacific/Johnston', 'Johnston Atoll'], ['+2813-17722', 'Pacific/Midway', 'Midway Islands'], ['+1917+16637', 'Pacific/Wake', 'Wake Island']], 'LB': [['+3353+03530', 'Asia/Beirut']], 'LC': [['+1401-06100', 'America/St_Lucia']], 'LA': [['+1758+10236', 'Asia/Vientiane']], 'TV': [['-0831+17913', 'Pacific/Funafuti']], 'TW': [['+2503+12130', 'Asia/Taipei']], 'TT': [['+1039-06131', 'America/Port_of_Spain']], 'TR': [['+4101+02858', 'Europe/Istanbul']], 'LK': [['+0656+07951', 'Asia/Colombo']], 'LI': [['+4709+00931', 'Europe/Vaduz']], 'LV': [['+5657+02406', 'Europe/Riga']], 'TO': [['-2110-17510', 'Pacific/Tongatapu']], 'LT': [['+5441+02519', 'Europe/Vilnius']], 'LU': [['+4936+00609', 'Europe/Luxembourg']], 'LR': [['+0618-01047', 'Africa/Monrovia']], 'LS': [['-2928+02730', 'Africa/Maseru']], 'TH': [['+1345+10031', 'Asia/Bangkok']], 'TF': [['-492110+0701303', 'Indian/Kerguelen']], 'TG': [['+0608+00113', 'Africa/Lome']], 'TD': [['+1207+01503', 'Africa/Ndjamena']], 'TC': [['+2128-07108', 'America/Grand_Turk']], 'LY': [['+3254+01311', 'Africa/Tripoli']], 'VA': [['+415408+0122711', 'Europe/Vatican']], 'VC': [['+1309-06114', 'America/St_Vincent']], 'AE': [['+2518+05518', 'Asia/Dubai']], 'AD': [['+4230+00131', 'Europe/Andorra']], 'AG': [['+1703-06148', 'America/Antigua']], 'AF': [['+3431+06912', 'Asia/Kabul']], 'AI': [['+1812-06304', 'America/Anguilla']], 'VI': [['+1821-06456', 'America/St_Thomas']], 'IS': [['+6409-02151', 'Atlantic/Reykjavik']], 'IR': [['+3540+05126', 'Asia/Tehran']], 'AM': [['+4011+04430', 'Asia/Yerevan']], 'AL': [['+4120+01950', 'Europe/Tirane']], 'AO': [['-0848+01314', 'Africa/Luanda']], 'AN': [['+1211-06900', 'America/Curacao']], 'AQ': [['-7750+16636', 'Antarctica/McMurdo', 'McMurdo Station, Ross Island'], ['-9000+00000', 'Antarctica/South_Pole', 'Amundsen-Scott Station, South Pole'], ['-6734-06808', 'Antarctica/Rothera', 'Rothera Station, Adelaide Island'], ['-6448-06406', 'Antarctica/Palmer', 'Palmer Station, Anvers Island'], ['-6736+06253', 'Antarctica/Mawson', 'Mawson Station, Holme Bay'], ['-6835+07758', 'Antarctica/Davis', 'Davis Station, Vestfold Hills'], ['-6617+11031', 'Antarctica/Casey', 'Casey Station, Bailey Peninsula'], ['-7824+10654', 'Antarctica/Vostok', 'Vostok Station, S Magnetic Pole'], ['-6640+14001', 'Antarctica/DumontDUrville', "Dumont-d'Urville Station, Terre Adelie"], ['-690022+0393524', 'Antarctica/Syowa', 'Syowa Station, E Ongul I']], 'AS': [['-1416-17042', 'Pacific/Pago_Pago']], 'AR': [['-3436-05827', 'America/Argentina/Buenos_Aires', 'Buenos Aires (BA, CF)'], ['-3124-06411', 'America/Argentina/Cordoba', 'most locations (CB, CC, CN, ER, FM, MN, SE, SF)'], ['-2447-06525', 'America/Argentina/Salta', '(SA, LP, NQ, RN)'], ['-2411-06518', 'America/Argentina/Jujuy', 'Jujuy (JY)'], ['-2649-06513', 'America/Argentina/Tucuman', 'Tucuman (TM)'], ['-2828-06547', 'America/Argentina/Catamarca', 'Catamarca (CT), Chubut (CH)'], ['-2926-06651', 'America/Argentina/La_Rioja', 'La Rioja (LR)'], ['-3132-06831', 'America/Argentina/San_Juan', 'San Juan (SJ)'], ['-3253-06849', 'America/Argentina/Mendoza', 'Mendoza (MZ)'], ['-3319-06621', 'America/Argentina/San_Luis', 'San Luis (SL)'], ['-5138-06913', 'America/Argentina/Rio_Gallegos', 'Santa Cruz (SC)'], ['-5448-06818', 'America/Argentina/Ushuaia', 'Tierra del Fuego (TF)']], 'AU': [['-3133+15905', 'Australia/Lord_Howe', 'Lord Howe Island'], ['-4253+14719', 'Australia/Hobart', 'Tasmania - most locations'], ['-3956+14352', 'Australia/Currie', 'Tasmania - King Island'], ['-3749+14458', 'Australia/Melbourne', 'Victoria'], ['-3352+15113', 'Australia/Sydney', 'New South Wales - most locations'], ['-3157+14127', 'Australia/Broken_Hill', 'New South Wales - Yancowinna'], ['-2728+15302', 'Australia/Brisbane', 'Queensland - most locations'], ['-2016+14900', 'Australia/Lindeman', 'Queensland - Holiday Islands'], ['-3455+13835', 'Australia/Adelaide', 'South Australia'], ['-1228+13050', 'Australia/Darwin', 'Northern Territory'], ['-3157+11551', 'Australia/Perth', 'Western Australia - most locations'], ['-3143+12852', 'Australia/Eucla', 'Western Australia - Eucla area']], 'AT': [['+4813+01620', 'Europe/Vienna']], 'AW': [['+1230-06958', 'America/Aruba']], 'IN': [['+2232+08822', 'Asia/Kolkata']], 'AX': [['+6006+01957', 'Europe/Mariehamn']], 'AZ': [['+4023+04951', 'Asia/Baku']], 'IE': [['+5320-00615', 'Europe/Dublin']], 'ID': [['-0610+10648', 'Asia/Jakarta', 'Java & Sumatra'], ['-0002+10920', 'Asia/Pontianak', 'west & central Borneo'], ['-0507+11924', 'Asia/Makassar', 'east & south Borneo, Celebes, Bali, Nusa Tengarra, west Timor'], ['-0232+14042', 'Asia/Jayapura', 'Irian Jaya & the Moluccas']], 'UA': [['+5026+03031', 'Europe/Kiev', 'most locations'], ['+4837+02218', 'Europe/Uzhgorod', 'Ruthenia'], ['+4750+03510', 'Europe/Zaporozhye', "Zaporozh'ye, E Lugansk / Zaporizhia, E Luhansk"], ['+4457+03406', 'Europe/Simferopol', 'central Crimea']], 'QA': [['+2517+05132', 'Asia/Qatar']], 'MZ': [['-2558+03235', 'Africa/Maputo']]}

def find_closest_timezone_choice(cctld,location):
    timezones = cctld_tz[cctld]
    tz = {'timezone':'','distance':1000000}
    pointA = ((location.lon,0,0),(location.lat,0,0))
    for timezone in timezones:
            pointB = convertTimezonePosition(timezone[0])
            distance = points2distance(pointA,pointB)
            if distance < tz['distance']:
                tz['distance'] = distance
                tz['timezone'] = timezone[1]
    return tz['timezone']
