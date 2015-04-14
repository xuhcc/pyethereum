import os
import rlp
from ethereum.chain import Chain
from ethereum.blocks import Block
import ethereum.db as db
from ethereum.slogging import configure
configure(':trace')

fn = os.path.join(os.path.dirname(__file__), 'blocks.fromthewire.hex.rlp')


def import_blocks(num=10):
    chain = Chain(db.DB())
    total_gas = 0
    total_txs = 0
    i = 0
    for rlp_data in open(fn):

        # for bh, txs, u in rlp.decode(rlp_data.strip().decode('hex')):
        #     i += 1
        #     total_txs += len(txs)
        #     print i, len(txs), total_txs

        for block_data in rlp.decode_lazy(rlp_data.strip().decode('hex')):
            i += 1
            assert len(block_data) == 3
            block = Block.deserialize(block_data, db=chain.db)
            total_gas += block.gas_used
            print block, block.gas_used, total_gas
            chain.add_block(block)
            if block.number == num:
                break
        if block.number == num:
            break


if __name__ == '__main__':
    import_blocks(100)
