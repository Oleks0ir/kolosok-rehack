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
