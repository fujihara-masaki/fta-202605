// Deleting a factor through an in-page dialog (PR-5: UI-14, J-13; replaces
// the browser's confirm()). The dialog names the factor and the number of its
// descendants as the server walked them for the data of this page
// (app/detail_view.py deletion_scope — the whole subtree the delete API
// removes, without the display's depth limit; delete.scope counts the factor
// itself, so descendants = scope − 1) and says that the numbers are those of
// when the screen was shown. Never counted from the rows on the page.
//
// Whether the factor may be deleted (判断2) is asked at three points with the
// same answer (edit/permissions.js): the button (disabled with its reason),
// opening this dialog, and confirming it (the data may have been updated
// meanwhile). Refused: nothing is asked or sent. Also refused at both points
// while the save of the edited factor (the factor deleted or one below it)
// is in flight.
//
// When the factor being edited in the inspector, or one of its ancestors, is
// deleted, the dialog says 「編集中の変更も破棄されます」. キャンセル, Esc and a
// failed delete keep the draft; only a successful delete drops the drafts it
// affects (deleting another factor keeps the draft). Afterwards a partial
// update selects the parent, or the top event (edit/refresh.js).

import { el, focusElement } from '../../common/dom.js';
import { openDialog } from '../../common/dialog.js';
import { requestJson } from '../../common/http.js';
import { notify } from '../../common/notify.js';
import { truncateForDisplay } from '../../common/text.js';
import { currentEditor, dropEditor } from './inspector.js';
import { getNode, isAtOrBelow, levelName } from './model.js';
import { checkDelete } from './permissions.js';

// Is the inspector's draft (if any) on the factor `nodeId` or below it?
function draftAffected(app, nodeId) {
  const editor = currentEditor();
  if (!editor || !editor.hasDraft()) return false;
  if (editor.nodeId === Number(nodeId)) return true;
  const edited = getNode(app.model, editor.nodeId);
  return Boolean(edited) && isAtOrBelow(app.model, edited, nodeId);
}

// The save of the edited factor is in flight and the delete would remove
// that factor (or it is below): refused until the save has ended, so the
// save and the delete never race (Codex review of e53767d).
const SAVING_REASON = '編集中の要因を保存しています。保存が終わってから削除してください。';

function saveInFlightAffected(app, nodeId) {
  const editor = currentEditor();
  return Boolean(editor) && editor.isSaving() && draftAffected(app, nodeId);
}

function check(app, id) {
  const answer = checkDelete(app, id);
  if (!answer.allowed) return answer;
  if (saveInFlightAffected(app, id)) return { allowed: false, reason: SAVING_REASON };
  return answer;
}

export function openDeleteDialog(app, nodeId, { invoker = null } = {}) {
  const id = Number(nodeId);
  const first = check(app, id);
  if (!first.allowed) {
    notify(first.reason, { type: 'error' });
    return null;
  }
  const node = getNode(app.model, id);
  const title = node.title;
  const scope = Number(node.delete && node.delete.scope);
  const descendants = Number.isInteger(scope) && scope > 0 ? scope - 1 : null;
  const affects = draftAffected(app, id);

  const body = [
    el('p', {}, '要因「', el('strong', { 'data-delete-title': true }, title), `」（${levelName(node.level)}要因）を削除します。`),
    descendants === null
      ? el('p', { 'data-delete-count': true }, 'この要因の子孫の要因もすべて削除されます。')
      : el('p', { 'data-delete-count': true },
        descendants > 0
          ? `この要因の子孫 ${descendants}件も一緒に削除されます（合計 ${scope}件）。`
          : 'この要因に子孫の要因はありません（この要因だけを削除します。合計 1件）。'),
    el('p', { class: 'ui-field-help', 'data-delete-when': true },
      '件数は画面を表示した時点の情報です。別のタブなどで変更されていると、実際に削除される件数と異なることがあります。'),
    affects ? el('p', { class: 'ui-dialog__warning', 'data-delete-draft': true }, '編集中の変更も破棄されます。') : null,
    el('p', { class: 'ui-dialog__warning' }, '評価・メモなども含めて削除され、この操作は取り消せません。'),
  ];

  return openDialog({
    title: '要因を削除しますか？',
    body,
    actions: [
      { id: 'cancel', label: 'キャンセル', autofocus: true },
      { id: 'delete', label: '削除する', variant: 'danger' },
    ],
    invoker,
    // The button replaced by a partial update meanwhile: its successor.
    fallbackFocus: () => document.querySelector(`[data-inspector-body] [data-action="delete"][data-node-id="${id}"]:not([disabled])`)
      || document.querySelector('[data-inspector-body] [data-inspector-title]'),
    onAction: async (actionId, dialog) => {
      if (actionId !== 'delete') {
        dialog.close(actionId);
        return;
      }
      // Asked again: the page may have been updated, or a save of the edited
      // factor started, while the dialog was open.
      const again = check(app, id);
      if (!again.allowed) {
        dialog.setError(again.reason);
        focusElement(dialog.button('cancel'));
        return;
      }
      dialog.setError(null);
      dialog.setBusy(true, '削除しています…');
      const result = await requestJson(`/nodes/${id}/delete`, { method: 'POST' });
      if (!result.ok) {
        // The draft stays.
        if (!dialog.isOpen()) {
          notify(`要因を削除できませんでした：${result.reason}`, { type: 'error' });
          return;
        }
        dialog.setBusy(false);
        dialog.setError(`削除できませんでした：${result.reason}`);
        focusElement(dialog.button('cancel'));
        return;
      }
      if (draftAffected(app, id)) dropEditor();
      dialog.close('deleted');
      notify(`要因「${truncateForDisplay(title)}」を削除しました`, { type: 'success' });
      app.refresh({ deleted: id });
    },
  });
}
