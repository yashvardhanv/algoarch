# Lesson 25 — Constrained Generation & Logits Guardrails (Outlines)

> **Priority:** ★★★★★ (Core Enterprise AI Engineering Bar)  
> **Estimated Study Time:** 50 minutes  
> **Key Skills:** Logit masking with Context-Free Grammars (CFG) & Finite State Machines (FSM), 100% deterministic JSON schema output, Outlines/Guidance internals, Eliminating parsing retries.

---

## 1. The Prompt Engineering Illusion vs Grammar Masking

- **The Amateur Way:** *"Please return ONLY valid JSON matching this schema, do NOT include markdown backticks..."*  
  At 1,000,000 queries, LLMs will randomly hallucinate trailing commas, markdown fences, or truncate closing brackets 2% to 5% of the time, crashing backend JSON parsers and forcing expensive retry loops.
- **The Staff Engineer Way (Constrained Generation):** You do not *ask* the model to be valid; you **mask invalid tokens at the logits level before softmax sampling**. If the grammar says the next character must be a closing quote `"` or a comma `,`, all other tokens in the 128,000 vocabulary have their logit scores set to `-infinity`.

---

## 2. Finite State Machine (FSM) Logit Masking

```
Current FSM State: inside JSON string key
Allowed Next Characters: alphanumeric character OR closing quote '"'

Model Logits:
- "name"   ──> Valid (keeps logit +4.2)
- "{"      ──> Invalid (logit set to -inf)
- " "      ──> Valid (keeps logit +1.1)
- "]"      ──> Invalid (logit set to -inf)

Result: Softmax only considers mathematically valid next tokens. Validation failure rate: 0.00%.
```

---

## 3. Libraries in Production: Outlines & Guidance

```python
# Conceptual example using Outlines / Pydantic schema enforcement
from pydantic import BaseModel, Field

class CandidateProfile(BaseModel):
    name: str = Field(..., description="Full legal candidate name")
    years_experience: int = Field(..., ge=0, le=50)
    top_skills: list[str] = Field(..., max_items=5)
    target_ctc_lpa: float = Field(..., ge=10.0, le=200.0)

# Outlines compiles CandidateProfile into a Regex / FSM guide:
# model = outlines.models.transformers("meta-llama/Meta-Llama-3-8B-Instruct")
# generator = outlines.generate.json(model, CandidateProfile)
# result = generator("Review Yashvardhan's resume...")
# Guaranteed 100% valid Pydantic object, no PydanticValidationError possible!
```
