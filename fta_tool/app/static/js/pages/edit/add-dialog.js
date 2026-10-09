// Manual add through an in-page dialog (PR-5: UI-11; replaces the legacy
// modal). AI is not used: the factor is made 手動・未評価 by the existing
// APIs (POST /analyses/{id}/nodes/add-level1, POST /nodes/{parent}/children).
//
// - The place is fixed when the dialog opens — analysis, parent and level —
//   and shown (追加先); the request goes there whatever is selected later.
// - The parent must be one the edit screen allows (J-25, 判断3:
//   edit/permissions.js), asked when the dialog opens and again right before
//   the request (the page may have been updated meanwhile).
// - A refusal of the server (e.g. 409 同名の要因が既に存在します) is shown in
//   the dialog, the input stays. The buttons are off while the request runs,
//   so it is never sent twice. Enter in the title (not the Enter that
//   confirms an IME conversion) adds; Esc and キャンセル close and drop the
//   input.
// - After a success the dialog closes and a partial update shows the factor;
//   selecting it goes through the R-01 check (edit.js autoSelect: the
//   inspector's unsaved draft is asked about; 編集を続ける keeps the selection
//   and the draft, the factor stays added). A later choice of the user is
//   never replaced by that selection (edit/refresh.js selectIntent); a later
//   add completed while that check is open becomes the one selected.
//   Nothing about the selection or the display sends the add again.

import { el, focusElement } from '../../common/dom.js';
import { openDialog } from '../../common/dialog.js';
import { requestJson } from '../../common/http.js';
import { isImeComposing } from '../../common/ime.js';
import { notify } from '../../common/notify.js';
import { normalizeText } from '../../common/text.js';
import { getNode, levelName } from './model.js';
import { checkParent, GONE } from './permissions.js';

let open = null; // { dialog, title, description } while the dialog is open

// Typed input in the dialog (a partial update that fails does not reload the
// page then).
export function hasAddDialogInput() {
  if (!open || !open.dialog.isOpen()) return false;
  return Boolean(open.title.value || open.description.value);
}

function invokerSelector(button) {
  const parts = ['[data-action="add"]'];
  for (const [key, attr] of [['parentId', 'data-parent-id'], ['level', 'data-level']]) {
    if (button.dataset[key] !== undefined) parts.push(`[${attr}="${CSS.escape(button.dataset[key])}"]`);
  }
  return parts.join('');
}

function check(app, place) {
  if (app.gone) return { allowed: false, reason: GONE };
  if (place.level === 1) return { allowed: true, reason: '' };
  return checkParent(app, place.parentId, place.level);
}

export function openAddDialog(app, { parentId = null, level, invoker = null } = {}) {
  const place = Object.freeze({
    analysisId: app.analysisId,
    parentId: parentId === null || parentId === undefined || parentId === '' ? null : Number(parentId),
    level: Number(level),
  });
  if (place.level !== 1 && place.parentId === null) {
    notify('親要因が指定されていないため、追加できません', { type: 'error' });
    return null;
  }
  const first = check(app, place);
  if (!first.allowed) {
    notify(first.reason, { type: 'error' });
    return null;
  }
  const parent = place.parentId === null ? null : getNode(app.model, place.parentId);
  const where = parent
    ? [`「`, el('strong', { 'data-add-parent': true }, parent.title), `」の下の${levelName(place.level)}要因`]
    : ['頂上事象の下の一次要因'];

  const title = el('input', {
    type: 'text', id: 'add-factor-title', class: 'ui-input', autocomplete: 'off', 'aria-required': 'true',
    'data-add-field': 'title',
  });
  const description = el('textarea', {
    id: 'add-factor-description', class: 'ui-input', rows: 3, 'data-add-field': 'description',
  });
  const body = [
    el('p', { 'data-add-place': true }, '追加先：', where),
    el('div', { class: 'ui-field' },
      el('label', { class: 'ui-field__label', for: 'add-factor-title' }, '要因タイトル（必須）'),
      title),
    el('div', { class: 'ui-field' },
      el('label', { class: 'ui-field__label', for: 'add-factor-description' }, '説明（任意）'),
      description),
    el('p', { class: 'ui-field-help' }, 'AIは使いません。手動・未評価の要因として追加します。同じ親の下に同じ名前の要因は追加できません。'),
  ];

  // The button that opened the dialog, found again when a partial update
  // replaced it meanwhile (plan 5.7).
  const successor = invoker && invoker.dataset ? invokerSelector(invoker) : null;
  const dialog = openDialog({
    title: '要因を手動追加',
    fallbackFocus: () => (successor && [...document.querySelectorAll(successor)].find((node) => node.offsetParent !== null))
      || document.querySelector('[data-inspector-body] [data-inspector-title]'),
    body,
    actions: [
      { id: 'cancel', label: 'キャンセル' },
      { id: 'add', label: '追加する', variant: 'primary' },
    ],
    invoker,
    className: 'ui-dialog--form',
    onAction: async (actionId, controller) => {
      if (actionId !== 'add') {
        controller.close(actionId);
        return;
      }
      const text = normalizeText(title.value);
      if (!text) {
        controller.setError('要因タイトルを入力してください');
        title.setAttribute('aria-invalid', 'true');
        focusElement(title);
        return;
      }
      title.removeAttribute('aria-invalid');
      const again = check(app, place);
      if (!again.allowed) {
        controller.setError(again.reason);
        return;
      }
      controller.setError(null);
      controller.setBusy(true, '追加しています…');
      const url = place.level === 1
        ? `/analyses/${place.analysisId}/nodes/add-level1`
        : `/nodes/${place.parentId}/children`;
      const result = await requestJson(url, {
        method: 'POST',
        body: { title: text, description: normalizeText(description.value) },
      });
      if (!result.ok) {
        if (!controller.isOpen()) {
          notify(`要因を追加できませんでした：${result.reason}`, { type: 'error' });
          return;
        }
        controller.setBusy(false);
        controller.setError(`追加できませんでした：${result.reason}`);
        focusElement(title);
        return;
      }
      controller.close('added');
      notify('要因を追加しました', { type: 'success' });
      const nodeId = Number(result.data && result.data.node_id);
      app.refresh(Number.isInteger(nodeId) && nodeId > 0 ? { select: nodeId } : {});
    },
  });
  open = { dialog, title, description };
  dialog.result.then(() => {
    if (open && open.dialog === dialog) open = null;
  });
  title.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || isImeComposing(event)) return; // the IME's Enter confirms a conversion only
    event.preventDefault();
    if (dialog.isBusy() || !dialog.isOpen()) return;
    dialog.button('add').click();
  });
  focusElement(title);
  return dialog;
}
