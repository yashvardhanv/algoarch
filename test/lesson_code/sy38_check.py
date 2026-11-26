"""Runs the python code blocks from data/new_lessons/sy38-collaborative-docs-crdt.md: OT transforms against an
identity-based model of intention, RGA against plain list edits and random delivery orders, and the worked numbers."""
import re, sys, random
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
apply, transform, RGA, HEAD, midpoint = ns['apply'], ns['transform'], ns['RGA'], ns['HEAD'], ns['midpoint']
random.seed(38)

# ---------------- OT ----------------
def random_op(s, site):
    if s and random.random() < 0.45:
        return ('del', random.randrange(len(s)), site)
    return ('ins', random.randint(0, len(s)), random.choice('XYZ'), site)

def intention(s, a, b):
    """Reference: track original characters by identity. Inserts go into a gap of the original text;
    two inserts in the same gap are ordered by site; deletes remove one original character."""
    deleted = {op[1] for op in (a, b) if op[0] == 'del'}
    gaps = {}
    for op in (a, b):
        if op[0] == 'ins':
            gaps.setdefault(op[1], []).append(op)
    out = []
    for g in range(len(s) + 1):
        for op in sorted(gaps.get(g, []), key=lambda o: o[3]):
            out.append(op[2])
        if g < len(s) and g not in deleted:
            out.append(s[g])
    return ''.join(out)

pairs = 0
for _ in range(6000):
    s = ''.join(random.choice('abc') for _ in range(random.randint(0, 6)))
    sa, sb = random.sample([1, 2, 3, 4], 2)
    a, b = random_op(s, sa), random_op(s, sb)
    left = apply(apply(s, a), transform(b, a))
    right = apply(apply(s, b), transform(a, b))
    assert left == right, (s, a, b, left, right)
    assert left == intention(s, a, b), (s, a, b, left, intention(s, a, b))
    pairs += 1

# worked example: CAT
ana, ben = ('ins', 1, 'H', 1), ('ins', 3, 'S', 2)
assert apply(apply('CAT', ana), ben) == 'CHAST' and apply(apply('CAT', ben), ana) == 'CHATS'
assert transform(ben, ana) == ('ins', 4, 'S', 2)
assert apply(apply('CAT', ana), transform(ben, ana)) == 'CHATS' == apply(apply('CAT', ben), transform(ana, ben))
assert transform(('del', 2, 1), ('del', 2, 2)) is None

# ---------------- RGA ----------------
def local_edit(r):
    t = r.text()
    if t and random.random() < 0.35:
        i = random.randrange(len(t))
        op = r.delete(i)
        assert r.text() == t[:i] + t[i + 1:], 'local delete did not act like a list delete'
    else:
        i, ch = random.randint(0, len(t)), random.choice('abcdefgh')
        op = r.insert(i, ch)
        assert r.text() == t[:i] + ch + t[i:], ('local insert landed in the wrong place', t, i, ch, r.text())
    return op

sims = 0
for trial in range(300):
    names = ['a', 'b', 'c']
    reps = {n: RGA(n) for n in names}
    log = []                                     # every op, in creation order
    inbox = {n: [] for n in names}               # ops not yet delivered to n
    for step in range(random.randint(1, 60)):
        n = random.choice(names)
        if inbox[n] and random.random() < 0.5:
            # deliver a random undelivered op (out of order), sometimes twice
            op = inbox[n].pop(random.randrange(len(inbox[n])))
            reps[n].receive(op)
            if random.random() < 0.1:
                reps[n].receive(op)
        else:
            op = local_edit(reps[n])
            log.append(op)
            for m in names:
                if m != n:
                    inbox[m].append(op)
    for n in names:
        random.shuffle(inbox[n])
        for op in inbox[n]:
            reps[n].receive(op)
        assert not reps[n].pending
    texts = {reps[n].text() for n in names}
    assert len(texts) == 1, texts
    # a fresh replica receiving every op in a random order agrees too
    fresh = RGA('z')
    shuffled = log[:]
    random.shuffle(shuffled)
    for op in shuffled:
        fresh.receive(op)
    assert fresh.text() in texts and not fresh.pending
    sims += 1

# interleaving case from Kleppmann et al.: sequentially typed words at the same spot stay contiguous
for _ in range(50):
    a, b = RGA('a'), RGA('b')
    base = [a.insert(i, ch) for i, ch in enumerate('Hello!')]
    for op in base:
        b.receive(op)
    oa = [a.insert(5 + i, ch) for i, ch in enumerate(' Alice')]
    ob = [b.insert(5 + i, ch) for i, ch in enumerate(' Charlie')]
    mix = oa + ob
    random.shuffle(mix)
    for op in mix:
        a.receive(op)
        b.receive(op)
    assert a.text() == b.text() and a.text() in ('Hello Alice Charlie!', 'Hello Charlie Alice!'), a.text()

# ---------------- fractional index precision ----------------
lo, hi, n = 0.5, 1.0, 0
while True:
    try:
        hi = midpoint(lo, hi)
    except ValueError:
        break
    n += 1
assert n == 52, n
assert 'after 52 inserts' in src
print('sy38 code checks passed (%d OT pairs, %d RGA simulations)' % (pairs, sims))
