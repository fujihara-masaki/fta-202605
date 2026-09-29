// The one place where the legacy app.js reaches the new screen. PR-3 still
// runs detail editing, manual add, delete and generation through app.js
// with its dialogs (plan 7.2); window.ftaEditBridge gives those functions
// what they need on the new page:
//   refresh(options)        show the result of a change ({select} after a
//                           manual add, {deleted} after a delete)
//   generationTargets(lv)   parents of the normal generation, from the data:
//                           {targets: ids, excluded: count} (J-07, J-25)
//   checkParent(id, lv)     may the factor be the parent of a manual add or
//                           a generation of level `lv`: {allowed, reason}
//   checkDelete(id)         may the factor be deleted from this screen:
//                           {allowed, reason}
//   genHost(id)             where a parent's generation badge goes
//   setGenerating(on)       generation buttons off while a generation runs
//   nodeTitle(id)           the factor's name (delete confirmation)
//
// checkParent and checkDelete answer from the summary the server computed
// for the data of the page (app/detail_view.py; 判断2・判断3): the buttons
// show the same answer, and app.js asks again right before it sends a
// request. This is the screen's own check on the data as fetched; it does
// not make the existing APIs safe.

import { generationTargets, getNode } from './model.js';

const GONE = '分析が見つかりません（削除された可能性があります）';
const NOT_ON_PAGE = 'この要因は画面のデータにないため、操作できません。ページを再読み込みしてください。';
const LEVEL_MISMATCH = '親要因の階層が合わないため、追加・生成できません。';
const DELETE_UNKNOWN = '安全に削除できるか確認できていないため、この画面では削除できません。';

const allowed = () => ({ allowed: true, reason: '' });
const refused = (reason) => ({ allowed: false, reason });

export function installBridge(app) {
  const bridge = {
    refresh: (options) => app.refresh(options || {}),
    generationTargets: (level) => {
      const { targets, excluded } = generationTargets(app.model, Number(level));
      return { targets: targets.map((node) => node.id), excluded: excluded.length };
    },
    checkParent: (id, level) => {
      if (app.gone) return refused(GONE);
      const node = getNode(app.model, id);
      if (!node) return refused(NOT_ON_PAGE);
      if (!node.canParent) return refused(node.parentReason || LEVEL_MISMATCH);
      if (Number(level) !== node.level + 1) return refused(LEVEL_MISMATCH);
      return allowed();
    },
    checkDelete: (id) => {
      if (app.gone) return refused(GONE);
      const node = getNode(app.model, id);
      if (!node) return refused(NOT_ON_PAGE);
      const answer = node.delete || {};
      return answer.allowed === true ? allowed() : refused(answer.reason || DELETE_UNKNOWN);
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
