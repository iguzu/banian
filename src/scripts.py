
## Delete all seats...
from banian import models
from google.appengine.ext import db


seats = models.Seat.all().fetch(500)
while(seats):
    to_delete = []
    for seat in seats:
        to_delete.append(seat.key())
    db.delete(to_delete)
    seats = models.Seat.all().fetch(500)

