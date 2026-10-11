// Judgement Yes / No / 未 (UI-12), from the work list or the inspector.
//
// - Saved at once through the existing API (POST /nodes/{id}/update with
//   user_judgement only).
// - One request per factor at a time (plan 5.2): a click while a request is
//   in flight only records the wish, which is sent next, so the last click
//   wins and an old answer cannot overwrite a newer one.
// - The page changes only after the server confirmed: then every
//   representation, the step counts and the generation targets follow
//   (C-04). On a failure nothing changes and the reason is shown (J-24).
// - Every request is registered with app.writes, so a partial update never
//   applies a page fetched before a judgement was saved (plan 3.4-5, P-3).

import { requestJson } from '../../common/http.js';
import { notify } from '../../common/notify.js';
import { getNode } from './model.js';
import { applyCounts, applyJudgement } from './view.js';

const VALUES = new Set(['yes', 'no', 'unknown']);
const queues = new Map();

function markPending(nodeId, value) {
  document.querySelectorAll(`[data-judgement-toggle][data-node-id="${nodeId}"]`).forEach((group) => {
    group.setAttribute('aria-busy', value === null ? 'false' : 'true');
    group.querySelectorAll('[data-value]').forEach((button) => {
      if (value !== null && button.dataset.value === value) button.dataset.pending = 'true';
      else delete button.dataset.pending;
    });
  });
}

async function drain(app, nodeId, queue) {
  queue.busy = true;
  try {
    while (queue.wanted !== null) {
      const value = queue.wanted;
      queue.wanted = null;
      const node = getNode(app.model, nodeId);
      if (!node || app.gone) break;
      if (node.judgement === value) continue;
      markPending(nodeId, value);
      const write = app.writes.begin();
      let result;
      try {
        result = await requestJson(`/nodes/${nodeId}/update`, { method: 'POST', body: { user_judgement: value } });
      } finally {
        app.writes.end(write, result && result.ok ? { nodeId, value } : null);
      }
      if (result.ok) {
        const current = getNode(app.model, nodeId);
        if (current) current.judgement = value;
        applyJudgement(nodeId, value);
        applyCounts(app);
        app.afterJudgement(nodeId);
        notify('評価を更新しました', { type: 'success' });
      } else {
        notify(`評価を保存できませんでした：${result.reason}`, { type: 'error' });
      }
    }
  } finally {
    queue.busy = false;
    markPending(nodeId, null);
  }
}

export function requestJudgement(app, nodeId, value) {
  if (!VALUES.has(value) || app.gone) return;
  const node = getNode(app.model, nodeId);
  if (!node) return;
  let queue = queues.get(node.id);
  if (!queue) {
    queue = { busy: false, wanted: null };
    queues.set(node.id, queue);
  }
  queue.wanted = value;
  if (queue.busy) {
    markPending(node.id, value);
    return;
  }
  drain(app, node.id, queue);
}
