# Lesson 26 — Post-training: SFT, RLHF, DPO and Verifiable-Reward RL

> **Priority:** ★★★★☆ — the "how does a base model become an assistant?" round, and the follow-up "why DPO, why RL?"
>
> **Study time:** 75 minutes. **Do this after:** Lesson 17 (Fine-Tuning vs RAG vs In-Context Learning). You should be comfortable with log-probabilities and the sigmoid.
>
> **Level:** advanced. Optional for a crash plan; worth doing if your target loops include model-training or research-engineering rounds.

A pretrained model continues text; it does not follow instructions. Post-training changes that in
stages: imitate good answers (supervised fine-tuning), then push towards answers people prefer (RLHF or
DPO), and, where an answer can be checked by a program, reward correct answers directly (RL with
verifiable rewards). Interviewers want the objectives, not the brand names: what each stage optimises,
what it needs in memory, and how it fails. Every formula below is implemented in plain Python and
checked against an independent computation.

---

## 1. Mental Model

> **Every stage maximises some score of the model's outputs while a penalty keeps it close to a
> reference model. The stages differ in where the score comes from: demonstrations (SFT), a learned
> reward model (RLHF), preference pairs used directly (DPO), or a program that checks the answer
> (verifiable rewards).**

What follows from it:

- **The KL leash is the common thread.** InstructGPT's RL objective subtracts `β · log(π_RL / π_SFT)`
  per token; DPO is derived from the same KL-regularised objective; GRPO puts a KL term in its loss.
  Remove the leash and the policy exploits whatever is scoring it.
- **A reward is only as good as its source.** A learned reward model can be gamed; a verifier can only
  check what it checks. Most post-training failures are the policy finding the gap.
- **Data beats algorithm at the margin you control.** Which prompts, whose demonstrations, which pairs
  and which verifiers decide what the model learns; the optimiser decides how fast.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "teach a format, a style, a new task from examples" | SFT on (prompt, response) pairs, loss on response tokens only |
| "we have pairs of better/worse answers, little RL infrastructure" | DPO against the SFT model as reference |
| "we have rankings and want a reusable scorer" | a reward model (Bradley-Terry loss), then RL (PPO) |
| "math, code, or anything a program can check" | RL with verifiable rewards; GRPO-style group baselines |
| "the model got worse at general tasks after alignment" | the alignment tax: KL strength, mixing in pretraining or SFT data |
| "reward goes up but quality goes down" | reward hacking: inspect samples, harden the reward, tighten KL |
| "memory budget is tight for RL" | count the models (§5), drop the critic (GRPO) or use DPO |

---

## 3. Stage 1: Supervised Fine-Tuning

Maximise the log-likelihood of good responses, but only on the response tokens: the prompt is given,
not learned.

```python
def sft_loss(token_logprobs, is_response):
    """Mean negative log-likelihood over response tokens only.
    token_logprobs[i] = log p(token_i | tokens before it); is_response[i] = True for response tokens."""
    picked = [lp for lp, r in zip(token_logprobs, is_response) if r]
    return -sum(picked) / len(picked)
```

InstructGPT's first step is exactly this: labelers wrote demonstrations for prompts (written by labelers
and submitted to the API), and GPT-3 was fine-tuned on them with supervised learning, about 13k prompts
in its SFT set. SFT teaches the *form* of a good answer quickly. It cannot teach "this answer is better
than that one", because it never sees a worse answer.

---

## 4. Stage 2a: Reward Model and RLHF

**Reward model.** Labelers rank `K` responses per prompt (InstructGPT used `4 ≤ K ≤ 9`), giving `C(K, 2)`
pairs. A scalar reward `r(x, y)` is trained so that the preferred response scores higher, under the
Bradley-Terry model `P(y_w ≻ y_l) = σ(r_w - r_l)`:

```python
import math

def sigmoid(z):
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))

def softplus(z):
    """log(1 + e^z), computed without overflow."""
    return max(z, 0.0) + math.log1p(math.exp(-abs(z)))

def reward_model_loss(r_w, r_l):
    """-log sigma(r_w - r_l) for one preference pair."""
    return softplus(-(r_w - r_l))

def ranking_loss(rewards_best_first):
    """InstructGPT-style: average the pairwise loss over all C(K, 2) pairs of one ranking."""
    k = len(rewards_best_first)
    pairs = [(i, j) for i in range(k) for j in range(i + 1, k)]
    return sum(reward_model_loss(rewards_best_first[i], rewards_best_first[j]) for i, j in pairs) / len(pairs)
```

**RL.** The SFT model is then optimised with PPO to maximise
`r(x, y) - β · log(π_RL(y|x) / π_SFT(y|x))`. InstructGPT's preferred variant (PPO-ptx) also adds
`γ` times the pretraining log-likelihood, because plain PPO regressed on several public NLP benchmarks, the
"alignment tax"; mixing in pretraining updates reduced the regressions, and did better than just raising
the KL coefficient. The headline result: on their prompt distribution, people preferred outputs of the
1.3B InstructGPT model over the 175B GPT-3.

---

## 5. What RLHF Costs in Memory: Count the Models

| Method | Models during training | Notes |
|---|---|---|
| PPO (InstructGPT) | policy, reference (SFT), reward model, value model | InstructGPT initialised the value function from the 6B reward model |
| GRPO | policy, reference, reward source | no value model: the group's mean reward is the baseline |
| DPO | policy, reference | reference log-probs are constants of the data, so they can be computed once in advance |

The DeepSeekMath paper motivates GRPO by this count: PPO's value model is usually about the size of the
policy, a substantial memory and compute cost. The DPO row follows from the loss below: the reference model
only ever appears through `log π_ref(y|x)` for fixed dataset responses.

---

## 6. Stage 2b: Direct Preference Optimization

The DPO derivation in four steps (Rafailov et al., 2023):

1. The KL-regularised objective is `max E[r(x, y)] - β · KL(π || π_ref)`.
2. Its optimum has a closed form: `π*(y|x) = π_ref(y|x) · exp(r(x, y)/β) / Z(x)`.
3. Invert it: `r(x, y) = β · log(π*(y|x)/π_ref(y|x)) + β · log Z(x)`.
4. Substitute into Bradley-Terry. `Z(x)` cancels in the difference `r_w - r_l`, leaving a loss on the policy alone:

`L_DPO = -log σ( β · [log π(y_w)/π_ref(y_w)] - β · [log π(y_l)/π_ref(y_l)] )`

```python
def dpo_loss_and_grad(logp_w, logp_l, ref_w, ref_l, beta):
    """DPO loss for one pair, from sequence log-probs under the policy and the reference.
    Returns (loss, d loss / d logp_w, d loss / d logp_l)."""
    r_w = beta * (logp_w - ref_w)          # implicit reward of the chosen response
    r_l = beta * (logp_l - ref_l)          # implicit reward of the rejected response
    loss = softplus(-(r_w - r_l))
    weight = sigmoid(r_l - r_w)            # large when the pair is currently ranked wrongly
    return loss, -beta * weight, beta * weight
```

**Reading the gradient.** Descending this loss raises `log π(y_w)` and lowers `log π(y_l)`, scaled by
`σ(r̂_l - r̂_w)`. The paper stresses that this weight matters: pairs the implicit reward already ranks
correctly get little push, and an unweighted version can make the model degenerate.

**Worked numbers (illustrative, from the check).** With `β = 0.1`, the chosen response at log-prob `-12`
(reference `-14`) and the rejected one at `-15` (reference `-13`): implicit rewards `0.2` and `-0.2`, loss
`≈ 0.513`, weight `≈ 0.401`. Swap the policy's two log-probs (the pair now ranked wrongly) and the loss rises
to `≈ 0.798` with weight `≈ 0.550`.

**The check proves the derivation on a toy.** Four responses with true rewards, every pair labelled with its
Bradley-Terry probability, a tabular softmax policy trained by gradient descent on the expected DPO loss: it
converges to `π_ref · exp(r/β) / Z`, the closed-form RLHF optimum from step 2.

**What the paper reports.** DPO gave the best reward-versus-KL frontier on controlled sentiment generation
(dominating PPO, even PPO with the ground-truth reward), about 61% GPT-4 win rate on TL;DR summarisation at
temperature 0 against about 57% for PPO at its best temperature, and was the only computationally efficient
method they tested that improved over the preferred completions on Anthropic HH dialogue. Experiments used
models up to 6B parameters. The reference model is the SFT model when one exists.

**What DPO does not give you.** It is offline: it learns from a fixed set of pairs, usually sampled from the
reference model, and never scores its own new outputs. RL methods sample from the current policy. That is the
trade: DPO is simpler and cheaper; online RL can keep improving on what the model now does.

---

## 7. Stage 3: RL With Verifiable Rewards

When correctness can be checked by a program (a math answer, unit tests, a format rule), use the check as the
reward. Tülu 3 calls this Reinforcement Learning with Verifiable Rewards (RLVR): a constant reward only when the
completion is verified correct, used as the last stage after SFT and DPO, and reported to improve GSM8K, MATH and
IFEval.

```python
import re

def math_reward(completion, gold):
    """1.0 if the last 'Answer: <number>' in the completion equals gold, else 0.0."""
    found = re.findall(r"Answer:\s*(-?\d+(?:\.\d+)?)", completion)
    return 1.0 if found and float(found[-1]) == float(gold) else 0.0

def group_advantages(rewards, eps=1e-6):
    """GRPO-style: normalise each sampled output's reward by its group's mean and standard deviation."""
    n = len(rewards)
    mean = sum(rewards) / n
    std = math.sqrt(sum((r - mean) ** 2 for r in rewards) / n)
    return [(r - mean) / (std + eps) for r in rewards]

def kl_estimate(logp, logp_ref):
    """Per-token KL estimator used in GRPO: ratio - log(ratio) - 1 with ratio = pi_ref / pi. Never negative."""
    log_ratio = logp_ref - logp
    return math.exp(log_ratio) - log_ratio - 1
```

**GRPO (DeepSeekMath).** For each question, sample a group of `G` outputs, score them, and use the normalised
reward as every token's advantage (outcome supervision); clip the probability ratio as PPO does; add `β` times
the KL estimate to the loss instead of folding it into the reward. DeepSeekMath-RL 7B reached 51.7% on MATH, up
from 46.8% for the instruct model it started from. In that paper the RL reward came from a learned reward model
trained on correctness labels, so "GRPO" and "verifiable rewards" are separate ideas that combine well.

**Read the advantage function closely.** If every output in a group gets the same reward (all right or all
wrong), every advantage is zero and the question teaches nothing. Prompt difficulty therefore controls the
signal: problems the model always solves or never solves are wasted compute. The check confirms this exactly.

**Reward hacking with verifiers.** `math_reward` takes the *last* `Answer:`. A policy that prints many answers,
or a verifier that takes the first match, invites gaming. A test-based reward is only as strong as its tests.
Inspect samples, not just the reward curve.

---

## 8. Pitfalls Checklist

1. **SFT loss on prompt tokens too**, which trains the model to predict the user.
2. **Saying DPO "has no reward model" and stopping there.** It has an implicit one, `β · log(π/π_ref)`, and it
   still needs a reference model and good pairs.
3. **Dropping the reference or the KL term**, then wondering why the policy drifts or games the reward.
4. **Treating `β` as a universal constant.** In both PPO and DPO it weights the KL leash (smaller `β`, more
   drift from the reference), but a good value depends on the method and the data; the DPO paper itself notes it
   did not meaningfully tune `β`.
5. **Claiming DPO always beats PPO.** The paper's evidence is on specific tasks with models up to 6B; online
   methods sample from the current policy, which DPO does not.
6. **Groups with no reward variance** in GRPO: zero advantage, no learning, full cost.
7. **A verifier that can be satisfied without solving the task** (format-only checks, first-match parsing, weak tests).
8. **Ignoring the alignment tax**: measure general benchmarks before and after, and keep a mix of earlier data.

---

## Drills

1. Why is the SFT loss averaged over response tokens only?
2. Write the Bradley-Terry probability and the reward-model loss for one pair. How many pairs does a ranking of 6 give?
3. Name the four models in InstructGPT-style PPO and say which one GRPO removes, and why that matters.
4. Derive the DPO loss from `π* = π_ref · exp(r/β)/Z` in three lines. Where does `Z` go?
5. Using `dpo_loss_and_grad`, what happens to the weight as the policy ranks a pair more and more correctly?
6. Why can DPO's reference log-probs be computed once before training?
7. Compute GRPO advantages for rewards `[1, 0, 0, 1]`, and for `[1, 1, 1, 1]`. What does the second case mean for training?
8. Give two ways a policy could raise `math_reward` without getting better at math, and how you would close each.

---

## Homework

1. Implement the toy in the check yourself: four responses, a reference distribution, true rewards, and gradient
   descent on the expected DPO loss. Plot (or print) the policy against `π_ref · exp(r/β)/Z` for `β` in
   `{0.05, 0.1, 1}`.
2. Train a small model (any open checkpoint you can run) with SFT on a few hundred instruction pairs, masking prompt
   tokens. Compare with and without the mask on held-out prompts.
3. Using an open preference-tuning library, run DPO from your SFT checkpoint on a public preference dataset, and
   track the implicit rewards of chosen and rejected responses during training.
4. Write a verifier for a GSM8K-style answer format and five adversarial completions that try to fool it. Harden it
   until all five fail.
5. Read section 4 of the DPO paper and section 4.1 of DeepSeekMath, then explain DPO's gradient and GRPO's advantage
   aloud in under two minutes each.

---

## Sources

All read 2026-11-26.

- Ouyang et al., *Training language models to follow instructions with human feedback* (InstructGPT, 2022),
  arxiv.org/abs/2203.02155 and the full text at arxiv.org/html/2203.02155 (first part). Source for the three steps,
  SFT/RM/PPO prompt counts, `K` between 4 and 9, the reward-model loss, the 6B reward model and value initialisation,
  the PPO and PPO-ptx objective, the alignment tax and the 1.3B-versus-175B preference result.
- Rafailov et al., *Direct Preference Optimization: Your Language Model is Secretly a Reward Model* (2023),
  arxiv.org/html/2305.18290 (first part). Source for the KL-regularised objective, the closed-form optimum, the
  reparameterisation, the DPO loss and gradient, the importance of the weighting, the pipeline and the reported results.
- Shao et al., *DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models* (2024),
  arxiv.org/html/2402.03300 (first part). Source for GRPO's group-normalised advantage, removal of the value model,
  the KL estimator and its placement in the loss, outcome versus process supervision, the reward-model reward, and
  the MATH result.
- Lambert et al., *Tülu 3: Pushing Frontiers in Open Language Model Post-Training* (2024), arxiv.org/abs/2411.15124
  and arxiv.org/html/2411.15124 (first part). Source for the RLVR name, the constant reward for verified completions,
  its place after SFT and DPO, and the tasks it improved.

## Further reading (not consulted)

The PPO paper (Schulman et al., 2017); the DeepSeek-R1 paper (only its abstract page was opened, so nothing here
relies on it); Constitutional AI and RL from AI feedback; later DPO variants (IPO, KTO, SimPO). None were read for this
revision.

*Last reviewed: 2026-11-26.*
