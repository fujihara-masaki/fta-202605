// Entry point loaded on every screen (base.html): shared behaviour that does
// not depend on the screen. Screen scripts import the same modules, so the
// unsaved-change registry and the open menu are shared.

import { installLinkGuard } from './unsaved.js';
import { initMenus } from './menu.js';

installLinkGuard();
initMenus(document);
