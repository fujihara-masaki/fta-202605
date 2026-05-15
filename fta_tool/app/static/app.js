// FTA Tool - app.js

// ===== Toast notifications =====
function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast ${type}`;
  setTimeout(() => { toast.className = 'toast hidden'; }, 3000);
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

// ===== Generate Factors =====
async function generateFactors(analysisId, level) {
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
