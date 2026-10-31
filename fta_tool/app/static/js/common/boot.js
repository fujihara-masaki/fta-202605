// Entry point loaded on every screen (base.html): shared behaviour that does
// not depend on the screen. Screen scripts import the same modules, so the
// unsaved-change registry and the open menu are shared. The focused control
// is kept in view with its outline (notify.js, PR-7).

import { installLinkGuard } from './unsaved.js';
import { initMenus } from './menu.js';
import { installFocusView } from './notify.js';

installLinkGuard();
initMenus(document);
installFocusView();
