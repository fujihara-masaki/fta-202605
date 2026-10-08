// Unsaved-change protection and the save coordinator (J-12, plan 5.1,
// 5.9.3). PR-4 completes the contract; PR-5 uses the same functions for the
// inspector and does not build another coordinator.
//
// A screen registers "save sources" (inputs that can be saved together):
//   registerSource({
//     id, order (SOURCE_ORDER), label (string | () => string),
//     target: { analysisId, nodeId? }   fixed when editing starts: the
//                                       registry keeps a frozen copy and
//                                       every save goes there, whatever is
//                                       selected later (plan 5.2)
//     isDirty()                         same normalisation as saving
//                                       (text.js normalizeText), so typing and
//                                       restoring the original is not unsaved
//     validate()?   -> reason | null    checked before anything is sent
//     save(target)? -> Promise<{ ok, reason?, status?, gone?, notSent? }>
//                                       one call of the existing API; `gone`
//                                       ('analysis' | 'node') when the target
//                                       no longer exists (HTTP 404), `notSent`
//                                       when nothing was sent (e.g. the page
//                                       already knows the analysis is gone)
//     commit(outcome)?                  update the saved value after a
//                                       success: the value that was sent (or
//                                       what the server returned), never what
//                                       was typed after sending
//     draftKey()?                       the current input as a string, so a
//                                       failed save is not sent again unchanged
//     discard()                         drop the input (破棄して移動)
//     leave: 'ask' (default) | 'auto'   'auto' is saved without asking before
//                                       a page is left (the header title):
//                                       it never joins the three choices
//     onLeaveBlocked(reason)?           an 'auto' source could not be saved:
//                                       show the reason at the input
//     prompt?                           discard-only sources (no save), see below
//   })   -> unregister()
//
// saveSource(source) is the one way to save a source: the save button, the
// automatic save before a generation and 保存して移動 all go through it, so
// they share the in-flight tracking, the saved value and the result. A
// second call while one is in flight waits for it and sends again only if
// the input is still unsaved.
//
// Leaving the page (in-page link) or another transition (requestLeave /
// requestTransition):
//   1. refused while a generation is prepared, runs or is being finished
//      (setGenerationPhase; J-01) — the input stays;
//   2. saves in flight are awaited (after 10 s the dialog says that the
//      server may be busy with something else; requests are never cancelled);
//      after every wait the generation state and the saves in flight are
//      checked again, and again right before discarding, saving or leaving
//      (a generation started meanwhile saves ① itself: nothing is then
//      asked, discarded or left);
//   3. 'auto' sources are saved; one that fails or is invalid stops the move
//      and shows its reason (no dialog);
//   4. other unsaved sources: 保存して移動 / 破棄して移動 / 編集を続ける.
//      保存して移動 validates every source first (nothing is sent if one is
//      invalid), then saves them one by one in `order` (要因 → 頂上事象 →
//      参考情報 → 一覧の改名); a failure does not stop the other sources.
//      Each source is shown as 保存済み / 失敗：理由 / 未送信：理由. The page
//      moves only when all were saved; 再試行 sends the failed and unsent
//      sources only; after a partial success 破棄して移動 says that the saved
//      ones stay saved and only the failed input is dropped.
//      編集を続ける and Esc close the dialog and give the focus back.
// Download links (download attribute) are never intercepted.
// Browser navigation (reload, back, closing the tab) gets the browser's own
// confirmation via beforeunload, registered only while something is unsaved
// or being saved, so back/forward caching is not blocked otherwise. The
// three choices cannot be offered there. Drafts are never stored in the
// browser, so nothing is recovered after a crash.
//
// A source that cannot be saved from the dialog leaves out save() (the
// new-analysis form: saved only by its own 作成して編集へ). While such a
// source has unsaved input the dialog offers only 続ける / 破棄して移動,
// worded by the source's optional `prompt`: { title, lead, note, continueLabel }.
// holdNavigation(message): while the page's own navigation is under way (a
// form POST already sent), in-page links are held and `message` is shown.

import { el } from './dom.js';
import { openDialog } from './dialog.js';
import { notify } from './notify.js';

export const SOURCE_ORDER = {
  factor: 10,
  topEvent: 20,
  context: 30,
  listRename: 40,
};

export const GENERATION_PHASES = ['idle', 'preparing', 'running', 'finishing'];
export const SLOW_WAIT_MS = 10000;
export const GENERATING_REASON = '生成の準備中・生成中・結果の反映中は保存できません。生成が終わるまでお待ちください（入力中の内容は保持されています）。';
const SAVING_REASON = '送信中の保存があります。保存が終わってから選んでください（送信した保存は取り消しません）。';
const UNEXPECTED_REASON = '保存中に予期しないエラーが発生しました';
const SLOW_MESSAGE = 'サーバーが別の処理（生成など）を実行中の可能性があります。保存が終わるまで待っています（送信した保存は取り消しません）。';

const sources = new Map();
const states = new WeakMap(); // source -> { target, promise, lastFailure }
const listeners = new Set();
let beforeUnloadRegistered = false;
let guardActive = false;
let linkGuardInstalled = false;
let navigationHold = null;
let generationPhase = 'idle';
let leavingPage = false;

function attempt(fn, fallback) {
  try {
    return fn();
  } catch {
    return fallback;
  }
}

function stateOf(source) {
  let state = states.get(source);
  if (!state) {
    state = { target: Object.freeze({ ...(source.target || {}) }), promise: null, lastFailure: null };
    states.set(source, state);
  }
  return state;
}

export function labelOf(source) {
  return typeof source.label === 'function' ? attempt(() => source.label(), source.id) : source.label;
}

function byOrder(a, b) {
  return (a.order ?? 100) - (b.order ?? 100);
}

function isAuto(source) {
  return source.leave === 'auto';
}

function keyOf(source) {
  return typeof source.draftKey === 'function' ? attempt(() => String(source.draftKey()), null) : null;
}

export function registerSource(source) {
  stateOf(source); // the target is fixed now
  sources.set(source.id, source);
  refresh();
  return () => {
    if (sources.get(source.id) === source) sources.delete(source.id);
    refresh();
  };
}

export function getSource(id) {
  return sources.get(id) || null;
}

// The target the source was registered with (frozen).
export function targetOf(source) {
  return stateOf(source).target;
}

export function lastFailure(source) {
  return stateOf(source).lastFailure;
}

export function dirtySources() {
  return [...sources.values()].filter((source) => attempt(() => source.isDirty(), false)).sort(byOrder);
}

export function hasUnsaved() {
  return dirtySources().length > 0;
}

export function isSourceSaving(source) {
  return Boolean(stateOf(source).promise) || attempt(() => Boolean(source.isSaving?.()), false);
}

export function isSaving() {
  return [...sources.values()].some(isSourceSaving);
}

// Called whenever a source's input or save state changes (`fn()`).
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function onBeforeUnload(event) {
  if (!hasUnsaved() && !isSaving()) return undefined;
  event.preventDefault();
  // Legacy browsers need returnValue set to show the prompt.
  event.returnValue = '';
  return '';
}

// Call after any input / save state change of a source.
export function refresh() {
  const needed = hasUnsaved() || isSaving();
  if (needed && !beforeUnloadRegistered) {
    window.addEventListener('beforeunload', onBeforeUnload);
    beforeUnloadRegistered = true;
  } else if (!needed && beforeUnloadRegistered) {
    window.removeEventListener('beforeunload', onBeforeUnload);
    beforeUnloadRegistered = false;
  }
  listeners.forEach((fn) => attempt(fn, null));
}

// ----- generation state (J-01, plan 5.9.1) ----------------------------------
// Set by the edit screen for the whole generation: preparing (waiting for
// saves, the automatic save), running (the requests), finishing (showing the
// result). Leaving with 保存して移動 is refused in every phase but idle.

export function setGenerationPhase(phase) {
  generationPhase = GENERATION_PHASES.includes(phase) ? phase : 'idle';
  refresh();
}

export function getGenerationPhase() {
  return generationPhase;
}

// ----- saving one source ---------------------------------------------------

function normalizeOutcome(outcome) {
  if (!outcome || typeof outcome !== 'object') return { ok: false, reason: '保存できませんでした' };
  if (outcome.ok) return { ...outcome, ok: true };
  return { ...outcome, ok: false, reason: outcome.reason || '保存できませんでした' };
}

/**
 * Save one source through its own save(): the save button, the automatic
 * save before a generation and 保存して移動 use this alone.
 * @returns {Promise<{ok: boolean, reason?: string, skipped?: boolean, invalid?: boolean,
 *   status?: number, gone?: string, notSent?: boolean}>}
 */
export async function saveSource(source) {
  const state = stateOf(source);
  while (state.promise) {
    // One at a time per source; then only if still unsaved.
    await state.promise.catch(() => null);
  }
  if (!attempt(() => source.isDirty(), false)) return { ok: true, skipped: true };
  if (typeof source.save !== 'function') return { ok: false, reason: 'この入力はここでは保存できません', notSent: true };
  const invalid = attempt(() => source.validate?.() || null, null);
  if (invalid) {
    state.lastFailure = { reason: invalid, key: keyOf(source), invalid: true };
    refresh();
    return { ok: false, reason: invalid, invalid: true, notSent: true };
  }
  const key = keyOf(source);
  // Set before the first await, so a click right after a blur sees it.
  state.promise = (async () => {
    let outcome;
    try {
      outcome = normalizeOutcome(await source.save(state.target));
    } catch {
      outcome = { ok: false, reason: UNEXPECTED_REASON };
    }
    if (outcome.ok) {
      state.lastFailure = null;
      attempt(() => source.commit?.(outcome), null);
    } else {
      state.lastFailure = { reason: outcome.reason, key, notSent: Boolean(outcome.notSent) };
    }
    return outcome;
  })();
  refresh();
  try {
    return await state.promise;
  } finally {
    state.promise = null;
    refresh();
  }
}

// Every save in flight (including sources that track their own saves).
export function whenAllIdle() {
  const pending = [...sources.values()].filter(isSourceSaving).map((source) => {
    const state = stateOf(source);
    return Promise.resolve(state.promise || attempt(() => source.whenIdle?.(), null)).catch(() => null);
  });
  return Promise.all(pending).then(() => (isSaving() ? whenAllIdle() : undefined));
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

// Wait for `promise`; after 300 ms a dialog says what is awaited, after 10 s
// that the server may be busy. 編集を続ける stops waiting (the request is
// not cancelled: the server may still apply it). Resolves to
// { done: true, value } or { done: false }.
async function waitFor(promise, invoker, { title, lead }) {
  const finished = Promise.resolve(promise).then((value) => ({ done: true, value }));
  const quick = await Promise.race([finished, delay(300).then(() => null)]);
  if (quick) return quick;

  const dialog = openDialog({
    title,
    body: [lead],
    actions: [{ id: 'continue', label: '編集を続ける', autofocus: true }],
    invoker,
    cancelAction: 'continue',
  });
  dialog.setStatus('保存しています…');
  const slowTimer = window.setTimeout(() => {
    if (dialog.isOpen()) dialog.setStatus(SLOW_MESSAGE);
  }, SLOW_WAIT_MS);
  const outcome = await Promise.race([finished, dialog.result.then(() => ({ done: false }))]);
  window.clearTimeout(slowTimer);
  if (outcome.done) dialog.close('idle', { restoreFocus: false });
  return outcome;
}

function waitUntilIdle(invoker) {
  return waitFor(whenAllIdle(), invoker, {
    title: '保存の完了を待っています',
    lead: '送信中の保存が終わってから移動します。',
  }).then((outcome) => outcome.done);
}

// What must not happen now: a generation is prepared, runs or is finished
// (J-01), or a save is in flight — discarding or leaving would contradict a
// request already sent (e.g. the reference information a generation that
// started meanwhile is saving). Checked again after every wait and right
// before discarding, saving or leaving.
function blockedReason() {
  if (generationPhase !== 'idle') return GENERATING_REASON;
  if (isSaving()) return SAVING_REASON;
  return null;
}

// ----- 保存して移動 ----------------------------------------------------------

const RESULT_TEXT = {
  saved: () => '保存済み',
  failed: (reason) => `失敗：${reason}`,
  unsent: (reason) => `未送信：${reason}`,
};

function goneKey(source, gone) {
  const target = targetOf(source);
  if (gone === 'node' && target.nodeId !== undefined && target.nodeId !== null) return `node:${target.nodeId}`;
  return `analysis:${target.analysisId}`;
}

function isGone(source, goneKeys) {
  const target = targetOf(source);
  return goneKeys.has(`analysis:${target.analysisId}`)
    || (target.nodeId !== undefined && target.nodeId !== null && goneKeys.has(`node:${target.nodeId}`));
}

function resultsBox(results, { partial }) {
  const failed = [...results.values()].some((entry) => entry.state !== 'saved');
  const items = [...results.entries()].map(([source, entry]) => el('li', {
    'data-save-result': entry.state,
    'data-source-id': source.id,
  }, `${labelOf(source)}：${RESULT_TEXT[entry.state](entry.reason)}`));
  return el('div', { 'data-save-results': true },
    el('p', {}, failed ? '保存できなかった変更があるため、移動していません。' : 'すべて保存しました。'),
    el('ul', {}, items),
    partial
      ? el('p', { 'data-partial-note': true },
        '保存済みの項目は取り消されません。「破棄して移動」を選ぶと、失敗した項目（未送信を含む）の入力だけが破棄されます。')
      : null);
}

async function saveAll(dialog, results) {
  if (generationPhase !== 'idle') {
    dialog.setError(GENERATING_REASON);
    return;
  }
  if (isSaving()) {
    dialog.setBusy(true, '送信中の保存の完了を待っています…');
    const slowTimer = window.setTimeout(() => {
      if (dialog.isOpen()) dialog.setStatus(SLOW_MESSAGE);
    }, SLOW_WAIT_MS);
    await whenAllIdle();
    window.clearTimeout(slowTimer);
    if (!dialog.isOpen()) return;
    dialog.setBusy(false);
    if (generationPhase !== 'idle') {
      dialog.setError(GENERATING_REASON);
      return;
    }
  }
  const targets = dirtySources().filter((source) => !isAuto(source) && typeof source.save === 'function');
  const invalid = targets
    .map((source) => [source, attempt(() => source.validate?.() || null, null)])
    .filter(([, reason]) => reason);
  if (invalid.length) {
    dialog.setError([
      '入力に不備があるため保存していません（何も送信していません）。',
      ...invalid.map(([source, reason]) => `${labelOf(source)}：${reason}`),
    ]);
    return;
  }

  dialog.setError(null);
  dialog.setBusy(true, '保存しています…');
  const goneKeys = new Set();
  for (const source of targets) {
    if (!dialog.isOpen()) return;
    if (isGone(source, goneKeys)) {
      results.set(source, { state: 'unsent', reason: '保存先が見つからないため送信していません' });
      continue;
    }
    const outcome = await saveSource(source);
    if (outcome.ok) {
      results.set(source, { state: 'saved' });
    } else {
      results.set(source, { state: outcome.notSent ? 'unsent' : 'failed', reason: outcome.reason });
      if (outcome.gone) goneKeys.add(goneKey(source, outcome.gone));
    }
  }
  if (!dialog.isOpen()) return;
  dialog.setBusy(false);

  const unsaved = [...results.values()].filter((entry) => entry.state !== 'saved');
  if (!unsaved.length && !hasUnsavedToAsk() && !blockedReason()) {
    dialog.close('saved', { restoreFocus: false });
    return;
  }
  const partial = [...results.values()].some((entry) => entry.state === 'saved');
  dialog.setError(resultsBox(results, { partial }));
  const retry = dialog.button('save');
  if (retry) {
    retry.textContent = '再試行';
    retry.focus();
  }
}

function hasUnsavedToAsk() {
  return dirtySources().some((source) => !isAuto(source));
}

function pendingList(pending) {
  return el('ul', { class: 'ui-dialog__list' }, pending.map((source) => el('li', {}, labelOf(source))));
}

// The sources the dialog listed ('auto' ones are never listed: they were
// saved before leaving, and a factor switch leaves them as they are).
function discardAll() {
  dirtySources().filter((source) => !isAuto(source)).forEach((source) => attempt(() => source.discard(), null));
  refresh();
}

// Two choices only, for input that this dialog cannot save (J-12: the
// new-analysis form is saved by its own button, so no 保存して移動).
function askToDiscard(invoker, pending, prompt = {}) {
  const dialog = openDialog({
    title: prompt.title || '保存していない入力があります',
    body: [
      prompt.lead || '次の入力はまだ保存されていません。',
      pendingList(pending),
      prompt.note || '移動すると、入力した内容は失われます。',
    ],
    actions: [
      { id: 'continue', label: prompt.continueLabel || '入力を続ける', autofocus: true },
      { id: 'discard', label: '破棄して移動', variant: 'danger-outline' },
    ],
    invoker,
    cancelAction: 'continue',
    onAction: (actionId, controller) => {
      if (actionId === 'discard') {
        const blocked = blockedReason();
        if (blocked) {
          controller.setError(blocked);
          return;
        }
        discardAll();
        controller.close('discarded', { restoreFocus: false });
      } else {
        controller.close('continue');
      }
    },
  });
  return dialog.result;
}

function askAboutUnsaved(invoker, { note = null } = {}) {
  const pending = dirtySources().filter((source) => !isAuto(source));
  const unsavable = pending.find((source) => typeof source.save !== 'function');
  if (unsavable) return askToDiscard(invoker, pending, unsavable.prompt);
  const results = new Map();
  const dialog = openDialog({
    title: '保存していない変更があります',
    body: [
      '次の変更はまだ保存されていません。',
      pendingList(pending),
      '保存してから移動するか、変更を破棄して移動するかを選んでください。',
      note,
    ],
    actions: [
      { id: 'continue', label: '編集を続ける', autofocus: true },
      { id: 'discard', label: '破棄して移動', variant: 'danger-outline' },
      { id: 'save', label: '保存して移動', variant: 'primary' },
    ],
    invoker,
    cancelAction: 'continue',
    onAction: (actionId, controller) => {
      if (actionId === 'continue') {
        controller.close('continue');
      } else if (actionId === 'discard') {
        const blocked = blockedReason();
        if (blocked) {
          controller.setError(blocked);
          return;
        }
        discardAll();
        controller.close('discarded', { restoreFocus: false });
      } else if (actionId === 'save') {
        saveAll(controller, results);
      }
    },
  });
  return dialog.result;
}

// 'auto' sources (the header title) are saved before leaving, without a
// dialog; a failure stops the move and its reason is shown at the input.
async function saveAutoSources(invoker) {
  for (const source of dirtySources().filter(isAuto)) {
    const state = stateOf(source);
    const failure = state.lastFailure;
    let reason = null;
    if (failure && !failure.invalid && failure.key !== null && failure.key === keyOf(source)) {
      reason = failure.reason; // the same input failed already: not sent again
    } else {
      const outcome = await waitFor(saveSource(source), invoker, {
        title: '保存の完了を待っています',
        lead: `${labelOf(source)}を保存してから移動します。`,
      });
      if (!outcome.done) return false;
      if (!outcome.value.ok) reason = outcome.value.reason;
    }
    if (reason) {
      attempt(() => source.onLeaveBlocked?.(reason), null);
      notify(`${labelOf(source)}を保存できなかったため、移動していません：${reason}`, { type: 'error' });
      return false;
    }
  }
  return true;
}

function refusedWhileGenerating() {
  if (generationPhase === 'idle') return false;
  notify(GENERATING_REASON, { type: 'warning' });
  return true;
}

// The state is checked again after every wait: a generation can start
// while a save is awaited (its preparation then saves ① itself), and a save
// can start meanwhile. Nothing is asked, discarded, saved or left while
// either holds.
async function runGuarded({ invoker, proceed }) {
  if (guardActive) return false;
  if (refusedWhileGenerating()) return false;
  guardActive = true;
  try {
    for (;;) {
      if (isSaving() && !(await waitUntilIdle(invoker))) return false;
      if (refusedWhileGenerating()) return false;
      if (!(await saveAutoSources(invoker))) return false;
      if (refusedWhileGenerating()) return false;
      if (!isSaving()) break;
    }
    if (hasUnsavedToAsk()) {
      const choice = await askAboutUnsaved(invoker);
      if (choice !== 'saved' && choice !== 'discarded') return false;
    }
    const blocked = blockedReason();
    if (blocked) {
      notify(`移動していません：${blocked}`, { type: 'warning' });
      return false;
    }
    refresh();
    proceed();
    return true;
  } finally {
    guardActive = false;
  }
}

// Leave the page (in-page link) with the unsaved-change check.
export function requestLeave(href, { invoker = null } = {}) {
  return runGuarded({
    invoker,
    proceed: () => {
      leavingPage = true;
      window.location.assign(href);
    },
  });
}

// True once the page is being left after the check (PR-5: a partial update
// asked for by a save of 保存して移動 must not reload the page then).
export function isLeavingPage() {
  return leavingPage;
}

// Any other transition that would drop the current input (e.g. opening the
// rename of another row): same three choices, then `proceed`.
export function requestTransition({ invoker = null, proceed }) {
  return runGuarded({ invoker, proceed });
}

// ----- switching the inspector's factor (R-01; PR-5) -------------------------
//
// requestSwitch({ source, invoker, proceed }) — `source` is the factor source
// of the inspector now (null while its details load or failed to load: there
// is no draft yet). Only that draft decides whether to ask: unsaved input of
// ① or the header title stays as it is and the factor is switched.
// The state is judged again after every wait and before discarding or
// proceeding (a generation can start, a save can end meanwhile):
//   - its save in flight: awaited (the dialog after 300 ms, the reason after
//     10 s; the request is never cancelled), then judged again;
//   - unchanged: switched at once (also while a generation runs: browsing is
//     never refused);
//   - changed, no generation: the same three choices as leaving the page,
//     listing every unsaved source (要因 → 頂上事象 → 参考情報; plan 5.9.3 and
//     the design record: 保存して移動 saves the factor and ①);
//   - changed while a generation is prepared, runs or is finished (J-01, the
//     part moved forward to PR-5): 編集を続ける / 破棄して移動 only, nothing is
//     sent; 破棄して移動 drops the inspector's change alone (①, the reference
//     information and the title stay). Once idle again, the three choices.
// 編集を続ける and Esc keep everything (proceed is not called) and give the
// focus back to `invoker`.

const SWITCH_NOTE = '「破棄して移動」を選ぶと、上の一覧のすべての変更が破棄されます。';
const GENERATING_SWITCH = '生成中は保存できません。生成が終わると保存できます。';

function isCurrent(source) {
  return Boolean(source) && sources.get(source.id) === source;
}

function askWhileGenerating(invoker, source) {
  const dialog = openDialog({
    title: '保存していない変更があります',
    body: [
      '次の変更はまだ保存されていません。',
      pendingList([source]),
      el('p', { 'data-generating-reason': true }, GENERATING_SWITCH),
      '「破棄して移動」を選ぶと、この要因の変更だけが破棄されます（頂上事象・参考情報・分析タイトルの入力は保持されます）。',
    ],
    actions: [
      { id: 'continue', label: '編集を続ける', autofocus: true },
      { id: 'discard', label: '破棄して移動', variant: 'danger-outline' },
    ],
    invoker,
    cancelAction: 'continue',
    onAction: (actionId, controller) => {
      if (actionId !== 'discard') {
        controller.close('continue');
        return;
      }
      // Judged again right before discarding: a save that started, or a
      // generation that ended (the three choices apply again).
      if (isSourceSaving(source) || generationPhase === 'idle') {
        controller.close('recheck', { restoreFocus: false });
        return;
      }
      attempt(() => source.discard(), null);
      refresh();
      controller.close('discarded', { restoreFocus: false });
    },
  });
  return dialog.result;
}

export async function requestSwitch({ source = null, invoker = null, proceed }) {
  if (guardActive) return false;
  guardActive = true;
  try {
    for (;;) {
      if (!isCurrent(source)) break;
      if (isSourceSaving(source)) {
        const state = stateOf(source);
        const outcome = await waitFor(state.promise || Promise.resolve(), invoker, {
          title: '保存の完了を待っています',
          lead: `${labelOf(source)}の保存が終わってから切り替えます。`,
        });
        if (!outcome.done) return false;
        continue;
      }
      if (!attempt(() => source.isDirty(), false)) break;
      if (generationPhase !== 'idle') {
        const choice = await askWhileGenerating(invoker, source);
        if (choice === 'recheck') continue;
        if (choice !== 'discarded') return false;
        continue; // judged once more before switching
      }
      const choice = await askAboutUnsaved(invoker, { note: SWITCH_NOTE });
      if (choice !== 'saved' && choice !== 'discarded') return false;
    }
    refresh();
    proceed();
    return true;
  } finally {
    guardActive = false;
  }
}

export function holdNavigation(message) {
  navigationHold = message;
}

export function releaseNavigation() {
  navigationHold = null;
}

export function installLinkGuard() {
  if (linkGuardInstalled) return;
  linkGuardInstalled = true;
  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest('a[href]') : null;
    if (!link || link.hasAttribute('download') || link.dataset.unsavedGuard === 'off') return;
    const target = (link.getAttribute('target') || '').toLowerCase();
    if (target && target !== '_self') return;
    let url;
    try {
      url = new URL(link.href, window.location.href);
    } catch {
      return;
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return;
    const here = window.location;
    const samePage = url.origin === here.origin && url.pathname === here.pathname && url.search === here.search;
    if (samePage && url.hash) return; // in-page anchor such as the skip link
    if (navigationHold) {
      event.preventDefault();
      notify(navigationHold, { type: 'info' });
      return;
    }
    if (!hasUnsaved() && !isSaving()) return;
    event.preventDefault();
    requestLeave(url.href, { invoker: link });
  });
}
