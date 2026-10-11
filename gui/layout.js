// One column per stage of the chain, left to right. Decisions are not drawn as nodes:
// the GUI shows them as a verdict on their target instead.
export const STAGE = {
  Source: 0, Evidence: 1, Claim: 2, Assumption: 2, Requirement: 3, Score: 4, Question: 5, Note: 5,
};
export const DX = 260;
export const DY = 90;

/** {id: {x, y}}: each node sits at the mean height of its inputs, pushed down to avoid overlaps. */
export function layout(nodes, edges) {
  const inputsOf = {};
  for (const e of edges) (inputsOf[e.from_id] ??= []).push(e.to_id);

  const columns = {};
  for (const n of nodes) if (n.type in STAGE) (columns[STAGE[n.type]] ??= []).push(n);

  const pos = {};
  for (const stage of Object.keys(columns).map(Number).sort((a, b) => a - b)) {
    const wanted = columns[stage].map((n, i) => {
      const ys = (inputsOf[n.id] || []).filter((id) => pos[id]).map((id) => pos[id].y);
      return { id: n.id, y: ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : i * DY };
    }).sort((a, b) => a.y - b.y);
    let floor = -Infinity;
    for (const w of wanted) {
      floor = Math.max(w.y, floor + DY);
      pos[w.id] = { x: stage * DX, y: floor };
    }
  }
  return pos;
}
