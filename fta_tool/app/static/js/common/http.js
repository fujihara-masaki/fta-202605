// JSON requests to the existing API. Every outcome is returned as a value
// (never thrown) so callers can show the concrete reason: the server's own
// message is kept as-is instead of being replaced by a generic one (C-02).
//
//   { ok: true,  status, data }
//   { ok: false, status, kind, reason, data }
//     kind: 'network' | 'http' | 'parse' | 'app'

export const NETWORK_ERROR_REASON = 'サーバーに接続できませんでした（通信エラー）';

export function reasonFromBody(data) {
  if (!data || typeof data !== 'object') return '';
  const value = data.detail ?? data.message;
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value.map((item) => (item && typeof item.msg === 'string' ? item.msg : ''))
      .filter(Boolean).join('、');
  }
  return '';
}

export async function requestJson(url, { method = 'GET', body } = {}) {
  const init = {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, init);
  } catch {
    return { ok: false, status: 0, kind: 'network', reason: NETWORK_ERROR_REASON, data: null };
  }

  let text = '';
  try {
    text = await response.text();
  } catch {
    return { ok: false, status: response.status, kind: 'network', reason: NETWORK_ERROR_REASON, data: null };
  }

  let data = null;
  let parsed = false;
  if (text) {
    try {
      data = JSON.parse(text);
      parsed = true;
    } catch {
      parsed = false;
    }
  }

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      kind: 'http',
      reason: reasonFromBody(data) || `サーバーでエラーが発生しました（HTTP ${response.status}）`,
      data,
    };
  }
  if (!parsed) {
    return {
      ok: false,
      status: response.status,
      kind: 'parse',
      reason: 'サーバーの応答を読み取れませんでした',
      data: null,
    };
  }
  if (data && typeof data === 'object' && data.success === false) {
    return {
      ok: false,
      status: response.status,
      kind: 'app',
      reason: reasonFromBody(data) || '処理に失敗しました',
      data,
    };
  }
  return { ok: true, status: response.status, data };
}
