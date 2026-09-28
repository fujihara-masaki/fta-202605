// Notifications (bottom centre). Success/info close after 3 s and warnings
// after 6 s as before; errors stay until the user closes them (J-24).
// Screen readers are told through two live regions rendered by base.html:
// #ui-live-status (role="status") and #ui-live-alert (role="alert").
//
// The stack stays short: the same notification again (e.g. a save that keeps
// failing) updates the one already shown with a repeat count, and beyond
// MAX_TOASTS the oldest notifications are closed — non-errors first, then
// errors — so persistent errors cannot pile up and cover the page. The
// newest notification is never the one closed.

import { el } from './dom.js';

const KIND_LABELS = {
  success: '完了',
  info: 'お知らせ',
  warning: '注意',
  error: 'エラー',
};

export const AUTO_CLOSE_MS = {
  success: 3000,
  info: 3000,
  warning: 6000,
};

export const MAX_TOASTS = 5;

const controllers = new WeakMap();

function stackElement() {
  let stack = document.getElementById('ui-toasts');
  if (!stack) {
    stack = el('div', { id: 'ui-toasts', class: 'ui-toast-stack' });
    document.body.append(stack);
  }
  return stack;
}

export function announce(message, { assertive = false } = {}) {
  const region = document.getElementById(assertive ? 'ui-live-alert' : 'ui-live-status');
  if (!region) return;
  // Clear first so the same text is announced again when repeated.
  region.textContent = '';
  window.setTimeout(() => {
    region.textContent = message;
  }, 50);
}

function enforceLimit(stack, newest) {
  const toasts = [...stack.querySelectorAll('.ui-toast')];
  const excess = toasts.length - MAX_TOASTS;
  if (excess <= 0) return;
  const candidates = toasts.filter((toast) => toast !== newest);
  const oldestFirst = [
    ...candidates.filter((toast) => toast.dataset.toastType !== 'error'),
    ...candidates.filter((toast) => toast.dataset.toastType === 'error'),
  ];
  oldestFirst.slice(0, excess).forEach((toast) => {
    const controller = controllers.get(toast);
    if (controller) controller.close();
    else toast.remove();
  });
}

export function notify(message, { type = 'success' } = {}) {
  const kind = KIND_LABELS[type] ? type : 'info';
  const text = String(message);
  const stack = stackElement();
  const label = `${KIND_LABELS[kind]}：${text}`;

  const same = [...stack.querySelectorAll('.ui-toast')].find(
    (toast) => toast.dataset.toastType === kind && toast.dataset.message === text,
  );
  if (same && controllers.has(same)) {
    const controller = controllers.get(same);
    controller.repeat();
    announce(label, { assertive: kind === 'error' });
    return controller.handle;
  }

  const closeButton = el('button', { type: 'button', class: 'ui-toast__close' }, '閉じる');
  const count = el('span', { class: 'ui-toast__count', hidden: true });
  const toast = el(
    'div',
    { class: `ui-toast ui-toast--${kind}`, dataset: { toastType: kind, message: text } },
    el('span', { class: 'ui-toast__kind' }, KIND_LABELS[kind]),
    el('p', { class: 'ui-toast__message' }, text, count),
    closeButton,
  );

  let timer = null;
  let closed = false;
  let repeats = 1;
  const close = () => {
    if (closed) return;
    closed = true;
    window.clearTimeout(timer);
    toast.remove();
  };
  const schedule = () => {
    const delay = AUTO_CLOSE_MS[kind];
    if (!delay || closed) return;
    window.clearTimeout(timer);
    timer = window.setTimeout(close, delay);
  };
  const handle = { element: toast, close };
  controllers.set(toast, {
    handle,
    close,
    repeat() {
      repeats += 1;
      count.textContent = `（${repeats}回）`;
      count.hidden = false;
      stack.append(toast); // move to the newest position
      schedule();
    },
  });

  closeButton.addEventListener('click', close);
  // Pause auto-close while the pointer or focus is on the notification.
  toast.addEventListener('mouseenter', () => window.clearTimeout(timer));
  toast.addEventListener('mouseleave', schedule);
  toast.addEventListener('focusin', () => window.clearTimeout(timer));
  toast.addEventListener('focusout', schedule);

  stack.append(toast);
  enforceLimit(stack, toast);
  announce(label, { assertive: kind === 'error' });
  schedule();
  return handle;
}
