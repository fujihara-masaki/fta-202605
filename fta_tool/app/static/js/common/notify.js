// Notifications (bottom centre). Success/info close after 3 s and warnings
// after 6 s as before; errors stay until the user closes them (J-24).
// Screen readers are told through two live regions rendered by base.html:
// #ui-live-status (role="status") and #ui-live-alert (role="alert").
//
// The stack stays short: the same notification again (e.g. a save that keeps
// failing) updates the one already shown with a repeat count, and beyond
// MAX_TOASTS the oldest notifications are closed — non-errors first, then
// errors — so persistent errors cannot pile up. The newest notification is
// never the one closed.
//
// The stack has a room of its own below the main area (on the edit screen
// below the work area; css/base.css, css/edit.css), so it never covers the
// screen (PR-7, plan 8.7 condition 4). It takes at most 30 % of the height
// (25 % below 700px) and scrolls inside: the newest is scrolled into view.
//
// The control that has the focus stays in view with its focus outline
// (plan 8.7 conditions 3 and 4): keepInView() scrolls the one area it
// scrolls in by the pixels missing, when the stack grew (that area got
// lower) and after a key that moved the focus (installFocusView, from
// boot.js: the browser scrolls a control reached with Tab or an arrow key
// only to the edge of its area, where the outline is cut). The focus, the
// input and its selection are never touched; a focus the app gives with
// preventScroll (after a partial update) keeps its scroll position.

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

const MARGIN = 8; // the focus outline (3px, 2px apart) and a little air

const MOVING_KEYS = new Set(['Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown']);

// The nearest ancestor that scrolls on this axis (overflow auto/scroll with
// more content than room), or null: a table that scrolls sideways is not
// the area that scrolls the page down.
function scrollParent(element, axis) {
  for (let box = element.parentElement; box; box = box.parentElement) {
    const style = getComputedStyle(box);
    const vertical = axis === 'y';
    if (/(auto|scroll)/.test(vertical ? style.overflowY : style.overflowX)
        && (vertical ? box.scrollHeight > box.clientHeight : box.scrollWidth > box.clientWidth)) return box;
  }
  return null;
}

// How far to scroll one axis so that [start, end] (with the margin) is in
// [low, high]; a span larger than the area shows its start.
function shift(start, end, low, high) {
  if (end - start + 2 * MARGIN > high - low) return start - MARGIN < low || start > high ? start - MARGIN - low : 0;
  if (end + MARGIN > high) return end + MARGIN - high;
  if (start - MARGIN < low) return start - MARGIN - low;
  return 0;
}

export function keepInView(element) {
  if (!element || element === document.body || !element.isConnected || element.closest('dialog')) return;
  const r = element.getBoundingClientRect();
  if (!r.width && !r.height) return;
  const down = scrollParent(element, 'y');
  if (down) {
    const top = down.getBoundingClientRect().top + down.clientTop;
    const dy = shift(r.top, r.bottom, top, top + down.clientHeight);
    if (dy) down.scrollTop += dy;
  }
  const across = scrollParent(element, 'x');
  if (across) {
    const left = across.getBoundingClientRect().left + across.clientLeft;
    const dx = shift(r.left, r.right, left, left + across.clientWidth);
    if (dx) across.scrollLeft += dx;
  }
}

// After the stack grew: the control with the focus (not one of the
// notifications') is kept in view.
function keepFocusInView(stack) {
  const active = document.activeElement;
  if (active && !stack.contains(active)) keepInView(active);
}

let keyMoving = false;

export function installFocusView() {
  document.addEventListener('keydown', (event) => {
    if (!MOVING_KEYS.has(event.key)) return;
    keyMoving = true;
    window.setTimeout(() => {
      keyMoving = false;
    }, 0);
  }, true);
  document.addEventListener('focusin', (event) => {
    if (keyMoving) keepInView(event.target);
  }, true);
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
      stack.scrollTop = stack.scrollHeight;
      keepFocusInView(stack);
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
  stack.scrollTop = stack.scrollHeight;
  keepFocusInView(stack);
  announce(label, { assertive: kind === 'error' });
  schedule();
  return handle;
}
