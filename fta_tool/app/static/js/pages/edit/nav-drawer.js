// The structure navigation folded below 1280px (PR-7, J-20, plan 5.9.4).
//
// From 1280px on, the navigation is the left pane. Narrower (css/edit.css,
// the same media query as FOLDED), it is hidden and the button 「構造を表示」
// at the start of the header shows it over the left of the work area (below
// the header, so it never covers the button):
// - the button tells its state (aria-expanded) and opens or closes it;
//   opening moves the focus to the factor selected in it (else its heading);
// - Esc in it (or on the button) closes it and gives the focus back to the
//   button; a click or the focus elsewhere on the screen closes it without
//   moving the focus;
// - choosing a factor in it closes it once the switch was allowed (after the
//   R-01 check: 編集を続ける leaves it open with the focus where it was); the
//   focus goes to the button, since the chosen element is hidden then.
// The navigation is in the tab order only while it is shown (display: none
// otherwise), after the header and the work steps.

export const FOLDED = '(width < 1280px)';

export function createNavDrawer(root) {
  const nav = root.querySelector('#edit-nav');
  const toggle = root.querySelector('[data-nav-toggle]');
  const media = window.matchMedia(FOLDED);
  const drawer = {
    isFolded: () => media.matches,
    isOpen: () => Boolean(nav && nav.hasAttribute('data-open')),
    open,
    close,
    afterSelect,
  };
  if (!nav || !toggle) return drawer;

  const render = () => {
    const open = drawer.isOpen() && drawer.isFolded();
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.textContent = open ? '構造を閉じる' : '構造を表示';
  };

  function open() {
    if (!drawer.isFolded()) return;
    nav.setAttribute('data-open', '');
    render();
    const current = nav.querySelector('[data-action="select"][aria-current]');
    const target = current || nav.querySelector('#edit-nav-heading');
    if (target) {
      target.focus();
      if (current) current.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
  }

  function close({ focusToggle = false } = {}) {
    if (!drawer.isOpen()) return;
    nav.removeAttribute('data-open');
    render();
    if (focusToggle && drawer.isFolded()) toggle.focus();
  }

  // After app.select() from the navigation (the switch was allowed).
  function afterSelect() {
    if (!drawer.isFolded() || !drawer.isOpen()) return;
    const active = document.activeElement;
    const focusWasHere = !active || active === document.body || nav.contains(active);
    close({ focusToggle: focusWasHere });
  }

  // Elsewhere on the screen: not the navigation, its button, a dialog or a
  // notification (those are over everything).
  const elsewhere = (target) => target instanceof Element && !nav.contains(target) && !toggle.contains(target)
    && !target.closest('dialog, .ui-toast-stack');

  toggle.addEventListener('click', () => {
    if (drawer.isOpen()) close({ focusToggle: true });
    else open();
  });
  const onEscape = (event) => {
    if (event.key !== 'Escape' || event.isComposing || !drawer.isFolded() || !drawer.isOpen()) return;
    event.preventDefault();
    close({ focusToggle: true });
  };
  nav.addEventListener('keydown', onEscape);
  toggle.addEventListener('keydown', onEscape);
  document.addEventListener('pointerdown', (event) => {
    if (drawer.isOpen() && drawer.isFolded() && elsewhere(event.target)) close();
  });
  document.addEventListener('focusin', (event) => {
    if (drawer.isOpen() && drawer.isFolded() && elsewhere(event.target)) close();
  });
  // Wider than 1280px again: the left pane; it starts folded next time.
  media.addEventListener('change', () => {
    if (!media.matches) nav.removeAttribute('data-open');
    render();
  });
  render();
  return drawer;
}
