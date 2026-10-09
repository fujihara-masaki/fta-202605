// Partial update (plan 3.4-5). After a manual add, a delete, a factor's save
// or a generation, the same URL (GET /analyses/{id}) is fetched again and
// only the regions marked data-region (work steps, structure navigation,
// work lists, tree, table) and the embedded summary are replaced. Step ① is
// never replaced, so typed input stays; the inspector is not taken from the
// answer but drawn again from the new data for the selection, and its
// factor editor (PR-5) is put back as it is — the draft, the focus and the
// saved values stay; nothing is read again for the same factor.
// Selection, step, tab, filter and scroll positions stay. After a manual
// add the new factor is selected through the R-01 check (app.requestSelect:
// an unsaved draft is asked about first), unless the user chose anything
// (even the same factor again) before the update was applied — it waits
// while a generation runs; after a
// delete its parent (the draft it affected was dropped by the delete
// dialog); either is brought into view. The focus goes back to the same
// element (data-node-id and role), or to its parent's row or the list
// heading when it is gone (plan 5.7). No new API.
// A factor removed elsewhere: the selection moves to its nearest remaining
// ancestor — except when the inspector holds a draft for it, which stays
// with its input and the reason it cannot be saved (never moved to another
// factor; plan 5.2).
//
// An old answer never rolls the page back (plan 3.4-5, P-3):
// - one fetch at a time; requests while one runs are merged into one more;
// - no fetch while a judgement or the top event of ① is being saved (the
//   writes the page shows at once, registered with app.writes); an answer
//   to a fetch issued before such a write started is discarded and the
//   fetch repeated;
// - the judgements the server confirmed on this page must be in the answer;
//   if not, the fetch is repeated, and a second mismatch shows
//   「表示を最新にできませんでした」 without applying anything. They are
//   checked by the next update only (dropped when it applies or gives up),
//   so a judgement changed later elsewhere (another tab) does not refuse
//   every update after it;
// - nothing is fetched while a generation runs; one fetch follows its end.
// 404: the analysis is gone — the page says so and stops the operations
// (since PR-4 also the header title's editing and ①'s saving).
// Another failure: the page is reloaded when nothing is being typed (the
// state comes back from the hash and sessionStorage), otherwise
// 「最新の表示に更新できませんでした」 is shown and the input stays. Typed input
// is what the shared save coordinator counts as unsaved or being saved (①,
// the header title: PR-4; the inspector's draft: PR-5), the open title
// editor and the manual-add dialog with input.
// whenIdle() resolves when no update runs or waits (the end of a
// generation, edit/generation.js).

import { el } from '../../common/dom.js';
import { requestText } from '../../common/http.js';
import { notify } from '../../common/notify.js';
import { hasUnsaved, isLeavingPage, isSaving } from '../../common/unsaved.js';
import { hasAddDialogInput } from './add-dialog.js';
import { currentEditor, renderInspector } from './inspector.js';
import { getNode, isAtOrBelow, readModel, stepForNode } from './model.js';
import { writeHash } from './state.js';
import { applyCounts, applySelection, applyStep, applyView, revealSelection } from './view.js';
import { applyFilter } from './filter.js';

const MAX_ATTEMPTS = 5;
const DATA_KEYS = ['action', 'role', 'nodeId', 'value', 'parentId', 'level', 'step', 'select', 'focus'];

function kebab(name) {
  return name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
}

function selectorFor(element) {
  const parts = [];
  for (const key of DATA_KEYS) {
    const value = element.dataset[key];
    if (value !== undefined) parts.push(`[data-${kebab(key)}="${CSS.escape(value)}"]`);
  }
  return parts.length ? parts.join('') : null;
}

// A function that finds the element again after a partial update replaced
// it (the same data-* in the same region or the inspector), or null when the
// element carries nothing to find it by (plan 5.7; PR-5: the dialogs give
// the focus back to the successor of the control that opened them).
export function successorOf(element) {
  if (!element || !element.dataset) return null;
  const selector = selectorFor(element);
  if (!selector) return null;
  const region = element.closest('[data-region]');
  const scope = region ? `[data-region="${region.dataset.region}"] ` : (
    element.closest('[data-inspector-body]') ? '[data-inspector-body] ' : '');
  return () => {
    if (element.isConnected) return element;
    return [...document.querySelectorAll(`${scope}${selector}`)].find((node) => isShown(node) && !node.disabled) || null;
  };
}

// Where the focus is, if it is in a part that will be replaced.
function describeFocus() {
  const active = document.activeElement;
  if (!active || active === document.body) return null;
  const region = active.closest('[data-region]');
  const inspector = active.closest('[data-inspector-body]');
  if (!region && !inspector) return null;
  const holder = active.closest('[data-node-id]');
  return {
    element: active,
    scope: region ? `[data-region="${region.dataset.region}"]` : '[data-inspector-body]',
    selector: selectorFor(active),
    nodeId: holder ? holder.dataset.nodeId : null,
  };
}

// Where the focus goes when its element is gone and no row of its parent is
// left in the same place: the heading of that list (plan 5.7).
function fallbackTarget(app, scope) {
  if (scope === '[data-inspector-body]') return document.querySelector('[data-inspector-body] [data-inspector-title]');
  if (scope === '[data-region="nav"]') return document.getElementById('edit-nav-heading');
  if (scope === '[data-region="tree"]') return document.getElementById('edit-panel-tree');
  if (scope === '[data-region="table"]') return document.getElementById('edit-panel-table');
  if (scope === '[data-region="steps"]') return document.querySelector('.edit-steps [aria-current="step"]');
  return document.querySelector(`[data-step-panel="${app.state.step}"] .edit-step-panel__title`);
}

function isShown(element) {
  return Boolean(element) && element.offsetParent !== null;
}

// Back to the same element (found again by data-node-id and its role);
// if it is gone, the row of its parent (of the nearest ancestor still there,
// when the parent went too), else the heading of the list.
function restoreFocus(app, focus, previousModel) {
  if (!focus) return;
  // The element itself is still there (the inspector's editor is put back
  // as it is, PR-5): it keeps the focus.
  if (focus.element && focus.element.isConnected && isShown(focus.element)) {
    if (document.activeElement !== focus.element) focus.element.focus({ preventScroll: true });
    return;
  }
  if (focus.selector) {
    const target = document.querySelector(`${focus.scope} ${focus.selector}`);
    if (isShown(target) && !target.disabled) {
      target.focus({ preventScroll: true });
      return;
    }
  }
  if (focus.scope !== '[data-inspector-body]') {
    const seen = new Set();
    let old = focus.nodeId ? getNode(previousModel, focus.nodeId) : null;
    while (old && old.parentId !== null && !seen.has(old.id)) {
      seen.add(old.id);
      const row = document.querySelector(
        `${focus.scope} [data-action="select"][data-node-id="${old.parentId}"]:not([data-focus])`,
      );
      if (isShown(row)) {
        row.focus({ preventScroll: true });
        return;
      }
      old = getNode(previousModel, old.parentId);
    }
  }
  const heading = fallbackTarget(app, focus.scope);
  if (isShown(heading)) heading.focus({ preventScroll: true });
}

// Typed input that a reload would lose (step ①, the header title and the
// inspector's draft as the save coordinator sees them, the open title
// editor, the manual-add dialog with input).
function hasTypedInput() {
  if (hasUnsaved() || isSaving()) return true;
  const titleEditor = document.querySelector('[data-title-editor]');
  if (titleEditor && !titleEditor.hidden) return true;
  return hasAddDialogInput();
}

function merge(pending, options) {
  const next = { ...(pending || {}) };
  for (const [key, value] of Object.entries(options || {})) {
    if (value !== undefined && value !== null) next[key] = value;
  }
  return next;
}

export function createRefresher(app, { scrollers }) {
  let running = false;
  let pending = null;
  let sequence = 0;
  let idleWaiters = [];

  function settle() {
    if (running || (pending && !app.gone)) return;
    const ready = idleWaiters;
    idleWaiters = [];
    ready.forEach((resolve) => resolve());
  }

  function stopOperations() {
    app.gone = true;
    const page = app.root;
    if (!page.querySelector('.edit-gone')) {
      page.prepend(el('p', { class: 'edit-gone', role: 'alert' },
        '分析が見つかりません（削除された可能性があります）。この画面では保存・生成・削除ができません。一覧へ戻ってください。'));
    }
    page.querySelectorAll('[data-action="judgement"], [data-action^="legacy-"], [data-action="add"], [data-action="delete"], [data-generate]').forEach((button) => {
      button.disabled = true;
      button.dataset.blockedReason = '分析が見つかりません';
    });
    page.querySelectorAll('[data-step-panel="1"] button').forEach((button) => {
      button.disabled = true;
    });
    // The header title: ✎ off; an open editor keeps its input (read-only)
    // and saves nothing more (edit/title.js).
    if (app.title) app.title.stop();
    // The inspector's editor keeps its input and sends nothing more.
    const editor = currentEditor();
    if (editor) editor.markGone('analysis');
    notify('分析が見つかりません（削除された可能性があります）', { type: 'error' });
  }

  function failed(result) {
    if (isLeavingPage()) return; // the page is being left (保存して移動): no reload, no message
    if (!hasTypedInput()) {
      app.saveSession();
      window.location.reload();
      return;
    }
    notify(
      `最新の表示に更新できませんでした（${result.reason || '応答を読み取れませんでした'}）。`
        + '入力中の内容を保存してから、ページを再読み込みしてください。',
      { type: 'error' },
    );
  }

  function matchesConfirmed(model) {
    for (const [nodeId, value] of app.writes.confirmed) {
      const node = getNode(model, nodeId);
      if (node && node.judgement !== value) return false;
    }
    return true;
  }

  function apply(doc, model, options) {
    const previousModel = app.model;
    const focus = describeFocus();
    const scroll = {
      nav: scrollers.nav ? scrollers.nav.scrollTop : 0,
      center: scrollers.center ? scrollers.center.scrollTop : 0,
      inspector: scrollers.inspector ? scrollers.inspector.scrollTop : 0,
    };

    document.querySelectorAll('[data-region]').forEach((current) => {
      const fresh = doc.querySelector(`[data-region="${current.dataset.region}"]`);
      if (fresh) current.replaceWith(document.importNode(fresh, true));
    });
    const data = document.getElementById('analysis-data');
    const freshData = doc.getElementById('analysis-data');
    if (data && freshData) data.textContent = freshData.textContent;
    app.model = model;
    app.writes.confirmed.clear();

    // What to select now (a new factor after a manual add: below, through
    // the R-01 check, once this update has been applied).
    const before = { sel: app.state.sel, step: app.state.step };
    const selected = app.state.sel === 'top' ? null : getNode(previousModel, app.state.sel);
    const editor = currentEditor();
    const keepsDraft = Boolean(editor) && editor.nodeId === Number(app.state.sel) && editor.hasDraft();
    // Only if the user has chosen nothing since the add (any choice, even of
    // the same factor again: A → B → A); the number was recorded when the
    // update was asked for and is never taken again (retries, a generation
    // holding the update back).
    const selectNew = options.select !== undefined && getNode(model, options.select)
      && options.selectIntent === app.selectionIntent
      && (options.selectFrom === undefined || options.selectFrom === app.state.sel);
    if (options.deleted !== undefined && selected && !keepsDraft
      && isAtOrBelow(previousModel, selected, Number(options.deleted))) {
      const deleted = getNode(previousModel, options.deleted);
      const parent = deleted && deleted.parentId !== null && deleted.parentId !== deleted.id
        ? getNode(model, deleted.parentId) : null;
      app.state.sel = parent ? String(parent.id) : 'top';
      app.state.step = parent ? stepForNode(parent) : 1;
    } else if (selected && !getNode(model, selected.id) && keepsDraft) {
      // Removed elsewhere while its draft is in the inspector: the selection,
      // the input and the reason it cannot be saved stay (inspector.js).
      if (!editor.gone) notify('編集中の要因が見つからないため、入力内容を保存できません（別のタブなどで削除された可能性があります）', { type: 'error' });
    } else if (selected && !getNode(model, selected.id)) {
      // Removed elsewhere (another tab): its nearest remaining ancestor.
      let current = selected;
      const seen = new Set();
      let replacement = null;
      while (current && current.parentId !== null && !seen.has(current.id)) {
        seen.add(current.id);
        replacement = getNode(model, current.parentId);
        if (replacement) break;
        current = getNode(previousModel, current.parentId);
      }
      app.state.sel = replacement ? String(replacement.id) : 'top';
      app.state.step = replacement ? stepForNode(replacement) : 1;
      notify('選んでいた要因が見つからなくなったため、選択を切り替えました', { type: 'info' });
    }

    applyView(app);
    applyStep(app);
    applySelection(app);
    applyCounts(app);
    applyFilter(app);
    if (app.applyStep1State) app.applyStep1State(); // the step status and ③・④'s notes were replaced
    writeHash(app.state);
    renderInspector(app);
    if (scrollers.nav) scrollers.nav.scrollTop = scroll.nav;
    if (scrollers.center) scrollers.center.scrollTop = scroll.center;
    if (scrollers.inspector) scrollers.inspector.scrollTop = scroll.inspector;
    if (app.state.sel !== before.sel) {
      // A new selection (the added factor, the parent of the deleted one):
      // as when it is chosen, another step starts at its top, and the
      // factor is brought into view where it is not.
      if (app.state.step !== before.step && app.state.view === 'work' && scrollers.center) {
        scrollers.center.scrollTop = 0;
      }
      revealSelection(app, null);
    }
    restoreFocus(app, focus, previousModel);
    app.saveSession();
    if (selectNew && app.requestSelect) {
      // The added factor, as its route of R-01: asked about an unsaved
      // draft first; 編集を続ける keeps the selection (the factor stays added).
      app.requestSelect(Number(options.select), { invoker: document.activeElement });
    }
  }

  // Put the requests off until the generation has ended (flush).
  function defer(options) {
    pending = merge(options, pending);
  }

  async function run(first) {
    running = true;
    let options = first;
    try {
      let mismatches = 0;
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
        await app.writes.whenIdle();
        // A write that ends can start the next one waiting for the same
        // factor (judgement.js) before this goes on: no fetch while one runs.
        while (app.writes.inFlight > 0) await app.writes.whenIdle();
        if (app.gone) return;
        if (app.generating) {
          defer(options);
          return;
        }
        // Requests made up to now are answered by this fetch.
        options = merge(options, pending);
        pending = null;
        sequence += 1;
        const token = sequence;
        const writeMark = app.writes.seq;
        const result = await requestText(`/analyses/${app.analysisId}`);
        if (token !== sequence || app.gone) return;
        if (app.writes.seq !== writeMark || app.writes.inFlight > 0) continue; // a judgement was saved meanwhile
        if (app.generating) {
          defer(options);
          return;
        }
        if (!result.ok) {
          if (result.status === 404) stopOperations();
          else failed(result);
          return;
        }
        const doc = new DOMParser().parseFromString(result.text, 'text/html');
        const model = readModel(doc);
        if (!model || model.analysisId !== app.analysisId) {
          failed({ reason: '応答を読み取れませんでした' });
          return;
        }
        if (!matchesConfirmed(model)) {
          mismatches += 1;
          if (mismatches >= 2) {
            // Both answers were fetched after these judgements were
            // confirmed, so they have been checked; most likely one was
            // changed elsewhere since (another tab). Kept, they would refuse
            // every later update until a reload.
            app.writes.confirmed.clear();
            notify('表示を最新にできませんでした。ページを再読み込みしてください。', { type: 'error' });
            return;
          }
          continue;
        }
        apply(doc, model, options);
        return;
      }
      notify('表示を最新にできませんでした。ページを再読み込みしてください。', { type: 'error' });
    } finally {
      running = false;
      if (pending && !app.generating && !app.gone) {
        const next = pending;
        pending = null;
        run(next);
      } else {
        settle();
      }
    }
  }

  return {
    request(options = {}) {
      if (app.gone) return;
      // The factor to select is selected only if the user has chosen nothing
      // since now (app.selectionIntent counts every choice of the user) and
      // the selection is still the one of now (a newer choice stays).
      const asked = options.select !== undefined
        ? { ...options, selectFrom: app.state.sel, selectIntent: app.selectionIntent }
        : options;
      if (running || app.generating) {
        pending = merge(pending, asked);
        return;
      }
      run(merge(null, asked));
    },
    // After a generation: the one fetch that was held back.
    flush() {
      if (!pending || running || app.generating || app.gone) return;
      const next = pending;
      pending = null;
      run(next);
    },
    // For app.js's dialogs: where the focus is when one opens, and back
    // there when it closes — to the same control, or to what replaced it
    // when an update ran meanwhile (plan 5.7).
    whenIdle() {
      if (!running && (!pending || app.gone)) return Promise.resolve();
      return new Promise((resolve) => idleWaiters.push(resolve));
    },
    describeFocus: () => describeFocus(),
    restoreFocus: (focus) => restoreFocus(app, focus, app.model),
  };
}
