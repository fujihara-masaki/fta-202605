// FTA Tool - app.js
//
// Legacy processing still used by the analysis edit screen (plan 7.2):
// generation only (replaced in PR-6). The title, the top event and the
// reference information are saved by the new screen since PR-4
// (js/pages/edit/title.js, step1.js, through js/common/unsaved.js); detail
// editing, manual add and delete since PR-5 (js/pages/edit/factor-editor.js,
// add-dialog.js, delete-dialog.js: the detail modal, the manual-add modal and
// the confirm() of deleteNode are gone). The new screen (js/pages/edit.js)
// owns selection, judgement, filter and the views; the parts below reach it
// through window.ftaEditBridge (js/pages/edit/bridge.js).

// ===== Notifications =====
// Every message of this file goes to the shared notifications
// (js/common/notify.js) with the same text and kind as before (the user's
// decision of 2026-09-29, 判断4; J-24 moved forward to PR-3): success and
// warnings close by themselves (3 s / 6 s as before), errors stay until
// they are closed, screen readers are told. This is the one connection
// point; the old #toast element is no longer rendered, so nothing is shown
// twice. Without the edit screen's bridge the module is loaded directly.
function showToast(message, type = 'success') {
  const bridge = window.ftaEditBridge;
  if (bridge) {
    bridge.notify(message, type);
    return;
  }
  import('/static/js/common/notify.js')
    .then(({ notify }) => notify(message, { type }))
    .catch(() => {});
}

// ===== Show the result of a change =====
// The edit screen shows it by a partial update through the bridge
// (js/pages/edit/refresh.js; the page is not reloaded, selection, step,
// view, scroll, filter and typed input are kept). The old name is kept for
// the callers below.
function reloadPreservingScroll(delayMs = 0, options = {}) {
  const bridge = window.ftaEditBridge;
  if (bridge) {
    bridge.refresh(options);
    return;
  }
  setTimeout(() => location.reload(), delayMs);
}

// ===== Before and after a generation =====
// The edit screen waits for saves in flight and saves ① as the level needs
// (一次: the top event — not empty — and the reference information; 二次・三次:
// the reference information only, J-09) through the same save as its save
// buttons, and tracks the generation until its result is shown
// (js/pages/edit/generation.js). null: nothing may be generated (the reason
// was shown).
async function _beginGeneration(level) {
  const bridge = window.ftaEditBridge;
  if (!bridge || typeof bridge.beginGeneration !== 'function') {
    showToast('画面の準備ができていないため、生成できません', 'error');
    return null;
  }
  return bridge.beginGeneration(Number(level));
}

// ===== Generation Status Badge =====
// Shown next to the parent's group heading in the work list (steps ③・④).
function setNodeGenStatus(nodeId, status, count) {
  const bridge = window.ftaEditBridge;
  const host = bridge ? bridge.genHost(nodeId) : null;
  if (!host) return;
  let badge = host.querySelector('.gen-status-badge');
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'gen-status-badge';
    host.appendChild(badge);
  }
  badge.className = `gen-status-badge gen-status-${status}`;
  if (status === 'generating') badge.textContent = '生成中…';
  else if (status === 'done') badge.textContent = `+${count}件`;
  else if (status === 'excluded') badge.textContent = '0件(除外)';
  else if (status === 'error') badge.textContent = 'エラー';
  else badge.textContent = '';
}

// Disable every generation trigger while a request is in flight so a slow
// LLM call can't be double-fired (or fired for another level in parallel).
// The edit screen keeps the buttons it disabled for another reason (J-25).
function setGenerateButtonsDisabled(disabled) {
  const bridge = window.ftaEditBridge;
  if (bridge) {
    bridge.setGenerating(disabled);
    return;
  }
  document.querySelectorAll('[data-generate]').forEach((btn) => {
    btn.disabled = disabled;
  });
}

// ===== Parents of a generation (J-25, 判断3) =====
// A 二次・三次 request always names its parent (never a request without
// parent_id, which the API would answer for every Yes factor), and the
// parent must be one the edit screen allows: never a factor with an
// inconsistent parent link or ancestor. Asked right before every request,
// from the data of the page; without the edit screen nothing is sent.
function _parentAllowed(parentId, level) {
  if (Number(level) === 1) return true;
  if (!parentId) {
    showToast('親要因が指定されていないため、追加・生成できません', 'error');
    return false;
  }
  const bridge = window.ftaEditBridge;
  const check = bridge
    ? bridge.checkParent(Number(parentId), Number(level))
    : { allowed: false, reason: '親要因を確認できないため、追加・生成できません' };
  if (!check.allowed) {
    showToast(check.reason, 'error');
    return false;
  }
  return true;
}

// ===== Generate Factors =====
async function generateFactors(analysisId, level) {
  const generation = await _beginGeneration(level);
  if (!generation) return;
  try {
    if (level >= 2) await generateFactorsSequential(analysisId, level);
    else await _generateLevel1(analysisId, level);
  } finally {
    await generation.end();
  }
}

async function _generateLevel1(analysisId, level) {
  // Level 1 — single call, show full-page overlay
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.classList.remove('hidden');
  setGenerateButtonsDisabled(true);
  try {
    const res = await fetch(`/analyses/${analysisId}/generate/level/${level}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    const qs = data.quality_summary || {};
    if (data.created > 0) {
      showToast(data.message || `${data.created}件の要因を生成しました`);
      reloadPreservingScroll(800);
      return;
    } else if (qs.all_candidates_excluded) {
      // Candidates were generated but the quality check rejected all of them.
      showToast(
        data.message || '生成候補は品質チェックによりすべて除外されました',
        'warning',
      );
    } else if (data.success) {
      showToast(data.message || '新規要因はありませんでした', 'warning');
    } else {
      showToast(data.message || '生成に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  } finally {
    if (overlay) overlay.classList.add('hidden');
    setGenerateButtonsDisabled(false);
  }
}

// ===== Generate Factors Sequential (level 2/3 — per parent) =====
// The parents are every Yes factor of the level above, taken from the edit
// screen's data (hidden by the filter or not, J-07), in the same order as
// before, except factors with an inconsistent parent link or ancestor
// (J-25, 判断3), which are counted and named separately; one request per
// parent, each with its parent_id, each checked again before it is sent.
async function generateFactorsSequential(analysisId, level) {
  const bridge = window.ftaEditBridge;
  const { targets: parentIds, excluded } = bridge
    ? bridge.generationTargets(level)
    : { targets: [], excluded: 0 };

  if (parentIds.length === 0) {
    showToast(
      excluded > 0
        ? `生成できる親要因がありません（Yes評価の要因のうち${excluded}件は親子関係に不整合があるため対象外です）`
        : 'Yes評価の要因がありません',
      'error',
    );
    return;
  }

  const excludedNote = excluded > 0 ? `（親子関係に不整合があるYes評価の要因${excluded}件は対象外）` : '';
  showToast(`${parentIds.length}件の親要因から順に生成中...${excludedNote}`);
  setGenerateButtonsDisabled(true);

  let totalCreated = 0;
  let totalErrors = 0;
  let totalExcludedCandidates = 0;  // candidates rejected by the quality check
  const reasonSet = new Set();

  try {
    for (const nodeId of parentIds) {
      if (!_parentAllowed(nodeId, level)) {
        setNodeGenStatus(nodeId, 'error');
        totalErrors++;
        continue;
      }
      setNodeGenStatus(nodeId, 'generating');

      try {
        const res = await fetch(`/analyses/${analysisId}/generate/level/${level}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parent_id: Number(nodeId) }),
        });
        const data = await res.json();
        const qs = data.quality_summary || {};
        if (data.created > 0) {
          setNodeGenStatus(nodeId, 'done', data.created);
          totalCreated += data.created;
        } else if (qs.all_candidates_excluded) {
          // Generated but all rejected — show「除外」on this parent's badge.
          setNodeGenStatus(nodeId, 'excluded');
          totalExcludedCandidates += (qs.ai_returned || 0);
          (qs.reason_summary || []).forEach((r) => reasonSet.add(r));
        } else if (data.success) {
          setNodeGenStatus(nodeId, 'done', 0);
        } else {
          setNodeGenStatus(nodeId, 'error');
          totalErrors++;
        }
      } catch (e) {
        setNodeGenStatus(nodeId, 'error');
        totalErrors++;
      }
    }
  } finally {
    setGenerateButtonsDisabled(false);
  }

  if (totalCreated > 0) {
    const note = totalExcludedCandidates > 0
      ? `（うち候補${totalExcludedCandidates}件は品質チェックで除外）` : '';
    showToast(`合計${totalCreated}件の要因を生成しました${note}`);
    reloadPreservingScroll(1200);
  } else if (totalExcludedCandidates > 0) {
    const reasons = reasonSet.size ? ` 主な理由: ${[...reasonSet].join('、')}` : '';
    showToast(
      `生成候補は${totalExcludedCandidates}件ありましたが、品質チェックによりすべて除外されました。${reasons}`,
      'warning',
    );
  } else if (totalErrors > 0) {
    showToast('エラーが発生しました', 'error');
  } else {
    showToast('新規要因はありませんでした', 'warning');
  }
}

// ===== Additional Generation =====
// Passes { additional: true } so the backend uses FTA_ADDITIONAL_FACTOR_COUNT
// and hands the existing sibling titles to the LLM to avoid duplicates.
//
// - generateAdditional(analysisId, null, 1): more level-1 factors
// - generateAdditional(analysisId, parentNodeId, childLevel): more children
//   of one specific parent (level-1 card → level 2, level-2 card → level 3)
async function generateAdditional(analysisId, parentNodeId, childLevel) {
  if (!_parentAllowed(parentNodeId, childLevel)) return;
  const generation = await _beginGeneration(childLevel);
  if (!generation) return;
  try {
    await _generateAdditional(analysisId, parentNodeId, childLevel);
  } finally {
    await generation.end();
  }
}

async function _generateAdditional(analysisId, parentNodeId, childLevel) {
  const overlay = (childLevel === 1) ? document.getElementById('loadingOverlay') : null;
  if (overlay) overlay.classList.remove('hidden');
  if (parentNodeId) setNodeGenStatus(parentNodeId, 'generating');
  setGenerateButtonsDisabled(true);

  try {
    const body = { additional: true };
    if (Number(childLevel) !== 1) body.parent_id = Number(parentNodeId);
    const res = await fetch(`/analyses/${analysisId}/generate/level/${childLevel}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    const qs = data.quality_summary || {};
    if (data.created > 0) {
      if (parentNodeId) setNodeGenStatus(parentNodeId, 'done', data.created);
      showToast(data.message || `${data.created}件を追加生成しました`);
      reloadPreservingScroll(800);
      return;
    } else if (qs.all_candidates_excluded) {
      if (parentNodeId) setNodeGenStatus(parentNodeId, 'excluded');
      showToast(
        data.message || '追加候補は品質チェックによりすべて除外されました',
        'warning',
      );
    } else if (data.success) {
      if (parentNodeId) setNodeGenStatus(parentNodeId, 'done', 0);
      showToast(data.message || '追加できる新規要因はありませんでした', 'warning');
    } else {
      if (parentNodeId) setNodeGenStatus(parentNodeId, 'error');
      showToast(data.message || '追加生成に失敗しました', 'error');
    }
  } catch (e) {
    if (parentNodeId) setNodeGenStatus(parentNodeId, 'error');
    showToast('通信エラーが発生しました', 'error');
  } finally {
    if (overlay) overlay.classList.add('hidden');
    setGenerateButtonsDisabled(false);
  }
}

// Judgement (UI-12), the filter (UI-15), the quality warning (UI-17), detail
// editing (UI-13・UI-14), manual add (UI-11) and delete are handled by the
// edit screen itself (js/pages/edit).
