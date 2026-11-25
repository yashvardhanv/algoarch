# System Design: benchmark (DRAFT 1)

Status: first pass, 2026-11-26. Phase 1 of `docs/plans/curriculum-overhaul-plan.md`; binding owner decisions are in `docs/curriculum/decisions.md`.
Not yet owner-reviewed. Every "Ours" cell is judged from **lesson titles and audit flags only**, not from the lesson bodies. Treat each as a hypothesis for the Phase 3 per-lesson review.

## Sources read (access date 2026-11-26)

| Code | Source | What was read | Limit |
|---|---|---|---|
| SDP | System Design Primer (GitHub README) | section index, 8 named system design exercises, 6 object-oriented design exercises, the appendix question list | only the first ~40K of 134K characters came back verbatim; later sections (DNS, CDN, load balancers, database, cache) rest on a summary |
| HI | Hello Interview system design guide (server-rendered pages) | navigation only: 9 core concepts, 10 key technologies, 7 common patterns, 32 question breakdowns, advanced topics | section bodies not opened; some items are paywalled, so only their titles are known |
| MIT | MIT 6.5840 Distributed Systems, Spring 2026 | 22-session schedule | marked tentative; read through a summarizing fetch |
| SRE | Google SRE book and SRE Workbook (sre.google) | both tables of contents | chapter bodies not read; licensed CC BY-NC-ND, so only headings are paraphrased here |

**Not read yet:** *Designing Data-Intensive Applications*, Alex Xu / ByteByteGo, AWS Well-Architected, Jepsen analyses, the key papers (Dynamo, Bigtable, Spanner, Kafka, Chubby, Borg), Martin Fowler, and any Kubernetes or container source. Our four container and Kubernetes lessons (`sy13` to `sy15`) are therefore **untested** against any source.

## Coverage matrix

`D` = dedicated chapter, session or breakdown; `P` = part of one; `-` = not named; `?` = judged from title only.

| Topic | SDP | HI | MIT | SRE | Ours (lesson ids) |
|---|---|---|---|---|---|
| Latency numbers, capacity estimation | D (appendix) | D (Numbers to Know) | - | - | `D` sy06 |
| Networking: DNS, CDN, load balancers, TLS | D | D (Networking Essentials) | - | P (load balancing chapters) | `D` sy16 ? |
| API design and auth | P (REST, RPC) | D | - | - | `D` sy17 |
| Data modeling | - | D | - | - | `-` |
| Caching patterns (cache-aside, write-through, write-behind) | D | D | P (Memcached at Facebook) | - | `P` sy01 ?, sy34 |
| Sharding and consistent hashing | D | D (two concepts) | - | - | `P` sy07 ? |
| Replication | D | - | D (chain replication, GFS) | - | `P` sy07 |
| CAP, consistency models, linearizability | D | D | D | - | `D` sy08 ? |
| Consensus (Paxos, Raft), coordination (ZooKeeper) | - | D (ZooKeeper) | D (Paxos, Raft x2, ZooKeeper) | P (distributed consensus chapter) | `D` sy09 ? (Raft) |
| Distributed transactions (2PC, Spanner) | - | - | D | - | `D` sy40 (thin), sy10 (sagas) |
| Time and ordering (clocks) | - | - | P | - | `-` |
| Relational and NoSQL storage, indexing | D | D (Postgres, Cassandra, DynamoDB, indexing) | - | - | `D` sy02-sy05 |
| Queues and event streams | D | D (Kafka) | - | - | `D` sy11, sy12, sy36 |
| Search | - | D (Elasticsearch) | - | - | `D` sy37 (thin) |
| Workflow orchestration | - | D (Temporal, multi-step processes) | - | - | `-` (sagas in sy10) |
| Stream processing | - | D (Flink) | - | P (data pipelines) | `P` sy27 |
| Scaling patterns (reads, writes, contention, large blobs, long-running tasks, real-time updates) | P | D (7 patterns) | - | - | `P` spread across case studies ? |
| SLOs, error budgets, alerting, toil | - | - | - | D (SRE ch. 3-6, 10; Workbook 2-5) | `P` sy19 (alerting) |
| Overload, cascading failures, data integrity | - | - | - | D (SRE ch. 21, 22, 26) | `P` sy18 ? |
| Incident response and postmortems | - | - | - | D (SRE ch. 13-16; Workbook 9-10) | `-` |
| Release engineering and canarying | - | - | - | D (SRE ch. 8; Workbook 16) | `P` sy15 (rollouts) |
| Containers and Kubernetes | - | - | - | - | `D` sy13-sy15 (no source read) |
| Security | D (section) | P (API gateway, auth) | - | - | `P` sy17 ? |
| Object-oriented / low-level design | D (6 exercises incl. LRU, parking lot) | - | - | - | `D` sy32, sy41 (thin) |
| Observability | - | - | - | D (monitoring chapters) | `D` sy19 |

### Case studies versus our lessons

| Case study | SDP | HI | Ours |
|---|---|---|---|
| URL shortener | yes | yes (Bitly) | `sy21` |
| Chat / WhatsApp | appendix | yes | `sy23` |
| News feed / timeline | yes | yes | `sy24` |
| Video streaming | - | yes (YouTube) | `sy25` |
| Ride matching / proximity | - | yes (Uber, Yelp, proximity search) | `sy26`, `sy43` |
| Rate limiter | appendix | yes | `sy22` |
| Ad-click aggregator | - | yes | `sy27` |
| Metrics monitoring | - | yes | `sy28` |
| Payments | - | yes | `sy29` |
| Job scheduler | - | yes | `sy30` |
| Notification system | - | yes | `sy33` |
| Distributed cache / key-value store | appendix | yes | `sy34` |
| Ticketing / flash sale | - | yes (Ticketmaster, Flash Sale) | `sy42` |
| Google Docs / collaborative editing | appendix | yes | `sy38` |
| Stock exchange / trading | appendix | yes (Robinhood) | `sy44` |
| **Web crawler** | yes | yes | **none** |
| **File sync (Dropbox)** | appendix | yes | **none** |
| Top-K (YouTube top K, trending) | appendix | yes | `sy39` (leaderboard) is related, not the same |
| News aggregator, online auction, price tracker, Tinder, Strava, online chess, LeetCode | - | yes (premium titles) | none; lower priority |
| Typeahead, object storage, message queue, search engine at scale | - | - | `sy31`, `sy35`, `sy36`, `sy37` (ours are extras relative to these two sources) |

Reading the matrix: our case-study coverage is strong. The two named gaps shared by both the Primer and Hello Interview are the **web crawler** and **file sync**. The bigger gaps are in the conceptual layer: **reliability engineering** (SLOs, error budgets, overload and cascading failure, incidents and postmortems) is a whole Google book and we have two lessons on adjacent ideas; **consistent hashing, caching patterns, and data modeling** are core concepts in two sources and have no lesson of their own by title; and **time and ordering** appears only as one MIT session.

## Hypotheses for the outline (to confirm, not decided)

| # | Proposed change | Action | Why | What gives |
|---|---|---|---|---|
| 1 | Web crawler case study | add 1 | both SDP and HI include it | none |
| 2 | File sync (Dropbox-style) | add 1, or extend `sy35` after review | both sources include it; overlaps object storage | decide after reading `sy35` |
| 3 | Reliability: SLOs and error budgets; overload and cascading failures; incident response and postmortems | add 2 lessons, or deepen `sy18` and `sy19` | SRE book parts II and III are entirely this; we only touch alerting and circuit breakers | none |
| 4 | Caching patterns and consistent hashing | add 1 lesson or fold into `sy01` and `sy07` | named concepts in SDP and HI, no title of ours | shorten Redis-specific detail |
| 5 | Time, ordering and consistency models | add 1 | MIT linearizability session; `sy08` may cover part of it | none |
| 6 | Data modeling | check `sy02` to `sy05` first | HI core concept | none if covered |
| 7 | Scaling patterns (contention, read/write scaling, large blobs, long-running tasks) | add 1 or 2 pattern lessons that the case studies link to | HI organizes ten of its breakdowns around them | none |
| 8 | Workflow orchestration (Temporal-style) | check `sy10` first | HI key technology and pattern | none |
| 9 | Merge overlapping lessons | review for merge: `sy26` with `sy43` (both geospatial); `sy01` with `sy34` (Redis vs distributed cache); `sy32` with `sy41` (machine coding) | audit-time reading found topic overlap that title similarity could not | frees about 3 lessons to pay for the additions |
| 10 | Thin lessons `sy37` to `sy44` | deepen | all flagged thin; most also lack practice | none |
| 11 | Containers and Kubernetes | benchmark separately | no source read | n/a |

Net effect if all accepted: System Design grows from 44 to about 50, or about 47 after the merges in row 9.

## Open questions

1. Is reliability engineering (SRE material) in scope for this course, or a separate interview-adjacent track?
2. Should low-frequency case studies (auction, Tinder, Strava, chess) be skipped entirely?

## Next steps

1. Read DDIA's contents and the key papers, a Kubernetes source, and Alex Xu / ByteByteGo; add their columns.
2. Re-judge each "Ours" cell against the lesson body, starting with the merge candidates in row 9.
3. Benchmark Behavioral next.
