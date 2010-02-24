from django.contrib import admin
from django.contrib.admin.options import ModelAdmin


from banian.models import Venue, Event, Seat, SeatGroup, TicketClass, \
     Transfer, SeatConfiguration,Image, Representation, Ticket, \
     UserEvent,Transaction


class VenueAdmin(ModelAdmin):
    pass

class EventAdmin(ModelAdmin):
    pass

class SeatAdmin(ModelAdmin):
    pass    

class SeatGroupAdmin(ModelAdmin):
    pass

class SeatConfigurationAdmin(ModelAdmin):
    pass

class SeatClassAdmin(ModelAdmin):
    pass

class TransferAdmin(ModelAdmin):
    pass

class ImageAdmin(ModelAdmin):
    pass
        
class RepresentationAdmin(ModelAdmin):
    pass        

class TicketAdmin(ModelAdmin):
    pass

class UserEventAdmin(ModelAdmin):
    pass

class TransactionAdmin(ModelAdmin):
    pass

class QuickEventAdmin(ModelAdmin):
    pass
     
admin.site.register(Event, EventAdmin)
admin.site.register(Venue, VenueAdmin)
admin.site.register(Seat, SeatAdmin)
admin.site.register(SeatGroup, SeatGroupAdmin)
admin.site.register(TicketClass, SeatClassAdmin)
admin.site.register(Transfer, TransferAdmin)
admin.site.register(SeatConfiguration, SeatConfigurationAdmin)
admin.site.register(Image, ImageAdmin)
admin.site.register(Representation, RepresentationAdmin)
admin.site.register(Ticket, TicketAdmin)
admin.site.register(UserEvent, UserEventAdmin)
admin.site.register(Transaction, TransactionAdmin)
