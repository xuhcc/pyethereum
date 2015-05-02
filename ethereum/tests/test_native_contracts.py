from ethereum import tester
from ethereum import utils
from ethereum import native_contracts

"""
test registration

test calling

test creation, how to do it in tester?
"""


class EchoContract(native_contracts.NativeContract):
    address = utils.int_to_addr(2000)

    def __call__(self, ext, msg):
        res, gas, data = 1, msg.gas, msg.data.data
        return res, gas, data


def test_registry():
    reg = native_contracts.registry
    assert tester.a0 not in reg

    native_contracts.registry.register(EchoContract)
    assert isinstance(native_contracts.registry[EchoContract.address], EchoContract)
    native_contracts.registry.unregister(EchoContract)


def test_echo_contract():
    native_contracts.registry.register(EchoContract)
    s = tester.state()
    testdata = 'hello'
    r = s._send(tester.k0, EchoContract.address, 0, testdata)
    assert r['output'] == testdata
    native_contracts.registry.unregister(EchoContract)


def test_native_contract_instances():
    native_contracts.registry.register(EchoContract)

    s = tester.state()

    # last 4 bytes of address are used to reference the contract
    data = EchoContract.address[-4:]
    value = 100

    r = s._send(tester.k0, native_contracts.CreateNativeContractInstance.address, value, data)
    eci_address = r['output']
    # expect to get address of new contract instance
    assert len(eci_address) == 20
    # expect that value was transfered to the new contract
    assert s.block.get_balance(eci_address) == value
    assert s.block.get_balance(native_contracts.CreateNativeContractInstance.address) == 0

    # test the new contract
    data = 'hello'
    r = s.send(tester.k0, eci_address, 0, data)
    assert r == data
    native_contracts.registry.unregister(EchoContract)
