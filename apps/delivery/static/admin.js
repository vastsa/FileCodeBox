import {$, api, bytes, date, cell, emptyRow, errorText, message} from './common.js';

// 管理凭证只存在当前标签页会话中；不与访客寄件凭证混用。
const tokenKey = 'filerelay_delivery_admin_token';
let token = sessionStorage.getItem(tokenKey) || '';
let page = 1, filePage = 1, selected = null, listSequence = 0, fileSequence = 0;
const stateNames = {active:'可投递', disabled:'已禁用', expired:'已过期', exhausted:'次数耗尽', deleted:'已删除', pending:'上传中', stored:'已收到', cleanup:'等待清理'};
function authScreen(loggedIn) {
  $('workspace').hidden = !loggedIn; $('login-panel').hidden = loggedIn; $('logout').hidden = !loggedIn;
  if (!loggedIn) { $('codes').replaceChildren(); $('received-files').replaceChildren(); $('files-panel').hidden = true; $('created').hidden = true; $('created-code').textContent = ''; }
}
function report(error) {
  if (error.status === 401) { token = ''; sessionStorage.removeItem(tokenKey); authScreen(false); }
  message($('message'), error.message, true);
}
const request = (path, options = {}) => api('/admin/delivery' + path, {...options, token});
function action(container, label, run, danger = false) {
  const button = document.createElement('button'); button.textContent = label; button.className = `quiet${danger ? ' danger' : ''}`;
  button.type = 'button'; container.append(button);
  button.addEventListener('click', async () => { button.disabled = true; try { await run(); } catch (error) { report(error); } finally { button.disabled = false; } });
}
function pagination(total, current, previous, next, info) {
  const pages = Math.max(1, Math.ceil(total / 20)); $(previous).disabled = current <= 1; $(next).disabled = current >= pages;
  $(info).textContent = `${current} / ${pages} 页 · 共 ${total} 条`;
}
async function loadCodes() {
  const sequence = ++listSequence;
  // 已删除寄件码不再作为可筛选的历史记录保留。
  const result = await request(`/codes?page=${page}`);
  if (sequence !== listSequence) return;
  if (!result.items.length && page > 1) { page--; return loadCodes(); }
  $('codes').replaceChildren();
  if (!result.items.length) emptyRow($('codes'), 6, '还没有寄件码。创建后即可邀请对方投递。');
  for (const item of result.items) {
    const row = $('codes').insertRow();
    cell(row, `${item.name} #${item.id}`); cell(row, `${item.storage_type} · ${item.target_path}`); cell(row, date(item.expires_at));
    const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = stateNames[item.status] || item.status; row.insertCell().append(badge);
    cell(row, `${item.used_count} / ${item.reserved_count} / ${item.max_uploads}`);
    const actions = row.insertCell(); actions.className = 'actions';
    action(actions, '查看收件', async () => { selected = item; filePage = 1; await loadFiles(); $('files-panel').scrollIntoView({behavior:'smooth', block:'start'}); });
    if (!item.deleted) {
      action(actions, item.enabled ? '禁用' : '启用', async () => { await request(`/codes/${item.id}`, {method:'PATCH', json:{enabled:!item.enabled}}); await loadCodes(); });
      action(actions, '删除', async () => {
        if (!window.confirm(`删除“${item.name}”的寄件码？会撤销投递权限，但保留已收到的文件。`)) return;
        await request(`/codes/${item.id}`, {method:'DELETE'}); message($('message'), '寄件码已永久删除，已生成的取件码仍可正常使用。'); await loadCodes();
      }, true);
    }
  }
  pagination(result.total, page, 'previous', 'next', 'page-info');
}
async function download(item) {
  // 支持文件系统接口的浏览器直接流式写盘，其他浏览器回退到 Blob 下载。
  let handle;
  if ('showSaveFilePicker' in window) {
    try { handle = await window.showSaveFilePicker({suggestedName:item.filename}); }
    catch (error) { if (error.name === 'AbortError') return; throw error; }
  }
  const response = await fetch(`/admin/delivery/files/${item.id}/download`, {headers:{Authorization:`Bearer ${token}`}, cache:'no-store'});
  if (!response.ok) { const error = new Error(errorText(await response.json().catch(() => ({})))); error.status=response.status; throw error; }
  if (handle) { const writable = await handle.createWritable(); await response.body.pipeTo(writable); return; }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href=url; link.download=item.filename; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
async function loadFiles() {
  if (!selected) return;
  const selection = selected; const sequence = ++fileSequence;
  const result = await request(`/codes/${selection.id}/files?page=${filePage}`);
  if (sequence !== fileSequence || selected.id !== selection.id) return;
  if (!result.items.length && filePage > 1) { filePage--; return loadFiles(); }
  $('files-panel').hidden=false; $('files-title').textContent=`${selection.name} · 收到的文件`;
  $('received-files').replaceChildren();
  if (!result.items.length) emptyRow($('received-files'), 5, '尚未收到文件。');
  for (const item of result.items) {
    const row=$('received-files').insertRow(); cell(row, item.filename || '正在接收'); cell(row, bytes(item.size)); cell(row, date(item.created_at)); cell(row, stateNames[item.status] || item.status);
    const actions=row.insertCell(); actions.className='actions';
    if (item.status === 'stored') action(actions, '下载', () => download(item));
    if (item.status !== 'pending') action(actions, '删除文件', async () => {
      if (!window.confirm(`确定永久删除文件“${item.filename}”？此操作不能撤销。`)) return;
      await request(`/files/${item.id}`, {method:'DELETE'}); await loadFiles();
    }, true);
  }
  pagination(result.total, filePage, 'files-previous', 'files-next', 'files-page-info');
}
function eventAction(id, event, handler) { $(id).addEventListener(event, () => Promise.resolve().then(handler).catch(report)); }
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button=event.submitter; button.disabled=true;
  try { const session=await api('/admin/login', {method:'POST', json:{password:$('password').value}}); token=session.token; sessionStorage.setItem(tokenKey,token); authScreen(true); message($('message'),'登录成功'); await loadCodes(); }
  catch(error) { report(error); }
  finally { button.disabled=false; $('password').value=''; }
});
$('create-form').addEventListener('submit', async event => {
  event.preventDefault(); const button=event.submitter; button.disabled=true; $('created').hidden=true;
  try {
    const result=await request('/codes', {method:'POST', json:{name:$('name').value, code:$('new-code').value.trim(), storage_type:$('storage').value, target_path:$('target').value, expires_at:new Date($('expires').value).toISOString(), max_uploads:Number($('maximum').value)}});
    $('created-code').textContent=result.code; $('created').hidden=false; $('copy-message').textContent=''; $('new-code').value='';
    page=1; message($('message'),'寄件码已创建，请保存下方口令并发给投递人。'); await loadCodes();
  } catch(error) { report(error); } finally { button.disabled=false; }
});
// HTTP 下的兼容复制必须直接在点击回调中触发，避免额外异步调度丢失用户手势。
$('copy-code').addEventListener('click', copyCreatedCode);
eventAction('logout','click',() => { token=''; sessionStorage.removeItem(tokenKey); authScreen(false); message($('message'),'已退出当前寄件管理会话。'); });
eventAction('refresh','click',loadCodes);
eventAction('previous','click',() => {page=Math.max(1,page-1); return loadCodes();}); eventAction('next','click',() => {page++; return loadCodes();});
eventAction('refresh-files','click',loadFiles); eventAction('files-previous','click',() => {filePage=Math.max(1,filePage-1); return loadFiles();}); eventAction('files-next','click',() => {filePage++; return loadFiles();});
// datetime-local 使用本机时区显示，提交时转成带时区的 ISO 日期。
const nextWeek=new Date(Date.now()+7*86400000); nextWeek.setMinutes(nextWeek.getMinutes()-nextWeek.getTimezoneOffset()); $('expires').value=nextWeek.toISOString().slice(0,16);
authScreen(false);
if (token) { api('/admin/verify',{token}).then(async () => {authScreen(true); await loadCodes();}).catch(report); }

async function copyCreatedCode() {
  const source = $('created-code');
  const text = source.textContent.trim();
  const notice = $('copy-message');
  if (!text) { notice.textContent = '请先创建寄件码。'; return; }
  // 新版剪贴板 API 仅在 HTTPS 等安全上下文可用；权限拒绝时继续尝试兼容路径。
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      notice.textContent = '已复制，可发给投递人。';
      return;
    } catch { /* 浏览器或嵌入页面可能拒绝权限，保留下方手动复制能力。 */ }
  }
  let selected = false;
  try {
    // 直接选中页面上的口令，不创建隐藏输入框，也不复制其他页面内容。
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(source);
    selection.removeAllRanges();
    selection.addRange(range);
    selected = selection.toString() === text;
    // 旧接口虽已弃用，但仍可为部分 HTTP 浏览器提供降级支持；不能保证所有浏览器允许。
    if (selected && document.execCommand('copy')) {
      notice.textContent = '已复制，可发给投递人。';
      return;
    }
  } catch { /* 禁止脚本复制时仍显示明确的手动操作说明，不误报成功。 */ }
  notice.textContent = selected
    ? '已选中寄件码，请按 Ctrl+C（Mac 为 ⌘C），或长按选中文字后复制。'
    : '请选中上方寄件码，按 Ctrl+C（Mac 为 ⌘C），或长按文字复制。';
}
