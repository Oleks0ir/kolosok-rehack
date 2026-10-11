// The chain grows left to right the way it is stored: each node sits one column to the right of
// the deepest node it is built on, so a PM question in the middle of a chain stays in the chain.
// Decisions are not drawn as nodes: the GUI shows them as a verdict on their target instead.
// STAGE is the usual order of the types (which types are drawn; connect direction in app.js).
export const STAGE = {
  Source: 0, Evidence: 1, Claim: 2, Assumption: 2, Requirement: 3, Score: 4, Question: 5, Note: 5,
};
export const CARD_W = 220; // node card size (app.js)
export const CARD_H = 86;
export const DX = 310; // leaves ~90 px between columns for the flow's S-bends
export const DY = 110;

/** {id: {x, y}}: column = depth in the chain; each node sits at the mean height of its inputs,
 *  pushed down to avoid overlaps. */
export function layout(nodes, edges) {
  const drawn = new Map(nodes.filter((n) => n.type in STAGE).map((n) => [n.id, n]));
  const inputsOf = {};
  for (const e of edges) {
    if (drawn.has(e.from_id) && drawn.has(e.to_id)) (inputsOf[e.from_id] ??= []).push(e.to_id);
  }

  const depth = {};
  const depthOf = (id) => {
    if (depth[id] === undefined) {
      depth[id] = 0; // the graph is append-only, so it has no loops; this only guards bad data
      depth[id] = Math.max(-1, ...(inputsOf[id] || []).map(depthOf)) + 1;
    }
    return depth[id];
  };

  const columns = {};
  for (const id of drawn.keys()) (columns[depthOf(id)] ??= []).push(id);

  const pos = {};
  for (const col of Object.keys(columns).map(Number).sort((a, b) => a - b)) {
    const wanted = columns[col].map((id, i) => {
      const ys = (inputsOf[id] || []).map((inp) => pos[inp].y);
      return { id, y: ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : i * DY };
    }).sort((a, b) => a.y - b.y);
    let floor = -Infinity;
    for (const w of wanted) {
      floor = Math.max(w.y, floor + DY);
      pos[w.id] = { x: col * DX, y: floor };
    }
  }
  return pos;
}
