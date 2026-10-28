// The generation log (PR-6: J-02, J-03, J-04; plan 5.6, 5.9.2).
//
// One log per analysis: the latest generation (a new one replaces it). Each
// row is bound to the parent the request named (never to the selection),
// and shows its result in one of the eight categories of plan 5.6 —
// 作成 / 候補0件 / 全候補除外 / 処理失敗 / 通信失敗 / 親なし / 分析なし /
// サーバーエラー — or, before the answer, 待機中 / 生成中 (送信していません
// when the check right before sending refused the parent). The same
// category is shown as a badge next to the parent's group heading (③・④).
// Categories are words, never colours alone.
//
// Kept in sessionStorage under fta:genlog:v1:<analysis id> (plan 5.9.2):
// the analysis, the times, the level, the kind, and per row the parent's id,
// the category, the counts, the server's reason and the HTTP status — never
// a factor's title or text, never a draft (the parents' names are taken from
// the page's data when shown; an unknown parent is shown as 「ID n」). It
// is written when the generation starts, after every answer and when it
// ends, so a reload — also the one a failed partial update starts — finds
// it. A restored log says that it is the result from before the reload and
// that its counts are those of that time; it never brings back a
// restriction or "still running": a row that had no answer yet is 結果不明.
// A parent no longer on the page gets 「現在はこの親が見つかりません」.
// 閉じる removes it from the page and from the storage.
// Storage that cannot be used (private browsing, quota, blocked) keeps the
// log on the page only and says so; generating and saving go on. Broken
// stored data is dropped.
// The log is shown only in the tab that made it: the tab is identified by a
// mark kept in window.name (it stays across reloads and navigations of the
// same tab), stored with the log. A tab opened by window.open with an opener
// gets a copy of this tab's sessionStorage but not its window.name, so it
// does not show the log (and drops the copy): checked by E-G06. Duplicating
// a tab with the browser's menu may copy window.name too; that is not
// checked — if the log shows there, it differs from the acceptance
// condition (plan 8.6-6) and is for the user to decide (fix it, or accept
// it as a constraint). This is not a history, nor a recovery of drafts, nor
// a sure removal when the browser is closed (a restored session may keep
// it).
// A write that fails (a full or blocked storage) removes the key, so a
// reload never brings back the previous generation's log as if it were
// this one; when the key cannot be removed either, the page says that an
// earlier result may come back (PR-6 review, R6).

import { el } from '../../common/dom.js';
import { sessionStore } from '../../common/storage.js';
import { getNode, levelName } from './model.js';

export const GENLOG_VERSION = 1;
export const genlogKey = (analysisId) => `fta:genlog:v${GENLOG_VERSION}:${Number(analysisId)}`;

export const CATEGORY_LABELS = {
  created: '作成',
  'no-candidates': '候補0件',
  'all-excluded': '全候補除外',
  failed: '処理失敗',
  network: '通信失敗',
  'parent-gone': '親なし',
  'analysis-gone': '分析なし',
  'server-error': 'サーバーエラー',
};
const PROGRESS_LABELS = {
  waiting: '待機中',
  running: '生成中…',
  skipped: '送信していません',
  unknown: '結果不明',
};
const ROW_STATES = new Set([...Object.keys(CATEGORY_LABELS), ...Object.keys(PROGRESS_LABELS)]);
export const FAILURE_STATES = new Set(['failed', 'network', 'parent-gone', 'analysis-gone', 'server-error']);

const MAX_TEXT = 300;
const MAX_REASONS = 10;

function text(value, max = MAX_TEXT) {
  return typeof value === 'string' ? value.slice(0, max) : '';
}

function count(value) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : 0;
}

export function kindLabel(log) {
  return `${levelName(log.level)}要因の${log.kind === 'additional' ? '追加生成' : '通常生成'}`;
}

function pad(n) {
  return String(n).padStart(2, '0');
}

function dateTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '（時刻不明）';
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// The mark of this tab (window.name, kept across reloads of the same tab).
function tabMark() {
  try {
    if (!window.name) window.name = `fta-tab:${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    return window.name;
  } catch {
    return null;
  }
}

// ----- the stored form ------------------------------------------------------

function storedRow(row) {
  return {
    parentId: row.parentId === null ? null : count(row.parentId),
    state: row.state,
    created: count(row.created),
    excluded: count(row.excluded),
    aiReturned: count(row.aiReturned),
    partialCreated: count(row.partialCreated),
    reasons: (row.reasons || []).map((reason) => text(reason, 100)).slice(0, MAX_REASONS),
    message: text(row.message),
    httpStatus: count(row.httpStatus),
    errorKind: text(row.errorKind, 20),
    checkParent: Boolean(row.checkParent),
    observed: row.observed === null || row.observed === undefined ? null : count(row.observed),
    warnings: row.warnings === null || row.warnings === undefined ? null : count(row.warnings),
    parentUnchecked: Boolean(row.parentUnchecked),
  };
}

function storedLog(log) {
  return {
    v: GENLOG_VERSION,
    analysisId: log.analysisId,
    tab: log.tab,
    startedAt: log.startedAt,
    endedAt: log.endedAt || null,
    level: log.level,
    kind: log.kind,
    status: log.status,
    excludedParents: count(log.excludedParents),
    update: log.update,
    jsError: Boolean(log.jsError),
    rows: log.rows.map(storedRow),
  };
}

// A stored log as it may be shown, or null when it is broken or not this
// analysis'.
function validLog(value, analysisId) {
  if (!value || typeof value !== 'object' || value.v !== GENLOG_VERSION) return null;
  if (Number(value.analysisId) !== Number(analysisId)) return null;
  if (![1, 2, 3].includes(value.level) || !['normal', 'additional'].includes(value.kind)) return null;
  if (!Array.isArray(value.rows) || value.rows.length > 500) return null;
  if (typeof value.startedAt !== 'string') return null;
  const rows = [];
  for (const row of value.rows) {
    if (!row || typeof row !== 'object' || !ROW_STATES.has(row.state)) return null;
    if (row.parentId !== null && !Number.isInteger(row.parentId)) return null;
    rows.push(storedRow(row));
  }
  return {
    ...storedLog({ ...value, rows: [] }),
    tab: typeof value.tab === 'string' ? value.tab : null,
    status: ['running', 'finishing', 'done'].includes(value.status) ? value.status : 'done',
    update: ['pending', 'applied', 'failed'].includes(value.update) ? value.update : 'pending',
    rows,
  };
}

// ----- the log --------------------------------------------------------------

export function createGenLog(app) {
  let log = null; // the log shown (or null)
  let restored = false;
  let stored = true; // false: the storage could not be used for it
  let staleKept = false; // the write failed and the previous log could not be removed

  function slot(level) {
    return document.querySelector(`[data-gen-log-slot="${level}"]`);
  }

  function save() {
    if (!log) return;
    const key = genlogKey(app.analysisId);
    stored = sessionStore.setJSON(key, storedLog(log));
    staleKept = false;
    if (!stored) {
      // Never leave the previous generation's log to be restored as this one.
      sessionStore.removeItem(key);
      staleKept = sessionStore.getItem(key) !== null;
    }
  }

  function parentName(row) {
    if (row.parentId === null) return '頂上事象の下（一次要因）';
    const node = getNode(app.model, row.parentId);
    return node ? `「${node.title}」` : `ID ${row.parentId}`;
  }

  function rowLabel(row) {
    if (row.state === 'created') return `作成 ${row.created}件`;
    return CATEGORY_LABELS[row.state] || PROGRESS_LABELS[row.state] || row.state;
  }

  // The details of a row (reasons, notes), as text.
  function rowDetails(row) {
    const lines = [];
    switch (row.state) {
      case 'created':
        if (row.excluded) lines.push(`候補のうち${row.excluded}件は品質チェック・重複で除外`);
        if (row.warnings) lines.push(`品質警告（要確認）付き：${row.warnings}件`);
        if (row.reasons.length && row.excluded) lines.push(`除外の主な理由：${row.reasons.join('、')}`);
        if (row.observed !== null && row.observed !== row.created) {
          lines.push(`注記：応答の作成件数（${row.created}件）と、更新後にこの親の下で確認できた新しい要因の数（${row.observed}件）が一致しません（件数は応答の値です）`);
        }
        break;
      case 'no-candidates':
        lines.push(row.message || '生成候補がありませんでした（LLMが要因を返しませんでした）');
        break;
      case 'all-excluded':
        lines.push(`生成候補${row.aiReturned ? `${row.aiReturned}件` : ''}はすべて品質チェックなどで除外されました`);
        if (row.reasons.length) lines.push(`主な理由：${row.reasons.join('、')}`);
        break;
      case 'failed':
        lines.push(row.message || '生成に失敗しました');
        if (row.partialCreated) lines.push(`一部作成：${row.partialCreated}件（失敗と併せて確認してください）`);
        if (row.parentUnchecked) lines.push('表示を更新できなかったため、親要因があるかは確認できていません');
        break;
      case 'network':
        lines.push('サーバーに接続できませんでした。生成されたかどうかは分かりません（保存済みの内容を確かめてから、必要なら生成し直してください）');
        break;
      case 'parent-gone':
        lines.push('親要因が見つかりません（削除された可能性があります）');
        if (row.message) lines.push(`サーバーの応答：${row.message}`);
        break;
      case 'analysis-gone':
        lines.push(row.message || '分析が見つかりません（削除された可能性があります）');
        break;
      case 'server-error':
        lines.push(row.errorKind === 'parse'
          ? `サーバーの応答を読み取れませんでした（HTTP ${row.httpStatus || '不明'}）。生成されたかどうかは分かりません`
          : `サーバーでエラーが発生しました（HTTP ${row.httpStatus || '不明'}）${row.message ? `：${row.message}` : ''}`);
        break;
      case 'skipped':
        lines.push(row.message || '送信していません');
        break;
      case 'unknown':
        // An exception of the page's own code (its reason is stored with
        // the row), or a reload while the row was under way.
        lines.push(row.message || '再読み込みの時点で生成中・待機中だったため、結果は確認できていません');
        if (row.observed !== null && row.observed > 0) {
          lines.push(`更新後の表示では、この親の下に新しいAIの要因が${row.observed}件あります（応答では確認できていません）`);
        }
        break;
      default:
        break;
    }
    if (row.parentId !== null && !getNode(app.model, row.parentId) && !['parent-gone', 'waiting', 'running'].includes(row.state)) {
      lines.push('現在はこの親が見つかりません');
    }
    return lines;
  }

  function summary() {
    const totals = { created: 0, failed: 0, excludedCandidates: 0, allExcluded: 0, none: 0, skipped: 0, unknown: 0, done: 0 };
    for (const row of log.rows) {
      if (row.state === 'created') totals.created += row.created;
      if (row.state === 'failed') totals.created += row.partialCreated;
      if (FAILURE_STATES.has(row.state)) totals.failed += 1;
      if (row.state === 'created') totals.excludedCandidates += row.excluded;
      if (row.state === 'all-excluded') {
        totals.allExcluded += 1;
        totals.excludedCandidates += row.aiReturned;
      }
      if (row.state === 'no-candidates') totals.none += 1;
      if (row.state === 'skipped') totals.skipped += 1;
      if (row.state === 'unknown') totals.unknown += 1;
      if (!['waiting', 'running'].includes(row.state)) totals.done += 1;
    }
    return totals;
  }

  function summaryText() {
    const totals = summary();
    const parts = [`作成 ${totals.created}件`];
    if (totals.failed) parts.push(`失敗した親 ${totals.failed}件`);
    if (totals.allExcluded) parts.push(`全候補除外の親 ${totals.allExcluded}件`);
    if (totals.none) parts.push(`候補0件の親 ${totals.none}件`);
    if (totals.unknown) parts.push(`結果不明の親 ${totals.unknown}件`);
    if (totals.skipped) parts.push(`送信しなかった親 ${totals.skipped}件`);
    if (totals.excludedCandidates) parts.push(`品質チェック・重複で除外した候補 ${totals.excludedCandidates}件`);
    return parts.join('・');
  }

  function progressText() {
    const total = log.rows.length;
    const { done } = summary();
    if (restored) {
      return log.status === 'done'
        ? '完了していました。'
        : '再読み込みの時点では完了していませんでした（その後の結果は確認できていません）。';
    }
    if (log.status === 'running') return `進行中：${done}/${total}件の親が終わりました。`;
    if (log.status === 'finishing') return '結果を反映しています。';
    return `完了：${total}件の親（要求ごとの結果は下の一覧）。`;
  }

  function render() {
    document.querySelectorAll('[data-gen-log-slot]').forEach((element) => element.replaceChildren());
    renderBadges();
    if (!log) return;
    const target = slot(log.level);
    if (!target) return;
    const rows = log.rows.map((row) => el('li', {
      class: 'edit-genlog__row',
      'data-gen-row': true,
      'data-parent-id': row.parentId === null ? 'top' : row.parentId,
      'data-category': row.state,
    },
    el('span', { class: 'edit-genlog__badge', 'data-category': row.state }, rowLabel(row)),
    el('span', { class: 'edit-genlog__parent' }, `親：${parentName(row)}`),
    rowDetails(row).length
      ? el('ul', { class: 'edit-genlog__details' }, rowDetails(row).map((line) => el('li', {}, line)))
      : null));
    const notes = [];
    if (restored) {
      notes.push(el('p', { class: 'edit-genlog__restored', 'data-gen-log-restored': true },
        '再読み込み前の結果です。件数は実行時点の値です（現在の要因の状態とは異なることがあります）。'));
    }
    if (log.update === 'failed') {
      notes.push(el('p', { class: 'edit-genlog__note', 'data-gen-log-update': true },
        '生成の後に画面の表示を更新できなかったため、作成された要因の表示と親要因の確認はできていません。ページを再読み込みしてください。'));
    }
    if (log.jsError) {
      notes.push(el('p', { class: 'edit-genlog__note', 'data-gen-log-error': true },
        '画面の処理中にエラーが発生したため、この結果は一部が欠けている可能性があります。'));
    }
    if (log.excludedParents) {
      notes.push(el('p', { class: 'edit-genlog__note' },
        `親子関係に不整合があるYes評価の要因 ${log.excludedParents}件は対象外です（要求を送っていません）。`));
    }
    const section = el('section', {
      class: 'edit-genlog', 'data-gen-log': true, 'data-level': log.level, 'data-kind': log.kind,
      'data-status': restored ? 'restored' : log.status, 'aria-labelledby': 'edit-genlog-title',
    },
    el('div', { class: 'edit-genlog__head' },
      el('h3', { class: 'edit-genlog__title', id: 'edit-genlog-title', tabindex: '-1' }, `生成ログ：${kindLabel(log)}`),
      el('button', {
        type: 'button', class: 'ui-btn ui-btn--sm', 'data-gen-log-close': true,
        disabled: !restored && log.status !== 'done',
      }, '閉じる')),
    el('p', { class: 'edit-genlog__when', 'data-gen-log-when': true },
      `この分析で ${dateTime(log.startedAt)} に実行した生成の結果`),
    ...notes,
    el('p', { class: 'edit-genlog__progress', 'data-gen-log-progress': true }, progressText()),
    el('p', { class: 'edit-genlog__summary', 'data-gen-log-summary': true }, `要約：${summaryText()}`),
    el('ul', { class: 'edit-genlog__rows' }, rows),
    el('p', { class: 'edit-genlog__scope', 'data-gen-log-scope': true },
      'この結果は、このタブで画面を開き直しても残ります（分析ごとに直近の1回分）。保存するのは結果の区分・件数・親のID・理由・時刻だけで、要因の内容や入力中の内容は保存しません。正式な履歴ではありません。「閉じる」で消えます。'),
    stored ? null : el('p', { class: 'edit-genlog__storage', 'data-gen-log-storage': true },
      staleKept
        ? 'ブラウザの保存領域に保存も削除もできなかったため、この画面を開き直すと、この結果は消え、以前の生成の結果が表示されることがあります（その実行時刻で区別できます）。'
        : 'ブラウザの保存領域を使えないため、この画面を開き直すと結果は消えます。'));
    target.replaceChildren(section);
  }

  // Badges next to the parents' group headings (③・④), from the log.
  function renderBadges() {
    document.querySelectorAll('[data-gen-badge]').forEach((badge) => badge.remove());
    if (!log) return;
    for (const row of log.rows) {
      if (row.parentId === null) continue;
      const host = document.querySelector(`[data-gen-host="${row.parentId}"]`);
      if (!host) continue;
      host.append(el('span', {
        class: 'edit-genbadge', 'data-gen-badge': true, 'data-category': row.state,
      }, restored ? `前回：${rowLabel(row)}` : rowLabel(row)));
    }
  }

  return {
    get current() {
      return log;
    },
    get restored() {
      return restored;
    },
    get stored() {
      return stored;
    },
    // A new generation: replaces the log shown and the stored one.
    begin({ level, kind, parents, excludedParents = 0 }) {
      restored = false;
      log = {
        analysisId: app.analysisId,
        tab: tabMark(),
        startedAt: new Date().toISOString(),
        endedAt: null,
        level,
        kind,
        status: 'running',
        excludedParents,
        update: 'pending',
        jsError: false,
        rows: parents.map((parentId) => storedRow({ parentId, state: 'waiting' })),
      };
      save();
      render();
      return log;
    },
    // After a row or the log changed: stored first, then drawn, so a reload
    // finds it even if drawing fails.
    changed() {
      save();
      render();
    },
    summary: () => summary(),
    summaryText: () => summaryText(),
    render,
    renderBadges,
    // A log kept by an earlier page of this tab (plan 5.9.2).
    restore() {
      const key = genlogKey(app.analysisId);
      const raw = sessionStore.getItem(key);
      if (raw === null) {
        stored = sessionStore.available;
        return;
      }
      let value = null;
      try {
        value = validLog(JSON.parse(raw), app.analysisId);
      } catch {
        value = null;
      }
      if (!value) {
        sessionStore.removeItem(key); // broken: dropped, the page goes on
        return;
      }
      const mark = tabMark();
      if (value.tab && mark && value.tab !== mark) {
        // A copy of another tab's storage (e.g. window.open): not this tab's.
        sessionStore.removeItem(key);
        return;
      }
      // Nothing of a generation that was under way comes back but its rows.
      value.rows.forEach((row) => {
        if (row.state === 'waiting' || row.state === 'running') row.state = 'unknown';
      });
      log = value;
      restored = true;
      stored = true;
      render();
    },
    close() {
      log = null;
      restored = false;
      sessionStore.removeItem(genlogKey(app.analysisId));
      render();
    },
  };
}
