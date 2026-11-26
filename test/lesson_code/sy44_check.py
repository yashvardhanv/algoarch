"""Runs the python code blocks from data/new_lessons/sy44.md against a naive matcher that keeps every resting order
in one list and re-sorts on (price, arrival) for every fill; then checks snapshot-and-replay recovery and two
replicas producing identical output, and the worked example and drill answers."""
import re, sys, random, copy
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
OrderBook, run, recover = ns['OrderBook'], ns['run'], ns['recover']
random.seed(44)

class Naive:
    def __init__(self):
        self.rest = []            # dicts: oid, side, price, qty, t
        self.t = 0
        self.seen = set()         # every id ever accepted: ids are never reused
    def _key(self, o):
        return (o['price'] if o['side'] == 'S' else -o['price'], o['t'])
    def submit(self, oid, side, qty, price=None):
        if oid in self.seen or qty <= 0 or (price is not None and (type(price) is not int or price <= 0)):
            raise ValueError('rejected')
        self.seen.add(oid)
        trades = []
        while qty > 0:
            opp = sorted((o for o in self.rest if o['side'] != side), key=self._key)
            if not opp:
                break
            o = opp[0]
            if price is not None and ((side == 'B' and o['price'] > price) or (side == 'S' and o['price'] < price)):
                break
            f = min(qty, o['qty'])
            trades.append((oid, o['oid'], o['price'], f))
            qty -= f
            o['qty'] -= f
            if o['qty'] == 0:
                self.rest.remove(o)
        if qty > 0 and price is not None:
            self.t += 1
            self.rest.append({'oid': oid, 'side': side, 'price': price, 'qty': qty, 't': self.t})
        return trades
    def cancel(self, oid):
        for o in self.rest:
            if o['oid'] == oid:
                self.rest.remove(o)
                return True
        return False
    def amend(self, oid, q):
        for o in self.rest:
            if o['oid'] == oid and q > 0:
                if q > o['qty']:
                    self.t += 1
                    o['t'] = self.t           # an increase loses time priority
                o['qty'] = q
                return True
        return False
    def depth(self, side, n=5):
        lv = {}
        for o in self.rest:
            if o['side'] == side:
                lv[o['price']] = lv.get(o['price'], 0) + o['qty']
        return sorted(lv.items(), reverse=(side == 'B'))[:n]
    def resting(self):
        return sorted((o['oid'], o['side'], o['price'], o['qty']) for o in self.rest)

def resting(book):
    return sorted((oid, side, price, q) for side in 'BS' for price, lv in book.levels[side].items()
                  for oid, q in lv.items())

def random_log(n, n_prices):
    log, live, oid = [], [], 0
    for seq in range(n):
        r = random.random()
        if r < 0.6 or not live:
            oid += 1
            side = random.choice('BS')
            if random.random() < 0.15:
                args = ('o%d' % oid, side, random.randint(1, 40))                       # market
            else:
                args = ('o%d' % oid, side, random.randint(1, 30), random.randint(100, 100 + n_prices))
            if random.random() < 0.02:
                args = (args[0], side, 0) + args[3:]                                   # rejected: qty 0
            log.append((seq, 'new', args))
            live.append('o%d' % oid)
            if random.random() < 0.02 and live:
                log.append((seq + 0.5, 'new', (random.choice(live), 'B', 5, 101)))      # duplicate id
        elif r < 0.8:
            log.append((seq, 'cancel', (random.choice(live),)))
        else:
            log.append((seq, 'amend', (random.choice(live), random.randint(1, 40))))
    return log

steps = 0
for trial in range(150):
    book, naive = OrderBook(), Naive()
    log = random_log(random.randint(1, 200), random.choice([1, 3, 8]))
    for seq, cmd, args in log:
        if cmd == 'new':
            try:
                got = book.submit(*args)
            except ValueError:
                got = 'rej'
            try:
                want = naive.submit(*args)
            except ValueError:
                want = 'rej'
            assert got == want, (seq, args, got, want)
        elif cmd == 'cancel':
            assert book.cancel(*args) == naive.cancel(*args)
        else:
            assert book.amend(*args) == naive.amend(*args)
        assert resting(book) == naive.resting(), seq
        for side in 'BS':
            assert book.depth(side) == naive.depth(side)
            heap = book.prices[side]
            assert len(heap) == len(set(heap)), 'duplicate prices in the heap'
        bb, ba = book._best('B'), book._best('S')            # never a crossed book
        assert bb is None or ba is None or bb < ba
        steps += 1

    # determinism: a replica fed the same log produces identical output
    b1, out1 = run(log)
    b2, out2 = run(log)
    nv = Naive()
    for seq, cmd, args in log:                                 # run() reports a market order's dropped remainder
        if cmd == 'new':
            try:
                fills = nv.submit(*args)
            except ValueError:
                continue
            want = args[2] - sum(f[3] for f in fills)
            got = [e[2] for e in out1 if e[0] == seq and e[1] == 'cancelled']
            assert got == ([(args[0], want)] if len(args) == 3 and want > 0 else []), (seq, args, got)
        elif cmd == 'cancel':
            nv.cancel(*args)
        else:
            nv.amend(*args)
    assert out1 == out2 and resting(b1) == resting(b2)
    # recovery: snapshot after a prefix, replay the rest
    if log:
        cut = random.randint(0, len(log))
        from_seq = log[cut][0] if cut < len(log) else log[-1][0] + 1
        snap, head = run(log[:cut])
        b3, tail = recover(snap, log, from_seq)
        assert head + tail == out1 and resting(b3) == resting(b1)

# worked example in the lesson
bk = OrderBook()
bk.submit('A1', 'S', 5, 101); bk.submit('A2', 'S', 3, 101); bk.submit('A3', 'S', 10, 102)
assert bk.submit('B1', 'B', 7, 101) == [('B1', 'A1', 101, 5), ('B1', 'A2', 101, 2)]
assert bk.levels['S'][101]['A2'] == 1 and bk.levels['S'][102]['A3'] == 10
assert bk.submit('M1', 'B', 4) == [('M1', 'A2', 101, 1), ('M1', 'A3', 102, 3)]
assert bk.levels['S'][102]['A3'] == 7 and 'M1' not in bk.orders
assert bk.submit('B2', 'B', 5, 100) == [] and bk.depth('B') == [(100, 5)]
bk.submit('A4', 'S', 2, 102)
assert bk.amend('A3', 9) and list(bk.levels['S'][102]) == ['A4', 'A3']
assert bk.amend('A4', 1) and list(bk.levels['S'][102]) == ['A4', 'A3']        # reduction keeps its place
assert bk.submit('M2', 'B', 100) == [('M2', 'A4', 102, 1), ('M2', 'A3', 102, 9)] and not bk.levels['S']
assert bk.cancel('A3') is False and bk.cancel('B2') is True and bk.cancel('B2') is False

# heap stays bounded: 10,000 rest-and-cancel cycles at one price behind the best bid
bk = OrderBook()
bk.submit('best', 'B', 1, 105)
for i in range(10000):
    bk.submit('c%d' % i, 'B', 1, 100)
    bk.cancel('c%d' % i)
assert len(bk.prices['B']) <= 2, len(bk.prices['B'])
# ids are never reused, even after a fill or a cancel; prices must be integer ticks
bk = OrderBook()
bk.submit('a', 'S', 1, 100); bk.submit('b', 'B', 1, 100)       # a and b fully filled
for bad in (('a', 'S', 1, 100), ('b', 'B', 1, 99), ('f', 'B', 1, 100.5)):
    try:
        bk.submit(*bad)
        raise AssertionError('accepted %r' % (bad,))
    except ValueError:
        pass
bk.submit('c', 'S', 2, 101); bk.cancel('c')
try:
    bk.submit('c', 'S', 2, 101)
    raise AssertionError('cancelled id reused')
except ValueError:
    pass
_, out = run([(0, 'new', ('s1', 'S', 3, 100)), (1, 'new', ('m1', 'B', 5))])
assert out[-1] == (1, 'cancelled', ('m1', 2)) and out[-2] == (1, 'trades', [('m1', 's1', 100, 3)])

# drill 1
bk = OrderBook()
bk.submit('X', 'S', 50, 101); bk.submit('Y', 'S', 30, 101); bk.submit('Z', 'S', 20, 100)
assert bk.submit('T', 'B', 60, 101) == [('T', 'Z', 100, 20), ('T', 'X', 101, 40)]
# drill 7
assert 1e6 / (1_000_000 * 0.25) == 4.0

print('sy44 code checks passed (%d steps against the naive matcher)' % steps)
