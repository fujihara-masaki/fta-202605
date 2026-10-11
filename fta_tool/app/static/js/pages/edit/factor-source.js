// A factor's draft as a save source of the shared coordinator (plan 5.2,
// 5.9.3). PR-4 made the contract (E-E20); since PR-5 the inspector's editor
// (edit/factor-editor.js) is its user.
//
//   createFactorSource({ app, nodeId, label, read, saved, onDiscard,
//                        onSaved, blockedReason })
//     nodeId     the factor whose editing started: fixed here (the target the
//                coordinator keeps is frozen when the source is registered),
//                so a save goes there whatever is selected later
//     read()     the current draft: { title, description, memo,
//                direct_cause_status, direct_cause_comment, evidence,
//                prevention_idea } (missing keys count as unchanged)
//     saved      the saved values when editing started (from GET /nodes/{id})
//     onDiscard  drop the draft (破棄して移動)
//     onSaved(fields)  PR-5: called by commit() right after a success, with
//                the values that were sent — the one success handling of the
//                save button and of 保存して移動 (synchronous: it must not
//                wait for anything that waits for this save)
//     blockedReason()  PR-5: a reason not to send now (e.g. the factor is
//                no longer on the page): nothing is sent (`notSent`)
//   -> a source for registerSource(); after a success its saved values are
//      what was sent, so input typed meanwhile stays unsaved.
// One POST /nodes/{id}/update per save, never with the judgement
// (user_judgement is saved on its own, plan 5.2). 404: the factor is gone
// (`gone: 'node'`); the analysis being gone (app.gone): nothing is sent.
// PR-5: nothing is sent while a generation is prepared, runs or is finished
// (J-01; the coordinator refuses 保存して移動 then anyway), and the request is
// registered with app.writes when the page has it (app.beginWrite), so a
// partial update fetched before the save is never applied (plan 3.4-5).

import { requestJson } from '../../common/http.js';
import { normalizeText } from '../../common/text.js';
import { GENERATING_REASON, getGenerationPhase, SOURCE_ORDER } from '../../common/unsaved.js';

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

export function createFactorSource({
  app, nodeId, label, read, saved = {}, onDiscard = null, onSaved = null, blockedReason = null,
}) {
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
      if (getGenerationPhase() !== 'idle') return { ok: false, notSent: true, reason: GENERATING_REASON };
      const blocked = blockedReason ? blockedReason() : null;
      if (blocked) return { ok: false, notSent: true, reason: blocked };
      const fields = draft();
      const endWrite = typeof app.beginWrite === 'function' ? app.beginWrite() : null;
      let result;
      try {
        result = await requestJson(`/nodes/${to.nodeId}/update`, { method: 'POST', body: fields });
      } finally {
        if (endWrite) endWrite();
      }
      if (result.ok) return { ok: true, status: result.status, value: fields };
      return { ok: false, status: result.status, reason: result.reason, gone: result.status === 404 ? 'node' : undefined };
    },
    commit(outcome) {
      baseline = { ...baseline, ...outcome.value };
      if (onSaved) onSaved({ ...outcome.value });
    },
    savedValues: () => ({ ...baseline }),
    discard() {
      if (onDiscard) onDiscard();
    },
  };
}
