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
        self.native_contracts[contract.address] = contract()
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

    def __init__(self):  # instance is created during registration Registry.register
        pass

    def __call__(self, ext, msg):
        self.ext = ext
        self.msg = msg
        return self._call()

    def _get_storage_data(self, key):
        return self.ext.get_storage_data(self.msg.to, key)

    def _set_storage_data(self, key, value):
        return self.ext.set_storage_data(self.msg.to, key, value)

    def _call(self):
        success = 1
        gas_used = 0
        output = []
        return success, gas_used, output


class CreateNativeContractInstance(NativeContract):

    """
    special contract to create an instance of native contract
    msg.data[:4] defines the native contract
    msg.data[4:] is sent as data to the new contract

    called by _apply_message
        value was added to this contract (needs to be moved)
    """

    address = utils.int_to_addr(1024)

    def __call__(self, ext, msg):
        assert len(msg.sender) == 20
        assert len(msg.data.extract_all()) >= 4

        # get native contract
        nc_address = registry.native_contract_address_prefix + msg.data.extract_all()[:4]
        print "IN CNCI", nc_address
        if nc_address not in registry:
            return 0, msg.gas, b''
        native_contract = registry[nc_address]

        # get new contract address
        if ext.tx_origin != msg.sender:
            ext._block.increment_nonce(msg.sender)
        nonce = utils.encode_int(ext._block.get_nonce(msg.sender) - 1)
        msg.to = registry.mk_instance_address(native_contract, msg.sender, nonce)
        assert not ext.get_balance(msg.to)  # must be none existant

        # value was initially added to this contract's address, we need to transfer
        success = ext._block.transfer_value(self.address, msg.to, msg.value)
        assert success
        assert not ext.get_balance(self.address)

        # call new instance with additional data
        msg.is_create = True
        msg.data = vm.CallData(msg.data.data[4:], 0, 0)
        res, gas, dat = registry[msg.to](ext, msg)
        assert gas >= 0
        return res, gas, memoryview(msg.to).tolist()


registry.register(CreateNativeContractInstance)


class NativeABIEvent(object):

    def __init__(self, ext, msg,   *args):
        ext.log(msg.to, topics, data)
import inspect
import abi
from ethereum.utils import encode_int, zpad, big_endian_to_int, is_numeric, is_string
import traceback


class FrozenClass(object):
    __isfrozen = False

    def __setattr__(self, key, value):
        if self.__isfrozen and not hasattr(self, key):
            raise TypeError("%r is a frozen class" % self)
        object.__setattr__(self, key, value)

    def _freeze(self):
        self.__isfrozen = True


def abi_encode_args(method, args):
    pass


def abi_decode_args(method, data):
    pass


def abi_encode_return_vals(method, vals):
    pass


def abi_decode_return_vals(method, data):
    pass


class NativeABIContract(NativeContract):

    """
    The special method NativeABIContract is the constructor
    which is run during creation of the contract and cannot be called afterwards.

    Constructor ?


    """

    events = []

    def __init__(self):
        self._setup_abi()
        self._method_by_id = dict()

    def _setup_abi(self):
        for name in dir(self):
            method = getattr(self, name)
            if not name.startswith('_') and inspect.ismethod(method):
                m_as = inspect.getargspec(method)
                arg_names = list(m_as.args)
                decode_types = list(m_as.defaults)
                assert len(arg_names) == len(decode_types) == len(set(arg_names))
                if 'returns' in arg_names:
                    assert arg_names.pop() == 'returns'
                    encode_types = decode_types.pop()  # can be list or multiple
                else:
                    encode_types = []
                m_id = abi.method_id(name, decode_types)
                self._method_by_id[m_id] = (name, method, decode_types, encode_types)

    def __call__(self, ext, msg):
        try:
            return self._safe_call(ext, msg)
        except Exception:
            print traceback.format_exc()
            return 0, msg.gas, []

    def _safe_call(self, ext, msg):
        super(NativeABIContract, self).__call__(ext, msg)
        calldata = msg.data.extract_all()
        # get method
        m_id = big_endian_to_int(calldata[:4])  # first 4 bytes encode method_id
        if m_id not in self._method_by_id:  # 404 method not found
            return 0, msg.gas, []           # no default methods supported
        # decode abi args
        name, method, decode_types, encode_types = self._method_by_id[m_id]
        args = abi.decode_abi(decode_types, calldata[4:])
        # call method
        res = self._method_by_id[m_id](args)
        # encode return value
        if isinstance(encode_types, list):
            assert isinstance(res, (list, tuple)) and len(res) == len(encode_types)
        else:
            res = (res, )
            encode_types = (encode_types, )
        return 1, msg.gas, abi.encode_abi(encode_types, res)

    def _decode_method_args(self, method):
        pass

    def encode_for_method(self, )

    def with_tester(self, state):
        """

        """


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
