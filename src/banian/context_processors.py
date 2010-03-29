'''
Created on Dec 23, 2009

@author: sboire
'''

from django.core.urlresolvers import reverse
from google.appengine.api import memcache
import logging

class Menu:

    def __init__(self,name,url,sub_menu=[],sibblings=[],description='',):
        self.name = name
        self.url = url
        self.description = description
        self.sub_menu = sub_menu

menu_autenticated = [
 Menu('Home',reverse('banian.views.default')),
 Menu('Tickets',reverse('banian.views.search_events'),
      sub_menu=[Menu('Search',reverse('banian.views.search_events')),
                Menu('My Tickets',reverse('banian.views.user_events')),
                Menu('My Transactions',reverse('banian.views.transactions')),]),
 Menu('Events',reverse('banian.views.events'),
      sub_menu=[Menu('My Events',reverse('banian.views.events')),
                Menu('Ticket Validation',reverse('banian.views.validation_list')),]),
 Menu('My Account',reverse('banian.views.settings'),
      sub_menu=[Menu('Account Settings',reverse('banian.views.settings')),
                Menu('Change Password',reverse('registration.views.password_change')),]),
 Menu('Log Out',reverse('django.contrib.auth.views.logout')),
 Menu('Help','/help/'),            
 ]

menu_anonymous = [Menu('Home',reverse('banian.views.default')),
                      Menu('Register',reverse('registration.views.register')),
                      Menu('Help','/help/'),      
                      ]

def find_menu(menu,path):
    for item in menu:
        if item.url == path:
            return menu.index(item)
        elif item.sub_menu:
            index = find_menu(item.sub_menu,path)
            if index != None:
                return menu.index(item)
    return None

def menu(request):
    if request.user.is_authenticated():
        menu = menu_autenticated
    else:
        menu = menu_anonymous
    sub_menu = None; current_sub_menu = None
    current_menu = find_menu(menu,request.path)
    if current_menu != None:
        memcache.set('%s-current_menu' % request.session.session_key,current_menu)
        sub_menu = menu[current_menu].sub_menu
        if sub_menu:
            current_sub_menu = find_menu(sub_menu,request.path)
            if current_sub_menu != None:
                memcache.set('%s-current_sub_menu' % request.session.session_key,current_sub_menu)
    else:
        current_menu = memcache.get('%s-current_menu' % request.session.session_key)
        if current_menu != None:
            sub_menu = menu[current_menu].sub_menu
            current_sub_menu = memcache.get('%s-current_sub_menu' % request.session.session_key)
    return {'menu':menu,'current_menu':current_menu,'sub_menu':sub_menu,'current_sub_menu':current_sub_menu,}
