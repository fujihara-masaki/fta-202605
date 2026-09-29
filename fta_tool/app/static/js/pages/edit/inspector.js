// Inspector (right pane), display only in PR-3 (plan 7.2): breadcrumb,
// tags (J-14), the parent-link notice (J-25), judgement (saved at once),
// quality warning (UI-17), the saved details, children, and the actions that
// still call the legacy functions of app.js (詳細を編集, AIで追加生成,
// 手動追加, 削除). Deletion and child actions are offered as the server
// computed them (app/detail_view.py): a disabled button shows its reason.
//
// The details come from GET /nodes/{id} when the inspector opens (plan
// 3.4-4) — never from what an earlier selection showed: the fields are
// cleared first, and only the answer for the latest selection is used.
// Text is always inserted as text (common/dom.js).

import { el } from '../../common/dom.js';
import { requestJson } from '../../common/http.js';
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

const DIRECT_CAUSE_FULL = {
  unknown: '未評価',
  likely: '直接要因の可能性が高い',
  unlikely: '直接要因の可能性が低い',
  direct: '直接要因',
  not_direct: '直接要因でない',
};

const DETAIL_FIELDS = [
  ['description', '説明'],
  ['memo', 'メモ'],
  ['direct_cause_status', '直接要因評価'],
  ['direct_cause_comment', '評価コメント'],
  ['evidence', '根拠'],
  ['prevention_idea', '再発防止策の候補'],
];

let sequence = 0;

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
        actionButton(app, '一次要因を手動追加', { 'data-action': 'legacy-add', 'data-level': '1' })),
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
  lines.push(el('p', {}, 'この要因を親にした生成・手動追加はできません。内容の確認と「詳細を編集」での保存はできます。'));
  return el('div', { class: 'edit-inspector__notice', role: 'note', 'data-integrity-notice': true }, lines);
}

function detailsSection(app, node) {
  const list = el('dl', { class: 'edit-details', 'data-details': true, hidden: true },
    DETAIL_FIELDS.map(([key, label]) => [el('dt', {}, label), el('dd', { 'data-detail': key })]));
  return section('要因の内容', [
    el('p', { class: 'edit-inspector__status', role: 'status', 'data-detail-status': true }, '保存されている内容を読み込んでいます…'),
    list,
    el('div', { class: 'edit-inspector__actions' },
      actionButton(app, '詳細を編集', { 'data-action': 'legacy-detail', 'data-node-id': node.id })),
    el('p', { class: 'edit-inspector__reason' },
      '「詳細を編集」で、タイトル・説明・メモ・直接要因評価・評価コメント・根拠・再発防止策を編集できます。'),
  ], { 'data-inspector-details': true });
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
        'data-action': 'legacy-add', 'data-parent-id': node.id, 'data-level': level,
      }, { blocked: reason, describedBy })));
    if (reason) content.push(el('p', { class: 'edit-inspector__reason', id: 'inspector-children-reason' }, reason));
  }
  return section(`子要因（${items.length}件）`, content, { 'data-inspector-children': true });
}

// 削除 as the server computed it for the data of this page (判断2); the
// legacy deleteNode checks the same result again before it asks or sends.
function deleteSection(app, node) {
  const allowed = Boolean(node.delete && node.delete.allowed);
  const reason = allowed ? '' : (node.delete && node.delete.reason) || '削除できるか確認できていません。';
  return el('section', { class: 'edit-inspector__section', 'data-inspector-delete': true },
    el('div', { class: 'edit-inspector__actions' },
      actionButton(app, 'この要因を削除', { 'data-action': 'legacy-delete', 'data-node-id': node.id },
        { blocked: reason, variant: 'ui-btn--danger-outline', describedBy: 'inspector-delete-reason' })),
    el('p', { class: 'edit-inspector__reason', id: 'inspector-delete-reason', 'data-delete-reason': true },
      allowed ? '子孫の要因もすべて削除されます。この操作は取り消せません。' : reason));
}

function nodeContent(app, node) {
  const { chain, underTopEvent } = ancestry(app.model, node);
  const items = [underTopEvent ? { label: '頂上事象', select: 'top' } : { label: '親子関係に不整合がある要因' }];
  for (const ancestor of chain) items.push({ label: ancestor.title, nodeId: ancestor.id });
  items.push({ label: node.title, current: true });
  return [
    crumbs(items),
    el('h3', { class: 'edit-inspector__title', tabindex: '-1', 'data-inspector-title': true }, node.title),
    tags(node),
    node.kind === 'ok' ? null : notice(app, node),
    section('評価', [
      judgementToggle(node),
      el('p', { class: 'edit-inspector__reason' }, '選んだ時点で保存されます（直接要因評価とは別の値です）。'),
    ]),
    node.warning
      ? section('品質警告', [
        el('p', { class: 'edit-inspector__warning', 'data-warning-text': true }, '読み込んでいます…'),
      ], { 'data-inspector-warning': true })
      : null,
    detailsSection(app, node),
    childrenSection(app, node),
    deleteSection(app, node),
  ].filter(Boolean);
}

async function loadDetails(app, node, token, { focusWarning }) {
  const result = await requestJson(`/nodes/${node.id}`);
  if (token !== sequence) return; // a later selection owns the inspector now
  const root = body();
  if (!root) return;
  const status = root.querySelector('[data-detail-status]');
  const list = root.querySelector('[data-details]');
  const warning = root.querySelector('[data-warning-text]');
  if (!result.ok || !result.data || result.data.id !== node.id) {
    if (status) {
      status.textContent = `保存されている内容を読み込めませんでした：${result.reason || '応答が正しくありません'}`;
      status.dataset.kind = 'error';
    }
    if (warning) warning.textContent = '品質警告を読み込めませんでした。';
    return;
  }
  const data = result.data;
  for (const [key] of DETAIL_FIELDS) {
    const cell = list ? list.querySelector(`[data-detail="${key}"]`) : null;
    if (!cell) continue;
    let value = data[key] ?? '';
    if (key === 'direct_cause_status') value = DIRECT_CAUSE_FULL[value] || value;
    const empty = !String(value).trim();
    cell.textContent = empty ? '（未入力）' : value;
    cell.dataset.empty = empty ? 'true' : 'false';
  }
  if (list) list.hidden = false;
  if (status) status.textContent = '保存されている内容です。';
  if (warning) {
    warning.textContent = data.warning_flags ? data.warning_flags : '（品質警告はありません）';
    if (focusWarning) focusWarningSection();
  }
}

function focusWarningSection() {
  const heading = document.querySelector('[data-inspector-warning] .edit-inspector__section-title');
  if (!heading) return;
  heading.scrollIntoView({ block: 'nearest' });
  heading.focus({ preventScroll: true });
}

export function renderInspector(app, { focusWarning = false, focusTitle = false } = {}) {
  const root = body();
  if (!root) return;
  sequence += 1;
  const token = sequence;
  if (app.state.sel === 'top') {
    root.replaceChildren(...topContent(app));
  } else {
    const node = getNode(app.model, app.state.sel);
    if (!node) {
      root.replaceChildren(el('p', { class: 'edit-inspector__status' }, '要因が選ばれていません。'));
      return;
    }
    root.replaceChildren(...nodeContent(app, node));
    loadDetails(app, node, token, { focusWarning });
    if (focusWarning) focusWarningSection();
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
