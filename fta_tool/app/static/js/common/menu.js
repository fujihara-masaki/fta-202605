// Disclosure menu: a button (aria-expanded / aria-controls) that shows a list
// of links. Esc closes it and returns focus to the button (plan 5.7).
// The panel is positioned with position: fixed from the button's rectangle so
// that it is not clipped by a scrolling table wrapper.
//
// Markup (see _macros.html export_menu):
//   <div data-ui-menu>
//     <button data-ui-menu-button aria-expanded="false" aria-controls="p1">…</button>
//     <div id="p1" data-ui-menu-panel hidden> … <a class="ui-menu__item">…</a> … </div>
//   </div>

let openMenu = null;

function items(panel) {
  return [...panel.querySelectorAll('a[href], button:not([disabled])')];
}

function position(button, panel) {
  const gap = 4;
  const margin = 8;
  const rect = button.getBoundingClientRect();
  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = document.documentElement.clientHeight;
  panel.style.maxHeight = '';
  const width = panel.offsetWidth;
  const height = panel.offsetHeight;

  let left = rect.right - width;
  left = Math.max(margin, Math.min(left, viewportWidth - width - margin));

  let top = rect.bottom + gap;
  const spaceBelow = viewportHeight - rect.bottom - gap - margin;
  const spaceAbove = rect.top - gap - margin;
  if (height > spaceBelow && spaceAbove > spaceBelow) {
    top = Math.max(margin, rect.top - gap - height);
    if (height > spaceAbove) panel.style.maxHeight = `${spaceAbove}px`;
  } else if (height > spaceBelow) {
    panel.style.maxHeight = `${Math.max(spaceBelow, 120)}px`;
  }
  panel.style.left = `${Math.round(left)}px`;
  panel.style.top = `${Math.round(top)}px`;
}

function setup(root) {
  if (root.dataset.uiMenuReady) return;
  root.dataset.uiMenuReady = '1';
  const button = root.querySelector('[data-ui-menu-button]');
  const panel = root.querySelector('[data-ui-menu-panel]');
  if (!button || !panel) return;

  const reposition = () => position(button, panel);

  const onOutsidePointer = (event) => {
    if (!root.contains(event.target)) close({ focusButton: false });
  };

  function open({ focusFirst = false } = {}) {
    if (openMenu && openMenu !== api) openMenu.close({ focusButton: false });
    panel.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    reposition();
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    document.addEventListener('pointerdown', onOutsidePointer, true);
    openMenu = api;
    if (focusFirst) items(panel)[0]?.focus();
  }

  function close({ focusButton = true } = {}) {
    if (panel.hidden) return;
    panel.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    window.removeEventListener('scroll', reposition, true);
    window.removeEventListener('resize', reposition);
    document.removeEventListener('pointerdown', onOutsidePointer, true);
    if (openMenu === api) openMenu = null;
    if (focusButton) button.focus();
  }

  const api = { open, close, root };

  button.addEventListener('click', () => {
    if (panel.hidden) open();
    else close({ focusButton: false });
  });

  root.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    const list = items(panel);
    if (event.target === button && event.key === 'ArrowDown') {
      event.preventDefault();
      open({ focusFirst: true });
      return;
    }
    if (panel.hidden || !panel.contains(event.target)) return;
    const index = list.indexOf(event.target);
    let next = null;
    if (event.key === 'ArrowDown') next = list[(index + 1) % list.length];
    else if (event.key === 'ArrowUp') next = list[(index - 1 + list.length) % list.length];
    else if (event.key === 'Home') next = list[0];
    else if (event.key === 'End') next = list[list.length - 1];
    if (next) {
      event.preventDefault();
      next.focus();
    }
  });

  // Close when focus leaves the menu (e.g. Tab past the last item).
  root.addEventListener('focusout', (event) => {
    if (panel.hidden) return;
    const next = event.relatedTarget;
    if (next && !root.contains(next)) close({ focusButton: false });
  });

  // Choosing an item (a download link) closes the menu and returns focus.
  panel.addEventListener('click', (event) => {
    if (event.target.closest('a[href]')) {
      window.setTimeout(() => close(), 0);
    }
  });
}

export function initMenus(scope = document) {
  scope.querySelectorAll('[data-ui-menu]').forEach(setup);
}

export function closeOpenMenu(options) {
  if (openMenu) openMenu.close(options);
}
