# AlgoArch — 50LPA FAANG Engineering Career Platform

[![Node.js](https://img.shields.io/badge/Node.js-18+-green.svg)](https://nodejs.org/)
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-4285F4.svg)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-10b981.svg)]()

> A publication-quality, production-grade engineering career acceleration platform calibrated for the ₹50LPA–₹1.2Cr+ Senior (L5) and Staff (L6) FAANG engineering hiring bar.

---

## ⚡ Key Highlights & Core Capabilities

- **106+ Sequenced Engineering Chapters**:
  - **Data Structures & Algorithms (26 Lessons)**: Core pattern recognition, Cyclic Sort, Topological Sort, Monotonic Queues, and Big-O invariants.
  - **High-Level Distributed Systems (44 Lessons)**: Flash sale 100k QPS ticket reservation, sub-20ms proximity services (Geohash vs H3 vs S2), ultra-low latency exchange matching engines (LMAX Disruptor), and consensus protocols (Raft/Paxos).
  - **Machine Learning & AI Systems (28 Lessons)**: Two-Tower recommendation funnels, DLRM ranking, context-aware embeddings, Vector ANN indexes (HNSW, ScaNN), and multi-tenant LLM inference gateways.
  - **Behavioral Altitude (8 Lessons)**: Amazon Leadership Principles, Google L5/L6 scope demonstration, architecture conflict resolution, and trade-off negotiation.
- **Real Google Gemini AI Technical Mentor**:
  - Live in-page contextual technical advisor powered by Google Gemini AI with automatic model fallback chains.
  - Cross-curriculum semantic deep-linking dynamically suggesting related chapters and failure mode diagnostics.
- **3-Tier Subscription & AI Usage Engine**:
  - Server-side enterprise gating (**Free Starter**, **Pro Engineer @ ₹499/mo**, **Staff Elite @ ₹1,499/mo**).
  - No client-side API keys required; automatic calendar midnight quota resets.
- **Creator-Inspired Study Tools**:
  - **Target Company Filter Rail**: Target questions frequently asked at Google, Meta, Amazon, Netflix, Apple, and Uber.
  - **Dynamic Study Planner (Grind 75 Style)**: Generates prioritized weekly syllabus based on weeks to interview and study hours/week.
  - **FAANG Mock Interview Rubric Scorecard**: 4-dimension hiring committee assessment tool (Signal Detection, Invariants, Code Quality, Senior Communication).
- **Interactive Visualizations & Live Monaco IDE**:
  - Monaco code editor for in-browser Python algorithm verification.
  - Interactive browser visualizers for distributed algorithms.
- **Full Admin CMS & LiteLLM Gateway**:
  - Live lesson editor, markdown preview, token tracking audit logs, and per-user quota controls.

---

## 🛠️ Tech Stack & Architecture

- **Backend**: Node.js (built-in http), SQLite, native HTTPS Gemini client (see Architecture below).
- **Frontend**: Vanilla JavaScript (ES6+), Modern Semantic HTML5, CSS Grid/Flexbox design tokens, Marked.js, Monaco Editor AMD loader.
- **AI Gateway**: Google Gemini REST API (`gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`) with enterprise TLS handling and semantic prompt conditioning.

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Node.js 18 or higher
- A Google Gemini API key (export as `GEMINI_API_KEY`)

### 2. Environment Configuration
```bash
# Set your Gemini API Key
export GEMINI_API_KEY="your-gemini-api-key"
# On Windows PowerShell:
$env:GEMINI_API_KEY="your-gemini-api-key"
```

### 3. Installation & Startup
```bash
# Clone the repository
git clone https://github.com/yashvardhanv/faang-career-platform.git
cd faang-career-platform

# Install dependencies
npm install

# Start the server
node server.js
```

The application will be live at:
```
http://127.0.0.1:5050
```

---

## 📁 Repository Layout

```
faang-career-platform/
├── data/
│   ├── curriculum.json        # 106+ sequenced lessons with company tags
│   ├── videos.json            # Verified YouTube technical lectures (oEmbed verified)
│   ├── users.json             # User profiles, streaks, plans, and daily quotas
│   ├── token_usage.json       # LiteLLM audit logs
│   ├── new_lessons/           # Full markdown guides for creator topics
│   └── all_labs_source.zip    # Offline lab download package
├── public/
│   ├── index.html             # Single-page interface with responsive modals
│   ├── style.css              # Anti-AI-slop design system & theme tokens
│   ├── app.js                 # Reactive controller, subscription engine, planner
│   └── vendor/                # Marked.js parser
├── server.js                  # HTTP server and REST API routes (no framework)
├── server_cms_auth.js         # Gemini AI client, subscription tiers, auth logic
└── litellm_tracker.js         # Token tracking and cost accounting middleware
```

---

## Architecture

- **Backend**: Node.js (built-in `http`, no framework), SQLite via `better-sqlite3`, native HTTPS Gemini client. Users, progress and token usage are still JSON files under `data/`.
- **Content is data**: curriculum, lesson guides (markdown), lesson documents (typed blocks), videos and resources live in `data/algoarch.db`. The API returns JSON and never HTML.
- **Frontend**: vanilla shell (`public/`) plus a React lesson reader (`web/`, built with Vite into `public/reader/`). The reader renders lesson documents from `GET /api/lessons/:id`.
- **Lesson document schema** (v1): sections of typed blocks (`paragraph`, `list`, `table`, `code`, `callout`, `card`, `qa`, `code_cell`, `widget`) with an inline AST. See `web/src/types.ts`.

### Setup

```bash
npm install
npm run db:import   # one-off: builds data/algoarch.db from curriculum.json + original lesson files
npm run build       # builds the React reader into public/reader/
npm start
```

`db:import` reads the original lesson markdown and HTML pages once (`--projects <dir>`). After it succeeds, those files are not needed at runtime. Keep a backup of `data/algoarch.db`: it is git-ignored and is now the only copy of the converted content.

Python code cells (Monaco editor + Pyodide in a Web Worker) and the timed-drill quiz are ported. The 279 interactive simulators are JavaScript, not content, so they are not imported yet and appear as placeholders. Monaco loads from cdnjs and Pyodide from jsDelivr on first use, so those features need internet access.

## ⚙️ Configuration (environment variables)

| Variable | Purpose |
| :--- | :--- |
| `GEMINI_API_KEY` | Required for the AI mentor (sent in a header, never in the URL) |
| `AUTH_SECRET` | HMAC secret for session tokens (auto-generated into `data/.auth_secret` if unset) |
| `ADMIN_KEY` | Required `x-admin-key` header for `/api/admin/*`; if unset, admin is loopback-only |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Enables real paid upgrades (order creation + signature verification) |
| `NODE_ENV=production` | Disables dev-only demo upgrades (no payment) |
| `ALLOW_DEMO_UPGRADE=false` | Explicitly disable demo upgrades outside production |
| `NODE_EXTRA_CA_CERTS` | Preferred fix behind a TLS-intercepting proxy; `GEMINI_INSECURE_TLS=1` is a last-resort dev-only opt-out |
| `ALGOARCH_DATA_DIR` | Override the data directory (used by tests) |

Run tests with `npm test`.

### Security model
- Identity comes only from a signed bearer token issued at login; client-sent `userId` is ignored.
- Plan gating (Monaco runner, lab downloads, company filters, planner, rubric) is enforced via server-side entitlements.
- Known limitation: OAuth sign-in buttons are simulated; login does not verify email ownership yet.

## 📜 License
MIT License. Created by Yashvardhan Vyas.
