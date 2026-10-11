# kolosok-rehack — AI Development Guidelines

Team **Kolosok** at the **European Hackathon League (EHL) Grand Finale**, Munich (TUM.ai).
This file is the rulebook for every AI agent (Claude Code, Codex, Cursor, …) and human working in this repo.
**Read it fully before your first change.** Human setup (GitHub token, credentials) lives in `README-Human`.

Source: [EHL Finale – All you need to know](https://tum-ai.notion.site/EHL-Finale-All-you-need-to-know-3eb7306bfd62808993e9ec18c2d64834)

---

## 0. Hard rules (non-negotiable)

1. **Entire must be enabled and every commit must carry a checkpoint.** The organisers will reject a submission that does not use Entire. No Entire → no valid submission.
2. **All work goes through git and gets pushed to `origin`.** Nothing that exists only on one laptop counts.
3. **`main` must always be demo-able.** We have a strict 6-minute slot for pitch + demo + questions.
4. **Never commit secrets** (API keys, tokens, `.env`). Entire redacts secrets in session logs, but do not rely on that.
5. **Never rewrite pushed history** (no `push --force`, no amending/rebasing pushed commits, no deleting `entire/*` branches or refs). Checkpoints are tied to commits; rewriting history can orphan them.
6. **Use English for code text and website copy.** Write comments, UI labels, and generated report prose in English. Preserve customer quotes and source fields verbatim as evidence.

## 1. Key times (Munich local time)

| When | What |
|---|---|
| Sat 10 Oct, 11:00–11:30 | Entire technical onboarding |
| **Sat 10 Oct, 13:00** | **Challenge selection deadline** (captain, on https://ehl.gg/) |
| Sat 13:30 → Sun 12:00 | Hacking |
| **Sun 11 Oct, 12:00** | **Submission deadline** — hard stop |
| Sun 12:00–14:30 | Challenge pitches (6 min incl. Q&A) |
| Sun 15:30–16:30 | Main-stage final (6 teams) |

Internal targets: **feature freeze Sun 10:00**, first full submission by **Sun 10:30**, final re-submission by **11:45**.
Submissions can be repeated as often as we like before the deadline, so submit early and update.

**Challenge:** BMW Group — AI for Product Decision Making: an app that turns customer feedback, product/sales data and web research into prioritized, PM-reviewed customer requirements with a full audit trail. Details: [`BMW-Challenge.md`](BMW-Challenge.md).

## 2. Setup checklist (each machine, once)

Prerequisites: `git` on `PATH` (Entire shells out to it — it fails with `exec: "git": executable file not found` otherwise).

```bash
# 1. Install Entire (bash / Git Bash). On Windows the binary ends up in ~/.local/bin/entire.exe
curl -fsSL https://entire.io/install.sh | bash

# 2. On the main branch of this repo:
git checkout main && git pull
git config pull.rebase true      # plain `git pull` makes merge commits, which carry no checkpoint
entire login                     # if not logged in yet
entire enable                    # enables session tracking in this repo
entire agent add claude-code     # install hooks for your agent; `entire agent list` shows others (codex, cursor, …)

# 3. Verify
entire status
entire doctor                    # if anything looks off
```

**You are set up correctly when** your next commit prints:

```
[entire] Pushing 1 checkpoint ref(s) to origin.... done
```

If you don't see that line, stop and fix Entire before writing more code.

## 3. Git workflow

- **Commit small and often** — at least every meaningful step, ideally every 15–30 min of agent work. Each commit becomes a checkpoint linking the code to the prompt/reasoning behind it.
- **Commit only from within a tracked agent session**, after the agent made the change with its file-edit tools. Hand-made commits, merge commits and shell (`sed`, `echo >`) edits get no checkpoint.
- **After every commit** check the checkpoint is there: `git log -1 --format=%B` must show an `Entire-Checkpoint:` line. If it is missing, fix it *before* pushing.
- **Commit messages:** imperative, prefixed by area, e.g. `feat(api): add route planner endpoint`, `fix(ui): handle empty results`, `docs: update run instructions`. Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `demo`.
- **Sync before push:** `git pull --rebase` on *unpushed* local commits only, then `git push`. Resolve conflicts, never discard teammates' work.
- **Branches:** short-lived feature branches (`feat/<topic>`, `fix/<topic>`) merged back to `main` quickly (within a few hours). Trivial fixes may go straight to `main`. Do not let branches drift overnight.
- **Do not commit:** `.env`, credentials, `node_modules/`, virtualenvs, large datasets or model weights, build artifacts. Add them to `.gitignore` as soon as they appear.
- **After every push** check the `[entire] Pushing … checkpoint ref(s)` line appeared.

## 4. How agents should work here

**Before starting a task**
1. Read this README, `README-Human` and **`VISION.md`** (our product idea, shared context for everyone); look at `Concept/` for the architecture sketch (`root.drawio`).
2. `git pull` and check what others (human or agent) are doing:
   - `entire recap` — summary of recent checkpoint activity
   - `entire session list` — active/past agent sessions
   - `entire checkpoint search "<topic>"` — has someone already tried this?
3. Confirm the task is not already in progress to avoid duplicate work.

**While working**
- Keep scope tight: do the requested task, nothing more. Hackathon time is the scarcest resource.
- Prefer simple, working solutions over clever ones; a reliable demo beats extra features.
- Match existing structure, naming, and style. Don't introduce new frameworks or languages without team agreement.
- Keep the app runnable at every commit. If you break `main`, fixing it is the top priority.
- Document how to run anything you add (see §6) in the same commit.
- Use `entire agent-help` for machine-readable, version-accurate CLI usage instead of guessing commands.

**Handing off / resuming**
- Use `entire session resume <branch>` or `entire checkpoint explain <id|sha>` to pick up someone else's context instead of re-deriving it.
- `entire dispatch` produces a summary of recent agent work — use it for handoffs and pitch prep.

**When unsure** about requirements or the challenge brief: ask the team; challenge questions go to the partners on **Discord** (https://discord.gg/4UDNd5TAg). Do not assume partner support is available overnight.

## 5. LLMs, keys, and resources

- **OpenAI** is a tech partner: each participant has **75 USD** of LLM/API credits. Use them for app-level LLM calls.
- Keys go in a local `.env` (gitignored) and are read via environment variables; provide a `.env.example` with placeholder names only.
- Be mindful of token spend; `entire session tokens <id>` / `entire checkpoint tokens <id>` show usage.

## 6. Demo & submission readiness

- Judging is a **strict 6-minute slot including questions** — design the product around one clear, rehearsable demo flow.
- Keep a **"How to run"** section here up to date (install, env vars, start command, demo script).
- Before submission: everything pushed, Entire checkpoints present (`entire checkpoint list`), all relevant content uploaded on https://ehl.gg/.
- Have a fallback (recorded video or screenshots) in case the live demo fails.

### How to run

Feedback analysis is available in [`feedback_topics_package/`](feedback_topics_package/README.md).
It extracts topics from Excel feedback locally with TF-IDF and average linkage,
computes deterministic sentiment statistics, and optionally adds English AI summaries.
Requires Python 3.10 or newer. From the repository root:

```powershell
cd feedback_topics_package
python -m pip install -r requirements.txt
python feedback_topics.py "path/to/input.xlsx" --output topics.json
python summarize_topics.py topics.json --output topics_stats.json --stats-only
python summarize_topics.py topics.json --output topics_summary.json --model gpt-5.4 --workers 5 --language en
python export_topics.py topics_summary.json
python -m unittest discover -p "test_*.py"
```

The second stage reads `OPENAI_API_KEY` or prompts for it with hidden input.
AI summaries send selected feedback excerpts to the OpenAI API and incur API charges.
Keep source data and generated reports local. See [topic extraction](feedback_topics_package/README_RU.md)
and [statistics and AI summaries](feedback_topics_package/README_SUMMARIES_RU.md)
for input columns, settings, and output formats.

The optional third stage creates `<input_stem>.readable/` with a self-contained
`report.html`, Markdown overview, compact JSONL catalog, complete per-topic JSON
records, and a data-reading guide. Open the HTML directly in a browser. Export is
fully local, uses only the standard library, preserves the source and requires no
new AI calls. See [readable exports](feedback_topics_package/README.md#readable-report-and-ai-exports-stage-3).

The [local data library](feedback_topics_package/DATA_LIBRARY.md) imports XLSX and
PDF sources into versioned SQLite storage and exports portable JSONL/schema/source
bundles. From `feedback_topics_package`, run `python data_library.py ingest-all .`,
then `python data_library.py status` to list completed and pending analyses separately.
This reuses existing analyses and does not start new AI calls.

## 7. Repo map

| Path | Purpose |
|---|---|
| `README.md` | This file — AI/dev guidelines (agents: start here) |
| `CLAUDE.md`, `AGENTS.md` | Auto-loaded agent entry points; they point here |
| `README-Human` | Human onboarding: GitHub token & credential setup |
| `BMW-Challenge.md` | BMW challenge brief: mission, scope, data, deliverables |
| `VISION.md` | Our product idea (decision graph / thought chains): read before building |
| `Concept/root.drawio` | Architecture / concept diagram |
| `.claude/`, `.codex/`, `.entire/` | Entire hook config — generated by `entire enable`; do not edit by hand |

