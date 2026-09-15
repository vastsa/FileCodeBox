import {$, api, bytes, date, errorText, message} from './common.js';

// 访客凭证只保存在当前页面内存，不进入 URL、Cookie 或浏览器持久化存储。
let session = null;
let busy = false;
function describe() { $('delivery-info').textContent = `${session.name} · 剩余 ${session.remaining} 次 · 单文件上限 ${bytes(session.upload_size)} · 有效期至 ${date(session.expires_at)}`; }
$('verify-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (busy) return;
  $('verify-button').disabled = true;
  session = null; $('upload-section').hidden = true;
  try {
    session = await api('/api/delivery/verify', {method:'POST', json:{code:$('code').value.trim()}});
    describe(); $('upload-section').hidden = false;
    message($('verify-message'), '验证通过，可以投递文件。');
  } catch (error) { message($('verify-message'), error.message, true); }
  finally { $('verify-button').disabled = false; }
});
$('files').addEventListener('change', () => {
  const files = [...$('files').files];
  $('selection-info').textContent = `已选择 ${files.length} 个文件，共 ${bytes(files.reduce((total,file) => total+file.size,0))}`;
});
function upload(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/delivery/upload');
    xhr.setRequestHeader('Authorization', `Bearer ${session.token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) $('progress').value = event.loaded / event.total * 100;
      $('progress-text').textContent = `${file.name} · ${Math.round($('progress').value)}%${$('progress').value >= 100 ? '，正在保存' : ''}`;
    };
    xhr.onload = () => {
      let data; try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data.detail);
      else reject(new Error(errorText(data)));
    };
    xhr.onerror = () => reject(new Error('网络连接中断，结果尚未确认。请联系接收方或重新验证剩余次数，勿直接重复投递。'));
    const form = new FormData(); form.append('file', file); xhr.send(form);
  });
}
$('upload-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (!session || busy) return;
  const files = [...$('files').files];
  if (!files.length) return;
  if (files.length > session.remaining) { message($('upload-message'), '所选文件数超过剩余次数，请减少文件或联系管理员。', true); return; }
  if (files.some(file => file.size > session.upload_size)) { message($('upload-message'), '所选文件中有文件超过单文件大小限制。', true); return; }
  busy = true; $('upload-button').disabled = true; $('verify-button').disabled = true; $('files').disabled = true;
  $('progress-box').hidden = false; $('results').replaceChildren(); message($('upload-message'), '正在投递，请保持页面打开。');
  let failed = false;
  try {
    for (const file of files) {
      $('progress').value = 0;
      const result = document.createElement('li'); $('results').append(result);
      result.textContent = `${file.name} · 正在上传`;
      try { await upload(file); session.remaining--; describe(); result.textContent = `${file.name} · 投递成功`; result.className = 'success'; }
      catch (error) { result.textContent = `${file.name} · ${error.message}`; result.className = 'error'; failed = true; break; }
    }
    message($('upload-message'), failed ? '后续文件已停止上传。成功的文件无需重传；请重新选择未成功的文件。' : '全部文件投递成功，接收方可以在后台查看。', failed);
    // 每次批次后清空选择，避免再次点击时把已成功文件重复提交。
    $('files').value = ''; $('selection-info').textContent = '';
  } finally {
    busy = false; $('upload-button').disabled = false; $('verify-button').disabled = false; $('files').disabled = false; $('progress-box').hidden = true;
  }
});
