// FTA Tool - app.js
//
// Legacy processing still used by the analysis edit screen in PR-3 (plan
// 7.2): title / top event / context saving, generation, the detail modal,
// manual add and delete. The new screen (js/pages/edit.js) owns selection,
// judgement, filter and the views; the parts below that depended on the old
// card columns reach it through window.ftaEditBridge (js/pages/edit/bridge.js).

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
// The edit screen shows it through the bridge (selection, step, view,
// scroll and filter are kept); `options` names a factor to select after a
// manual add ({ select, level }) or the deleted factor ({ deleted }).
function reloadPreservingScroll(delayMs = 0, options = {}) {
  const bridge = window.ftaEditBridge;
  if (bridge) {
    bridge.refresh(options);
    return;
  }
  setTimeout(() => location.reload(), delayMs);
}

// ===== Analysis Title =====
function _showTitleError(msg) {
  const span = document.getElementById('titleError');
  if (!span) return;
  span.textContent = msg;
  span.hidden = false;
}

function _clearTitleError() {
  const span = document.getElementById('titleError');
  if (span) span.hidden = true;
}

async function saveAnalysisTitle(analysisId, newTitle) {
  const trimmed = (newTitle || '').trim();
  const el = document.getElementById('analysisTitle');

  if (!trimmed) {
    _showTitleError('タイトルは必須です');
    showToast('タイトルは必須です', 'error');
    if (el) el.focus();
    return false;
  }
  if (trimmed.length > 255) {
    _showTitleError('タイトルは255文字以内で入力してください');
    showToast('タイトルは255文字以内で入力してください', 'error');
    if (el) el.focus();
    return false;
  }

  try {
    const res = await fetch(`/analyses/${analysisId}/title`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: trimmed }),
    });
    const data = await res.json();
    if (data.success) {
      _clearTitleError();
      document.title = data.title + ' - FTA編集';
      showToast('タイトルを保存しました');
      return true;
    }
    const errMsg = data.detail || '保存に失敗しました';
    _showTitleError(errMsg);
    showToast(errMsg, 'error');
    if (el) el.focus();
    return false;
  } catch {
    showToast('通信エラーが発生しました', 'error');
    return false;
  }
}

// The analysis list's inline rename and delete moved to js/pages/list.js
// (PR-1). saveAnalysisTitle above is still used by the analysis detail page.

// ===== Top Event =====
async function saveTopEvent(analysisId, { quiet = false } = {}) {
  const input = document.getElementById('topEventInput');
  if (!input) return false;
  const top_event = input.value.trim();
  try {
    const res = await fetch(`/analyses/${analysisId}/top-event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ top_event }),
    });
    const data = await res.json();
    if (data.success) {
      input.dataset.saved = top_event;
      if (!quiet) showToast('頂上事象を保存しました');
      return true;
    }
    showToast('保存に失敗しました', 'error');
    return false;
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
    return false;
  }
}

// ===== Analysis Context (system / incident) =====
async function saveAnalysisContext(analysisId, { quiet = false } = {}) {
  const sysEl = document.getElementById('systemContextInput');
  const incEl = document.getElementById('incidentContextInput');
  if (!sysEl && !incEl) return true;
  const payload = {};
  if (sysEl) payload.system_context = sysEl.value.trim();
  if (incEl) payload.incident_context = incEl.value.trim();
  try {
    const res = await fetch(`/analyses/${analysisId}/context`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      if (sysEl) sysEl.dataset.saved = data.system_context || '';
      if (incEl) incEl.dataset.saved = data.incident_context || '';
      const status = document.getElementById('analysisContextStatus');
      if (status) {
        const filled = !!(data.system_context || data.incident_context);
        status.textContent = filled ? '入力済み' : '未入力・追加できます';
        status.classList.toggle('filled', filled);
        status.classList.toggle('empty', !filled);
      }
      if (!quiet) showToast('分析コンテキストを保存しました');
      return true;
    }
    showToast(data.detail || '分析コンテキストの保存に失敗しました', 'error');
    return false;
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
    return false;
  }
}

// Like ensureTopEventReady: an edited-but-unsaved context is silently saved
// before generation so the LLM sees what the user sees. Context is optional,
// so (unlike the top event) empty input never blocks generation.
async function ensureAnalysisContextReady(analysisId) {
  const sysEl = document.getElementById('systemContextInput');
  const incEl = document.getElementById('incidentContextInput');
  const dirty = [sysEl, incEl].some(
    (el) => el && el.dataset.saved !== undefined && el.dataset.saved !== el.value.trim(),
  );
  if (!dirty) return true;
  const ok = await saveAnalysisContext(analysisId, { quiet: true });
  if (ok) showToast('編集中の分析コンテキストを保存してから生成します');
  return ok;
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

// ===== Parents of manual add and generation (J-25, 判断3) =====
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

// Level-1 generation needs a top event: block empty input, and silently save
// an edited-but-unsaved value first so the LLM sees what the user sees.
async function ensureTopEventReady(analysisId) {
  const input = document.getElementById('topEventInput');
  if (!input) return true;
  const current = input.value.trim();
  if (!current) {
    showToast('頂上事象を入力してから生成してください', 'error');
    input.focus();
    return false;
  }
  if (input.dataset.saved !== undefined && input.dataset.saved !== current) {
    const ok = await saveTopEvent(analysisId, { quiet: true });
    if (!ok) return false;
    showToast('編集中の頂上事象を保存してから生成します');
  }
  return true;
}

// ===== Generate Factors =====
async function generateFactors(analysisId, level) {
  if (level === 1 && !(await ensureTopEventReady(analysisId))) return;
  if (!(await ensureAnalysisContextReady(analysisId))) return;

  if (level >= 2) {
    await generateFactorsSequential(analysisId, level);
    return;
  }
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
  if (childLevel === 1 && !(await ensureTopEventReady(analysisId))) return;
  if (!(await ensureAnalysisContextReady(analysisId))) return;

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

// Judgement (UI-12), the filter (UI-15) and the quality warning (UI-17) are
// handled by the edit screen itself (js/pages/edit); the card columns with
// their direct title editing are gone (J-10: titles are edited in the
// detail dialog until the inspector takes over in PR-5).

// ===== Delete Node =====
// Only as the edit screen computed it for the data of the page (J-25,
// 判断2): a factor whose delete would remove factors of another analysis,
// whose subtree could not be walked completely, or whose category is kept
// undeletable is refused before the confirmation, and nothing is sent.
// Without the edit screen nothing is deleted. This does not make the delete
// API itself safe.
async function deleteNode(nodeId, analysisId) {
  const bridge = window.ftaEditBridge;
  const check = bridge
    ? bridge.checkDelete(Number(nodeId))
    : { allowed: false, reason: '削除できるか確認できないため、削除できません' };
  if (!check.allowed) {
    showToast(check.reason, 'error');
    return;
  }
  const title = bridge.nodeTitle(nodeId);
  const name = title !== null ? title : `ID: ${nodeId}`;
  if (!confirm(`要因「${name}」を削除しますか？\nこの要因の子要因もすべて削除されます。この操作は取り消せません。`)) return;
  try {
    const res = await fetch(`/nodes/${nodeId}/delete`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('削除しました');
      reloadPreservingScroll(500, { deleted: Number(nodeId) });
    } else {
      showToast('削除に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  }
}

// ===== Node Detail Modal =====
let currentNodeId = null;
let lastFocusedBeforeModal = null;

function _openModal(modalId, focusSelector) {
  lastFocusedBeforeModal = document.activeElement;
  const modal = document.getElementById(modalId);
  modal.classList.remove('hidden');
  const target = focusSelector ? modal.querySelector(focusSelector) : null;
  if (target) setTimeout(() => target.focus(), 50);
}

function _closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal || modal.classList.contains('hidden')) return;
  modal.classList.add('hidden');
  if (lastFocusedBeforeModal && typeof lastFocusedBeforeModal.focus === 'function') {
    lastFocusedBeforeModal.focus();
    lastFocusedBeforeModal = null;
  }
}

async function openNodeDetail(nodeId) {
  // Load the saved values from the server: memo / evidence / prevention etc.
  // are not rendered in the card DOM, and pre-filling them as blanks would
  // overwrite the stored values on save.
  let node = null;
  try {
    const res = await fetch(`/nodes/${nodeId}`);
    if (res.ok) node = await res.json();
  } catch { /* fall back to DOM below */ }

  if (!node) {
    showToast('ノード情報の取得に失敗しました', 'error');
    return;
  }

  document.getElementById('modalNodeId').value = nodeId;
  document.getElementById('modalTitle').value = node.title || '';
  document.getElementById('modalDescription').value = node.description || '';
  document.getElementById('modalMemo').value = node.memo || '';
  document.getElementById('modalDirectStatus').value = node.direct_cause_status || 'unknown';
  document.getElementById('modalDirectComment').value = node.direct_cause_comment || '';
  document.getElementById('modalEvidence').value = node.evidence || '';
  document.getElementById('modalPrevention').value = node.prevention_idea || '';

  const warnRow = document.getElementById('modalWarningRow');
  if (warnRow) {
    if (node.warning_flags) {
      warnRow.hidden = false;
      document.getElementById('modalWarningText').textContent = node.warning_flags;
    } else {
      warnRow.hidden = true;
    }
  }

  currentNodeId = nodeId;
  _openModal('nodeDetailModal', '#modalTitle');
}

function closeNodeDetail() {
  _closeModal('nodeDetailModal');
  currentNodeId = null;
}

async function saveNodeDetail() {
  const nodeId = document.getElementById('modalNodeId').value;
  const title = document.getElementById('modalTitle').value.trim();
  if (!title) {
    showToast('要因タイトルは必須です', 'error');
    document.getElementById('modalTitle').focus();
    return;
  }
  const payload = {
    title,
    description: document.getElementById('modalDescription').value.trim(),
    memo: document.getElementById('modalMemo').value.trim(),
    direct_cause_status: document.getElementById('modalDirectStatus').value,
    direct_cause_comment: document.getElementById('modalDirectComment').value.trim(),
    evidence: document.getElementById('modalEvidence').value.trim(),
    prevention_idea: document.getElementById('modalPrevention').value.trim(),
  };
  const saveBtn = document.getElementById('modalSaveBtn');
  if (saveBtn) saveBtn.disabled = true;
  try {
    const res = await fetch(`/nodes/${nodeId}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      showToast('保存しました');
      closeNodeDetail();
      reloadPreservingScroll(600);
    } else {
      showToast('保存に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

// ===== Add Node Modal =====
function showAddNodeModal(analysisId, parentId, level) {
  if (!_parentAllowed(parentId, level)) return;
  document.getElementById('addNodeAnalysisId').value = analysisId;
  document.getElementById('addNodeParentId').value = parentId || '';
  document.getElementById('addNodeLevel').value = level;
  document.getElementById('addNodeTitle').value = '';
  document.getElementById('addNodeDescription').value = '';
  _openModal('addNodeModal', '#addNodeTitle');
}

function closeAddNodeModal() {
  _closeModal('addNodeModal');
}

async function submitAddNode() {
  const analysisId = document.getElementById('addNodeAnalysisId').value;
  const parentId = document.getElementById('addNodeParentId').value;
  const level = parseInt(document.getElementById('addNodeLevel').value);
  const title = document.getElementById('addNodeTitle').value.trim();
  const description = document.getElementById('addNodeDescription').value.trim();

  if (!title) {
    showToast('タイトルを入力してください', 'error');
    document.getElementById('addNodeTitle').focus();
    return;
  }
  // The page may have been updated while the dialog was open.
  if (!_parentAllowed(parentId, level)) return;

  try {
    let url, body;
    if (level === 1) {
      url = `/analyses/${analysisId}/nodes/add-level1`;
      body = { title, description };
    } else {
      url = `/nodes/${parentId}/children`;
      body = { title, description };
    }
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.success) {
      showToast('要因を追加しました');
      closeAddNodeModal();
      reloadPreservingScroll(500, { select: data.node_id, level });
    } else {
      showToast(data.detail || '追加に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  }
}

// ===== Keyboard support =====
// Close modals on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeNodeDetail();
    closeAddNodeModal();
  }
});

// The analysis title (contenteditable): Enter should commit (blur → save),
// not insert a newline into a single-line title. Rebuilt in PR-4.
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  const t = e.target;
  if (t && t.isContentEditable && t.id === 'analysisTitle') {
    e.preventDefault();
    t.blur();
  }
});
