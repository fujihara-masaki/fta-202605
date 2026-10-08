// Analysis title in the header (PR-4: UI-07, plan 5.1, 5.7). ✎ opens an
// input: Enter saves, Esc cancels (the Enter / Esc that confirms or cancels
// an IME conversion does neither: C-08), leaving the input saves — except
// when the focus goes to the editor's own 保存・取消 (focusout relatedTarget),
// so a click there never saves twice or saves what is being cancelled.
// Required and 255 characters as on the list and the new-analysis form
// (common/text.js validateAnalysisTitle: code points after trimming).
//
// The title is a save source of the shared coordinator with leave: 'auto':
// leaving the page waits for a save started by the focus leaving the input,
// saves a changed title without asking, and stays (with the input and the
// reason) when it is empty, too long or cannot be saved. It is not the list's
// rename (SOURCE_ORDER.listRename) and never joins the three choices. One
// save at a time (saveSource): the blur and the click that caused it never
// send the same title twice; a title that failed is not sent again unchanged
// by leaving the input or the page (Enter and 保存 send it again).
// While a generation is prepared, runs or is finished nothing is sent: the
// input stays open with 「生成中のため保存していません」 (J-01).
// The updated time is not shown (J-15).

import { requestJson } from '../../common/http.js';
import { announce, notify } from '../../common/notify.js';
import { focusElement } from '../../common/dom.js';
import { isImeComposing } from '../../common/ime.js';
import {
  ANALYSIS_TITLE_MAX,
  countChars,
  isSameText,
  normalizeText,
  validateAnalysisTitle,
} from '../../common/text.js';
import {
  getGenerationPhase,
  isSourceSaving,
  lastFailure,
  refresh as refreshUnsaved,
  registerSource,
  saveSource,
  subscribe,
} from '../../common/unsaved.js';
import { GONE_REASON, outcomeOf } from './step1.js';

export const GENERATING_TITLE = '生成中のため保存していません（生成が終わると保存できます）';

export function createTitleEditor(app) {
  const view = document.querySelector('[data-title-view]');
  const editor = document.querySelector('[data-title-editor]');
  const heading = document.querySelector('[data-title-text]');
  const editButton = document.querySelector('[data-title-edit]');
  const input = document.getElementById('analysisTitleInput');
  const saveButton = document.querySelector('[data-title-save]');
  const cancelButton = document.querySelector('[data-title-cancel]');
  const counter = document.querySelector('[data-title-count]');
  const help = document.getElementById('analysisTitleHelp');
  const error = document.querySelector('[data-title-error]');
  if (!view || !editor || !input || !editButton) return null;

  let open = false;
  const saved = () => input.dataset.saved ?? '';

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
    input.setAttribute('aria-invalid', 'true');
  }

  function clearError() {
    error.textContent = '';
    error.hidden = true;
    input.removeAttribute('aria-invalid');
  }

  function updateCounter() {
    const length = countChars(normalizeText(input.value));
    if (counter) counter.textContent = String(length);
    if (help) help.dataset.overLimit = length > ANALYSIS_TITLE_MAX ? 'true' : 'false';
  }

  function applyTitle(title) {
    input.dataset.saved = title;
    heading.textContent = title;
    editButton.setAttribute('aria-label', `分析タイトルを変更：${title}`);
    document.querySelectorAll('.edit-header [data-bind-title]').forEach((node) => {
      node.textContent = `：${title}`;
    });
    document.title = `${title} - FTA編集`;
  }

  const source = {
    id: 'edit-analysis-title',
    leave: 'auto',
    label: '分析タイトル',
    target: { analysisId: app.analysisId },
    isDirty: () => open && !isSameText(input.value, saved()),
    draftKey: () => normalizeText(input.value),
    validate: () => validateAnalysisTitle(input.value),
    async save(to) {
      if (app.gone) return { ok: false, notSent: true, reason: GONE_REASON };
      if (getGenerationPhase() !== 'idle') return { ok: false, notSent: true, reason: GENERATING_TITLE };
      const title = normalizeText(input.value);
      const result = await requestJson(`/analyses/${to.analysisId}/title`, { method: 'POST', body: { title } });
      return outcomeOf(result, { value: result.ok && typeof result.data?.title === 'string' ? result.data.title : title });
    },
    commit(outcome) {
      applyTitle(outcome.value);
    },
    discard() {
      close({ focus: false });
    },
    onLeaveBlocked(reason) {
      if (!open) return;
      showError(reason);
      focusElement(input);
    },
  };

  function setBusy(busy) {
    input.readOnly = busy || app.gone;
    saveButton.disabled = busy || app.gone;
    cancelButton.disabled = busy;
    saveButton.textContent = busy ? '保存中…' : '保存';
    editor.setAttribute('aria-busy', busy ? 'true' : 'false');
  }

  function openEditor() {
    if (app.gone || open) {
      if (open) focusElement(input);
      return;
    }
    open = true;
    input.value = saved();
    clearError();
    updateCounter();
    view.hidden = true;
    editor.hidden = false;
    setBusy(false);
    input.focus();
    input.select();
    refreshUnsaved();
  }

  function close({ focus = true } = {}) {
    if (!open) return;
    open = false;
    input.value = saved();
    clearError();
    editor.hidden = true;
    view.hidden = false;
    refreshUnsaved();
    if (focus) focusElement(editButton);
  }

  // trigger: 'enter' | 'button' | 'blur'
  async function commit(trigger) {
    if (!open || isSourceSaving(source)) return;
    if (!source.isDirty()) {
      close({ focus: trigger !== 'blur' });
      return;
    }
    const invalid = validateAnalysisTitle(input.value);
    if (invalid) {
      showError(invalid);
      if (trigger !== 'blur') {
        focusElement(input);
        announce(invalid, { assertive: true });
      }
      refreshUnsaved(); // the failure is recorded when leaving checks again
      return;
    }
    if (getGenerationPhase() !== 'idle') {
      showError(GENERATING_TITLE);
      return;
    }
    const failure = lastFailure(source);
    if (trigger === 'blur' && failure && !failure.invalid && failure.key === source.draftKey()) {
      // The same title failed already: leaving the input again does not send
      // it again (Enter or 保存 do).
      showError(failure.reason);
      return;
    }
    const focusWasInside = editor.contains(document.activeElement);
    const outcome = await saveSource(source);
    if (outcome.ok) {
      if (outcome.skipped) return;
      const keepFocus = trigger !== 'blur' || editor.contains(document.activeElement) || focusWasInside;
      close({ focus: keepFocus && trigger !== 'blur' });
      notify('タイトルを保存しました', { type: 'success' });
      return;
    }
    showError(outcome.reason);
    if (!outcome.notSent) notify(`タイトルを保存できませんでした：${outcome.reason}`, { type: 'error' });
    if (trigger !== 'blur') focusElement(input);
    if (outcome.gone) app.refresh();
  }

  editButton.addEventListener('click', openEditor);
  input.addEventListener('input', () => {
    updateCounter();
    if (!error.hidden && !validateAnalysisTitle(input.value)) clearError();
    refreshUnsaved();
  });
  input.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== 'Escape') return;
    if (isImeComposing(event)) return; // the key belongs to the IME conversion
    event.preventDefault();
    if (event.key === 'Enter') commit('enter');
    else if (!isSourceSaving(source)) close();
  });
  saveButton.addEventListener('click', () => commit('button'));
  cancelButton.addEventListener('click', () => {
    if (!isSourceSaving(source)) close();
  });
  editor.addEventListener('focusout', (event) => {
    const next = event.relatedTarget;
    if (next instanceof Node && editor.contains(next)) return; // 保存・取消 or the input itself
    commit('blur');
  });

  registerSource(source);
  subscribe(() => setBusy(isSourceSaving(source)));

  return {
    source,
    isOpen: () => open,
    stop() {
      editButton.disabled = true;
      setBusy(isSourceSaving(source));
    },
  };
}
