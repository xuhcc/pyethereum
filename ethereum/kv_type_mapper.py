import abi


class TypedStorage(object):

    _prefix = b''
    _set = None
    _get = None

    def __init__(self, value_type='unit8'):
        self._value_type = value_type

    def setup(self, prefix, getter, setter):
        assert isinstance(prefix, bytes)
        self._prefix = prefix
        self._set = setter
        self._get = getter

    def _key(self, k):
        return b'%s:%s' % (self._prefix, k)

    def set(self, k=b'', v=None, value_type=None):
        assert v is not None
        v = abi.encode_abi([value_type or self._value_type], [v])
        self._set(self._key(k), v)

    def get(self, k=b'', value_type=None):
        r = self._get(self._key(k))
        return abi.decode_abi([value_type or self._value_type], r)[0]


class Scalar(TypedStorage):
    pass


class List(TypedStorage):

    def __getitem__(self, i):
        assert isinstance(i, (int, long))
        return self.get(bytes(i))

    def __setitem__(self, i, v):
        assert isinstance(i, (int, long))
        self.set(bytes(i), v)
        if i >= len(self):
            self.set(b'__len__', i + 1, value_type='uint32')

    def __len__(self):
        return self.get(b'__len__', value_type='uint32')

    def append(self, v):
        self[len(self)] = v

    def __contains__(self, idx):
        raise NotImplementedError()


class Dict(List):

    def __getitem__(self, k):
        assert isinstance(k, bytes), k
        return self.get(k)

    def __setitem__(self, k, v):
        assert isinstance(k, bytes)
        self.set(k, v)

    def __contains__(self, k):
        raise NotImplementedError('unset keys return zero as a default')


class DBdized(object):

    storage = dict(a=Scalar('uint32'),
                   b=List('uint16'),
                   c=Dict('uint32')
                   )

    def __init__(self):
        self.db = dict()
        for k, ts in self.storage.items():
            ts.setup(k,  self.dbget, self.dbset)
            if isinstance(ts, (List, Dict)):
                setattr(self, k, ts)
            else:
                assert isinstance(ts, Scalar)

                def _mk_property(skalar):
                    return property(lambda s: skalar.get(), lambda s, v: skalar.set(v=v))
                setattr(self.__class__, k, _mk_property(ts))

    def dbget(self, k):
        return self.db.get(k, b'\0' * 32)

    def dbset(self, k, v):
        self.db[k] = v


def test_it():

    dbd = DBdized()

    # skalar
    assert 'a' not in dbd.db
    assert dbd.a == 0
    dbd.a = 1
    assert dbd.a == 1
    assert dbd.db['a:'] == abi.encode_abi(['uint32'], [1])

    dbd.a = 2
    assert dbd.a == 2

    # list
    assert isinstance(dbd.b, List)
    assert dbd.b[0] == 0
    dbd.b[0] = 10
    assert dbd.b[0] == 10
    assert dbd.db['b:0'] == abi.encode_abi(['uint16'], [10])

    dbd.b[1000] = 12
    assert dbd.db['b:1000'] == abi.encode_abi(['uint16'], [12])
    assert dbd.b[1000] == 12

    assert len(dbd.b) == 1001
    dbd.b[1000] = 66
    assert dbd.b[1000] == 66
    assert len(dbd.b) == 1001

    dbd.b.append(99)
    assert len(dbd.b) == 1002
    dbd.b.append(99)
    assert len(dbd.b) == 1003

    # mapping
    key = b'test'
    assert dbd.c[key] == 0
    dbd.c[key] = 33
    assert dbd.c[key] == 33
    dbd.c[key] = 66
    assert dbd.c[key] == 66

    print dbd.db


if __name__ == '__main__':
    test_it()
