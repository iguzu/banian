
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



## Add new properties on existing entities (property default)

from banian import models
from google.appengine.ext import db

events = models.Event.all().fetch(500)
for e in events:
    if e.first_representation() != 'Draft':
        e.visibility = 'Published'
    else:
        e.visibility = 'Draft'
    e.private = False
    e.put()

