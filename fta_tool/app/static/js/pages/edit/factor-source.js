// A factor's draft as a save source of the shared coordinator (plan 5.2,
// 5.9.3). PR-4 completes the contract; the inspector's editing that will use
// it is PR-5 (R-01). In PR-4 it is exercised by E-E20 only.
//
//   createFactorSource({ app, nodeId, label, read, saved, onDiscard })
//     nodeId     the factor whose editing started: fixed here (the target the
//                coordinator keeps is frozen when the source is registered),
//                so a save goes there whatever is selected later
//     read()     the current draft: { title, description, memo,
//                direct_cause_status, direct_cause_comment, evidence,
//                prevention_idea } (missing keys count as unchanged)
//     saved      the saved values when editing started (from GET /nodes/{id})
//     onDiscard  drop the draft (破棄して移動)
//   -> a source for registerSource(); after a success its saved values are
//      what was sent, so input typed meanwhile stays unsaved.
// One POST /nodes/{id}/update per save, never with the judgement
// (user_judgement is saved on its own, plan 5.2). 404: the factor is gone
// (`gone: 'node'`); the analysis being gone (app.gone): nothing is sent.

import { requestJson } from '../../common/http.js';
import { normalizeText } from '../../common/text.js';
import { SOURCE_ORDER } from '../../common/unsaved.js';

export const FACTOR_FIELDS = [
  'title', 'description', 'memo', 'direct_cause_status', 'direct_cause_comment', 'evidence', 'prevention_idea',
];

function normalizeFields(values, base = {}) {
  const fields = {};
  for (const key of FACTOR_FIELDS) {
    const value = values && Object.prototype.hasOwnProperty.call(values, key) ? values[key] : base[key];
    if (value === undefined) continue;
    fields[key] = key === 'direct_cause_status' ? String(value || 'unknown') : normalizeText(value);
  }
  return fields;
}

function sameFields(a, b) {
  return FACTOR_FIELDS.every((key) => (a[key] ?? '') === (b[key] ?? ''));
}

export function createFactorSource({ app, nodeId, label, read, saved = {}, onDiscard = null }) {
  let baseline = normalizeFields(saved);
  const draft = () => normalizeFields(read(), baseline);
  return {
    id: `edit-factor-${Number(nodeId)}`,
    order: SOURCE_ORDER.factor,
    label,
    target: { analysisId: app.analysisId, nodeId: Number(nodeId) },
    isDirty: () => !sameFields(draft(), baseline),
    draftKey: () => JSON.stringify(draft()),
    validate: () => (draft().title ? null : '要因タイトルは必須です'),
    async save(to) {
      if (app.gone) return { ok: false, notSent: true, reason: '分析が見つからないため送信していません（削除された可能性があります）' };
      const fields = draft();
      const result = await requestJson(`/nodes/${to.nodeId}/update`, { method: 'POST', body: fields });
      if (result.ok) return { ok: true, status: result.status, value: fields };
      return { ok: false, status: result.status, reason: result.reason, gone: result.status === 404 ? 'node' : undefined };
    },
    commit(outcome) {
      baseline = { ...baseline, ...outcome.value };
    },
    discard() {
      if (onDiscard) onDiscard();
    },
  };
}
