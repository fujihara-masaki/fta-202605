// Filter (UI-15): text in the name or description, AND the judgement /
// 要確認 choice — the same rules as before. Rows of the work list and the
// table that do not match are hidden; the structure navigation and the tree
// only highlight the matches and dim the rest, never hiding a parent (J-08).
// The generation targets are computed from the data, so the filter never
// changes them (J-07). The conditions are kept per analysis in
// sessionStorage (plan 5.5). While an IME conversion is under way the list is
// not filtered on every keystroke; it is when the conversion ends.

const HIDE_SELECTOR = '[data-role="work-item"][data-node-id], [data-role="table-item"][data-node-id]';
const MARK_SELECTOR = '[data-role="nav-item"][data-node-id], [data-role="tree-item"][data-node-id]';

function controls() {
  return {
    text: document.getElementById('edit-filter-text'),
    judge: document.getElementById('edit-filter-judgement'),
    count: document.getElementById('edit-filter-count'),
  };
}

function matches(node, text, judge) {
  if (text) {
    const haystack = `${node.title || ''} ${node.description || ''}`.toLowerCase();
    if (!haystack.includes(text)) return false;
  }
  if (!judge) return true;
  if (judge === 'warning') return Boolean(node.warning);
  return node.judgement === judge;
}

export function currentFilter() {
  const { text, judge } = controls();
  return { text: text ? text.value : '', judge: judge ? judge.value : '' };
}

export function applyFilter(app) {
  const { count } = controls();
  const filter = currentFilter();
  const text = filter.text.trim().toLowerCase();
  const judge = filter.judge;
  const active = Boolean(text || judge);
  const hits = new Set();
  for (const node of app.model.nodes) {
    if (!active || matches(node, text, judge)) hits.add(node.id);
  }
  document.querySelectorAll(HIDE_SELECTOR).forEach((element) => {
    element.hidden = active && !hits.has(Number(element.dataset.nodeId));
  });
  document.querySelectorAll(MARK_SELECTOR).forEach((element) => {
    const hit = hits.has(Number(element.dataset.nodeId));
    element.classList.toggle('is-filter-match', active && hit);
    element.classList.toggle('is-filter-dim', active && !hit);
  });
  if (count) {
    const total = app.model.nodes.length;
    count.textContent = active ? `一致 ${hits.size}件（全${total}件）` : `全${total}件`;
  }
}

export function initFilter(app, saved) {
  const { text, judge } = controls();
  if (!text || !judge) return;
  if (saved && typeof saved === 'object') {
    if (typeof saved.text === 'string') text.value = saved.text;
    if (typeof saved.judge === 'string' && [...judge.options].some((option) => option.value === saved.judge)) {
      judge.value = saved.judge;
    }
  }
  const changed = () => {
    applyFilter(app);
    app.saveSession();
  };
  text.addEventListener('input', (event) => {
    if (event.isComposing) return;
    changed();
  });
  text.addEventListener('compositionend', changed);
  judge.addEventListener('change', changed);
  applyFilter(app);
}

export function clearFilter(app) {
  const { text, judge } = controls();
  if (text) text.value = '';
  if (judge) judge.value = '';
  applyFilter(app);
  app.saveSession();
}
