// Unsaved-change protection (J-12).
//
// Screens register "save sources" (an input that can be saved). A source is
// bound to its target when editing starts and describes itself:
//   { id, order, label (string | () => string),
//     isDirty(), isSaving()?, whenIdle()?, validate()?, save()?, discard(),
//     prompt? }
// isDirty() must compare with the same normalisation used when saving
// (text.js normalizeText), so typing and then restoring the original is not
// "unsaved".
//
// - In-page links are intercepted: with unsaved changes a dialog offers
//   保存して移動 / 破棄して移動 / 編集を続ける. 保存して移動 validates every
//   source first (nothing is sent if one is invalid), then saves them one by
//   one in `order`; if any save fails the page stays and the reasons are
//   shown. Download links (download attribute) are never intercepted.
// - Browser navigation (reload, back, closing the tab) gets the browser's own
//   confirmation via beforeunload, registered only while something is unsaved
//   or being saved, so back/forward caching is not blocked otherwise.
// - A source that cannot be saved from the dialog leaves out save() (the
//   new-analysis form: saved only by its own 作成して編集へ). While such a
//   source has unsaved input the dialog offers only 続ける / 破棄して移動,
//   worded by the source's optional `prompt`:
//     { title, lead, note, continueLabel }
// - holdNavigation(message): while the page's own navigation is under way
//   (a form POST already sent), an in-page link would cancel it after the
//   server may have acted on it, so links are held and `message` is shown.
//   Browser navigation (back, reload) is not affected.
//
// Scope: the list screen's inline rename (PR-1) and the new-analysis form
// (PR-2, discard-only). The full save-coordination contract of plan 5.9.3
// (edit-screen sources and the generation state of J-01) is completed in PR-4.

import { el } from './dom.js';
import { openDialog } from './dialog.js';
import { notify } from './notify.js';

export const SOURCE_ORDER = {
  factor: 10,
  topEvent: 20,
  context: 30,
  listRename: 40,
};

const sources = new Map();
let beforeUnloadRegistered = false;
let guardActive = false;
let linkGuardInstalled = false;
let navigationHold = null;

function attempt(fn, fallback) {
  try {
    return fn();
  } catch {
    return fallback;
  }
}

function labelOf(source) {
  return typeof source.label === 'function' ? attempt(() => source.label(), source.id) : source.label;
}

function byOrder(a, b) {
  return (a.order ?? 100) - (b.order ?? 100);
}

export function registerSource(source) {
  sources.set(source.id, source);
  refresh();
  return () => {
    if (sources.get(source.id) === source) sources.delete(source.id);
    refresh();
  };
}

export function dirtySources() {
  return [...sources.values()].filter((source) => attempt(() => source.isDirty(), false)).sort(byOrder);
}

export function hasUnsaved() {
  return dirtySources().length > 0;
}

export function isSaving() {
  return [...sources.values()].some((source) => attempt(() => Boolean(source.isSaving?.()), false));
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
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function whenAllIdle() {
  const pending = [...sources.values()]
    .filter((source) => attempt(() => Boolean(source.isSaving?.()), false))
    .map((source) => Promise.resolve(attempt(() => source.whenIdle?.(), null)).catch(() => null));
  return Promise.all(pending);
}

// Wait for saves already in flight (plan 5.1 step 1). Requests are never
// cancelled: the server may still apply them.
async function waitUntilIdle(invoker) {
  const idle = whenAllIdle().then(() => 'idle');
  const quick = await Promise.race([idle, delay(300).then(() => 'slow')]);
  if (quick === 'idle') return true;

  const dialog = openDialog({
    title: '保存の完了を待っています',
    body: ['送信中の保存が終わってから移動します。'],
    actions: [{ id: 'continue', label: '編集を続ける', autofocus: true }],
    invoker,
    cancelAction: 'continue',
  });
  dialog.setStatus('保存しています…');
  const slowTimer = window.setTimeout(() => {
    if (dialog.isOpen()) {
      dialog.setStatus('サーバーが別の処理（生成など）を実行中の可能性があります。保存が終わるまで待っています。');
    }
  }, 10000);
  const outcome = await Promise.race([idle, dialog.result]);
  window.clearTimeout(slowTimer);
  if (outcome === 'idle') {
    dialog.close('idle', { restoreFocus: false });
    return true;
  }
  return false;
}

async function saveAll(dialog) {
  const targets = dirtySources();
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
  const results = [];
  for (const source of targets) {
    let outcome;
    try {
      outcome = await source.save();
    } catch {
      outcome = { ok: false, reason: '保存中に予期しないエラーが発生しました' };
    }
    results.push([source, outcome || { ok: false, reason: '保存できませんでした' }]);
  }
  if (!dialog.isOpen()) return;
  dialog.setBusy(false);

  const failed = results.filter(([, outcome]) => !outcome.ok);
  if (!failed.length) {
    dialog.close('saved', { restoreFocus: false });
    return;
  }
  const lines = [
    '保存できなかった変更があるため、移動していません。',
    ...failed.map(([source, outcome]) => `${labelOf(source)}：${outcome.reason}`),
  ];
  if (results.some(([, outcome]) => outcome.ok)) {
    lines.push('保存できた変更は取り消されません。「破棄して移動」を選ぶと、保存できなかった変更だけが破棄されます。');
  }
  dialog.setError(lines);
  const retry = dialog.button('save');
  if (retry) {
    retry.textContent = '再試行';
    retry.focus();
  }
}

function pendingList(pending) {
  return el('ul', { class: 'ui-dialog__list' }, pending.map((source) => el('li', {}, labelOf(source))));
}

function discardAll() {
  dirtySources().forEach((source) => attempt(() => source.discard(), null));
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
        discardAll();
        controller.close('discarded', { restoreFocus: false });
      } else {
        controller.close('continue');
      }
    },
  });
  return dialog.result;
}

function askAboutUnsaved(invoker) {
  const pending = dirtySources();
  const unsavable = pending.find((source) => typeof source.save !== 'function');
  if (unsavable) return askToDiscard(invoker, pending, unsavable.prompt);
  const list = pendingList(pending);
  const dialog = openDialog({
    title: '保存していない変更があります',
    body: [
      '次の変更はまだ保存されていません。',
      list,
      '保存してから移動するか、変更を破棄して移動するかを選んでください。',
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
        discardAll();
        controller.close('discarded', { restoreFocus: false });
      } else if (actionId === 'save') {
        saveAll(controller);
      }
    },
  });
  return dialog.result;
}

async function runGuarded({ invoker, proceed }) {
  if (guardActive) return false;
  guardActive = true;
  try {
    if (isSaving() && !(await waitUntilIdle(invoker))) return false;
    if (hasUnsaved()) {
      const choice = await askAboutUnsaved(invoker);
      if (choice !== 'saved' && choice !== 'discarded') return false;
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
  return runGuarded({ invoker, proceed: () => window.location.assign(href) });
}

// Any other transition that would drop the current input (e.g. opening the
// rename of another row): same three choices, then `proceed`.
export function requestTransition({ invoker = null, proceed }) {
  return runGuarded({ invoker, proceed });
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
