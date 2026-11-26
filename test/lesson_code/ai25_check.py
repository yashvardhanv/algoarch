"""Runs the python code blocks from data/new_lessons/ai25-constrained-generation.md against reference checks
(a regular expression and brute-force enumeration of the language), and asserts the worked numbers."""
import re, sys, random, math, itertools
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
masked_softmax, SegmentDFA, LABEL_SCHEMA = ns['masked_softmax'], ns['SegmentDFA'], ns['LABEL_SCHEMA']
walk, build_index, allowed_tokens, constrained_decode = ns['walk'], ns['build_index'], ns['allowed_tokens'], ns['constrained_decode']
random.seed(25)

REGEX = re.compile(r'\{"label":"(pos|neg)","n":(0|[1-9][0-9]*)\}')
dfa = SegmentDFA(LABEL_SCHEMA)

# --- reference language: every member with n < 10**5 (enough for every prefix with <= 4 digits)
LANG = ['{"label":"%s","n":%d}' % (lab, n) for lab in ('pos', 'neg') for n in range(10**5)]
PREFIXES = set()
for w in LANG:
    if len(w) <= 25:
        for i in range(len(w) + 1):
            PREFIXES.add(w[:i])
def ref_viable(s):
    """s is a prefix of some member of the language (exact for len(s) <= 24, i.e. at most 5 digits after n:)."""
    return s in PREFIXES

# --- DFA vs regex and prefix set, on members, on mutations of members, and on random strings
alphabet = '{}":,labeposngx0123456789 '
def run(text):
    st = walk(dfa, dfa.start, text)
    return st
samples = random.sample(LANG, 400) + ['{"label":"pos","n":0}', '{"label":"neg","n":40}']
for w in samples:
    assert run(w) is not None and dfa.accepting(run(w)), w
    for _ in range(5):
        i = random.randrange(len(w)); m = w[:i] + random.choice(alphabet) + w[i + 1:]
        st = run(m)
        assert (st is not None and dfa.accepting(st)) == bool(REGEX.fullmatch(m)), m
    for i in range(len(w) + 1):
        p = w[:i]
        if len(p) <= 24:
            assert (run(p) is not None) == ref_viable(p), p
for _ in range(3000):
    s = '{"label":"' + ''.join(random.choice(alphabet) for _ in range(random.randint(0, 12)))
    if len(s) > 24: continue
    st = run(s)
    assert (st is not None) == ref_viable(s), s
    assert (st is not None and dfa.accepting(st)) == bool(REGEX.fullmatch(s)), s
for bad in ['{"label":"pos","n":01}', '{"label":"pos","n":}', '{"label":"po","n":1}', '{"label":"pos","n":1}x']:
    st = run(bad)
    assert not (st is not None and dfa.accepting(st)), bad

# --- masked softmax vs independent renormalisation
for _ in range(300):
    toks = list(range(random.randint(1, 12)))
    logits = {t: random.uniform(-20, 20) for t in toks}
    allowed = set(random.sample(toks, random.randint(1, len(toks))))
    p = masked_softmax(logits, allowed)
    full = {t: math.exp(logits[t]) for t in toks}
    z = sum(full[t] for t in allowed)
    for t in toks:
        want = full[t] / z if t in allowed else 0.0
        assert abs(p[t] - want) < 1e-12 and (t in allowed or p[t] == 0.0)

# --- the toy vocabulary used for the lesson's illustrative numbers
TOY_VOCAB = dict(enumerate([
    '{', '"', 'label', ':', 'pos', 'neg', ',', 'n', '0', '1', '4', '7', '12', '}',
    '{"', '":"', '","', '":', 'po', 's', 'ne', 'g', 'x', ' ', '1}', 'label":"', '","n":',
]))
EOS = 'EOS'

def ref_index_entry(prefix_text, vocab):
    """Brute force: token t is allowed after prefix_text iff prefix_text + t is a viable prefix AND some
    continuation in this vocabulary finishes. Finishing is checked by BFS over viable texts (bounded length)."""
    out = set()
    for tok, text in vocab.items():
        s = prefix_text + text
        if ref_viable(s) and can_finish(s, vocab):
            out.add(tok)
    return out

_finish_memo = {}
def can_finish(s, vocab, limit=24):
    if s in _finish_memo: return _finish_memo[s]
    seen, stack, ok = {s}, [s], False
    while stack:
        cur = stack.pop()
        if REGEX.fullmatch(cur): ok = True; break
        for text in vocab.values():
            nxt = cur + text
            if len(nxt) <= limit and nxt not in seen and ref_viable(nxt):
                seen.add(nxt); stack.append(nxt)
    _finish_memo[s] = ok
    return ok

def check_vocab(vocab, n_decodes):
    _finish_memo.clear()                    # the memo is per vocabulary
    index = build_index(dfa, vocab)
    # every legal move from the start, explored through short prefixes, agrees with brute force
    frontier = [('', dfa.start)] if dfa.start in index else []
    if not index:
        assert not can_finish('', vocab)
        return index
    seen = set()
    while frontier:
        text, st = frontier.pop()
        if text in seen or len(text) > 18: continue
        seen.add(text)
        got = set(index[st])
        _finish_memo.clear() if len(_finish_memo) > 200000 else None
        assert got == ref_index_entry(text, vocab), (text, got)
        for tok, nst in index[st].items():
            assert nst == walk(dfa, st, vocab[tok])
            frontier.append((text + vocab[tok], nst))
    # random "models": every finished output matches the regex, every unfinished one is a viable prefix
    for _ in range(n_decodes):
        table = {}
        def logits_fn(prefix):
            key = tuple(prefix)
            if key not in table:
                table[key] = {t: random.gauss(0, 3) for t in list(vocab) + [EOS]}
            return table[key]
        toks, finished = constrained_decode(logits_fn, index, dfa, EOS, random.choice([3, 8, 40]))
        text = ''.join(vocab[t] for t in toks)
        if finished:
            assert REGEX.fullmatch(text), text
        else:
            st = walk(dfa, dfa.start, text)
            assert st is not None and st in index
    return index

index = check_vocab(TOY_VOCAB, 400)
n_states = len(index)
max_legal = max(len(allowed_tokens(index, dfa, s, EOS)) for s in index)
print("toy vocab:", len(TOY_VOCAB), "tokens;", n_states, "live states; max legal per state", max_legal)
assert len(TOY_VOCAB) == 27 and n_states == 19 and max_legal == 7

# EOS only in accepting states
for s in index:
    assert (EOS in allowed_tokens(index, dfa, s, EOS)) == dfa.accepting(s)

# dead-end pruning (drill 4): 'po' is legal character-wise but cannot be finished without 's'
v = {0: '{"label":"', 1: 'po', 2: 'pos', 3: 'neg', 4: '","n":', 5: '7', 6: '}'}
idx = check_vocab(v, 100)
after_open = walk(dfa, dfa.start, '{"label":"')
assert set(idx[after_open]) == {2, 3}
assert walk(dfa, after_open, 'po') is not None           # legal prefix, yet pruned
# a vocabulary that can never close the object yields an empty index
assert build_index(dfa, {0: '{"label":"', 1: 'pos', 2: '","n":', 3: '7'}) == {}

# random vocabularies of fragments
fragments = ['{', '"', 'label', ':', 'pos', 'neg', ',', 'n', '0', '3', '9', '30', '}', '{"', '":"', '","', '":',
             'po', 's', 'ne', 'g', 'p', 'o', 'e', 'l', 'a', 'b', '"label', 'n":', '0}', '9}', 'x', 'lab', 'el']
for _ in range(25):
    vocab = dict(enumerate(random.sample(fragments, random.randint(6, len(fragments)))))
    check_vocab(vocab, 40)

# an unconstrained random model almost never produces a valid object (why masking exists)
valid = 0
for _ in range(300):
    toks = [random.choice(list(TOY_VOCAB)) for _ in range(random.randint(3, 12))]
    valid += bool(REGEX.fullmatch(''.join(TOY_VOCAB[t] for t in toks)))
assert valid < 5
print("ai25 code checks passed")
