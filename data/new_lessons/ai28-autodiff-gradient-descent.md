# Lesson 28 — Autodiff and Gradient Descent, with Optimizers

> **Priority:** ★★★★★ — every "how does training actually work?" question bottoms out here: what a gradient is, who computes it, and what an optimizer does with it.
>
> **Study time:** 75 minutes. **Do this after:** you need only the chain rule and Python. It comes before the language-model-from-scratch lesson.
>
> **Level:** core.

A neural network is a long composition of simple functions, and training means nudging its parameters to make one number, the loss, smaller. To do that you need the derivative of the loss with respect to every parameter, and you need it cheaply. Reverse-mode automatic differentiation gives you all of them for about the price of a small multiple of one forward pass. Gradient descent and its variants then decide what to do with them. Interviewers for ML-engineering roles ask for the idea behind both and sometimes for the code; this lesson builds a working engine of about forty lines and tests it against the numerical definition of a derivative.

*Visual (planned): a gradient-descent scene on the bowl in section 5, with three balls (SGD, momentum, Adam) rolling at once and the loss plotted underneath.*

---

## 1. Mental Model

> **Run the program forward and record, for every operation, how its output changes when each input changes. Then walk the record backwards, multiplying those local slopes together and adding up the contributions that arrive at the same variable. That is the chain rule, applied once, from the output to everything else.**

What follows from it:

- **One backward pass yields every gradient.** The output is one number (the loss) and the inputs are millions of parameters. Reverse mode computes the whole gradient in one backward sweep; forward mode needs one pass per input, which the Baydin et al. survey (section 3) states for functions from many inputs to one output.
- **Sharing means summing.** If a variable is used in two places, the gradient reaching it is the sum of the gradients from both places. Forgetting this is the classic autodiff bug, and the check for this lesson has tests aimed at it.
- **The gradient is only a direction.** Plain gradient descent steps `p <- p - lr * g`. Whether that converges, crawls or explodes depends on the learning rate against the curvature of the loss, not on the autodiff.
- **Optimizers are bookkeeping on gradients.** Momentum keeps a running velocity; Adam keeps running averages of the gradient and its square. Neither needs anything from the engine except the gradient.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "how does backprop work?" | reverse-mode autodiff: the forward pass records local slopes, the backward pass multiplies and sums them |
| "how would you test your gradients?" | compare with central finite differences on a few random inputs (section 4) |
| "loss goes to NaN or infinity after a few steps" | learning rate above the stability limit (section 5), then look for log(0), exp overflow, division by zero |
| "loss decreases but very slowly, directions differ wildly in scale" | ill-conditioning: momentum or an adaptive method, or rescale the inputs |
| "why does Adam have bias correction?" | its moving averages start at zero and would otherwise be too small early on (section 6) |
| "gradient of a shared weight is wrong" | accumulation: `+=`, never `=`; and reset gradients between steps |
| "why not differentiate symbolically or numerically?" | numeric costs two extra evaluations per parameter and is noisy: use it only as a check |

---

## 3. The Engine

Each `Value` stores a number, the `Value`s it was computed from, and the local slope of itself with respect to each of them. `backward` orders the nodes so that every node is processed before the nodes it was computed from, then pushes gradient from the output down to the leaves.

```python
import math

class Value:
    """A scalar that remembers how it was made, so gradients can flow back through it."""
    def __init__(self, data, parents=(), local_grads=()):
        self.data = float(data)
        self.grad = 0.0                  # d(output)/d(this), filled in by backward()
        self._parents = parents          # the Values this one was computed from
        self._local = local_grads        # d(this)/d(parent), one number per parent

    def __add__(self, o):
        o = o if isinstance(o, Value) else Value(o)
        return Value(self.data + o.data, (self, o), (1.0, 1.0))
    def __mul__(self, o):
        o = o if isinstance(o, Value) else Value(o)
        return Value(self.data * o.data, (self, o), (o.data, self.data))
    def __pow__(self, k):                # k is a plain number, not a Value
        return Value(self.data ** k, (self,), (k * self.data ** (k - 1),))
    def exp(self):
        e = math.exp(self.data); return Value(e, (self,), (e,))
    def log(self):
        return Value(math.log(self.data), (self,), (1.0 / self.data,))
    def tanh(self):
        t = math.tanh(self.data); return Value(t, (self,), (1.0 - t * t,))
    def relu(self):
        return Value(max(0.0, self.data), (self,), (1.0 if self.data > 0 else 0.0,))
    __radd__ = __add__
    __rmul__ = __mul__
    def __neg__(self): return self * -1.0
    def __sub__(self, o): return self + (-o if isinstance(o, Value) else -o)
    def __rsub__(self, o): return (-self) + o
    def __truediv__(self, o): return self * (o if isinstance(o, Value) else Value(o)) ** -1.0
    def __rtruediv__(self, o): return (self ** -1.0) * o

    def backward(self):
        order, seen, stack = [], set(), [(self, False)]      # iterative DFS: no recursion limit
        while stack:
            node, expanded = stack.pop()
            if expanded:
                order.append(node)                           # all parents already listed
            elif id(node) not in seen:
                seen.add(id(node))
                stack.append((node, True))
                stack.extend((p, False) for p in node._parents)
        self.grad = 1.0
        for node in reversed(order):                         # consumers before producers
            for parent, local in zip(node._parents, node._local):
                parent.grad += local * node.grad             # += : a node used twice sums both paths
```

Three details carry the weight:

- `parent.grad += local * node.grad`. The `+=` is the sharing rule. With `=`, the diamond `(x + 1) * (x + 2)` would report the slope through only one of its two paths.
- The ordering is a post-order depth-first walk with an explicit stack. A recursive version works on toy graphs and dies on a graph thousands of operations deep, which a long chain produces. The check builds a chain of 5000 multiplications.
- `grad` starts at zero and only grows. Calling `backward` twice without resetting doubles every gradient. A training loop that builds a fresh graph per step hides this until you reuse leaves (parameters) across steps: reset their gradients before each backward pass.

The slopes are ones from a calculus table: `d(a*b)/da = b`, `d(x^k)/dx = k*x^(k-1)`, `d tanh = 1 - tanh^2`. `relu` has slope 1 above zero and 0 at or below it; at exactly zero the derivative does not exist, libraries pick a convention, and so does this code.

---

## 4. Trust, but Check: Finite Differences

A derivative is a limit, so you can approximate it with two forward evaluations: `(f(x+h) - f(x-h)) / 2h`. The central form has error proportional to `h^2` rather than `h`. It costs two evaluations per parameter, which is why it is a test and never a trainer. Choose `h` around `1e-6` in double precision: much smaller and rounding error dominates, much larger and curvature does.

```python
def numeric_grad(f, xs, eps=1e-6):
    """Central finite differences: (f(x+h) - f(x-h)) / 2h, one coordinate at a time."""
    out = []
    for i in range(len(xs)):
        hi = list(xs); hi[i] += eps
        lo = list(xs); lo[i] -= eps
        out.append((f(*hi) - f(*lo)) / (2 * eps))
    return out

def sgd_step(params, grads, lr):
    return [p - lr * g for p, g in zip(params, grads)]

class Momentum:
    """v <- mu*v + g ; p <- p - lr*v   (the velocity form)."""
    def __init__(self, lr, mu=0.9):
        self.lr, self.mu, self.v = lr, mu, None
    def step(self, params, grads):
        if self.v is None: self.v = [0.0] * len(params)
        self.v = [self.mu * v + g for v, g in zip(self.v, grads)]
        return [p - self.lr * v for p, v in zip(params, self.v)]

class Adam:
    """Kingma & Ba, Algorithm 1: moving averages of g and g*g, each bias-corrected."""
    def __init__(self, lr=0.001, b1=0.9, b2=0.999, eps=1e-8):
        self.lr, self.b1, self.b2, self.eps = lr, b1, b2, eps
        self.m = self.s = None; self.t = 0
    def step(self, params, grads):
        if self.m is None: self.m, self.s = [0.0] * len(params), [0.0] * len(params)
        self.t += 1
        self.m = [self.b1 * m + (1 - self.b1) * g for m, g in zip(self.m, grads)]
        self.s = [self.b2 * s + (1 - self.b2) * g * g for s, g in zip(self.s, grads)]
        out = []
        for p, m, s in zip(params, self.m, self.s):
            m_hat = m / (1 - self.b1 ** self.t)               # undo the pull towards the zero start
            s_hat = s / (1 - self.b2 ** self.t)
            out.append(p - self.lr * m_hat / (math.sqrt(s_hat) + self.eps))
        return out
```

The gradient check is your first debugging move for any new operation: pick a function that uses it, compare `backward` against `numeric_grad` at a handful of random points, and expect agreement to roughly six digits. The check script runs three hundred random expression graphs through exactly this comparison, including ones that reuse sub-expressions, and tests the diamond and shared-node cases by hand.

---

## 5. Gradient Descent on a Bowl

Take `f(x, y) = 0.5 x^2 + 12.5 y^2`. The curvature is 1 along `x` and 25 along `y`. For plain gradient descent on a quadratic, each coordinate is multiplied by `1 - lr * curvature` every step, so:

- It converges only if `|1 - lr * 25| < 1`, that is `lr < 2/25 = 0.08`. The steepest direction sets the limit.
- Once `lr` is stable for `y`, the flat direction `x` shrinks by `1 - lr` per step. With `lr = 0.07` that is a factor 0.93: slow. The ratio of the largest to the smallest curvature (here 25) is the condition number, and it is what makes descent crawl.

The next block runs the engine on this bowl for 100 steps from `(1, 1)`, runs the gradient check on one function, and trains a line with the same engine.

```python
def quad(p):
    """f(x, y) = 0.5*x^2 + 12.5*y^2 : curvature 1 along x, 25 along y (an ill-conditioned bowl)."""
    x, y = Value(p[0]), Value(p[1])
    loss = 0.5 * x ** 2.0 + 12.5 * y ** 2.0
    loss.backward()
    return loss.data, [x.grad, y.grad]

def run(step_fn, steps=100, start=(1.0, 1.0)):
    p = list(start)
    for _ in range(steps):
        _, g = quad(p)
        p = step_fn(p, g)
    return quad(p)[0]

RESULTS = {}

def demo():
    lines = []
    probe = lambda x, y: (x * y).tanh() + x.exp() / (y * y + 1.0)
    pt = [0.7, -1.3]
    vx, vy = Value(pt[0]), Value(pt[1]); probe(vx, vy).backward()
    num = numeric_grad(lambda a, b: probe(Value(a), Value(b)).data, pt)
    err = max(abs(vx.grad - num[0]), abs(vy.grad - num[1]))
    lines.append(f"gradient check: max |autodiff - finite difference| < 1e-8 is {err < 1e-8}")
    for lr in (0.07, 0.09):
        RESULTS[f"sgd_lr{lr}"] = run(lambda p, g: sgd_step(p, g, lr))
        lines.append(f"SGD      lr={lr:<5} loss after 100 steps = {RESULTS[f'sgd_lr{lr}']:.3g}")
    RESULTS["momentum"] = run(Momentum(0.1, 0.5).step)
    lines.append(f"Momentum lr=0.1   mu=0.5 loss after 100 steps = {RESULTS['momentum']:.3g}")
    RESULTS["momentum_untuned"] = run(Momentum(0.02, 0.9).step)
    lines.append(f"Momentum lr=0.02  mu=0.9 loss after 100 steps = {RESULTS['momentum_untuned']:.3g}")
    adam = Adam(0.1)
    RESULTS["adam"] = run(adam.step)
    lines.append(f"Adam     lr=0.1   loss after 100 steps = {RESULTS['adam']:.3g}")
    # train y = w*x + b on points from y = 2x + 1 using the engine itself
    data = [(x / 4.0, 2.0 * (x / 4.0) + 1.0) for x in range(-8, 9)]
    w, b, opt = 0.0, 0.0, Adam(0.05)
    for _ in range(400):
        vw, vb = Value(w), Value(b)
        loss = Value(0.0)
        for x, y in data:
            loss = loss + (vw * x + vb - y) ** 2.0
        loss = loss * (1.0 / len(data))
        loss.backward()
        w, b = opt.step([w, b], [vw.grad, vb.grad])
    RESULTS["fit_w"], RESULTS["fit_b"] = w, b
    lines.append(f"fit y=wx+b: w={w:.3f} b={b:.3f}")
    return lines

if __name__ == "__main__":
    print("\n".join(demo()))
```

Output (produced by the check script, which fails if this block drifts from the code):

```text
gradient check: max |autodiff - finite difference| < 1e-8 is True
SGD      lr=0.07  loss after 100 steps = 2.49e-07
SGD      lr=0.09  loss after 100 steps = 3.01e+20
Momentum lr=0.1   mu=0.5 loss after 100 steps = 1.14e-29
Momentum lr=0.02  mu=0.9 loss after 100 steps = 0.000113
Adam     lr=0.1   loss after 100 steps = 0.000112
fit y=wx+b: w=2.000 b=1.000
```

Reading it:

1. `lr = 0.07` is below the limit and converges; `lr = 0.09` is just above it and the loss reaches about `3e20` in 100 steps. The edge is where the theory says it is.
2. Momentum with `lr = 0.1, mu = 0.5` is far better: the loss falls to about `1e-29`. That learning rate would have exploded plain SGD; the velocity damps the back-and-forth across the steep direction, which is what allows the larger step.
3. Momentum with `lr = 0.02, mu = 0.9` does *worse* than tuned SGD here (about `1e-4` against `2.5e-7`). Momentum is not a free upgrade: `mu` and `lr` interact, and a high `mu` overshoots and rings. Retune both together.
4. Adam with `lr = 0.1` reaches about `1e-4` in 100 steps. It did not need the curvature to be known, but it does not win on a smooth 2-D bowl. Its job is badly mismatched scales across many parameters, which this toy lacks.
5. The last line fits `y = 2x + 1` from 17 points with the engine computing the gradients and Adam stepping: the same machinery, one level up.

These numbers are for this bowl and these hyperparameters. They show mechanisms (a stability limit, a conditioning penalty, an interaction between `lr` and `mu`), not a ranking of optimizers.

---

## 6. The Optimizers, Precisely

**SGD.** `p <- p - lr * g`. With minibatches, `g` is a noisy estimate of the full gradient. The noise can help or hurt; it is one reason learning rates are usually decayed late in training.

**Momentum.** `v <- mu * v + g`, `p <- p - lr * v`. This is the form implemented above; `mu = 0` recovers SGD. Where gradients keep the same sign, `v` builds up towards `g / (1 - mu)`; where they alternate, contributions cancel.

**Adam** (Kingma and Ba, Algorithm 1). Keep `m`, a moving average of `g`, and `s`, a moving average of `g * g`, both starting at zero:

```text
m <- b1*m + (1-b1)*g          s <- b2*s + (1-b2)*g*g
m_hat = m / (1 - b1^t)        s_hat = s / (1 - b2^t)
p <- p - lr * m_hat / (sqrt(s_hat) + eps)
```

The paper's suggested defaults are `lr = 0.001`, `b1 = 0.9`, `b2 = 0.999`, `eps = 1e-8`. Two things to be able to explain:

- **Why bias correction.** Because `m` and `s` start at zero they are biased towards zero in the first steps, especially for `s` since `b2` is close to 1 (the paper says the bias matters most when the decay rate is near 1). Dividing by `1 - b^t` removes it. A consequence the check verifies: on the first step the update is `lr * g / (|g| + eps)`, so its size is about `lr` whether the gradient is `1e-3` or `1e3`.
- **Why divide by `sqrt(s_hat)`.** Each parameter's step is scaled by the inverse of its own recent gradient size, so parameters with consistently large gradients take smaller steps than parameters with tiny ones. The paper lists invariance to diagonal rescaling of the gradients among its properties.

Left out on purpose: weight decay (and its decoupled variant), warmup and decay schedules, gradient clipping. Large-model training leans on them; this lesson does not cover them and its sources do not either.

---

## 7. Pitfalls Checklist

1. **`=` instead of `+=` when accumulating gradients.** Right on trees, wrong the moment a value is used twice.
2. **Not resetting gradients between steps.** Old gradients pile onto new ones; the symptom is a loss that behaves as if the learning rate keeps growing.
3. **A recursive topological sort.** Fine in the demo, a `RecursionError` on a long chain.
4. **Trusting a loss curve as a gradient test.** A wrong gradient can still lower the loss for a while. Run the finite-difference check.
5. **A finite-difference `h` that is too small.** `1e-12` subtracts two nearly equal numbers and measures rounding noise.
6. **Raising the learning rate until it diverges, then blaming the optimizer.** On a quadratic the limit is `2 / (largest curvature)`.
7. **Changing `mu` without retuning `lr`.** Section 5, point 3.
8. **Calling Adam "better SGD".** It is different: per-parameter scaling. It is a common default; whether it is best depends on the problem.
9. **Differentiating through a kink without saying so.** `relu` at zero, `abs`, `max`: state the convention.

---

## Drills

1. For `y = x * x + x` at `x = 3`, give `dy/dx`, and say which line of `backward` makes the engine get it right.
2. Why is reverse mode the right choice for a loss with ten million parameters and one output? When would forward mode win?
3. A colleague's `backward` uses `parent.grad = local * node.grad`. Write the smallest expression on which it fails and say what it returns.
4. Why does the central difference `(f(x+h) - f(x-h)) / 2h` beat `(f(x+h) - f(x)) / h` for the same `h`, and what happens to your check as `h` shrinks towards `1e-15`?
5. On `0.5 x^2 + 12.5 y^2`, derive the largest stable learning rate for plain gradient descent and say which coordinate decides it.
6. In section 5, momentum with `lr = 0.1` is excellent and with `lr = 0.02, mu = 0.9` is worse than SGD. Give the mechanism for the second result.
7. Compute Adam's first update for a single parameter with gradient `g = 5` and `lr = 0.01` (ignore `eps`). Repeat for `g = 0.005`. What do you notice and why?
8. Your training loss is `nan` at step 3. Give an ordered list of five things you would check.

---

## Homework

1. Add `sigmoid` and `__abs__` to the engine, with finite-difference tests. State the convention you chose at the kink.
2. Implement RMSProp-style scaling (Adam without the first moment and without bias correction) and show on the bowl what bias correction changes in the first steps.
3. Write a two-parameter logistic regression on a small separable dataset using only `Value`; train it with SGD and with Adam and compare the loss after 200 steps.
4. Build a recursive `backward`, find the chain length at which it fails on your machine, and compare with the iterative one.
5. Read the Adam paper's section 2 and rederive why the first-step update has size about `lr`.
6. Work the example in Baydin et al. section 3, `y = ln(x1) + x1*x2 - sin(x2)` at `(2, 5)`, through your engine and match the survey's reverse-mode adjoints.

---

## Sources

Read on 26 November 2026:

- Kingma and Ba, "Adam: A Method for Stochastic Optimization", arXiv:1412.6980 v9 (ICLR 2015), full text from the arXiv PDF. Used for the algorithm, the default values, the zero-initialisation bias and its correction. The PDF text extraction garbled the pseudocode box, so the update rule above was checked against the prose in section 2 and the check script's independent implementation, not copied from the box.
- Baydin, Pearlmutter, Radul and Siskind, "Automatic Differentiation in Machine Learning: a Survey", arXiv:1502.05767, full text (ar5iv rendering). Used for forward versus reverse mode and the worked example in the homework.

Not consulted, and nothing above relies on them: the original backpropagation papers, micrograd-style tutorials, the decoupled weight decay (AdamW) paper, momentum convergence analyses. The stability bound and the conditioning remarks in section 5 are standard facts about gradient descent on quadratics, derived above and confirmed by the printed output, not taken from a source.

*Last reviewed: 26 November 2026.*
