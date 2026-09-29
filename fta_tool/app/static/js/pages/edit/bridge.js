// The one place where the legacy app.js reaches the new screen. PR-3 still
// runs detail editing, manual add, delete and generation through app.js
// with its dialogs (plan 7.2); window.ftaEditBridge gives those functions
// what they need on the new page:
//   refresh(options)        show the result of a change ({select, level} after
//                           a manual add, {deleted} after a delete)
//   generationTargets(lv)   parents of the normal generation, from the data
//   genHost(id)             where a parent's generation badge goes
//   setGenerating(on)       generation buttons off while a generation runs
//   nodeTitle(id)           the factor's name (delete confirmation)

import { generationTargets, getNode } from './model.js';

export function installBridge(app) {
  const bridge = {
    refresh: (options) => app.refresh(options || {}),
    generationTargets: (level) => {
      const { targets, excluded } = generationTargets(app.model, Number(level));
      return { targets: targets.map((node) => node.id), excluded: excluded.length };
    },
    genHost: (id) => document.querySelector(`[data-gen-host="${Number(id)}"]`),
    setGenerating: (on) => app.setGenerating(Boolean(on)),
    nodeTitle: (id) => {
      const node = getNode(app.model, id);
      return node ? node.title : null;
    },
  };
  window.ftaEditBridge = Object.freeze(bridge);
  return bridge;
}
