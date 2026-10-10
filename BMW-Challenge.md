# BMW Group Challenge — AI for Product Decision Making

## The challenge

What should the next generation of a BMW vehicle offer its customers? Build an AI-powered application that helps product managers (PMs) derive, justify and prioritize **customer requirements** for a successor vehicle. Ground proposals in customer feedback, BMW product and sales data, and web research, while keeping the **PM firmly in control of every decision**.

**Why it matters**: Defining a new generation means understanding what customers value today and what they will value when the successor reaches the market. PM work today is manual, slow and hard to trace. AI should make evidence, assumptions and uncertainties transparent and under human control.

## Your mission

Build an AI-powered application that ingests heterogeneous data, derives customer requirements for a vehicle, prioritizes them, and puts a product manager in the loop at the decisions that matter.

The app should be able to:

1. **Ingest** the provided data and enrich it with structured knowledge from the web.
2. **Extract signals** such as recurring complaints, unmet needs, competitor advantages and market trends, each linked to its sources.
3. **Derive requirements** from those findings: clear, actionable, customer-facing and realistic.
4. **Prioritize** them with a logic you define and can explain.
5. **Involve the PM** to approve, reject, edit or challenge requirements and the rationale and evidence behind them.
6. **Record everything in an audit trail** (a complete, chronological record of all actions, changes and access events).

Extra context:
- Use the BMW **1 Series, 5 Series, 7 Series**, or a combination.
- Focus on **Europe, China, the United States**, or any subset that best shows your approach.
- Think **3–5 years ahead**: which customer needs should shape the next generation?
- Make clear where conclusions rest on **evidence** and where on **forward-looking assumptions**.
- Judges care about how diverse information becomes actionable PM insight with transparent reasoning, not about a specific workflow or architecture.

## Scope

**In scope** — customer requirements on the product:
features, equipment, comfort, space, usability, infotainment and digital services, design and quality perception, driving experience, range and charging as experienced by the customer, variant and package offering, etc.

**Out of scope:**
- Regulatory and homologation requirements (safety, emissions, type approval)
- Technical and engineering requirements (component specs, architecture, supplier topics)
- Pricing, business case and cost calculation (cost or effort may be used as a rough prioritization factor)

## Data and sources

Provided data, per vehicle:

| Dataset | What it contains | What it is good for |
|---|---|---|
| Customer verbatims | Free-text customer feedback on the current vehicle | Pain points, unmet needs, what customers love and must not lose |
| Equipment list | Standard and optional equipment by trim and market | What the car offers today, gaps against competitors |
| Sales volumes | Units by powertrain and region | Where the car sells, which powertrains matter, where it underperforms |
| Customer study | Customer ratings in various categories | How customers perceive, like/dislike, rate different components of a car |

External enrichment is allowed _(PDF)_: competitor information, reviews, market and technology trends.

## Make it yours

- Demonstrate the app for **at least one derivative in one market**, but do not build it as a one-off: it should adapt to other BMW vehicles and markets. The remaining datasets and scenarios are available for optional testing.
- The challenge is broad. Focus where your team can contribute most (e.g. deep web research turned into usable evidence, or integrating and interpreting the BMW data). You do not need every capability at the same depth, but show how your focus connects the path **from evidence to a PM decision**.
- _(PDF)_ Valued: trustworthy sources, transparent reasoning, thoughtful prioritization, clear handling of uncertainty and conflicting evidence, and a view on how the concept scales across vehicle lines and markets.
- _(PDF)_ Focus on customer value, not engineering specs, regulation or detailed business cases.

## Expected deliverables

1. **Concept and demonstrable prototype** of an AI-powered product-requirements application that processes heterogeneous inputs, derives requirements, supports prioritization and integrates human review.
2. **Structured sample list of derived requirements.** Each requirement must include:
   - unique identifier
   - clear, actionable description
   - linked findings and sources
   - priority or score
   - applied prioritization rationale
   - evidence level
   - key future-facing assumptions and uncertainties
   - current decision status
3. **End-to-end workflow** showing how inputs become proposed and prioritized requirements, which steps the AI does autonomously, and where human review is **mandatory**.
4. **Demonstrable audit trail** making each requirement traceable from findings and sources, through consolidation, scoring, prioritization and the human decision. It must record changes to requirement content, scores, priorities, evidence and status, including **who or what** initiated each change, **when**, and the **documented rationale**.

**Important:** teams are free to choose technical approach, architecture, prioritization logic and UX. The deliverables describe capabilities and outcomes to demonstrate, not a prescribed design. They may be one integrated solution or a combination of connected concepts, prototypes, models and visualizations.

## What to demonstrate (short form)

- A working prototype showing how AI supports identifying, formulating and prioritizing requirements from the provided data and external sources.
- A representative set of requirements with clear evidence and reasoning, showing which factors drive prioritization.
- A transparent decision-support experience where PMs can review, challenge, modify, approve or reject AI proposals, with evidence, assumptions, uncertainties and decisions visible and traceable throughout.
