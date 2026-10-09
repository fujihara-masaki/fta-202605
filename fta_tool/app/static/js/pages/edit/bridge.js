// The one place where the legacy app.js reaches the new screen. Since PR-5
// only generation still runs through app.js (PR-6 replaces it; detail
// editing, manual add and delete are the screen's own: edit/factor-editor.js,
// add-dialog.js, delete-dialog.js). window.ftaEditBridge gives it what it
// needs on the new page:
//   refresh(options)        show the result of a change by a partial update
//   generationTargets(lv)   parents of the normal generation, from the data:
//                           {targets: ids, excluded: count} (J-07, J-25)
//   checkParent(id, lv)     may the factor be the parent of a generation of
//                           level `lv`: {allowed, reason} (edit/permissions.js)
//   genHost(id)             where a parent's generation badge goes
//   setGenerating(on)       generation buttons off while a generation runs
//   notify(message, type)   app.js's messages in the shared notifications
//                           (J-24, moved forward to PR-3 by 判断4): the same
//                           text and kind ('success' | 'warning' | 'error')
//   beginWrite()            a save the page shows at once starts; call the
//                           function it returns when it has ended. Tracked
//                           like a judgement: no update is fetched
//                           meanwhile, and one fetched before it is not
//                           applied (plan 3.4-5, P-3). ① and the inspector's
//                           factor save use it themselves (step1.js,
//                           factor-source.js)
//   beginGeneration(level)  PR-4: before a generation sends anything —
//                           waits for saves in flight and saves ① as the
//                           level needs (edit/generation.js). Resolves to
//                           null (nothing may be generated; the reason was
//                           shown) or {end()}, to call once the generation
//                           and its result are completely done
//
// checkParent answers from the summary the server computed for the data of
// the page (app/detail_view.py; 判断3): the buttons show the same answer, and
// app.js asks again right before it sends a request. This is the screen's own
// check on the data as fetched; it does not make the existing APIs safe.

import { notify } from '../../common/notify.js';
import { generationTargets } from './model.js';
import { checkParent } from './permissions.js';

// The kinds app.js's showToast knew; anything else was shown as success.
const LEGACY_TYPES = new Set(['success', 'warning', 'error']);

export function installBridge(app) {
  const bridge = {
    refresh: (options) => app.refresh(options || {}),
    generationTargets: (level) => {
      const { targets, excluded } = generationTargets(app.model, Number(level));
      return { targets: targets.map((node) => node.id), excluded: excluded.length };
    },
    checkParent: (id, level) => checkParent(app, id, level),
    genHost: (id) => document.querySelector(`[data-gen-host="${Number(id)}"]`),
    setGenerating: (on) => app.setGenerating(Boolean(on)),
    notify: (message, type) => {
      notify(message, { type: LEGACY_TYPES.has(type) ? type : 'success' });
    },
    beginWrite: () => app.beginWrite(),
    beginGeneration: (level) => app.beginGeneration(Number(level)),
  };
  window.ftaEditBridge = Object.freeze(bridge);
  return bridge;
}
