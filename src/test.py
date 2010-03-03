#@PydevCodeAnalysisIgnore
## popo
import array
import time
import datetime
import gaepytz
class Foo:
  x = 0
  y = 1
  def foo(cls):
    print "classmethod: hello"
    print cls.x
  foo = classmethod(foo)
  def bar():
    print "staticmethod: hello"
    print Foo.x
  bar = staticmethod(bar)
# haha



class tata(object):
    x = 10
    y = 11

def f(tata):
    tata.x= 20
    return tata

if __name__ == "__main__":
    a = {'a':1,'b':2}
    
    b = array.array('i')
    b.append(10)
    for item in b:
        item = 11
    print b
    
    t2 = time.time()
    print(t2)
    d2 = datetime.datetime.utcfromtimestamp(t2).replace(tzinfo=gaepytz.utc).astimezone(gaepytz.timezone('America/Montreal'))
    print(d2)
