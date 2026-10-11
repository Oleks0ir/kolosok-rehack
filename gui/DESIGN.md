# Design language — "M stripes as flow"

Approved by the team on the start screen (`start.js`, `start.css`, open `/ui/?start`). Every new
GUI page (graph view, mid-process view) follows these rules. Two references shaped it: the BMW M
stripes and editorial Sankey diagrams (black ribbons and labels on warm paper). Motion and craft
follow Apple's fluid-interface principles (WWDC "Designing Fluid Interfaces").

## The idea in one line

**The three M stripes are the flow of reasoning.** They run together as a bundle and fan out where
there's a choice. They pass *through* what was chosen and lead on to the next step. A line
always means "this came from that", the same meaning as an edge in the decision graph.

## Color

| Token | Value | Use |
|---|---|---|
| `--paper` | `#f4f3ef` | Page background (warm, not white) |
| `--ink` | `#111111` | Text, chosen cards, primary button, hairlines that matter |
| `--muted` | `#77746c` | Secondary text, unchosen options |
| `--hair` | `#d9d6ce` | Quiet dividers |
| `--ghost` | `#c9c5bb` | Thin lines to options that weren't taken |
| `--m-light` | `#1ea7e8` | Stripe 1; focus ring |
| `--m-dark` | `#1d2a8c` | Stripe 2 |
| `--m-red` | `#e4161f` | Stripe 3; errors |

- Color lives in the stripes. Everything else is ink on paper. Don't tint cards, panels or buttons.
- A chosen or active thing turns **solid ink with white text**. A not-chosen thing turns **muted**
  and keeps a ghost line to it. It stays visible and clickable.

## Type

- Face: **BMW Type Next** (licensed; used when installed or put in `gui/fonts/`, which is
  gitignored). Fallback: `system-ui` (SF on a Mac). Stack: `--type` in `start.css`.
- Large display text is light weight (300) with tight leading (≈1.05) and negative tracking
  (−0.025em). Example: the page title at 44px.
- Labels and option names are **bold UPPERCASE** with positive tracking (+0.04 to +0.08em), at
  11–15px. Section eyebrows are 11px, bold, uppercase, `--muted`.
- Body text is 13–14px with leading ≈1.5, in `--muted` for explanations.
- Show hierarchy through weight, size and case together, never size alone.

## Shapes and layout

- **Square corners** everywhere (radius 0). No shadows, no gradients, no rounded pills.
- **Hairline rules**, not boxes. A 2px ink rule on top of an option is its "landing pad" for the
  stripes. A 1px ink rule closes a title block, and `--hair` separates the quieter parts.
- **Editorial grid:** a left column (≈280px) holds titles and numbered step labels (ink circle
  with the number). The right column holds the flow. Generous vertical space: 96px of bend room
  (`FORK`) above every row.
- **Cards sit above the stripes** (`z-index`, `--paper` background), so the stripes appear to
  run *through* them.
- At phone width (≤800px) there is one column. The title covers the stripes' start, and labels
  sit left of the bundle with the bend room below them. No horizontal scroll.

## The stripes (how to draw them)

- There are 3 stripes, each 10px wide, touching (no gaps), with butt caps, in the order light
  blue, dark blue, red.
- Paths run vertically: straight down, then a cubic S-bend in the last `FORK` px before a
  target.
- Apply the offsets **along the curve's normal**, not sideways, so a bundle keeps its full
  width through bends (`curve()` in `start.js`).
- Assign stripes to targets **in order** (`floor(i * targets / 3)`), so they never cross.
- One target: all three pass through it, side by side. Several targets: they split and later
  rejoin.
- Options that aren't taken get a 1.5px `--ghost` line from the bundle.

## Motion

- Use **springs, not timed tweens**, for anything that moves because of the user: critically
  damped (damping 1.0), response ≈0.45s. X, Y and offset each spring independently.
- **Always start from the current on-screen value.** A new click mid-animation re-targets the
  motion, so it never jumps and never locks input.
- New parts **grow out of where the flow is**. A new stripe segment starts at the previous
  card's exit.
- Press feedback is instant on pointer-down: `:active { transform: scale(.97) }` over 100ms.
- Reveals: opacity plus a 14px rise, about 500ms, ease `cubic-bezier(.2,.8,.2,1)`, starting
  ~140ms after the stripes so the flow leads.
- Leaving a screen means materializing out: opacity, a slight scale-up (1.015) and blur, 450ms.
- `prefers-reduced-motion`: springs snap and transitions become short fades. Nothing else
  changes.

## Interaction

- One choice per row, and the next row opens only when it's needed. Scroll it into view
  (`block: "nearest"`).
- Every earlier choice stays changeable (agency and forgiveness). There are no confirmation
  dialogs.
- Validate inline. Put the message in `--m-red` under the action, and focus the field that
  needs fixing.
- Use direct, specific labels ("Start agent", "Your CSV", "What should the agent work out?").
- Keyboard: real `<button>`s with `aria-pressed`, a visible `--m-light` focus ring, and `inert`
  on everything hidden or behind an overlay.

## Don't

- Don't use the BMW roundel or the M logo. The brand is evoked by the stripe colors only.
- Don't add color outside the stripes, or decoration that doesn't carry meaning.
- Don't use rounded corners, drop shadows or dashboard-style chrome.
- Don't use CSS keyframe animation for things the user drives (they can't be interrupted).
