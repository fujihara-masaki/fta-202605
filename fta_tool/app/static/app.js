// FTA Tool - app.js

// ===== Toast notifications =====
function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast ${type}`;
  setTimeout(() => { toast.className = 'toast hidden'; }, 3000);
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
    _showTitleError('タイトルは空にできません');
    showToast('タイトルは空にできません', 'error');
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

function startTitleRename(analysisId) {
  const link = document.getElementById(`title-link-${analysisId}`);
  if (!link) return;
  const currentTitle = link.textContent.trim();
  const cell = link.closest('td');
  const originalHTML = cell.innerHTML;

  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentTitle;
  input.className = 'rename-input';
  input.maxLength = 255;

  const saveBtn = document.createElement('button');
  saveBtn.textContent = '保存';
  saveBtn.className = 'btn btn-xs btn-primary';

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'キャンセル';
  cancelBtn.className = 'btn btn-xs btn-outline';

  const hintSpan = document.createElement('span');
  hintSpan.className = 'rename-hint';
  hintSpan.textContent = '255文字以内で入力してください';

  const errSpan = document.createElement('span');
  errSpan.className = 'rename-error';
  errSpan.hidden = true;

  cell.innerHTML = '';
  cell.append(input, saveBtn, cancelBtn, hintSpan, errSpan);
  input.focus();
  input.select();

  const showRenameErr = (msg) => { errSpan.textContent = msg; errSpan.hidden = false; input.focus(); };
  const clearRenameErr = () => { errSpan.hidden = true; };

  const doSave = async () => {
    const newTitle = input.value.trim();
    if (!newTitle) { showRenameErr('タイトルは空にできません'); return; }
    clearRenameErr();
    const ok = await saveAnalysisTitle(analysisId, newTitle);
    if (ok) {
      cell.innerHTML = originalHTML;
      const linkEl = document.getElementById(`title-link-${analysisId}`);
      if (linkEl) linkEl.textContent = newTitle;
    } else {
      showRenameErr('保存に失敗しました');
    }
  };

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); doSave(); }
    if (e.key === 'Escape') { cell.innerHTML = originalHTML; }
  });
  saveBtn.addEventListener('click', doSave);
  cancelBtn.addEventListener('click', () => { cell.innerHTML = originalHTML; });
}

// ===== Top Event =====
async function saveTopEvent(analysisId) {
  const input = document.getElementById('topEventInput');
  if (!input) return;
  const top_event = input.value.trim();
  try {
    const res = await fetch(`/analyses/${analysisId}/top-event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ top_event }),
    });
    const data = await res.json();
    if (data.success) showToast('頂上事象を保存しました');
    else showToast('保存に失敗しました', 'error');
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  }
}

// ===== Generation Status Badge =====
function setNodeGenStatus(nodeId, status, count) {
  const card = document.getElementById(`node-${nodeId}`);
  if (!card) return;
  let badge = card.querySelector('.gen-status-badge');
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'gen-status-badge';
    const header = card.querySelector('.node-card-header');
    if (header) header.appendChild(badge);
  }
  badge.className = `gen-status-badge gen-status-${status}`;
  if (status === 'generating') badge.textContent = '生成中…';
  else if (status === 'done') badge.textContent = `+${count}件`;
  else if (status === 'error') badge.textContent = 'エラー';
  else badge.textContent = '';
}

// ===== Generate Factors =====
async function generateFactors(analysisId, level) {
  if (level >= 2) {
    await generateFactorsSequential(analysisId, level);
    return;
  }
  // Level 1 — single call, show full-page overlay
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.classList.remove('hidden');
  try {
    const res = await fetch(`/analyses/${analysisId}/generate/level/${level}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (data.success || data.created > 0) {
      showToast(data.message || `${data.created}件の要因を生成しました`);
      setTimeout(() => location.reload(), 800);
    } else {
      showToast(data.message || '生成に失敗しました', 'error');
      if (overlay) overlay.classList.add('hidden');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
    if (overlay) overlay.classList.add('hidden');
  }
}

// ===== Generate Factors Sequential (level 2/3 — per parent card) =====
async function generateFactorsSequential(analysisId, level) {
  const parentLevel = level - 1;
  const parentCards = document.querySelectorAll(`.level-${parentLevel}-card.yes`);

  if (parentCards.length === 0) {
    showToast('Yes評価の要因がありません', 'error');
    return;
  }

  showToast(`${parentCards.length}件の親要因から順に生成中...`);

  let totalCreated = 0;
  let totalErrors = 0;

  for (const card of parentCards) {
    const nodeId = card.dataset.nodeId;
    setNodeGenStatus(nodeId, 'generating');

    try {
      const res = await fetch(`/analyses/${analysisId}/generate/level/${level}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_id: parseInt(nodeId) }),
      });
      const data = await res.json();
      if (data.success || data.created > 0) {
        setNodeGenStatus(nodeId, 'done', data.created);
        totalCreated += data.created;
      } else {
        setNodeGenStatus(nodeId, 'error');
        totalErrors++;
      }
    } catch (e) {
      setNodeGenStatus(nodeId, 'error');
      totalErrors++;
    }
  }

  if (totalCreated > 0) {
    showToast(`合計${totalCreated}件の要因を生成しました`);
    setTimeout(() => location.reload(), 1200);
  } else {
    const msg = totalErrors > 0 ? 'エラーが発生しました' : '新規要因はありませんでした';
    showToast(msg, totalErrors > 0 ? 'error' : 'success');
  }
}

// ===== Additional Generation (未実装) =====
// TODO: 追加生成機能の実装ポイント
//
// 【一次要因の追加生成】 generateAdditional(analysisId, null, 1)
//   - 既存の一次要因タイトル一覧を取得し、existing_titles として API に渡す
//   - POST /analyses/{id}/generate/level/1 に { additional: true, existing_titles: [...] } を送信
//   - LLM に既存要因を提示することで重複・言い換えを避け、2〜3 件を追加生成する
//
// 【各要因の追加生成】 generateAdditional(analysisId, parentNodeId, childLevel)
//   - parentNodeId の子ノード一覧を取得し、existing_titles として API に渡す
//   - POST /analyses/{id}/generate/level/{childLevel} に
//     { parent_id: parentNodeId, additional: true, existing_titles: [...] } を送信
//   - 三次要因（childLevel === 3）は本ツールの最深レベルのため追加生成ボタン非表示が原則
//
// 実装時は analysis_detail.html の各 TODO コメント箇所にボタンを追加し、
// この関数を復活させる（または別名で再実装する）。
//
// async function generateAdditional(analysisId, parentNodeId, childLevel) { ... }

// ===== Judgement =====
async function setJudgement(nodeId, judgement) {
  try {
    const res = await fetch(`/nodes/${nodeId}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_judgement: judgement }),
    });
    const data = await res.json();
    if (data.success) {
      const card = document.getElementById(`node-${nodeId}`);
      if (card) {
        card.classList.remove('yes', 'no', 'unknown');
        card.classList.add(judgement);
        // Update button states
        card.querySelectorAll('.judgement-btn').forEach(btn => {
          btn.classList.remove('active');
          if (btn.classList.contains(judgement)) btn.classList.add('active');
        });
      }
      showToast('評価を更新しました');
    } else {
      showToast('更新に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  }
}

// ===== Save Node Title =====
async function saveNodeTitle(nodeId, title) {
  const trimmed = title.trim();
  if (!trimmed) return;
  try {
    await fetch(`/nodes/${nodeId}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: trimmed }),
    });
  } catch (e) {
    console.error('Failed to save title', e);
  }
}

// ===== Delete Node =====
async function deleteNode(nodeId, analysisId) {
  if (!confirm('この要因を削除しますか？（子要因も削除されます）')) return;
  try {
    const res = await fetch(`/nodes/${nodeId}/delete`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('削除しました');
      setTimeout(() => location.reload(), 500);
    } else {
      showToast('削除に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  }
}

// ===== Node Detail Modal =====
let currentNodeId = null;
const nodeCache = {};

async function openNodeDetail(nodeId) {
  // Collect values from the DOM
  const card = document.getElementById(`node-${nodeId}`);
  const titleEl = card ? card.querySelector('.node-title') : null;
  const descEl = card ? card.querySelector('.node-desc') : null;

  document.getElementById('modalNodeId').value = nodeId;
  document.getElementById('modalTitle').value = titleEl ? titleEl.textContent.trim() : '';
  document.getElementById('modalDescription').value = descEl ? descEl.textContent.trim() : '';
  document.getElementById('modalMemo').value = '';
  document.getElementById('modalDirectStatus').value = 'unknown';
  document.getElementById('modalDirectComment').value = '';
  document.getElementById('modalEvidence').value = '';
  document.getElementById('modalPrevention').value = '';

  currentNodeId = nodeId;
  document.getElementById('nodeDetailModal').classList.remove('hidden');
}

function closeNodeDetail() {
  document.getElementById('nodeDetailModal').classList.add('hidden');
  currentNodeId = null;
}

async function saveNodeDetail() {
  const nodeId = document.getElementById('modalNodeId').value;
  const payload = {
    title: document.getElementById('modalTitle').value.trim(),
    description: document.getElementById('modalDescription').value.trim(),
    memo: document.getElementById('modalMemo').value.trim(),
    direct_cause_status: document.getElementById('modalDirectStatus').value,
    direct_cause_comment: document.getElementById('modalDirectComment').value.trim(),
    evidence: document.getElementById('modalEvidence').value.trim(),
    prevention_idea: document.getElementById('modalPrevention').value.trim(),
  };
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
      setTimeout(() => location.reload(), 600);
    } else {
      showToast('保存に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  }
}

// ===== Add Node Modal =====
function showAddNodeModal(analysisId, parentId, level) {
  document.getElementById('addNodeAnalysisId').value = analysisId;
  document.getElementById('addNodeParentId').value = parentId || '';
  document.getElementById('addNodeLevel').value = level;
  document.getElementById('addNodeTitle').value = '';
  document.getElementById('addNodeDescription').value = '';
  document.getElementById('addNodeModal').classList.remove('hidden');
  setTimeout(() => document.getElementById('addNodeTitle').focus(), 100);
}

function closeAddNodeModal() {
  document.getElementById('addNodeModal').classList.add('hidden');
}

async function submitAddNode() {
  const analysisId = document.getElementById('addNodeAnalysisId').value;
  const parentId = document.getElementById('addNodeParentId').value;
  const level = parseInt(document.getElementById('addNodeLevel').value);
  const title = document.getElementById('addNodeTitle').value.trim();
  const description = document.getElementById('addNodeDescription').value.trim();

  if (!title) {
    showToast('タイトルを入力してください', 'error');
    return;
  }

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
      setTimeout(() => location.reload(), 500);
    } else {
      showToast(data.detail || '追加に失敗しました', 'error');
    }
  } catch (e) {
    showToast('通信エラーが発生しました', 'error');
  }
}

// Close modals on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeNodeDetail();
    closeAddNodeModal();
  }
});
