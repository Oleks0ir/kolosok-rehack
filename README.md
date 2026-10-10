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

**Challenge:** BMW Group. _Brief details TBD; add a one-line summary of the task here._

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
1. Read this README and `README-Human`; look at `Concept/` for the architecture sketch (`root.drawio`).
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

Prerequisites: Python 3.10+.

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The app stores runs in `data/workbench.sqlite3` and includes a small synthetic BMW 5 Series demo dataset. The interactive API is at `http://127.0.0.1:8000/docs`.

Optional integrations are configured through environment variables or a local `.env` file:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | LLM signal classification, requirement drafting and embeddings |
| `OPENAI_MODEL` | OpenAI model name; defaults to `gpt-6-luna` |
| `TAVILY_API_KEY` | Live web search and source enrichment |
| `DATABASE_PATH` | SQLite file path; defaults to `data/workbench.sqlite3` |

Without API keys, the pipeline runs locally with rule-based extraction, hashed text vectors and explainable scoring. When a key is configured, relevant evidence is sent to that provider. Never put a real key in a committed file.

To enable an integration, copy `.env.example` to `.env`, fill only the key(s) you want to use, and restart the app.

### Demo script

1. Select **Run demo pipeline** to load the included evidence and run M1–M5.
2. Open the highest-ranked requirement and follow its signal and source links.
3. Approve, reject, edit or challenge a requirement at the M6 PM gate; each action needs a comment.
4. Propose a measurable customer-facing target and approve it at M7.
5. Optionally compare A/B/C persona scenarios at M8. Results are labelled simulated and low evidence; the PM must opt in before they affect the score.
6. Sign off approved requirements at M9. Use **Replay from a step** to create a new run branch; previous runs and their audit records remain available.

Imports accept CSV, JSON or plain text. CSV works best with columns such as `source_type`, `source_ref`, `market`, `model`, `date`, `reliability` and `text_or_value`. Export prioritized requirements from the **Export CSV** control.

## 7. Repo map

| Path | Purpose |
|---|---|
| `README.md` | This file — AI/dev guidelines (agents: start here) |
| `CLAUDE.md`, `AGENTS.md` | Auto-loaded agent entry points; they point here |
| `README-Human` | Human onboarding: GitHub token & credential setup |
| `Concept/root.drawio` | Architecture / concept diagram |
| `.claude/`, `.codex/`, `.entire/` | Entire hook config — generated by `entire enable`; do not edit by hand |

