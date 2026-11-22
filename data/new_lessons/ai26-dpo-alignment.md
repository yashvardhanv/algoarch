# Lesson 26 — Model Alignment: RLHF, DPO & Synthetic Data Distillation

> **Priority:** ★★★★☆ (Foundation Model & Post-Training Senior Bar)  
> **Estimated Study Time:** 60 minutes  
> **Key Skills:** Supervised Fine-Tuning (SFT), Reward Modeling, Proximal Policy Optimization (PPO), Direct Preference Optimization (DPO), Rejection Sampling, Synthetic Data Quality Filtering.

---

## 1. The Post-Training Pipeline: SFT -> Alignment

Pre-training predicts the next token on internet data. It learns grammar and world facts, but does not know how to follow instructions safely. Post-training aligns the model into a helpful assistant:

```
[Base Model (Raw Internet)]
         │
         ▼
[Supervised Fine-Tuning (SFT)] (High quality (prompt, response) pairs)
         │
         ▼
[Preference Alignment]
  ├── Legacy Method: RLHF with PPO (Train separate Reward Model -> optimize policy)
  └── Modern Standard: DPO (Direct Preference Optimization - No separate reward model!)
```

---

## 2. Why DPO Replaced PPO in Modern Production

Traditional RLHF with PPO requires training **4 simultaneous models** in GPU VRAM:
1. Policy model (actor)
2. Value model (critic)
3. Reference model (KL penalty anchor)
4. Reward model
This is notoriously unstable, sensitive to hyperparameters, and frequently experiences policy collapse.

**Direct Preference Optimization (DPO):**
Rafailov et al. (Stanford, 2023) showed that the optimal policy under the Bradley-Terry preference model can be derived directly in closed form:
`Loss_DPO = - log sigma [ beta * log(pi(y_w | x) / pi_ref(y_w | x)) - beta * log(pi(y_l | x) / pi_ref(y_l | x)) ]`
Where `y_w` is the chosen (winning) response and `y_l` is the rejected (losing) response.
- **Benefits:** No reward model training; no reinforcement learning instability; standard cross-entropy style loss; half the GPU memory requirement.

---

## 3. Synthetic Data Distillation & Quality Filters

Top AI labs no longer rely solely on human annotators. Instead:
1. **Teacher Generation:** Frontier model (e.g. Claude 3.5 Sonnet) generates multiple diverse candidate answers using high temperature.
2. **Automated Verification:** Deterministic unit tests, linters, or strict LLM judges filter out incorrect completions.
3. **Rejection Sampling (Best-of-N):** Only the highest-scoring candidate is kept for student fine-tuning.
