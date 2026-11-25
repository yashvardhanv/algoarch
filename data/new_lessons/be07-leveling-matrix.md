# Lesson 07 — Leveling Matrix: Senior (L5) vs Mid (L4) Mastery

> **Priority:** ★★★★★ (The single factor that decides which level you are offered)  
> **Estimated Study Time:** 50 minutes  
> **Key Skills:** Navigating Ambiguity, Driving Technical RFCs, Cross-Team Influence Without Authority, Proactive Risk Identification, Blameless Post-Mortems, Mentorship.

---

## 1. What FAANG Hiring Committees Actually Grade by Level

| Dimension | SDE-2 / L4 (Mid-Level) | SDE-3 / L5 (Senior) |
|---|---|---|
| **Problem Scope** | Well-defined tasks ("Implement this Kafka consumer with retry") | **Ambiguous business problems** ("Payment failure rate in EMEA is 4%; find why and fix it") |
| **Autonomy** | Needs architectural guidance from senior team members | **End-to-end ownership:** writes the RFC, benchmarks solutions, drives consensus |
| **Technical Vision** | Focuses on speed of shipping their assigned module | Focuses on **systemic maintainability, failure blast radius, observability, and tech debt** |
| **Influence** | Collaborates with peers within the immediate pod | **Cross-functional leadership:** leads discussions across Product, Security, Infra, Data |
| **Failure Handling** | Fixes the immediate bug and moves on | Conducts a **blameless post-mortem**, identifies root architectural causes, deploys automated guardrails |

---

## 2. The Language of an L5 Engineer (Interview Transcripts)

Notice the critical vocabulary shift:
- **L4 Answer:** *"My manager asked me to migrate our database to Postgres, so I wrote the migration scripts and transferred the tables."*
- **L5 Answer:** *"We identified that our MySQL instance was experiencing CPU spikes during month-end billing due to locking conflicts. I drafted an RFC evaluating MongoDB, DynamoDB, and Postgres with Partitioning. I organized an architecture review with our data and infra leads, demonstrated that Postgres range partitioning gave us 4x write throughput with zero application code rewrites, and planned a phased dual-write migration with zero customer downtime."*

---

## 3. The 4 Artifacts Every Senior Engineer Must Reference

In your behavioral answers, naturally mention:
1. **The Technical RFC (Request for Comments):** Proving you document trade-offs and build consensus before writing code.
2. **The Decision Matrix:** Comparing 3 options with concrete criteria (latency, cost, operational complexity).
3. **The Rollout & Rollback Runbook:** Showing you anticipate failure modes before pushing to production.
4. **The Blameless Post-Mortem:** Demonstrating institutional learning and psychological safety after incidents.
