// Analysis edit (B), PR-3 skeleton (plan 7.2, 8.3).
//
// The server renders the structure (app/detail_view.py, plan 3.4-1); this
// module keeps the screen state (plan 3.4-3):
// - selection of a factor or the top event, kept in step on the structure
//   navigation, the work list and its parent groups, the tree, the table and
//   the inspector (R-01 routes: navigation, work row, parent name, tree,
//   table, 要確認, breadcrumb, child link); choosing a factor switches the
//   work step;
// - work steps ①〜⑤ (a guide; the order is not enforced), view tabs
//   (WAI-ARIA tabs, arrow keys), judgement, filter;
// - state in the URL hash and sessionStorage (plan 5.5), restored on reload;
// - the bridge the legacy app.js uses for detail editing, manual add,
//   delete and generation (still the old processing in PR-3), whose results
//   are shown by a partial update instead of a reload (edit/refresh.js);
// - PR-4: ① with its save status (edit/step1.js), the header title edited
//   inline (edit/title.js), ⑤'s counts (view.js applySummary) and the
//   generation's connection to the shared save coordinator
//   (edit/generation.js, js/common/unsaved.js), which also guards leaving
//   the page;
// - PR-5: the inspector's editor of the factor (edit/factor-editor.js), and
//   every R-01 route (the select buttons, the top event, 要確認, the
//   breadcrumb, child links, the selection after a manual add) through one
//   guarded switch, requestSelect(): the inspector's unsaved draft is asked
//   about (common/unsaved.js requestSwitch) before anything changes; the
//   manual-add and delete dialogs (edit/add-dialog.js, delete-dialog.js).
//   Generation still runs through app.js (PR-6).
// Text from the user or the LLM is only ever inserted as text.

import { el } from '../common/dom.js';
import { notify } from '../common/notify.js';
import { requestSwitch } from '../common/unsaved.js';
import { installBridge } from './edit/bridge.js';
import { applyFilter, clearFilter, currentFilter, initFilter } from './edit/filter.js';
import {
  currentFactorSource,
  renderInspector,
  setEditorHooks,
  updateTopEventText,
} from './edit/inspector.js';
import { openAddDialog } from './edit/add-dialog.js';
import { openDeleteDialog } from './edit/delete-dialog.js';
import { requestJudgement } from './edit/judgement.js';
import { createRefresher, successorOf } from './edit/refresh.js';
import { createStep1 } from './edit/step1.js';
import { createTitleEditor } from './edit/title.js';
import { createGeneration } from './edit/generation.js';
import { getNode, readModel, stepForNode } from './edit/model.js';
import { loadSession, saveSession, stateFromHash, VIEWS, writeHash } from './edit/state.js';
import {
  applyCounts,
  applySelection,
  applyStep,
  applyTopEvent,
  applyTopEventNotes,
  applyView,
  revealSelection,
} from './edit/view.js';

const SOURCES = {
  nav: 'nav',
  work: 'work',
  'work-warning': 'work',
  group: 'work',
  tree: 'tree',
  'tree-warning': 'tree',
  table: 'table',
  crumb: 'inspector',
  child: 'inspector',
};

function createWriteTracker() {
  let waiters = [];
  const tracker = {
    seq: 0,
    inFlight: 0,
    confirmed: new Map(), // factor id -> judgement the server confirmed, until an update checked it
    begin() {
      tracker.seq += 1;
      tracker.inFlight += 1;
      return tracker.seq;
    },
    end(token, confirmed) {
      tracker.inFlight = Math.max(0, tracker.inFlight - 1);
      if (confirmed) tracker.confirmed.set(confirmed.nodeId, confirmed.value);
      if (tracker.inFlight === 0) {
        const ready = waiters;
        waiters = [];
        ready.forEach((resolve) => resolve());
      }
    },
    whenIdle() {
      return tracker.inFlight === 0 ? Promise.resolve() : new Promise((resolve) => waiters.push(resolve));
    },
  };
  return tracker;
}

function start(root, model) {
  const analysisId = model.analysisId;
  const session = loadSession(analysisId);
  const scrollers = {
    nav: root.querySelector('[data-scroll="nav"]'),
    center: root.querySelector('[data-scroll="center"]'),
    inspector: root.querySelector('[data-scroll="inspector"]'),
  };
  const savedScroll = session.scroll && typeof session.scroll === 'object' ? session.scroll : null;

  const app = {
    root,
    analysisId,
    model,
    state: stateFromHash(model, window.location.hash),
    generating: false,
    gone: false,
    writes: createWriteTracker(),
    centerScroll: { work: 0, tree: 0, table: 0, ...(savedScroll && savedScroll.center) },
  };

  app.saveSession = () => {
    if (scrollers.center) app.centerScroll[app.state.view] = scrollers.center.scrollTop;
    saveSession(analysisId, {
      scroll: {
        nav: scrollers.nav ? scrollers.nav.scrollTop : 0,
        inspector: scrollers.inspector ? scrollers.inspector.scrollTop : 0,
        center: { ...app.centerScroll },
      },
      filter: currentFilter(),
    });
  };

  app.setView = (view) => {
    if (!VIEWS.includes(view) || view === app.state.view) return;
    if (scrollers.center) app.centerScroll[app.state.view] = scrollers.center.scrollTop;
    app.state.view = view;
    applyView(app);
    if (scrollers.center) scrollers.center.scrollTop = app.centerScroll[view] || 0;
    writeHash(app.state);
  };

  app.setStep = (step) => {
    if (!Number.isInteger(step) || step < 1 || step > 5) return;
    const changed = step !== app.state.step;
    app.setView('work');
    app.state.step = step;
    applyStep(app);
    if (changed && scrollers.center) scrollers.center.scrollTop = 0;
    writeHash(app.state);
  };

  // Show a factor (or the top event). Only after the switch was allowed:
  // the R-01 routes call requestSelect. Choosing the factor already shown
  // (or its 要確認) keeps its editor and draft: nothing is drawn again.
  // Every choice the user makes on an R-01 route counts (even the factor
  // already shown): a selection asked for before it (after a manual add) is
  // then not made (edit/refresh.js).
  app.selectionIntent = 0;

  app.select = (sel, { source = null, focusWarning = false } = {}) => {
    const node = sel === 'top' ? null : getNode(app.model, sel);
    if (sel !== 'top' && !node) return;
    const next = node ? String(node.id) : 'top';
    const same = next === app.state.sel;
    const step = node ? stepForNode(node) : 1;
    const stepChanged = step !== app.state.step;
    app.state.sel = next;
    app.state.step = step;
    applySelection(app);
    applyStep(app);
    if (stepChanged && app.state.view === 'work' && scrollers.center) scrollers.center.scrollTop = 0;
    writeHash(app.state);
    if (!same || focusWarning) renderInspector(app, { focusWarning });
    revealSelection(app, source);
  };

  // Every R-01 route (plan 5.1): a switch to another factor or to the top
  // event first asks about the inspector's unsaved draft (3 choices; during
  // a generation 2, J-01). Resolves to true when the selection changed.
  app.requestSelect = (sel, { source = null, focusWarning = false, invoker = null } = {}) => {
    const next = sel === 'top' ? 'top' : String(Number(sel));
    if (next === app.state.sel) {
      app.select(sel, { source, focusWarning });
      return Promise.resolve(true);
    }
    if (next !== 'top' && !getNode(app.model, next)) return Promise.resolve(false);
    const opener = invoker || document.activeElement;
    return requestSwitch({
      source: currentFactorSource(),
      invoker: opener,
      fallbackFocus: successorOf(opener),
      proceed: () => app.select(sel, { source, focusWarning }),
    });
  };

  // The selection after a manual add (edit/refresh.js), one at a time: the
  // latest added factor is the target. While its check is open (the three
  // choices for an unsaved draft), the selection after a later add only
  // replaces the target — it is not dropped because the check is busy, and
  // the earlier factor is not selected over it. Before switching, the
  // target is judged again: if the user chose anything meanwhile
  // (selectionIntent), nothing is selected. 編集を続ける keeps the selection
  // and the draft, and drops the target.
  let autoTarget = null;
  let autoRunning = false;
  app.autoSelect = (nodeId, intent) => {
    autoTarget = { id: Number(nodeId), intent };
    if (autoRunning) return;
    autoRunning = true;
    const opener = document.activeElement;
    requestSwitch({
      source: currentFactorSource(),
      invoker: opener,
      fallbackFocus: successorOf(opener),
      proceed: () => {
        const target = autoTarget;
        if (target && target.intent === app.selectionIntent && getNode(app.model, target.id)) {
          app.select(target.id, {});
        }
      },
    }).finally(() => {
      autoRunning = false;
      autoTarget = null;
    });
  };

  app.afterJudgement = () => {
    applyFilter(app);
  };

  // Show the result of a legacy change (manual add: {select}, delete:
  // {deleted}) by a partial update; none while a generation runs, one after.
  const refresher = createRefresher(app, { scrollers });
  app.refresh = (options = {}) => refresher.request(options);
  app.whenRefreshed = () => refresher.whenIdle();

  app.setGenerating = (on) => {
    app.generating = on;
    document.querySelectorAll('[data-generate]').forEach((button) => {
      button.disabled = on || button.hasAttribute('data-blocked-reason');
    });
    if (!on) refresher.flush();
  };

  // A save the page shows at once (a judgement, the top event of ①): no
  // partial update is fetched meanwhile, and one fetched before is not
  // applied (plan 3.4-5, P-3). Call the returned function when it has ended.
  app.beginWrite = () => {
    const write = app.writes.begin();
    let ended = false;
    return () => {
      if (ended) return;
      ended = true;
      app.writes.end(write, null);
    };
  };

  // ① (PR-4): the step status says when something is unsaved; ③・④ say that
  // an unsaved top event is not used (J-09). Again after a partial update,
  // which replaces those parts.
  let step1 = null;
  app.applyStep1State = () => {
    const top = document.getElementById('topEventInput');
    const unsaved = Boolean(step1 && step1.anyDirty());
    applyTopEvent(top ? top.dataset.saved : '', { unsaved });
    applyTopEventNotes(Boolean(step1 && step1.topEvent.isDirty()));
  };
  step1 = createStep1(app);
  const title = createTitleEditor(app);
  app.title = title;
  const generation = createGeneration(app, { step1, title });
  app.beginGeneration = (level) => generation.begin(level);

  // The one success handling of a factor's save (the inspector's 保存 and
  // 保存して移動): called synchronously by the source's commit(), after the
  // request ended. The data and what is counted from it change at once; the
  // server-rendered parts follow by a partial update, which is only asked
  // for here and never awaited (it waits for writes in flight itself, and the
  // save does not wait for it). A failure of the display is not a failure of
  // the save: it is told separately and never sends the save again.
  setEditorHooks({
    onSaved(nodeId, fields) {
      try {
        const node = getNode(app.model, nodeId);
        if (node) {
          node.title = fields.title;
          node.description = fields.description;
          node.memo = Boolean(fields.memo);
          node.directCause = fields.direct_cause_status;
        }
        applyCounts(app);
        applyFilter(app);
        if (app.state.sel === String(nodeId)) renderInspector(app);
      } catch {
        notify('要因は保存しましたが、画面の表示を更新できませんでした。ページを再読み込みしてください。', { type: 'error' });
      }
      app.refresh();
    },
  });

  installBridge(app);
  initFilter(app, session.filter);
  applyView(app);
  applyStep(app);
  applySelection(app);
  applyCounts(app);
  app.applyStep1State();
  renderInspector(app);

  if (savedScroll) {
    if (scrollers.nav) scrollers.nav.scrollTop = Number(savedScroll.nav) || 0;
    if (scrollers.center) scrollers.center.scrollTop = Number(app.centerScroll[app.state.view]) || 0;
    if (scrollers.inspector) scrollers.inspector.scrollTop = Number(savedScroll.inspector) || 0;
  } else {
    revealSelection(app, null);
  }

  // ----- events --------------------------------------------------------

  const runLegacy = (action, button) => {
    if (app.gone) return;
    const level = Number(button.dataset.level);
    const parentId = button.dataset.parentId ? Number(button.dataset.parentId) : null;
    const legacy = window;
    if (action === 'legacy-generate' && typeof legacy.generateFactors === 'function') {
      legacy.generateFactors(app.analysisId, level);
    } else if (action === 'legacy-generate-additional' && typeof legacy.generateAdditional === 'function') {
      legacy.generateAdditional(app.analysisId, parentId, level);
    }
  };

  // Skip links move the focus without touching the hash, which holds the
  // screen state.
  const followSkipLink = (event, link) => {
    const id = (link.getAttribute('href') || '').replace(/^#/, '');
    const target = id ? document.getElementById(id) : null;
    if (!target) return;
    event.preventDefault();
    if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
    target.focus();
  };

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const skip = target.closest('a.skip-link');
    if (skip) {
      followSkipLink(event, skip);
      return;
    }
    if (!root.contains(target)) return;
    const tab = target.closest('[data-view-tab]');
    if (tab) {
      app.setView(tab.dataset.viewTab);
      return;
    }
    const button = target.closest('[data-action]');
    if (!button || button.disabled) return;
    const action = button.dataset.action;
    if (action === 'select') {
      app.selectionIntent += 1;
      app.requestSelect(button.dataset.select === 'top' ? 'top' : button.dataset.nodeId, {
        source: SOURCES[button.dataset.role] || null,
        focusWarning: button.dataset.focus === 'warning',
        invoker: button,
      });
    } else if (action === 'add') {
      if (!app.gone) {
        openAddDialog(app, {
          parentId: button.dataset.parentId || null, level: Number(button.dataset.level), invoker: button,
        });
      }
    } else if (action === 'delete') {
      if (!app.gone) openDeleteDialog(app, Number(button.dataset.nodeId), { invoker: button });
    } else if (action === 'step') {
      app.setStep(Number(button.dataset.step));
    } else if (action === 'judgement') {
      requestJudgement(app, Number(button.dataset.nodeId), button.dataset.value);
    } else if (action === 'filter-clear') {
      clearFilter(app);
    } else if (action.startsWith('legacy-')) {
      runLegacy(action, button);
    }
  });

  const tablist = root.querySelector('[role="tablist"]');
  if (tablist) {
    tablist.addEventListener('keydown', (event) => {
      const tabs = [...tablist.querySelectorAll('[role="tab"]')];
      const index = tabs.indexOf(document.activeElement);
      if (index < 0) return;
      let next = null;
      if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length];
      else if (event.key === 'ArrowLeft') next = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === 'Home') next = tabs[0];
      else if (event.key === 'End') next = tabs[tabs.length - 1];
      if (!next) return;
      event.preventDefault();
      app.setView(next.dataset.viewTab);
      next.focus();
    });
  }

  window.addEventListener('pagehide', () => app.saveSession());

  // Saving the top event updates data-saved (edit/step1.js); the step
  // status, the top event in the outlines and the inspector follow it.
  const topInput = document.getElementById('topEventInput');
  if (topInput) {
    new MutationObserver(() => {
      app.applyStep1State();
      updateTopEventText(topInput.dataset.saved);
    }).observe(topInput, { attributes: true, attributeFilter: ['data-saved'] });
  }

  return app;
}

const root = document.querySelector('[data-edit-page]');
if (root) {
  const model = readModel();
  if (model) {
    start(root, model);
  } else {
    const body = document.querySelector('[data-inspector-body]');
    if (body) {
      body.replaceChildren(el('p', { class: 'edit-inspector__status', 'data-kind': 'error' },
        '画面の表示に必要なデータを読み込めませんでした。ページを再読み込みしてください。'));
    }
    notify('画面の表示に必要なデータを読み込めませんでした。ページを再読み込みしてください。', { type: 'error' });
  }
}
