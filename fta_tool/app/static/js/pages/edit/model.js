// Factor summary embedded by the server (<script type="application/json"
// id="analysis-data">, plan 3.4-2; built by app/detail_view.py) and what the
// screen derives from it: step counts, generation targets, ancestry for the
// breadcrumb. Targets and counts come from this data, never from what is
// visible on the page (J-07). Walks record what they visited and stop after
// three levels (plan 5.9.5), so cyclic parent links cannot hang the page.

export const MAX_DEPTH = 3;
export const LEVEL_NAMES = { 1: '一次', 2: '二次', 3: '三次' };
export const JUDGEMENT_LABELS = { yes: 'Yes', no: 'No', unknown: '未評価' };
export const DIRECT_CAUSE_LABELS = {
  likely: '可能性高',
  unlikely: '可能性低',
  direct: '直接要因',
  not_direct: '直接要因でない',
};

export function levelName(level) {
  return LEVEL_NAMES[level] || `階層${level}`;
}

export function judgementLabel(value) {
  return JUDGEMENT_LABELS[value] || String(value);
}

export function createModel(raw) {
  if (!raw || typeof raw !== 'object' || !Array.isArray(raw.nodes)) return null;
  const nodes = raw.nodes;
  const byId = new Map();
  for (const node of nodes) byId.set(node.id, node);
  const childrenOf = new Map();
  for (const node of nodes) {
    if (node.parentId === null || node.parentId === node.id || !byId.has(node.parentId)) continue;
    if (!childrenOf.has(node.parentId)) childrenOf.set(node.parentId, []);
    childrenOf.get(node.parentId).push(node);
  }
  return {
    analysisId: raw.analysisId,
    factorCounts: raw.factorCounts || {},
    lookupsOk: raw.lookupsOk !== false,
    nodes,
    byId,
    childrenOf,
  };
}

// The summary of a page (the current document or a fetched one).
export function readModel(doc = document) {
  const script = doc.getElementById('analysis-data');
  if (!script) return null;
  try {
    return createModel(JSON.parse(script.textContent || ''));
  } catch {
    return null;
  }
}

export function getNode(model, id) {
  if (!model || id === null || id === undefined) return null;
  const text = String(id);
  if (!/^\d+$/.test(text)) return null;
  return model.byId.get(Number(text)) || null;
}

// Consistent link (the factor sits in the tree at its place, possibly below
// an inconsistent ancestor).
export function isDisplayLink(node) {
  return node.kind === 'ok' || node.kind === 'upper';
}

export function isConsistentRoot(node) {
  return node.kind === 'ok' && node.level === 1 && node.parentId === null;
}

export function firstRoot(model) {
  return model.nodes.find(isConsistentRoot) || null;
}

// Ancestors for the breadcrumb, nearest last; consistent links only, so a
// factor of the inconsistent group starts at its group entry.
export function ancestry(model, node) {
  const chain = [];
  const seen = new Set([node.id]);
  let current = node;
  while (chain.length < MAX_DEPTH && isDisplayLink(current) && current.parentId !== null) {
    const parent = model.byId.get(current.parentId);
    if (!parent || seen.has(parent.id)) break;
    seen.add(parent.id);
    chain.unshift(parent);
    current = parent;
  }
  return { chain, underTopEvent: isConsistentRoot(chain[0] || node) };
}

// Is `node` the factor `ancestorId` or below it (parent links in the data,
// each visited once)?
export function isAtOrBelow(model, node, ancestorId) {
  const seen = new Set();
  let current = node;
  while (current && !seen.has(current.id)) {
    if (current.id === Number(ancestorId)) return true;
    seen.add(current.id);
    current = current.parentId === null ? null : getNode(model, current.parentId);
  }
  return false;
}

export function childrenOf(model, node) {
  return (model.childrenOf.get(node.id) || []).filter((child) => child.id !== node.id);
}

export function stepCounts(model, level) {
  let total = 0;
  let unevaluated = 0;
  for (const node of model.nodes) {
    if (node.kind !== 'ok' || node.level !== level) continue;
    total += 1;
    if (node.judgement !== 'yes' && node.judgement !== 'no') unevaluated += 1;
  }
  return { total, unevaluated };
}

// Parents of the normal generation of `level` (2 or 3): every Yes factor of
// the level above, shown or hidden by the filter (J-07), except factors with
// an inconsistent parent link or ancestor (J-25; the user's decision 判断3),
// which are counted separately.
export function generationTargets(model, level) {
  const targets = [];
  const excluded = [];
  for (const node of model.nodes) {
    if (node.level !== level - 1 || node.judgement !== 'yes') continue;
    (node.canParent ? targets : excluded).push(node);
  }
  return { targets, excluded };
}

// The work step that shows a factor: ② for 一次, ③ for 二次, ④ for 三次
// (a factor of an unexpected level: the nearest of ②〜④).
export function stepForNode(node) {
  if (!node) return 1;
  return Math.min(Math.max(Number(node.level) + 1, 2), 4);
}

// Counts of ⑤ (PR-4), as app/detail_view.py summary_counts: per level the
// factors in place, the factors with an inconsistent parent link or ancestor
// in a row of their own, and every factor. Always from the data, never from
// what the page shows.
export const SUMMARY_COLUMNS = ['total', 'yes', 'no', 'unknown', 'warning', 'direct'];

function countRow(items) {
  return {
    total: items.length,
    yes: items.filter((node) => node.judgement === 'yes').length,
    no: items.filter((node) => node.judgement === 'no').length,
    unknown: items.filter((node) => node.judgement !== 'yes' && node.judgement !== 'no').length,
    warning: items.filter((node) => node.warning).length,
    direct: items.filter((node) => node.directCause === 'direct').length,
  };
}

export function summaryCounts(model) {
  const rows = {};
  for (const level of [1, 2, 3]) {
    rows[String(level)] = countRow(model.nodes.filter((node) => node.kind === 'ok' && node.level === level));
  }
  rows.anomaly = countRow(model.nodes.filter((node) => node.kind !== 'ok'));
  rows.all = countRow(model.nodes);
  return rows;
}
