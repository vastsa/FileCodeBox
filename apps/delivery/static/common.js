// 所有服务端/文件名文本都通过 textContent 渲染，禁止将不可信内容拼接为 HTML。
export const $ = (id) => document.getElementById(id);
export function message(node, text, error = false) { node.textContent = text; node.className = `message ${error ? 'error' : 'success'}`; }
export function bytes(size) { if (size < 1024) return `${size} B`; const units = ['KiB','MiB','GiB']; let n = size / 1024, i = 0; while (n >= 1024 && i < 2) { n /= 1024; i++; } return `${n.toFixed(1)} ${units[i]}`; }
export function date(value) { return value ? new Date(value).toLocaleString() : '—'; }
export function errorText(body) {
  const detail = body?.detail;
  if (Array.isArray(detail)) return detail.map(item => item.msg).join('；');
  return typeof detail === 'string' ? detail : body?.message || '请求失败，请稍后重试';
}
export async function api(path, {token, json, ...options} = {}) {
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (json !== undefined) { headers.set('Content-Type', 'application/json'); options.body = JSON.stringify(json); }
  const response = await fetch(path, {...options, headers, cache: 'no-store'});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(errorText(body)); error.status = response.status; throw error; }
  return body.detail;
}
export function cell(row, text) { const node = row.insertCell(); node.textContent = text; return node; }
export function emptyRow(body, count, text) { body.replaceChildren(); const node = body.insertRow().insertCell(); node.colSpan = count; node.className = 'empty'; node.textContent = text; }
