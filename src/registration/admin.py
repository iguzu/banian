from django.contrib import admin
from registration.models import RegistrationProfile
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import ugettext_lazy as _ #@UnresolvedImport


class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('__unicode__', 'activation_key_expired')
    search_fields = ('user__username', 'user__first_name')



class UserAdmin(UserAdmin):
    fieldsets = (
        (_('Basic Info'), {'fields': ('username','name','password',)}),
        (_('Permissions'), {'fields': ('is_staff', 'is_active', 'is_superuser', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (_('Groups'), {'fields': ('groups',)}),
    )
    list_display = ('username', 'name', 'is_staff')
    search_fields = ('username', 'name')
   
    

admin.site.register(RegistrationProfile,RegistrationAdmin)
    