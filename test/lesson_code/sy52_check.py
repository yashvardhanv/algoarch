"""Runs the python blocks from data/new_lessons/sy52-scaling-patterns-blobs-tasks-realtime.md against independent
references: the upload cost formulas against a summation form and against the lesson's own lossy-network protocol
simulation, both upload servers against fault injection, the task store against a second implementation on random
operation sequences, the event-stream parser against the examples in the WHATWG standard and a second parser on
fuzzed input, and every number the lesson prints."""
import re, sys, math, random, itertools

src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)

def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the computed figure: %r' % p

# ---------------------------------------------------------------- blobs: the S3 limits and the cost of failure
MIB, GIB = 1 << 20, 1 << 30
assert (ns['MAX_PARTS'], ns['MIN_PART'], ns['MAX_PART']) == (10_000, 5 * MIB, 5 * GIB)
assert abs(ns['max_object_bytes']() / (1 << 40) - 48.8) < 0.05                       # the page says 48.8 TiB
assert ns['min_part_bytes'](1 * GIB) == 5 * MIB                                      # small objects: the minimum part
assert ns['min_part_bytes'](100 * GIB) == math.ceil(100 * GIB / 10_000)
assert ns['part_count'](100 * GIB, ns['min_part_bytes'](100 * GIB)) <= 10_000
assert ns['part_count'](100 * GIB, ns['min_part_bytes'](100 * GIB) - 1) > 10_000     # one byte smaller does not fit
assert ns['part_count'](100 * 10 ** 9, 100 * 10 ** 6) == 1000 and ns['api_calls'](100 * 10 ** 9, 100 * 10 ** 6) == 1002
need('48.8 TiB', '1,002')

expected_sent, expected_requests, best_chunk = ns['expected_sent'], ns['expected_requests'], ns['best_chunk']

def ref_chunk_cost(c, p):
    """Blocks sent to deliver one whole chunk of c blocks when a failure restarts it: X = q^c c + sum q^(i-1) p (i + X)."""
    q = 1 - p
    num = q ** c * c + sum(q ** (i - 1) * p * i for i in range(1, c + 1))
    return num / q ** c

for p in (0.0005, 0.01, 0.1):
    for c in (1, 3, 20, 57):
        assert abs(expected_sent(c, c, p) - ref_chunk_cost(c, p)) < 1e-6 * max(1, ref_chunk_cost(c, p))
        assert abs(expected_sent(5 * c, c, p) - 5 * ref_chunk_cost(c, p)) < 1e-6 * 5 * ref_chunk_cost(c, p)
    assert abs(expected_sent(100, 30, p) - (3 * ref_chunk_cost(30, p) + ref_chunk_cost(10, p))) < 1e-6 * expected_sent(100, 30, p)
    assert abs(expected_sent(100, 30, p, True) - 100 / (1 - p)) < 1e-9
assert expected_sent(100, 10, 0) == 100 and expected_sent(100, 10, 0, True) == 100
assert abs(expected_sent(1000, 1, 0.01) - 1000 / 0.99) < 1e-6                         # chunk of one block: every block is its own request

# best_chunk against brute force over every size
for total, p, ov in ((200, 0.01, 2), (500, 0.002, 5), (300, 0.05, 1)):
    costs = {c: expected_sent(total, c, p) + ov * expected_requests(total, c, p) for c in range(1, total + 1)}
    assert costs[best_chunk(total, p, ov)] == min(costs.values())
    assert best_chunk(total, p, ov, True) == total                                    # resuming from the offset: never chunk for loss
T, P, OV = 10_000, 0.001, 2
rows = [10, best_chunk(T, P, OV), 100, 1000, T]
for c in rows:
    a, b = expected_sent(T, c, P), expected_requests(T, c, P)
    r, s = expected_sent(T, c, P, True), expected_requests(T, c, P, True)
    need('| %s | %s | %s | %s | %s |' % (c, format(round(a), ','), format(round(b), ','), format(round(a + OV * b), ','),
                                        format(round(r + OV * s), ',')))
assert best_chunk(T, P, OV) == 61 and best_chunk(T, P, OV, True) == T
need('| 61 |')

# the protocol simulation agrees with the formula
PartStore, OffsetStore, Conflict, Flaky = ns['PartStore'], ns['OffsetStore'], ns['Conflict'], ns['Flaky']
upload_parts, upload_offset = ns['upload_parts'], ns['upload_offset']
source = ['b%d' % i for i in range(200)]
tot_part = tot_off = 0
trials = 400
for seed in range(trials):
    net = Flaky(0.01, 0.0, seed)
    assert upload_parts(source, 20, PartStore(10), net, seed) == source
    tot_part += net.blocks_sent
    net = Flaky(0.01, 0.0, seed)
    assert upload_offset(source, 20, OffsetStore(200), net) == source
    tot_off += net.blocks_sent
assert abs(tot_part / trials / expected_sent(200, 20, 0.01) - 1) < 0.02, tot_part / trials
assert abs(tot_off / trials / expected_sent(200, 20, 0.01, True) - 1) < 0.02, tot_off / trials
assert tot_part / trials > tot_off / trials                                           # parts resend whole chunks, offsets only the rest
# correctness under heavy faults, lost acknowledgements and every part size
for seed in range(60):
    for p, ack in ((0.0, 0.0), (0.02, 0.3), (0.2, 0.5)):
        for chunk in (1, 7, 20, 200):
            n_parts = -(-200 // chunk)
            if p * chunk <= 0.5:                                  # whole-part retries only finish when a part can get through
                assert upload_parts(source, chunk, PartStore(n_parts), Flaky(p, ack, seed), seed) == source
            assert upload_offset(source, chunk, OffsetStore(200), Flaky(p, ack, seed)) == source

# the stores on their own
st = PartStore(3)
st.put_part(2, ['b']); st.put_part(1, ['a']); st.put_part(3, ['c']); st.put_part(2, ['b'])    # any order, a repeat replaces
assert st.complete([3, 1, 2]) == ['a', 'b', 'c']
for bad in ([1, 2], [1, 2, 3, 4], [1, 2, 2]):
    st = PartStore(3)
    st.put_part(1, ['a']); st.put_part(2, ['b'])
    try:
        st.complete(bad)
        raise AssertionError('completed with a bad manifest %r' % bad)
    except ValueError:
        pass
st = PartStore(3)
st.put_part(1, ['a']); st.put_part(2, ['b'])
try:
    st.complete([1, 2, 3]); raise AssertionError('completed with a part never uploaded')
except ValueError:
    pass
for n in (0, 4):
    try:
        PartStore(3).put_part(n, ['x']); raise AssertionError('accepted part %d' % n)
    except ValueError:
        pass
st = PartStore(2)
st.put_part(1, ['old']); st.put_part(1, ['new']); st.put_part(2, ['z'])
assert st.complete([1, 2]) == ['new', 'z']

os_ = OffsetStore(5)
assert os_.head() == 0 and os_.patch(0, ['a', 'b']) == 2 and os_.head() == 2
try:
    os_.patch(0, ['a', 'b']); raise AssertionError('a repeated PATCH was accepted')    # the blind retry after a lost answer
except Conflict:
    pass
assert os_.data == ['a', 'b']                                                            # and it changed nothing
try:
    os_.patch(1, ['x']); raise AssertionError('an offset in the middle was accepted')
except Conflict:
    pass
assert os_.patch(2, ['c', 'd', 'e'], arrived=2) == 4 and os_.data == ['a', 'b', 'c', 'd']  # the part that arrived is kept
try:
    os_.patch(4, ['e', 'f']); raise AssertionError('data past the declared length')
except ValueError:
    pass

# a client that never asks and just repeats the same PATCH after a lost answer is stopped by the offset check
def blind(source, chunk, store, ack, seed):
    rng = random.Random(seed)
    off = 0
    while off < len(source):
        blocks = source[off:off + chunk]
        try:
            new = store.patch(off, blocks)
        except Conflict:
            return 'conflict'
        if rng.random() < ack:
            continue                                                                   # the answer was lost; repeat the same PATCH
        off = new
    return 'done'
outcomes = {blind(source, 20, OffsetStore(200), 0.4, s) for s in range(30)}
assert 'conflict' in outcomes                                                            # the server refused the duplicate

# ---------------------------------------------------------------- long-running tasks
TaskStore, run_fleet = ns['TaskStore'], ns['run_fleet']
Q, R, S_, F, C = 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'

class RefStore:
    """A second implementation: an event log per task, state derived by replaying it."""
    def __init__(self, lease, maxa):
        self.lease, self.maxa, self.log, self.order = lease, maxa, {}, []

    def submit(self, tid):
        if tid not in self.log:
            self.log[tid] = []; self.order.append(tid)
        return tid

    def view(self, tid):
        st, attempts, lease, prog, res, err = Q, 0, None, 0, None, None
        for ev in self.log[tid]:
            kind = ev[0]
            if kind == 'claim':
                st, attempts, lease = R, attempts + 1, ev[1] + self.lease
            elif kind == 'hb':
                lease = ev[1] + self.lease
                if ev[2] is not None:
                    prog = ev[2]
            elif kind == 'done':
                st, res, prog, lease = S_, ev[1], 100, None
            elif kind == 'retry':
                st, lease = Q, None
            elif kind == 'fail':
                st, err, lease = F, ev[1], None
            elif kind == 'cancel':
                st, lease = C, None
        return st, attempts, lease, prog, res, err

    def claim(self, now):
        for tid in self.order:
            if self.view(tid)[0] == Q:
                self.log[tid].append(('claim', now))
                return tid, self.view(tid)[1]
        return None

    def heartbeat(self, tid, token, now, progress=None):
        if tid not in self.log:
            return 'stale'
        st, attempts, *_ = self.view(tid)
        if attempts != token or st not in (R, C):
            return 'stale'
        if st == C:
            return 'cancelled'
        self.log[tid].append(('hb', now, progress))
        return 'ok'

    def complete(self, tid, token, result):
        if tid not in self.log:
            return False
        st, attempts, *_ = self.view(tid)
        if attempts != token or st != R:
            return False
        self.log[tid].append(('done', result))
        return True

    def fail(self, tid, token, error):
        if tid not in self.log:
            return 'stale'
        st, attempts, *_ = self.view(tid)
        if attempts != token or st != R:
            return 'stale'
        if attempts < self.maxa:
            self.log[tid].append(('retry',)); return 'retry'
        self.log[tid].append(('fail', error)); return 'failed'

    def cancel(self, tid):
        if tid not in self.log or self.view(tid)[0] in (S_, F, C):
            return False
        self.log[tid].append(('cancel',)); return True

    def reap(self, now):
        out = []
        for tid in self.order:
            st, attempts, lease, *_ = self.view(tid)
            if st == R and lease <= now:
                if attempts < self.maxa:
                    self.log[tid].append(('retry',))
                else:
                    self.log[tid].append(('fail', 'lease expired on the last attempt'))
                out.append(tid)
        return out

    def get(self, tid):
        st, attempts, lease, prog, res, err = self.view(tid)
        v = {'state': st, 'done': st in (S_, F, C), 'progress': prog}
        if st == S_:
            v['result'] = res
        if st == F:
            v['error'] = err
        return v

for seed in range(300):
    rng = random.Random(seed)
    lease, maxa = rng.choice((2, 5)), rng.choice((1, 2, 3))
    a, b = TaskStore(lease, maxa), RefStore(lease, maxa)
    now, tokens = 0, {}
    for step in range(120):
        now += rng.choice((0, 1, 1, 2, 3))
        op = rng.choice(('submit', 'submit', 'claim', 'claim', 'hb', 'complete', 'fail', 'cancel', 'reap', 'get'))
        tid = rng.randrange(4)
        tok = rng.randrange(0, 5)
        if op == 'submit':
            assert a.submit(tid) == b.submit(tid)
        elif op == 'claim':
            assert a.claim(now) == b.claim(now)
        elif tid not in a.tasks and op != 'reap':
            continue
        elif op == 'hb':
            prog = rng.choice((None, 10, 50))
            assert a.heartbeat(tid, tok, now, prog) == b.heartbeat(tid, tok, now, prog)
        elif op == 'complete':
            assert a.complete(tid, tok, 'r%d' % step) == b.complete(tid, tok, 'r%d' % step)
        elif op == 'fail':
            assert a.fail(tid, tok, 'e%d' % step) == b.fail(tid, tok, 'e%d' % step)
        elif op == 'cancel':
            assert a.cancel(tid) == b.cancel(tid)
        elif op == 'reap':
            assert a.reap(now) == b.reap(now)
        elif op == 'get':
            assert a.get(tid) == b.get(tid)
        for t in a.tasks:                                                                # invariants on every step
            v = a.get(t)
            assert a.tasks[t]['attempts'] <= maxa
            assert v['done'] == (v['state'] in (S_, F, C))
# scenarios the lesson describes
st = TaskStore(lease_s=5, max_attempts=3)
assert st.submit('t') == 't' and st.submit('t') == 't' and len(st.tasks) == 1               # a retried submit does not enqueue twice
tid, tok1 = st.claim(0)
assert tok1 == 1 and st.claim(0) is None                                                    # one claim at a time
assert st.heartbeat('t', 1, 3, progress=40) == 'ok' and st.get('t')['progress'] == 40
assert st.reap(7) == [] and st.reap(8) == ['t']                                             # lease was renewed at 3, so it ends at 8
tid, tok2 = st.claim(9)
assert tok2 == 2
assert st.heartbeat('t', 1, 10) == 'stale' and st.complete('t', 1, 'late') is False         # the paused worker wakes up: fenced out
assert st.fail('t', 1, 'x') == 'stale'
assert st.complete('t', 2, 'ok') is True and st.get('t') == {'state': S_, 'done': True, 'progress': 100, 'result': 'ok'}
assert st.complete('t', 2, 'again') is False and st.cancel('t') is False and st.reap(10_000) == []   # terminal states stay
st = TaskStore(lease_s=5, max_attempts=2)
st.submit('a'); st.submit('b')
a_id, ta = st.claim(0)
assert st.fail('a', ta, 'boom') == 'retry' and st.get('a')['state'] == Q
a_id, ta = st.claim(1)                                                                       # 'a' is first in order again
assert (a_id, ta) == ('a', 2) and st.fail('a', 2, 'boom') == 'failed' and st.get('a') == {'state': F, 'done': True, 'progress': 0, 'error': 'boom'}
b_id, tb = st.claim(2)
assert st.cancel('b') is True and st.heartbeat('b', tb, 3) == 'cancelled' and st.complete('b', tb, 'x') is False
st = TaskStore(lease_s=2, max_attempts=1)
st.submit('c'); st.claim(0)
assert st.reap(2) == ['c'] and st.get('c') == {'state': F, 'done': True, 'progress': 0, 'error': 'lease expired on the last attempt'}

fleet = {}
for c in (0.0, 0.1, 0.2, 0.4):
    fleet[c] = run_fleet(1000, 20, c, seed=5)
    secs, counts, claims = fleet[c]
    want_claims = 1000 * (1 - c ** 3) / (1 - c)
    want_failed = 1000 * c ** 3
    assert abs(claims - want_claims) / want_claims < 0.04, (c, claims, want_claims)
    assert abs(counts.get('FAILED', 0) - want_failed) <= max(3, 0.35 * want_failed), (c, counts)
    assert sum(counts.values()) == 1000 and set(counts) <= {S_, F}
assert fleet[0.0][0:2] == (399, {S_: 1000}) and fleet[0.0][2] == 1000
assert fleet[0.0][0] < fleet[0.1][0] < fleet[0.2][0] < fleet[0.4][0]                        # more crashes, longer to finish
for c, (secs, counts, claims) in fleet.items():
    need('| %d%% | %d | %d | %d | %d | %d |' % (round(c * 100), secs, counts.get(S_, 0), counts.get(F, 0), claims,
                                               round(1000 * (1 - c ** 3) / (1 - c))))

# ---------------------------------------------------------------- real-time: the event-stream format
parse = ns['parse_event_stream']
ev, last, retry = parse('data: YHOO\ndata: +2\ndata: 10\n\n')
assert ev == [('message', 'YHOO\n+2\n10', '')]                                             # the standard's first example
ev, last, retry = parse(': test stream\n\ndata: first event\nid: 1\n\ndata:second event\nid\n\ndata:  third event\n\n')
assert ev == [('message', 'first event', '1'), ('message', 'second event', ''), ('message', ' third event', '')]
assert last == ''                                                                          # an id field with no value resets it
ev, last, _ = parse('data\n\ndata\ndata\n\ndata:')
assert ev == [('message', '', ''), ('message', '\n', '')]                                  # the last block has no blank line: dropped
ev, last, _ = parse('data:test\n\ndata: test\n\n')
assert ev == [('message', 'test', ''), ('message', 'test', '')]
ev, last, retry = parse('retry: 1500\nevent: add\nid: 9\ndata: x\n\nfoo: bar\nretry: 12a\ndata: y\n\n')
assert ev == [('add', 'x', '9'), ('message', 'y', '9')] and last == '9' and retry == 1500  # retry with a non-digit is ignored; id persists
assert parse('id: a\0b\ndata: z\n\n')[0] == [('message', 'z', '')]                            # an id with NUL is ignored
assert parse('﻿data: a\n\n')[0] == [('message', 'a', '')]
assert parse('data: a\r\ndata: b\r\rdata: c\n\n')[0] == [('message', 'a\nb', ''), ('message', 'c', '')]
assert parse('event: only-type\n\n')[0] == [] and parse('data: cut off')[0] == [] and parse('')[0] == []
assert parse('data: a\n\n', last_id='5')[1] == '5' and parse('data: a\n\n', last_id='5')[0] == [('message', 'a', '5')]

def ref_parse(text, last_id=''):
    """Second parser: one character at a time, with an explicit CR-then-LF state."""
    if text[:1] == '﻿':
        text = text[1:]
    events, retry = [], None
    buf_data, buf_type, buf_id = None, '', last_id
    cur, prev_cr = '', False
    def line_done(line):
        nonlocal buf_data, buf_type, buf_id, last_id, retry
        if line == '':
            last_id = buf_id
            if buf_data is not None:
                events.append((buf_type or 'message', buf_data, last_id))
            buf_data, buf_type = None, ''
            return
        if line[0] == ':':
            return
        if ':' in line:
            k, v = line[:line.index(':')], line[line.index(':') + 1:]
            v = v[1:] if v[:1] == ' ' else v
        else:
            k, v = line, ''
        if k == 'data':
            buf_data = v if buf_data is None else buf_data + '\n' + v
        elif k == 'event':
            buf_type = v
        elif k == 'id' and '\0' not in v:
            buf_id = v
        elif k == 'retry' and v != '' and all(ch in '0123456789' for ch in v):
            retry = int(v)
    for ch in text:
        if prev_cr and ch == '\n':
            prev_cr = False
            continue
        prev_cr = False
        if ch in '\r\n':
            line_done(cur)
            cur = ''
            prev_cr = ch == '\r'
        else:
            cur += ch
    return events, last_id, retry

alphabet = ['data', 'id', 'event', 'retry', ':', ': ', '\n', '\n\n', '\r', '\r\n', 'x', '1', '12', ' ', '\0']
for seed in range(3000):
    rng = random.Random(seed)
    s = ''.join(rng.choice(alphabet) for _ in range(rng.randrange(0, 30)))
    assert parse(s) == ref_parse(s), repr(s)
    assert parse(s, '7') == ref_parse(s, '7'), repr(s)

# ---------------------------------------------------------------- real-time: resuming a stream
EventLog, Subscriber = ns['EventLog'], ns['Subscriber']
log = EventLog(keep=3)
for d in (10, 20, 30, 40, 50):
    log.append(d)
assert log.events == [(3, 30), (4, 40), (5, 50)] and log.total == 150
assert log.since(2) == [(3, 30), (4, 40), (5, 50)] and log.since(4) == [(5, 50)] and log.since(5) == []
assert log.since(1) is None and log.since(0) is None                                        # events 2 and beyond are gone
assert EventLog(3).since(0) == [] and log.serve(1) == 'event: snapshot\nid: 5\ndata: 150\n\n'
assert log.serve(4) == 'id: 5\ndata: 50\n\n'
for last_id in range(0, 6):
    got = log.since(last_id)
    assert got is None or all(e[0] > last_id for e in got)                                   # never replays what the client has
sub = Subscriber()
assert sub.receive(log.serve(0)) == 0 and (sub.total, sub.last_id, sub.snapshots) == (150, 5, 1)
assert sub.receive(log.serve(5)) == 0 and sub.receive('id: 5\ndata: 50\n\n') == 0 and sub.total == 150   # a duplicate is ignored
log.append(7)
assert sub.receive(log.serve(sub.last_id)) == 1 and (sub.total, sub.last_id) == (157, 6)
try:
    sub.receive('id: 9\ndata: 1\n\n'); raise AssertionError('a gap was applied')
except ValueError:
    pass

def trial(seed, keep, n=200):
    rng = random.Random(seed)
    lg, sb = EventLog(keep), Subscriber()
    produced = 0
    while produced < n:
        for _ in range(rng.randrange(1, 12)):
            lg.append(rng.randrange(1, 10)); produced += 1
        text = lg.serve(sb.last_id)
        cut = rng.randrange(len(text) + 1) if rng.random() < 0.7 else len(text)             # the connection dies anywhere
        sb.receive(text[:cut])
        events, _, _ = parse(text[:cut])
        full, _, _ = parse(text)
        assert events == full[:len(events)]                                                  # only whole events, a prefix of the stream
    sb.receive(lg.serve(sb.last_id))
    assert (sb.total, sb.last_id) == (lg.total, lg.next_id - 1), (seed, keep)
    return sb.snapshots
snaps = {k: sum(trial(s, k) for s in range(200)) for k in (2, 5, 50)}
assert snaps[2] > snaps[5] > 0 and snaps[50] == 0

poll_load, long_poll_load, keepalive_rate, reconnect_rate = ns['poll_load'], ns['long_poll_load'], ns['keepalive_rate'], ns['reconnect_rate']
assert poll_load(1_000_000, 5) == 200_000 and poll_load(1_000_000, 1) == 1_000_000
assert long_poll_load(1_000_000, 30, 0) == 1_000_000 / 30
assert abs(long_poll_load(1000, 30, 50) - 50_000) < 1                                        # when events are frequent, a request per event
lam = 1 / 3600
assert round(long_poll_load(1_000_000, 30, lam)) == 33_472
# Monte Carlo: simulate holds directly and count requests per second
rng = random.Random(3)
users, horizon, lam2, TO = 400, 3600.0, 0.02, 30.0
reqs = 0
for _ in range(users):
    t = 0.0
    while t < horizon:
        t += min(rng.expovariate(lam2), TO)
        reqs += 1
assert abs(reqs / horizon / long_poll_load(users, TO, lam2) - 1) < 0.03, (reqs / horizon, long_poll_load(users, TO, lam2))
assert keepalive_rate(1_000_000, 15) == 1_000_000 / 15 and reconnect_rate(100_000, 2) == 50_000
for need_ in ('200,000', '1,000,000', '33,472', '66,667', '278', '2.5 s', '50,000'):
    need(need_)
assert round(1_000_000 * lam) == 278 and round(100 * (1_000_000 * lam) / 200_000, 2) == 0.14
need('0.14%')

# figures quoted in the prose
assert ns['held_connections'](2, 3 * GIB / (10 * MIB)) == 614.4 and 2 * 3 * GIB / MIB == 6144
need('614 connections', '6,144 MiB', '307 seconds')
assert round(0.999 ** 10000 * 100, 4) == 0.0045 and round(expected_sent(T, T, P) / T) == 2214
need('0.0045%', '2,214 times')
assert round(ns['min_part_bytes'](100 * GIB) / MIB, 2) == 10.24
need('10.24 MiB')
assert round(100 * (1_000_000 * lam) / 1_000_000, 2) == 0.03
need('0.03%')
streams = {k: (sum(ns['run_stream'](s, k)[1] for s in range(200)), all(ns['run_stream'](s, k)[0] for s in range(200))) for k in (2, 5, 50)}
assert streams == {2: (2171, True), 5: (1920, True), 50: (0, True)}, streams
for k, (n, ok) in streams.items():
    need('| %d | %s |' % (k, format(n, ',')))
assert fleet[0.4][2] - 1000 == 553 and round(1000 * 0.4 ** 3) == 64 and abs(fleet[0.4][0] / fleet[0.0][0] - 1.33) < 0.01
need('553 extra claims', 'formula says 64')
assert abs(1000 * 0.2 ** 3 / 1000 - 0.008) < 1e-12 and abs((1 - 0.2 ** 3) / 0.8 - 1.24) < 1e-12
need('222.6 blocks', '202.0')
assert round(expected_sent(200, 20, 0.01), 1) == 222.6 and round(expected_sent(200, 20, 0.01, True), 1) == 202.0

print('sy52 code checks passed')
