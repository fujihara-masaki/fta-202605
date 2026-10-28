// The operations a generation holds back (PR-6, J-01; plan 5.3, 5.9.1).
// While a generation is prepared, runs or is being finished, the screen
// refuses every write and every way off the page: judgements, the save
// buttons (① and the inspector), manual add, delete, another generation,
// exports and in-page links. Browsing stays free: selecting factors, the
// work steps, the view tabs, the filter, scrolling and typing drafts.
//
// This module only shows the state: buttons are disabled (`data-gen-locked`
// marks the ones disabled here, so only those are given back) and links get
// aria-disabled. Every operation also checks the phase where it starts and
// again right before it sends (judgement.js, step1.js, factor-editor.js,
// add-dialog.js, delete-dialog.js, the link guard of common/unsaved.js) —
// a button that was enabled when it was drawn never decides alone.
// The page root carries data-generation-phase for the styles.
// This is a restriction inside this page only: another tab, another worker
// or a direct API call are not held back by it (plan 2.4, 5.3).

import { getGenerationPhase } from '../../common/unsaved.js';

const BUTTONS = [
  '[data-action="judgement"]',
  '[data-action="add"]',
  '[data-action="delete"]',
  '[data-generate]',
  '[data-save-button]',
].join(', ');

// Links that leave the page or export: the header's menu, 一覧へ, the export
// links (the export menu's and ⑤'s).
const LINKS = '.app-header a[href], [data-leave-link], a[href][download]';

export const LOCKED_TITLE = '生成中は使えません（生成が終わると使えます）';

export function generationUnderWay() {
  return getGenerationPhase() !== 'idle';
}

export function applyRestrictions(app) {
  const phase = getGenerationPhase();
  const on = phase !== 'idle';
  if (app && app.root) app.root.dataset.generationPhase = phase;
  if (on) {
    document.querySelectorAll(BUTTONS).forEach((button) => {
      if (button.disabled || button.dataset.genLocked) return;
      button.disabled = true;
      button.dataset.genLocked = 'true';
      if (!button.title) {
        button.title = LOCKED_TITLE;
        button.dataset.genTitle = 'true';
      }
    });
    document.querySelectorAll(LINKS).forEach((link) => {
      if (link.dataset.genLocked) return;
      link.setAttribute('aria-disabled', 'true');
      link.dataset.genLocked = 'true';
    });
    return;
  }
  document.querySelectorAll('[data-gen-locked]').forEach((element) => {
    delete element.dataset.genLocked;
    if (element.dataset.genTitle) {
      element.removeAttribute('title');
      delete element.dataset.genTitle;
    }
    if (element.tagName === 'A') {
      element.removeAttribute('aria-disabled');
      return;
    }
    // Back as it was, unless another reason holds it now: the analysis is
    // gone, or the server said it cannot act (J-25, data-blocked-reason).
    element.disabled = Boolean(app && app.gone) || element.hasAttribute('data-blocked-reason');
  });
}
