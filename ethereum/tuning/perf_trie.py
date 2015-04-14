import timeit
import numpy
from dis import dis

from ethereum.trie import bin_to_nibbles, nibbles_to_bin
from ethereum.utils import ascii_chr, to_string, to_string2


bin_to_nibbles_in = '3772f07c10e1682f17b777a5645c4acaa3a3d9059df8c799dd0911e795a2aabb'\
    .decode('hex')

bin_to_nibbles_out = [3, 7, 7, 2, 15, 0, 7, 12, 1, 0, 14, 1, 6, 8, 2, 15, 1, 7, 11, 7, 7, 7, 10,
                      5, 6, 4, 5, 12, 4, 10, 12, 10, 10, 3, 10, 3, 13, 9, 0, 5, 9, 13, 15, 8,
                      12, 7, 9, 9, 13, 13, 0, 9, 1, 1, 14, 7, 9, 5, 10, 2, 10, 10, 11, 11]

# timer


def time_compare(func_a, func_b, param):
    def a():
        func_a(param)

    def b():
        func_b(param)
    ta = min(timeit.repeat(a, number=10000))
    tb = min(timeit.repeat(b, number=10000))
    print '%s:%s %.2f:1' % (func_a.__name__, func_b.__name__, ta / tb)
    assert func_a(param) == func_b(param)


# numpy
np16 = numpy.fromiter([16] * 32, dtype=numpy.uint8)


def bin_to_nibbles_np(s):
    a = numpy.repeat(numpy.fromstring(s, dtype=numpy.uint8), 2)
    a = a.reshape((32, 2))
    a = a.transpose(1, 0)
    numpy.divide(a[0], np16, a[0])
    numpy.mod(a[1], np16, a[1])
    a = a.transpose(1, 0)
    return a.reshape(64,).tolist()

time_compare(bin_to_nibbles, bin_to_nibbles_np, bin_to_nibbles_in)


def bin_to_nibbles_mv_generator(s):
    for v in memoryview(s).tolist():
        yield v // 16
        yield v % 16


def bin_to_nibbles_mv(s):
    return list(bin_to_nibbles_mv_generator(s))

time_compare(bin_to_nibbles, bin_to_nibbles_mv, bin_to_nibbles_in)
print

###############################################################


def l_nibbles_to_bin(nibbles):
    res = b''
    for i in range(0, len(nibbles), 2):
        res += chr(16 * nibbles[i] + nibbles[i + 1])
    return res
time_compare(nibbles_to_bin, l_nibbles_to_bin, bin_to_nibbles_out)


def n_nibbles_to_bin(nibbles):
    assert len(nibbles) == 64
    res = bytearray(32)
    for i in range(0, len(nibbles), 2):
        res[i // 2] = 16 * nibbles[i] + nibbles[i + 1]
    return res

time_compare(nibbles_to_bin, n_nibbles_to_bin, bin_to_nibbles_out)

# utils.int_to_bytes #########################################
print


from ethereum.utils import int_to_bytes
import binascii
import ctypes
PyLong_AsByteArray = ctypes.pythonapi._PyLong_AsByteArray
PyLong_AsByteArray.argtypes = [ctypes.py_object,
                               ctypes.c_char_p,
                               ctypes.c_size_t,
                               ctypes.c_int,
                               ctypes.c_int]


def hex_int_to_bytes(lnum):
    return hex(lnum)[2:-1].decode('hex')


def ct_int_to_bytes(lnum):
    a = ctypes.create_string_buffer(lnum.bit_length() // 8 + 1)
    PyLong_AsByteArray(lnum, a, len(a), 0, 1)
    return a.raw.lstrip('\0')

time_compare(int_to_bytes, ct_int_to_bytes, 2**253 - 1)
time_compare(int_to_bytes, hex_int_to_bytes, 2**253 - 1)

print
#######################

# string
time_compare(to_string, str, 'hello')
time_compare(to_string, to_string2, 'hello')
time_compare(to_string, lambda x: x, 'hello')

print 'local str', min(timeit.repeat(str, number=1000000))
print 'imported str', min(timeit.repeat(to_string2, number=1000000))

print


# if raise vs assert

def test_raise(a):
    if a > 1000:
        raise Exception


def test_assert(a):
    assert a < 1000

time_compare(test_raise, test_assert, 999)
