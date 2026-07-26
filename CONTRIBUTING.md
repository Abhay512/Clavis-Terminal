# Contributing to Clavis Terminal

Thanks for being here. This project is a real-time market-data system, and most of it is
ordinary, high-quality engineering — concurrency, storage, resilience, APIs, interface work —
which means there is a lot here that does not require knowing anything about options trading.

**Start here:** [good first issues](https://github.com/Abhay512/Clavis-Terminal/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
· [help wanted](https://github.com/Abhay512/Clavis-Terminal/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22)

---

## Read this first: what this repository is and is not

This repository is the **platform** — ingestion, analytics infrastructure, storage, API and
interface. It is **not** the trading strategy.

The decision engines in `backend/engine/` ship as **reference implementations**: same public
interface as production, same output shape, fully runnable, deliberately simpler. The calibrated
thresholds in `config.py` are neutral defaults, not fitted values. This is stated in the README
and it is permanent.

**Why this matters for you:** it saves you from spending a weekend on a PR that cannot be
merged. The table below is honest about where your time will and will not pay off.

### Where contributions are very welcome

| Area | Examples |
|:--|:--|
| **Infrastructure & resilience** | reconnect logic, backfill correctness, crash safety, graceful shutdown, clock and timezone handling |
| **Storage & performance** | Parquet layout, SQLite query and index work, memory footprint, profiling the hot path |
| **Broker adapters** | abstracting `feed/` behind an interface so other brokers or a simulated feed can drive the same engine |
| **Dashboard & UX** | accessibility, responsive layout, keyboard navigation, colour-blind safety, new visualisations, performance under high row throughput |
| **Testing** | more coverage on the pure functions, property tests for the flow decomposition, fixtures, a synthetic feed harness |
| **Tooling & DX** | CI, type hints, Docker, developer scripts, editor config |
| **Documentation** | setup on other platforms, clearer explanations, diagrams, fixing anything that is wrong or unclear |
| **New analytics boards** | a new read-only board computed from data the engine already produces |

### Where contributions cannot be merged

| Area | Why |
|:--|:--|
| **Tuning the reference thresholds** | The published numbers are deliberately neutral. "I optimised `OW_MIN_SCORE` to 62" cannot be evaluated, because the data it was fitted on is not in this repository. |
| **Restoring the withheld production logic** | The gap is intentional, not an oversight or a TODO. |
| **Strategy changes justified only by a backtest we cannot reproduce** | If the result cannot be regenerated from a recording anyone can run, it cannot be reviewed. See [Changing detection logic](#changing-detection-logic). |
| **Anything that places orders** | This system is deliberately read-only. Execution belongs in a separate project with a very different review standard. |

If you are unsure which side of the line an idea falls on, **open an issue and ask before you
build.** That is always faster than finding out in review.

---

## Development setup

You do **not** need a broker subscription to develop against most of this repository. The engine
runs against synthetic input in tests, and the dashboard runs entirely on generated fixtures.

### Using Developer Scripts (Makefile / dev.cmd)

To simplify common tasks, you can use the provided `Makefile` (macOS/Linux) or `dev.cmd` (Windows) from the root directory.

#### macOS/Linux (Makefile)
```bash
make install       # Installs both backend and dashboard dependencies
make lint          # Runs ruff check on the backend
make test          # Runs backend tests
make build         # Compiles backend and builds dashboard
make dev-dashboard # Starts the dashboard development server
```

#### Windows (dev.cmd)
```cmd
dev.cmd install       # Installs both backend and dashboard dependencies
dev.cmd lint          # Runs ruff check on the backend
dev.cmd test          # Runs backend tests
dev.cmd build         # Compiles backend and builds dashboard
dev.cmd dev-dashboard # Starts the dashboard development server
```

### Backend

```bash
git clone https://github.com/<your-fork>/Clavis-Terminal.git
cd Clavis-Terminal/backend

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install ruff

python -m tests.test_oneway        # 9 checks, no market needed
ruff check .                       # must be clean
```

### Dashboard

```bash
cd dashboard
npm install
cp .env.local.example .env.local
```

Set `NEXT_PUBLIC_DEMO=true` in `.env.local` and the whole interface renders against fixtures with
no backend at all:

```bash
npm run dev            # http://localhost:3000
npx tsc --noEmit       # must be clean
npm run build          # must succeed
```

### Everything at once, in containers

```bash
docker compose up -d --build
docker compose run --rm backend python -m tests.test_oneway
```

---

## Before you open a pull request

Run what CI runs. It takes about a minute and saves a review round-trip.

```bash
# backend
cd backend
ruff check .
python -m compileall -q .
python -m tests.test_oneway

# dashboard
cd ../dashboard
npx tsc --noEmit
npm run build
```

CI runs the same checks on Python 3.11/3.12 and Node 18/20, builds both container images, and
fails the build if a `.env` file or a credential-shaped string ever appears in the tree.

---

## Code style

Not many rules, and the linter enforces most of them.

**Python**

- Ruff is the source of truth — configuration lives in `backend/pyproject.toml`. Run `ruff check .`
  and `ruff check . --fix`.
- Line length 100. Type hints on anything public.
- Standard library over a dependency. A new runtime dependency needs a reason in the PR
  description; this process runs unattended during market hours and every package is a new way
  for that to stop being true.

**TypeScript**

- Strict mode, no `any` in new code.
- Colours come from the Tailwind theme tokens, never hard-coded hex. The palette is
  colour-vision-deficiency separated on purpose — see `tailwind.config.ts`.
- One component per board, matching the existing file layout.

**Comments**

Write comments that explain *why*, not *what*. If a threshold or an ordering is non-obvious, one
line explaining the reasoning is worth more than a paragraph restating the code. Skip the
paragraph.

**Commits**

Conventional-commit prefixes, one logical change per commit:

```
feat(engine): add a rolling median helper for baseline flow
fix(feed): reconnect after a socket close with no error frame
docs: clarify the redirect-URL step in Kite setup
test: cover the roll-netting branch in ranking
refactor(dashboard): extract the shared meter component
build: pin the Node base image
```

---

## Changing detection logic

Anything that affects what appears on a board is held to a stricter standard than the rest of the
codebase, because a plausible-looking rule that is quietly wrong is expensive in a way a UI bug is
not.

1. **Synthetic tests prove the wiring, never the rule.** A synthetic feed can ramp open interest
   in ways real strikes physically cannot. Rules have passed synthetic tests here while being
   mathematically impossible on live data.
2. **Validate on a recording.** Use `replay.py` against a real recorded session. State which
   session, and what changed.
3. **Show the failure case too.** A change that only ever improves things has usually not been
   tested hard enough. Say what it makes worse.
4. **Keep it explainable.** If the reason a signal fired cannot be read off the board at the
   moment it fires, it does not ship. This applies to learned components as much as to rules — see
   the README's [rules-versus-model section](README.md#rules-or-a-learned-model).

---

## Reporting bugs

Use the [bug report template](https://github.com/Abhay512/Clavis-Terminal/issues/new?template=bug_report.yml).
The single most useful thing you can include is the **boot log** — the first twenty lines tell a
reviewer almost everything about universe size, token state and feed health.

**Never paste an API key, an API secret or an access token into an issue.** If you post one by
accident, [regenerate it immediately](https://developers.kite.trade/) — assume anything published
on the internet is compromised the moment it appears.

## Reporting a security issue

Do **not** open a public issue. See [SECURITY.md](SECURITY.md).

---

## A note on scope and review

This is maintained alongside a live trading operation, so review is sometimes slower than you
would like — please be patient, and feel free to bump a PR that has gone quiet for a week.

Small, focused pull requests get merged. Large ones that mix a refactor, a feature and a style
pass tend to stall, not because they are bad but because they are hard to review with confidence.
If you are planning something substantial, open an issue first and let us agree on the shape of it
before you write the code.

By contributing you agree that your work is licensed under the [MIT License](LICENSE), and that
you have read the [Code of Conduct](CODE_OF_CONDUCT.md).
