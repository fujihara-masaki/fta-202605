// The inspector's editor of one factor (PR-5: UI-13・UI-14, J-10, J-11,
// plan 5.1, 5.2). The seven fields — タイトル・説明・メモ・直接要因評価・
// 評価コメント・根拠・再発防止策 — are the only place where a factor's details
// and its title are edited (the old detail modal and the direct editing on
// the cards are gone).
//
// - Bound to the analysis and the factor when it is made (`analysisId`,
//   `nodeId`); never moved to another factor. The inspector makes a new
//   editor when another factor is chosen (after the switch is confirmed).
// - The fields are filled from GET /nodes/{id} (plan 3.4-4) and stay disabled
//   until that answer arrived: nothing typed over empty placeholders can be
//   saved, and a failed load registers nothing (再読み込み tries again). An
//   answer for an editor that is no longer the inspector's is dropped (A → B
//   → A: the first A's answer is never used).
// - Once loaded, the draft is a save source of the shared coordinator
//   (createFactorSource, js/common/unsaved.js): 保存 calls saveSource, as
//   保存して移動 does, so both share the in-flight tracking, the saved
//   values (what was sent: input typed meanwhile stays unsaved) and the one
//   success handling (onSaved). One POST /nodes/{id}/update, never the
//   judgement. 保存・取消 are off while the save is in flight.
// - 入力中（未保存）／保存済み compares after the normalisation used for saving
//   (common/text.js), so typing and restoring is not unsaved.
// - Saving is refused while a generation is prepared, runs or is finished
//   (J-01): the reason is shown, the input stays.
// - markGone(): the factor is no longer on the page (removed elsewhere) —
//   the input stays (read-only), its reason is shown, nothing is sent and the
//   target is never changed to another factor.
// Text is always inserted as text.

import { el, focusElement } from '../../common/dom.js';
import { requestJson } from '../../common/http.js';
import { isImeComposing } from '../../common/ime.js';
import { announce, notify } from '../../common/notify.js';
import {
  GENERATING_REASON,
  getGenerationPhase,
  isSourceSaving,
  lastFailure,
  refresh as refreshUnsaved,
  registerSource,
  saveSource,
  subscribe,
} from '../../common/unsaved.js';
import { createFactorSource } from './factor-source.js';

export const GONE_FACTOR_REASON = '編集中の要因が見つからないため、入力内容を保存できません（別のタブなどで削除された可能性があります）。必要な内容は控えてから、別の要因を選ぶか一覧へ戻ってください。';
export const GONE_ANALYSIS_REASON = '分析が見つからないため、入力内容を保存できません（削除された可能性があります）。';

const DIRECT_OPTIONS = [
  ['unknown', '未評価'],
  ['likely', '直接要因の可能性が高い'],
  ['unlikely', '直接要因の可能性が低い'],
  ['direct', '直接要因'],
  ['not_direct', '直接要因でない'],
];

const FIELDS = [
  { key: 'title', label: '要因タイトル', kind: 'input', required: true },
  { key: 'description', label: '説明', rows: 3 },
  { key: 'memo', label: 'メモ', rows: 2 },
  { key: 'direct_cause_status', label: '直接要因評価', kind: 'select' },
  { key: 'direct_cause_comment', label: '評価コメント', rows: 2 },
  { key: 'evidence', label: '根拠', rows: 2 },
  { key: 'prevention_idea', label: '再発防止策の候補', rows: 2 },
];

const STATUS_TEXT = {
  loading: '読み込み中…',
  failed: '読み込めませんでした',
  saving: '保存中…',
  dirty: '入力中（未保存）',
  saved: '保存済み',
  gone: '保存できません',
};

function control(spec, id) {
  const attrs = { id, class: 'ui-input', 'data-factor-field': spec.key, disabled: true };
  if (spec.kind === 'input') {
    return el('input', { ...attrs, type: 'text', autocomplete: 'off', 'aria-required': 'true' });
  }
  if (spec.kind === 'select') {
    return el('select', attrs, DIRECT_OPTIONS.map(([value, text]) => el('option', { value }, text)));
  }
  return el('textarea', { ...attrs, rows: spec.rows || 2 });
}

/**
 * @param {object} app the edit screen
 * @param {object} node the factor of the embedded data when editing starts
 * @param {object} hooks
 *   onSaved(nodeId, fields)  the success handling shared by 保存 and 保存して移動
 *   onLoaded(editor)         the details arrived (the inspector shows the warning)
 */
export function createFactorEditor(app, node, { onSaved, onLoaded } = {}) {
  const nodeId = Number(node.id);
  const analysisId = app.analysisId;
  const prefix = `factor-${nodeId}`;
  let phase = 'loading'; // loading | ready | failed
  let gone = null; // null | 'node' | 'analysis'
  let closed = false;
  let data = null;
  let source = null;
  let unregister = null;
  let unsubscribe = null;
  let loadError = '';

  const inputs = {};
  const rows = FIELDS.map((spec) => {
    const id = `${prefix}-${spec.key}`;
    const input = control(spec, id);
    inputs[spec.key] = input;
    return el('div', { class: 'ui-field edit-editor__field' },
      el('label', { class: 'ui-field__label', for: id }, spec.label,
        spec.required ? el('span', { class: 'edit-editor__required' }, '（必須）') : null),
      input);
  });

  const status = el('span', { class: 'ui-status', 'data-factor-status': true, 'data-state': 'loading' }, STATUS_TEXT.loading);
  const loadLine = el('p', { class: 'edit-inspector__status', role: 'status', 'data-detail-status': true },
    '保存されている内容を読み込んでいます…');
  const retry = el('button', { type: 'button', class: 'ui-btn ui-btn--sm', 'data-factor-reload': true, hidden: true },
    '再読み込み');
  const message = el('p', { class: 'edit-editor__message', role: 'alert', 'data-factor-message': true });
  const saveButton = el('button', {
    type: 'button', class: 'ui-btn ui-btn--sm ui-btn--primary', 'data-factor-save': true, disabled: true,
  }, '保存');
  const cancelButton = el('button', {
    type: 'button', class: 'ui-btn ui-btn--sm', 'data-factor-cancel': true, disabled: true,
  }, '取消');

  const element = el('div', {
    class: 'edit-editor', 'data-factor-editor': true, 'data-node-id': nodeId, 'data-phase': phase,
  },
  el('div', { class: 'edit-editor__head' },
    el('p', { class: 'edit-editor__lead' }, '「保存」で確定します。評価（Yes／No／未）はここでは保存しません。'),
    status),
  loadLine,
  retry,
  el('div', { class: 'edit-editor__fields' }, rows),
  el('div', { class: 'edit-editor__bar' },
    message,
    el('div', { class: 'edit-editor__buttons' }, cancelButton, saveButton)));

  const read = () => {
    const values = {};
    for (const spec of FIELDS) values[spec.key] = inputs[spec.key].value;
    return values;
  };

  function fill(values) {
    for (const spec of FIELDS) {
      const input = inputs[spec.key];
      let value = values[spec.key] ?? '';
      if (spec.key === 'direct_cause_status') {
        value = String(value || 'unknown');
        // A value the list does not know is kept as it is, never changed.
        if (![...input.options].some((option) => option.value === value)) {
          input.append(el('option', { value }, value));
        }
      }
      input.value = String(value);
    }
  }

  const goneReason = () => {
    if (app.gone || gone === 'analysis') return GONE_ANALYSIS_REASON;
    if (gone === 'node') return GONE_FACTOR_REASON;
    return null;
  };

  const savedTitle = () => (source ? source.savedValues().title : (data && data.title) || node.title);

  function render() {
    if (closed) return;
    const saving = Boolean(source) && isSourceSaving(source);
    const dirty = Boolean(source) && source.isDirty();
    const blocked = goneReason();
    const generating = getGenerationPhase() !== 'idle';
    let state = phase === 'ready' ? (saving ? 'saving' : (dirty ? 'dirty' : 'saved')) : phase;
    if (blocked && phase === 'ready') state = 'gone';
    status.dataset.state = state;
    status.textContent = STATUS_TEXT[state];
    status.className = `ui-status ui-status--${state === 'gone' || state === 'failed' ? 'dirty' : state}`;
    element.dataset.phase = blocked ? 'gone' : phase;

    for (const input of Object.values(inputs)) {
      input.disabled = phase !== 'ready';
      if (input.tagName === 'SELECT') input.disabled = phase !== 'ready' || Boolean(blocked);
      else input.readOnly = Boolean(blocked);
    }
    // While the save is in flight 保存・取消 refuse (aria-disabled, so the
    // focus stays on 保存); otherwise they are disabled when they cannot act.
    saveButton.disabled = phase !== 'ready' || Boolean(blocked);
    saveButton.setAttribute('aria-disabled', saving ? 'true' : 'false');
    saveButton.textContent = saving ? '保存中…' : '保存';
    saveButton.setAttribute('aria-busy', saving ? 'true' : 'false');
    cancelButton.disabled = phase !== 'ready' || (!dirty && !saving) || Boolean(blocked);
    cancelButton.setAttribute('aria-disabled', saving ? 'true' : 'false');

    let text = '';
    let kind = '';
    if (blocked) {
      text = blocked;
      kind = 'error';
    } else if (phase === 'ready' && !saving) {
      const failure = lastFailure(source);
      if (failure && dirty && failure.key === source.draftKey()) {
        text = `保存できませんでした：${failure.reason}`;
        kind = 'error';
      } else if (generating && dirty) {
        text = `${GENERATING_REASON}`;
        kind = 'info';
      }
    }
    message.textContent = text;
    message.dataset.kind = kind;
    message.hidden = !text;
    inputs.title.setAttribute('aria-invalid',
      phase === 'ready' && source && source.validate() ? 'true' : 'false');
  }

  function register(values) {
    source = createFactorSource({
      app,
      nodeId,
      label: () => `要因「${savedTitle()}」の内容`,
      read,
      saved: values,
      onDiscard: () => {
        fill(source.savedValues());
        render();
      },
      onSaved: (fields) => {
        render();
        if (onSaved) onSaved(nodeId, fields);
      },
      blockedReason: goneReason,
    });
    unregister = registerSource(source);
    unsubscribe = subscribe(render);
  }

  async function load() {
    phase = 'loading';
    loadError = '';
    retry.hidden = true;
    loadLine.hidden = false;
    loadLine.dataset.kind = '';
    loadLine.textContent = '保存されている内容を読み込んでいます…';
    render();
    const result = await requestJson(`/nodes/${nodeId}`);
    if (closed) return; // another factor (or a later editor of this one) owns the inspector now
    if (!result.ok || !result.data || Number(result.data.id) !== nodeId
      || Number(result.data.analysis_id) !== Number(analysisId)) {
      phase = 'failed';
      loadError = result.ok ? '応答が正しくありません' : result.reason;
      loadLine.dataset.kind = 'error';
      loadLine.textContent = result.status === 404
        ? 'この要因が見つかりません（削除された可能性があります）。'
        : `保存されている内容を読み込めませんでした：${loadError}。読み込めるまで編集・保存はできません。`;
      retry.hidden = result.status === 404;
      render();
      if (result.status === 404) app.refresh(); // the structure tells whether the analysis is gone too
      if (onLoaded) onLoaded(editor);
      return;
    }
    data = result.data;
    fill(data);
    phase = 'ready';
    loadLine.hidden = true;
    loadLine.textContent = '';
    register(data);
    render();
    if (onLoaded) onLoaded(editor);
  }

  async function save() {
    if (phase !== 'ready' || !source || isSourceSaving(source)) return;
    const blocked = goneReason();
    if (blocked) {
      announce(blocked, { assertive: true });
      return;
    }
    if (getGenerationPhase() !== 'idle') {
      message.textContent = GENERATING_REASON;
      message.dataset.kind = 'info';
      message.hidden = false;
      return;
    }
    if (!source.isDirty()) {
      notify('この要因に保存していない変更はありません', { type: 'info' });
      return;
    }
    const outcome = await saveSource(source);
    if (closed) return;
    if (outcome.ok) {
      if (!outcome.skipped) notify('要因を保存しました', { type: 'success' });
      return;
    }
    render();
    if (outcome.invalid) {
      focusElement(inputs.title);
      announce(outcome.reason, { assertive: true });
      return;
    }
    if (!outcome.notSent) notify(`要因を保存できませんでした：${outcome.reason}`, { type: 'error' });
    // 404: the factor (or the whole analysis) is gone — the partial update
    // tells which; the input stays and is never sent to another factor.
    if (outcome.gone) app.refresh();
  }

  function cancel() {
    if (phase !== 'ready' || !source || isSourceSaving(source) || goneReason()) return;
    fill(source.savedValues());
    refreshUnsaved();
    render();
  }

  saveButton.addEventListener('click', save);
  cancelButton.addEventListener('click', cancel);
  retry.addEventListener('click', () => {
    if (phase === 'failed') load();
  });
  for (const input of Object.values(inputs)) {
    input.addEventListener('input', () => refreshUnsaved());
    input.addEventListener('change', () => refreshUnsaved());
  }
  inputs.title.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || isImeComposing(event)) return; // the IME's Enter confirms a conversion only
    event.preventDefault();
    save();
  });

  const editor = {
    nodeId,
    analysisId,
    element,
    load,
    render,
    get phase() {
      return phase;
    },
    get data() {
      return data;
    },
    get source() {
      return source;
    },
    get gone() {
      return gone;
    },
    savedTitle,
    hasDraft: () => Boolean(source) && (source.isDirty() || isSourceSaving(source)),
    isSaving: () => Boolean(source) && isSourceSaving(source),
    // The factor is no longer on the page: keep the input, send nothing.
    markGone(kind = 'node') {
      if (!gone) gone = kind;
      render();
    },
    // Close this editor: its source leaves the coordinator. Called by the
    // inspector only once a switch has been confirmed (or the draft was
    // dropped by deleting its factor).
    close() {
      if (closed) return;
      closed = true;
      for (const input of Object.values(inputs)) input.disabled = true;
      saveButton.disabled = true;
      cancelButton.disabled = true;
      if (unsubscribe) unsubscribe();
      if (unregister) unregister();
      unregister = null;
      source = null;
    },
    get closed() {
      return closed;
    },
  };
  return editor;
}
