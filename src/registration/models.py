import datetime
import random
import re
import sha

from google.appengine.ext import db
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _ #@UnresolvedImport

SHA1_RE = re.compile('^[a-f0-9]{40}$')




class User(User):
    ''' django User extension '''
    name = db.StringProperty()
    address = db.PostalAddressProperty(required=False)
    country = db.StringProperty()
    addressname = db.StringProperty()
    distance_units = db.IntegerProperty(choices=set([1, 2]),default=1)
    preferred_distance = db.IntegerProperty(default=30)
    time_format = db.IntegerProperty(choices=set([1, 2]),default=1)
    short_addressname = db.StringProperty()
    location = db.GeoPtProperty()
    paypal_id = db.EmailProperty(indexed=False,required=False)
    karma = db.IntegerProperty(default=0)

    def __init__(self,*args,**kwargs):
        super(User,self).__init__(*args,**kwargs)
        if self.distance_units == None:
            self.distance_units = 1
        if self.preferred_distance == None:
            self.preferred_distance = 30
        if self.time_format == None:
            self.time_format = 1



    def __unicode__(self):
        return u"%s (%s)" % (self.username, self.name)

    def mutable(self):
        return True

class RegistrationManager(models.Manager):
    """
    Custom manager for the ``RegistrationProfile`` model.
    
    The methods defined here provide shortcuts for account creation
    and activation (including generation and emailing of activation
    keys), and for cleaning out expired inactive accounts.
    
    """
    def activate_user(self, activation_key):
        """
        Validate an activation key and activate the corresponding
        ``User`` if valid.
        
        If the key is valid and has not expired, return the ``User``
        after activating.
        
        If the key is not valid or has expired, return ``False``.
        
        If the key is valid but the ``User`` is already active,
        return ``False``.
        
        To prevent reactivation of an account which has been
        deactivated by site administrators, the activation key is
        reset to the string constant ``RegistrationProfile.ACTIVATED``
        after successful activation.

        To execute customized logic when a ``User`` is activated,
        connect a function to the signal
        ``registration.signals.user_activated``; this signal will be
        sent (with the ``User`` as the value of the keyword argument
        ``user``) after a successful activation.
        
        """
        from registration.signals import user_activated
        
        # Make sure the key we're trying conforms to the pattern of a
        # SHA1 hash; if it doesn't, no point trying to look it up in
        # the database.
        if SHA1_RE.search(activation_key):
            profile = RegistrationProfile.get_by_key_name("key_"+activation_key)
            if not profile:
                return False
            if not profile.activation_key_expired():
                user = profile.user
                user.is_active = True
                user.put()
                profile.activation_key = RegistrationProfile.ACTIVATED
                profile.put()
                user_activated.send(sender=self.model, user=user) #@UndefinedVariable
                return user
        return False
    
    def create_inactive_user(self, username, password, name, email, domain_override="", 
                             send_email=True):
        """
        Create a new, inactive ``User``, generate a
        ``RegistrationProfile`` and email its activation key to the
        ``User``, returning the new ``User``.
        
        To disable the email, call with ``send_email=False``.

        The activation email will make use of two templates:

        ``registration/activation_email_subject.txt``
            This template will be used for the subject line of the
            email. It receives one context variable, ``site``, which
            is the currently-active
            ``django.contrib.sites.models.Site`` instance. Because it
            is used as the subject line of an email, this template's
            output **must** be only a single line of text; output
            longer than one line will be forcibly joined into only a
            single line.

        ``registration/activation_email.txt``
            This template will be used for the body of the email. It
            will receive three context variables: ``activation_key``
            will be the user's activation key (for use in constructing
            a URL to activate the account), ``expiration_days`` will
            be the number of days for which the key will be valid and
            ``site`` will be the currently-active
            ``django.contrib.sites.models.Site`` instance.

        To execute customized logic once the new ``User`` has been
        created, connect a function to the signal
        ``registration.signals.user_registered``; this signal will be
        sent (with the new ``User`` as the value of the keyword
        argument ``user``) after the ``User`` and
        ``RegistrationProfile`` have been created, and the email (if
        any) has been sent..
        
        """
        from registration.signals import user_registered
        # prepend "key_" to the key_name, because key_names can't start with numbers
        new_user = User(username=username, key_name="_"+username.lower(),name=name,
            email=email, is_active=False)
        new_user.set_password(password)
        new_user.put()
        
        registration_profile = self.create_profile(new_user)
        
        if send_email:
            from django.core.mail import send_mail
            current_site = domain_override
#            current_site = Site.objects.get_current()
            
            subject = render_to_string('registration/activation_email_subject.txt',
                                       { 'site': current_site })
            # Email subject *must not* contain newlines
            subject = ''.join(subject.splitlines())
            
            message = render_to_string('registration/activation_email.txt',
                                       { 'activation_key': registration_profile.activation_key,
                                         'expiration_days': settings.ACCOUNT_ACTIVATION_DAYS,
                                         'site': current_site })
            
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [new_user.email])
        user_registered.send(sender=self.model, user=new_user) #@UndefinedVariable
        return new_user
    
    def create_profile(self, user):
        """
        Create a ``RegistrationProfile`` for a given
        ``User``, and return the ``RegistrationProfile``.
        
        The activation key for the ``RegistrationProfile`` will be a
        SHA1 hash, generated from a combination of the ``User``'s
        username and a random salt.
        
        """
        salt = sha.new(str(random.random())).hexdigest()[:5]
        activation_key = sha.new(salt+user.username).hexdigest()
#        prepend "key_" to the key_name, because key_names can't start with numbers     
        registrationprofile = RegistrationProfile(user=user, activation_key=activation_key, key_name="key_"+activation_key)
        registrationprofile.put()
        return registrationprofile
        
    def delete_expired_users(self):
        """
        Remove expired instances of ``RegistrationProfile`` and their
        associated ``User``s.
        
        Accounts to be deleted are identified by searching for
        instances of ``RegistrationProfile`` with expired activation
        keys, and then checking to see if their associated ``User``
        instances have the field ``is_active`` set to ``False``; any
        ``User`` who is both inactive and has an expired activation
        key will be deleted.
        
        It is recommended that this method be executed regularly as
        part of your routine site maintenance; this application
        provides a custom management command which will call this
        method, accessible as ``manage.py cleanupregistration``.
        
        Regularly clearing out accounts which have never been
        activated serves two useful purposes:
        
        1. It alleviates the ocasional need to reset a
           ``RegistrationProfile`` and/or re-send an activation email
           when a user does not receive or does not act upon the
           initial activation email; since the account will be
           deleted, the user will be able to simply re-register and
           receive a new activation key.
        
        2. It prevents the possibility of a malicious user registering
           one or more accounts and never activating them (thus
           denying the use of those usernames to anyone else); since
           those accounts will be deleted, the usernames will become
           available for use again.
        
        If you have a troublesome ``User`` and wish to disable their
        account while keeping it in the database, simply delete the
        associated ``RegistrationProfile``; an inactive ``User`` which
        does not have an associated ``RegistrationProfile`` will not
        be deleted.
        
        """
        for profile in RegistrationProfile.all():
            if profile.activation_key_expired():
                user = profile.user
                if not user.is_active:
                    user.delete()
                    profile.delete()


class RegistrationProfile(db.Model):
    """
    A simple profile which stores an activation key for use during
    user account registration.
    
    Generally, you will not want to interact directly with instances
    of this model; the provided manager includes methods
    for creating and activating new accounts, as well as for cleaning
    out accounts which have never been activated.
    
    While it is possible to use this model as the value of the
    ``AUTH_PROFILE_MODULE`` setting, it's not recommended that you do
    so. This model's sole purpose is to store data temporarily during
    account registration and activation.
    
    """
    ACTIVATED = u"ALREADY_ACTIVATED"
    
    user = db.ReferenceProperty(User, verbose_name=_('user'))
    activation_key = db.StringProperty(_('activation key'))
    objects = RegistrationManager()
    
    class Meta:
        verbose_name = _('registration profile')
        verbose_name_plural = _('registration profiles')
    
    def __unicode__(self):
        return u"Registration information for %s" % self.user
    
    def activation_key_expired(self):
        """
        Determine whether this ``RegistrationProfile``'s activation
        key has expired, returning a boolean -- ``True`` if the key
        has expired.
        
        Key expiration is determined by a two-step process:
        
        1. If the user has already activated, the key will have been
           reset to the string constant ``ACTIVATED``. Re-activating
           is not permitted, and so this method returns ``True`` in
           this case.

        2. Otherwise, the date the user signed up is incremented by
           the number of days specified in the setting
           ``ACCOUNT_ACTIVATION_DAYS`` (which should be the number of
           days after signup during which a user is allowed to
           activate their account); if the result is less than or
           equal to the current date, the key has expired and this
           method returns ``True``.
        
        """
        expiration_date = datetime.timedelta(days=settings.ACCOUNT_ACTIVATION_DAYS)
        return self.activation_key == RegistrationProfile.ACTIVATED or \
               (self.user.date_joined + expiration_date <= datetime.datetime.now())
    activation_key_expired.boolean = True
