# Curriculum outline (DRAFT 1 for owner review)

Date: 2026-11-26. Built from the four benchmark files, `decisions.md` (owner answers included) and the 106 lessons in `data/curriculum.json`.
Every status below is judged from lesson titles and audit flags, not from lesson bodies; Phase 3 re-checks each lesson against its body before any rewrite.

## How to read this

- **Status:** `keep` (as is), `rewrite` (replace the body), `deepen` (add depth and practice), `move` (same lesson, new place), `NEW` (to be written), `NEW?` (conditional: confirm against the lesson body or a source first).
- **Level:**
  - `core`: in the Standard pathway, and in Crash when the lesson is rated 5 stars.
  - `extended`: the case-study library; in the Deep pathway only.
  - `advanced`: optional depth, outside Crash and Standard.
- **Ids:** existing ids never change (the baseline guard fails the build if one disappears). New lessons take the next free number in their course; order is set by this outline, not by id. New lessons get a star rating when they are authored.
- **No lesson text is written in this phase.** Authoring follows the owner rule: one lesson first, then review, then the rest.

## Size and the cap

| Course | Today | Outline | New |
|---|---:|---:|---:|
| AI Engineering | 28 | 34 | 6 |
| DSA | 26 | 32 | 6 |
| System Design | 44 | 77 | 33 |
| Behavioral | 8 | 13 | 5 |
| **Total** | **106** | **156** | **50** |

**Conflict to resolve:** decision 2 caps the curriculum at 110 to 140 lessons. The owner's answer for System Design (real-life case studies "as many as we can", in detail) cannot fit under 140. Dropping everything marked `NEW?` and the `extended` tier 3 case studies gives about 143, still over 140; there is no honest way to reach 140 without cutting what the owner asked for.
**Resolved (owner, 2026-11-26): cap raised to about 155.** Original recommendation: raise the cap to about 155 and ship in waves (see "Build order"), so the cap is never a reason to write a thin case study. Pathways keep learners from being overwhelmed: Crash stays near 60 lessons whatever the library size.

## AI Engineering (28 to 34)

Owner: multimodality ignored for now. Foundations arc comes first (decision 1).

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| **Block 0: Foundations** | | | | |
| 1 | ai00 | Environment & Architecture | rewrite (thin, no practice) | core |
| 2 | ai28 | Autodiff and Gradient Descent (with optimizers) | NEW | core |
| 3 | ai29 | A Language Model from Scratch, and Training Hygiene | NEW | core |
| 4 | ai30 | Attention and the Transformer Block | NEW | core |
| 5 | ai02 | Tokens, BPE and Embeddings | move from RAG block, deepen (tokenization) | core |
| 6 | ai31 | Pretraining Data and Scaling Laws | NEW | extended |
| **Block I: RAG** | | | | |
| 7 | ai01 | RAG, From Scratch | keep | core |
| 8 | ai03 | Ingestion & Chunking Strategies | keep | core |
| 9 | ai04 | Hybrid Retrieval & Reranking | keep | core |
| 10 | ai05 | Evaluation of RAG Systems | keep | core |
| 11 | ai06 | Production RAG & Security | keep | core |
| **Block II: Context and agents** | | | | |
| 12 | ai07 | Context Engineering & Structured Output | keep; check it covers prompt basics | core |
| 13 | ai08 | The Automated Eval Harness | keep | core |
| 14 | ai09 | Model Behaviour & Prefix Caching | keep | core |
| 15 | ai10 | The Agent Loop from Scratch | keep | core |
| 16 | ai11 | Orchestration & Durable Execution | keep | core |
| 17 | ai12 | Model Context Protocol (MCP) Server | keep | core |
| 18 | ai13 | Multi-Agent Architectures | keep | core |
| **Block III: Safety and economics** | | | | |
| 19 | ai14 | Prompt Injection & Defense In Depth | keep | core |
| 20 | ai15 | Red-Teaming & Adversarial Testing | keep | core |
| 21 | ai16 | Observability, Tracing & Cost Engineering | keep; check it covers user feedback loops | core |
| 22 | ai17 | Fine-Tuning vs RAG vs In-Context Learning | keep | core |
| 23 | ai18 | Senior AI Architectural Judgment | keep | core |
| **Block IV: Interview case studies** | | | | |
| 24 | ai19 | The AI Engineering Interview Framework | keep | core |
| 25 | ai20 | Case Study: Enterprise RAG at Scale | keep | core |
| 26 | ai21 | Case Study: Autonomous Agent Platform | keep | core |
| 27 | ai22 | Case Study: Universal LLM Gateway | keep | core |
| **Block V: Advanced bar** | | | | |
| 28 | ai23 | High-Throughput LLM Serving: vLLM, PagedAttention, KV Cache, FlashAttention, Speculative Decoding | deepen (thin) | advanced |
| 29 | ai24 | Semantic Vector Caching & Prompt Routing | deepen (thin) | advanced |
| 30 | ai25 | Constrained Generation & Logits Guardrails | deepen (thin) | advanced |
| 31 | ai26 | Post-training: SFT, RLHF, DPO and Verifiable-Reward RL | deepen (thin) | advanced |
| 32 | ai32 | Reasoning Models | NEW | advanced |
| 33 | ai33 | Dataset Engineering: Curation, Annotation and Synthetic Data | NEW? (fold into ai26 if its body already covers it) | advanced |
| 34 | ai27 | Two-Tower Recommendation System Architecture | deepen | extended |

## DSA (26 to 32)

Owner: sorting and grids are separate lessons; advanced lessons stay separate from the core path.

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 1 | ds00 | The Recognition Engine | keep | core |
| **Block I: Recognition core** | | | | |
| 2 | ds01 | Complexity & the Recognition Reflex | keep | core |
| 3 | ds02 | Hashmap as an Index | keep | core |
| 4 | ds03 | Two Pointers | keep | core |
| 5 | ds04 | Sliding Window | keep | core |
| 6 | ds05 | Prefix Sums & Difference Arrays | keep | core |
| 7 | ds26 | Sorting and Selection (merge sort, quicksort, quickselect, stability, linear sorts) | NEW | core |
| 8 | ds06 | Binary Search & Search on Answer | keep | core |
| 9 | ds07 | Monotonic Stack & Deque | keep | core |
| 10 | ds08 | Heaps & Top-K | keep | core |
| **Block II: Structures where traversal is the algorithm** | | | | |
| 11 | ds09 | Linked List Surgery | keep | core |
| 12 | ds10 | Trees & DFS Return-Value Design | keep | core |
| 13 | ds11 | Graphs: BFS, DFS & Modelling | keep | core |
| 14 | ds27 | Matrix and Grid Problems | NEW | core |
| 15 | ds25 | Topological Sort & DAG Dependency Resolution | move from creator block (a core topic) | core |
| 16 | ds12 | Union-Find (Disjoint Set Union) | keep | core |
| **Block III: Search and optimisation** | | | | |
| 17 | ds28 | Recursion Fundamentals | NEW (short; backtracking assumes it) | core |
| 18 | ds13 | Backtracking | keep | core |
| 19 | ds14 | Dynamic Programming I: 1D | keep | core |
| 20 | ds15 | Dynamic Programming II: 2D & Sequences | keep | core |
| 21 | ds16 | Greedy & Intervals | keep | core |
| 22 | ds17 | Tries & Bit Manipulation | keep | core |
| 23 | ds30 | Design a Data Structure (LRU, LFU, min-stack, iterators) | NEW? (verify against Blind 75 and EPI first) | core |
| 24 | ds31 | Pattern-Recognition Index | NEW (check overlap with ds00) | core |
| 25 | ds18 | Mock Rounds & 45-Min Protocol | keep | core |
| **Block IV: Advanced (optional)** | | | | |
| 26 | ds19 | Advanced Graphs: Shortest Paths, MST & SCC | deepen (thin) | advanced |
| 27 | ds20 | Segment Trees & Fenwick Trees | deepen (thin) | advanced |
| 28 | ds21 | Bitmask DP & State Compression | deepen (thin) | advanced |
| 29 | ds22 | Math, Probability & Reservoir Sampling | deepen (thin) | advanced |
| 30 | ds23 | String Algorithms: KMP, Rabin-Karp & Rolling Hash | deepen (thin) | advanced |
| 31 | ds24 | Cyclic Sort & In-Place State Encodings | deepen | advanced |
| 32 | ds29 | Balanced and Binary Search Trees (AVL, red-black idea, B-trees) | NEW | advanced |

## System Design (44 to 77)

Owner: reliability engineering in scope; real-life case studies in detail, as many as we can; low-frequency ones included. No merges for the sake of count: ride matching (sy26) and proximity (sy43) stay separate, as do Redis (sy01) and distributed cache (sy34). A merge is decided only in Phase 3, after reading two bodies and finding true duplication.
Tiering of case studies: **tier 1** is backed by both public sources read (Primer and Hello Interview); **tier 2** is a well-known real product or infrastructure system; **tier 3** is lower-frequency but real.

### Foundations, distributed systems, resilience

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 1 | sy20 | The System Design Interview Framework | move to the front | core |
| 2 | sy06 | Latency Numbers & Capacity Estimation | move | core |
| 3 | sy01 | Redis Internals & Eviction | keep | core |
| 4 | sy45 | Caching Patterns and Consistent Hashing | NEW | core |
| 5 | sy02 | Postgres I: Indexes & Scans | keep | core |
| 6 | sy03 | Postgres II: MVCC & Locking | keep | core |
| 7 | sy04 | Postgres III: Query Planner & Pooling | keep | core |
| 8 | sy05 | NoSQL, LSM Trees & Cassandra | keep | core |
| 9 | sy47 | Data Modeling and Schema Design | NEW? (check sy02 to sy05 first) | core |
| 10 | sy07 | Replication & Sharding | keep | core |
| 11 | sy08 | CAP Theorem to PACELC | keep | core |
| 12 | sy46 | Time, Clocks and Ordering (Lamport, vector clocks, linearizability) | NEW | core |
| 13 | sy09 | Distributed Consensus & Raft | keep | core |
| 14 | sy10 | Idempotency, Outbox & Sagas | keep | core |
| 15 | sy53 | Workflow Orchestration (Temporal-style) | NEW? (check sy10 first) | extended |
| 16 | sy11 | Kafka I: The Log & Producers | keep | core |
| 17 | sy12 | Kafka II: Consumers & Compaction | keep | core |
| 18 | sy16 | Networking, TLS & Load Balancing | keep | core |
| 19 | sy17 | API Design, Auth & Gateways | keep | core |
| 20 | sy13 | Docker & Container Internals | keep; benchmark against a container source in Phase 3 | extended |
| 21 | sy14 | Kubernetes I: Core Control Plane | keep; same | extended |
| 22 | sy15 | Kubernetes II: Networking & Rollouts | keep; same | extended |

### Reliability engineering (new block, in scope per owner)

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 23 | sy18 | Resilience: Rate Limiting & Circuit Breakers | keep | core |
| 24 | sy19 | Observability: Metrics, Tracing & Alerting | keep | core |
| 25 | sy48 | SLOs, SLIs and Error Budgets | NEW | core |
| 26 | sy49 | Overload, Load Shedding and Cascading Failures | NEW | core |
| 27 | sy50 | Incident Response and Blameless Postmortems | NEW | extended |

### Scaling patterns (new block)

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 28 | sy51 | Scaling Patterns I: Reads, Writes and Contention | NEW | core |
| 29 | sy52 | Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates | NEW | core |

### Case studies: existing

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 30 | sy21 | TinyURL & Distributed ID Generator | keep | core |
| 31 | sy22 | Distributed Rate Limiter | keep | core |
| 32 | sy23 | WhatsApp / Real-Time Chat (add presence and typing indicators) | deepen | core |
| 33 | sy24 | Twitter / Instagram Newsfeed | keep | core |
| 34 | sy25 | YouTube / Netflix Video Streaming | keep | core |
| 35 | sy26 | Uber / Geospatial Ride Matching | keep | core |
| 36 | sy43 | Proximity Service & Location-Based Systems | deepen (thin) | core |
| 37 | sy27 | Ad-Click Aggregator & Stream Processing | keep | core |
| 38 | sy28 | Time-Series Metrics System | keep | core |
| 39 | sy29 | Payment Ledger & Digital Wallet | keep | core |
| 40 | sy30 | Distributed Task Scheduler | keep | core |
| 41 | sy31 | Search Typeahead / Autocomplete | keep | core |
| 42 | sy33 | Notification System | keep | core |
| 43 | sy34 | Distributed Cache (Memcached/Redis) | keep | core |
| 44 | sy35 | Distributed Object Storage (S3) | keep | core |
| 45 | sy36 | Distributed Message Queue (SQS / RabbitMQ) | keep | core |
| 46 | sy37 | Distributed Search Engine (Elasticsearch at Scale) | deepen (thin) | core |
| 47 | sy38 | Real-Time Collaborative Docs & Whiteboard | deepen (thin) | extended |
| 48 | sy39 | Real-Time Gaming Leaderboard | deepen (thin) | extended |
| 49 | sy42 | Flash Sale & Ticket Reservation (Ticketmaster) | deepen (thin) | core |
| 50 | sy44 | Stock Exchange & Order Matching Engine | deepen (thin) | extended |
| 51 | sy40 | Distributed Transactions, Spanner TrueTime & Multi-Region DR | deepen (thin) | advanced |
| 52 | sy32 | Low-Level Design (LLD) & Machine Coding | deepen | core |
| 53 | sy41 | Machine Coding: Parking Lot, Splitwise & In-Memory DB | deepen (thin) | extended |

### Case studies: new, tier 1 (backed by both public sources)

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 54 | sy54 | Web Crawler | NEW | core |
| 55 | sy55 | File Sync and Storage (Dropbox / Google Drive) | NEW (check sy35 overlap) | core |
| 56 | sy56 | Top-K and Trending (YouTube top videos, hashtags) | NEW | core |

### Case studies: new, tier 2 (real products and infrastructure)

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 57 | sy57 | Maps Routing and ETA (Google Maps) | NEW | extended |
| 58 | sy58 | Hotel and Flight Booking (Airbnb / Booking.com) | NEW | extended |
| 59 | sy59 | Online Auction (eBay) | NEW | extended |
| 60 | sy60 | Online Judge with Sandboxed Code Execution (LeetCode) | NEW | extended |
| 61 | sy61 | Video Conferencing (Zoom / Meet, WebRTC) | NEW | extended |
| 62 | sy62 | Music Streaming (Spotify) | NEW | extended |
| 63 | sy63 | Email Service (Gmail) | NEW | extended |
| 64 | sy64 | Food Delivery Dispatch (DoorDash / Swiggy) | NEW | extended |
| 65 | sy65 | Live Streaming with Live Comments (Twitch) | NEW | extended |
| 66 | sy66 | Log Aggregation and Search (ELK / Splunk) | NEW | extended |
| 67 | sy67 | Content Delivery Network | NEW | extended |
| 68 | sy68 | Distributed Lock Service (Chubby / ZooKeeper) | NEW | extended |
| 69 | sy69 | Dynamo-style Key-Value Store | NEW | extended |

### Case studies: new, tier 3 (lower frequency, still real)

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| 70 | sy70 | Dating App Matching and Swipe Feed (Tinder) | NEW | extended |
| 71 | sy71 | Fitness Activity Tracking (Strava) | NEW | extended |
| 72 | sy72 | Multiplayer Game Backend and Matchmaking (online chess) | NEW | extended |
| 73 | sy73 | Price Tracker and Alerts | NEW | extended |
| 74 | sy74 | News Aggregator | NEW | extended |
| 75 | sy75 | Feature Flags and Config Service | NEW | extended |
| 76 | sy76 | Social Graph and "People You May Know" | NEW | extended |
| 77 | sy77 | DNS at Scale | NEW | extended |

**Each case study lesson** has the same shape: requirements, capacity estimates, API and data model, the high-level design, two or three deep dives, failure modes, what real companies did (with dated sources), and drills. "In detail" means the deep dives are worked, not named.

## Behavioral (8 to 13)

Owner delegated the two questions; rulings are in `decisions.md`. No compensation figures anywhere (decision 4).

| # | Id | Title | Status | Level |
|---|---|---|---|---|
| **Block 1: Scored signals** | | | | |
| 1 | be01 | What the Behavioral Round Actually Grades | keep | core |
| 2 | be02 | Your Core Engineering Stories Inventory | keep 8 as inventory, mark 3 to 5 as the core set | core |
| 3 | be13 | The Big Three Opening Questions (about you, most impactful project, a conflict) | NEW? (check be02 and be03 first) | core |
| **Block 2: Decisive questions and company specifics** | | | | |
| 4 | be03 | The High-Stakes Killer Questions | keep | core |
| 5 | be04 | Company-Specific Loops (Amazon LP & Googleyness) | keep; add other companies only after reading their sources | core |
| 6 | be06 | Mock Behavioral Rounds & Self-Scoring (add questions to ask the interviewer) | deepen | core |
| **Block 3: Offers** | | | | |
| 7 | be05 | The Recruiter Screen & Negotiation Structure | rewrite (source outside the repo still has about 17 figures) | core |
| 8 | be08 | Offer Structure and Equity Playbook | deepen (already de-figured; thin) | extended |
| **Block 4: Staff scope** | | | | |
| 9 | be07 | Leveling Matrix: Mid (L4) vs Senior (L5) Mastery | deepen (thin); the first sample lesson | extended |
| 10 | be09 | What Staff Engineers Do: Scope and Archetypes | NEW | advanced |
| 11 | be10 | Writing Engineering Strategy and Design Docs | NEW | advanced |
| 12 | be11 | Operating at Staff: Quality, Alignment and Presenting to Executives | NEW | advanced |
| 13 | be12 | Career Growth: Promotion Packets, Sponsors and Visibility | NEW | advanced |

## Cross-cutting rules

- **Pathways:** Crash = core lessons rated 5 stars; Standard = core; Deep = core plus extended plus advanced. After authoring, `npm run pathways` regenerates them; a build check fails if any lesson is unreachable.
- **Prerequisites** (`prereqs`), objectives and level are authored per lesson during Phase 3, not here.
- **Foundations first:** AI Engineering's Block 0 sits before RAG (decision 1), so Crash for AI starts with foundations only if their stars are 5; decide when the foundations lessons are rated.
- **Compensation:** `be05` and `be08` carry structure and sources, never figures.
- **Visuals:** scenes only for flagship lessons (decision 3); good candidates are `ai28` (gradient descent), `ai30` (attention), `sy45` (consistent hashing), `sy46` (clocks) and `ds26` (sorting).

## Build order (Phase 3), each wave ends at an owner review

1. **Sample (one lesson):** `be07`. Rewritten alone, then reviewed. Nothing else is touched until the owner approves its style and depth.
2. **Wave 1, thin advanced lessons:** `ai23` to `ai26`, `ds19` to `ds25`, `sy37` to `sy44`, `be08`. Deepening first, because they are the weakest.
3. **Wave 2, gaps with two-source backing:** `ai28` to `ai31`, `ds26`, `ds27`, `ds28`, `sy45`, `sy46`, `sy48` to `sy52`, `sy54` to `sy56`, `be09` to `be12`.
4. **Wave 3, the case-study library:** `sy57` to `sy69` (tier 2), then `sy70` to `sy77` (tier 3).
5. **Wave 4, conditionals:** resolve each `NEW?` after reading the relevant lesson body; write the ones still needed.

Each wave starts with one lesson shown to the owner before the rest of the wave is written.

## Questions for the owner

1. **Cap:** raise 140 to about 155? (Recommended.) Otherwise name what to cut.
2. **Advanced level:** is "advanced = optional, outside Crash and Standard" right for ds19 to ds25 and ai23 to ai26?
3. **Tier 3 case studies:** keep all eight, or stop after tier 2?
4. **Foundations in the Crash path:** should AI's foundations arc be in Crash, or only in Standard and Deep?
