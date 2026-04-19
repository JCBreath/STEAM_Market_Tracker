// ── State ────────────────────────────────────────────────────────────────────
const state = {
  searchJobId: null, bulkJobId: null,
  searchItems: [], sortCol: 'name', sortDir: 1,
  bulkStartTs: null, bulkTimer: null,
  activeSSE: {},
};

const $ = id => document.getElementById(id);
const VIZ_FILTER_COOKIE = 'steam_tracker_viz_filters';

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function fmtSize(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  return (b/1048576).toFixed(1) + ' MB';
}
function fmtDate(ts) { return new Date(ts*1000).toLocaleString(); }
function fmtDur(startTs, endTs) {
  const s = Math.round((endTs || Date.now()/1000) - startTs);
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm ' + (s%60) + 's';
  return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
}
function badge(status) {
  const map = { running:'badge-running', done:'badge-done', error:'badge-error', stopped:'badge-stopped' };
  return `<span class="badge ${map[status]||'badge-stopped'}">${status}</span>`;
}
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function copyText(t) { navigator.clipboard.writeText(t).catch(()=>{}); }
function setCookie(name, value, days=180) {
  const expires = new Date(Date.now() + days*86400000).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}
function getCookie(name) {
  const prefix = `${name}=`;
  const part = document.cookie.split('; ').find(row => row.startsWith(prefix));
  return part ? decodeURIComponent(part.slice(prefix.length)) : '';
}
function deleteCookie(name) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

// ── Navigation ───────────────────────────────────────────────────────────────
function switchTab(idx) {
  document.querySelectorAll('.page').forEach((p,i) => p.classList.toggle('active', i===idx));
  document.querySelectorAll('.nav-item').forEach((n,i) => n.classList.toggle('active', i===idx));
  $('hdr-title').textContent = ['数据库','构建','导入','搜索','文件'][idx];
  $('hdr-actions').innerHTML = idx === 0
    ? `<button class="btn btn-ghost btn-sm" onclick="exportDb('csv')">⬇ CSV</button>
       <button class="btn btn-ghost btn-sm" onclick="exportDb('json')">⬇ JSON</button>
       <button class="btn btn-ghost btn-sm" onclick="loadViz()">⟳</button>`
    : '';
  if (idx === 4) { loadFiles(); loadHistory(); }
}

function switchFileTab(idx) {
  document.querySelectorAll('.itab').forEach((t,i) => t.classList.toggle('active', i===idx));
  document.querySelectorAll('.itab-panel').forEach((p,i) => p.classList.toggle('active', i===idx));
}

// ── Log ──────────────────────────────────────────────────────────────────────
function appendLog(boxId, text) {
  const box = $(boxId);
  const line = document.createElement('span');
  line.className = 'le';
  line.textContent = text;
  if (/\[ERROR\]/i.test(text)) line.classList.add('le-error');
  else if (/\[WARN\]/i.test(text)) line.classList.add('le-warn');
  else if (/Done|Success|Saved|Found/i.test(text)) line.classList.add('le-good');
  else if (/^\[INFO\]/i.test(text)) line.classList.add('le-info');
  box.appendChild(line);
  if (box.scrollHeight - box.scrollTop - box.clientHeight < 60) box.scrollTop = box.scrollHeight;
}
function clearLog(boxId) { $(boxId).innerHTML = ''; }

// ── Server status ────────────────────────────────────────────────────────────
async function checkServer() {
  try {
    await fetch('/api/jobs');
    $('srv-dot').className = 'dot'; $('srv-label').textContent = 'Connected';
  } catch {
    $('srv-dot').className = 'dot err'; $('srv-label').textContent = 'Server offline';
  }
}
checkServer();

// ── SSE ──────────────────────────────────────────────────────────────────────
function openSSE(jobId, type, onEvent) {
  const prev = state.activeSSE[type];
  if (prev) prev.close();
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  state.activeSSE[type] = es;
  es.onmessage = e => onEvent(JSON.parse(e.data));
  es.onerror = () => { es.close(); delete state.activeSSE[type]; };
  return es;
}

// ══════════════════════════════════════════════════════════════════════════════
// LIBRARY
// ══════════════════════════════════════════════════════════════════════════════
let _categories = [], _libJobId = null, _libTimer = null, _libStartTs = null;

async function loadCategoryTree() {
  const el = $('cat-tree');
  try { _categories = await api('GET', '/api/categories'); }
  catch (e) { el.innerHTML = `<div class="empty-state" style="color:var(--danger)">Failed: ${e.message}</div>`; return; }

  let html = '';
  for (const grp of _categories) {
    html += `<div class="chip-group">
      <div class="chip-group-label">${escHtml(grp.group)}</div>
      <div class="chip-row">`;
    for (const cat of grp.items) {
      const approx = cat.approx >= 1000 ? (cat.approx/1000).toFixed(1)+'k' : cat.approx;
      html += `<label class="cat-chip">
        <input type="checkbox" class="cat-cb" id="cat-${cat.id}" data-catid="${cat.id}" data-tag="${cat.type_tag}" data-approx="${cat.approx}" checked onchange="updateEstimate()">
        ${escHtml(cat.name)}<span class="approx">~${approx}</span>
      </label>`;
    }
    html += `</div></div>`;
  }
  el.innerHTML = html;
  updateEstimate();
}

function selectAllCats(v) { document.querySelectorAll('.cat-cb').forEach(c => c.checked = v); updateEstimate(); }
function selectWeaponOnly() {
  const s = new Set(['pistol','smg','rifle','sniper','shotgun','machinegun','knife','gloves']);
  document.querySelectorAll('.cat-cb').forEach(c => { c.checked = s.has(c.dataset.catid); });
  updateEstimate();
}
function updateEstimate() {
  let total = 0;
  document.querySelectorAll('.cat-cb:checked').forEach(c => { total += parseInt(c.dataset.approx||0); });
  const mins = Math.round(total * 3 / 60);
  $('lib-estimate').textContent = total > 0
    ? `~${total.toLocaleString()} 条 / 约 ${mins < 60 ? mins+'m' : Math.round(mins/60)+'h'}` : '';
}
function getSelectedTags() {
  const tags = [];
  document.querySelectorAll('.cat-cb:checked').forEach(c => tags.push(c.dataset.tag));
  return tags;
}

async function refreshCheckpointBanner() {
  try {
    const cp = await api('GET', '/api/library/checkpoint');
    const bar = $('lib-cp-bar');
    if (!cp.exists) { bar.style.display = 'none'; return; }
    bar.style.display = '';
    const upd = cp.updated_at ? new Date(cp.updated_at*1000).toLocaleString() : '–';
    $('lib-cp-info').textContent =
      `已完成 ${cp.done_cats}/${cp.total_cats} (${cp.percent}%)  · 当前：${cp.current_tag||'–'}  · 偏移：${cp.current_offset}  · ${upd}`;
  } catch { $('lib-cp-bar').style.display = 'none'; }
}

async function resumeBuild() {
  const cp = await api('GET', '/api/library/checkpoint');
  if (!cp.exists) { alert('无断点记录'); return; }
  const params = {
    selected_type_tags: cp.params.selected_type_tags,
    delay_min: parseFloat($('lib-dmin').value) || cp.params.delay_min || 2.0,
    delay_max: parseFloat($('lib-dmax').value) || cp.params.delay_max || 4.0,
    max_429_retries: parseInt($('lib-retries').value) || 8,
    retry_backoff_base: 15.0,
    currency: cp.params.currency || 1,
    resume: true,
  };
  $('lib-cp-bar').style.display = 'none';
  await _launchLibraryJob(params, `续传：${cp.done_cats}/${cp.total_cats} 已完成`);
}

async function discardCheckpoint() {
  if (!confirm('清除断点并按当前勾选重新构建？（DB已有数据不受影响）')) return;
  await api('DELETE', '/api/library/checkpoint');
  $('lib-cp-bar').style.display = 'none';
}

async function startLibrary() {
  const tags = getSelectedTags();
  if (!tags.length) { alert('请至少选择一个分类。'); return; }
  const dmin = parseFloat($('lib-dmin').value) || 2;
  const dmax = parseFloat($('lib-dmax').value) || 4;
  if (dmin >= dmax) { alert('Delay Min 必须小于 Delay Max。'); return; }
  await _launchLibraryJob({
    selected_type_tags: tags,
    delay_min: dmin, delay_max: dmax,
    max_429_retries: parseInt($('lib-retries').value) || 8,
    retry_backoff_base: 15.0,
    price_min: $('lib-pmin').value !== '' ? parseFloat($('lib-pmin').value) : null,
    price_max: $('lib-pmax').value !== '' ? parseFloat($('lib-pmax').value) : null,
    resume: false,
  }, `全新构建：${tags.length} 个分类`);
}

async function _launchLibraryJob(params, statusLabel) {
  $('lib-progress-card').style.display = '';
  clearLog('lib-log');
  $('lib-bar').style.width = '0%'; $('lib-pct-label').textContent = '0%';
  $('lib-done-cats').textContent = '0'; $('lib-total-cats').textContent = params.selected_type_tags.length;
  $('lib-collected').textContent = '0'; $('lib-elapsed').textContent = '0s';
  $('lib-cat-label').textContent = '初始化中…';
  $('lib-badge').innerHTML = badge('running'); $('lib-status-text').textContent = statusLabel;
  $('lib-dl-wrap').style.display = 'none';
  $('lib-start-btn').disabled = true; $('lib-stop-btn').classList.remove('hidden');
  _libStartTs = Date.now() / 1000;
  clearInterval(_libTimer);
  _libTimer = setInterval(() => { $('lib-elapsed').textContent = fmtDur(_libStartTs); }, 1000);
  try {
    const { id } = await api('POST', '/api/jobs/library', params);
    _libJobId = id; localStorage.setItem('libJobId', id);
    openSSE(id, 'library', handleLibraryEvent);
  } catch (err) {
    $('lib-badge').innerHTML = badge('error');
    $('lib-status-text').textContent = '启动失败: ' + err.message;
    resetLibraryButtons();
  }
}

async function tryReconnectLibrary() {
  const savedId = localStorage.getItem('libJobId');
  if (!savedId) return false;
  try {
    const job = await api('GET', `/api/jobs/${savedId}`);
    if (job.type !== 'library' || job.status !== 'running') return false;
    _libJobId = savedId; _libStartTs = job.created_at;
    $('lib-progress-card').style.display = '';
    $('lib-badge').innerHTML = badge('running');
    $('lib-status-text').textContent = '已重连至进行中的构建任务';
    $('lib-start-btn').disabled = true; $('lib-stop-btn').classList.remove('hidden');
    $('lib-dl-wrap').style.display = 'none'; $('lib-cp-bar').style.display = 'none';
    if (job.progress) {
      const p = job.progress;
      $('lib-bar').style.width = (p.percent||0) + '%'; $('lib-pct-label').textContent = (p.percent||0) + '%';
      $('lib-done-cats').textContent = p.done_cats||0; $('lib-total-cats').textContent = p.total_cats||'–';
      $('lib-collected').textContent = (p.collected||0).toLocaleString();
      if (p.current_cat) $('lib-cat-label').textContent = `正在抓取：${p.current_cat}`;
    }
    if (job.log && job.log.length) job.log.forEach(l => appendLog('lib-log', l));
    clearInterval(_libTimer);
    _libTimer = setInterval(() => { $('lib-elapsed').textContent = fmtDur(_libStartTs); }, 1000);
    openSSE(savedId, 'library', handleLibraryEvent);
    return true;
  } catch { return false; }
}

function handleLibraryEvent(ev) {
  if (ev.type === 'log') {
    appendLog('lib-log', ev.text);
  } else if (ev.type === 'progress') {
    const p = ev.progress;
    $('lib-bar').style.width = (p.percent||0) + '%'; $('lib-pct-label').textContent = (p.percent||0) + '%';
    $('lib-done-cats').textContent = p.done_cats||0; $('lib-total-cats').textContent = p.total_cats||'–';
    $('lib-collected').textContent = (p.collected||0).toLocaleString();
    if (p.current_cat) $('lib-cat-label').textContent = `正在抓取：${p.current_cat} [${p.cat_index}/${p.total_cats}]`;
  } else if (ev.type === 'done') {
    clearInterval(_libTimer);
    $('lib-badge').innerHTML = badge(ev.status);
    $('lib-status-text').textContent = ev.status==='done' ? '构建完成！' : ev.status==='error' ? '出错，请查看日志' : '已停止';
    $('lib-dl-wrap').style.display = '';
    $('lib-cat-label').textContent = ev.status==='done' ? '所有分类已完成' : '';
    resetLibraryButtons();
    loadVizStats();
    if (ev.status !== 'done') refreshCheckpointBanner();
    else { $('lib-cp-bar').style.display = 'none'; localStorage.removeItem('libJobId'); }
  }
}

function resetLibraryButtons() { $('lib-start-btn').disabled = false; $('lib-stop-btn').classList.add('hidden'); }

// ══════════════════════════════════════════════════════════════════════════════
// SEARCH
// ══════════════════════════════════════════════════════════════════════════════
async function startSearch() {
  const query = $('s-query').value.trim();
  if (!query) { $('s-query').focus(); return; }
  const params = {
    query, max_items: parseInt($('s-max').value)||100,
    timeout: parseFloat($('s-timeout').value)||15,
    no_proxy: $('s-noproxy').checked, proxy: $('s-proxy').value.trim(),
    save_csv: $('s-savecsv').checked, save_json: $('s-savejson').checked,
  };
  $('s-status-card').style.display = ''; $('s-results-card').style.display = 'none';
  clearLog('s-log');
  $('s-badge').innerHTML = badge('running'); $('s-status-text').textContent = `Searching "${query}"…`;
  $('s-export-btns').style.display = 'none';
  $('s-start-btn').disabled = true; $('s-stop-btn').classList.remove('hidden');
  state.searchItems = [];
  try {
    const { id } = await api('POST', '/api/jobs/search', params);
    state.searchJobId = id; openSSE(id, 'search', handleSearchEvent);
  } catch (err) {
    $('s-badge').innerHTML = badge('error'); $('s-status-text').textContent = 'Failed: ' + err.message;
    resetSearchButtons();
  }
}

function handleSearchEvent(ev) {
  if (ev.type === 'log') { appendLog('s-log', ev.text); }
  else if (ev.type === 'items') {
    state.searchItems = ev.items; renderResults();
    $('s-results-card').style.display = ''; $('s-export-btns').style.display = '';
    $('s-results-title').textContent = `Results — ${ev.items.length} items`;
  } else if (ev.type === 'done') {
    $('s-badge').innerHTML = badge(ev.status);
    $('s-status-text').textContent = ev.status==='done' ? `Done — ${state.searchItems.length} items` : ev.status==='error' ? 'Error' : 'Stopped';
    resetSearchButtons();
  }
}
function resetSearchButtons() { $('s-start-btn').disabled = false; $('s-stop-btn').classList.add('hidden'); }

function sortResults(col) {
  if (state.sortCol === col) state.sortDir *= -1; else { state.sortCol = col; state.sortDir = 1; }
  renderResults();
}
function renderResults() {
  const filter = ($('s-filter').value||'').toLowerCase();
  let items = state.searchItems.filter(i => !filter || i.name.toLowerCase().includes(filter));
  const col = state.sortCol, dir = state.sortDir;
  items.sort((a,b) => { const va=a[col]??'', vb=b[col]??''; return typeof va==='number'&&typeof vb==='number' ? (va-vb)*dir : String(va).localeCompare(String(vb))*dir; });
  document.querySelectorAll('#s-table th').forEach(th => { th.classList.remove('sorted'); th.querySelector('.sort-icon').textContent='↕'; });
  const idx = ['name','steam_sell_price_usd','steam_sell_listings'].indexOf(col);
  if (idx >= 0) { const th=document.querySelectorAll('#s-table th')[idx]; th.classList.add('sorted'); th.querySelector('.sort-icon').textContent=dir>0?'▲':'▼'; }
  const tbody = $('s-tbody'); tbody.innerHTML = '';
  if (!items.length) { tbody.innerHTML = '<tr><td colspan="3" class="empty-state">No results</td></tr>'; }
  else items.forEach(item => {
    const tr = document.createElement('tr');
    const price = item.steam_sell_price_text || (item.steam_sell_price_usd!=null ? `$${item.steam_sell_price_usd.toFixed(2)}` : '–');
    tr.innerHTML = `<td class="name-cell">${escHtml(item.name)}<button class="copy-btn" onclick="copyText(${JSON.stringify(item.name)})">⎘</button></td><td class="price-cell">${escHtml(price)}</td><td class="listings-cell">${item.steam_sell_listings!=null?item.steam_sell_listings.toLocaleString():'–'}</td>`;
    tbody.appendChild(tr);
  });
  $('s-count').textContent = `${items.length} / ${state.searchItems.length}`;
}

function exportClient(fmt) {
  const items = state.searchItems; if (!items.length) return;
  let content, mime, ext;
  if (fmt === 'csv') {
    const fields = ['name','steam_sell_price_text','steam_sell_price_usd','steam_sell_listings'];
    content = [fields.join(','), ...items.map(it => fields.map(f=>`"${String(it[f]??'').replace(/"/g,'""')}"`).join(','))].join('\r\n');
    mime='text/csv'; ext='csv';
  } else { content=JSON.stringify(items,null,2); mime='application/json'; ext='json'; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content],{type:mime}));
  a.download = `steam_results_${Date.now()}.${ext}`; a.click();
  URL.revokeObjectURL(a.href);
}

// ══════════════════════════════════════════════════════════════════════════════
// BULK SCRAPE
// ══════════════════════════════════════════════════════════════════════════════
async function startBulk() {
  const dmin = parseFloat($('b-dmin').value)||2, dmax = parseFloat($('b-dmax').value)||4;
  if (dmin >= dmax) { alert('Delay Min must be less than Delay Max.'); return; }
  const maxVal = $('b-max').value.trim();
  const params = {
    output_file: $('b-fname').value.trim(),
    max_items: maxVal ? parseInt(maxVal) : null,
    start_offset: parseInt($('b-offset').value)||0,
    delay_min: dmin, delay_max: dmax,
    max_429_retries: parseInt($('b-retries').value)||8,
    retry_backoff_base: parseFloat($('b-backoff').value)||15,
  };
  $('b-progress-card').style.display = ''; clearLog('b-log');
  $('b-bar').style.width='0%'; $('b-pct-label').textContent='0%';
  $('b-collected').textContent='0'; $('b-total').textContent='–';
  $('b-requests').textContent='0'; $('b-elapsed').textContent='0s';
  $('b-badge').innerHTML=badge('running'); $('b-status-text').textContent='Initialising…';
  $('b-dl-btn-wrap').style.display='none';
  $('b-start-btn').disabled=true; $('b-stop-btn').classList.remove('hidden');
  state.bulkStartTs = Date.now()/1000;
  clearInterval(state.bulkTimer);
  state.bulkTimer = setInterval(()=>{ $('b-elapsed').textContent=fmtDur(state.bulkStartTs); }, 1000);
  try {
    const { id } = await api('POST', '/api/jobs/bulk', params);
    state.bulkJobId = id; openSSE(id, 'bulk', handleBulkEvent);
  } catch (err) {
    $('b-badge').innerHTML=badge('error'); $('b-status-text').textContent='Failed: '+err.message;
    resetBulkButtons();
  }
}
function handleBulkEvent(ev) {
  if (ev.type==='log') appendLog('b-log', ev.text);
  else if (ev.type==='progress') {
    const p=ev.progress, pct=p.percent||0;
    $('b-bar').style.width=pct+'%'; $('b-pct-label').textContent=pct+'%';
    $('b-collected').textContent=(p.collected||0).toLocaleString();
    $('b-total').textContent=p.total_market>0?p.total_market.toLocaleString():'–';
    $('b-requests').textContent=(p.requests||0).toLocaleString();
  } else if (ev.type==='done') {
    clearInterval(state.bulkTimer);
    $('b-badge').innerHTML=badge(ev.status);
    $('b-status-text').textContent=ev.status==='done'?'Completed':ev.status==='error'?'Error':'Stopped';
    $('b-dl-btn-wrap').style.display=''; resetBulkButtons();
  }
}
function resetBulkButtons() { $('b-start-btn').disabled=false; $('b-stop-btn').classList.add('hidden'); }

async function stopCurrentJob(type) {
  const jid = type==='search' ? state.searchJobId : type==='bulk' ? state.bulkJobId : _libJobId;
  if (!jid) return;
  try { await api('DELETE', `/api/jobs/${jid}`); } catch(e) { console.error('Stop failed:', e); }
  if (type==='search') resetSearchButtons();
  else if (type==='bulk') resetBulkButtons();
  else resetLibraryButtons();
}

async function downloadOutput(type) {
  const jid = type==='bulk' ? state.bulkJobId : type==='library' ? _libJobId : state.searchJobId;
  if (!jid) return;
  try {
    const job = await api('GET', `/api/jobs/${jid}`);
    if (job.output_file) window.location = `/api/files/${encodeURIComponent(job.output_file)}`;
    else alert('No output file saved.');
  } catch(e) { alert('Error: '+e.message); }
}

// ══════════════════════════════════════════════════════════════════════════════
// FILES
// ══════════════════════════════════════════════════════════════════════════════
async function loadFiles() {
  const el = $('files-body'); el.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const files = await api('GET', '/api/files');
    if (!files.length) { el.innerHTML = '<div class="empty-state">暂无输出文件。</div>'; return; }
    let html = '';
    files.forEach(f => {
      const ext = f.name.split('.').pop().toUpperCase();
      const icon = ext==='CSV' ? '📄' : ext==='JSON' ? '📋' : '📁';
      html += `<div class="file-item">
        <div class="file-icon">${icon}</div>
        <div class="file-info">
          <div class="file-name">${escHtml(f.name)}</div>
          <div class="file-meta">${fmtSize(f.size)} · ${fmtDate(f.modified)}</div>
        </div>
        <div class="file-actions">
          <a href="/api/files/${encodeURIComponent(f.name)}" download><button class="btn btn-ghost btn-sm">⬇</button></a>
          <button class="btn btn-danger btn-sm" onclick="deleteFile(${JSON.stringify(f.name)})">✕</button>
        </div>
      </div>`;
    });
    el.innerHTML = html;
  } catch(e) { el.innerHTML = `<div class="empty-state" style="color:var(--danger)">${e.message}</div>`; }
}

async function deleteFile(name) {
  if (!confirm(`Delete "${name}"?`)) return;
  try { await api('DELETE', `/api/files/${encodeURIComponent(name)}`); loadFiles(); }
  catch(e) { alert('Delete failed: '+e.message); }
}

// ══════════════════════════════════════════════════════════════════════════════
// HISTORY
// ══════════════════════════════════════════════════════════════════════════════
async function loadHistory() {
  const el = $('history-body'); el.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const jobs = await api('GET', '/api/jobs');
    if (!jobs.length) { el.innerHTML = '<div class="empty-state">暂无任务记录。</div>'; return; }
    const typeColors = { search:'var(--accent)', library:'var(--success)', bulk:'var(--warn)' };
    let html = '';
    jobs.forEach(j => {
      const dur = j.finished_at ? fmtDur(j.created_at,j.finished_at) : fmtDur(j.created_at);
      html += `<div class="job-item">
        <div class="job-info">
          <div class="job-type" style="color:${typeColors[j.type]||'var(--dim)'}">${j.type}</div>
          <div class="job-meta">${j.item_count.toLocaleString()} 条 · ${dur}</div>
        </div>
        ${badge(j.status)}
      </div>`;
    });
    el.innerHTML = html;
  } catch(e) { el.innerHTML = `<div class="empty-state" style="color:var(--danger)">${e.message}</div>`; }
}

// ══════════════════════════════════════════════════════════════════════════════
// DATABASE VISUALIZATION
// ══════════════════════════════════════════════════════════════════════════════
let _vizCatChart = null, _vizPriceChart = null;
let _vizPage = 0, _vizTotal = 0;
let _vizFiltersRestored = false;
const VIZ_PAGE_SIZE = 50;
const CHART_CFG = { color:'#5a7898', grid:'rgba(30,65,110,0.5)' };

async function loadViz() {
  if (!_vizFiltersRestored) { restoreVizFilters(); _vizFiltersRestored = true; }
  await loadVizStats();
  await loadVizTable();
}

function _vizFilterState() {
  return {
    search: $('viz-search').value || '',
    category: $('viz-cat-filter').value || '',
    sort_by: $('viz-sort-sel').value || 'name',
    steam_price_min: $('viz-steam-min').value || '',
    steam_price_max: $('viz-steam-max').value || '',
    buff_price_min: $('viz-buff-min').value || '',
    buff_price_max: $('viz-buff-max').value || '',
    listings_min: $('viz-listings-min').value || '',
    listings_max: $('viz-listings-max').value || '',
    has_steam_price: $('viz-has-steam').value || '',
    has_buff_price: $('viz-has-buff').value || '',
    has_ratio: $('viz-has-ratio').value || '',
  };
}

function saveVizFilters() { setCookie(VIZ_FILTER_COOKIE, JSON.stringify(_vizFilterState())); }

function restoreVizFilters() {
  const raw = getCookie(VIZ_FILTER_COOKIE);
  if (!raw) return;
  try {
    const s = JSON.parse(raw);
    $('viz-search').value = s.search || '';
    $('viz-cat-filter').value = s.category || '';
    $('viz-sort-sel').value = s.sort_by || 'name';
    $('viz-steam-min').value = s.steam_price_min || '';
    $('viz-steam-max').value = s.steam_price_max || '';
    $('viz-buff-min').value = s.buff_price_min || '';
    $('viz-buff-max').value = s.buff_price_max || '';
    $('viz-listings-min').value = s.listings_min || '';
    $('viz-listings-max').value = s.listings_max || '';
    $('viz-has-steam').value = s.has_steam_price || '';
    $('viz-has-buff').value = s.has_buff_price || '';
    $('viz-has-ratio').value = s.has_ratio || '';
  } catch (_) { deleteCookie(VIZ_FILTER_COOKIE); }
}

async function loadVizStats() {
  try {
    const [stats, priceDist] = await Promise.all([
      api('GET', '/api/db/stats'), api('GET', '/api/db/price_dist'),
    ]);
    const lastUpd = stats.last_updated ? new Date(stats.last_updated*1000).toLocaleString() : '–';
    $('viz-stats-row').innerHTML = `
      <div class="stat-tile"><div class="t-label">总条目</div><div class="t-val accent">${stats.total.toLocaleString()}</div></div>
      <div class="stat-tile"><div class="t-label">分类数</div><div class="t-val">${stats.by_category.length}</div></div>
      <div class="stat-tile" style="min-width:180px"><div class="t-label">最近更新</div><div class="t-val" style="font-size:13px;line-height:1.4">${lastUpd}</div></div>`;

    const sel = $('viz-cat-filter'), prev = sel.value;
    sel.innerHTML = '<option value="">全部分类</option>';
    stats.by_category.forEach(c => {
      const o = document.createElement('option');
      o.value = c.category_type||''; o.textContent = `${c.category_type||'未知'} (${c.count.toLocaleString()})`;
      sel.appendChild(o);
    });
    sel.value = prev;
    if (sel.value !== prev) sel.value = '';
    _renderCatChart(stats.by_category);
    _renderPriceChart(priceDist);
  } catch(e) { $('viz-stats-row').innerHTML = `<span style="color:var(--danger)">${e.message}</span>`; }
}

function _renderCatChart(byCategory) {
  const sorted = [...byCategory].sort((a,b) => b.count-a.count);
  const ctx = $('viz-cat-canvas').getContext('2d');
  if (_vizCatChart) _vizCatChart.destroy();
  _vizCatChart = new Chart(ctx, {
    type:'bar',
    data:{ labels:sorted.map(c=>c.category_type||'未知'), datasets:[{ data:sorted.map(c=>c.count), backgroundColor:'rgba(30,155,255,0.55)', borderColor:'rgba(30,155,255,1)', borderWidth:1, borderRadius:4 }] },
    options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{callbacks:{label:c=>` ${c.raw.toLocaleString()} 条`}} },
      scales:{ x:{grid:{color:CHART_CFG.grid},ticks:{color:CHART_CFG.color,font:{size:11}}}, y:{grid:{display:false},ticks:{color:CHART_CFG.color,font:{size:11}}} } }
  });
}

function _renderPriceChart(priceDist) {
  const ctx = $('viz-price-canvas').getContext('2d');
  if (_vizPriceChart) _vizPriceChart.destroy();
  const colors = priceDist.map((_,i) => `hsla(${200+i*16},72%,55%,0.72)`);
  _vizPriceChart = new Chart(ctx, {
    type:'bar',
    data:{ labels:priceDist.map(b=>b.label), datasets:[{ data:priceDist.map(b=>b.count), backgroundColor:colors, borderColor:colors.map(c=>c.replace('0.72','1')), borderWidth:1, borderRadius:4 }] },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{callbacks:{label:c=>` ${c.raw.toLocaleString()} 条`}} },
      scales:{ x:{grid:{display:false},ticks:{color:CHART_CFG.color,font:{size:11}}}, y:{grid:{color:CHART_CFG.grid},ticks:{color:CHART_CFG.color,font:{size:11}}} } }
  });
}

function vizReload() { saveVizFilters(); _vizPage=0; loadVizTable(); }
function _numOrBlank(id) { const v=($(id).value||'').trim(); return v===''?'':v; }
function _boolOrBlank(id) { const v=$(id).value; return v===''?'':v; }

function resetVizFilters() {
  ['viz-search','viz-steam-min','viz-steam-max','viz-buff-min','viz-buff-max','viz-listings-min','viz-listings-max'].forEach(id => $(id).value='');
  $('viz-cat-filter').value=''; $('viz-sort-sel').value='name';
  $('viz-has-steam').value=''; $('viz-has-buff').value=''; $('viz-has-ratio').value='';
  deleteCookie(VIZ_FILTER_COOKIE);
  vizReload();
}
function vizPage(dir) {
  const next = _vizPage+dir, max = Math.ceil(_vizTotal/VIZ_PAGE_SIZE)-1;
  if (next<0||next>max) return; _vizPage=next; loadVizTable();
}

async function loadVizTable() {
  const params = new URLSearchParams();
  [
    ['search', ($('viz-search').value||'').trim()],
    ['category', $('viz-cat-filter').value],
    ['sort_by', $('viz-sort-sel').value],
    ['steam_price_min', _numOrBlank('viz-steam-min')],
    ['steam_price_max', _numOrBlank('viz-steam-max')],
    ['buff_price_min', _numOrBlank('viz-buff-min')],
    ['buff_price_max', _numOrBlank('viz-buff-max')],
    ['listings_min', _numOrBlank('viz-listings-min')],
    ['listings_max', _numOrBlank('viz-listings-max')],
    ['has_steam_price', _boolOrBlank('viz-has-steam')],
    ['has_buff_price', _boolOrBlank('viz-has-buff')],
    ['has_ratio', _boolOrBlank('viz-has-ratio')],
    ['limit', String(VIZ_PAGE_SIZE)],
    ['offset', String(_vizPage*VIZ_PAGE_SIZE)],
  ].forEach(([k, v]) => { if (v !== '') params.set(k, v); });
  try {
    const { items, total } = await api('GET', `/api/db/items?${params}`);
    _vizTotal = total;
    const tbody = $('viz-tbody');
    if (!items.length) { tbody.innerHTML='<tr><td colspan="7" class="empty-state">暂无数据</td></tr>'; }
    else tbody.innerHTML = items.map(it => {
      const usd  = it.sell_price_usd != null ? `$${it.sell_price_usd.toFixed(2)}` : '–';
      const buff = it.buff_price     != null ? `¥${it.buff_price.toFixed(2)}`    : '–';
      const r = it.steam_buff_ratio;
      const ratio = r != null
        ? `<span class="ratio-pill ${r<1?'good':r<1.2?'warn':'bad'}">${r.toFixed(3)}</span>` : '–';
      const listings = it.sell_listings != null ? it.sell_listings.toLocaleString() : '–';
      const upd = it.last_updated ? new Date(it.last_updated*1000).toLocaleDateString() : '–';
      return `<tr>
        <td class="name-cell">${escHtml(it.name)}<button class="copy-btn" onclick="copyText(${JSON.stringify(it.name)})">⎘</button></td>
        <td style="color:var(--dim);font-size:12px">${escHtml(it.category_type||'–')}</td>
        <td class="price-cell">${usd}</td>
        <td style="color:#f0c060;font-variant-numeric:tabular-nums">${buff}</td>
        <td>${ratio}</td>
        <td class="listings-cell">${listings}</td>
        <td style="color:var(--dim);font-size:12px">${upd}</td>
      </tr>`;
    }).join('');
    const totalPages = Math.max(1, Math.ceil(total/VIZ_PAGE_SIZE));
    $('viz-count').textContent = `共 ${total.toLocaleString()} 条`;
    $('viz-page-info').textContent = `第 ${_vizPage+1} / ${totalPages} 页`;
    $('viz-prev-btn').disabled = _vizPage===0;
    $('viz-next-btn').disabled = _vizPage>=totalPages-1;
  } catch(e) { $('viz-tbody').innerHTML=`<tr><td colspan="7" class="empty-state" style="color:var(--danger)">${e.message}</td></tr>`; }
}

async function exportDb(fmt) {
  try { const r = await api('POST', `/api/db/export?fmt=${fmt}`); window.location=`/api/files/${encodeURIComponent(r.file)}`; }
  catch(e) { alert('Export failed: '+e.message); }
}

// ══════════════════════════════════════════════════════════════════════════════
// BUFF CSV IMPORT
// ══════════════════════════════════════════════════════════════════════════════
const IMPORT_FIELDS = [
  { key:'name',       label:'物品名称 *' },
  { key:'hash_name',  label:'Hash 名称' },
  { key:'buff_price', label:'BUFF 参考价' },
];
const IMPORT_HINTS = {
  name:      ['商品名称','名称','name','item_name','物品名称','card_csgo'],
  hash_name: ['hash_name','hash name','hash'],
  buff_price:['f_Strong','f_strong','buff参考价','buff价格','buff price','buff_price','参考价','最新售价'],
};
let _importHeaders = [];

function onImportFileChange() {
  const file = $('import-file').files[0]; if (!file) return;
  $('upload-hint').textContent = file.name;
  $('import-result').textContent = '';
  const reader = new FileReader();
  reader.onload = e => {
    _importHeaders = _parseCsvFirstRow(e.target.result);
    _renderImportMapping();
    $('import-mapping').classList.remove('hidden');
  };
  reader.readAsText(file, 'utf-8');
}
function _parseCsvFirstRow(text) {
  text = text.replace(/^\uFEFF/,'');
  const line = text.split(/\r?\n/)[0]||'';
  const cols=[]; let inQ=false, cur='';
  for (const c of line) {
    if (c==='"') inQ=!inQ;
    else if (c===','&&!inQ) { cols.push(cur.trim()); cur=''; }
    else cur+=c;
  }
  cols.push(cur.trim()); return cols;
}
function _guessCol(key) {
  const hints = IMPORT_HINTS[key]||[];
  return _importHeaders.find(h=>hints.some(hint=>h===hint)) ||
         _importHeaders.find(h=>hints.some(hint=>h.toLowerCase().includes(hint.toLowerCase()))) || '';
}
function _renderImportMapping() {
  $('import-mapping-rows').innerHTML = IMPORT_FIELDS.map(f => {
    const guessed = _guessCol(f.key);
    const opts = ['', ..._importHeaders].map(h => `<option value="${escHtml(h)}"${h===guessed?' selected':''}>${escHtml(h)||'-- 跳过 --'}</option>`).join('');
    return `<div class="field"><label>${escHtml(f.label)}</label><select id="imp-${f.key}">${opts}</select></div>`;
  }).join('');
}
async function doImport() {
  const file = $('import-file').files[0]; if (!file) return;
  if (!$('imp-name').value) { $('import-result').innerHTML='<span style="color:var(--danger)">请选择"物品名称"对应的列。</span>'; return; }
  const mapping={};
  IMPORT_FIELDS.forEach(f => { const v=$(`imp-${f.key}`).value; if (v) mapping[f.key]=v; });
  const fd = new FormData();
  fd.append('file', file); fd.append('mapping', JSON.stringify(mapping));
  $('import-result').innerHTML='<span style="color:var(--dim)">导入中…</span>';
  try {
    const r = await fetch('/api/db/import_csv', {method:'POST',body:fd});
    if (!r.ok) { const t=await r.text(); throw new Error(t); }
    const { imported, skipped } = await r.json();
    $('import-result').innerHTML = `<span style="color:var(--success)">✓ 导入 ${imported.toLocaleString()} 条</span>` +
      (skipped ? `<span style="color:var(--dim);margin-left:8px">（${skipped} 行跳过）</span>` : '');
    loadVizStats();
  } catch(e) { $('import-result').innerHTML=`<span style="color:var(--danger)">导入失败：${e.message}</span>`; }
}

// ── Enter key ─────────────────────────────────────────────────────────────────
document.getElementById('s-query').addEventListener('keydown', e => { if (e.key==='Enter') startSearch(); });

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  loadCategoryTree();
  loadViz();
  const reconnected = await tryReconnectLibrary();
  if (!reconnected) refreshCheckpointBanner();
})();
