"""Runs the python blocks of the sy63 email-service lesson: the outbound retry queue against the RFC 5321 retry rules and an
independent simulation of lost replies (at-least-once delivery and duplicates), the receiver's duplicate window, an IMAP-style
mailbox (UID, UIDVALIDITY, mod-sequence, tombstones) against full-state replicas under random operations, and DMARC alignment
against an independently written brute-force. Figures the lesson prints from simulations are asserted here."""
import re, sys, random, hashlib

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 4, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
OutQueue, retry_delay, classify = ns['OutQueue'], ns['retry_delay'], ns['classify']
Inbox, Mailbox, Replica = ns['Inbox'], ns['Mailbox'], ns['Replica']
org_domain, aligned, dmarc_result = ns['org_domain'], ns['aligned'], ns['dmarc_result']


def need(*phrases):
    for p in phrases:
        assert p in src, 'lesson text is missing the checked figure: %r' % p


def forbid(*phrases):
    for p in phrases:
        assert p not in src, 'lesson text still contains stale wording: %r' % p


# ---- 1. reply classes and the retry schedule --------------------------------------------------------------------------
assert [classify(c) for c in (250, 251, 421, 450, 452, 550, 554, 500)] == ['ok', 'ok', 'defer', 'defer', 'defer', 'fail', 'fail', 'fail']
assert [retry_delay(n) for n in range(1, 8)] == [1800, 3600, 7200, 10800, 10800, 10800, 10800]
# RFC 5321 4.5.4.1: at least 30 minutes between tries, two tries in the first hour, then one every two or three hours
t, times = 0, [0]
for n in range(1, 40):
    t += retry_delay(n)
    times.append(t)
assert [x for x in times if x <= 3600] == [0, 1800] and times[2] == 5400     # two tries inside the first hour, the third at 1.5 hours
assert all(retry_delay(n) >= 1800 for n in range(1, 100)) and max(retry_delay(n) for n in range(1, 100)) == 10800

# ---- 2. the queue: due times, per-recipient outcomes, bounce rules ------------------------------------------------------
q = OutQueue()
q.submit('m1', ['a@x', 'b@y', 'c@z'], 0, 'me@home')
assert q.due(0) == [('m1', 'a@x'), ('m1', 'b@y'), ('m1', 'c@z')]
q.report('m1', 'a@x', 250, 0)
q.report('m1', 'b@y', 451, 0)
q.report('m1', 'c@z', 550, 0)
assert q.state('m1', 'a@x') == 'delivered' and q.state('m1', 'b@y') == 'queued' and q.state('m1', 'c@z') == 'bounced'
assert [d['rcpt'] for d in q.dsns] == ['c@z'] and q.dsns[0]['to'] == 'me@home' and q.dsns[0]['return_path'] == ''
assert q.due(1799) == [] and q.due(1800) == [('m1', 'b@y')]            # exactly 30 minutes: due; one second earlier: not
q.report('m1', 'b@y', 451, 1800)
assert q.due(1800 + 3599) == [] and q.due(1800 + 3600) == [('m1', 'b@y')]
assert q.attempts('m1', 'b@y') == 2
# a bounce is never bounced: the null reverse-path gets no DSN even on a permanent failure (RFC 5321 6.2 / 4.5.5)
q.submit('dsn1', ['me@home'], 0, '')
q.report('dsn1', 'me@home', 550, 5)
assert q.state('dsn1', 'me@home') == 'bounced' and all(d['mid'] != 'dsn1' for d in q.dsns)
# a finished recipient never comes back, and a late report on it changes nothing
q.report('m1', 'a@x', 451, 99999)
assert q.state('m1', 'a@x') == 'delivered' and q.due(10 ** 7) == [('m1', 'b@y')]
ndsn = len(q.dsns)
q.report('m1', 'a@x', 550, 99999)                       # a duplicate failure report for a delivered recipient must not bounce it
q.report('m1', 'c@z', 250, 99999)                       # nor a late success revive a bounced one
assert q.state('m1', 'a@x') == 'delivered' and q.state('m1', 'c@z') == 'bounced' and len(q.dsns) == ndsn and q.attempts('m1', 'a@x') == 1
# give-up: a deferral AT or after 5 days becomes a bounce; one second before it is still retried
q = OutQueue()
q.submit('g', ['r@z'], 0, 's@h')
q.report('g', 'r@z', 451, 5 * 86400 - 1)
assert q.state('g', 'r@z') == 'queued'
q.report('g', 'r@z', 451, 5 * 86400)
assert q.state('g', 'r@z') == 'bounced' and q.dsns[-1]['reason'] == 'giveup'
# the give-up clock starts at submission, not at the first failure
q = OutQueue()
q.submit('g2', ['r@z'], 1000, 's@h')
q.report('g2', 'r@z', 451, 1000 + 5 * 86400 - 1)
assert q.state('g2', 'r@z') == 'queued'
q.report('g2', 'r@z', 451, 1000 + 5 * 86400)
assert q.state('g2', 'r@z') == 'bounced'
# the number of tries in five days (the lesson prints this)
q = OutQueue()
q.submit('c', ['r@z'], 0, 's@h')
tries, now = 0, 0
while q.state('c', 'r@z') == 'queued':
    now = q.next_due('c', 'r@z')
    assert q.due(now) == [('c', 'r@z')]
    q.report('c', 'r@z', 421, now)
    tries += 1
assert tries == 43 and now >= 5 * 86400 and q.attempts("c", "r@z") == 43, (tries, now)
need("43 tries")

# ---- 3. at-least-once: a lost reply to the final dot makes the sender retry, so the receiver sees the message twice -------
def simulate(n_msgs, p_lost, dedupe, seed):
    rng = random.Random(seed)
    inbox, stored = Inbox(), 0
    q = OutQueue()
    for i in range(n_msgs):
        q.submit('m%d' % i, ['u@d'], 0, 's@h')
    now = 0
    while any(q.state('m%d' % i, 'u@d') == 'queued' for i in range(n_msgs)):
        now += 60
        for mid, rc in q.due(now):
            body = 'body-' + mid
            if dedupe:
                stored += inbox.accept(rc, '<%s@h>' % mid, body, now) == 'stored'
            else:
                stored += 1                                    # a receiver with no memory files every arrival
            q.report(mid, rc, 451 if rng.random() < p_lost else 250, now)      # the receiver kept it; the 250 never arrived
    return stored, n_msgs
st_naive, n = simulate(1000, 0.10, False, 7)
st_dedupe, _ = simulate(1000, 0.10, True, 7)
assert st_dedupe == 1000                                   # one stored copy of every message
dups = st_naive - 1000
assert dups == 120, dups                                   # printed in the lesson
need('120 duplicate copies', '1,000 messages, 10%')

# ---- 4. the receiver's duplicate window --------------------------------------------------------------------------------
ib = Inbox(window=6 * 86400)
assert ib.accept('u@d', '<a@h>', 'hello', 0) == 'stored'
assert ib.accept('u@d', '<a@h>', 'hello', 100) == 'duplicate'
assert ib.accept('u@d', '<a@h>', 'hello!', 100) == 'stored'          # same Message-ID, different body: a different message
assert ib.accept('v@d', '<a@h>', 'hello', 100) == 'stored'           # another recipient is another delivery
assert ib.accept('u@d', '<a@h>', 'hello', 6 * 86400) == 'duplicate'  # still inside the window at exactly its edge
assert ib.accept('u@d', '<a@h>', 'hello', 6 * 86400 + 1) == 'stored' # beyond it: the honest hole
assert len(ib.store) == 4
assert Inbox().window >= 5 * 86400                                     # at least the sender's give-up time

# ---- 5. mailbox: UIDs, UIDVALIDITY, mod-sequences, tombstones -----------------------------------------------------------
mb = Mailbox(7)
u1, u2, u3 = mb.append(), mb.append(), mb.append()
assert (u1, u2, u3) == (1, 2, 3)
mb.expunge(3)
assert mb.append() == 4                                  # RFC 3501: a UID is never reused, even the highest one
mb.expunge(4); mb.expunge(1)
assert mb.append() == 5 and sorted(mb.snapshot()) == [2, 5]
m0 = mb.highest_modseq
mb.set_flags(2, {'\\Seen'})
assert mb.changes_since(m0) == ({2: frozenset({'\\Seen'})}, [])
assert mb.changes_since(mb.highest_modseq) == ({}, [])
# expunge is visible as VANISHED to a client that knew the message
r = Replica()
r.sync(mb)
assert r.msgs == mb.snapshot()
mb.expunge(2)
ch, van = mb.changes_since(r.modseq)
assert van == [2] and ch == {}
r.sync(mb)
assert r.msgs == mb.snapshot() and 2 not in r.msgs
# tombstone compaction: a client older than the floor must fully resync, one at the floor may not
mb2 = Mailbox(1)
for _ in range(3):
    mb2.append()
old = mb2.highest_modseq
mb2.expunge(1)
mb2.compact()
fl = mb2.highest_modseq
assert mb2.changes_since(old) is None and mb2.changes_since(fl) == ({}, [])
r2 = Replica(); r2.uidvalidity, r2.modseq, r2.msgs = 1, old, {1: frozenset(), 2: frozenset(), 3: frozenset()}
r2.sync(mb2)
assert r2.msgs == mb2.snapshot() == {2: frozenset(), 3: frozenset()}      # the expunge was lost with the tombstone, resync fixed it
# UIDVALIDITY: a re-created mailbox restarts UIDs; the replica must drop its cache, not merge
mb3 = Mailbox(10)
for _ in range(5):
    mb3.append()
r3 = Replica(); r3.sync(mb3)
mb3 = Mailbox(11)                                         # deleted and created again: same UIDs mean different mail
mb3.append(); mb3.set_flags(1, {'\\Flagged'})
r3.sync(mb3)
assert r3.msgs == mb3.snapshot() == {1: frozenset({'\\Flagged'})} and r3.uidvalidity == 11


def fuzz_mailbox(seed, steps=120):
    rng = random.Random(seed)
    mb, reps = Mailbox(1), [Replica() for _ in range(3)]
    for _ in range(steps):
        op = rng.random()
        live = sorted(mb.snapshot())
        if op < 0.35 or not live:
            mb.append(rng.choice([(), ('\\Seen',)]))
        elif op < 0.6:
            mb.set_flags(rng.choice(live), {rng.choice(['\\Seen', '\\Flagged', 'x'])})
        elif op < 0.8:
            mb.expunge(rng.choice(live))
        elif op < 0.85:
            mb.compact()
        else:
            rep = rng.choice(reps)
            rep.sync(mb)
            assert rep.msgs == mb.snapshot(), seed
        if op > 0.97:
            mb = Mailbox(mb.uidvalidity + 1)
    for rep in reps:
        rep.sync(mb)
        assert rep.msgs == mb.snapshot(), seed
    return mb
for s in range(400):
    fuzz_mailbox(s)
# UID never reused over a long run with expunges of the highest message
mbx, seen = Mailbox(1), set()
rng = random.Random(3)
for _ in range(500):
    if rng.random() < 0.6 or not mbx.snapshot():
        u = mbx.append(); assert u not in seen; seen.add(u)
    else:
        mbx.expunge(max(mbx.snapshot()))
# a client resyncs from a state older than 100 changes ago, with big UIDs and mod-sequences (no string ordering)
mbx = Mailbox(1)
for _ in range(120):
    mbx.append()
rep = Replica(); rep.sync(mbx)
for u in range(100, 121):
    mbx.set_flags(u, {'\\Seen'})
mbx.expunge(9); mbx.expunge(10)
rep.sync(mbx)
assert rep.msgs == mbx.snapshot() and 9 not in rep.msgs and 10 not in rep.msgs and rep.msgs[110] == frozenset({'\\Seen'})
assert mbx.highest_modseq > 100 and mbx.changes_since(99) is not None

# ---- 6. DMARC: identifier alignment ------------------------------------------------------------------------------------
SUF = {'com', 'co.uk', 'org', 'github.io'}
assert org_domain('news.example.com', SUF) == 'example.com'
assert org_domain('a.b.example.co.uk', SUF) == 'example.co.uk'
assert org_domain('example.co.uk', SUF) == 'example.co.uk'
assert org_domain('com', SUF) is None and org_domain('co.uk', SUF) is None
assert org_domain('me.github.io', SUF) == 'me.github.io'
assert org_domain('X.Example.COM', SUF) == 'example.com'
assert aligned('example.com', 'alerts@news.example.com'.split('@')[1], 'r', SUF) is True        # RFC 7489 3.1.1 example
assert aligned('example.com', 'news.example.com', 's', SUF) is False                            # strict: exact match only
assert aligned('example.com', 'example.com', 's', SUF) is True
assert aligned('com', 'example.com', 'r', SUF) is False                                         # "d=com" never aligns
assert aligned('evil-example.com', 'example.com', 'r', SUF) is False                            # a suffix of the string is not a parent domain
assert aligned('example.com', 'badexample.com', 'r', SUF) is False
assert aligned('a.co.uk', 'b.co.uk', 'r', SUF) is False                                         # different registrants under one public suffix
assert aligned('x.me.github.io', 'y.me.github.io', 'r', SUF) is True
assert aligned('me.github.io', 'you.github.io', 'r', SUF) is False


def ref_org(d, suffixes):
    """Brute force: walk the ancestors from the TLD downward; the organizational domain is the first one that is not a public suffix."""
    labels = d.lower().split('.')
    for k in range(1, len(labels) + 1):
        cand = '.'.join(labels[-k:])
        if not (cand in suffixes or k == 1):
            return cand
    return None


def ref_pass(frm, spf, dkims, ms, md, suffixes):
    cands = []
    if spf[0] == 'pass':
        cands.append((spf[1], ms))
    for res, dom in dkims:
        if res == 'pass':
            cands.append((dom, md))
    for dom, mode in cands:
        if mode == 's':
            ok = dom.lower() == frm.lower()
        else:
            a, b = ref_org(dom, suffixes), ref_org(frm, suffixes)
            ok = a is not None and a == b
        if ok:
            return 'pass'
    return 'fail'


names = ['example.com', 'news.example.com', 'a.news.example.com', 'evil-example.com', 'badexample.com', 'example.co.uk',
         'mail.example.co.uk', 'other.co.uk', 'com', 'co.uk', 'me.github.io', 'you.github.io', 'x.me.github.io', 'EXAMPLE.com', 'org']
for a in names:
    for b in names:
        for mode in 'rs':
            exp = (a.lower() == b.lower()) if mode == 's' else (ref_org(a, SUF) is not None and ref_org(a, SUF) == ref_org(b, SUF))
            assert aligned(a, b, mode, SUF) == exp, (a, b, mode)
rng = random.Random(5)
for _ in range(3000):
    frm = rng.choice(names)
    spf = (rng.choice(['pass', 'fail', 'none']), rng.choice(names))
    dk = [(rng.choice(['pass', 'fail']), rng.choice(names)) for _ in range(rng.randint(0, 3))]
    ms, md = rng.choice('rs'), rng.choice('rs')
    assert dmarc_result(frm, spf, dk, ms, md, SUF) == ref_pass(frm, spf, dk, ms, md, SUF), (frm, spf, dk, ms, md)
# a failed check never counts even when the domain aligns; an unaligned pass never counts either
assert dmarc_result('example.com', ('fail', 'example.com'), [('fail', 'example.com')], 'r', 'r', SUF) == 'fail'
assert dmarc_result('example.com', ('pass', 'bounce.mailer.net'), [('pass', 'mailer.net')], 'r', 'r', SUF) == 'fail'
assert dmarc_result('example.com', ('pass', 'bounce.mailer.net'), [('pass', 'news.example.com')], 'r', 'r', SUF) == 'pass'
assert dmarc_result('example.com', ('pass', 'mail.example.com'), [], 'r', 's', SUF) == 'pass'
assert dmarc_result('example.com', ('pass', 'mail.example.com'), [], 's', 's', SUF) == 'fail'

# ---- 7. stale-wording locks and cited figures --------------------------------------------------------------------------
need('Do this after', 'Last reviewed: 27 November 2026', 'RFC 5321', 'RFC 3501', 'RFC 7489', 'RFC 8620', 'RFC 7162', 'RFC 3464',
     'at least 30 minutes', '4-5 days', '5,000 messages per day', '0.3%', 'Message-ID')
assert len(re.findall(r'^\d+\. ', src.split('## Drills')[1].split('## Homework')[0], re.M)) == 8, 'eight drills'
for bad in ('lakh', 'crore', 'LPA'):
    forbid(bad)
print('sy63 code checks passed')
