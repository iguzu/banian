from google.appengine.ext import db

class help(db.Model):
    date = db.DateTimeProperty(auto_now_add=True)