
class DBType(object):

    _prefix = b''
    _set = None
    _get = None

    def __init__(self, value_type='unit32'):
        self._value_type = value_type

    def _key(self, k):
        return '%s:%s' % (self._prefix, k)

    def set(self, k, v):
        self._set(self._key(k), v)

    def get(self, k):
        return self._get(self._key(k))


class Scalar(DBType):

    def set(self, value):
        self._set(self._prefix, value)

    def get(self):
        return self._get(self._prefix)


class List(DBType):

    def __getitem__(self, i):
        return self.get(str(i))

    def __setitem__(self, i, v):
        self.set(str(i), v)


class Dict(List):
    pass


class A(object):

    storage = dict(a=Scalar('uint32'),
                   b=List('address'),
                   c=Dict('uint32')
                   )

    def __init__(self):
        self.db = dict()
        for k, v in self.storage.items():
            v._get = self.dbget
            v._set = self.dbset
            v._prefix = k
            if isinstance(v, (List, Dict)):
                setattr(self, k, v)
            else:
                assert isinstance(v, Scalar)
                setattr(self, k, property(v.get, v.set))

    def dbget(self, k):
        print 'getting', k
        return self.db.get(k, None)

    def dbset(self, k, v):
        print 'setting', k, v
        self.db[k] = v


a = A()

print a.a
a.a = 1
print a.a
a.a = 2
print a.a

print 'b:', a.b

print a.b[0]
a.b[0] = 10
print a.b[0]

a.b[1000] = 12
print a.b[1000]
print a.db
