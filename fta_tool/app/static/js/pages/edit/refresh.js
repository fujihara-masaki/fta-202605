// Partial update (plan 3.4-5). After a manual add, a delete, a detail save
// or a generation, the same URL (GET /analyses/{id}) is fetched again and
// only the regions marked data-region (work steps, structure navigation,
// work lists, tree, table) and the embedded summary are replaced. Step ① is
// never replaced, so typed input stays; the inspector is not taken from the
// answer but drawn again from the new data for the selection (it holds no
// draft in PR-3) and reads the saved details again. Selection, step, tab,
// filter and scroll positions stay (after a manual add the new factor is
// selected, unless another one was chosen before the update was applied —
// it waits while a generation runs; after a delete its parent; either is
// brought into view); the focus goes back to the same element (data-node-id
// and role), or to its parent's row or the list heading when it is gone
// (plan 5.7). No new API.
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
// the header title: PR-4), the open title editor and an open legacy dialog.
// whenIdle() resolves when no update runs or waits (the end of a
// generation, edit/generation.js).

import { el } from '../../common/dom.js';
import { requestText } from '../../common/http.js';
import { notify } from '../../common/notify.js';
import { hasUnsaved, isSaving } from '../../common/unsaved.js';
import { renderInspector } from './inspector.js';
import { getNode, readModel, stepForNode } from './model.js';
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

// Where the focus is, if it is in a part that will be replaced.
function describeFocus() {
  const active = document.activeElement;
  if (!active || active === document.body) return null;
  const region = active.closest('[data-region]');
  const inspector = active.closest('[data-inspector-body]');
  if (!region && !inspector) return null;
  const holder = active.closest('[data-node-id]');
  return {
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

// Typed input that a reload would lose (step ① and the header title as the
// save coordinator sees them, the open title editor, an open legacy dialog).
function hasTypedInput() {
  if (hasUnsaved() || isSaving()) return true;
  const titleEditor = document.querySelector('[data-title-editor]');
  if (titleEditor && !titleEditor.hidden) return true;
  for (const id of ['nodeDetailModal', 'addNodeModal']) {
    const dialog = document.getElementById(id);
    if (dialog && !dialog.classList.contains('hidden')) return true;
  }
  return false;
}

function isAtOrBelow(model, selected, ancestorId) {
  const seen = new Set();
  let current = selected;
  while (current && !seen.has(current.id)) {
    if (current.id === ancestorId) return true;
    seen.add(current.id);
    current = current.parentId === null ? null : getNode(model, current.parentId);
  }
  return false;
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
    page.querySelectorAll('[data-action="judgement"], [data-action^="legacy-"], [data-generate]').forEach((button) => {
      button.disabled = true;
      button.dataset.blockedReason = '分析が見つかりません';
    });
    page.querySelectorAll('[data-step-panel="1"] button').forEach((button) => {
      button.disabled = true;
    });
    // The header title: ✎ off; an open editor keeps its input (read-only)
    // and saves nothing more (edit/title.js).
    if (app.title) app.title.stop();
    notify('分析が見つかりません（削除された可能性があります）', { type: 'error' });
  }

  function failed(result) {
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

    // What to select now.
    const before = { sel: app.state.sel, step: app.state.step };
    const selected = app.state.sel === 'top' ? null : getNode(previousModel, app.state.sel);
    if (options.select !== undefined && getNode(model, options.select)
      && (options.selectFrom === undefined || options.selectFrom === app.state.sel)) {
      const node = getNode(model, options.select);
      app.state.sel = String(node.id);
      app.state.step = stepForNode(node);
    } else if (options.deleted !== undefined && selected && isAtOrBelow(previousModel, selected, Number(options.deleted))) {
      const deleted = getNode(previousModel, options.deleted);
      const parent = deleted && deleted.parentId !== null && deleted.parentId !== deleted.id
        ? getNode(model, deleted.parentId) : null;
      app.state.sel = parent ? String(parent.id) : 'top';
      app.state.step = parent ? stepForNode(parent) : 1;
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
      // The factor to select is selected only if the selection is still the
      // one of now when the update is applied (a newer choice stays).
      const asked = options.select !== undefined ? { ...options, selectFrom: app.state.sel } : options;
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
