#@PydevCodeAnalysisIgnore
## popo
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
    if 'a' in a:
        


#comment yo yo to
    
    