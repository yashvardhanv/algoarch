"""Runs the python blocks of data/new_lessons/sy74-news-aggregator.md against references:
shingles and Jaccard from their definitions, MinHash as an unbiased estimator, the banding probability against a
simulation, near-duplicate clustering against exact pairwise components, entry de-duplication and ranking."""
import re, sys, math, random, itertools
src = open(sys.argv[1], encoding='utf-8').read()
ns = {}
for b in re.findall(r"```python\n(.*?)```", src, re.S):
    exec(b, ns)
shingles, jaccard, minhash, estimate = ns['shingles'], ns['jaccard'], ns['minhash'], ns['estimate']
band_keys, lsh_probability, Dedup = ns['band_keys'], ns['lsh_probability'], ns['Dedup']
FeedStore, next_interval, story_score = ns['FeedStore'], ns['next_interval'], ns['story_score']

# ---- shingles and Jaccard ------------------------------------------------------------------------------------------
assert shingles("The cat sat on the mat", 3) == {'the cat sat', 'cat sat on', 'sat on the', 'on the mat'}
assert shingles("The CAT, sat!  on the mat.", 3) == shingles("the cat sat on the mat", 3)      # case and punctuation do not matter
assert shingles("two words", 3) == {'two words'} and shingles("", 3) == set() and shingles("...", 3) == set()
assert jaccard({1, 2, 3}, {2, 3, 4}) == 2 / 4 and jaccard({1}, {1}) == 1.0 and jaccard({1}, {2}) == 0.0
assert jaccard(set(), set()) == 0.0                                    # two empty documents are not "the same story"
rnd = random.Random(2)
for _ in range(200):
    a = {rnd.randrange(30) for _ in range(rnd.randint(0, 20))}
    b = {rnd.randrange(30) for _ in range(rnd.randint(0, 20))}
    want = len([x for x in a if x in b]) / len(set(list(a) + list(b))) if (a or b) else 0.0
    assert abs(jaccard(a, b) - want) < 1e-12

# ---- MinHash: the fraction of equal minima estimates Jaccard ---------------------------------------------------------
def pair_with_jaccard(common, unique, tag):
    a = {f"{tag}c{i}" for i in range(common)} | {f"{tag}a{i}" for i in range(unique)}
    b = {f"{tag}c{i}" for i in range(common)} | {f"{tag}b{i}" for i in range(unique)}
    return a, b
for common, unique, j in ((5, 10, 0.2), (24, 12, 0.5), (32, 4, 0.8), (38, 1, 0.95)):
    trials, total = 200, 0.0
    for t in range(trials):
        a, b = pair_with_jaccard(common, unique, f"t{t}")
        assert abs(jaccard(a, b) - j) < 1e-12
        total += estimate(minhash(a, 100), minhash(b, 100))
    sigma = math.sqrt(j * (1 - j) / 100)
    assert abs(total / trials - j) < 4 * sigma / math.sqrt(trials) + 1e-9, (j, total / trials)
assert estimate(minhash({'x', 'y'}, 50), minhash({'x', 'y'}, 50)) == 1.0
assert estimate(minhash({'x'}, 50), minhash({'q'}, 50)) < 0.1
assert len(minhash({'x'}, 37)) == 37 and minhash(set(), 10) is None
# the signature really holds minima (a max-based version estimates equally well, so test the values directly)
_base, COEFFS, P = ns['_base'], ns['COEFFS'], ns['P']
shs = {'alpha beta gamma', 'beta gamma delta', 'gamma delta epsilon', 'delta epsilon zeta'}
sig = minhash(shs, 20)
for (ca, cb), m in zip(COEFFS[:20], sig):
    values = [(ca * _base(x) + cb) % P for x in shs]
    assert m == min(values) and m <= max(values)

# ---- the banding probability against a simulation -----------------------------------------------------------------------
BANDS, ROWS = 20, 5
for common, unique, j in ((18, 6, 0.6), (28, 6, 0.7), (32, 4, 0.8), (36, 2, 0.9), (24, 12, 0.5)):
    trials, hits = 1500, 0
    for t in range(trials):
        a, b = pair_with_jaccard(common, unique, f"b{j}_{t}")
        ka, kb = set(band_keys(minhash(a, 100), BANDS, ROWS)), set(band_keys(minhash(b, 100), BANDS, ROWS))
        hits += bool(ka & kb)
    p = lsh_probability(j, BANDS, ROWS)
    assert abs(hits / trials - p) < 4 * math.sqrt(p * (1 - p) / trials) + 0.004, (j, hits / trials, p)
assert abs(lsh_probability(0.8, 20, 5) - 0.99965) < 1e-4 and abs(lsh_probability(0.5, 20, 5) - 0.4701) < 1e-3
assert lsh_probability(0, 20, 5) == 0 and lsh_probability(1, 20, 5) == 1
assert len(set(band_keys([7] * 100, 20, 5))) == 20                  # equal segments in different bands must not collide
assert len(band_keys(list(range(100)), 20, 5)) == 20 and len({k for k in band_keys(list(range(100)), 20, 5)}) == 20

# ---- near-duplicate clustering against exact pairwise components ---------------------------------------------------------
vocab = [f"w{i}" for i in range(400)]
def make_docs(seed, max_edits):
    r = random.Random(seed)
    docs = []
    for s in range(12):                                                  # 12 stories, each with a few rewrites
        base = [r.choice(vocab) for _ in range(60)]
        for _ in range(r.randint(1, 4)):
            d = base[:]
            for _ in range(r.randint(0, max_edits)):                      # a few edited words
                d[r.randrange(len(d))] = r.choice(vocab)
            docs.append(' '.join(d))
    docs += [' '.join(r.choice(vocab) for _ in range(60)) for _ in range(10)]   # unrelated one-offs
    r.shuffle(docs)
    return docs

def run(max_edits, threshold, seeds=6):
    found = total = 0
    for seed in range(seeds):
        docs = make_docs(seed, max_edits)
        dd = Dedup(threshold=threshold)
        ids = [dd.add(d) for d in docs]
        sets = [shingles(d) for d in docs]
        for i, k in itertools.combinations(range(len(docs)), 2):
            if jaccard(sets[i], sets[k]) >= threshold:
                total += 1
                found += ids[i] == ids[k]
        # precision: stories are unions of verified pairs, so members are linked by chains of true >= threshold pairs
        groups = {}
        for i, sid in enumerate(ids):
            groups.setdefault(sid, []).append(i)
        for members in groups.values():
            seen, stack = {members[0]}, [members[0]]
            while stack:
                x = stack.pop()
                for y in members:
                    if y not in seen and jaccard(sets[x], sets[y]) >= threshold:
                        seen.add(y); stack.append(y)
            assert seen == set(members), "a story must be connected by verified pairs"
    return found, total
found, total = run(max_edits=1, threshold=0.8)                            # light rewrites at the default threshold
assert total > 20 and found / total > 0.99, (found, total)
found2, total2 = run(max_edits=6, threshold=0.5)                          # heavy rewrites near the curve's shoulder
assert total2 > 100 and 0.7 < found2 / total2 < 0.9, (found2, total2)     # the S-curve at work: about four pairs in five
print("recall light/heavy", found, total, found2, total2)
# a pair exactly at the threshold is merged (>=): 'a b c d e' and 'a b c d x' share 2 of 4 shingles. Use many bands of one row so the pair is surely a candidate.
dd = Dedup(threshold=0.5, bands=100, rows=1)
assert jaccard(shingles('a b c d e'), shingles('a b c d x')) == 0.5
assert dd.add('a b c d e') == dd.add('a b c d x')
dd = Dedup(threshold=0.51, bands=100, rows=1)
assert dd.add('a b c d e') != dd.add('a b c d x')
# a document with no words gets its own story and never merges
dd = Dedup(0.5)
a, b, c = dd.add(""), dd.add(""), dd.add("hello there general kenobi you are a bold one")
assert len({a, b, c}) == 3
d1 = dd.add("hello there general kenobi you are a bold one")
assert d1 == c

# ---- entries: identity is the id, order is the updated time ---------------------------------------------------------------
st = FeedStore()
assert st.ingest([('urn:1', 10, 'a'), ('urn:2', 11, 'b')]) == [('urn:1', 10, 'a'), ('urn:2', 11, 'b')]
assert st.ingest([('urn:1', 10, 'a')]) == []                              # the same entry again: nothing new
assert st.ingest([('urn:1', 20, 'a2')]) == [('urn:1', 20, 'a2')]          # a revision: reported, same id
assert st.ingest([('urn:1', 15, 'old')]) == []                            # an out-of-order older copy is ignored
assert st.seen['urn:1'] == 20 and len(st.seen) == 2
assert st.ingest([('urn:3', 1, 'x'), ('urn:3', 1, 'x')]) == [('urn:3', 1, 'x')]   # duplicates inside one batch

# ---- polling cadence --------------------------------------------------------------------------------------------------------
assert next_interval([], 60, 3600) == 3600
assert next_interval([600, 600, 600], 60, 3600) == 300
assert next_interval([10, 10, 10], 60, 3600) == 60 and next_interval([100000], 60, 3600) == 3600
assert next_interval([100, 900, 300, 50000], 60, 3600) == 300           # even count: the median is the mean of the middle two (600), halved
assert next_interval([100, 300, 500], 60, 3600) == 150                   # the median gap, halved

# ---- ranking ----------------------------------------------------------------------------------------------------------------
assert abs(story_score(1, 0) - 1.0) < 1e-12
assert abs(story_score(1, 6, half_life_hours=6) - 0.5) < 1e-12 and abs(story_score(1, 12, half_life_hours=6) - 0.25) < 1e-12
assert story_score(4, 0) > story_score(2, 0) > story_score(1, 0) and abs(story_score(4, 0) - 3.0) < 1e-12
assert story_score(1, 0, source_weight=2.0) == 2.0
assert story_score(8, 24, half_life_hours=6) < story_score(1, 0)          # a day-old big story loses to a fresh single report
assert story_score(1, 0.0) > story_score(1, 0.0001) > story_score(1, 5)
print("sy74 code checks passed")
