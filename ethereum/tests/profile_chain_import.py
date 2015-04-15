import os
import rlp
import time
from ethereum.chain import Chain
from ethereum.blocks import Block
import ethereum.db as db
from ethereum.utils import sha3_call_counter, sha3
import cProfile
import pstats
import StringIO

from ethereum.slogging import get_logger, configure_logging, get_configuration
logger = get_logger()
import sys
from ethereum.slogging import configure
configure(':info')

fn = os.path.join(os.path.dirname(__file__), 'blocks.fromthewire.hex.rlp')


def iter_blocks(num=100):
    longest = 0
    i = 0
    for rlp_data in open(fn):
        for block_data in rlp.decode_lazy(rlp_data.strip().decode('hex')):
            i += 1
            if i == num:
                break
        if i == num:
            break
    print i, 'blocks scanned'


def decode_blocks(num=100):
    blocks = []
    for rlp_data in open(fn):
        blks = rlp.decode(rlp_data.strip().decode('hex'))
        assert len(blks[0]) == 3
        blocks.append(blks)
        if len(blocks) >= num:
            break
    print len(blocks), 'blocks scanned'
    return blocks


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


def run():
    # import_blocks(100)
    # iter_blocks(1000000)
    return decode_blocks(100)

if __name__ == '__main__':
    if len(sys.argv) == 2:
        pr = cProfile.Profile()
        blocks = run()
        pr.enable()
        rlp.encode(blocks)
        pr.disable()
        s = StringIO.StringIO()
        sortby = 'tottime'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats(50)
        print s.getvalue()
    else:
        st = time.time()
        run()
        print
        print 'took total', time.time() - st
        print 'took w/o sha3', time.time() - st - sha3_call_counter[3]
