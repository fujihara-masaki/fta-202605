// ① 頂上事象・参考情報 (PR-4: UI-07・UI-08, J-11). Two save sources of the
// shared save coordinator (js/common/unsaved.js):
// - the top event (POST /analyses/{id}/top-event; may be empty);
// - the two kinds of reference information, saved by one request
//   (POST /analyses/{id}/context; the server keeps demo_points and unknown
//   keys, which the page never shows).
// The save buttons, leaving the page (保存して移動) and the automatic save
// before a generation all call saveSource(), so they share the saved value
// and the result. "Unsaved" compares the input with the saved value after
// the normalisation used for saving (common/text.js: CRLF/LF and the
// surrounding white space), so a value stored with CRLF or spaces is not
// unsaved when the page opens, and typing then restoring is saved again.
// After a success the saved value becomes what was sent (as the server
// answered), never what was typed meanwhile.
// The saved top event is shown at once (step status, outlines, inspector):
// it is registered with app.writes, so a partial update fetched before it is
// never applied (plan 3.4-5, P-3).

import { requestJson } from '../../common/http.js';
import { notify } from '../../common/notify.js';
import { isSameText, normalizeText } from '../../common/text.js';
import {
  isSourceSaving,
  lastFailure,
  refresh as refreshUnsaved,
  registerSource,
  saveSource,
  SOURCE_ORDER,
  subscribe,
} from '../../common/unsaved.js';

export const GONE_REASON = '分析が見つからないため送信していません（削除された可能性があります）';

const STATUS_TEXT = {
  saved: '保存済み',
  dirty: '入力中（未保存）',
  saving: '保存中…',
};

// requestJson's result as the coordinator's outcome.
export function outcomeOf(result, extra = {}) {
  if (result.ok) return { ok: true, status: result.status, ...extra };
  return {
    ok: false,
    status: result.status,
    reason: result.reason,
    gone: result.status === 404 ? 'analysis' : undefined,
  };
}

function savedOf(field) {
  return field ? field.dataset.saved ?? '' : '';
}

function fieldDirty(field) {
  return Boolean(field) && !isSameText(field.value, savedOf(field));
}

export function createStep1(app) {
  const top = document.getElementById('topEventInput');
  const system = document.getElementById('systemContextInput');
  const incident = document.getElementById('incidentContextInput');
  if (!top || !system || !incident) return null;
  const target = { analysisId: app.analysisId };

  const topEvent = {
    id: 'edit-top-event',
    order: SOURCE_ORDER.topEvent,
    label: '頂上事象',
    target,
    fields: [top],
    isDirty: () => fieldDirty(top),
    draftKey: () => normalizeText(top.value),
    async save(to) {
      if (app.gone) return { ok: false, notSent: true, reason: GONE_REASON };
      const value = normalizeText(top.value);
      const endWrite = app.beginWrite();
      let result;
      try {
        result = await requestJson(`/analyses/${to.analysisId}/top-event`, { method: 'POST', body: { top_event: value } });
      } finally {
        endWrite();
      }
      const saved = result.ok && typeof result.data?.top_event === 'string' ? result.data.top_event : value;
      return outcomeOf(result, { value: saved });
    },
    commit(outcome) {
      top.dataset.saved = outcome.value; // the outlines and the inspector follow (edit.js)
    },
    discard() {
      top.value = savedOf(top);
    },
  };

  const context = {
    id: 'edit-context',
    order: SOURCE_ORDER.context,
    label: '参考情報（システム構成・対象範囲／障害発生時の状況・観測事実）',
    target,
    fields: [system, incident],
    isDirty: () => fieldDirty(system) || fieldDirty(incident),
    draftKey: () => JSON.stringify([normalizeText(system.value), normalizeText(incident.value)]),
    async save(to) {
      if (app.gone) return { ok: false, notSent: true, reason: GONE_REASON };
      const sent = { system_context: normalizeText(system.value), incident_context: normalizeText(incident.value) };
      const result = await requestJson(`/analyses/${to.analysisId}/context`, { method: 'POST', body: sent });
      const data = result.ok ? result.data || {} : {};
      return outcomeOf(result, {
        value: {
          system_context: typeof data.system_context === 'string' ? data.system_context : sent.system_context,
          incident_context: typeof data.incident_context === 'string' ? data.incident_context : sent.incident_context,
        },
      });
    },
    commit(outcome) {
      system.dataset.saved = outcome.value.system_context;
      incident.dataset.saved = outcome.value.incident_context;
      const status = document.getElementById('analysisContextStatus');
      if (status) {
        const filled = Boolean(outcome.value.system_context || outcome.value.incident_context);
        status.textContent = filled ? '入力済み' : '未入力・追加できます';
        status.classList.toggle('filled', filled);
        status.classList.toggle('empty', !filled);
      }
    },
    discard() {
      system.value = savedOf(system);
      incident.value = savedOf(incident);
    },
  };

  const sources = { 'top-event': topEvent, context };
  const messages = {
    'top-event': document.querySelector('[data-save-message="top-event"]'),
    context: document.querySelector('[data-save-message="context"]'),
  };
  const buttons = {
    'top-event': document.querySelector('[data-save-button="top-event"]'),
    context: document.querySelector('[data-save-button="context"]'),
  };

  function setStatus(field, state) {
    const status = document.querySelector(`[data-save-status="${field.id}"]`);
    if (!status) return;
    status.dataset.state = state;
    status.textContent = STATUS_TEXT[state];
    status.className = `ui-status ui-status--${state}`;
  }

  function render() {
    for (const [kind, source] of Object.entries(sources)) {
      const saving = isSourceSaving(source);
      for (const field of source.fields) {
        setStatus(field, saving ? 'saving' : (fieldDirty(field) ? 'dirty' : 'saved'));
      }
      const button = buttons[kind];
      if (button) {
        button.disabled = saving || app.gone;
        button.setAttribute('aria-busy', saving ? 'true' : 'false');
      }
      const message = messages[kind];
      const failure = lastFailure(source);
      if (message && !saving) {
        // A failure stays shown while that input is unchanged.
        const current = failure && failure.key === source.draftKey() && source.isDirty();
        message.textContent = current ? `保存できませんでした：${failure.reason}` : '';
        message.dataset.kind = current ? 'error' : '';
      }
    }
    app.applyStep1State();
  }

  async function saveFrom(kind) {
    const source = sources[kind];
    if (app.gone) return;
    if (!source.isDirty()) {
      notify(`${source === topEvent ? '頂上事象' : '参考情報'}に保存していない変更はありません`, { type: 'info' });
      return;
    }
    const outcome = await saveSource(source);
    if (outcome.ok) {
      notify(source === topEvent ? '頂上事象を保存しました' : '参考情報を保存しました', { type: 'success' });
      return;
    }
    notify(`${source === topEvent ? '頂上事象' : '参考情報'}を保存できませんでした：${outcome.reason}`, { type: 'error' });
    if (outcome.gone) app.refresh();
  }

  for (const field of [top, system, incident]) field.addEventListener('input', () => refreshUnsaved());
  for (const [kind, button] of Object.entries(buttons)) {
    if (button) button.addEventListener('click', () => saveFrom(kind));
  }
  const unregister = [registerSource(topEvent), registerSource(context)];
  subscribe(render);
  render();

  return {
    topEvent,
    context,
    fields: { top, system, incident },
    render,
    anyDirty: () => topEvent.isDirty() || context.isDirty(),
    unregister: () => unregister.forEach((fn) => fn()),
  };
}
