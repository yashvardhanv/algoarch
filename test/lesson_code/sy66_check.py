"""Runs the python blocks of the sy66 log aggregation lesson against brute-force references: segment search with time and
stream pruning against a scan of every flushed line, retention that never drops a line inside the window, the merge-policy
model against its closed forms, and the at-least-once shipper against a lossy, duplicating, reordering channel. Figures the
lesson prints from simulation are asserted here."""
import re, sys, random, collections

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
LogStore, merge_sim, digit_sum, written_formula = ns['LogStore'], ns['merge_sim'], ns['digit_sum'], ns['written_formula']
Agent, Receiver = ns['Agent'], ns['Receiver']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


# ---- 1. search: segments, pruning, near-real-time visibility ----------------------------------------------------------------
def scan(lines, terms, t0, t1, stream=None):
    out = []
    for ts, st, text in lines:
        words = text.lower().split()
        if t0 <= ts < t1 and (stream is None or st == stream) and all(t in words for t in terms):
            out.append((ts, st, text))
    return sorted(out)


s = LogStore()
s.append(10, 'web', 'GET /a 200'); s.append(11, 'web', 'GET /b 500')
assert s.search(['get'], 0, 100)[0] == []                    # not searchable until a refresh makes a segment
s.refresh()
assert [t for t, _, _ in s.search(['get'], 0, 100)[0]] == [10, 11]
assert s.search(['get'], 10, 11)[0] == [(10, 'web', 'GET /a 200')]            # [t0, t1): t1 itself excluded, t0 included
assert s.search(['get'], 11, 12)[0] == [(11, 'web', 'GET /b 500')]
assert s.search(['get'], 12, 20)[0] == [] and s.search(['get'], 0, 10)[0] == []
assert s.search(['GET'], 0, 100)[0] == []                                      # terms are matched lower-case; the caller lower-cases
assert s.search(['get', '500'], 0, 100)[0] == [(11, 'web', 'GET /b 500')]     # AND of two terms
assert s.search(['get', 'missing'], 0, 100)[0] == []
assert s.search(['get'], 0, 100, stream='db')[0] == []
s.refresh()                                                                    # an empty buffer adds no segment
assert len(s.segments) == 1

rng = random.Random(21)
words = ['error', 'warn', 'timeout', 'user', 'db', 'retry', 'ok', 'cache', 'miss', 'hit', 'w10', 'w11', 'w12']
for trial in range(300):
    st = LogStore()
    flushed = []
    for step in range(rng.randint(1, 120)):
        ts = rng.randint(0, 60) if rng.random() < .3 else step + rng.randint(-3, 3)      # mostly in order, some late arrivals
        line = (ts, rng.choice(['a', 'b', 'c']), ' '.join(rng.choice(words) for _ in range(rng.randint(1, 4))))
        st.append(*line)
        flushed.append(line)
        if rng.random() < .15:
            st.refresh()
    st.refresh()
    visible = [l for seg in st.segments for l in seg.docs]
    assert sorted(visible) == sorted(flushed)
    for _ in range(12):
        t0 = rng.randint(-5, 130); t1 = t0 + rng.randint(0, 40)
        terms = rng.sample(words, rng.randint(1, 2))
        stream = rng.choice([None, 'a', 'b', 'z'])
        got, scanned = st.search(terms, t0, t1, stream)
        assert got == scan(visible, terms, t0, t1, stream), (trial, terms, t0, t1, stream)
        assert scanned <= len(st.segments)
# pruning really skips segments: ten disjoint hours, a one-hour query opens one segment
st = LogStore()
for hour in range(10):
    for i in range(5):
        st.append(hour * 3600 + i, 'web', 'GET ok')
    st.refresh()
got, scanned = st.search(['get'], 3 * 3600, 4 * 3600)
assert len(got) == 5 and scanned == 1
got, scanned = st.search(['get'], 0, 10 * 3600)
assert len(got) == 50 and scanned == 10
# a stream filter skips segments that hold no line of that stream
st = LogStore()
st.append(1, 'a', 'x'); st.refresh(); st.append(2, 'b', 'x'); st.refresh()
assert st.search(['x'], 0, 10, 'b') == ([(2, 'b', 'x')], 1) and st.search(['x'], 0, 10, 'q') == ([], 0)
# a late line widens its segment's range, so a query for the late time must open that segment
st = LogStore()
st.append(5000, 'web', 'late line'); st.append(100, 'web', 'late line'); st.refresh()
st.append(200, 'web', 'other'); st.refresh()
assert st.search(['late'], 90, 110)[0] == [(100, 'web', 'late line')]
assert st.search(['late'], 90, 110)[1] == 1 and st.search(['other'], 90, 300)[1] == 2

# ---- 2. retention drops whole segments, and only ones entirely older than the cutoff -------------------------------------
for trial in range(200):
    st = LogStore()
    for step in range(rng.randint(1, 80)):
        st.append(rng.randint(0, 100), 'a', 'x y')
        if rng.random() < .2:
            st.refresh()
    st.refresh()
    before = [l for seg in st.segments for l in seg.docs]
    nseg = len(st.segments)
    cutoff = rng.randint(0, 110)
    dropped = st.expire(cutoff)
    after = [l for seg in st.segments for l in seg.docs]
    assert dropped == nseg - len(st.segments)
    cb, ca = collections.Counter(before), collections.Counter(after)
    assert not (ca - cb)                                                       # retention never invents lines
    assert all(ca[l] == cb[l] for l in cb if l[0] >= cutoff)                   # nothing inside the retention window is lost
    assert all(seg.max_ts >= cutoff for seg in st.segments)                    # every surviving segment reaches into the window
    assert all(l[0] < cutoff for l in (cb - ca))                               # every line that disappears is older than the cutoff

# ---- 3. merge model against its closed forms --------------------------------------------------------------------------------
def digits(n, m):
    out = 0
    while n:
        out += n % m; n //= m
    return out


for m in (2, 3, 4, 10):
    for n in range(0, 700):
        segs, written = merge_sim(n, m)
        assert segs == digit_sum(n, m) == digits(n, m), (n, m)
        assert written == written_formula(n, m), (n, m)
        if n:
            assert written <= n * sum(1 for t in range(0, 60) if m ** t <= n), (n, m)      # at most 1 + floor(log_m n) writes per flushed unit
assert merge_sim(1000, 10)[0] == 1 and merge_sim(1000, 10)[1] == 4000                    # 10^3 flushes: every doc written 4 times
assert merge_sim(999, 10)[0] == 27 and merge_sim(10, 10) == (1, 20) and merge_sim(9, 10) == (9, 9)
assert merge_sim(0, 10) == (0, 0)
assert written_formula(4096, 2) == 4096 * 13

# ---- 4. at-least-once shipping with dedupe ---------------------------------------------------------------------------------------
def run(seed, make_receiver):
    r = random.Random(seed)
    sent, agents = [], {n: Agent(n) for n in ('web', 'db', 'cache')}
    rx = make_receiver()
    pending = {n: r.randint(5, 45) for n in agents}
    got_ = {n: set() for n in agents}
    for rnd in range(400):
        for name, ag in agents.items():
            if pending[name] and r.random() < .6:
                for _ in range(r.randint(1, 4)):
                    if pending[name]:
                        line = '%s-%d' % (name, ag.seq)
                        ag.log(line); sent.append((name, ag.seq - 1, line)); pending[name] -= 1
            msgs = ag.outbox()
            r.shuffle(msgs)
            for m in msgs:
                if r.random() < .5:                                  # a lost message is simply never delivered
                    for _ in range(2 if r.random() < .25 else 1):    # some are delivered twice
                        got_[m[0]].add(m[1])
                        ack = rx.accept(*m)
                        prefix = 0
                        while prefix in got_[m[0]]:
                            prefix += 1
                        assert ack == prefix, (seed, m, ack, prefix)         # the ack is exactly the contiguous prefix received: not lagging, not ahead
                        if r.random() < .5:                           # a lost ack is simply never delivered
                            ag.on_ack(ack)
        if not any(pending.values()) and not any(a.unacked for a in agents.values()):
            break
    return sent, rx, agents


for seed in range(300):
    sent, rx, agents = run(seed, Receiver)
    assert sorted(rx.stored) == sorted(sent), seed                      # every line stored exactly once
    assert all(not a.unacked for a in agents.values()), seed            # and every line eventually acknowledged
    for name in agents:
        seqs = sorted(q for n, q, _ in rx.stored if n == name)
        assert seqs == list(range(len(seqs)))
        assert rx.expect[name] == len(seqs) and not rx.early[name]


class NoDedupe(Receiver):
    def accept(self, source, seq, line):
        self.stored.append((source, seq, line))
        return super().accept(source, seq, line)


dups = sum(len(run(seed, NoDedupe)[1].stored) - len(run(seed, NoDedupe)[0]) for seed in range(20))
assert dups > 0                                                          # the channel does duplicate: the test is not vacuous
# sequence numbers past 9 and 99 are compared as numbers
ag = Agent('x')
for i in range(120):
    ag.log('l%d' % i)
rx = Receiver()
for s_, q, l in reversed(ag.outbox()):                                  # worst case order: newest first
    last = rx.accept(s_, q, l)
assert last == 120 and len(rx.stored) == 120 and not rx.early['x']
assert [q for _, q, _ in ag.outbox()] == list(range(120))
ag.on_ack(100)
assert [q for _, q, _ in ag.outbox()] == list(range(100, 120))
ag.on_ack(50)                                                            # a late, smaller ack changes nothing
assert len(ag.outbox()) == 20
rx2 = Receiver()
assert rx2.accept('x', 3, 'c') == 0 and rx2.accept('x', 0, 'a') == 1 and rx2.accept('x', 1, 'b') == 2 and rx2.accept('x', 2, 'z') == 4
assert rx2.accept('x', 3, 'c') == 4 and len(rx2.stored) == 4              # the duplicate of 3 is ignored; the gap closed at 2

need('digit sum', 'written_formula', '4 times', 'exactly once')
for stale in ('searchable immediately', 'delete the old lines one by one'):
    assert stale.lower() not in src.lower(), 'stale wording: %r' % stale
print('sy66 code checks passed')
