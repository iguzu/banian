"""
Views which allow users to create and activate accounts.

"""

from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from registration.forms import UserRegistrationForm, UserAuthenticationForm
from django.contrib.auth.forms import PasswordChangeForm
from registration.models import RegistrationProfile
from recaptcha.client import captcha
from django.contrib.auth.models import Message
from django.utils.translation import ugettext #@UnresolvedImport
from django.contrib.sites.models import Site, RequestSite
from django.views.decorators.cache import never_cache
from django.contrib.auth import REDIRECT_FIELD_NAME
import logging

def activate(request, activation_key,
             template_name='registration/activate.html',
             extra_context=None):
    """
    Activate a ``User``'s account from an activation key, if their key
    is valid and hasn't expired.
    
    By default, use the template ``registration/activate.html``; to
    change this, pass the name of a template as the keyword argument
    ``template_name``.
    
    **Required arguments**
    
    ``activation_key``
       The activation key to validate and use for activating the
       ``User``.
    
    **Optional arguments**
       
    ``extra_context``
        A dictionary of variables to add to the template context. Any
        callable object in this dictionary will be called to produce
        the end result which appears in the context.
    
    ``template_name``
        A custom template to use.
    
    **Context:**
    
    ``account``
        The ``User`` object corresponding to the account, if the
        activation was successful. ``False`` if the activation was not
        successful.
    
    ``expiration_days``
        The number of days for which activation keys stay valid after
        registration.
    
    Any extra variables supplied in the ``extra_context`` argument
    (see above).
    
    **Template:**
    
    registration/activate.html or ``template_name`` keyword argument.
    
    """
    activation_key = activation_key.lower() # Normalize before trying anything with it.
    account = RegistrationProfile.objects.activate_user(activation_key)
    if extra_context is None:
        extra_context = {}
    context = RequestContext(request)
    for key, value in extra_context.items():
        context[key] = callable(value) and value() or value
    context['nologin'] = True
    return render_to_response(template_name,
                              { 'account': account,
                                'expiration_days': settings.ACCOUNT_ACTIVATION_DAYS, },
                              context_instance=context)


def register(request, success_url=None,
             form_class=UserRegistrationForm,
             template_name='registration/registration_form.html',
             extra_context=None):
    """
    Allow a new user to register an account.
    
    Following successful registration, issue a redirect; by default,
    this will be whatever URL corresponds to the named URL pattern
    ``registration_complete``, which will be
    ``/accounts/register/complete/`` if using the included URLConf. To
    change this, point that named pattern at another URL, or pass your
    preferred URL as the keyword argument ``success_url``.
    
    By default, ``registration.forms.RegistrationForm`` will be used
    as the registration form; to change this, pass a different form
    class as the ``form_class`` keyword argument. The form class you
    specify must have a method ``save`` which will create and return
    the new ``User``.
    
    By default, use the template
    ``registration/registration_form.html``; to change this, pass the
    name of a template as the keyword argument ``template_name``.
    
    **Required arguments**
    
    None.
    
    **Optional arguments**
    
    ``form_class``
        The form class to use for registration.
    
    ``extra_context``
        A dictionary of variables to add to the template context. Any
        callable object in this dictionary will be called to produce
        the end result which appears in the context.
    
    ``success_url``
        The URL to redirect to on successful registration.
    
    ``template_name``
        A custom template to use.
    
    **Context:**
    
    ``form``
        The registration form.
    
    Any extra variables supplied in the ``extra_context`` argument
    (see above).
    
    **Template:**
    
    registration/registration_form.html or ``template_name`` keyword
    argument.
    
    """
    CaptchaError = None
    if request.method == 'POST':
        form = form_class(data=request.POST, files=request.FILES)
        domain_override = request.get_host()
        challenge = request.POST.get('recaptcha_challenge_field')
        response  = request.POST.get('recaptcha_response_field')
        remoteip  = request.META['REMOTE_ADDR']
        cResponse = captcha.submit(challenge,response,"6LcoxQcAAAAAAIm3YRGvW7hr2kmgxoXONKDf_Mi9",remoteip)
        if not cResponse.is_valid :
            CaptchaError = cResponse.error_code
            
        if (form.is_valid() and cResponse.is_valid):
            form.save(domain_override)
            # success_url needs to be dynamically generated here; setting a
            # a default value using reverse() will cause circular-import
            # problems with the default URLConf for this application, which
            # imports this file.
            return HttpResponseRedirect(success_url or reverse('registration_complete'))
    else:
        form = form_class()
    
    if extra_context is None:
        extra_context = {'nologin':True}
    context = RequestContext(request)
    for key, value in extra_context.items():
        context[key] = callable(value) and value() or value
    chtml = captcha.displayhtml(public_key = "6LcoxQcAAAAAAHdG6W6ojYccJckkkMLg5myaLUw9",use_ssl = False,error = CaptchaError)
    return render_to_response(template_name,
                              { 'form': form, 'captchahtml' : chtml, 'captchaerror' : CaptchaError },
                              context_instance=context)

@login_required
def password_change(request, template_name='registration/password_change_form.html',
                    post_change_redirect=None):
    if post_change_redirect is None:
        post_change_redirect = reverse('banian.views.default')
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            if request.user.is_authenticated():
                Message(user=request.user, message=ugettext("password was updated successfully.")).put()

            return HttpResponseRedirect(post_change_redirect)
    else:
        form = PasswordChangeForm(request.user)
    return render_to_response(template_name, {
        'form': form,
    }, context_instance=RequestContext(request))


def login(request, template_name='registration/login.html', redirect_field_name=REDIRECT_FIELD_NAME):
    logging.debug(request.POST)
    "Displays the login form and handles the login action."
    redirect_to = request.REQUEST.get(redirect_field_name, '')
    if request.method == "POST":
        form = UserAuthenticationForm(data=request.POST)
        if form.is_valid():
            # Light security check -- make sure redirect_to isn't garbage.
            if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
                redirect_to = settings.LOGIN_REDIRECT_URL
            from django.contrib.auth import login
            login(request, form.get_user())
            if request.session.test_cookie_worked():
                request.session.delete_test_cookie()
            return HttpResponseRedirect(redirect_to)
    else:
        form = UserAuthenticationForm(request)
    request.session.set_test_cookie()
    if Site._meta.installed: #@UndefinedVariable
        current_site = Site.objects.get_current()
    else:
        current_site = RequestSite(request)
    return render_to_response(template_name, {
        'form': form,
        redirect_field_name: redirect_to,
        'site': current_site,
        'site_name': current_site.name,
        'nologin':True,
    }, context_instance=RequestContext(request))
login = never_cache(login)


