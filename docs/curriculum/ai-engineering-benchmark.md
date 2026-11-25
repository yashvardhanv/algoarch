# AI Engineering: benchmark (DRAFT 1)

Status: first pass, 2026-11-26. Phase 1 of `docs/plans/curriculum-overhaul-plan.md` (that plan is on branch `claude/epic-davinci-ugc6xq`).
Not yet owner-reviewed. Every "Ours" cell below is judged from **lesson titles and the audit flags only**, not from reading each lesson body. Treat each as a hypothesis to confirm in the per-lesson review (Phase 3).

## Sources read (access date 2026-11-26)

| Code | Source | What was read | Limit |
|---|---|---|---|
| KZH | Karpathy, *Neural Networks: Zero to Hero* (karpathy.ai/zero-to-hero.html) | all 8 lessons, in order | no publication date on the page; list marked "ongoing" |
| C336 | Stanford CS336 *Language Modeling from Scratch*, Spring 2026 (cs336.stanford.edu) | 19-session schedule | schedule is marked tentative |
| C224 | Stanford CS224N *NLP with Deep Learning*, Winter 2026 (web.stanford.edu/class/cs224n) | 19-topic schedule | schedule is marked tentative |
| HFC | Hugging Face *LLM Course* (huggingface.co/learn/llm-course) | chapter ranges only (1-4 Transformers library, 5-8 Datasets/Tokenizers/classic NLP, 9 demos, 10-12 advanced fine-tuning, data curation, reasoning models) | chapter titles for 2-12 not retrieved |

| HUY | Chip Huyen, *AI Engineering* (O'Reilly, Dec 2024), read in a browser on the O'Reilly page | the 10 chapter titles plus the publisher's overview paragraph | chapter titles only: no section lists or chapter summaries, so a topic is marked only when a chapter title or the overview names it |

HUY chapters: 1 Introduction to Building AI Applications with Foundation Models; 2 Understanding Foundation Models; 3 Evaluation Methodology; 4 Evaluate AI Systems; 5 Prompt Engineering; 6 RAG and Agents; 7 Finetuning; 8 Dataset Engineering; 9 Inference Optimization; 10 AI Engineering Architecture and User Feedback.

Still to read: Raschka *LLMs from scratch*, Lilian Weng, Eugene Yan, Anthropic and OpenAI agent and prompting guides, DeepLearning.AI short courses, and the key papers (Attention Is All You Need, PagedAttention, FlashAttention, LoRA, RAG, ReAct, DPO).

## Coverage matrix (what each source teaches, versus our 28 lessons)

`D` = a dedicated lesson or session, `P` = part of one, `-` = absent, `?` = judged from title only.

| Topic | KZH | C336 | C224 | HFC | HUY | Ours (lesson ids) |
|---|---|---|---|---|---|---|
| Backpropagation and autodiff from scratch | D | P | D | - | - | `-` |
| Gradient descent, loss, optimizers | P | P | P | - | - | `-` |
| Language-model basics (bigram, MLP, sampling) | D | - | D | P | P (ch.2) | `-` |
| Training hygiene (init, normalization, splits, diagnostics) | D | P | - | - | - | `-` |
| Tokenization / BPE | D | D | P (guest) | D | P (ch.2) | `P` ai02 ? |
| Embeddings / word vectors | - | - | D | - | - | `P` ai02 ? |
| Attention and the transformer block | D | D | D | D | P (ch.2) | `-` |
| Architecture variants (attention alternatives, MoE) | - | D | - | - | P (ch.2) | `-` |
| Pretraining data, filtering, mixing, synthetic data | - | D | P | P | D (ch.8) | `-` |
| Scaling laws | - | D | P | - | P (ch.2) | `-` |
| GPUs, kernels, parallelism | - | D | - | - | P (ch.9) | `P` ai23 ? |
| Inference and serving (batching, KV cache, paging) | - | D | - | - | D (ch.9) | `D` ai23, ai24 ? |
| SFT / RLHF / DPO / RL with verifiable rewards | - | D | D | P | P (ch.2, 7) | `D` ai26 ? (thin) |
| Fine-tuning and parameter-efficient tuning (LoRA) | - | - | D | D | D (ch.7) | `P` ai17 ? |
| Prompt engineering | - | - | D | - | D (ch.5) | `P` ai07 ? |
| RAG, tool use, agents | - | - | D | - | D (ch.6) | `D` ai01-06, ai10-13 |
| Evaluation, benchmarks, AI-as-judge | - | D | D | - | D (ch.3, 4) | `D` ai05, ai08 |
| Reasoning models | - | P | D | D | - | `-` |
| Multimodality | - | D | D (guest) | - | - | `-` |
| Safety and prompt injection | - | - | P | - | - | `D` ai14, ai15 |
| AI application architecture and user feedback | - | - | - | - | D (ch.10) | `P` ai16, ai22 ? |
| Dataset engineering (curation, annotation, synthesis) | - | D | - | P | D (ch.8) | `P` ai26 ? |
| Observability, cost, orchestration, MCP, gateways | - | - | - | - | - | `D` ai11, ai12, ai16, ai22 |

Reading the matrix: the public courses agree strongly on a foundations arc (autodiff, language models, training basics, attention and transformers, pretraining, post-training, inference) that **we do not teach**. The one practitioner source we now have, Huyen's *AI Engineering*, does not teach the arc as such (it starts at foundation models from the application side) but gives dedicated chapters to topics we only touch: prompt engineering, fine-tuning, dataset engineering, and application architecture with user feedback. Its chapter titles do not name observability, cost, MCP, orchestration or gateways, so those remain untested against any source until the other practitioner sources are read.

## Hypotheses for the outline (to confirm, not decided)

Each addition needs a rationale and a "what we shorten to make room" line (plan §3.4).

| # | Proposed change | Action | Why | What gives |
|---|---|---|---|---|
| 1 | Foundations arc: autodiff and gradient descent with optimizers; a language model from scratch with training hygiene; attention and the transformer block | add 3 lessons before `ai01` | three of the four sources teach this before anything applied; later lessons (RAG, serving, alignment) assume it | none. These are new, small lessons |
| 2 | Tokenization depth (BPE) | merge into `ai02` | KZH, C336 and HFC all give tokenization a lesson of its own | shorten embeddings section |
| 3 | Pretraining data and scaling laws | add 1 lesson | C336 spends 5 of 19 sessions on it | none |
| 4 | Inference systems: KV cache, FlashAttention, speculative decoding | merge into `ai23` | C336 session 10; `ai23` is flagged thin | combine `ai24` and `ai25` follow-ups only if they overlap on review |
| 5 | Post-training: SFT, RLHF, DPO, RL with verifiable rewards | deepen `ai26` | C336 and C224 each give it two sessions; `ai26` is flagged thin | none |
| 6 | Reasoning models | add 1 lesson | C224 and HFC both include it | none |
| 7 | Multimodality | defer | appears in two courses but is a lower interview weight | decide after the practitioner sources |
| 8 | Setup lesson `ai00` | rewrite | flagged thin, with no practice and no visual | none |
| 9 | Dataset engineering (curation, annotation, synthetic data) | add 1 lesson, or fold into `ai26` after review | HUY gives it a whole chapter (8) and C336 gives data two sessions; we only touch it through `ai26` | decide after reading `ai26` |
| 10 | Prompt engineering fundamentals | check `ai07` first | HUY chapter 5 and C224's adaptation session; `ai07` is about context and structured output and may not cover the basics | none if `ai07` already covers it |
| 11 | AI application architecture and user feedback | check `ai16` and `ai22` first | HUY chapter 10; user-feedback loops are not obvious from our titles | none if the two lessons already cover it |

Net effect if all accepted: AI Engineering grows from 28 to about 34 lessons (rows 9 to 11 add at most one). Whether that fits the overall 110 to 140 budget depends on the other three courses; this benchmark does not decide it.

## Open questions for the owner

1. Is a foundations arc wanted at all? The current course is aimed at applied interviews; the arc raises the starting bar. If the audience already knows this, it may be better as an optional prerequisite pathway.
2. Is multimodality in scope?

## Next steps

1. Read the remaining practitioner sources listed above and add their columns.
2. Re-judge each "Ours" cell against the lesson body rather than the title.
3. Owner approves the outline; then the same process for DSA, System Design and Behavioral.
