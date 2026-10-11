// Dependency-free logic smoke test; this is NOT a browser/layout test.
// Usage: node test_report_ui.js F70_topics_summary.readable/report.html
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync(process.argv[2], 'utf8');
const payload = page.match(/<script type="application\/json" id="report-data">([\s\S]*?)<\/script>/)[1];
const code = page.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const source = JSON.parse(payload);
const ids = [...page.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
const elements = new Map(ids.map(id => [id, {
  textContent: id === 'report-data' ? payload : '', innerHTML: '',
  value: id === 'sort' ? 'count' : id === 'min-reviews' ? '0' : '', checked: false,
  listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; },
  querySelectorAll() { return []; }, scrollIntoView() {}, focus() {},
}]));
const context = vm.createContext({
  document: {getElementById: id => {
    assert(elements.has(id), `Missing HTML element ${id}`);
    return elements.get(id);
  }, querySelector: () => ({hidden: false}), title: ''},
  window: {matchMedia: () => ({matches: false})},
});
vm.runInContext(code, context);
const get = id => elements.get(id);
const input = (id, value) => {get(id).value = value; get(id).listeners.input();};
const reset = () => get('reset').listeners.click();
const visibleCount = () => (get('topic-list').innerHTML.match(/data-id=/g) || []).length;
assert.equal(visibleCount(), source.topics.length);
if (source.topics.length) {
  const first = source.topics[0];
  input('search', first.topic_id);
  assert.equal(visibleCount(), 1);
  assert(get('detail').innerHTML.includes(first.topic_id));
  assert(!get('detail').innerHTML.includes('NaN'));
  reset();
  input('min-reviews', '10');
  assert.equal(visibleCount(), source.topics.filter(t => t.review_count >= 10).length);
  reset();
  get('signals-only').checked = true;
  get('signals-only').listeners.change();
  assert.equal(visibleCount(), source.topics.filter(t => t.signals.length).length);
  reset();
  get('sort').value = 'bad_count';
  get('sort').listeners.change();
  const expected = [...source.topics].sort((a,b) => b.negative_or_mixed_count-a.negative_or_mixed_count || a.topic_id.localeCompare(b.topic_id))[0];
  assert.equal(get('topic-list').innerHTML.match(/data-id="([^"]+)"/)[1], expected.topic_id);
}
input('search', '__definitely_absent__');
assert.equal(visibleCount(), 0);
assert(get('detail').innerHTML.includes('No topics'));
reset();
assert.equal(visibleCount(), source.topics.length);
assert(!page.includes('href="overview.md"'));
assert(!page.includes('href="README.md"'));
const template = fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]), '..', 'report_template.html'), 'utf8');
const rawCode = template.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const templateNotice = {hidden: true};
const templateMain = {hidden: false};
vm.runInNewContext(rawCode, {document: {
  getElementById: id => id === 'report-data' ? {textContent: '__REPORT_DATA__'} : templateNotice,
  querySelector: () => templateMain,
}});
assert.equal(templateNotice.hidden, false);
assert.equal(templateMain.hidden, true);
console.log(`UI logic passed: ${source.topics.length} topics; search, filters, sorting, empty state, reset, and template guidance.`);
