// Keeping every representation of a factor in step (plan 3.4-3): the
// structure navigation, the work list and its parent groups, the tree, the
// table and the inspector carry data-node-id, and one function per concern
// updates all of them — selection, work step, view tab, judgement, counts.

import { generationTargets, getNode, judgementLabel, stepCounts } from './model.js';

const ITEM_SELECTOR = '[data-role$="-item"]';

export function applySelection(app) {
  document.querySelectorAll('[data-action="select"][aria-current]').forEach((element) => {
    element.removeAttribute('aria-current');
  });
  document.querySelectorAll(`${ITEM_SELECTOR}.is-selected`).forEach((element) => {
    element.classList.remove('is-selected');
  });
  if (app.state.sel === 'top') {
    document.querySelectorAll('[data-action="select"][data-select="top"]').forEach((element) => {
      element.setAttribute('aria-current', 'true');
    });
    return;
  }
  const id = app.state.sel;
  // The 要確認 buttons select too but are not the factor's own entry.
  document.querySelectorAll(`[data-action="select"][data-node-id="${id}"]:not([data-focus])`).forEach((element) => {
    element.setAttribute('aria-current', 'true');
  });
  document.querySelectorAll(`${ITEM_SELECTOR}[data-node-id="${id}"]`).forEach((element) => {
    element.classList.add('is-selected');
  });
}

export function applyStep(app) {
  const { step } = app.state;
  document.querySelectorAll('[data-action="step"][data-step]').forEach((button) => {
    if (button.closest('[data-inspector-body]')) return;
    if (Number(button.dataset.step) === step) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
  document.querySelectorAll('[data-step-panel]').forEach((panel) => {
    panel.hidden = Number(panel.dataset.stepPanel) !== step;
  });
  const anomalies = document.querySelector('[data-work-anomalies]');
  if (anomalies) {
    anomalies.hidden = !(step >= 2 && step <= 4) || !anomalies.querySelector('[data-node-id]');
  }
}

export function applyView(app) {
  const { view } = app.state;
  document.querySelectorAll('[data-view-tab]').forEach((tab) => {
    const selected = tab.dataset.viewTab === view;
    tab.setAttribute('aria-selected', selected ? 'true' : 'false');
    tab.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll('[data-view-panel]').forEach((panel) => {
    panel.hidden = panel.dataset.viewPanel !== view;
  });
}

// Step statuses (②〜④) and the targets of the normal generation (③・④),
// counted from the embedded data.
export function applyCounts(app) {
  for (const level of [1, 2, 3]) {
    const status = document.querySelector(`[data-step-status="${level + 1}"]`);
    if (status) {
      const counts = stepCounts(app.model, level);
      status.textContent = `${counts.total}件・未評価${counts.unevaluated}`;
    }
  }
  for (const level of [2, 3]) {
    const { targets, excluded } = generationTargets(app.model, level);
    const count = document.querySelector(`[data-target-count="${level}"]`);
    if (count) count.textContent = String(targets.length);
    const box = document.querySelector(`[data-target-excluded="${level}"]`);
    if (box) {
      box.hidden = excluded.length === 0;
      const number = box.querySelector('[data-target-excluded-count]');
      if (number) number.textContent = String(excluded.length);
    }
  }
}

export function applyJudgement(nodeId, value) {
  document.querySelectorAll(`${ITEM_SELECTOR}[data-node-id="${nodeId}"]`).forEach((element) => {
    element.dataset.judgement = value;
  });
  document.querySelectorAll(`[data-judgement-chip][data-node-id="${nodeId}"]`).forEach((chip) => {
    chip.textContent = judgementLabel(value);
    chip.className = `ui-chip ui-chip--${value}`;
  });
  document.querySelectorAll(`[data-judgement-toggle][data-node-id="${nodeId}"] [data-value]`).forEach((button) => {
    button.setAttribute('aria-pressed', button.dataset.value === value ? 'true' : 'false');
  });
}

export function applyTopEvent(saved) {
  const text = String(saved ?? '').trim();
  const status = document.querySelector('[data-step-status="1"]');
  if (status) status.textContent = text ? '頂上事象：入力済み' : '頂上事象：未入力';
  document.querySelectorAll('[data-action="select"][data-select="top"] .edit-outline__title').forEach((title) => {
    title.textContent = text ? saved : '（頂上事象が未設定です）';
  });
}

// Bring the selected factor into view in the panes other than the one the
// selection came from.
export function revealSelection(app, source) {
  const id = app.state.sel;
  const selector = id === 'top'
    ? '[data-action="select"][data-select="top"]'
    : `[data-action="select"][data-node-id="${id}"]:not([data-focus])`;
  const places = {
    nav: document.querySelector(`#edit-nav ${selector}`),
    work: document.querySelector(`#edit-panel-work ${selector}`),
    tree: document.querySelector(`#edit-panel-tree ${selector}`),
    table: document.querySelector(`#edit-panel-table ${selector}`),
  };
  for (const [place, element] of Object.entries(places)) {
    if (!element || place === source) continue;
    if (place !== 'nav' && place !== app.state.view) continue;
    if (element.offsetParent === null) continue;
    element.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
}

export function nodeTitle(app, id) {
  const node = getNode(app.model, id);
  return node ? node.title : null;
}
