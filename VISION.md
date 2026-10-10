# Vision — Decision Graph (database of thought chains)

> The team's shared starting idea. Every agent and teammate should read this before working on the product.
> Challenge context: [`BMW-Challenge.md`](BMW-Challenge.md). Status: **idea stage, details still open.**

## The problem

A product manager (PM) defining the next vehicle generation works with many sources of information:
market analysis, conferences, sales figures, customer feedback and more. **These sources are not connected to each other.**
The path from "what we know" to "what we decided" lives in people's heads, slides and meetings. Afterwards it is hard to see
**how and why** a decision was made.

## Our central idea

This is the main innovation of our solution.

A tool that lets the PM arrive at a new specification (a set of requirements, i.e. the solution) **by reasoning it out step by step**.
The emphasis is on **interpretability**: the system must show its reasoning, not just give answers.

**Data structure: a database of thought chains.**
It is inspired by git and graphs; the comparison is loose, not literal.

- **What:** a structure that records **how and why each step of a decision was made**.
- **Why:** to make the decision process **explainable and transparent**.
- **How:** every meeting, agent call, tool run, report and so on creates a **node**. Nodes connect to the nodes they came from or depend on.
  Over time these nodes form a **graph** that anyone can examine to trace a decision back to its origins.

## Bigger ambition (feasibility not yet decided)

Our first idea was an app that **automates the decision-making process end to end**:
a workflow takes the PM's requests and works step by step toward a decision, using tools, agents and so on.
Every step would be recorded as nodes in the graph.

In that setup the chain also becomes a control mechanism, not only a record:

- The PM can **go back to any earlier step**,
- **change an argument or a prioritisation** there,
- and that change **propagates forward** through all the steps that depend on it, updating the end result.

**Open question:** we don't know yet how feasible this is in the hackathon time frame, or which part of it we should build.
Treat this section as the direction, not a committed scope.

## Data model (agreed)

**Core rule:** the graph does no work; it only stores results.
All work happens in **processing steps** (LLM agent, formula, PM action).
**Each step run writes one new node, plus edges to the nodes it used as input.**

### Node types

| Type | What it is | Typically made by |
|---|---|---|
| **Source** | One input data file / document (e.g. "G70 feedback.xlsx") | import step |
| **Evidence** | A tool result: data query output, web search result (with URL), counter-evidence. Stores the exact quotes/rows/URLs | agent tool |
| **Claim** | A finding (complaint, unmet need, competitor gap, trend), linked to its evidence | agent or PM |
| **Assumption** | A forward-looking guess (3–5 years), explicitly marked as not evidence | agent or PM |
| **Question** | An open question: from the agent to the PM, or a PM instruction to the agent | agent or PM |
| **Requirement** | A customer requirement proposal | agent or PM |
| **Score** | Priority score with its formula breakdown | scoring formula |
| **Decision** | PM approves / rejects / postpones / edits **any** node, with reason | **PM only** |
| **Note** | Free input: meeting outcome, expert opinion, PM comment | PM / team |

### Fields

```
Node
  id           e.g. "CLM-012"
  type         Source | Evidence | Claim | Assumption | Question | Requirement | Score | Decision | Note
  content      the result itself
  created_by   "agent:<name>" | "tool:<name>" | "PM:<name>"
  method       prompt or formula used
  rationale    why (LLM explanation or PM comment)
  timestamp
  version      1, 2, 3 …
  replaces     id of the previous version (empty for v1)
  status       ok | stale

Edge
  from, to, relation: derived_from | supports | contradicts | scores | decides
```

### Write rules

1. **Only one write function** (`add_node(type, content, inputs, created_by, method, rationale)`). Nothing else writes to the graph.
2. **Append-only:** nodes are never changed or deleted. An edit creates a new version that points to the old one (`replaces`). The full history is therefore always kept, and that history is the audit trail.
3. **Every node except Source, Question and Note must have inputs**, so nothing is untraceable.
4. **Readable over exhaustive:** one Source node per file, not per row. Evidence keeps its quotes/rows inside its content, so the graph stays small enough for a person to keep an overview.
5. **Human-only nodes:** Decisions and prioritisation weights can only be created by the PM. This is enforced inside `add_node` (it rejects them unless `created_by` is a PM), not in the prompt.

## System: how the graph gets built (agreed)

### The loop: a flexible agent, not a fixed workflow

1. **Look:** the agent reads the current graph (what's known, open, weak or contradictory).
2. **Decide:** it picks its next action and stores why (as the new node's rationale).
3. **Act:** it calls a tool; the result is written as new nodes.
4. **Pause:** after N actions, or when it needs input, it hands over to the PM.

### Agent tools

| Tool | What it does | Writes |
|---|---|---|
| `query_data` | Look into the BMW files (feedback, sales, study, equipment) | Evidence |
| `web_search` | Find competitor info and trends | Evidence (with URL) |
| `add_claim` | State a finding, linked to its evidence | Claim |
| `add_assumption` | State a forward-looking guess, clearly marked | Assumption |
| `propose_requirement` | Turn claims into a requirement | Requirement |
| `score` | Run the fixed scoring formula | Score |
| `challenge` | Look for counter-evidence to an existing node | Evidence (`contradicts`) |
| `ask_pm` | Stop and ask the PM a question | Question |

### The PM steers at any time

Accept, reject or edit any node, say "dig deeper here" or "challenge this", or give a new direction.
PM input becomes the agent's next priority.

### Going back (propagation)

When the PM changes a node, everything built on it is marked **stale**. Then:
- **Scores** recompute automatically.
- **The agent** gets "these nodes are stale because of X" as its next task and decides what to redo, drop or keep.
- **PM decisions** are never changed automatically; they are flagged "re-review: evidence changed".

**In one line:** the agent builds the reasoning, the PM steers and decides, and every step is a traceable node.
