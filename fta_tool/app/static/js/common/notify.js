// Notifications (bottom centre). Success/info close after 3 s and warnings
// after 6 s as before; errors stay until the user closes them (J-24).
// Screen readers are told through two live regions rendered by base.html:
// #ui-live-status (role="status") and #ui-live-alert (role="alert").

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

const MAX_TOASTS = 5;

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

export function notify(message, { type = 'success' } = {}) {
  const kind = KIND_LABELS[type] ? type : 'info';
  const stack = stackElement();
  const closeButton = el('button', { type: 'button', class: 'ui-toast__close' }, '閉じる');
  const toast = el(
    'div',
    { class: `ui-toast ui-toast--${kind}`, dataset: { toastType: kind } },
    el('span', { class: 'ui-toast__kind' }, KIND_LABELS[kind]),
    el('p', { class: 'ui-toast__message' }, message),
    closeButton,
  );

  let timer = null;
  let closed = false;
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

  closeButton.addEventListener('click', close);
  // Pause auto-close while the pointer or focus is on the notification.
  toast.addEventListener('mouseenter', () => window.clearTimeout(timer));
  toast.addEventListener('mouseleave', schedule);
  toast.addEventListener('focusin', () => window.clearTimeout(timer));
  toast.addEventListener('focusout', schedule);

  stack.append(toast);
  // Keep the stack short: drop the oldest non-error notifications first.
  const toasts = [...stack.querySelectorAll('.ui-toast')];
  const excess = toasts.length - MAX_TOASTS;
  if (excess > 0) {
    toasts.filter((t) => t.dataset.toastType !== 'error').slice(0, excess).forEach((t) => t.remove());
  }

  announce(`${KIND_LABELS[kind]}：${message}`, { assertive: kind === 'error' });
  schedule();
  return { element: toast, close };
}
