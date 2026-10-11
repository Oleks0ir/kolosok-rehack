// Run: node gui/layout.test.mjs
import assert from "node:assert/strict";
import { layout, DX, DY } from "./layout.js";

const nodes = [
  { id: "SRC-001", type: "Source" },
  { id: "EVD-001", type: "Evidence" },
  { id: "EVD-002", type: "Evidence" },
  { id: "CLM-001", type: "Claim" },
  { id: "DEC-001", type: "Decision" },
  { id: "QST-001", type: "Question" },
  { id: "EVD-003", type: "Evidence" },
];
const edges = [
  { from_id: "EVD-001", to_id: "SRC-001" },
  { from_id: "EVD-002", to_id: "SRC-001" },
  { from_id: "CLM-001", to_id: "EVD-002" },
  { from_id: "DEC-001", to_id: "CLM-001" },
  { from_id: "QST-001", to_id: "CLM-001" }, // PM asks to dig deeper on the claim
  { from_id: "EVD-003", to_id: "QST-001" }, // the agent's answer
  { from_id: "EVD-003", to_id: "SRC-001" },
];
const pos = layout(nodes, edges);

assert.equal(pos["DEC-001"], undefined, "decisions are not drawn");
assert.equal(pos["CLM-001"].x, 2 * DX, "claims sit in column 2");
assert.equal(pos["EVD-002"].y - pos["EVD-001"].y, DY, "siblings don't overlap");
assert.equal(pos["CLM-001"].y, pos["EVD-002"].y, "a node lines up with its input");
assert.equal(pos["QST-001"].x, 3 * DX, "a question sits right after what it asks about");
assert.equal(pos["EVD-003"].x, 4 * DX, "the answer grows the chain further right, not back left");
console.log("layout ok");
