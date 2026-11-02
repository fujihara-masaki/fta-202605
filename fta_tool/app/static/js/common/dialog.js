// Modal dialogs on the native <dialog> element (showModal): the rest of the
// page becomes inert, Tab stays inside, and Esc is handled as the "cancel"
// choice (編集を続ける / キャンセル). Focus goes to the safe choice when the
// dialog opens and returns to the element that opened it when it closes
// (plan 5.7). All text is inserted with DOM APIs, never innerHTML.

import { el, append, paragraphs, focusElement } from './dom.js';

let sequence = 0;

const VARIANT_CLASSES = {
  primary: 'ui-btn--primary',
  danger: 'ui-btn--danger',
  'danger-outline': 'ui-btn--danger-outline',
};

/**
 * @param {object} options
 * @param {string} options.title
 * @param {Array<string|Node>|string|Node} [options.body]
 * @param {Array<{id: string, label: string, variant?: string, autofocus?: boolean}>} options.actions
 * @param {Element} [options.invoker] element that opened the dialog (focus returns here)
 * @param {() => Element|null} [options.fallbackFocus] used when the invoker is gone
 * @param {(actionId: string, dialog: object) => void} [options.onAction]
 * @param {string} [options.cancelAction] result used for Esc (default 'cancel')
 */
export function openDialog({
  title,
  body = [],
  actions = [],
  invoker = null,
  fallbackFocus = null,
  onAction = null,
  cancelAction = 'cancel',
  className = '',
}) {
  sequence += 1;
  const id = `ui-dialog-${sequence}`;
  const opener = invoker || document.activeElement;

  const dialog = el('dialog', {
    class: `ui-dialog ${className}`.trim(),
    id,
    'aria-labelledby': `${id}-title`,
    'aria-describedby': `${id}-body`,
  });
  const heading = el('h2', { class: 'ui-dialog__title', id: `${id}-title` }, title);
  const bodyEl = el('div', { class: 'ui-dialog__body', id: `${id}-body` }, paragraphs(body));
  const status = el('p', { class: 'ui-dialog__status', role: 'status' });
  const error = el('div', { class: 'ui-dialog__error', role: 'alert' });
  const footer = el('div', { class: 'ui-dialog__actions' });

  const buttons = new Map();
  for (const action of actions) {
    const button = el('button', {
      type: 'button',
      class: `ui-btn ${VARIANT_CLASSES[action.variant] || ''}`.trim(),
      dataset: { dialogAction: action.id },
    }, action.label);
    buttons.set(action.id, button);
    footer.append(button);
  }
  dialog.append(heading, bodyEl, status, error, footer);
  document.body.append(dialog);

  let busy = false;
  let closed = false;
  let resolveResult;
  const result = new Promise((resolve) => {
    resolveResult = resolve;
  });

  const restoreFocus = () => {
    if (focusElement(opener)) return;
    const fallback = typeof fallbackFocus === 'function' ? fallbackFocus() : null;
    focusElement(fallback);
  };

  const finish = (value, { restore = true } = {}) => {
    if (closed) return;
    closed = true;
    if (dialog.open) dialog.close();
    dialog.remove();
    if (restore) restoreFocus();
    resolveResult(value);
  };

  const controller = {
    element: dialog,
    result,
    button: (actionId) => buttons.get(actionId),
    isOpen: () => !closed,
    isBusy: () => busy,
    setBusy(on, message = '') {
      busy = Boolean(on);
      for (const button of buttons.values()) button.disabled = busy;
      status.textContent = busy ? message : '';
      dialog.setAttribute('aria-busy', busy ? 'true' : 'false');
    },
    setStatus(message = '') {
      status.textContent = message;
    },
    // items: string | Node | Array — the first entry becomes the lead line,
    // further string entries become a bullet list.
    setError(items) {
      error.replaceChildren();
      const list = [items].flat().filter(Boolean);
      if (!list.length) return;
      const box = el('div', { class: 'ui-dialog__error-box' });
      const [lead, ...rest] = list;
      append(box, lead instanceof Node ? lead : el('p', {}, lead));
      if (rest.length) {
        box.append(el('ul', {}, rest.map((item) => el('li', {}, item))));
      }
      error.append(box);
    },
    close(value, { restoreFocus: restore = true } = {}) {
      finish(value, { restore });
    },
  };

  footer.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-dialog-action]');
    if (!button || busy || closed) return;
    const actionId = button.dataset.dialogAction;
    if (onAction) onAction(actionId, controller);
    else controller.close(actionId);
  });

  // Esc: treat as the cancel choice; ignore it while an operation is running.
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    if (busy || closed) return;
    if (onAction) onAction(cancelAction, controller);
    else controller.close(cancelAction);
  });
  // The browser may still close the dialog on its own (e.g. repeated Esc).
  dialog.addEventListener('close', () => {
    if (!closed) finish(cancelAction);
  });

  dialog.showModal();
  const initial = actions.find((action) => action.autofocus);
  if (initial) buttons.get(initial.id).focus();
  return controller;
}
