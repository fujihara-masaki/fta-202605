// Analysis list (A): inline rename, delete confirmation, export menus.
//
// - Rename (UI-02): ✎ opens an inline editor. Enter / 保存 saves, Esc / 取消
//   restores. The Enter/Esc that belongs to an IME conversion is ignored
//   (C-08). Required, 255 characters after trimming. The server's reason is
//   shown as-is (C-02) and the browser tab title is left alone (C-01).
//   While the title is changed and unsaved, leaving the page or opening
//   another row's editor asks 保存して移動 / 破棄して移動 / 編集を続ける (J-12).
// - Delete (UI-03): in-page dialog with the title and the factor count at the
//   time the list was rendered (J-13); on success the row is removed.
// - Export (UI-04): menus are set up by common/boot.js.

import { requestJson } from '../common/http.js';
import { notify, announce } from '../common/notify.js';
import { openDialog } from '../common/dialog.js';
import { registerSource, refresh, requestTransition, SOURCE_ORDER } from '../common/unsaved.js';
import { el, focusElement } from '../common/dom.js';
import {
  ANALYSIS_TITLE_MAX,
  countChars,
  isSameText,
  normalizeText,
  truncateForDisplay,
  validateAnalysisTitle,
} from '../common/text.js';
import { isImeComposing } from '../common/ime.js';

const tableWrap = document.querySelector('[data-list-table]');
const tbody = tableWrap ? tableWrap.querySelector('tbody') : null;
const emptyState = document.querySelector('[data-empty-state]');
const countEl = document.querySelector('[data-analysis-count]');
const heading = document.getElementById('list-heading');

let activeRename = null;

function rowTitle(row) {
  return row.dataset.title ?? '';
}

function applyTitle(row, title) {
  row.dataset.title = title;
  const link = row.querySelector('[data-title-link]');
  if (link) link.textContent = title;
  row.querySelectorAll('[data-bind-title]').forEach((node) => {
    node.textContent = `：${title}`;
  });
  const renameButton = row.querySelector('[data-action="rename"]');
  if (renameButton) renameButton.setAttribute('aria-label', `タイトルを変更：${title}`);
}

function focusRow(row) {
  if (!row) return focusElement(heading);
  const link = row.querySelector('[data-title-link]');
  if (link && !link.closest('[hidden]') && focusElement(link)) return true;
  const input = row.querySelector('[data-rename-editor] input');
  if (focusElement(input)) return true;
  return focusElement(heading);
}

// ----- Inline rename -------------------------------------------------------

function isDirty(ctx) {
  return !isSameText(ctx.input.value, ctx.original);
}

function buildEditor(analysisId) {
  const inputId = `rename-input-${analysisId}`;
  const helpId = `rename-help-${analysisId}`;
  const errorId = `rename-error-${analysisId}`;
  const input = el('input', {
    type: 'text',
    id: inputId,
    class: 'ui-input',
    autocomplete: 'off',
    'aria-describedby': `${helpId} ${errorId}`,
  });
  const saveButton = el('button', { type: 'button', class: 'ui-btn ui-btn--sm ui-btn--primary', 'data-rename-save': true }, '保存');
  const cancelButton = el('button', { type: 'button', class: 'ui-btn ui-btn--sm', 'data-rename-cancel': true }, '取消');
  const counter = el('span', { 'data-rename-count': true }, '0');
  const help = el(
    'p',
    { class: 'ui-field-help rename-editor__help', id: helpId },
    counter,
    `／${ANALYSIS_TITLE_MAX}文字（必須）・Enterで保存、Escで取消`,
  );
  const error = el('p', { class: 'ui-field-error rename-editor__error', id: errorId, hidden: true });
  const editor = el(
    'div',
    { class: 'rename-editor', role: 'group', 'aria-label': 'タイトルの変更', 'data-rename-editor': true },
    el('label', { class: 'visually-hidden', for: inputId }, `分析タイトル（必須、${ANALYSIS_TITLE_MAX}文字以内）`),
    input,
    el('div', { class: 'rename-editor__actions' }, saveButton, cancelButton),
    help,
    error,
  );
  return { editor, input, saveButton, cancelButton, counter, help, error };
}

function updateCounter(ctx) {
  const length = countChars(normalizeText(ctx.input.value));
  ctx.counter.textContent = String(length);
  ctx.help.dataset.overLimit = length > ANALYSIS_TITLE_MAX ? 'true' : 'false';
}

function showError(ctx, message, kind) {
  ctx.errorKind = kind;
  ctx.error.textContent = message;
  ctx.error.hidden = false;
  ctx.input.setAttribute('aria-invalid', 'true');
}

function clearError(ctx) {
  ctx.errorKind = null;
  ctx.error.textContent = '';
  ctx.error.hidden = true;
  ctx.input.removeAttribute('aria-invalid');
}

function setBusy(ctx, busy) {
  ctx.input.readOnly = busy;
  ctx.saveButton.disabled = busy;
  ctx.cancelButton.disabled = busy;
  ctx.saveButton.textContent = busy ? '保存中…' : '保存';
  ctx.editor.setAttribute('aria-busy', busy ? 'true' : 'false');
}

function closeRename(ctx, { focus = true } = {}) {
  if (ctx.closed) return;
  ctx.closed = true;
  if (ctx.unregister) ctx.unregister();
  ctx.editor.remove();
  ctx.view.hidden = false;
  if (activeRename === ctx) activeRename = null;
  refresh();
  if (focus) focusElement(ctx.row.querySelector('[data-action="rename"]'));
}

function saveRename(ctx, { fromGuard = false } = {}) {
  if (ctx.saving) return ctx.savePromise;
  const invalid = validateAnalysisTitle(ctx.input.value);
  if (invalid) {
    showError(ctx, invalid, 'validation');
    if (!fromGuard) {
      ctx.input.focus();
      announce(invalid, { assertive: true });
    }
    return Promise.resolve({ ok: false, reason: invalid });
  }

  const title = normalizeText(ctx.input.value);
  ctx.saving = true;
  setBusy(ctx, true);
  refresh();
  ctx.savePromise = requestJson(`/analyses/${ctx.id}/title`, { method: 'POST', body: { title } })
    .then((result) => {
      ctx.saving = false;
      if (result.ok) {
        const saved = typeof result.data?.title === 'string' ? result.data.title : title;
        applyTitle(ctx.row, saved);
        closeRename(ctx, { focus: !fromGuard });
        notify('タイトルを保存しました', { type: 'success' });
        return { ok: true };
      }
      setBusy(ctx, false);
      showError(ctx, result.reason, 'server');
      refresh();
      if (!fromGuard) {
        notify(`タイトルを保存できませんでした：${result.reason}`, { type: 'error' });
        ctx.input.focus();
      }
      return { ok: false, reason: result.reason };
    });
  return ctx.savePromise;
}

function startRename(row) {
  const view = row.querySelector('[data-title-view]');
  if (!view) return;
  const analysisId = row.dataset.analysisId;
  const parts = buildEditor(analysisId);
  const ctx = {
    row,
    view,
    id: analysisId,
    original: rowTitle(row),
    saving: false,
    savePromise: null,
    closed: false,
    errorKind: null,
    unregister: null,
    ...parts,
  };

  ctx.input.value = ctx.original;
  view.hidden = true;
  view.after(ctx.editor);
  updateCounter(ctx);

  ctx.unregister = registerSource({
    id: `list-rename-${analysisId}`,
    order: SOURCE_ORDER.listRename,
    label: () => `分析「${truncateForDisplay(ctx.original)}」のタイトル（変更後：「${truncateForDisplay(ctx.input.value)}」）`,
    isDirty: () => isDirty(ctx),
    isSaving: () => ctx.saving,
    whenIdle: () => ctx.savePromise || Promise.resolve(),
    validate: () => validateAnalysisTitle(ctx.input.value),
    save: () => saveRename(ctx, { fromGuard: true }),
    discard: () => closeRename(ctx, { focus: false }),
  });

  ctx.input.addEventListener('input', () => {
    updateCounter(ctx);
    if (ctx.errorKind === 'validation' && !validateAnalysisTitle(ctx.input.value)) clearError(ctx);
    refresh();
  });
  ctx.input.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== 'Escape') return;
    // The key that confirms or cancels an IME conversion is not ours.
    if (isImeComposing(event)) return;
    event.preventDefault();
    if (event.key === 'Enter') saveRename(ctx);
    else if (!ctx.saving) closeRename(ctx); // keep the editor while a save is in flight
  });
  ctx.saveButton.addEventListener('click', () => saveRename(ctx));
  ctx.cancelButton.addEventListener('click', () => closeRename(ctx));

  activeRename = ctx;
  ctx.input.focus();
  ctx.input.select();
}

function requestRename(row, invoker) {
  const current = activeRename;
  if (current) {
    if (current.row === row) {
      current.input.focus();
      return;
    }
    if (current.saving || isDirty(current)) {
      requestTransition({
        invoker,
        proceed: () => {
          if (activeRename) closeRename(activeRename, { focus: false });
          startRename(row);
        },
      });
      return;
    }
    closeRename(current, { focus: false });
  }
  startRename(row);
}

// ----- Delete --------------------------------------------------------------

function removeRow(row, title) {
  if (activeRename && activeRename.row === row) closeRename(activeRename, { focus: false });
  const rows = tbody ? [...tbody.querySelectorAll('tr[data-analysis-id]')] : [];
  const index = rows.indexOf(row);
  const neighbour = rows[index + 1] || rows[index - 1] || null;
  row.remove();
  const remaining = Math.max(rows.length - 1, 0);
  if (countEl) countEl.textContent = String(remaining);
  if (remaining === 0) {
    if (tableWrap) tableWrap.hidden = true;
    if (emptyState) {
      emptyState.hidden = false;
      focusElement(emptyState.querySelector('h2'));
    }
  } else {
    focusRow(neighbour);
  }
  notify(`分析「${truncateForDisplay(title)}」を削除しました`, { type: 'success' });
}

function openDeleteDialog(row, invoker) {
  const analysisId = row.dataset.analysisId;
  const title = rowTitle(row);
  const count = Number.parseInt(row.dataset.factorCount || '0', 10) || 0;
  const discardsRename = Boolean(activeRename && activeRename.row === row && isDirty(activeRename));

  const body = [
    el('p', {}, '分析「', el('strong', {}, title), '」を削除します。'),
    count > 0
      ? `この分析の要因 ${count}件（一覧を表示した時点の件数）と、それぞれの評価・メモもすべて削除されます。`
      : 'この分析に要因はありません（一覧を表示した時点）。',
    discardsRename ? '編集中のタイトルの変更も破棄されます。' : null,
    el('p', { class: 'ui-dialog__warning' }, 'この操作は取り消せません。'),
  ];

  openDialog({
    title: '分析を削除しますか？',
    body,
    actions: [
      { id: 'cancel', label: 'キャンセル', autofocus: true },
      { id: 'delete', label: '削除する', variant: 'danger' },
    ],
    invoker,
    fallbackFocus: () => heading,
    onAction: async (actionId, dialog) => {
      if (actionId !== 'delete') {
        dialog.close(actionId);
        return;
      }
      dialog.setError(null);
      dialog.setBusy(true, '削除しています…');
      const result = await requestJson(`/analyses/${analysisId}/delete`, { method: 'POST' });
      if (result.ok) {
        dialog.close('deleted', { restoreFocus: false });
        removeRow(row, title);
        return;
      }
      if (!dialog.isOpen()) {
        notify(`分析を削除できませんでした：${result.reason}`, { type: 'error' });
        return;
      }
      dialog.setBusy(false);
      dialog.setError(`削除できませんでした：${result.reason}`);
      focusElement(dialog.button('cancel'));
    },
  });
}

// ----- Wiring --------------------------------------------------------------

if (tbody) {
  tbody.addEventListener('click', (event) => {
    const button = event.target instanceof Element ? event.target.closest('button[data-action]') : null;
    if (!button) return;
    const row = button.closest('tr[data-analysis-id]');
    if (!row) return;
    if (button.dataset.action === 'rename') requestRename(row, button);
    else if (button.dataset.action === 'delete') openDeleteDialog(row, button);
  });
}
