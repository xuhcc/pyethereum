"""
WARNING: Below techniques are not officially supported by the Ethereum protocol.


DAPP developers often develop and test contracts in a HLL like python first and then
recode it in Serpent or Solidity.

This module tries to support this approach by providing an infrastructe where
contracts written in Python can be contracts in a live (private) blockchain.


Implementation:
    special.specials is extended
        - to be registry of NativeContracts and their instances
        - implementing __contains__ and __getattr__
    NativeContracts have a address range for their instances

Creating Instances of NativeContracts
    a special CreateNativeContractInstance contract is used to create instances of NativeContracts

Calling Instances of NativeContracts
    for CALL and CALLCODE
    _apply_message queries the registry with the address and
    directly calls the native contract if available (FIXME: how to check existance)


Limitations:
    EXTCODESIZE on an address with a NativeContract
        returns 0

    EXTCODECOPY on an address with a NativeContract
        returns ''
"""

import specials
import utils
import processblock
import vm
import inspect
import abi
from ethereum.utils import encode_int, zpad, big_endian_to_int
import traceback
from slogging import get_logger
log = get_logger('nativecontracts')


class Registry(object):

    """
    NativeContracts:
    0000|000000000000|0123

    NativeContract Instances:
    0000|0123456789ab|0123
    """

    native_contract_address_prefix = '\0' * 16
    native_contract_instance_address_prefix = '\0' * 4

    def __init__(self):
        # register special contracts as defaults
        self.native_contracts = dict(specials.specials)  # address: contract

    def mk_instance_address(self, native_contract, sender, nonce):
        assert native_contract.address.startswith(self.native_contract_address_prefix)
        addr = '\0' * 4
        addr += processblock.mk_contract_address(sender, nonce)[:12]
        addr += native_contract.address[-4:]
        return addr

    def is_instance_address(self, address):
        assert isinstance(address, bytes) and len(address) == 20
        return address.startswith(self.native_contract_instance_address_prefix)

    def address_to_native_contract_class(self, address):
        assert isinstance(address, bytes) and len(address) == 20
        assert self.is_instance_address(address)
        nca = self.native_contract_address_prefix + address[-4:]
        return self.native_contracts[nca]

    def register(self, contract):
        "registers NativeContract classes"
        assert issubclass(contract, NativeContract)
        assert len(NativeContract.address) == 20
        assert NativeContract.address.startswith(self.native_contract_address_prefix)
        self.native_contracts[contract.address] = contract._on_msg
        print("registered native contract {} at address {}".format(contract, contract.address))

    def unregister(self, contract):
        del self.native_contracts[contract.address]

    def __contains__(self, address):
        nca = self.native_contract_address_prefix + address[-4:]
        return self.is_instance_address(address) and nca in self.native_contracts

    def __getitem__(self, address):
        return self.address_to_native_contract_class(address)

# set registry
specials.specials = registry = Registry()


class NativeContract(object):

    address = utils.int_to_addr(1024)

    def __init__(self, ext, msg):
        self._ext = ext
        self._msg = msg
        self.gas = msg.gas

    @classmethod
    def _on_msg(cls, ext, msg):
        print 'IN ON MESSAGE' * 10
        nac = cls(ext, msg)
        try:
            return nac._safe_call()
        except Exception:
            print ('\n' * 2) + traceback.format_exc()
            return 0, msg.gas, []

    def _get_storage_data(self, key):
        return self._ext.get_storage_data(self._msg.to, key)

    def _set_storage_data(self, key, value):
        return self._ext.set_storage_data(self._msg.to, key, value)

    def _safe_call(self):
        return 1, self.gas, []


class CreateNativeContractInstance(NativeContract):

    """
    special contract to create an instance of native contract
    instance refers to instance in the BC.

    msg.data[:4] defines the native contract
    msg.data[4:] is sent as data to the new contract

    called by _apply_message
        value was added to this contract (needs to be moved)
    """

    address = utils.int_to_addr(1024)

    def _safe_call(self):
        assert len(self._msg.sender) == 20
        assert len(self._msg.data.extract_all()) >= 4

        # get native contract
        nc_address = registry.native_contract_address_prefix + self._msg.data.extract_all()[:4]
        print "IN CNCI", nc_address
        if nc_address not in registry:
            return 0, self._msg.gas, b''
        native_contract = registry[nc_address].im_self

        # get new contract address
        if self._ext.tx_origin != self._msg.sender:
            self._ext._block.increment_nonce(self._msg.sender)
        nonce = utils.encode_int(self._ext._block.get_nonce(self._msg.sender) - 1)
        self._msg.to = registry.mk_instance_address(native_contract, self._msg.sender, nonce)
        assert not self._ext.get_balance(self._msg.to)  # must be none existant

        # value was initially added to this contract's address, we need to transfer
        success = self._ext._block.transfer_value(self.address, self._msg.to, self._msg.value)
        assert success
        assert not self._ext.get_balance(self.address)

        # call new instance with additional data
        self._msg.is_create = True
        self._msg.data = vm.CallData(self._msg.data.data[4:], 0, 0)
        res, gas, dat = registry[self._msg.to](self._ext, self._msg)
        assert gas >= 0
        return res, gas, memoryview(self._msg.to).tolist()


registry.register(CreateNativeContractInstance)


#   helper to de/encode method calls

def abi_encode_args(method, args):
    "encode args for method: method_id|data"
    assert issubclass(method.im_class, NativeABIContract), method.im_class
    method_id, arg_types = method.im_class._get_method_abi(method)[:2]
    return zpad(encode_int(method_id), 4) + abi.encode_abi(arg_types, args)


def abi_decode_args(method, data):
    # data is payload w/o method_id
    assert issubclass(method.im_class, NativeABIContract), method.im_class
    arg_types = method.im_class._get_method_abi(method)[1]
    return abi.decode_abi(arg_types, data)


def abi_encode_return_vals(method, vals):
    assert issubclass(method.im_class, NativeABIContract)
    return_types = method.im_class._get_method_abi(method)[2]
    # encode return value to list
    print 'aBI RETURN VALs', repr(vals), return_types
    if isinstance(return_types, list):
        assert isinstance(vals, (list, tuple)) and len(vals) == len(return_types)
    elif vals is None:
        assert return_types is None
        print "in abi return as None"
        return ''
    else:
        vals = (vals, )
        return_types = (return_types, )
    return abi.encode_abi(return_types, vals)


def abi_decode_return_vals(method, data):
    assert issubclass(method.im_class, NativeABIContract)
    return_types = method.im_class._get_method_abi(method)[2]
    if not len(data):
        if return_types is None:
            return None
        return b''
    elif not isinstance(return_types, (list, tuple)):
        return abi.decode_abi((return_types, ), data)[0]
    else:
        return abi.decode_abi(return_types, data)


class NativeABIContract(NativeContract):

    """
    public method must have a signature describing
    - the arguments with their types
    - the return value

    The 'returns' keyword arg indicates, that this is a public abi method

    def afunc(ctx, a='uint16', b='uint16', returns='uint32'):
        return a + b

    The special method NativeABIContract is the constructor
    which is run during creation of the contract and cannot be called afterwards.

    Constructor ?
    """

    __isfrozen = False

    def __init__(self, ext, msg):
        super(NativeABIContract, self).__init__(ext, msg)

        # copy special variables
        self.msg_data = msg.data.extract_all()
        self.msg_sender = msg.sender
        self.msg_gas = property(lambda: self._gas)
        self.msg_value = msg.value

        self.tx_gasprice = ext.tx_gasprice
        self.tx_origin = ext.tx_origin

        self.block_coinbase = ext.block_coinbase
        self.block_timestamp = ext.block_timestamp

        self.block_difficulty = ext.block_difficulty
        self.block_number = ext.block_number
        self.block_gaslimit = ext.block_gas_limit

        self.address = msg.to
        self.get_balance = ext.get_balance
        self.get_block_hash = ext.block_hash

        if self.block_number > 0:
            self.block_prevhash = self.get_block_hash(self.block_number - 1)
        else:
            self.block_prevhash = '\0' * 32

        self.__isfrozen = True

    @property
    def balance(self):  # can change during subcalls
        return self.get_balance(self.address)

    def suicide(self, address):
        assert isinstance(address, bytes) and len(address) == 20
        self._ext.set_balance(address, self.get_balance(address) + self.balance)
        self._ext.set_balance(self.address, 0)
        self._ext.add_suicide(self.address)

    @classmethod
    def _get_method_abi(cls, method):
        m_as = inspect.getargspec(method)
        arg_names = list(m_as.args)[1:]
        if 'returns' not in arg_names:  # indicates, this is an abi method
            return None, None, None
        arg_types = list(m_as.defaults)
        assert len(arg_names) == len(arg_types) == len(set(arg_names))
        assert arg_names.pop() == 'returns'  # must be last element
        return_types = arg_types.pop()  # can be list or multiple
        name = method.__func__.func_name
        m_id = abi.method_id(name, arg_types)
        return (m_id, arg_types, return_types)

    @classmethod
    def _abi_methods(cls):
        methods = []
        for name in dir(cls):
            method = getattr(cls, name)
            if inspect.ismethod(method):
                m_abi = cls._get_method_abi(method)
                if m_abi[0]:
                    methods.append(method)
        return methods

    @classmethod
    def _find_method(cls, method_id):
        for method in cls._abi_methods():
            m_abi = cls._get_method_abi(method)
            if m_abi[0] and m_abi[0] == method_id:
                return method, m_abi[1], m_abi[2]
        return None, None, None

    def default_method(self):
        """
        method which gets called by default if no other method is found
        note: this is no abi method and must make sense from self.msg_data
        """
        return 1, self.gas, []

    def _safe_call(self):
        print "in safe call"
        calldata = self._msg.data.extract_all()
        # get method
        m_id = big_endian_to_int(calldata[:4])  # first 4 bytes encode method_id
        method, arg_types, return_types = self._find_method(m_id)
        if not method:  # 404 method not found
            log.warn('method not found, calling default', methodid=m_id)
            return 1, self.gas, []  # no default methods supported
        # decode abi args
        print 'calldata', method,  calldata[4:], arg_types
        args = abi.decode_abi(arg_types, calldata[4:])
        # call (unbound) method
        try:
            res = method(self, *args)
        except RuntimeError as e:
            log.warn("error in method", method=method, error=e)
            return 0, self.gas, []
        return 1, self.gas, memoryview(abi_encode_return_vals(method, res)).tolist()

    def __setattr__(self, key, value):
        "protect users from abusing properties"
        if self.__isfrozen and not hasattr(self, key):
            raise TypeError("%r must not be extended" % self)
        object.__setattr__(self, key, value)


class ABIEvent(object):

    """
    ABIEvents must implementa function called abi, which defines 
    the canonical typ of the data and whether it is indexed or not. 
    https://github.com/ethereum/wiki/wiki/Ethereum-Contract-ABI#events

    class Shout(nc.ABIEvent):
        arg_types = ['uint16', 'uint16', 'uint16']
        indexed = 1  # up to which arg_index args should be indexed
    """

    arg_types = []
    indexed = 0

    def __init__(self, ctx, *args):
        assert isinstance(ctx, NativeABIContract)
        assert len(self.arg_types) == len(args)

        # topic0 sha3(EventName + signature)
        topics = [abi.method_id(self.__class__.__name__, self.arg_types)]

        # topics 1-n
        for i in range(min(self.indexed, 3)):
            topics.append(abi.encode_abi([arg_types[i]], [args[i]]))

        # remaining non indexed data
        data = abi.encode_abi(arg_types[i:], args[i:])
        ctx._ext.log(ctx.address, topics, data)


#  Tester helpers #####################################


def tester_call_method(state, sender, method, *args):
    data = abi_encode_args(method, args)
    to = method.im_class.address
    r = state._send(sender, to, value=0, evmdata=data)['output']
    return abi_decode_return_vals(method, r)


def tester_nac(state, sender, address, value=0):
    "create an object which acts as a porxy for the contract"
    klass = registry[address].im_self
    assert issubclass(klass, NativeABIContract)

    def mk_method(method):
        def m(s, *args):
            data = abi_encode_args(method, args)
            r = state._send(sender, address, value=value, evmdata=data)['output']
            return abi_decode_return_vals(method, r)
        return m

    class cproxy(object):
        pass
    for m in klass._abi_methods():
        setattr(cproxy, m.__func__.func_name, mk_method(m))

    return cproxy()


def tester_create_native_contract_instance(state, sender, contract, value=0):
    assert issubclass(contract, NativeContract)
    assert NativeABIContract.address in registry
    # last 4 bytes of address are used to reference the contract
    data = contract.address[-4:]
    r = state._send(sender, CreateNativeContractInstance.address, value, data)
    return r['output']


''

""

"""
Storage Objects
Type Safe Wrap Methods

call
address.call

    def init(): - executed upon contract creation, accepts no parameters
    def shared(): - executed before running init and user functions
    def code(): - executed before any user functions

constants

stop


modifiers, @nca.isowner


"""


if __name__ == '__main__':

    nac = NativeABIContract()
