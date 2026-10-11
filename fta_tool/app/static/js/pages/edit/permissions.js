// What the edit screen allows for a factor, answered from the summary the
// server computed for the data of the page (app/detail_view.py; the user's
// decisions 判断2・判断3 of 2026-09-29). The buttons show the same answer, and
// the dialogs ask again when they open and right before they send a
// request (plan 5.3: the button, opening the confirmation, confirming).
// This is the screen's own check on the data as fetched; it does not make
// the existing APIs safe.

import { getNode } from './model.js';

export const GONE = '分析が見つかりません（削除された可能性があります）';
const NOT_ON_PAGE = 'この要因は画面のデータにないため、操作できません。ページを再読み込みしてください。';
const LEVEL_MISMATCH = '親要因の階層が合わないため、追加・生成できません。';
const DELETE_UNKNOWN = '安全に削除できるか確認できていないため、この画面では削除できません。';

const allowed = () => ({ allowed: true, reason: '' });
const refused = (reason) => ({ allowed: false, reason });

// May the factor be the parent of a manual add or a generation of level
// `level` (never one with an inconsistent link or ancestor: J-25, 判断3)?
export function checkParent(app, id, level) {
  if (app.gone) return refused(GONE);
  const node = getNode(app.model, id);
  if (!node) return refused(NOT_ON_PAGE);
  if (!node.canParent) return refused(node.parentReason || LEVEL_MISMATCH);
  if (Number(level) !== node.level + 1) return refused(LEVEL_MISMATCH);
  return allowed();
}

// May the factor be deleted from this screen (判断2)?
export function checkDelete(app, id) {
  if (app.gone) return refused(GONE);
  const node = getNode(app.model, id);
  if (!node) return refused(NOT_ON_PAGE);
  const answer = node.delete || {};
  return answer.allowed === true ? allowed() : refused(answer.reason || DELETE_UNKNOWN);
}
