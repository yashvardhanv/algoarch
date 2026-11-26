"""Runs the python blocks of the sy55 file sync lesson against independent references: a from-scratch window hash for
chunk boundaries, a journal replay, exhaustive two-client interleavings, crash injection, a random multi-client model
run, and a brute-force cycle test for directory moves."""
import re, sys, random, itertools, collections, hashlib

src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
assert len(blocks) >= 3, 'expected the lesson code blocks'
ns = {}
for b in blocks:
    exec(b, ns)
sha, fixed_chunks, cdc_chunks, GEAR = ns['sha'], ns['fixed_chunks'], ns['cdc_chunks'], ns['GEAR']
BlockStore, MetaServer, Client, Crash, Tree = ns['BlockStore'], ns['MetaServer'], ns['Client'], ns['Crash'], ns['Tree']
rng = random.Random(55)

def rbytes(n, r=rng):
    return bytes(r.getrandbits(8) for _ in range(n))

# ---- 1. chunking -------------------------------------------------------------------------------------------------
assert sha(b'abc') == hashlib.sha256(b'abc').hexdigest()
assert fixed_chunks(b'', 4) == [] and fixed_chunks(b'abcdefghij', 4) == [b'abcd', b'efgh', b'ij']
assert len(GEAR) == 256 and len(set(GEAR)) == 256 and all(0 <= g < 2 ** 64 for g in GEAR)

def ref_cdc(data, bits, lo, hi):
    """Boundaries from a window hash recomputed from scratch at every byte (no rolling state)."""
    out, start = [], 0
    for i in range(len(data)):
        h = 0
        for j in range(64):
            if i - j < 0: break
            h = (h + (GEAR[data[i - j]] << j)) % 2 ** 64
        size = i + 1 - start
        if (size >= lo and h >> (64 - bits) == 0) or size >= hi:
            out.append(data[start:i + 1]); start = i + 1
    if start < len(data): out.append(data[start:])
    return out

for _ in range(60):
    d = rbytes(rng.randint(0, 1500))
    p = (rng.randint(3, 7), rng.randint(1, 40), rng.randint(60, 400))
    got = cdc_chunks(d, *p)
    assert got == ref_cdc(d, *p), p
    assert b''.join(got) == d
    assert all(len(c) <= p[2] for c in got) and all(len(c) >= p[1] for c in got[:-1])
run = next((v for v in (bytes([x]) * 1100 for x in range(256)) if set(map(len, ref_cdc(v, 6, 16, 512)[:-1])) == {512}), None)
assert run is not None, 'some constant byte has no natural boundary'            # such a run gets cut by the maximum alone
assert cdc_chunks(run, 6, 16, 512) == [run[:512]] * 2 + [run[:76]]
assert cdc_chunks(b'', 6, 16, 512) == []

# a few bytes inserted into a big file: fixed blocks all change after the edit, content-defined chunks resynchronise
def changed(old, new, chunker):
    have = {sha(c) for c in chunker(old)}
    return sum(1 for c in chunker(new) if sha(c) not in have), len(chunker(new))
fx, cd = [], []
r2 = random.Random(9)
for _ in range(60):
    base = rbytes(30000, r2)
    at = r2.randint(200, 3000)
    edited = base[:at] + rbytes(7, r2) + base[at:]
    f_changed, f_total = changed(base, edited, lambda d: fixed_chunks(d, 64))
    c_changed, c_total = changed(base, edited, lambda d: cdc_chunks(d, 6, 16, 512))
    fx.append(f_changed / f_total); cd.append(c_changed)
assert min(fx) > 0.8, min(fx)                 # an insert near the front rewrites almost every fixed block
assert max(cd) <= 8 and sum(cd) / len(cd) < 4, (max(cd), sum(cd) / len(cd))
# an in-place overwrite (same length) touches a single fixed block
base = rbytes(6400, r2)
assert changed(base, base[:3000] + b'ZZZZ' + base[3004:], lambda d: fixed_chunks(d, 64))[0] == 1

# ---- 2. block store, journal and clients -------------------------------------------------------------------------
def mk(n=2, size=8):
    store = BlockStore(); meta = MetaServer(store)
    return store, meta, [Client(chr(65 + i), meta, store, 'ns', lambda d: fixed_chunks(d, size)) for i in range(n)]

def no_dangling(meta, store):
    for rows in meta.journal.values():
        for _, _, bl in rows:
            assert bl is None or all(h in store.blocks for h in bl), 'journal row points at a missing block'

def replay(meta, store, nsid='ns'):
    files = {}
    for _, path, bl in meta.journal[nsid]:
        if bl is None: files.pop(path, None)
        else: files[path] = b''.join(store.blocks[h] for h in bl)
    return files

def quiesce(cs, rounds=5):
    for _ in range(rounds):
        for c in cs: c.push()
        for c in cs: c.pull()

# protocol: commit says which blocks are missing, upload them, commit again
store, meta, (a, b) = mk()
assert meta.commit('ns', 'f', [sha(b'12345678')], 0)[0] == 'need_blocks'
assert meta.commit('ns', 'f', [sha(b'12345678')], 0) == ('need_blocks', [sha(b'12345678')])
store.put(b'12345678')
assert meta.commit('ns', 'f', [sha(b'12345678')], 0) == ('ok', 1)
assert meta.commit('ns', 'f', [sha(b'12345678')], 0) == ('conflict', 1)            # stale base
assert meta.commit('ns', 'f', [sha(b'12345678')], 1) == ('ok', 2)
assert meta.list('ns', 0)[0][0] == 1 and [r[0] for r in meta.list('ns', 1)] == [2]

# dedup: identical content under two paths, and a small edit, upload only new blocks
store, meta, (a, b) = mk()
data = rbytes(64)                                    # 8 blocks of 8 bytes
a.write('one', data); a.write('two', data); a.push()
assert store.bytes_in == 64 and len(store.blocks) == len({data[i:i + 8] for i in range(0, 64, 8)})
a.write('one', data[:16] + b'XXXXXXXX' + data[24:]); a.push()
assert store.bytes_in == 72
b.pull(); assert b.files == a.files and b.files['two'] == data
no_dangling(meta, store)

# crash after uploading part of a file: the retry uploads only what is missing, and no row ever dangles
store, meta, (a, b) = mk()
data = rbytes(80)
a.write('big', data)
try:
    a.push(crash_after_blocks=4); assert False, 'should crash'
except Crash:
    pass
assert store.bytes_in == 32 and meta.journal['ns'] == [] and 'big' in a.dirty
no_dangling(meta, store)
a.push()
assert store.bytes_in == 80 and len(meta.journal['ns']) == 1 and not a.dirty
b.pull(); assert b.files['big'] == data

# crash after the commit but before the client recorded it: re-push is a no-op, not a duplicate or a conflict
store, meta, (a, b) = mk()
a.write('f', b'hello wo')
try:
    a.push(crash_after_commit=True); assert False
except Crash:
    pass
assert len(meta.journal['ns']) == 1
a.push(); a.pull()
assert len(meta.journal['ns']) == 1 and not a.dirty and a.files == {'f': b'hello wo'}

# two clients edit the same file from the same base, in every interleaving of push and pull
acts = ['A.push', 'B.push', 'A.pull', 'B.pull']
for order in itertools.permutations(acts):
    store, meta, (a, b) = mk()
    a.write('f', b'base base'); quiesce([a, b])
    assert a.files == b.files == {'f': b'base base'}
    a.write('f', b'edit by A'); b.write('f', b'edit by B')
    cl = {'A': a, 'B': b}
    for step in order:
        who, what = step.split('.'); getattr(cl[who], what)()
    quiesce([a, b])
    assert a.files == b.files == replay(meta, store), order
    assert sorted(a.files.values()) == [b'edit by A', b'edit by B'], (order, a.files)       # nothing lost
    assert len(a.files) == 2 and 'f' in a.files and any('conflicted copy' in p for p in a.files)
    no_dangling(meta, store)

# an edit on top of a pulled change is not a conflict
store, meta, (a, b) = mk()
a.write('f', b'one'); a.push(); b.pull(); b.write('f', b'two'); b.push(); a.pull()
assert a.files == b.files == {'f': b'two'} and len(meta.journal['ns']) == 2

# pulling your own earlier commit while a newer local edit is pending is not a conflict, and the cursor moves on
store, meta, (a, b) = mk()
a.write('f', b'version 1'); a.push(); a.write('f', b'version 2')
a.pull()
assert a.files == {'f': b'version 2'} and a.dirty == {'f'} and a.cursor == 1 and meta.list('ns', a.cursor) == []
a.push(); b.pull()
assert a.files == b.files == {'f': b'version 2'} and b.cursor == 2

# delete versus edit: the edit survives, the delete is dropped
store, meta, (a, b) = mk()
a.write('f', b'keep me'); quiesce([a, b])
a.remove('f'); b.write('f', b'edited!!')
b.push(); quiesce([a, b])
assert a.files == b.files == {'f': b'edited!!'}
# a plain delete propagates
a.remove('f'); quiesce([a, b])
assert a.files == b.files == {}

# random runs against the journal replay: three clients, edits, deletes, pushes, pulls and crashes
pool = [b'', b'x', b'same content!', rbytes(40, random.Random(1)), rbytes(40, random.Random(2)), rbytes(100, random.Random(3))]
for seed in range(300):
    rr = random.Random(seed)
    store, meta, cs = mk(3)
    for _ in range(rr.randint(5, 40)):
        c = rr.choice(cs); op = rr.random()
        if op < 0.35: c.write(rr.choice(['p', 'q', 'r']), rr.choice(pool))
        elif op < 0.45: c.remove(rr.choice(['p', 'q', 'r']))
        elif op < 0.65: c.push()
        elif op < 0.85: c.pull()
        else:
            try: c.push(crash_after_blocks=rr.randint(0, 3))
            except Crash: pass
        no_dangling(meta, store)
    quiesce(cs, 8)
    state = replay(meta, store)
    assert all(c.files == state for c in cs), seed
    assert all(c.cursor == len(meta.journal['ns']) for c in cs), seed
    n = len(meta.journal['ns']); quiesce(cs, 2)
    assert len(meta.journal['ns']) == n, seed                  # quiet means quiet
    assert store.bytes_in == sum(len(v) for v in store.blocks.values())      # each block received exactly once

# ---- 3. directory moves ----------------------------------------------------------------------------------------
def acyclic(parent):
    for n in parent:
        seen, x = set(), n
        while x is not None:
            if x in seen: return False
            seen.add(x); x = parent[x]
    return True

t = Tree()
drafts, archives = t.add(0, 'Drafts'), t.add(0, 'Archives')
january = t.add(drafts, 'January')
assert t.path_of(january) == '/Drafts/January'
assert t.move(archives, january) is True and t.path_of(archives) == '/Drafts/January/Archives'
assert t.move(drafts, archives) is False                       # would make Drafts its own grandparent
assert t.parent[drafts] == 0 and acyclic(t.parent)
u = Tree(); d2, a2 = u.add(0, 'Drafts'), u.add(0, 'Archives'); j2 = u.add(d2, 'January')
assert u.move(d2, a2) is True and u.move(a2, j2) is False       # the other arrival order: the other move loses
assert u.path_of(j2) == '/Archives/Drafts/January'
assert t.move(0, drafts) is False and t.move(drafts, drafts) is False

for seed in range(300):
    rr = random.Random(seed)
    t = Tree()
    ids = [0]
    for _ in range(rr.randint(1, 25)):
        ids.append(t.add(rr.choice(ids), 'n%d' % len(ids)))
    for _ in range(40):
        n, p = rr.choice(ids), rr.choice(ids)
        trial = dict(t.parent)
        if n != 0: trial[n] = p
        want = n != 0 and acyclic(trial)                         # brute force: apply, then look for a cycle
        before = dict(t.parent)
        assert t.move(n, p) == want, (seed, n, p)
        assert acyclic(t.parent)
        changed_keys = [k for k in t.parent if t.parent[k] != before[k]]
        assert len(changed_keys) <= 1                            # a move rewrites one parent pointer, whatever the subtree size
chain = Tree(); top = chain.add(0, 'top'); prev = top
for i in range(1000): prev = chain.add(prev, 'd%d' % i)
other = chain.add(0, 'other')
before = dict(chain.parent)
assert chain.move(top, other) and sum(1 for k in before if before[k] != chain.parent[k]) == 1
assert chain.path_of(prev).startswith('/other/top/d0/d1/')
print('sy55 code checks passed')
