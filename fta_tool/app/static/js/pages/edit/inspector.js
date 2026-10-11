// Inspector (right pane): breadcrumb, tags (J-14), the parent-link notice
// (J-25), judgement (saved at once), quality warning (UI-17), the factor's
// editor (PR-5: edit/factor-editor.js — title, description, memo and the
// direct-cause fields, saved with 保存), children with AI additional
// generation (still the legacy function of app.js until PR-6) and the manual
// add dialog, and 削除 (the in-page dialog, edit/delete-dialog.js). Deletion
// and child actions are offered as the server computed them
// (app/detail_view.py): a disabled button shows its reason.
//
// The editor holds the draft. renderInspector() draws the rest again (after
// a judgement, a save, a partial update) and puts the same editor element
// back, with the focus and the text selection where they were, so neither
// a partial update nor a new drawing drops the input. A new editor (and a
// new GET /nodes/{id}) is made only when another factor is shown, i.e. after
// the switch was confirmed (edit.js requestSelect, R-01); the old editor's
// source leaves the save coordinator only then. When the edited factor is no
// longer in the data (removed elsewhere) while it has a draft, the editor
// stays with its input and the reason it cannot be saved (plan 5.2).
// Text is always inserted as text (common/dom.js).

import { el } from '../../common/dom.js';
import { createFactorEditor } from './factor-editor.js';
import {
  ancestry,
  childrenOf,
  DIRECT_CAUSE_LABELS,
  getNode,
  isConsistentRoot,
  isDisplayLink,
  judgementLabel,
  levelName,
} from './model.js';

let editor = null; // the editor of the factor shown, or null
let editorHooks = {};

function body() {
  return document.querySelector('[data-inspector-body]');
}

function crumbs(items) {
  return el(
    'nav',
    { class: 'edit-crumbs', 'aria-label': 'パンくず' },
    el('ol', {}, items.map((item) => {
      if (item.current) return el('li', { 'aria-current': 'page' }, item.label);
      if (item.select === 'top') {
        return el('li', {}, el('button', {
          type: 'button', class: 'edit-link', 'data-action': 'select', 'data-select': 'top', 'data-role': 'crumb',
        }, item.label));
      }
      if (item.nodeId !== undefined) {
        return el('li', {}, el('button', {
          type: 'button', class: 'edit-link', 'data-action': 'select', 'data-node-id': item.nodeId, 'data-role': 'crumb',
        }, item.label));
      }
      return el('li', {}, item.label);
    })),
  );
}

function section(title, children, attrs = {}) {
  return el('section', { class: 'edit-inspector__section', ...attrs },
    el('h4', { class: 'edit-inspector__section-title', tabindex: '-1' }, title),
    children);
}

function chip(node) {
  return el('span', {
    class: `ui-chip ui-chip--${node.judgement}`, 'data-judgement-chip': true, 'data-node-id': node.id,
  }, judgementLabel(node.judgement));
}

function judgementToggle(node) {
  return el(
    'div',
    { class: 'ui-judgement', role: 'group', 'aria-label': `評価：${node.title}`, 'data-judgement-toggle': true, 'data-node-id': node.id },
    [['yes', 'Yes'], ['no', 'No'], ['unknown', '未']].map(([value, text]) => el('button', {
      type: 'button',
      class: `ui-judgement__option ui-judgement__option--${value}`,
      'data-action': 'judgement',
      'data-node-id': node.id,
      'data-value': value,
      'aria-pressed': node.judgement === value ? 'true' : 'false',
    }, text)),
  );
}

function tags(node) {
  const direct = DIRECT_CAUSE_LABELS[node.directCause];
  return el('div', { class: 'edit-inspector__tags' },
    el('span', { class: 'ui-tag ui-tag--level' }, levelName(node.level)),
    el('span', { class: `ui-tag ${node.ai ? 'ui-tag--ai' : 'ui-tag--manual'}` }, node.ai ? 'AI' : '手動'),
    node.warning ? el('span', { class: 'ui-tag ui-tag--warning' }, '要確認') : null,
    direct ? el('span', { class: 'ui-tag ui-tag--direct' }, `直接要因評価：${direct}`) : null,
    node.memo ? el('span', { class: 'ui-tag ui-tag--memo' }, 'メモあり') : null);
}

// A button that runs a legacy action. `blocked` (the reason) keeps it
// disabled even when generation ends: app.setGenerating only re-enables
// generation buttons without data-blocked-reason.
function actionButton(app, label, attrs, { blocked = '', generate = false, variant = '', describedBy = null } = {}) {
  return el('button', {
    type: 'button',
    class: `ui-btn ui-btn--sm ${variant}`.trim(),
    ...attrs,
    'data-generate': generate || undefined,
    'data-blocked-reason': blocked || undefined,
    disabled: Boolean(blocked) || (generate && app.generating),
    'aria-describedby': describedBy || undefined,
  }, label);
}

function childList(app, parent, items) {
  if (!items.length) return el('p', { class: 'edit-inspector__status' }, '子要因はありません。');
  return el('ul', { class: 'edit-children' }, items.map((child) => el('li', {},
    chip(child),
    el('button', {
      type: 'button', class: 'edit-link', 'data-action': 'select', 'data-node-id': child.id, 'data-role': 'child',
    }, child.title),
    isDisplayLink(child) ? null : el('span', { class: 'ui-tag ui-tag--issue' }, child.label))));
}

function topContent(app) {
  const input = document.getElementById('topEventInput');
  const saved = input ? input.dataset.saved || '' : '';
  const roots = app.model.nodes.filter(isConsistentRoot);
  return [
    crumbs([{ label: '頂上事象', current: true }]),
    el('h3', { class: 'edit-inspector__title', tabindex: '-1', 'data-inspector-title': true }, '頂上事象'),
    el('p', { class: 'edit-inspector__text', 'data-top-event-text': true }, saved.trim() ? saved : '（頂上事象が未設定です）'),
    el('div', { class: 'edit-inspector__actions' },
      el('button', { type: 'button', class: 'ui-btn ui-btn--sm', 'data-action': 'step', 'data-step': '1' },
        '「① 頂上事象・参考情報」を開く')),
    section(`一次要因（${roots.length}件）`, [
      childList(app, null, roots),
      el('div', { class: 'edit-inspector__actions' },
        roots.length
          ? actionButton(app, '一次要因を追加生成', { 'data-action': 'legacy-generate-additional', 'data-level': '1' }, { generate: true })
          : null,
        actionButton(app, '一次要因を手動追加', { 'data-action': 'add', 'data-level': '1' })),
    ]),
  ];
}

function notice(app, node) {
  const lines = [el('p', {}, el('strong', {}, '親子関係の不整合：'), node.label)];
  for (const note of (node.notes || []).slice(1)) lines.push(el('p', {}, note));
  if (node.kind === 'upper' && node.anomalyRoot !== null) {
    const root = getNode(app.model, node.anomalyRoot);
    if (root) {
      lines.push(el('p', {}, '不整合のある上位の要因：', el('button', {
        type: 'button', class: 'edit-link', 'data-action': 'select', 'data-node-id': root.id, 'data-role': 'crumb',
      }, root.title)));
    }
  }
  lines.push(el('p', {}, 'この要因を親にした生成・手動追加はできません。内容の確認と、このインスペクタでの内容の保存はできます。'));
  return el('div', { class: 'edit-inspector__notice', role: 'note', 'data-integrity-notice': true }, lines);
}

// The editor of the factor (edit/factor-editor.js); the same element is put
// back every time the inspector is drawn again.
function detailsSection(current) {
  return section('要因の内容', [current.element], { 'data-inspector-details': true });
}

// Children of the factor (links select them), and — for 一次・二次 — AI
// additional generation and manual add below it: allowed whatever the
// judgement (J-16), never below a factor with an inconsistent link or
// ancestor (J-25, 判断3).
function childrenSection(app, node) {
  const items = childrenOf(app.model, node);
  const content = [childList(app, node, items)];
  if (node.level === 1 || node.level === 2) {
    const reason = node.canParent ? '' : node.parentReason;
    const describedBy = reason ? 'inspector-children-reason' : null;
    const level = String(node.level + 1);
    content.push(el('div', { class: 'edit-inspector__actions' },
      actionButton(app, 'AIで追加生成', {
        'data-action': 'legacy-generate-additional', 'data-parent-id': node.id, 'data-level': level,
      }, { blocked: reason, generate: true, describedBy }),
      actionButton(app, '手動追加', {
        'data-action': 'add', 'data-parent-id': node.id, 'data-level': level,
      }, { blocked: reason, describedBy })));
    if (reason) content.push(el('p', { class: 'edit-inspector__reason', id: 'inspector-children-reason' }, reason));
  }
  return section(`子要因（${items.length}件）`, content, { 'data-inspector-children': true });
}

// 削除 as the server computed it for the data of this page (判断2): the
// number of descendants is the server's walk of what the delete API removes
// (delete.scope counts the factor itself), never the rows shown here. The
// dialog (edit/delete-dialog.js) checks the same answer again when it opens
// and before it sends.
function deleteSection(app, node) {
  const allowed = Boolean(node.delete && node.delete.allowed);
  const reason = allowed ? '' : (node.delete && node.delete.reason) || '削除できるか確認できていません。';
  const scope = allowed ? Number(node.delete.scope) : NaN;
  let text = reason;
  if (allowed) {
    if (Number.isInteger(scope) && scope > 1) {
      text = `子孫の要因 ${scope - 1}件もすべて削除されます（画面を表示した時点の件数）。この操作は取り消せません。`;
    } else if (scope === 1) {
      text = 'この要因に子孫の要因はありません（画面を表示した時点）。削除は取り消せません。';
    } else {
      text = '子孫の要因もすべて削除されます。この操作は取り消せません。';
    }
  }
  return el('section', { class: 'edit-inspector__section', 'data-inspector-delete': true },
    el('div', { class: 'edit-inspector__actions' },
      actionButton(app, 'この要因を削除', { 'data-action': 'delete', 'data-node-id': node.id },
        { blocked: reason, variant: 'ui-btn--danger-outline', describedBy: 'inspector-delete-reason' })),
    el('p', { class: 'edit-inspector__reason', id: 'inspector-delete-reason', 'data-delete-reason': true }, text));
}

function breadcrumb(app, node) {
  const { chain, underTopEvent } = ancestry(app.model, node);
  const items = [underTopEvent ? { label: '頂上事象', select: 'top' } : { label: '親子関係に不整合がある要因' }];
  for (const ancestor of chain) items.push({ label: ancestor.title, nodeId: ancestor.id });
  items.push({ label: node.title, current: true });
  return crumbs(items);
}

function warningSection(current) {
  let text = '読み込んでいます…';
  if (current.phase === 'ready') text = current.data.warning_flags ? current.data.warning_flags : '（品質警告はありません）';
  else if (current.phase === 'failed') text = '品質警告を読み込めませんでした。';
  return section('品質警告', [
    el('p', { class: 'edit-inspector__warning', 'data-warning-text': true }, text),
  ], { 'data-inspector-warning': true });
}

function nodeContent(app, node, current) {
  return [
    breadcrumb(app, node),
    el('h3', { class: 'edit-inspector__title', tabindex: '-1', 'data-inspector-title': true }, node.title),
    tags(node),
    node.kind === 'ok' ? null : notice(app, node),
    section('評価', [
      judgementToggle(node),
      el('p', { class: 'edit-inspector__reason' }, '選んだ時点で保存されます（直接要因評価とは別の値です）。'),
    ]),
    node.warning ? warningSection(current) : null,
    detailsSection(current),
    childrenSection(app, node),
    deleteSection(app, node),
  ].filter(Boolean);
}

// The edited factor is no longer in the data (removed elsewhere) but its
// draft stays: the input and why it cannot be saved (plan 5.2).
function goneContent(current) {
  return [
    el('h3', { class: 'edit-inspector__title', tabindex: '-1', 'data-inspector-title': true }, current.savedTitle()),
    el('p', { class: 'edit-inspector__notice', role: 'alert', 'data-factor-gone': true },
      '編集中の要因が見つかりません。入力内容は保存できません（別のタブなどで削除された可能性があります）。'),
    detailsSection(current),
  ];
}

function focusWarningSection() {
  const heading = document.querySelector('[data-inspector-warning] .edit-inspector__section-title');
  if (!heading) return;
  heading.scrollIntoView({ block: 'nearest' });
  heading.focus({ preventScroll: true });
}

// The element of the editor that has the focus, and its text selection, so
// they come back after the editor was put back.
function captureFocus() {
  const active = document.activeElement;
  if (!editor || !active || !editor.element.contains(active)) return null;
  const range = typeof active.selectionStart === 'number'
    ? { start: active.selectionStart, end: active.selectionEnd, direction: active.selectionDirection } : null;
  return { element: active, range };
}

function restoreCaptured(captured) {
  if (!captured || !captured.element.isConnected) return;
  captured.element.focus({ preventScroll: true });
  if (captured.range) {
    try {
      captured.element.setSelectionRange(captured.range.start, captured.range.end, captured.range.direction);
    } catch {
      // not a text control
    }
  }
}

export function currentEditor() {
  return editor && !editor.closed ? editor : null;
}

// The draft's save source of the factor shown (null while loading or when
// the load failed: nothing to protect yet).
export function currentFactorSource() {
  const current = currentEditor();
  return current ? current.source : null;
}

function closeEditor() {
  if (editor) editor.close();
  editor = null;
}

// Drop the draft of the editor (its factor or an ancestor was deleted).
export function dropEditor() {
  closeEditor();
}

export function setEditorHooks(hooks) {
  editorHooks = hooks || {};
}

function onLoaded(app, current, focusWarning) {
  if (current !== editor) return;
  const warning = document.querySelector('[data-inspector-body] [data-warning-text]');
  if (warning) {
    if (current.phase === 'ready') warning.textContent = current.data.warning_flags || '（品質警告はありません）';
    else warning.textContent = '品質警告を読み込めませんでした。';
  }
  if (focusWarning || current.pendingFocusWarning) {
    current.pendingFocusWarning = false;
    focusWarningSection();
  }
}

export function renderInspector(app, { focusWarning = false, focusTitle = false } = {}) {
  const root = body();
  if (!root) return;
  const captured = captureFocus();
  if (app.state.sel === 'top') {
    closeEditor();
    root.replaceChildren(...topContent(app));
  } else {
    const id = Number(app.state.sel);
    const node = getNode(app.model, id);
    const same = editor && editor.nodeId === id && editor.analysisId === app.analysisId;
    if (same && !node) {
      editor.markGone('node');
      root.replaceChildren(...goneContent(editor));
    } else if (!node) {
      closeEditor();
      root.replaceChildren(el('p', { class: 'edit-inspector__status' }, '要因が選ばれていません。'));
      return;
    } else if (same) {
      root.replaceChildren(...nodeContent(app, node, editor));
      editor.render();
      if (focusWarning) {
        if (editor.phase === 'loading') editor.pendingFocusWarning = true;
        else focusWarningSection();
      }
    } else {
      closeEditor();
      const created = createFactorEditor(app, node, {
        onSaved: (nodeId, fields) => editorHooks.onSaved?.(nodeId, fields),
        onLoaded: (current) => onLoaded(app, current, focusWarning),
      });
      editor = created;
      root.replaceChildren(...nodeContent(app, node, created));
      created.load();
      if (focusWarning) focusWarningSection();
    }
  }
  restoreCaptured(captured);
  if (app.gone) {
    // The analysis is gone (edit/refresh.js): nothing can be saved any more.
    root.querySelectorAll('[data-action="judgement"], [data-action^="legacy-"], [data-action="add"], [data-action="delete"]')
      .forEach((button) => {
        button.disabled = true;
      });
    if (editor) editor.render();
  }
  if (focusTitle) {
    const title = root.querySelector('[data-inspector-title]');
    if (title) title.focus({ preventScroll: false });
  }
}

export function updateTopEventText(saved) {
  const text = document.querySelector('[data-inspector-body] [data-top-event-text]');
  if (text) text.textContent = String(saved ?? '').trim() ? saved : '（頂上事象が未設定です）';
}
