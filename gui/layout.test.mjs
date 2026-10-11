// Run: node gui/layout.test.mjs
import assert from "node:assert/strict";
import { layout, DX, DY } from "./layout.js";

const nodes = [
  { id: "SRC-001", type: "Source" },
  { id: "EVD-001", type: "Evidence" },
  { id: "EVD-002", type: "Evidence" },
  { id: "CLM-001", type: "Claim" },
  { id: "DEC-001", type: "Decision" },
];
const edges = [
  { from_id: "EVD-001", to_id: "SRC-001" },
  { from_id: "EVD-002", to_id: "SRC-001" },
  { from_id: "CLM-001", to_id: "EVD-002" },
  { from_id: "DEC-001", to_id: "CLM-001" },
];
const pos = layout(nodes, edges);

assert.equal(pos["DEC-001"], undefined, "decisions are not drawn");
assert.equal(pos["CLM-001"].x, 2 * DX, "claims sit in column 2");
assert.equal(pos["EVD-002"].y - pos["EVD-001"].y, DY, "siblings don't overlap");
assert.equal(pos["CLM-001"].y, pos["EVD-002"].y, "a node lines up with its input");
console.log("layout ok");
