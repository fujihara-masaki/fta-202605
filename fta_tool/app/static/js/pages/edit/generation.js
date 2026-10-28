// Generation (PR-6: UI-09・UI-10; J-01〜J-07, J-09, J-16; plan 5.3〜5.6,
// 5.9.1, 5.9.2). Replaces the legacy generation of app.js (and its overlay):
// the normal generation (一次: below the top event; 二次・三次: every
// eligible Yes parent of the level above, one request per parent, each
// naming its parent_id) and the additional generation (一次, or below one
// eligible parent whatever its judgement — Yes, No or 未評価, J-16 — never
// below a 三次要因). Manual add is the dialog of edit/add-dialog.js.
//
// Phases (shared with the save coordinator, common/unsaved.js
// setGenerationPhase; never stored, a reload starts idle):
//   idle → preparing → running → finishing → idle
//   preparing  started by a generation button (all generation buttons off
//              at once). Waits for every save in flight — judgements (a
//              queue of the same factor up to its last wish), the
//              inspector's factor, the top event, the reference information
//              and the analysis title — naming them, and checks how each
//              ended: if any failed, nothing is requested (the reason is
//              shown, the input stays). After 10 s it says that the server
//              may be busy with something else and keeps waiting (10 s is
//              no time limit of the generation). Then the automatic save
//              through the same saveSource() as the save buttons: 一次
//              (normal and additional) — the top event (empty: nothing is
//              generated) and the reference information; 二次・三次 — the
//              reference information only, the saved top event is used
//              (J-09). The inspector's draft is never saved here. The
//              targets are fixed after the waits (a judgement saved
//              meanwhile counts). 生成を取りやめる returns to idle at once
//              and nothing is ever requested by that preparation, whatever
//              its waits do later; it cancels nothing already sent (a save
//              in flight still reaches the server) and never touches a
//              generation started after it.
//   running    the requests, one after the other. Right before each, the
//              parent is checked again against the page's data (still
//              there, eligible — J-25 判断3 — of the right level, and for the
//              normal generation still Yes); a refused parent is not sent.
//              No fallback to a request without parent_id. Each answer is
//              put in the log row of the parent the request named (never
//              the selection) as one of the categories of plan 5.6.
//   finishing  one partial update (also after 0 created or a failure: the
//              page is checked against the server), then the rows are
//              checked against the data it brought (親なし only when the
//              update succeeded and the requested parent is not there; the
//              number of new children under a parent against `created`,
//              which is never replaced), the summary is notified (J-04),
//              and the phase ends — in a finally, whatever happened (an
//              answer, a failure, an exception of the page's own code, a
//              failed update). No time limit of its own: it ends when the
//              update has been applied or has failed (the refresher never
//              waits for anything this phase blocks).
// In every phase but idle the page refuses writes and leaving
// (edit/restrict.js, and each operation's own check), the browser asks
// before leaving (beforeunload), details are not read (edit/factor-editor.js).
// After idle: the restrictions are lifted (not those of a missing analysis
// or of J-25) and the factor shown is read again.
// This holds back operations of this page only: other tabs, other workers
// and direct API calls are not (plan 2.4, 5.3).
//
// Leaving the page during a generation (PR-6 review R7). Once the browser's
// confirmation was accepted, pagehide marks the generation under way as
// left: from then on it sends nothing and records nothing — no further
// request, no automatic save of its preparation, and an answer that still
// arrives is not judged (a request cut off by the leaving is no network
// failure: its result is unknown). Nothing is stopped on the server. A
// reload or a closed tab ends there (the stored rows still under way are
// 結果不明 in the restored log). When the page comes back from the
// back/forward cache (pageshow, persisted), the left generation is ended,
// once, never resumed and never sent again:
//   preparing  it is dropped (nothing was requested), as with 取りやめる;
//   running    its rows are settled — the results received before leaving
//              stay, a parent whose request was sent but not answered is
//              結果不明 (the server may have created factors), a parent not
//              sent yet is 送信していません — and it is finished as usual
//              (one partial update, the rows checked against it, the
//              summary, idle);
//   finishing  its own finishing goes on (its rows were settled before).
// Its continuations that run later (an answer, a wait that ends) find it
// left and do nothing; a generation started after the return is another
// run and never touched by them. Leaving that was cancelled in the
// browser's confirmation is no leaving: the generation simply goes on.

import { el } from '../../common/dom.js';
import { announce, notify } from '../../common/notify.js';
import { normalizeText } from '../../common/text.js';
import {
  getGenerationPhase,
  inFlightSaves,
  isSaving,
  lastFailure,
  saveSource,
  setGenerationPhase,
  SLOW_WAIT_MS,
} from '../../common/unsaved.js';
import { CATEGORY_LABELS } from './genlog.js';
import { refetchAfterGeneration } from './inspector.js';
import { judgementWaits } from './judgement.js';
import { generationTargets, getNode, levelName } from './model.js';
import { checkParent, GONE } from './permissions.js';
import { applyRestrictions } from './restrict.js';

const BUSY = '別の生成の準備中または実行中です。完了までお待ちください。';

const SLOW = 'サーバーが別の処理（生成など）を実行中の可能性があります。保存が終わるまで待ち続けるか、「生成を取りやめる」を選べます（送信した保存は取り消しません）。';
const RESTRICTED = '完了まで保存・評価・追加・削除・出力・画面の移動はできません。入力中の内容は保持されます。';

// ----- one request ------------------------------------------------------------

// The answer of one generation request, told apart as plan 5.6 needs: a
// network failure, HTTP 404 (the analysis), another HTTP error, an answer
// that is not JSON, or the JSON answer.
async function sendRequest(url, body) {
  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    return { kind: 'network', status: 0 };
  }
  let text = '';
  try {
    text = await response.text();
  } catch {
    return { kind: 'network', status: response.status };
  }
  let data = null;
  try {
    data = JSON.parse(text);
  } catch {
    data = null;
  }
  const detail = data && typeof data === 'object' && typeof data.detail === 'string' ? data.detail : '';
  if (response.status === 404) return { kind: 'analysis-gone', status: 404, reason: detail };
  if (!response.ok) return { kind: 'http', status: response.status, reason: detail };
  if (!data || typeof data !== 'object' || Array.isArray(data)) return { kind: 'parse', status: response.status };
  return { kind: 'json', status: response.status, data };
}

function count(value) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : 0;
}

function reasonsOf(summary) {
  const list = summary && Array.isArray(summary.reason_summary) ? summary.reason_summary : [];
  return list.filter((item) => typeof item === 'string');
}

// Plan 5.6: the category of one answer (親なし is decided after the update).
export function classify(row, answer, { parentNamed }) {
  row.httpStatus = answer.status || 0;
  if (answer.kind === 'network') {
    row.state = 'network';
    return;
  }
  if (answer.kind === 'analysis-gone') {
    row.state = 'analysis-gone';
    row.message = answer.reason || '分析が見つかりません（削除された可能性があります）';
    return;
  }
  if (answer.kind === 'http' || answer.kind === 'parse') {
    row.state = 'server-error';
    row.errorKind = answer.kind;
    row.message = answer.reason || '';
    return;
  }
  const data = answer.data;
  const created = count(data.created);
  const summary = data.quality_summary && typeof data.quality_summary === 'object' ? data.quality_summary : {};
  const message = typeof data.message === 'string' ? data.message : '';
  if (data.success === true) {
    if (created > 0) {
      row.state = 'created';
      row.created = created;
      row.excluded = count(data.skipped);
      row.reasons = reasonsOf(summary);
      row.message = message;
    } else if (summary.all_candidates_excluded === true) {
      row.state = 'all-excluded';
      row.aiReturned = count(summary.ai_returned);
      row.reasons = reasonsOf(summary);
      row.message = message;
    } else {
      row.state = 'no-candidates';
      row.message = message;
    }
    return;
  }
  row.state = 'failed';
  row.message = message;
  row.partialCreated = created;
  row.checkParent = parentNamed; // 親なし or 処理失敗: decided by the update
}

// ----- the controller -----------------------------------------------------------

export function createGeneration(app, { step1, title, log }) {
  let current = null; // the generation under way (preparing, running or finishing)
  let sequence = 0;

  const statusBox = document.querySelector('[data-gen-status]');

  function phaseChanged(phase) {
    setGenerationPhase(phase);
    applyRestrictions(app);
  }

  // The status line above the work area (visible on every tab and step).
  function renderStatus(run) {
    if (!statusBox) return;
    if (run && run !== current) return; // a cancelled preparation never draws over a later generation
    const phase = getGenerationPhase();
    if (!run || phase === 'idle') {
      statusBox.hidden = true;
      statusBox.replaceChildren();
      statusBox.dataset.phase = 'idle';
      return;
    }
    statusBox.hidden = false;
    statusBox.dataset.phase = phase;
    const label = run.label;
    const parts = [];
    if (phase === 'preparing') {
      const waiting = run.waiting.length
        ? `${run.waiting.map((name) => `「${name}」`).join('')}の保存が終わるのを待っています。`
        : (run.autoSaving ? `生成前の自動保存：${run.autoSaving}を保存しています。` : '生成の前の確認をしています。');
      parts.push(el('p', { class: 'edit-genstatus__text', 'data-gen-status-text': true },
        el('strong', {}, `生成の準備中（${label}）：`), waiting, '生成はまだ始まっていません。'));
      if (run.slow) parts.push(el('p', { class: 'edit-genstatus__slow', 'data-gen-status-slow': true }, SLOW));
      parts.push(el('div', { class: 'edit-genstatus__actions' },
        el('button', { type: 'button', class: 'ui-btn ui-btn--sm', 'data-gen-cancel': true }, '生成を取りやめる')));
    } else if (phase === 'running') {
      const progress = run.total > 1 ? `${run.index}/${run.total}件目の親` : (run.level === 1 ? '一次要因' : '1件の親');
      parts.push(el('p', { class: 'edit-genstatus__text', 'data-gen-status-text': true },
        el('strong', {}, `生成中（${label}・${progress}）：`), 'サーバーの応答を待っています。', RESTRICTED));
    } else {
      parts.push(el('p', { class: 'edit-genstatus__text', 'data-gen-status-text': true },
        el('strong', {}, `結果を反映しています（${label}）。`), RESTRICTED));
    }
    statusBox.replaceChildren(...parts);
  }

  // A preparation that was cancelled (取りやめる) or whose page was left
  // (R7): nothing more is requested or saved for it.
  function stopped(run) {
    return run.cancelled || run.left;
  }

  function release(run) {
    if (run.slowTimer) window.clearTimeout(run.slowTimer);
    if (current === run) current = null;
  }

  // Back to idle: the restrictions are lifted, held-back partial updates
  // run, and the details held back for the factor shown are read — all of
  // a generation's details after one ran, only those held back when nothing
  // was generated (pendingOnly). Never for a run that is no longer the
  // current one (a cancelled preparation must not touch a later generation).
  function toIdle(run, { pendingOnly }) {
    const mine = current === run || current === null;
    release(run);
    if (!mine) return;
    phaseChanged('idle');
    app.setGenerating(false);
    renderStatus(null);
    try {
      refetchAfterGeneration({ pendingOnly });
    } catch {
      // the inspector shows its own state
    }
  }

  // Back to idle without generating (a failed preparation or 取りやめる; PR-6
  // review R3: the details of a factor chosen meanwhile are read now).
  function stopPreparing(run) {
    toIdle(run, { pendingOnly: true });
  }

  function failPreparing(run, reason, focus = null) {
    stopPreparing(run);
    notify(reason, { type: 'error' });
    if (focus) {
      // The empty top event: ① is opened so its input can be filled in.
      if (focus.closest('[data-step-panel="1"]')) app.setStep(1);
      focus.focus();
    }
  }

  function cancel() {
    const run = current;
    if (!run || getGenerationPhase() !== 'preparing') return;
    run.cancelled = true;
    stopPreparing(run);
    notify('生成を取りやめました。生成の要求は送っていません（送信済みの保存は取り消されません）。', { type: 'info' });
  }

  // Step 1-2 of plan 5.9.1: every save in flight, named, and how it ended.
  async function waitForSaves(run) {
    const failures = new Map();
    for (;;) {
      if (stopped(run)) return null;
      const waits = [...inFlightSaves(), ...judgementWaits(app)];
      if (!waits.length) {
        if (app.writes.inFlight > 0) {
          await app.writes.whenIdle();
          continue;
        }
        await Promise.resolve(); // a write that starts when another ends
        if (!isSaving() && app.writes.inFlight === 0 && !judgementWaits(app).length) break;
        continue;
      }
      run.waiting = [...new Set(waits.map((wait) => wait.label))];
      renderStatus(run);
      const outcomes = await Promise.all(waits.map((wait) => Promise.resolve(wait.promise)
        .catch(() => ({ ok: false, reason: '予期しないエラーが発生しました' }))));
      outcomes.forEach((outcome, index) => {
        const wait = waits[index];
        if (outcome && outcome.ok === false) failures.set(wait.id, `${wait.label}：${outcome.reason || '保存できませんでした'}`);
      });
      await Promise.resolve();
    }
    run.waiting = [];
    return [...failures.values()];
  }

  // The automatic save of ① (one source); null when it was saved or had
  // nothing to save, else the reason.
  async function autoSave(run, source, name) {
    if (stopped(run) || !source.isDirty()) return null;
    run.autoSaving = name;
    renderStatus(run);
    const outcome = await saveSource(source);
    run.autoSaving = null;
    if (stopped(run)) return null;
    if (!outcome.ok) return `${name}の保存に失敗したため、生成を開始しませんでした：${outcome.reason}。入力中の内容は残しています。`;
    notify(`編集中の${name}を保存してから生成します`, { type: 'success' });
    return null;
  }

  // The rows of the generation, fixed after the waits.
  function plan(run) {
    const { kind, level, parentId } = run.request;
    if (level === 1) return { parents: [null], excluded: 0 };
    if (kind === 'additional') {
      const answer = checkParent(app, parentId, level);
      if (!answer.allowed) return { error: answer.reason };
      return { parents: [parentId], excluded: 0 };
    }
    const { targets, excluded } = generationTargets(app.model, level);
    if (!targets.length) {
      return {
        error: excluded.length
          ? `生成できる親要因がありません（Yes評価の${levelName(level - 1)}要因のうち${excluded.length}件は親子関係に不整合があるため対象外です）`
          : `Yes評価の${levelName(level - 1)}要因がないため、生成できません`,
      };
    }
    return { parents: targets.map((node) => node.id), excluded: excluded.length };
  }

  async function prepare(run) {
    const failures = await waitForSaves(run);
    if (failures === null || stopped(run)) return { cancelled: true };
    if (failures.length) {
      return {
        reason: `先に送っていた保存に失敗したため、生成を開始しませんでした（生成の要求は送っていません）：${failures.join('／')}。入力中の内容は残しています。`,
      };
    }
    if (title && title.source.isDirty()) {
      const failure = lastFailure(title.source);
      return { reason: `分析タイトルの保存に失敗したため、生成を開始しませんでした：${failure ? failure.reason : '保存していない変更があります'}` };
    }
    if (app.gone) return { reason: GONE };
    if (step1) {
      if (run.level === 1) {
        if (!normalizeText(step1.fields.top.value)) {
          return { reason: '頂上事象を入力してから生成してください', focus: step1.fields.top };
        }
        const failed = await autoSave(run, step1.topEvent, '頂上事象');
        if (stopped(run)) return { cancelled: true };
        if (failed) return { reason: failed };
      }
      const failed = await autoSave(run, step1.context, '参考情報');
      if (stopped(run)) return { cancelled: true };
      if (failed) return { reason: failed };
    }
    // Saves that started meanwhile (none can, but never generate over one).
    const later = await waitForSaves(run);
    if (later === null || stopped(run)) return { cancelled: true };
    if (later.length) return { reason: `保存に失敗したため、生成を開始しませんでした：${later.join('／')}` };
    if (app.gone) return { reason: GONE };
    const fixed = plan(run);
    if (fixed.error) return { reason: fixed.error };
    return { ok: true, ...fixed };
  }

  // The children of a parent in the data (null: below the top event), to
  // tell the new ones after the update.
  function childIds(model, parentId) {
    return new Set(model.nodes
      .filter((node) => (parentId === null ? node.parentId === null && node.level === 1 : node.parentId === parentId))
      .map((node) => node.id));
  }

  function parentCheckFor(run, parentId) {
    if (parentId === null) return { allowed: true };
    if (app.gone) return { allowed: false, reason: GONE };
    const answer = checkParent(app, parentId, run.level);
    if (!answer.allowed) return answer;
    if (run.request.kind === 'normal') {
      const node = getNode(app.model, parentId);
      if (!node || node.judgement !== 'yes') return { allowed: false, reason: '親要因がYes評価ではなくなったため、送信していません' };
    }
    return { allowed: true };
  }

  async function runRequests(run, entry) {
    const url = `/analyses/${app.analysisId}/generate/level/${run.level}`;
    const rows = entry.rows;
    for (let index = 0; index < rows.length; index += 1) {
      if (run.left) return; // R7: nothing more is sent
      const row = rows[index];
      run.index = index + 1;
      if (run.analysisGone) {
        row.state = 'skipped';
        row.message = '分析が見つからないため送信していません';
        log.changed();
        continue;
      }
      const answer = parentCheckFor(run, row.parentId);
      if (!answer.allowed) {
        row.state = 'skipped';
        row.message = `送信の直前の確認で対象外になったため、送信していません：${answer.reason}`;
        log.changed();
        continue;
      }
      row.state = 'running';
      log.changed();
      renderStatus(run);
      const body = run.request.kind === 'additional' ? { additional: true } : {};
      if (row.parentId !== null) body.parent_id = row.parentId;
      const result = await sendRequest(url, body);
      if (run.left) return; // R7: not judged — the row stays 生成中 until it is settled as 結果不明
      classify(row, result, { parentNamed: row.parentId !== null });
      if (row.state === 'analysis-gone') run.analysisGone = true;
      log.changed();
      const node = row.parentId === null ? null : getNode(app.model, row.parentId);
      announce(`${node ? `親「${node.title}」` : levelName(run.level)}：${row.state === 'created' ? `作成 ${row.created}件` : (CATEGORY_LABELS[row.state] || '送信していません')}`);
    }
  }

  // No row stays 待機中・生成中 once the generation ends (PR-6 review, R4):
  // a row whose request was sent but whose answer was not judged (an
  // exception of the page's own code) is 結果不明 — the server may have
  // created factors — and a row never sent is 送信していません. Rows with a
  // result keep it. R7: the same when the page was left and came back.
  function settleRows(entry, { left = false } = {}) {
    for (const row of entry.rows) {
      if (row.state === 'running') {
        row.state = 'unknown';
        if (left) {
          row.message = 'ページを離れたため、この親の結果を確認できていません（要求は送信済みで、サーバーで作成された可能性があります。保存済みの内容を確かめてください）';
        } else {
          row.message = entry.jsError
            ? '画面の処理中にエラーが発生したため、この親の結果を確認できていません（要求は送信済みで、サーバーで作成された可能性があります。保存済みの内容を確かめてください）'
            : 'この親の結果を確認できていません（要求は送信済みです）';
        }
      } else if (row.state === 'waiting') {
        row.state = 'skipped';
        if (left) {
          row.message = 'ページを離れたため送信していません（戻った後も自動では送信しません）';
        } else {
          row.message = entry.jsError
            ? '画面の処理中にエラーが発生したため、送信していません'
            : '送信していません';
        }
      }
    }
  }

  // After the update: what the data it brought says about each row.
  function checkRows(run, entry, applied) {
    entry.update = applied ? 'applied' : 'failed';
    for (const row of entry.rows) {
      if (!applied) {
        if (row.state === 'failed' && row.checkParent) row.parentUnchecked = true;
        continue;
      }
      const parentThere = row.parentId === null || Boolean(getNode(app.model, row.parentId));
      if (row.state === 'failed' && row.checkParent && !parentThere) {
        row.state = 'parent-gone';
        continue;
      }
      if ((row.state === 'created' || row.state === 'unknown') && parentThere) {
        const before = run.snapshot.get(row.parentId === null ? 'top' : row.parentId) || new Set();
        const fresh = app.model.nodes.filter((node) => node.ai && !before.has(node.id)
          && (row.parentId === null ? node.parentId === null && node.level === 1 : node.parentId === row.parentId));
        row.observed = fresh.length;
        row.warnings = fresh.filter((node) => node.warning).length;
      }
    }
  }

  // J-04: the summary, as a warning when something failed beside created
  // factors. Rows whose result is unknown (R4) are never told as success or
  // as 候補0件.
  function notifySummary(run, entry) {
    const totals = log.summary();
    const label = run.label;
    const failed = totals.failed;
    const unknown = totals.unknown;
    const many = entry.rows.length > 1;
    if (totals.created > 0 && unknown > 0) {
      notify(`${label}：${totals.created}件作成しました。${failed ? `${failed}件の親で失敗し、` : ''}`
        + `${unknown}件の親は結果を確認できていません（詳細は生成ログ）`, { type: 'warning' });
    } else if (totals.created > 0 && failed > 0) {
      notify(many
        ? `${label}：${totals.created}件作成、${failed}件の親で失敗しました（詳細は生成ログ）`
        : `${label}：${totals.created}件作成しましたが、失敗もありました（詳細は生成ログ）`, { type: 'warning' });
    } else if (totals.created > 0) {
      const note = totals.excludedCandidates ? `（うち候補${totals.excludedCandidates}件は品質チェック・重複で除外）` : '';
      notify(`${label}：${totals.created}件作成しました${note}`, { type: 'success' });
    } else if (unknown > 0) {
      notify(`${label}：作成を確認できませんでした（${failed ? `${failed}件の親で失敗、` : ''}`
        + `${unknown}件の親は結果不明。詳細は生成ログ）`, { type: 'error' });
    } else if (failed > 0) {
      notify(`${label}：作成できませんでした（${many ? `${failed}件の親で失敗。` : ''}詳細は生成ログ）`, { type: 'error' });
    } else if (totals.allExcluded > 0) {
      const reasons = [...new Set(entry.rows.flatMap((row) => (row.state === 'all-excluded' ? row.reasons : [])))];
      notify(`${label}：生成候補はすべて品質チェックなどで除外されました${reasons.length ? `（主な理由：${reasons.join('、')}）` : ''}`, { type: 'warning' });
    } else if (totals.skipped > 0 && totals.none === 0) {
      notify(`${label}：送信できる親がなかったため、生成していません（詳細は生成ログ）`, { type: 'warning' });
    } else {
      notify(`${label}：生成候補がありませんでした（LLMが要因を返しませんでした）`, { type: 'warning' });
    }
  }

  // left: the page was left while the requests ran and has come back (R7).
  async function finish(run, entry, { left = false } = {}) {
    settleRows(entry, { left }); // before anything is drawn (drawing may fail too)
    try {
      phaseChanged('finishing');
      entry.status = 'finishing';
      log.changed();
      renderStatus(run);
      app.setGenerating(false); // the partial update held back during the requests runs now
      const mark = app.refreshMark();
      app.refresh({});
      await app.whenRefreshed(); // until it has been applied or has failed
      const outcome = app.lastRefresh();
      const applied = Boolean(outcome) && outcome.seq > mark && outcome.kind === 'applied';
      checkRows(run, entry, applied);
      entry.status = 'done';
      entry.endedAt = new Date().toISOString();
      log.changed();
      notifySummary(run, entry);
      if (left) {
        notify('ページを離れる前に実行中だった生成を終了しました。戻った後に生成の要求を送り直してはいません'
          + '（サーバーでの処理は止めていません）。結果は生成ログで確かめてください。', { type: 'info' });
      }
      if (entry.jsError) notify('生成の処理中に画面のエラーが発生しました。生成ログの内容が一部欠けている可能性があります。', { type: 'error' });
    } catch {
      entry.jsError = true;
      entry.status = 'done';
      if (!entry.endedAt) entry.endedAt = new Date().toISOString();
      try {
        log.changed(); // stored first: a reload shows the settled rows
      } catch {
        // the log could not be drawn; it was stored if the storage works
      }
      notify('生成の結果を反映する処理でエラーが発生しました。ページを再読み込みしてください。', { type: 'error' });
    } finally {
      toIdle(run, { pendingOnly: false });
    }
  }

  async function execute(run, prepared) {
    phaseChanged('running');
    let entry = null;
    try {
      run.total = prepared.parents.length;
      run.index = 0;
      run.snapshot = new Map(prepared.parents.map((parentId) => [
        parentId === null ? 'top' : parentId, childIds(app.model, parentId)]));
      run.logBegun = true;
      entry = log.begin({
        level: run.level, kind: run.request.kind, parents: prepared.parents, excludedParents: prepared.excluded,
      });
      run.entry = entry;
      renderStatus(run);
      const scope = run.request.kind === 'normal' && run.level > 1
        ? `対象の親 ${run.total}件（Yesの${levelName(run.level - 1)}要因すべて。絞り込みで表示していない要因も含みます）`
          + (prepared.excluded ? `。親子関係に不整合があるため対象外：${prepared.excluded}件` : '')
        : (run.request.parentId ? `親「${getNode(app.model, run.request.parentId)?.title || `ID ${run.request.parentId}`}」` : '頂上事象の下');
      notify(`${run.label}を開始しました：${scope}`, { type: 'info' });
      await runRequests(run, entry);
    } catch {
      if (entry) entry.jsError = true;
    } finally {
      if (run.left) {
        // R7: the page was left. Nothing more is done here: a page that
        // comes back ends this generation itself (restored()), a page
        // that does not come back is gone.
      } else if (entry) {
        await finish(run, entry);
      } else {
        // An exception before the log began (or while it began): nothing
        // was sent. A log that was begun and stored for it is dropped, so a
        // reload never shows rows that were never sent.
        if (run.logBegun) {
          try {
            log.close();
          } catch {
            // the storage was cleared first (genlog.js close)
          }
        }
        toIdle(run, { pendingOnly: true });
        notify('生成を開始できませんでした（画面の処理でエラーが発生しました。生成の要求は送っていません）。', { type: 'error' });
      }
    }
  }

  // request: { kind: 'normal' | 'additional', level, parentId }
  async function start(request) {
    if (app.gone) {
      notify(GONE, { type: 'error' });
      return;
    }
    if (getGenerationPhase() !== 'idle' || current) {
      notify(BUSY, { type: 'warning' });
      return;
    }
    const level = Number(request.level);
    const parentId = request.parentId === null || request.parentId === undefined || request.parentId === ''
      ? null : Number(request.parentId);
    if (![1, 2, 3].includes(level)) return;
    const kind = request.kind === 'additional' ? 'additional' : 'normal';
    if (level > 1 && kind === 'additional') {
      // A 二次・三次 additional generation always names its parent.
      if (parentId === null) {
        notify('親要因が指定されていないため、追加生成できません', { type: 'error' });
        return;
      }
      const answer = checkParent(app, parentId, level);
      if (!answer.allowed) {
        notify(answer.reason, { type: 'error' });
        return;
      }
    }
    if (level > 1 && kind === 'normal' && !judgementWaits(app).length) {
      const { targets, excluded } = generationTargets(app.model, level);
      if (!targets.length) {
        notify(excluded.length
          ? `生成できる親要因がありません（Yes評価の${levelName(level - 1)}要因のうち${excluded.length}件は親子関係に不整合があるため対象外です）`
          : `Yes評価の${levelName(level - 1)}要因がないため、生成できません`, { type: 'error' });
        return;
      }
    }
    sequence += 1;
    const parent = parentId === null ? null : getNode(app.model, parentId);
    const run = {
      id: sequence,
      request: { kind, level, parentId: level === 1 ? null : parentId },
      level,
      label: `${levelName(level)}要因の${kind === 'additional' ? '追加生成' : '通常生成'}${parent && kind === 'additional' ? `（親：「${parent.title}」）` : ''}`,
      cancelled: false,
      waiting: [],
      autoSaving: null,
      slow: false,
      slowTimer: null,
      left: false, // the page was left meanwhile (R7)
      entry: null, // its log entry, once the requests began
      restoring: false, // ended after the return from the back/forward cache (R7)
    };
    current = run;
    phaseChanged('preparing');
    app.setGenerating(true);
    renderStatus(run);
    run.slowTimer = window.setTimeout(() => {
      if (current !== run || getGenerationPhase() !== 'preparing') return;
      run.slow = true;
      renderStatus(run);
    }, SLOW_WAIT_MS);

    let prepared;
    try {
      prepared = await prepare(run);
    } catch {
      prepared = { reason: '生成の準備中にエラーが発生したため、生成を開始しませんでした' };
    }
    // 取りやめた: idle already (and maybe another generation since) — nothing more.
    // The page was left (R7): it is dropped when the page comes back.
    if (stopped(run) || current !== run) return;
    if (run.slowTimer) window.clearTimeout(run.slowTimer);
    if (!prepared.ok) {
      failPreparing(run, prepared.reason, prepared.focus || null);
      return;
    }
    await execute(run, prepared);
  }

  // R7: the page is left (after the browser's confirmation, if any).
  function left() {
    if (current) current.left = true;
  }

  // R7: the page came back from the back/forward cache. The generation that
  // was under way when it was left is ended here, once (current is cleared
  // by its idle; a repeated pageshow finds nothing).
  function restored() {
    const run = current;
    if (!run || !run.left || run.restoring) return;
    run.restoring = true;
    const phase = getGenerationPhase();
    if (phase === 'finishing') return; // its own finishing goes on (settled already)
    if (phase === 'running' && run.entry) {
      finish(run, run.entry, { left: true });
      return;
    }
    // Still preparing: nothing was requested.
    run.cancelled = true;
    stopPreparing(run);
    notify('ページを離れたため、生成の準備を取りやめました。生成の要求は送っていません'
      + '（送信済みの保存は取り消されません）。', { type: 'info' });
  }

  window.addEventListener('pagehide', left);
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) restored();
  });

  if (statusBox) {
    statusBox.addEventListener('click', (event) => {
      const button = event.target instanceof Element ? event.target.closest('[data-gen-cancel]') : null;
      if (button) cancel();
    });
  }

  return {
    start,
    cancel,
    get running() {
      return current;
    },
  };
}
