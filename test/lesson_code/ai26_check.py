"""Runs the python code blocks from data/new_lessons/ai26-dpo-alignment.md against reference checks
(direct formulas, finite differences, enumeration, and the closed-form KL-regularised optimum)."""
import re, sys, random, math, itertools, statistics
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
sft_loss, sigmoid, softplus = ns['sft_loss'], ns['sigmoid'], ns['softplus']
reward_model_loss, ranking_loss, dpo_loss_and_grad = ns['reward_model_loss'], ns['ranking_loss'], ns['dpo_loss_and_grad']
math_reward, group_advantages, kl_estimate = ns['math_reward'], ns['group_advantages'], ns['kl_estimate']
random.seed(26)

# --- helpers against the textbook definitions
for z in [-800, -50, -1, -1e-9, 0, 1e-9, 1, 50, 800]:
    ref_sig = 1 / (1 + math.exp(-z)) if z > -700 else 0.0
    assert abs(sigmoid(z) - ref_sig) < 1e-12
    if abs(z) < 50:
        assert abs(softplus(z) - math.log(1 + math.exp(z))) < 1e-12
assert softplus(800) == 800 and softplus(-800) < 1e-300

# --- SFT: mean NLL over response tokens only
for _ in range(200):
    n = random.randint(1, 20)
    lps = [-random.random() * 5 for _ in range(n)]
    mask = [random.random() < 0.5 for _ in range(n)]
    if not any(mask): mask[-1] = True
    want = statistics.fmean(-lp for lp, m in zip(lps, mask) if m)
    assert abs(sft_loss(lps, mask) - want) < 1e-12
assert abs(sft_loss([-100.0, -1.0, -3.0], [False, True, True]) - 2.0) < 1e-12   # prompt token ignored

# --- reward model: Bradley-Terry NLL, and the ranking average over C(K,2) pairs
for _ in range(200):
    a, b = random.uniform(-10, 10), random.uniform(-10, 10)
    assert abs(reward_model_loss(a, b) - (-math.log(1 / (1 + math.exp(-(a - b)))))) < 1e-9
for k in range(2, 10):
    rs = sorted((random.uniform(-3, 3) for _ in range(k)), reverse=True)
    pairs = list(itertools.combinations(range(k), 2))
    assert len(pairs) == math.comb(k, 2)
    want = sum(-math.log(1 / (1 + math.exp(-(rs[i] - rs[j])))) for i, j in pairs) / math.comb(k, 2)
    assert abs(ranking_loss(rs) - want) < 1e-9
assert math.comb(6, 2) == 15                                                    # drill 2

# --- DPO loss and gradient vs the paper's formula and central finite differences
def ref_dpo(lw, ll, rw, rl, beta):
    z = beta * (lw - rw) - beta * (ll - rl)
    return -math.log(1 / (1 + math.exp(-z)))
for _ in range(500):
    lw, ll, rw, rl = (random.uniform(-40, -1) for _ in range(4))
    beta = random.choice([0.01, 0.1, 0.5, 1.0])
    loss, gw, gl = dpo_loss_and_grad(lw, ll, rw, rl, beta)
    assert abs(loss - ref_dpo(lw, ll, rw, rl, beta)) < 1e-9
    h = 1e-5
    fw = (ref_dpo(lw + h, ll, rw, rl, beta) - ref_dpo(lw - h, ll, rw, rl, beta)) / (2 * h)
    fl = (ref_dpo(lw, ll + h, rw, rl, beta) - ref_dpo(lw, ll - h, rw, rl, beta)) / (2 * h)
    assert abs(gw - fw) < 1e-6 and abs(gl - fl) < 1e-6, (gw, fw, gl, fl)
    assert gw <= 0 <= gl                                        # descent raises chosen, lowers rejected

# worked numbers in the lesson
loss, gw, gl = dpo_loss_and_grad(-12, -15, -14, -13, 0.1)
assert round(loss, 3) == 0.513 and round(gl / 0.1, 3) == 0.401
loss2, gw2, gl2 = dpo_loss_and_grad(-15, -12, -14, -13, 0.1)
assert round(loss2, 3) == 0.798 and round(gl2 / 0.1, 3) == 0.550
# drill 5: the weight shrinks as the margin grows
ws = [dpo_loss_and_grad(-10 + m, -10 - m, -10, -10, 0.1)[2] for m in range(0, 50, 5)]
assert all(a > b for a, b in zip(ws, ws[1:]))

# --- the toy that proves the derivation: DPO on exact Bradley-Terry data converges to pi_ref*exp(r/beta)/Z
def log_softmax(th):
    m = max(th); z = math.log(sum(math.exp(t - m) for t in th)) + m
    return [t - z for t in th]
def train_tabular(pi_ref, r, beta, steps=20000, lr=0.5):
    n = len(r); th = [math.log(p) for p in pi_ref]
    ref = [math.log(p) for p in pi_ref]
    for _ in range(steps):
        lp = log_softmax(th); pi = [math.exp(x) for x in lp]
        g_lp = [0.0] * n
        for i, j in itertools.combinations(range(n), 2):
            pij = 1 / (1 + math.exp(-(r[i] - r[j])))          # P(i preferred over j)
            for w, l, prob in ((i, j, pij), (j, i, 1 - pij)):
                _, gw_, gl_ = dpo_loss_and_grad(lp[w], lp[l], ref[w], ref[l], beta)
                g_lp[w] += prob * gw_; g_lp[l] += prob * gl_
        s = sum(g_lp)
        g_th = [g_lp[m] - pi[m] * s for m in range(n)]        # chain rule through log-softmax
        th = [t - lr * g for t, g in zip(th, g_th)]
    return [math.exp(x) for x in log_softmax(th)]
for pi_ref, r, beta in [([0.4, 0.3, 0.2, 0.1], [0.0, 1.0, 2.0, 0.5], 1.0),
                        ([0.25, 0.25, 0.25, 0.25], [1.0, 0.0, 0.3, 0.6], 0.5),
                        ([0.7, 0.1, 0.1, 0.1], [0.0, 0.4, 0.2, 0.1], 0.2)]:
    w = [p * math.exp(x / beta) for p, x in zip(pi_ref, r)]
    closed = [x / sum(w) for x in w]
    got = train_tabular(pi_ref, r, beta)
    assert all(abs(a - b) < 1e-4 for a, b in zip(got, closed)), (got, closed)

# --- verifiable reward
assert math_reward("so the total is 12. Answer: 12", 12) == 1.0
assert math_reward("Answer: 7 ... wait, Answer: 12", 12) == 1.0       # last answer counts
assert math_reward("Answer: 12 ... no, Answer: 7", 12) == 0.0
assert math_reward("the answer is 12", 12) == 0.0                       # wrong format earns nothing
assert math_reward("Answer: -3.5", -3.5) == 1.0 and math_reward("Answer: 12.0", 12) == 1.0
assert math_reward("", 1) == 0.0

# --- GRPO advantages vs statistics module; zero-variance groups give zero signal
for _ in range(300):
    rs = [random.choice([0.0, 1.0, 0.5, random.random()]) for _ in range(random.randint(2, 16))]
    adv = group_advantages(rs)
    mu, sd = statistics.fmean(rs), statistics.pstdev(rs)
    for a, x in zip(adv, rs):
        assert abs(a - (x - mu) / (sd + 1e-6)) < 1e-9
    assert abs(sum(adv)) < 1e-6 * len(rs)
adv = group_advantages([1, 0, 0, 1])
assert all(abs(a - s) < 1e-5 for a, s in zip(adv, [1, -1, -1, 1]))       # drill 7
assert group_advantages([1, 1, 1, 1]) == [0.0, 0.0, 0.0, 0.0]
assert group_advantages([0, 0, 0]) == [0.0, 0.0, 0.0]

# --- KL estimator: never negative, zero iff equal, and unbiased: E_{x~pi}[k] = KL(pi || ref) exactly
for _ in range(300):
    n = random.randint(2, 8)
    p = [random.random() + 1e-3 for _ in range(n)]; s = sum(p); p = [x / s for x in p]
    q = [random.random() + 1e-3 for _ in range(n)]; s = sum(q); q = [x / s for x in q]
    est = sum(pi * kl_estimate(math.log(pi), math.log(qi)) for pi, qi in zip(p, q))
    kl = sum(pi * math.log(pi / qi) for pi, qi in zip(p, q))
    assert abs(est - kl) < 1e-12, (est, kl)
    assert all(kl_estimate(math.log(pi), math.log(qi)) >= 0 for pi, qi in zip(p, q))
assert kl_estimate(-2.0, -2.0) == 0.0
print("ai26 code checks passed")
