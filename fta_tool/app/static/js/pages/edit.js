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
//   delete and generation (still the old processing in PR-3).
// Text from the user or the LLM is only ever inserted as text.

import { el } from '../common/dom.js';
import { notify } from '../common/notify.js';
import { installBridge } from './edit/bridge.js';
import { applyFilter, clearFilter, currentFilter, initFilter } from './edit/filter.js';
import { renderInspector, updateTopEventText } from './edit/inspector.js';
import { requestJudgement } from './edit/judgement.js';
import { getNode, readModel, stepForNode } from './edit/model.js';
import { loadSession, saveSession, stateFromHash, VIEWS, writeHash } from './edit/state.js';
import {
  applyCounts,
  applySelection,
  applyStep,
  applyTopEvent,
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
    confirmed: new Map(), // factor id -> judgement the server confirmed
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

  app.select = (sel, { source = null, focusWarning = false } = {}) => {
    const node = sel === 'top' ? null : getNode(app.model, sel);
    if (sel !== 'top' && !node) return;
    const step = node ? stepForNode(node) : 1;
    const stepChanged = step !== app.state.step;
    app.state.sel = node ? String(node.id) : 'top';
    app.state.step = step;
    applySelection(app);
    applyStep(app);
    if (stepChanged && app.state.view === 'work' && scrollers.center) scrollers.center.scrollTop = 0;
    writeHash(app.state);
    renderInspector(app, { focusWarning });
    revealSelection(app, source);
  };

  app.afterJudgement = () => {
    applyFilter(app);
  };

  app.setGenerating = (on) => {
    app.generating = on;
    document.querySelectorAll('[data-generate]').forEach((button) => {
      button.disabled = on || button.hasAttribute('data-blocked-reason');
    });
  };

  // Is the selection this factor or below it (parent links, any analysis
  // data on the page; a walk that remembers what it visited)?
  const selectionAtOrBelow = (node) => {
    const seen = new Set();
    let current = getNode(app.model, app.state.sel);
    while (current && !seen.has(current.id)) {
      if (current.id === node.id) return true;
      seen.add(current.id);
      current = current.parentId === null ? null : getNode(app.model, current.parentId);
    }
    return false;
  };

  // Show the result of a legacy change. Until the partial update exists the
  // page is reloaded; the state (hash, scroll, filter) comes back.
  app.refresh = (options = {}) => {
    if (options.select !== undefined && options.select !== null) {
      app.state.sel = String(options.select);
      if (options.level) app.state.step = Math.min(Math.max(Number(options.level) + 1, 2), 4);
    } else if (options.deleted !== undefined && options.deleted !== null) {
      const deleted = getNode(app.model, options.deleted);
      if (deleted && selectionAtOrBelow(deleted)) {
        const parent = deleted.parentId === null || deleted.parentId === deleted.id
          ? null : getNode(app.model, deleted.parentId);
        app.state.sel = parent ? String(parent.id) : 'top';
        app.state.step = parent ? stepForNode(parent) : 1;
      }
    }
    writeHash(app.state);
    app.saveSession();
    window.location.reload();
  };

  installBridge(app);
  initFilter(app, session.filter);
  applyView(app);
  applyStep(app);
  applySelection(app);
  applyCounts(app);
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
    const nodeId = button.dataset.nodeId ? Number(button.dataset.nodeId) : null;
    const legacy = window;
    if (action === 'legacy-generate' && typeof legacy.generateFactors === 'function') {
      legacy.generateFactors(app.analysisId, level);
    } else if (action === 'legacy-generate-additional' && typeof legacy.generateAdditional === 'function') {
      legacy.generateAdditional(app.analysisId, parentId, level);
    } else if (action === 'legacy-add' && typeof legacy.showAddNodeModal === 'function') {
      legacy.showAddNodeModal(app.analysisId, parentId, level);
    } else if (action === 'legacy-detail' && typeof legacy.openNodeDetail === 'function') {
      legacy.openNodeDetail(nodeId);
    } else if (action === 'legacy-delete' && typeof legacy.deleteNode === 'function') {
      legacy.deleteNode(nodeId, app.analysisId);
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
      app.select(button.dataset.select === 'top' ? 'top' : button.dataset.nodeId, {
        source: SOURCES[button.dataset.role] || null,
        focusWarning: button.dataset.focus === 'warning',
      });
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

  // The legacy saveTopEvent updates data-saved; the step status, the top
  // event in the outlines and the inspector follow it.
  const topInput = document.getElementById('topEventInput');
  if (topInput) {
    new MutationObserver(() => {
      applyTopEvent(topInput.dataset.saved);
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
