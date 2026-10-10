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
| **Signal** | A finding: complaint, unmet need, competitor gap, trend. Stores the exact quotes/rows it is based on | LLM agent or analysis |
| **Requirement** | A customer requirement proposal | LLM agent or PM |
| **Score** | Priority score with its formula breakdown | scoring formula |
| **Decision** | PM approves / rejects / postpones / edits, with reason | PM |
| **Note** | Free input: meeting outcome, expert opinion, PM comment | PM / team |

### Fields

```
Node
  id           e.g. "SIG-012"
  type         Source | Signal | Requirement | Score | Decision | Note
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
3. **Every node except a Source must have inputs**, so nothing is untraceable.
4. **Readable over exhaustive:** one Source node per file, not per row. A Signal keeps its supporting quotes inside its content, so the graph stays small enough for a person to keep an overview.

### Propagation

Edges mean "B was built from A". When a node gets a new version, everything downstream is marked **stale**.
