// Where the screen state is kept (plan 5.5):
// - the selected factor, the work step and the view tab in the URL hash
//   (#sel=123&step=3&view=work; sel=top is the top event), changed with
//   history.replaceState so no history entries are added;
// - scroll positions and the filter per analysis in sessionStorage through
//   common/storage.js, which never throws: without storage the screen works
//   with the defaults.
// Drafts are never stored in the browser. The keys of the old screen
// (ftaTreeOpen_… and the like) are not read.

import { sessionStore } from '../../common/storage.js';
import { firstRoot, getNode, stepForNode } from './model.js';

export const VIEWS = ['work', 'tree', 'table'];

export function readHash(hash = window.location.hash) {
  const params = new URLSearchParams(String(hash || '').replace(/^#/, ''));
  return { sel: params.get('sel'), step: params.get('step'), view: params.get('view') };
}

// Default display: ② with the first 一次要因, or ① with the top event when
// there is none (e.g. right after 作成して編集へ).
export function defaultState(model) {
  const root = firstRoot(model);
  return root ? { sel: String(root.id), step: 2, view: 'work' } : { sel: 'top', step: 1, view: 'work' };
}

// The hash is checked against the data. An unknown factor or a malformed
// value gives the default display; an invalid step or view falls back for
// that part only. No error is shown.
export function stateFromHash(model, hash) {
  const parsed = readHash(hash);
  if (!parsed.sel) return defaultState(model);
  const node = parsed.sel === 'top' ? null : getNode(model, parsed.sel);
  if (parsed.sel !== 'top' && !node) return defaultState(model);
  const step = /^[1-5]$/.test(parsed.step || '') ? Number(parsed.step) : (node ? stepForNode(node) : 1);
  const view = VIEWS.includes(parsed.view) ? parsed.view : 'work';
  return { sel: node ? String(node.id) : 'top', step, view };
}

export function writeHash(state) {
  const hash = `#sel=${encodeURIComponent(state.sel)}&step=${state.step}&view=${state.view}`;
  if (window.location.hash === hash) return;
  try {
    window.history.replaceState(window.history.state, '', hash);
  } catch {
    // The screen keeps working; only a reload would lose the state.
  }
}

const sessionKey = (analysisId) => `fta:edit:v1:${analysisId}`;

export function loadSession(analysisId) {
  const value = sessionStore.getJSON(sessionKey(analysisId), null);
  return value && typeof value === 'object' ? value : {};
}

export function saveSession(analysisId, value) {
  return sessionStore.setJSON(sessionKey(analysisId), value);
}
