/* ============================================================
   ERP 系统 - 前端逻辑（完整版）
   包含：基础框架、业务模块、发票、凭证、对账单、
        数据导入、备份恢复、打印、原生下载
   ============================================================ */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

/* ==================== 通用工具 ==================== */
function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
function fenToYuan(f) { return (Number(f) || 0) / 100; }
function yuanToFen(y) { return Math.round((Number(y) || 0) * 100); }
function fmtMoney(fen) {
  return '¥' + fenToYuan(fen).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
function fmtNum(n) {
  const v = Number(n || 0);
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}
function todayStr() {
  const d = new Date(), p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function shortTime(s) { return s ? String(s).replace('T', ' ').slice(0, 16) : '-'; }

/* ==================== 通用下载（弹出原生另存为对话框） ==================== */
async function downloadWithDialog(url, filename) {
  try {
    const res = await fetch(url, { credentials: 'same-origin' });
    if (!res.ok) {
      toast('下载失败：HTTP ' + res.status, 'error');
      return;
    }
    const blob = await res.blob();

    const b64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });

    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file) {
      const path = await window.pywebview.api.save_file(filename, b64);
      if (path === null) {
        toast('已取消下载');
        return;
      }
      if (typeof path === 'string' && path.startsWith('ERROR:')) {
        toast('保存失败：' + path.slice(6), 'error');
        return;
      }
      toast('已保存到：' + path, 'success');
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(a.href);
      }, 100);
      toast('已开始下载：' + filename, 'success');
    }
  } catch (e) {
    toast('下载失败：' + (e.message || e), 'error');
  }
}

/* ==================== 主题（Claude 明暗双主题） ==================== */
function initTheme() {
  let theme = 'light';
  try { theme = localStorage.getItem('erp-theme') || 'light'; } catch (e) {}
  if (theme !== 'dark' && theme !== 'light') {
    theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark' : 'light';
  }
  document.documentElement.dataset.theme = theme;
}
function toggleTheme() {
  const cur = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = cur;
  try { localStorage.setItem('erp-theme', cur); } catch (e) {}
  toast(cur === 'dark' ? '已切换到暗色模式' : '已切换到亮色模式');
}

/* ==================== 逐字晕开动画（Claude 式：每字 45ms 模糊→清晰，更快更利落） ==================== */
function revealText(el, text, delay) {
  const d = delay || 45;
  const frag = document.createDocumentFragment();
  for (const ch of String(text)) {
    const span = document.createElement('span');
    span.className = ch === ' ' ? 'reveal-char space' : 'reveal-char';
    span.textContent = ch === ' ' ? '\u00A0' : ch;
    span.style.animationDelay = (el._revealCount || 0) * d + 'ms';
    frag.appendChild(span);
    el._revealCount = (el._revealCount || 0) + 1;
  }
  el.innerHTML = '';
  el.appendChild(frag);
}

/* ==================== 全局 AI 助手（浮动对话面板，Text-to-Insight） ==================== */
function initAIAssistant() {
  // 浮动按钮
  const fab = document.createElement('div');
  fab.id = 'aiFab';
  fab.className = 'ai-fab';
  fab.innerHTML = ICONS.ai;
  fab.title = 'AI 经营助手';
  document.body.appendChild(fab);

  // 对话面板
  const panel = document.createElement('div');
  panel.id = 'aiPanel';
  panel.className = 'ai-panel';
  panel.innerHTML = `
    <div class="ai-panel-head">
      <span class="ai-panel-title">AI 经营助手</span>
      <button class="ai-panel-close">×</button>
    </div>
    <div class="ai-panel-body" id="aiChatBody">
      <div class="ai-msg ai-msg-bot">
        <div class="ai-msg-bubble">你好！我可以帮你查询经营数据。试试问：<br>
          · 本月销售额多少？<br>
          · 哪个客户买最多？<br>
          · 哪些商品库存不足？<br>
          · 今天有什么待办？</div>
      </div>
    </div>
    <div class="ai-panel-input">
      <input type="text" id="aiChatInput" placeholder="输入问题，回车发送..." autocomplete="off">
      <button id="aiChatSend" class="btn btn-primary btn-sm">发送</button>
    </div>`;
  document.body.appendChild(panel);

  let open = false;
  const toggle = () => {
    open = !open;
    panel.classList.toggle('show', open);
    if (open) setTimeout(() => $('#aiChatInput').focus(), 200);
  };
  fab.addEventListener('click', toggle);
  panel.querySelector('.ai-panel-close').addEventListener('click', toggle);

  const send = async () => {
    const input = $('#aiChatInput');
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    const body = $('#aiChatBody');
    body.innerHTML += `<div class="ai-msg ai-msg-user"><div class="ai-msg-bubble">${escapeHtml(q)}</div></div>`;
    body.scrollTop = body.scrollHeight;
    const ans = document.createElement('div');
    ans.className = 'ai-msg ai-msg-bot';
    ans.innerHTML = '<div class="ai-msg-bubble ai-stream-text"></div>';
    body.appendChild(ans);
    const bubble = ans.querySelector('.ai-msg-bubble');
    bubble.textContent = '思考中...';
    body.scrollTop = body.scrollHeight;

    try {
      const data = await api('/api/ai/query', 'POST', { question: q });
      bubble.textContent = '';
      // 逐字晕开模拟流式输出（LLM 接入后切换真实 SSE）
      const text = data.answer || '';
      await revealText(bubble, text, 25);
      if (data.nav) {
        bubble.innerHTML += `<br><button class="ai-msg-nav" data-nav="${data.nav}">查看详情 →</button>`;
        const nb = bubble.querySelector('.ai-msg-nav');
        if (nb) nb.addEventListener('click', () => { navigate(nb.dataset.nav); toggle(); });
      }
    } catch (e) {
      bubble.classList.add('ai-msg-error');
      bubble.textContent = '查询失败：' + (e.message || e);
    }
    body.scrollTop = body.scrollHeight;
  };
  $('#aiChatSend').addEventListener('click', send);
  $('#aiChatInput').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
}

/* ==================== 前端错误边界 ==================== */
function showErrorBoundary(msg) {
  let bar = $('#errorBoundary');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'errorBoundary';
    bar.className = 'error-boundary';
    bar.innerHTML = `
      <span class="eb-icon">!</span>
      <span class="eb-msg"></span>
      <button class="eb-close">×</button>
      <button class="eb-reload">刷新恢复</button>`;
    document.body.appendChild(bar);
    bar.querySelector('.eb-close').addEventListener('click', () => bar.remove());
    bar.querySelector('.eb-reload').addEventListener('click', () => location.reload());
  }
  bar.querySelector('.eb-msg').textContent = msg;
  bar.classList.add('show');
  clearTimeout(bar._t);
  bar._t = setTimeout(() => bar.classList.remove('show'), 8000);
}

/* ==================== 引导式空状态（解决"不知道该干什么"） ==================== */
function emptyGuide(icon, title, desc, btnText, btnId) {
  return `<div class="empty-guide">
    <div class="empty-guide-icon">${icon}</div>
    <div class="empty-guide-title">${title}</div>
    <div class="empty-guide-desc">${desc}</div>
    ${btnText ? `<button class="btn btn-primary" id="${btnId}">${btnText}</button>` : ''}
  </div>`;
}

/* ==================== 全局搜索（金蝶/用友式快捷入口） ==================== */
let searchCache = null;      // 已加载的基础数据缓存
let searchTimer = null;
let searchItems = [];        // 当前面板条目
let searchFocus = -1;

async function loadSearchCache() {
  if (searchCache) return searchCache;
  const [products, customers, suppliers, sales, purchase] = await Promise.all([
    api('/api/products'), api('/api/customers'), api('/api/suppliers'),
    api('/api/sales_orders'), api('/api/purchase_orders')
  ]);
  searchCache = { products, customers, suppliers, sales, purchase };
  return searchCache;
}

function searchNavItems() {
  const groups = [];
  MENUS.forEach(m => {
    if (m.adminOnly && (!currentUser || currentUser.role !== 'admin')) return;
    if (['dashboard', 'data_import'].includes(m.key)) return;
    groups.push({
      icon: m.icon, title: m.name, sub: '菜单：' + m.group, nav: m.key, tag: '菜单'
    });
  });
  return groups;
}

function runSearch(q) {
  q = (q || '').trim().toLowerCase();
  const panel = $('#searchPanel');
  if (!q) { panel.classList.add('hidden'); return; }
  loadSearchCache().then(cache => {
    const res = [];
    // AI 智能开单入口（Text-to-Action 雏形）
    if (/开单|开一张|销售单|下单|卖|售/.test(q)) {
      res.push({
        icon: ICONS.spark, title: 'AI 智能开单：' + q,
        sub: '解析并预填一张销售订单，确认后提交',
        nav: 'ai_open_order', tag: 'AI', orderText: q
      });
    }
    // 菜单
    searchNavItems().forEach(m => {
      if ((m.title + m.sub).toLowerCase().includes(q)) res.push(m);
    });
    const push = (list, icon, titleFn, subFn, nav) => {
      (list || []).slice(0, 6).forEach(it => {
        const title = titleFn(it), sub = subFn(it);
        if ((title + sub).toLowerCase().includes(q)) res.push({ icon, title, sub, nav, tag: nav });
      });
    };
    push(cache.products, ICONS.box, p => `${p.name}`, p => `编码 ${p.code} · 库存 ${fmtNum(p.stock)}`, 'products');
    push(cache.customers, ICONS.users, c => c.name, c => c.contact ? `联系人 ${c.contact}` : `电话 ${c.phone || '-'}`, 'customers');
    push(cache.suppliers, ICONS.truck, s => s.name, s => `联系人 ${s.contact || '-'}`, 'suppliers');
    push(cache.sales, ICONS.file, o => `${o.order_no}`, o => `${o.customer_name || '-'} · ${fmtMoney(o.final_amount)} · ${o.status}`, 'sales');
    push(cache.purchase, ICONS.download, o => `${o.order_no}`, o => `${o.supplier_name || '-'} · ${fmtMoney(o.final_amount)} · ${o.status}`, 'purchase');
    searchItems = res.slice(0, 12);
    searchFocus = -1;
    if (!searchItems.length) {
      panel.innerHTML = `<div class="search-empty">没有找到与「${escapeHtml(q)}」相关的内容</div>
        <div class="search-tip">试试「开单 客户A A4纸 50包 8折」可用 AI 智能开单</div>`;
      panel.classList.remove('hidden');
      return;
    }
    panel.innerHTML = searchItems.map((it, i) =>
      `<div class="search-item" data-i="${i}">
        <span class="si-icon">${it.icon}</span>
        <span class="si-main">
          <div class="si-title">${escapeHtml(it.title)}</div>
          <div class="si-sub">${escapeHtml(it.sub)}</div>
        </span>
        <span class="si-tag">${escapeHtml(it.tag)}</span>
      </div>`).join('') +
      `<div class="search-tip">按 / 打开搜索 · ↑↓ 选择 · Enter 跳转 · Esc 关闭</div>`;
    panel.classList.remove('hidden');
    $$('.search-item', panel).forEach(el => {
      el.addEventListener('mousedown', e => {
        e.preventDefault();
        closeSearch();
        const it = searchItems[Number(el.dataset.i)];
        if (!it) return;
        if (it.nav === 'ai_open_order') { doAIOpenOrder(it.orderText || q); return; }
        navigate(it.nav);
      });
    });
  }).catch(() => {});
}

/* AI 智能开单：解析自然语言 -> 预填建单弹窗 */
async function doAIOpenOrder(text) {
  try {
    toast('AI 正在解析开单指令...');
    const parsed = await api('/api/ai/parse_order', 'POST', { text });
    if (!parsed.items || !parsed.items.length) {
      toast('未能识别商品明细，请按示例描述：客户A A4纸 50包 8折', 'error');
      return;
    }
    if (!parsed.customer_id) {
      toast('未能识别客户，请带上客户名称', 'error');
      return;
    }
    const whs = await api('/api/warehouses');
    if (!whs.length) { toast('请先添加仓库', 'error'); return; }
    openSOCreateModal(whs, {
      customer_id: parsed.customer_id,
      discount: fenToYuan(parsed.discount),
      items: parsed.items.map(it => ({
        product_id: it.product_id, price: fenToYuan(it.price), qty: it.qty
      })),
      sourceTip: parsed.source === 'ai' ? 'AI 解析' : '规则解析'
    });
  } catch (e) {}
}

function closeSearch() {
  $('#searchPanel').classList.add('hidden');
  $('#globalSearch').blur();
  searchItems = [];
  searchFocus = -1;
}

function focusSearch() {
  const input = $('#globalSearch');
  input.focus();
  input.select();
}

function openSearchPanel() {
  const q = $('#globalSearch').value;
  if (!q.trim()) return;
  runSearch(q);
}

/* ==================== 全局状态 ==================== */
let currentUser = null;
let csrfToken = '';

/* ==================== Toast ==================== */
let toastTimer = null;
function toast(msg, type = 'success') {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast show ' + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast'; }, 2600);
}

/* ==================== API 封装 ==================== */
async function api(url, method = 'GET', data = null) {
  const opt = {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }
  };
  if (csrfToken) opt.headers['X-CSRF-Token'] = csrfToken;
  if (data !== null) opt.body = JSON.stringify(data);

  let json;
  try {
    const res = await fetch(url, opt);
    json = await res.json();
  } catch (e) {
    json = { code: 1, msg: '网络异常' };
  }
  if (json.code === 401) {
    currentUser = null;
    showLogin();
    throw new Error(json.msg);
  }
  if (json.code === 2) {
    const err = new Error(json.msg);
    err.creditWarning = true;
    throw err;
  }
  if (json.code !== 0) {
    toast(json.msg || '操作失败', 'error');
    throw new Error(json.msg);
  }
  return json.data;
}

/* ==================== 弹窗 ==================== */
function openModal(title, body, foot, width) {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = body;
  $('#modalFoot').innerHTML = foot || '';
  $('#modalBox').style.maxWidth = width || '640px';
  $('#modalMask').classList.remove('hidden');
}
function closeModal() {
  $('#modalMask').classList.add('hidden');
  $('#modalBody').innerHTML = '';
  $('#modalFoot').innerHTML = '';
}
function confirmDialog(message, onOk) {
  openModal('操作确认',
    `<p class="confirm-text">${escapeHtml(message)}</p>`,
    `<button class="btn" id="dlgCancel">取消</button>
     <button class="btn btn-danger" id="dlgOk">确定</button>`, '420px');
  $('#dlgCancel').addEventListener('click', closeModal);
  $('#dlgOk').addEventListener('click', async () => {
    closeModal();
    try { await onOk(); } catch (e) {}
  });
}

/* ==================== 图标库（SVG，线性风格，替代 emoji） ==================== */
const svg = p => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + p + '</svg>';
const ICONS = {
  dashboard: svg('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
  box: svg('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>'),
  folder: svg('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'),
  warehouse: svg('<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>'),
  users: svg('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
  truck: svg('<rect x="1" y="3" width="15" height="13" rx="1"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>'),
  briefcase: svg('<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'),
  file: svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>'),
  download: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
  list: svg('<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>'),
  credit: svg('<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>'),
  wallet: svg('<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>'),
  arrowDown: svg('<circle cx="12" cy="12" r="10"/><polyline points="8 12 12 16 16 12"/><line x1="12" y1="8" x2="12" y2="16"/>'),
  arrowUp: svg('<circle cx="12" cy="12" r="10"/><polyline points="16 12 12 8 8 12"/><line x1="12" y1="16" x2="12" y2="8"/>'),
  ai: svg('<path d="M12 2l1.9 5.8L20 9.7l-4.5 3.8 1.5 6-5-3.5-5 3.5 1.5-6L4 9.7l6.1-1.9z"/>'),
  landmark: svg('<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>'),
  receipt: svg('<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z"/><line x1="8" y1="7" x2="16" y2="7"/><line x1="8" y1="11" x2="16" y2="11"/><line x1="8" y1="15" x2="12" y2="15"/>'),
  book: svg('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'),
  clipboard: svg('<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>'),
  trend: svg('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>'),
  upload: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>'),
  database: svg('<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'),
  printer: svg('<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>'),
  key: svg('<path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>'),
  banknote: svg('<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01"/><path d="M18 12h.01"/>'),
  alert: svg('<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
  clock: svg('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
  check: svg('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'),
  bell: svg('<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>'),
  spark: svg('<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/><path d="M19 15l.9 2.6L22.5 18.5l-2.6.9L19 22l-.9-2.6-2.6-.9 2.6-.9z"/>'),
  refresh: svg('<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>'),
  plug: svg('<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z"/>'),
  boxFill: svg('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>'),
  api: svg('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'),
  search2: svg('<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>')
};

/* ==================== 菜单配置（分组） ==================== */
const NAV_GROUPS = [
  { title: '总览', items: [
    { key: 'dashboard', name: '工作台', icon: 'dashboard' }
  ]},
  { title: '基础资料', items: [
    { key: 'products',    name: '商品管理',   icon: 'box' },
    { key: 'categories',  name: '商品分类',   icon: 'folder' },
    { key: 'warehouses',  name: '仓库管理',   icon: 'warehouse' },
    { key: 'customers',   name: '客户管理',   icon: 'users' },
    { key: 'suppliers',   name: '供应商管理', icon: 'truck' },
    { key: 'employees',   name: '员工管理',   icon: 'briefcase' }
  ]},
  { title: '进销存', items: [
    { key: 'sales',    name: '销售订单', icon: 'file' },
    { key: 'purchase', name: '采购订单', icon: 'download' },
    { key: 'stock',    name: '库存流水', icon: 'list' }
  ]},
  { title: '财务', items: [
    { key: 'receivables', name: '应收账款', icon: 'credit' },
    { key: 'payables',    name: '应付账款', icon: 'wallet' },
    { key: 'receipts',    name: '回款单',   icon: 'arrowDown' },
    { key: 'payments',    name: '付款单',   icon: 'arrowUp' },
    { key: 'fund',        name: '资金账户', icon: 'landmark' },
    { key: 'invoices_in', name: '进项发票', icon: 'receipt' },
    { key: 'invoices_out', name: '销项发票', icon: 'receipt' },
    { key: 'vouchers',    name: '会计凭证', icon: 'book' },
    { key: 'statements',  name: '客户对账单', icon: 'clipboard' },
    { key: 'profit',      name: '利润分析', icon: 'trend' }
  ]},
  { title: '系统', items: [
    { key: 'data_import', name: '数据导入', icon: 'upload' },
    { key: 'backup',      name: '备份恢复', icon: 'database', adminOnly: true },
    { key: 'print_tpl',   name: '打印模板', icon: 'printer',  adminOnly: true },
    { key: 'users',       name: '用户管理', icon: 'key',      adminOnly: true },
    { key: 'ai_settings', name: 'AI 设置',  icon: 'plug',     adminOnly: true },
    { key: 'demo',        name: '演示数据', icon: 'spark',    adminOnly: true },
    { key: 'openapi',     name: '开放接口', icon: 'api' }
  ]}
];

const MENUS = NAV_GROUPS.reduce((acc, g) =>
  acc.concat(g.items.map(m => ({ ...m, group: g.title, icon: ICONS[m.icon] }))), []);

/* ==================== 启动 ==================== */
document.addEventListener('DOMContentLoaded', () => {
  bindGlobal();
  tickClock();
  setInterval(tickClock, 1000);
  checkLogin();
});

function bindGlobal() {
  initTheme();

  // ---- 前端错误边界（S 级标准：不白屏，友好提示+恢复） ----
  window.addEventListener('error', e => {
    console.error('[GlobalError]', e.message, e.filename, e.lineno);
    showErrorBoundary(e.message || '未知错误');
  });
  window.addEventListener('unhandledrejection', e => {
    console.error('[UnhandledRejection]', e.reason);
    const msg = e.reason && e.reason.message ? e.reason.message : String(e.reason || 'Promise 异常');
    if (!msg.includes('Failed to fetch') && !msg.includes('NetworkError')) {
      showErrorBoundary(msg);
    }
  });

  // ---- 全局 AI 助手（浮动按钮 + 对话面板） ----
  initAIAssistant();

  $('#loginBtn').addEventListener('click', doLogin);
  $('#loginPwd').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
  $('#logoutBtn').addEventListener('click', doLogout);
  $('#modalClose').addEventListener('click', closeModal);
  $('#modalMask').addEventListener('click', e => {
    if (e.target === $('#modalMask')) closeModal();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  // ---- 主题切换 ----
  $('#themeToggle').addEventListener('click', toggleTheme);

  // ---- 全局搜索 ----
  const searchInput = $('#globalSearch');
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(openSearchPanel, 220);
  });
  searchInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeSearch(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const items = $$('.search-item', $('#searchPanel'));
      if (!items.length) return;
      searchFocus = (searchFocus + 1) % items.length;
      items.forEach((el, i) => el.classList.toggle('focused', i === searchFocus));
      items[searchFocus].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const items = $$('.search-item', $('#searchPanel'));
      if (!items.length) return;
      searchFocus = searchFocus <= 0 ? items.length - 1 : searchFocus - 1;
      items.forEach((el, i) => el.classList.toggle('focused', i === searchFocus));
      items[searchFocus].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      const items = $$('.search-item', $('#searchPanel'));
      if (searchFocus >= 0 && items[searchFocus]) {
        const it = searchItems[searchFocus];
        closeSearch();
        if (it) navigate(it.nav);
      } else if (items.length === 1) {
        const it = searchItems[0];
        closeSearch();
        if (it) navigate(it.nav);
      }
    }
  });

  // ---- 快捷键：/ 或 Ctrl+K 聚焦搜索 ----
  document.addEventListener('keydown', e => {
    const tag = (e.target && e.target.tagName) || '';
    const isTyping = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable);
    if (e.key === '/' && !isTyping) {
      e.preventDefault();
      focusSearch();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      focusSearch();
    }
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('.search-box') && !e.target.closest('#searchPanel')) {
      $('#searchPanel').classList.add('hidden');
    }
  });
}

function tickClock() {
  const d = new Date(), p = n => String(n).padStart(2, '0');
  const w = ['日','一','二','三','四','五','六'][d.getDay()];
  $('#clock').textContent =
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} 周${w} ` +
    `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

async function checkLogin() {
  try {
    const res = await fetch('/api/current_user', { credentials: 'same-origin' });
    const json = await res.json();
    if (json.code === 0 && json.data) {
      currentUser = json.data;
      const tRes = await fetch('/api/csrf_token', { credentials: 'same-origin' });
      const tJson = await tRes.json();
      csrfToken = tJson.data || '';
      showMain();
      return;
    }
  } catch (e) {}
  showLogin();
}

async function doLogin() {
  const username = $('#loginUser').value.trim();
  const password = $('#loginPwd').value;
  if (!username || !password) { toast('请输入账号和密码', 'error'); return; }
  try {
    const data = await api('/api/login', 'POST', { username, password });
    currentUser = data;
    csrfToken = data.csrf_token || '';
    toast('登录成功');
    showMain();
  } catch (e) {}
}

async function doLogout() {
  confirmDialog('确定要退出登录吗？', async () => {
    try { await api('/api/logout', 'POST'); } catch (e) {}
    currentUser = null;
    csrfToken = '';
    showLogin();
  });
}

function showLogin() {
  $('#loginPage').classList.remove('hidden');
  $('#layout').classList.add('hidden');
  closeModal();
}

function showMain() {
  $('#loginPage').classList.add('hidden');
  $('#layout').classList.remove('hidden');
  renderNav();
  const n = currentUser.real_name || currentUser.username;
  $('#userName').textContent = n;
  $('#userRole').textContent = currentUser.role === 'admin' ? '管理员' : '普通员工';
  $('#avatar').textContent = n.charAt(0).toUpperCase();
  navigate('dashboard');
}

function renderNav() {
  const nav = $('#nav');
  nav.innerHTML = NAV_GROUPS.map(g => {
    const visible = g.items.filter(m => !m.adminOnly || (currentUser && currentUser.role === 'admin'));
    if (!visible.length) return '';
    return `<div class="nav-group">
      <div class="nav-group-title">${g.title}</div>
      ${visible.map(m => `<a class="nav-item" data-key="${m.key}">
        <span class="nav-icon">${ICONS[m.icon]}</span><span>${m.name}</span></a>`).join('')}
    </div>`;
  }).join('');
  $$('.nav-item', nav).forEach(el => {
    el.addEventListener('click', () => navigate(el.dataset.key));
  });
}

/* ==================== 路由 ==================== */
const PAGES = {
  dashboard:    renderDashboard,
  products:     renderProducts,
  categories:   renderCategories,
  warehouses:   renderWarehouses,
  customers:    renderCustomers,
  suppliers:    renderSuppliers,
  sales:        renderSales,
  purchase:     renderPurchase,
  receivables:  renderReceivables,
  payables:     renderPayables,
  receipts:     renderReceipts,
  payments:     renderPayments,
  fund:         renderFund,
  profit:       renderProfit,
  stock:        renderStock,
  employees:    renderEmployees,
  users:        renderUsers,
  invoices_in:  () => renderInvoices('进项'),
  invoices_out: () => renderInvoices('销项'),
  vouchers:     renderVouchers,
  statements:   renderStatements,
  data_import:  renderDataImport,
  backup:       renderBackup,
  print_tpl:    renderPrintTemplates,
  ai_settings:  renderAISettings,
  demo:         renderDemo,
  openapi:      renderOpenAPI
};

async function navigate(key) {
  const m = MENUS.find(x => x.key === key);
  if (!m) return;
  if (m.adminOnly && (!currentUser || currentUser.role !== 'admin')) {
    toast('无权限', 'error');
    return;
  }
  $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.key === key));
  $('#pageTitle').textContent = m.name;
  $('#content').innerHTML = '<div class="loading">加载中...</div>';
  // 页面入场动画（卡片逐张晕开上浮）
  const content = $('#content');
  content.classList.remove('page-anim');
  void content.offsetWidth;
  content.classList.add('page-anim');
  try {
    await PAGES[key]();
  } catch (e) {
    $('#content').innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

function statusBadge(s) {
  const map = {
    '待确认': 'badge-warn', '已出库': 'badge-success', '已入库': 'badge-success',
    '已取消': 'badge-muted', '未收': 'badge-warn', '部分收款': 'badge-info',
    '已收完': 'badge-success', '未付': 'badge-warn', '部分付款': 'badge-info',
    '已付完': 'badge-success'
  };
  return `<span class="badge ${map[s] || 'badge-info'}">${escapeHtml(s || '-')}</span>`;
}

/* ==================== 工作台（主次布局 + 横带分层 + 右侧待办栏） ==================== */
function trendChartSvg(trend) {
  const max = Math.max(...trend.map(t => t.sales), ...trend.map(t => t.profit), 1);
  const bw = 11, gap = 30, chartH = 120, baseY = 10, labelH = 22;
  const n = trend.length;
  const w = n * gap + 16;
  let gridLines = '';
  for (let g = 0; g <= 3; g++) {
    const y = baseY + chartH - (chartH * g / 3);
    gridLines += `<line x1="6" y1="${y}" x2="${w - 6}" y2="${y}" stroke="#EEF1F6" stroke-width="1"/>`;
  }
  let bars = '', labels = '';
  trend.forEach((t, i) => {
    const x = 8 + i * gap;
    const hS = Math.max((t.sales / max) * chartH, 1.5);
    const hP = Math.max((t.profit / max) * chartH, 1.5);
    bars += `<rect x="${x}" y="${baseY + chartH - hS}" width="${bw}" height="${hS}" rx="2" fill="#3B82F6"/>`;
    bars += `<rect x="${x + bw + 3}" y="${baseY + chartH - hP}" width="${bw}" height="${hP}" rx="2" fill="#10B981"/>`;
    labels += `<text x="${x + bw + 1.5}" y="${baseY + chartH + labelH - 4}" text-anchor="middle" font-size="11" fill="#98A1B3">${t.month.slice(5)}月</text>`;
  });
  const h = baseY + chartH + labelH;
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMin meet" role="img">${gridLines}${bars}${labels}</svg>`;
}

function buildTodoList(d) {
  const a = d.alerts || {};
  const items = [];
  if (a.overdue_ar_count > 0) {
    items.push({ sev: 'emergency', tag: '紧急', title: `${a.overdue_ar_count} 笔应收已逾期`,
      meta: `合计 ${fmtMoney(a.overdue_ar_amount)}，请尽快跟进回款`, nav: 'receivables' });
  }
  if (a.low_stock_count > 0) {
    items.push({ sev: 'important', tag: '重要', title: `${a.low_stock_count} 个商品低于安全库存`,
      meta: '建议及时补货，避免缺货', nav: 'products' });
  }
  if (a.pending_sales_count > 0) {
    items.push({ sev: 'important', tag: '重要', title: `${a.pending_sales_count} 张销售单待确认出库`,
      meta: '确认后扣减库存并生成应收', nav: 'sales' });
  }
  if (a.pending_purchase_count > 0) {
    items.push({ sev: 'tip', tag: '提示', title: `${a.pending_purchase_count} 张采购单待确认入库`,
      meta: '确认后更新库存与加权成本', nav: 'purchase' });
  }
  if (a.overdue_ap_count > 0) {
    items.push({ sev: 'tip', tag: '提示', title: `${a.overdue_ap_count} 笔应付已逾期`,
      meta: `合计 ${fmtMoney(a.overdue_ap_amount)}，请安排付款计划`, nav: 'payables' });
  }
  if (a.follow_up_count > 0) {
    items.push({ sev: 'important', tag: '重要', title: `${a.follow_up_count} 个客户待跟进`,
      meta: '建议电话回访或微信跟进，推进复购', nav: 'customers' });
  }
  if (!items.length) {
    items.push({ sev: 'tip', tag: '提示', title: '今日暂无待办事项', meta: '业务均处理完毕' });
  }
  return items;
}

async function renderDashboard() {
  const d = await api('/api/dashboard');
  const k = d.kpi;
  const isAdmin = currentUser && currentUser.role === 'admin';

  // ---- 顶部：4 个核心 KPI（紧凑，去掉冗余的回款/付款/应付） ----
  const coreKpis = isAdmin
    ? [
        { icon: ICONS.banknote, label: '今日销售额', value: fmtMoney(k.today_sales), cls: 'blue', nav: 'sales', sub: `${k.today_order_count} 笔订单` },
        { icon: ICONS.trend, label: '本月毛利', value: fmtMoney(k.month_gross_profit), cls: 'green', nav: 'profit', sub: `销售额 ${fmtMoney(k.month_sales_amount)}` },
        { icon: ICONS.credit, label: '应收余额', value: fmtMoney(k.ar_balance), cls: 'red', nav: 'receivables', sub: `逾期 ${d.alerts.overdue_ar_count} 笔` },
        { icon: ICONS.landmark, label: '资金总额', value: fmtMoney(k.fund_total), cls: 'cyan', nav: 'fund', sub: `应付 ${fmtMoney(k.ap_balance)}` }
      ]
    : [
        { icon: ICONS.file, label: '本月订单', value: k.month_order_count, cls: 'blue', nav: 'sales', sub: `${k.today_order_count} 笔今日` },
        { icon: ICONS.trend, label: '本月销售额', value: fmtMoney(k.month_sales_amount), cls: 'blue', nav: 'sales', sub: '' },
        { icon: ICONS.alert, label: '库存预警', value: d.alerts.low_stock_count, cls: 'red', nav: 'products', sub: '低于安全库存' },
        { icon: ICONS.clock, label: '待确认销售', value: d.alerts.pending_sales_count, cls: 'orange', nav: 'sales', sub: '需及时处理' }
      ];
  const kpiHtml = `<div class="dash-kpi-grid">
    ${coreKpis.map(kp => `<div class="kpi-card compact ${kp.cls} clickable" data-nav="${kp.nav}">
      <div class="kpi-icon">${kp.icon}</div>
      <div class="kpi-content">
        <div class="kpi-value">${kp.value}</div>
        <div class="kpi-label">${kp.label}</div>
        ${kp.sub ? `<div class="kpi-sub">${kp.sub}</div>` : ''}
      </div>
    </div>`).join('')}
  </div>`;

  // ---- 快速操作（高频入口前置：打开就知道该干什么） ----
  const quickHtml = `<div class="dash-quick">
    <div class="dash-quick-title">快速操作</div>
    <button class="quick-btn primary" id="qkSales">${ICONS.file}<span>新建销售单</span></button>
    <button class="quick-btn" id="qkAIOrder">${ICONS.spark}<span>AI 智能开单</span></button>
    <button class="quick-btn" id="qkPurchase">${ICONS.download}<span>新建采购单</span></button>
    <button class="quick-btn" id="qkReceipt">${ICONS.arrowDown}<span>登记回款</span></button>
    <button class="quick-btn" id="qkPayment">${ICONS.arrowUp}<span>登记付款</span></button>
  </div>`;

  // ---- 趋势图（紧凑） ----
  const trendHtml = isAdmin ? `<div class="dash-trend">
    <div class="section-title">近 6 月销售趋势</div>
    <div class="chart-legend">
      <span><i style="background:#3B82F6"></i>销售额</span>
      <span><i style="background:#10B981"></i>毛利</span>
    </div>
    <div class="trend-chart">${trendChartSvg(d.trend)}</div>
  </div>` : '';

  // ---- 需处理事项：tab 切换（待确认 / 低库存），减少冗余表格 ----
  const pendingRows = [
    ...d.pending_sales.map(o => ({ no: o.order_no, party: o.customer_name || '-', date: o.order_date || '-', amount: o.final_amount, type: '销售' })),
    ...d.pending_purchase.map(o => ({ no: o.order_no, party: o.supplier_name || '-', date: o.order_date || '-', amount: o.final_amount, type: '采购' }))
  ];
  const pendingBody = pendingRows.length
    ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>单号</th><th>往来单位</th><th>类型</th><th>日期</th><th class="num">金额</th></tr></thead>
        <tbody>${pendingRows.map(o => `<tr>
          <td>${escapeHtml(o.no)}</td>
          <td>${escapeHtml(o.party)}</td>
          <td><span class="badge ${o.type === '销售' ? 'badge-info' : 'badge-warn'}">${o.type}</span></td>
          <td>${escapeHtml(o.date)}</td>
          <td class="num">${fmtMoney(o.amount)}</td>
        </tr>`).join('')}</tbody></table></div>`
    : '<div class="empty">暂无待确认单据</div>';

  const lowBody = d.low_stock.length
    ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th class="num">当前库存</th>
          <th class="num">安全库存</th><th>状态</th></tr></thead>
        <tbody>${d.low_stock.map(p => `<tr>
          <td>${escapeHtml(p.code)}</td><td>${escapeHtml(p.name)}</td>
          <td class="num text-danger">${fmtNum(p.stock)}</td>
          <td class="num">${fmtNum(p.safety_stock)}</td>
          <td><span class="badge badge-danger">库存不足</span></td>
        </tr>`).join('')}</tbody></table></div>`
    : '<div class="empty">库存充足，无需补货</div>';

  const needActionHtml = `<div class="need-action">
    <div class="need-action-head">
      <div class="need-action-tab active" data-tab="pending">待确认业务
        <span class="count ${pendingRows.length ? '' : 'zero'}">${pendingRows.length}</span></div>
      <div class="need-action-tab" data-tab="lowstock">库存预警
        <span class="count ${d.alerts.low_stock_count ? '' : 'zero'}">${d.alerts.low_stock_count}</span></div>
    </div>
    <div class="need-action-body" id="naPending">${pendingBody}</div>
    <div class="need-action-body hidden" id="naLowstock">${lowBody}</div>
  </div>`;

  // ---- 侧栏：AI 摘要（紧凑） + 今日待办 + 逾期应收（精简 3 条） ----
  const todos = buildTodoList(d);
  const todoHtml = todos.length
    ? todos.map(t => `<div class="todo-item sev-${t.sev}" ${t.nav ? `data-nav="${t.nav}"` : ''}>
        <span class="todo-dot"></span>
        <div class="todo-body">
          <div class="todo-title"><span class="tag tag-${t.sev === 'emergency' ? 'emergency' : (t.sev === 'important' ? 'important' : 'tip')}">${t.tag}</span>${escapeHtml(t.title)}</div>
          <div class="todo-meta">${escapeHtml(t.meta || '')}</div>
        </div>
      </div>`).join('')
    : '<div class="todo-empty">今日暂无待办</div>';

  const overdueTop = d.overdue_receivables.slice(0, 3);
  const overdueHtml = overdueTop.length
    ? `<div class="overdue-list">
        ${overdueTop.map(r => `<div class="overdue-item" data-nav="receivables">
          <div><div class="oi-name">${escapeHtml(r.customer_name)}</div>
          <div class="oi-meta">逾期 ${r.days} 天 · ${escapeHtml(r.order_no)}</div></div>
          <div class="oi-amount">${fmtMoney(r.balance)}</div>
        </div>`).join('')}
        ${d.overdue_receivables.length > 3 ? `<div class="text-muted" style="text-align:center;font-size:12px;padding:4px 0;cursor:pointer" data-nav="receivables">还有 ${d.overdue_receivables.length - 3} 笔，查看全部 →</div>` : ''}
      </div>`
    : '<div class="todo-empty">暂无逾期应收</div>';

  // ---- 组装页面 ----
  $('#content').innerHTML = `
    <div class="dash-top">
      ${kpiHtml}
      ${quickHtml}
    </div>
    <div class="dash-layout">
      <div class="dash-main">
        ${trendHtml}
        ${needActionHtml}
      </div>
      <div class="dash-aside">
        <div class="ai-card compact" id="aiSummaryCard">
          <div class="ai-card-head">
            <div class="ai-card-title">
              <span class="spark">${ICONS.spark}</span>AI 经营摘要
              <span class="ai-badge ai-off" id="aiBadge">规则摘要</span>
            </div>
          </div>
          <div class="ai-text" id="aiText"><div class="loading">正在生成摘要...</div></div>
          <div class="ai-foot">
            <span id="aiHint"></span>
            <button class="ai-refresh" id="aiRefresh">${ICONS.refresh}<span>刷新</span></button>
          </div>
        </div>
        <div class="card todo-card">
          <div class="section-title">今日待办</div>
          <div class="todo-list">${todoHtml}</div>
        </div>
        <div class="card todo-card">
          <div class="section-title">逾期应收
            <span class="badge ${d.overdue_receivables.length ? 'badge-danger' : 'badge-success'}">${d.alerts.overdue_ar_count} 笔</span>
          </div>
          ${overdueHtml}
        </div>
      </div>
    </div>`;

  // ---- 绑定事件 ----
  $$('#content [data-nav]').forEach(el => el.addEventListener('click', () => navigate(el.dataset.nav)));
  // 需处理 tab 切换
  $$('.need-action-tab').forEach(tab => tab.addEventListener('click', () => {
    $$('.need-action-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    $('#naPending').classList.toggle('hidden', tab.dataset.tab !== 'pending');
    $('#naLowstock').classList.toggle('hidden', tab.dataset.tab !== 'lowstock');
  }));
  // 快速操作
  $('#qkSales').addEventListener('click', async () => {
    const whs = await api('/api/warehouses');
    if (whs.length) openSOCreateModal(whs); else toast('请先添加仓库', 'error');
  });
  $('#qkAIOrder').addEventListener('click', openAIOrderDialog);
  $('#qkPurchase').addEventListener('click', async () => {
    const whs = await api('/api/warehouses');
    if (whs.length) openPOCreateModal(whs); else toast('请先添加仓库', 'error');
  });
  $('#qkReceipt').addEventListener('click', openReceiptModal);
  $('#qkPayment').addEventListener('click', openPaymentModal);

  renderAISummary();
}

/* AI 经营摘要：规则兜底，接入 API 后自动切到大模型 */
async function renderAISummary() {
  const badge = $('#aiBadge'), text = $('#aiText'), hint = $('#aiHint'), btn = $('#aiRefresh');
  if (!text) return;
  const spin = s => { if (btn) btn.classList.toggle('spinning', s); };
  try {
    spin(true);
    const s = await api('/api/ai/summary');
    spin(false);
    badge.className = 'ai-badge ' + (s.source === 'ai' ? 'ai-on' : (s.source === 'fallback' ? 'ai-err' : 'ai-off'));
    badge.textContent = s.source === 'ai' ? 'AI 已接入'
      : (s.source === 'fallback' ? 'AI 回退' : '规则摘要');

    // ---- 结构化渲染：概览（逐字晕开）+ 异常标签 + 建议列表 ----
    const overview = s.overview || s.raw_text || '暂无摘要';
    const anomalies = Array.isArray(s.anomalies) ? s.anomalies : [];
    const actions = Array.isArray(s.actions) ? s.actions : [];

    const anomalyHtml = anomalies.length
      ? `<div class="ai-anomaly-list">${anomalies.map(a =>
          `<span class="ai-anomaly ${a.level || 'warning'}" ${a.nav ? `data-nav="${a.nav}"` : ''}>${escapeHtml(a.text)}</span>`).join('')}</div>`
      : '<div class="ai-empty-anomaly">当前无异常预警</div>';
    const actionHtml = actions.length
      ? `<ol class="ai-action-list">${actions.map(a =>
          `<li ${a.nav ? `data-nav="${a.nav}" class="clickable"` : ''}>${escapeHtml(a.text || a)}</li>`).join('')}</ol>`
      : '';

    text.innerHTML = `
      <div class="ai-overview" id="aiOverview"></div>
      <div class="ai-section-label">异常信号</div>
      ${anomalyHtml}
      ${actionHtml ? `<div class="ai-section-label">行动建议</div>${actionHtml}` : ''}
    `;
    // 概览逐字晕开，异常和建议直接显示
    const ov = $('#aiOverview');
    if (ov) revealText(ov, overview);
    // 异常和建议可点击跳转
    $$('#aiText [data-nav]').forEach(el => el.addEventListener('click', () => navigate(el.dataset.nav)));

    if (hint) hint.innerHTML = (s.source === 'ai' ? '由大模型实时生成，供经营参考'
      : (s.source === 'fallback' ? 'AI 调用失败，已自动回退规则摘要'
        : '未接入 AI：可在「系统 → AI 设置」填入接口后开启'))
      + ' <button class="ai-report-btn" id="aiReportBtn">生成报告</button>';
    const rpt = $('#aiReportBtn');
    if (rpt) rpt.addEventListener('click', () => window.open('/api/ai/report', '_blank'));
  } catch (e) {
    spin(false);
    badge.className = 'ai-badge ai-err';
    badge.textContent = '摘要失败';
    text.textContent = e.message || '摘要生成失败';
  }
  if (btn) btn.addEventListener('click', renderAISummary);
}

/* ==================== AI 智能开单（Text-to-Action 对话式入口） ==================== */
async function openAIOrderDialog() {
  openModal('AI 智能开单',
    `<div class="ai-order-input">
       <div class="ai-order-hint">用自然语言描述开单需求，AI 自动解析并预填表单</div>
       <textarea class="input" id="aiOrderText" rows="3"
         placeholder="例如：给客户广州启航办公用品开一张销售单，A4复印纸 50包，中性笔 100支，85折，备注：加急发货"></textarea>
       <div class="ai-order-examples">
         <span class="ai-example" data-text="给客户张三开一张销售单，A4纸 50包，8折">A4纸 50包 8折</span>
         <span class="ai-example" data-text="给客户李四开单，中性笔 100支 笔记本 30本">多商品</span>
         <span class="ai-example" data-text="50包A4纸给客户王五，备注：下午送达">数量前置+备注</span>
       </div>
     </div>
     <div id="aiOrderResult" class="hidden"></div>`,
    `<button class="btn" id="aiOrderClose">关闭</button>
     <button class="btn btn-primary" id="aiOrderParse">解析并预填</button>`, '640px');

  $('#aiOrderClose').addEventListener('click', closeModal);
  $$('.ai-example').forEach(el => el.addEventListener('click', () => {
    $('#aiOrderText').value = el.dataset.text;
  }));

  $('#aiOrderParse').addEventListener('click', async () => {
    const text = $('#aiOrderText').value.trim();
    if (!text) { toast('请输入开单描述', 'error'); return; }
    const btn = $('#aiOrderParse');
    btn.disabled = true; btn.textContent = '解析中...';
    try {
      const r = await api('/api/ai/parse_order', 'POST', { text });
      _renderAIOrderResult(r);
    } catch (e) {
      toast('解析失败：' + (e.message || ''), 'error');
    } finally {
      btn.disabled = false; btn.textContent = '解析并预填';
    }
  });
}

function _renderAIOrderResult(r) {
  const box = $('#aiOrderResult');
  const items = r.items || [];
  const total = items.reduce((s, it) => s + (it.amount || 0), 0);
  const final = Math.max(total - (r.discount || 0), 0);
  const custOk = !!r.customer_id;
  const itemsOk = items.length > 0;

  box.classList.remove('hidden');
  box.innerHTML = `
    <div class="ai-result-card">
      <div class="ai-result-head">
        <span class="ai-badge ${r.source === 'ai' ? 'ai-on' : 'ai-off'}">${r.source === 'ai' ? 'AI 解析' : '规则解析'}</span>
        ${r.tip ? `<span class="text-muted" style="font-size:12px">${escapeHtml(r.tip)}</span>` : ''}
      </div>
      <div class="ai-result-row">
        <span class="ai-result-label">客户</span>
        <span class="${custOk ? '' : 'text-danger'}">${escapeHtml(r.customer_name || '未识别，请手动选择')}</span>
      </div>
      <div class="ai-result-row">
        <span class="ai-result-label">商品明细</span>
        <div style="flex:1">
          ${items.length ? items.map(it => `<div class="ai-result-item">
            <span>${escapeHtml(it.name)}</span>
            <span class="text-muted">× ${it.qty}</span>
            <span>${fmtMoney(it.amount)}</span>
          </div>`).join('') : '<span class="text-danger">未识别商品</span>'}
        </div>
      </div>
      ${r.discount ? `<div class="ai-result-row">
        <span class="ai-result-label">优惠</span>
        <span>${fmtMoney(r.discount)}（${(r.discount_rate * 100).toFixed(0)}折）</span>
      </div>` : ''}
      ${r.remark ? `<div class="ai-result-row">
        <span class="ai-result-label">备注</span>
        <span>${escapeHtml(r.remark)}</span>
      </div>` : ''}
      <div class="ai-result-row ai-result-total">
        <span class="ai-result-label">实收合计</span>
        <span class="text-danger" style="font-size:16px;font-weight:600">${fmtMoney(final)}</span>
      </div>
      <div class="ai-result-actions">
        <button class="btn" id="aiOrderRetry">重新输入</button>
        <button class="btn btn-primary" id="aiOrderConfirm" ${(!custOk || !itemsOk) ? 'disabled' : ''}>
          ${(!custOk || !itemsOk) ? '信息不完整' : '确认并打开建单'}
        </button>
      </div>
    </div>`;

  $('#aiOrderRetry').addEventListener('click', () => {
    box.classList.add('hidden');
    $('#aiOrderText').focus();
  });
  const confirmBtn = $('#aiOrderConfirm');
  if (confirmBtn && !confirmBtn.disabled) {
    confirmBtn.addEventListener('click', async () => {
      closeModal();
      const whs = await api('/api/warehouses');
      if (whs.length) {
        openSOCreateModal(whs, {
          customer_id: r.customer_id,
          items: items,
          discount: r.discount || 0,
          remark: r.remark || '',
          sourceTip: r.source === 'ai' ? 'AI 解析' : '规则解析',
        });
      } else {
        toast('请先添加仓库', 'error');
      }
    });
  }
}

/* ==================== 商品分类 ==================== */
async function renderCategories() {
  const list = await api('/api/categories');
  const rows = list.length ? list.map(c => `<tr>
      <td>${c.id}</td><td>${escapeHtml(c.name)}</td>
      <td>${escapeHtml(c.remark || '-')}</td>
      <td class="num">${c.product_count}</td>
      <td><button class="btn-link" data-act="edit" data-id="${c.id}">编辑</button>
        <button class="btn-link danger" data-act="del" data-id="${c.id}">删除</button></td>
    </tr>`).join('') : '<tr><td colspan="5" class="empty">暂无分类</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left"><strong>商品分类</strong></div>
        <div class="toolbar-right"><button class="btn btn-primary" id="catAdd">+ 新增分类</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th style="width:60px">ID</th><th>名称</th><th>备注</th>
          <th class="num" style="width:100px">商品数</th>
          <th style="width:140px">操作</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;

  const cache = {}; list.forEach(c => cache[c.id] = c);
  $('#catAdd').addEventListener('click', () => openCatModal(null));
  $$('#content [data-act]').forEach(btn => btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id);
    if (btn.dataset.act === 'edit') openCatModal(cache[id]);
    else confirmDialog(`删除分类「${cache[id].name}」？`, async () => {
      await api('/api/categories/' + id, 'DELETE');
      toast('已删除'); renderCategories();
    });
  }));
}

function openCatModal(c) {
  const isEdit = !!c;
  openModal(isEdit ? '编辑分类' : '新增分类',
    `<div class="form-group"><label>名称 *</label>
       <input class="input" id="catName" value="${isEdit ? escapeHtml(c.name) : ''}"></div>
     <div class="form-group"><label>备注</label>
       <textarea class="input" id="catRemark">${isEdit ? escapeHtml(c.remark || '') : ''}</textarea></div>`,
    `<button class="btn" id="catCancel">取消</button>
     <button class="btn btn-primary" id="catSave">保存</button>`, '460px');
  $('#catCancel').addEventListener('click', closeModal);
  $('#catSave').addEventListener('click', async () => {
    const name = $('#catName').value.trim();
    if (!name) { toast('请输入名称', 'error'); return; }
    try {
      if (isEdit) await api('/api/categories/' + c.id, 'PUT', { name, remark: $('#catRemark').value.trim() });
      else await api('/api/categories', 'POST', { name, remark: $('#catRemark').value.trim() });
      closeModal(); toast('已保存'); renderCategories();
    } catch (e) {}
  });
}

/* ==================== 仓库 ==================== */
async function renderWarehouses() {
  const list = await api('/api/warehouses');
  const rows = list.map(w => `<tr>
      <td>${escapeHtml(w.code)}</td><td>${escapeHtml(w.name)}</td>
      <td>${escapeHtml(w.wtype || '-')}</td>
      <td>${escapeHtml(w.address || '-')}</td>
      <td><button class="btn-link" data-act="edit" data-id="${w.id}">编辑</button>
        <button class="btn-link danger" data-act="del" data-id="${w.id}">删除</button></td>
    </tr>`).join('');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left"><strong>仓库档案</strong></div>
        <div class="toolbar-right"><button class="btn btn-primary" id="whAdd">+ 新增仓库</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th>类型</th><th>地址</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;

  const cache = {}; list.forEach(w => cache[w.id] = w);
  $('#whAdd').addEventListener('click', () => openWhModal(null));
  $$('#content [data-act]').forEach(btn => btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id);
    if (btn.dataset.act === 'edit') openWhModal(cache[id]);
    else confirmDialog(`删除仓库「${cache[id].name}」？`, async () => {
      await api('/api/warehouses/' + id, 'DELETE');
      toast('已删除'); renderWarehouses();
    });
  }));
}

function openWhModal(w) {
  const isEdit = !!w;
  openModal(isEdit ? '编辑仓库' : '新增仓库',
    `<div class="form-row">
       <div class="form-group"><label>编码 *</label>
         <input class="input" id="wCode" value="${isEdit ? escapeHtml(w.code) : ''}"></div>
       <div class="form-group"><label>名称 *</label>
         <input class="input" id="wName" value="${isEdit ? escapeHtml(w.name) : ''}"></div>
     </div>
     <div class="form-group"><label>类型</label>
       <select class="input" id="wType">
         <option value="正常仓" ${!isEdit || w.wtype === '正常仓' ? 'selected' : ''}>正常仓</option>
         <option value="次品仓" ${isEdit && w.wtype === '次品仓' ? 'selected' : ''}>次品仓</option>
         <option value="在途仓" ${isEdit && w.wtype === '在途仓' ? 'selected' : ''}>在途仓</option>
       </select></div>
     <div class="form-group"><label>地址</label>
       <input class="input" id="wAddress" value="${isEdit ? escapeHtml(w.address || '') : ''}"></div>
     <div class="form-group"><label>备注</label>
       <input class="input" id="wRemark" value="${isEdit ? escapeHtml(w.remark || '') : ''}"></div>`,
    `<button class="btn" id="whCancel">取消</button>
     <button class="btn btn-primary" id="whSave">保存</button>`);
  $('#whCancel').addEventListener('click', closeModal);
  $('#whSave').addEventListener('click', async () => {
    const code = $('#wCode').value.trim(), name = $('#wName').value.trim();
    if (!code || !name) { toast('编码和名称不能为空', 'error'); return; }
    const payload = {
      code, name,
      wtype: $('#wType').value,
      address: $('#wAddress').value.trim(),
      remark: $('#wRemark').value.trim()
    };
    try {
      if (isEdit) await api('/api/warehouses/' + w.id, 'PUT', payload);
      else await api('/api/warehouses', 'POST', payload);
      closeModal(); toast('已保存'); renderWarehouses();
    } catch (e) {}
  });
}

/* ==================== 商品 ==================== */
async function renderProducts() {
  const [list, cats, whs] = await Promise.all([
    api('/api/products'), api('/api/categories'), api('/api/warehouses')
  ]);
  const renderRows = (data) => data.length ? data.map(p => {
    const low = (p.stock || 0) <= (p.safety_stock || 0);
    return `<tr>
      <td>${escapeHtml(p.code)}</td>
      <td>${escapeHtml(p.name)}</td>
      <td>${escapeHtml(p.category_name || '-')}</td>
      <td>${escapeHtml(p.unit || '-')}</td>
      <td class="num">${fmtMoney(p.purchase_price)}</td>
      <td class="num">${fmtMoney(p.sale_price)}</td>
      <td class="num">${fmtMoney(p.cost_price)}</td>
      <td class="num ${low ? 'text-danger' : ''}">${fmtNum(p.stock)}</td>
      <td class="num">${fmtNum(p.safety_stock)}</td>
      <td><button class="btn-link" data-act="edit" data-id="${p.id}">编辑</button>
        <button class="btn-link danger" data-act="del" data-id="${p.id}">删除</button></td>
    </tr>`;
  }).join('') : '<tr><td colspan="10" class="empty">暂无商品</td></tr>';

  const tableArea = list.length
    ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th>分类</th><th>单位</th>
          <th class="num">进价</th><th class="num">售价</th><th class="num">成本价</th>
          <th class="num">库存</th><th class="num">安全库存</th>
          <th style="width:140px">操作</th></tr></thead>
        <tbody id="pTbody">${renderRows(list)}</tbody></table></div>`
    : emptyGuide(ICONS.box, '还没有商品', '商品是进销存的基础，先录入商品才能开销售单和采购单。支持 Excel 批量导入。', '+ 新增商品', 'pAddEmpty');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="pSearch" placeholder="搜索编码/名称">
          <select class="input" id="pCat"><option value="">全部分类</option>
            ${cats.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('')}
          </select>
          <button class="btn btn-primary" id="pSearchBtn">查询</button>
          <button class="btn" onclick="downloadWithDialog('/api/export/products', 'products_' + Date.now() + '.csv')">导出CSV</button>
        </div>
        <div class="toolbar-right"><button class="btn btn-primary" id="pAdd">+ 新增商品</button></div>
      </div>
      ${tableArea}
    </div>`;

  const cache = {}; list.forEach(p => cache[p.id] = p);
  const bind = () => {
    $$('#pTbody [data-act]').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      if (btn.dataset.act === 'edit') openProdModal(cache[id], cats, whs);
      else confirmDialog(`删除商品「${cache[id].name}」？`, async () => {
        await api('/api/products/' + id, 'DELETE');
        toast('已删除'); refresh();
      });
    }));
  };
  const refresh = async () => {
    const kw = $('#pSearch').value.trim(), cid = $('#pCat').value;
    const data = await api('/api/products?keyword=' + encodeURIComponent(kw) +
      '&category_id=' + encodeURIComponent(cid));
    data.forEach(p => cache[p.id] = p);
    $('#pTbody').innerHTML = renderRows(data); bind();
  };
  $('#pSearchBtn').addEventListener('click', refresh);
  $('#pAdd').addEventListener('click', () => openProdModal(null, cats, whs));
  const pAddEmpty = $('#pAddEmpty'); if (pAddEmpty) pAddEmpty.addEventListener('click', () => openProdModal(null, cats, whs));
  bind();
}

function openProdModal(p, cats, whs) {
  const isEdit = !!p;
  const catOpts = cats.map(c =>
    `<option value="${c.id}" ${isEdit && p.category_id === c.id ? 'selected' : ''}>${escapeHtml(c.name)}</option>`
  ).join('');
  const whOpts = whs.map(w => `<option value="${w.id}">${escapeHtml(w.name)}</option>`).join('');

  openModal(isEdit ? '编辑商品' : '新增商品',
    `<div class="form-row">
       <div class="form-group"><label>编码 *</label>
         <input class="input" id="pCode" value="${isEdit ? escapeHtml(p.code) : ''}"></div>
       <div class="form-group"><label>名称 *</label>
         <input class="input" id="pName" value="${isEdit ? escapeHtml(p.name) : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>分类</label>
         <select class="input" id="pCat2"><option value="">未分类</option>${catOpts}</select></div>
       <div class="form-group"><label>单位</label>
         <input class="input" id="pUnit" value="${isEdit ? escapeHtml(p.unit || '个') : '个'}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>进价（元）</label>
         <input type="number" step="0.01" class="input" id="pPurchase"
                value="${isEdit ? fenToYuan(p.purchase_price) : 0}"></div>
       <div class="form-group"><label>售价（元）</label>
         <input type="number" step="0.01" class="input" id="pSale"
                value="${isEdit ? fenToYuan(p.sale_price) : 0}"></div>
     </div>
     ${isEdit ? '' : `<div class="form-row">
       <div class="form-group"><label>初始库存</label>
         <input type="number" class="input" id="pStock" value="0"></div>
       <div class="form-group"><label>入库仓库</label>
         <select class="input" id="pWh">${whOpts}</select></div>
     </div>`}
     <div class="form-row">
       <div class="form-group"><label>安全库存</label>
         <input type="number" class="input" id="pSafety"
                value="${isEdit ? (p.safety_stock || 0) : 0}"></div>
       <div class="form-group"><label>备注</label>
         <input class="input" id="pRemark"
                value="${isEdit ? escapeHtml(p.remark || '') : ''}"></div>
     </div>`,
    `<button class="btn" id="pCancel">取消</button>
     <button class="btn btn-primary" id="pSave">保存</button>`, '700px');

  $('#pCancel').addEventListener('click', closeModal);
  $('#pSave').addEventListener('click', async () => {
    const code = $('#pCode').value.trim(), name = $('#pName').value.trim();
    if (!code || !name) { toast('编码和名称不能为空', 'error'); return; }
    const payload = {
      code, name,
      category_id: $('#pCat2').value || null,
      unit: $('#pUnit').value.trim() || '个',
      purchase_price: parseFloat($('#pPurchase').value) || 0,
      sale_price: parseFloat($('#pSale').value) || 0,
      safety_stock: parseInt($('#pSafety').value) || 0,
      remark: $('#pRemark').value.trim()
    };
    if (!isEdit) {
      payload.stock = parseInt($('#pStock').value) || 0;
      payload.warehouse_id = parseInt($('#pWh').value) || 1;
    }
    try {
      if (isEdit) await api('/api/products/' + p.id, 'PUT', payload);
      else await api('/api/products', 'POST', payload);
      closeModal(); toast('已保存'); renderProducts();
    } catch (e) {}
  });
}

/* ==================== 客户 ==================== */
async function renderCustomers() {
  const list = await api('/api/customers');
  const renderRows = (data) => data.length ? data.map(c => `<tr>
      <td>${escapeHtml(c.code)}</td><td>${escapeHtml(c.name)}</td>
      <td>${escapeHtml(c.contact || '-')}</td>
      <td>${escapeHtml(c.phone || '-')}</td>
      <td class="num">${fmtMoney(c.credit_limit)}</td>
      <td><span class="badge badge-info">${escapeHtml(c.level || '普通')}</span></td>
      <td class="num">${fmtMoney(c.total_sales)}</td>
      <td class="num ${c.ar_balance > 0 ? 'text-danger' : ''}">${fmtMoney(c.ar_balance)}</td>
      <td><button class="btn-link" data-act="edit" data-id="${c.id}">编辑</button>
        <button class="btn-link danger" data-act="del" data-id="${c.id}">删除</button></td>
    </tr>`).join('') : '<tr><td colspan="9" class="empty">暂无客户</td></tr>';

  const tableArea = list.length
    ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th>联系人</th><th>电话</th>
          <th class="num">信用额度</th><th>等级</th><th class="num">累计销售</th>
          <th class="num">应收余额</th><th style="width:140px">操作</th></tr></thead>
        <tbody id="cTbody">${renderRows(list)}</tbody></table></div>`
    : emptyGuide(ICONS.users, '还没有客户', '客户是销售的起点，先录入客户信息才能开销售单和管理应收。', '+ 新增客户', 'cAddEmpty');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="cSearch" placeholder="搜索编码/名称/联系人">
          <button class="btn btn-primary" id="cSearchBtn">查询</button>
          <button class="btn" onclick="downloadWithDialog('/api/export/customers', 'customers_' + Date.now() + '.csv')">导出CSV</button>
        </div>
        <div class="toolbar-right"><button class="btn btn-primary" id="cAdd">+ 新增客户</button></div>
      </div>
      ${tableArea}
    </div>`;

  const cache = {}; list.forEach(c => cache[c.id] = c);
  const bind = () => {
    $$('#cTbody [data-act]').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      if (btn.dataset.act === 'edit') openCustModal(cache[id]);
      else confirmDialog(`删除客户「${cache[id].name}」？`, async () => {
        await api('/api/customers/' + id, 'DELETE');
        toast('已删除'); refresh();
      });
    }));
  };
  const refresh = async () => {
    const kw = $('#cSearch').value.trim();
    const data = await api('/api/customers?keyword=' + encodeURIComponent(kw));
    data.forEach(c => cache[c.id] = c);
    $('#cTbody').innerHTML = renderRows(data); bind();
  };
  $('#cSearchBtn').addEventListener('click', refresh);
  $('#cAdd').addEventListener('click', () => openCustModal(null));
  const cAddEmpty = $('#cAddEmpty'); if (cAddEmpty) cAddEmpty.addEventListener('click', () => openCustModal(null));
  bind();
}

function openCustModal(c) {
  const isEdit = !!c;
  openModal(isEdit ? '编辑客户' : '新增客户',
    `<div class="form-row">
       <div class="form-group"><label>编码 *</label>
         <input class="input" id="cCode" value="${isEdit ? escapeHtml(c.code) : ''}"></div>
       <div class="form-group"><label>名称 *</label>
         <input class="input" id="cName" value="${isEdit ? escapeHtml(c.name) : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>联系人</label>
         <input class="input" id="cContact" value="${isEdit ? escapeHtml(c.contact || '') : ''}"></div>
       <div class="form-group"><label>电话</label>
         <input class="input" id="cPhone" value="${isEdit ? escapeHtml(c.phone || '') : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>信用额度（元）</label>
         <input type="number" step="0.01" class="input" id="cCredit"
                value="${isEdit ? fenToYuan(c.credit_limit) : 0}"></div>
       <div class="form-group"><label>等级</label>
         <select class="input" id="cLevel">
           ${['普通','银牌','金牌','钻石'].map(l =>
             `<option value="${l}" ${isEdit && c.level === l ? 'selected' : ''}>${l}</option>`
           ).join('')}
         </select></div>
     </div>
     <div class="form-group"><label>地址</label>
       <input class="input" id="cAddress" value="${isEdit ? escapeHtml(c.address || '') : ''}"></div>
     <div class="form-group"><label>备注</label>
       <input class="input" id="cRemark" value="${isEdit ? escapeHtml(c.remark || '') : ''}"></div>`,
    `<button class="btn" id="cCancel">取消</button>
     <button class="btn btn-primary" id="cSave">保存</button>`);
  $('#cCancel').addEventListener('click', closeModal);
  $('#cSave').addEventListener('click', async () => {
    const code = $('#cCode').value.trim(), name = $('#cName').value.trim();
    if (!code || !name) { toast('编码和名称不能为空', 'error'); return; }
    const payload = {
      code, name,
      contact: $('#cContact').value.trim(),
      phone: $('#cPhone').value.trim(),
      address: $('#cAddress').value.trim(),
      credit_limit: parseFloat($('#cCredit').value) || 0,
      level: $('#cLevel').value,
      remark: $('#cRemark').value.trim()
    };
    try {
      if (isEdit) await api('/api/customers/' + c.id, 'PUT', payload);
      else await api('/api/customers', 'POST', payload);
      closeModal(); toast('已保存'); renderCustomers();
    } catch (e) {}
  });
}

/* ==================== 供应商 ==================== */
async function renderSuppliers() {
  const list = await api('/api/suppliers');
  const renderRows = (data) => data.length ? data.map(s => `<tr>
      <td>${escapeHtml(s.code)}</td><td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(s.contact || '-')}</td>
      <td>${escapeHtml(s.phone || '-')}</td>
      <td><button class="btn-link" data-act="edit" data-id="${s.id}">编辑</button>
        <button class="btn-link danger" data-act="del" data-id="${s.id}">删除</button></td>
    </tr>`).join('') : '<tr><td colspan="5" class="empty">暂无供应商</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="sSearch" placeholder="搜索编码/名称">
          <button class="btn btn-primary" id="sSearchBtn">查询</button>
          <button class="btn" onclick="downloadWithDialog('/api/export/suppliers', 'suppliers_' + Date.now() + '.csv')">导出CSV</button>
        </div>
        <div class="toolbar-right"><button class="btn btn-primary" id="sAdd">+ 新增供应商</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th>联系人</th><th>电话</th>
          <th style="width:140px">操作</th></tr></thead>
        <tbody id="sTbody">${renderRows(list)}</tbody></table></div>
    </div>`;

  const cache = {}; list.forEach(s => cache[s.id] = s);
  const bind = () => {
    $$('#sTbody [data-act]').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      if (btn.dataset.act === 'edit') openSupModal(cache[id]);
      else confirmDialog(`删除供应商「${cache[id].name}」？`, async () => {
        await api('/api/suppliers/' + id, 'DELETE');
        toast('已删除'); refresh();
      });
    }));
  };
  const refresh = async () => {
    const kw = $('#sSearch').value.trim();
    const data = await api('/api/suppliers?keyword=' + encodeURIComponent(kw));
    data.forEach(s => cache[s.id] = s);
    $('#sTbody').innerHTML = renderRows(data); bind();
  };
  $('#sSearchBtn').addEventListener('click', refresh);
  $('#sAdd').addEventListener('click', () => openSupModal(null));
  bind();
}

function openSupModal(s) {
  const isEdit = !!s;
  openModal(isEdit ? '编辑供应商' : '新增供应商',
    `<div class="form-row">
       <div class="form-group"><label>编码 *</label>
         <input class="input" id="sCode" value="${isEdit ? escapeHtml(s.code) : ''}"></div>
       <div class="form-group"><label>名称 *</label>
         <input class="input" id="sName" value="${isEdit ? escapeHtml(s.name) : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>联系人</label>
         <input class="input" id="sContact" value="${isEdit ? escapeHtml(s.contact || '') : ''}"></div>
       <div class="form-group"><label>电话</label>
         <input class="input" id="sPhone" value="${isEdit ? escapeHtml(s.phone || '') : ''}"></div>
     </div>
     <div class="form-group"><label>地址</label>
       <input class="input" id="sAddress" value="${isEdit ? escapeHtml(s.address || '') : ''}"></div>
     <div class="form-group"><label>备注</label>
       <input class="input" id="sRemark" value="${isEdit ? escapeHtml(s.remark || '') : ''}"></div>`,
    `<button class="btn" id="sCancel">取消</button>
     <button class="btn btn-primary" id="sSave">保存</button>`);
  $('#sCancel').addEventListener('click', closeModal);
  $('#sSave').addEventListener('click', async () => {
    const code = $('#sCode').value.trim(), name = $('#sName').value.trim();
    if (!code || !name) { toast('编码和名称不能为空', 'error'); return; }
    const payload = {
      code, name,
      contact: $('#sContact').value.trim(),
      phone: $('#sPhone').value.trim(),
      address: $('#sAddress').value.trim(),
      remark: $('#sRemark').value.trim()
    };
    try {
      if (isEdit) await api('/api/suppliers/' + s.id, 'PUT', payload);
      else await api('/api/suppliers', 'POST', payload);
      closeModal(); toast('已保存'); renderSuppliers();
    } catch (e) {}
  });
}

/* ==================== 销售订单 ==================== */
async function renderSales() {
  const [list, whs] = await Promise.all([api('/api/sales_orders'), api('/api/warehouses')]);
  const renderRows = (data) => data.length ? data.map(o => `<tr>
      <td>${escapeHtml(o.order_no)}</td>
      <td>${escapeHtml(o.customer_name || '-')}</td>
      <td>${escapeHtml(o.order_date || '-')}</td>
      <td class="num">${fmtMoney(o.final_amount)}</td>
      <td class="num ${(o.gross_profit || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtMoney(o.gross_profit)}</td>
      <td>${statusBadge(o.status)}</td>
      <td><button class="btn-link" data-act="view" data-id="${o.id}">详情</button>
        ${o.status === '待确认' ? `<button class="btn-link" data-act="confirm" data-id="${o.id}">出库</button>` : ''}
        ${o.status !== '已取消' ? `<button class="btn-link danger" data-act="cancel" data-id="${o.id}">取消</button>` : ''}
        ${o.status !== '已出库' ? `<button class="btn-link danger" data-act="del" data-id="${o.id}">删除</button>` : ''}
      </td>
    </tr>`).join('') : '<tr><td colspan="7" class="empty">暂无销售订单</td></tr>';

  const tableArea = list.length
    ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>订单号</th><th>客户</th><th>日期</th><th class="num">实收</th>
          <th class="num">毛利</th><th>状态</th><th style="width:220px">操作</th></tr></thead>
        <tbody id="soTbody">${renderRows(list)}</tbody></table></div>`
    : emptyGuide(ICONS.file, '还没有销售订单', '销售订单是核心收入流。需要先有商品和客户，然后新建销售单完成出库。', '+ 新建销售订单', 'soAddEmpty');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="soSearch" placeholder="搜索订单号/客户">
          <select class="input" id="soStatus">
            <option value="">全部状态</option>
            <option value="待确认">待确认</option>
            <option value="已出库">已出库</option>
            <option value="已取消">已取消</option>
          </select>
          <button class="btn btn-primary" id="soSearchBtn">查询</button>
          <button class="btn" onclick="downloadWithDialog('/api/export/sales_orders', 'sales_orders_' + Date.now() + '.csv')">导出CSV</button>
        </div>
        <div class="toolbar-right"><button class="btn btn-primary" id="soAdd">+ 新建销售订单</button></div>
      </div>
      ${tableArea}
    </div>`;

  const refresh = async () => {
    const kw = $('#soSearch').value.trim(), st = $('#soStatus').value;
    const data = await api('/api/sales_orders?keyword=' + encodeURIComponent(kw) +
      '&status=' + encodeURIComponent(st));
    $('#soTbody').innerHTML = renderRows(data); bind();
  };
  const bind = () => {
    $$('#soTbody [data-act]').forEach(btn => btn.addEventListener('click', async () => {
      const id = Number(btn.dataset.id), act = btn.dataset.act;
      if (act === 'view') showSODetail(id);
      else if (act === 'confirm') confirmDialog('确定出库？将扣减库存并生成应收。', async () => {
        await api('/api/sales_orders/' + id + '/confirm', 'POST');
        toast('出库成功'); refresh();
      });
      else if (act === 'cancel') confirmDialog('确定取消订单？', async () => {
        await api('/api/sales_orders/' + id + '/cancel', 'POST');
        toast('已取消'); refresh();
      });
      else confirmDialog('确定删除？', async () => {
        await api('/api/sales_orders/' + id, 'DELETE');
        toast('已删除'); refresh();
      });
    }));
  };
  $('#soSearchBtn').addEventListener('click', refresh);
  $('#soAdd').addEventListener('click', () => openSOCreateModal(whs));
  const soAddEmpty = $('#soAddEmpty'); if (soAddEmpty) soAddEmpty.addEventListener('click', () => openSOCreateModal(whs));
  bind();
}

async function showSODetail(oid) {
  const d = await api('/api/sales_orders/' + oid);
  const itemRows = d.items.map(it => `<tr>
      <td>${escapeHtml(it.product_code || '-')}</td>
      <td>${escapeHtml(it.product_name || '-')}</td>
      <td class="num">${fmtMoney(it.price)}</td>
      <td class="num text-muted">${fmtMoney(it.cost_price)}</td>
      <td class="num">${fmtNum(it.qty)}</td>
      <td class="num">${fmtMoney(it.amount)}</td>
    </tr>`).join('');

  openModal('销售订单详情',
    `<div class="info-grid">
       <div><span class="info-label">订单号：</span>${escapeHtml(d.order_no)}</div>
       <div><span class="info-label">客户：</span>${escapeHtml(d.customer_name || '-')}</div>
       <div><span class="info-label">仓库：</span>${escapeHtml(d.warehouse_name || '-')}</div>
       <div><span class="info-label">日期：</span>${escapeHtml(d.order_date || '-')}</div>
       <div><span class="info-label">状态：</span>${statusBadge(d.status)}</div>
     </div>
     <table class="detail-table">
       <thead><tr><th>编码</th><th>名称</th><th class="num">售价</th>
         <th class="num">成本价</th><th class="num">数量</th><th class="num">金额</th></tr></thead>
       <tbody>${itemRows}</tbody></table>
     <div style="margin-top:14px;text-align:right;font-size:14px">
       <div>总额：<strong>${fmtMoney(d.total_amount)}</strong></div>
       <div>优惠：<strong>${fmtMoney(d.discount)}</strong></div>
       <div>成本：<strong>${fmtMoney(d.total_cost)}</strong></div>
       <div>毛利：<strong class="${(d.gross_profit || 0) >= 0 ? 'text-success' : 'text-danger'}">${fmtMoney(d.gross_profit)}</strong></div>
       <div style="font-size:18px">实收：<strong class="text-danger">${fmtMoney(d.final_amount)}</strong></div>
     </div>`,
    `<button class="btn" id="soPrint">打印送货单</button>
     <button class="btn" id="soClose">关闭</button>`, '720px');

  $('#soClose').addEventListener('click', closeModal);
  $('#soPrint').addEventListener('click', () => printSalesOrder(oid));
}

async function openSOCreateModal(whs, prefill) {
  const [customers, products] = await Promise.all([api('/api/customers'), api('/api/products')]);
  if (!customers.length) { toast('请先添加客户', 'error'); return; }
  if (!products.length) { toast('请先添加商品', 'error'); return; }
  if (!whs.length) { toast('请先添加仓库', 'error'); return; }

  openModal(prefill
      ? `智能开单（${prefill.sourceTip || '解析'}）· 确认后提交`
      : '新建销售订单',
    `<div class="form-row">
       <div class="form-group"><label>客户 *</label>
         <select class="input" id="soCust"><option value="">-- 选择客户 --</option>
           ${customers.map(c => `<option value="${c.id}">${escapeHtml(c.code)} ${escapeHtml(c.name)}</option>`).join('')}
         </select></div>
       <div class="form-group"><label>仓库 *</label>
         <select class="input" id="soWh">${whs.map(w => `<option value="${w.id}">${escapeHtml(w.name)}</option>`).join('')}</select></div>
       <div class="form-group"><label>日期</label>
         <input type="date" class="input" id="soDate" value="${todayStr()}"></div>
     </div>
     <div class="form-group"><label>商品明细 *</label>
       <table class="table items-table">
         <thead><tr><th style="width:40%">商品</th><th style="width:20%">单价</th>
           <th style="width:18%">数量</th><th>金额</th><th style="width:70px">操作</th></tr></thead>
         <tbody id="soItems"></tbody></table>
       <button type="button" class="btn btn-sm" id="soAddItem">+ 添加商品</button></div>
     <div class="form-row">
       <div class="form-group"><label>优惠金额（元）</label>
         <input type="number" class="input" id="soDiscount" value="0" step="0.01" min="0"></div>
       <div class="form-group"><label>应收合计</label>
         <div class="total-amount" id="soTotal">¥0.00</div></div>
     </div>
     <div class="form-group"><label>备注</label>
       <input class="input" id="soRemark"></div>`,
    `<button class="btn" id="soCancel">取消</button>
     <button class="btn btn-primary" id="soSubmit">提交订单</button>`, '860px');

  const tbody = $('#soItems');
  const calc = () => {
    let total = 0;
    tbody.querySelectorAll('tr').forEach(tr => {
      const price = parseFloat(tr.querySelector('.item-price').value) || 0;
      const qty = parseInt(tr.querySelector('.item-qty').value) || 0;
      const amt = yuanToFen(price) * qty;
      tr.querySelector('.item-amount').textContent = fmtMoney(amt);
      total += amt;
    });
    const disc = yuanToFen(parseFloat($('#soDiscount').value) || 0);
    $('#soTotal').textContent = fmtMoney(Math.max(total - disc, 0));
  };
  const addRow = () => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><select class="input item-product">
        <option value="">-- 选择商品 --</option>
        ${products.map(p => `<option value="${p.id}" data-price="${fenToYuan(p.sale_price)}">${escapeHtml(p.code)} ${escapeHtml(p.name)}（库存 ${p.stock}）</option>`).join('')}
      </select></td>
      <td><input type="number" step="0.01" class="input item-price" value="0"></td>
      <td><input type="number" class="input item-qty" value="1" min="1"></td>
      <td class="item-amount">¥0.00</td>
      <td><button type="button" class="btn btn-sm btn-danger item-del">删除</button></td>`;
    tbody.appendChild(tr);
    tr.querySelector('.item-product').addEventListener('change', ev => {
      const opt = ev.target.selectedOptions[0];
      tr.querySelector('.item-price').value = opt && opt.dataset.price ? opt.dataset.price : 0;
      calc();
    });
    tr.querySelector('.item-price').addEventListener('input', calc);
    tr.querySelector('.item-qty').addEventListener('input', calc);
    tr.querySelector('.item-del').addEventListener('click', () => { tr.remove(); calc(); });
    calc();
  };
  $('#soAddItem').addEventListener('click', addRow);
  $('#soDiscount').addEventListener('input', calc);
  addRow();

  // 智能开单预填（Text-to-Action）
  if (prefill) {
    if (prefill.customer_id) $('#soCust').value = String(prefill.customer_id);
    if (typeof prefill.discount === 'number') $('#soDiscount').value = fenToYuan(prefill.discount);
    if (prefill.remark) $('#soRemark').value = prefill.remark;
    if (prefill.items && prefill.items.length) {
      $$('#soItems tr').forEach(tr => tr.remove());
      prefill.items.forEach(it => {
        addRow();
        const trs = $$('#soItems tr');
        const tr = trs[trs.length - 1];
        tr.querySelector('.item-product').value = String(it.product_id);
        tr.querySelector('.item-product').dispatchEvent(new Event('change'));
        tr.querySelector('.item-price').value = fenToYuan(it.price);
        tr.querySelector('.item-qty').value = it.qty;
      });
    }
    calc();
    toast('已按指令预填，请核对后提交', 'success');
  }

  $('#soCancel').addEventListener('click', closeModal);
  $('#soSubmit').addEventListener('click', async () => {
    const customer_id = parseInt($('#soCust').value, 10);
    if (!customer_id) { toast('请选择客户', 'error'); return; }
    const items = [];
    tbody.querySelectorAll('tr').forEach(tr => {
      const pid = parseInt(tr.querySelector('.item-product').value, 10);
      const price = parseFloat(tr.querySelector('.item-price').value) || 0;
      const qty = parseInt(tr.querySelector('.item-qty').value) || 0;
      if (pid && qty > 0) items.push({ product_id: pid, price, qty });
    });
    if (!items.length) { toast('请添加商品明细', 'error'); return; }
    const payload = {
      customer_id,
      warehouse_id: parseInt($('#soWh').value, 10),
      order_date: $('#soDate').value || todayStr(),
      discount: parseFloat($('#soDiscount').value) || 0,
      remark: $('#soRemark').value.trim(),
      items
    };
    try {
      const res = await api('/api/sales_orders', 'POST', payload);
      closeModal(); toast('订单创建成功：' + res.order_no);
      renderSales();
    } catch (e) {
      if (e.creditWarning) {
        confirmDialog(e.message + '\n\n是否强制下单？', async () => {
          payload.force = 1;
          const res = await api('/api/sales_orders', 'POST', payload);
          closeModal(); toast('订单创建成功：' + res.order_no);
          renderSales();
        });
      }
    }
  });
}

/* ==================== 采购订单 ==================== */
async function renderPurchase() {
  const [list, whs] = await Promise.all([api('/api/purchase_orders'), api('/api/warehouses')]);
  const renderRows = (data) => data.length ? data.map(o => `<tr>
      <td>${escapeHtml(o.order_no)}</td>
      <td>${escapeHtml(o.supplier_name || '-')}</td>
      <td>${escapeHtml(o.order_date || '-')}</td>
      <td class="num">${fmtMoney(o.final_amount)}</td>
      <td>${statusBadge(o.status)}</td>
      <td><button class="btn-link" data-act="view" data-id="${o.id}">详情</button>
        ${o.status === '待确认' ? `<button class="btn-link" data-act="confirm" data-id="${o.id}">入库</button>` : ''}
        ${o.status !== '已取消' ? `<button class="btn-link danger" data-act="cancel" data-id="${o.id}">取消</button>` : ''}
        ${o.status !== '已入库' ? `<button class="btn-link danger" data-act="del" data-id="${o.id}">删除</button>` : ''}
      </td>
    </tr>`).join('') : '<tr><td colspan="6" class="empty">暂无采购订单</td></tr>';

  const tableArea = list.length
    ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>订单号</th><th>供应商</th><th>日期</th><th class="num">实付</th>
          <th>状态</th><th style="width:220px">操作</th></tr></thead>
        <tbody id="poTbody">${renderRows(list)}</tbody></table></div>`
    : emptyGuide(ICONS.download, '还没有采购订单', '采购订单用于补货入库，更新库存和成本。需要先有商品和供应商。', '+ 新建采购订单', 'poAddEmpty');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="poSearch" placeholder="搜索订单号/供应商">
          <button class="btn btn-primary" id="poSearchBtn">查询</button>
          <button class="btn" onclick="downloadWithDialog('/api/export/purchase_orders', 'purchase_orders_' + Date.now() + '.csv')">导出CSV</button>
        </div>
        <div class="toolbar-right"><button class="btn btn-primary" id="poAdd">+ 新建采购订单</button></div>
      </div>
      ${tableArea}
    </div>`;

  const refresh = async () => {
    const kw = $('#poSearch').value.trim();
    const data = await api('/api/purchase_orders?keyword=' + encodeURIComponent(kw));
    $('#poTbody').innerHTML = renderRows(data); bind();
  };
  const bind = () => {
    $$('#poTbody [data-act]').forEach(btn => btn.addEventListener('click', async () => {
      const id = Number(btn.dataset.id), act = btn.dataset.act;
      if (act === 'view') showPODetail(id);
      else if (act === 'confirm') confirmDialog('确定入库？将增加库存、更新成本价、生成应付。', async () => {
        await api('/api/purchase_orders/' + id + '/confirm', 'POST');
        toast('入库成功'); refresh();
      });
      else if (act === 'cancel') confirmDialog('确定取消订单？', async () => {
        await api('/api/purchase_orders/' + id + '/cancel', 'POST');
        toast('已取消'); refresh();
      });
      else confirmDialog('确定删除？', async () => {
        await api('/api/purchase_orders/' + id, 'DELETE');
        toast('已删除'); refresh();
      });
    }));
  };
  $('#poSearchBtn').addEventListener('click', refresh);
  $('#poAdd').addEventListener('click', () => openPOCreateModal(whs));
  const poAddEmpty = $('#poAddEmpty'); if (poAddEmpty) poAddEmpty.addEventListener('click', () => openPOCreateModal(whs));
  bind();
}

async function showPODetail(oid) {
  const d = await api('/api/purchase_orders/' + oid);
  const itemRows = d.items.map(it => `<tr>
      <td>${escapeHtml(it.product_code || '-')}</td>
      <td>${escapeHtml(it.product_name || '-')}</td>
      <td class="num">${fmtMoney(it.price)}</td>
      <td class="num">${fmtNum(it.qty)}</td>
      <td class="num">${fmtMoney(it.amount)}</td>
      <td>${escapeHtml(it.batch_no || '-')}</td>
      <td>${escapeHtml(it.expire_date || '-')}</td>
    </tr>`).join('');

  openModal('采购订单详情',
    `<div class="info-grid">
       <div><span class="info-label">订单号：</span>${escapeHtml(d.order_no)}</div>
       <div><span class="info-label">供应商：</span>${escapeHtml(d.supplier_name || '-')}</div>
       <div><span class="info-label">仓库：</span>${escapeHtml(d.warehouse_name || '-')}</div>
       <div><span class="info-label">日期：</span>${escapeHtml(d.order_date || '-')}</div>
       <div><span class="info-label">状态：</span>${statusBadge(d.status)}</div>
     </div>
     <table class="detail-table">
       <thead><tr><th>编码</th><th>名称</th><th class="num">进价</th><th class="num">数量</th>
         <th class="num">金额</th><th>批次</th><th>有效期</th></tr></thead>
       <tbody>${itemRows}</tbody></table>
     <div style="margin-top:14px;text-align:right;font-size:16px">
       实付：<strong class="text-danger">${fmtMoney(d.final_amount)}</strong></div>`,
    `<button class="btn" id="poPrint">打印入库单</button>
     <button class="btn" id="poClose">关闭</button>`, '720px');

  $('#poClose').addEventListener('click', closeModal);
  $('#poPrint').addEventListener('click', () => printPurchaseOrder(oid));
}

async function openPOCreateModal(whs) {
  const [suppliers, products] = await Promise.all([api('/api/suppliers'), api('/api/products')]);
  if (!suppliers.length) { toast('请先添加供应商', 'error'); return; }
  if (!products.length) { toast('请先添加商品', 'error'); return; }
  if (!whs.length) { toast('请先添加仓库', 'error'); return; }

  openModal('新建采购订单',
    `<div class="form-row">
       <div class="form-group"><label>供应商 *</label>
         <select class="input" id="poSup"><option value="">-- 选择供应商 --</option>
           ${suppliers.map(s => `<option value="${s.id}">${escapeHtml(s.code)} ${escapeHtml(s.name)}</option>`).join('')}
         </select></div>
       <div class="form-group"><label>仓库 *</label>
         <select class="input" id="poWh">${whs.map(w => `<option value="${w.id}">${escapeHtml(w.name)}</option>`).join('')}</select></div>
       <div class="form-group"><label>日期</label>
         <input type="date" class="input" id="poDate" value="${todayStr()}"></div>
     </div>
     <div class="form-group"><label>商品明细 *</label>
       <table class="table items-table">
         <thead><tr><th style="width:36%">商品</th><th style="width:18%">进价</th>
           <th style="width:14%">数量</th><th style="width:18%">批次</th>
           <th>金额</th><th style="width:70px">操作</th></tr></thead>
         <tbody id="poItems"></tbody></table>
       <button type="button" class="btn btn-sm" id="poAddItem">+ 添加商品</button></div>
     <div class="form-row">
       <div class="form-group"><label>优惠金额（元）</label>
         <input type="number" class="input" id="poDiscount" value="0" step="0.01" min="0"></div>
       <div class="form-group"><label>应付合计</label>
         <div class="total-amount" id="poTotal">¥0.00</div></div>
     </div>
     <div class="form-group"><label>备注</label>
       <input class="input" id="poRemark"></div>`,
    `<button class="btn" id="poCancel">取消</button>
     <button class="btn btn-primary" id="poSubmit">提交订单</button>`, '900px');

  const tbody = $('#poItems');
  const calc = () => {
    let total = 0;
    tbody.querySelectorAll('tr').forEach(tr => {
      const price = parseFloat(tr.querySelector('.item-price').value) || 0;
      const qty = parseInt(tr.querySelector('.item-qty').value) || 0;
      const amt = yuanToFen(price) * qty;
      tr.querySelector('.item-amount').textContent = fmtMoney(amt);
      total += amt;
    });
    const disc = yuanToFen(parseFloat($('#poDiscount').value) || 0);
    $('#poTotal').textContent = fmtMoney(Math.max(total - disc, 0));
  };
  const addRow = () => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><select class="input item-product">
        <option value="">-- 选择商品 --</option>
        ${products.map(p => `<option value="${p.id}" data-price="${fenToYuan(p.purchase_price)}">${escapeHtml(p.code)} ${escapeHtml(p.name)}</option>`).join('')}
      </select></td>
      <td><input type="number" step="0.01" class="input item-price" value="0"></td>
      <td><input type="number" class="input item-qty" value="1" min="1"></td>
      <td><input class="input item-batch"></td>
      <td class="item-amount">¥0.00</td>
      <td><button type="button" class="btn btn-sm btn-danger item-del">删除</button></td>`;
    tbody.appendChild(tr);
    tr.querySelector('.item-product').addEventListener('change', ev => {
      const opt = ev.target.selectedOptions[0];
      tr.querySelector('.item-price').value = opt && opt.dataset.price ? opt.dataset.price : 0;
      calc();
    });
    tr.querySelector('.item-price').addEventListener('input', calc);
    tr.querySelector('.item-qty').addEventListener('input', calc);
    tr.querySelector('.item-del').addEventListener('click', () => { tr.remove(); calc(); });
    calc();
  };
  $('#poAddItem').addEventListener('click', addRow);
  $('#poDiscount').addEventListener('input', calc);
  addRow();

  $('#poCancel').addEventListener('click', closeModal);
  $('#poSubmit').addEventListener('click', async () => {
    const supplier_id = parseInt($('#poSup').value, 10);
    if (!supplier_id) { toast('请选择供应商', 'error'); return; }
    const items = [];
    tbody.querySelectorAll('tr').forEach(tr => {
      const pid = parseInt(tr.querySelector('.item-product').value, 10);
      const price = parseFloat(tr.querySelector('.item-price').value) || 0;
      const qty = parseInt(tr.querySelector('.item-qty').value) || 0;
      if (pid && qty > 0) items.push({
        product_id: pid, price, qty,
        batch_no: tr.querySelector('.item-batch').value.trim()
      });
    });
    if (!items.length) { toast('请添加商品明细', 'error'); return; }
    const payload = {
      supplier_id,
      warehouse_id: parseInt($('#poWh').value, 10),
      order_date: $('#poDate').value || todayStr(),
      discount: parseFloat($('#poDiscount').value) || 0,
      remark: $('#poRemark').value.trim(),
      items
    };
    try {
      const res = await api('/api/purchase_orders', 'POST', payload);
      closeModal(); toast('采购订单创建成功：' + res.order_no);
      renderPurchase();
    } catch (e) {}
  });
}

/* ==================== 应收 / 应付 ==================== */
async function renderReceivables() {
  const list = await api('/api/receivables');
  const renderRows = (data) => data.length ? data.map(r => `<tr>
      <td>${escapeHtml(r.order_no)}</td>
      <td>${escapeHtml(r.customer_name || '-')}</td>
      <td class="num">${fmtMoney(r.amount)}</td>
      <td class="num text-success">${fmtMoney(r.received)}</td>
      <td class="num text-danger">${fmtMoney((r.amount || 0) - (r.received || 0))}</td>
      <td>${statusBadge(r.status)}</td>
      <td>${escapeHtml(r.due_date || '-')}</td>
    </tr>`).join('') : '<tr><td colspan="7" class="empty">暂无应收</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="rSearch" placeholder="搜索订单号/客户">
          <select class="input" id="rStatus">
            <option value="">全部</option>
            <option value="未收">未收</option>
            <option value="部分收款">部分收款</option>
            <option value="已收完">已收完</option>
          </select>
          <button class="btn btn-primary" id="rSearchBtn">查询</button>
          <button class="btn" id="rAging">账龄分析</button>
          <button class="btn" onclick="downloadWithDialog('/api/export/receivables', 'receivables_' + Date.now() + '.csv')">导出CSV</button>
        </div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>订单号</th><th>客户</th><th class="num">应收</th>
          <th class="num">已收</th><th class="num">余额</th><th>状态</th><th>到期日</th></tr></thead>
        <tbody id="rTbody">${renderRows(list)}</tbody></table></div>
    </div>`;

  const refresh = async () => {
    const kw = $('#rSearch').value.trim(), st = $('#rStatus').value;
    const data = await api('/api/receivables?keyword=' + encodeURIComponent(kw) +
      '&status=' + encodeURIComponent(st));
    $('#rTbody').innerHTML = renderRows(data);
  };
  $('#rSearchBtn').addEventListener('click', refresh);
  $('#rAging').addEventListener('click', async () => {
    const d = await api('/api/receivables/aging');
    const sumRows = d.summary.map(s =>
      `<tr><td>${s.bucket} 天</td><td class="num">${fmtMoney(s.amount)}</td></tr>`).join('');
    const detRows = d.details.map(x => `<tr>
        <td>${escapeHtml(x.order_no)}</td>
        <td>${escapeHtml(x.customer_name || '-')}</td>
        <td class="num">${fmtMoney(x.balance)}</td>
        <td class="num">${x.days}</td><td>${x.bucket}</td>
      </tr>`).join('');
    openModal('账龄分析',
      `<div class="card-title">汇总</div>
       <table class="detail-table" style="margin-bottom:16px">
         <thead><tr><th>账龄</th><th class="num">金额</th></tr></thead>
         <tbody>${sumRows}</tbody></table>
       <div class="card-title">明细</div>
       <div style="max-height:300px;overflow:auto"><table class="detail-table">
         <thead><tr><th>订单号</th><th>客户</th><th class="num">余额</th>
           <th class="num">账龄(天)</th><th>区间</th></tr></thead>
         <tbody>${detRows || '<tr><td colspan="5" class="empty">无数据</td></tr>'}</tbody></table></div>`,
      `<button class="btn" id="agClose">关闭</button>`, '720px');
    $('#agClose').addEventListener('click', closeModal);
  });
}

async function renderPayables() {
  const list = await api('/api/payables');
  const renderRows = (data) => data.length ? data.map(r => `<tr>
      <td>${escapeHtml(r.order_no)}</td>
      <td>${escapeHtml(r.supplier_name || '-')}</td>
      <td class="num">${fmtMoney(r.amount)}</td>
      <td class="num text-success">${fmtMoney(r.paid)}</td>
      <td class="num text-danger">${fmtMoney((r.amount || 0) - (r.paid || 0))}</td>
      <td>${statusBadge(r.status)}</td>
      <td>${escapeHtml(r.due_date || '-')}</td>
    </tr>`).join('') : '<tr><td colspan="7" class="empty">暂无应付</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="paySearch" placeholder="搜索订单号/供应商">
          <button class="btn btn-primary" id="paySearchBtn">查询</button>
          <button class="btn" onclick="downloadWithDialog('/api/export/payables', 'payables_' + Date.now() + '.csv')">导出CSV</button>
        </div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>订单号</th><th>供应商</th><th class="num">应付</th>
          <th class="num">已付</th><th class="num">余额</th><th>状态</th><th>到期日</th></tr></thead>
        <tbody id="payTbody">${renderRows(list)}</tbody></table></div>
    </div>`;

  $('#paySearchBtn').addEventListener('click', async () => {
    const kw = $('#paySearch').value.trim();
    const data = await api('/api/payables?keyword=' + encodeURIComponent(kw));
    $('#payTbody').innerHTML = renderRows(data);
  });
}

/* ==================== 回款 / 付款 ==================== */
async function renderReceipts() {
  const list = await api('/api/receipts');
  const rows = list.length ? list.map(r => `<tr>
      <td>${escapeHtml(r.receipt_no)}</td>
      <td>${escapeHtml(r.customer_name || '-')}</td>
      <td>${escapeHtml(r.account_name || '-')}</td>
      <td class="num">${fmtMoney(r.amount)}</td>
      <td>${escapeHtml(r.method || '-')}</td>
      <td>${escapeHtml(r.receipt_date || '-')}</td>
    </tr>`).join('') : '<tr><td colspan="6" class="empty">暂无回款</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left"><strong>回款单</strong></div>
        <div class="toolbar-right"><button class="btn btn-primary" id="rcAdd">+ 登记回款</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>单号</th><th>客户</th><th>收款账户</th><th class="num">金额</th>
          <th>方式</th><th>日期</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;

  $('#rcAdd').addEventListener('click', () => openReceiptModal());
}

async function openReceiptModal() {
  const [customers, accounts] = await Promise.all([
    api('/api/customers'), api('/api/fund_accounts')
  ]);
  if (!customers.length || !accounts.length) {
    toast('请先添加客户和资金账户', 'error'); return;
  }
  const allRec = await api('/api/receivables');
  const pending = allRec.filter(r => (r.amount || 0) - (r.received || 0) > 0);

  openModal('回款登记',
    `<div class="form-row">
       <div class="form-group"><label>客户 *</label>
         <select class="input" id="rcCust"><option value="">-- 选择 --</option>
           ${customers.map(c => `<option value="${c.id}">${escapeHtml(c.code)} ${escapeHtml(c.name)}</option>`).join('')}
         </select></div>
       <div class="form-group"><label>账户 *</label>
         <select class="input" id="rcAcc">${accounts.map(a =>
           `<option value="${a.id}">${escapeHtml(a.name)}（余额 ${fmtMoney(a.balance)}）</option>`).join('')}</select></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>方式</label>
         <select class="input" id="rcMethod">
           <option value="银行转账">银行转账</option><option value="现金">现金</option>
           <option value="支票">支票</option><option value="支付宝">支付宝</option><option value="微信">微信</option>
         </select></div>
       <div class="form-group"><label>日期</label>
         <input type="date" class="input" id="rcDate" value="${todayStr()}"></div>
     </div>
     <div class="form-group"><label>核销明细（勾选自动带出余额，可修改）</label>
       <div style="max-height:260px;overflow:auto">
         <table class="detail-table">
           <thead><tr><th style="width:40px">选</th><th>订单号</th><th class="num">应收</th>
             <th class="num">余额</th><th style="width:120px">本次核销(元)</th></tr></thead>
           <tbody id="rcTbody"></tbody></table></div></div>
     <div class="form-row">
       <div class="form-group"><label>收款金额合计</label>
         <div class="total-amount" id="rcTotal">¥0.00</div></div>
       <div class="form-group"><label>备注</label>
         <input class="input" id="rcRemark"></div>
     </div>`,
    `<button class="btn" id="rcCancel">取消</button>
     <button class="btn btn-primary" id="rcSave">提交</button>`, '860px');

  const tbody = $('#rcTbody');
  const calc = () => {
    let total = 0;
    tbody.querySelectorAll('tr').forEach(tr => {
      if (tr.querySelector('.rc-check').checked) {
        total += yuanToFen(parseFloat(tr.querySelector('.rc-amt').value) || 0);
      }
    });
    $('#rcTotal').textContent = fmtMoney(total);
  };
  const renderRecs = (custId) => {
    const filtered = custId ? pending.filter(r => r.customer_id === custId) : [];
    tbody.innerHTML = filtered.length
      ? filtered.map(r => {
          const bal = (r.amount || 0) - (r.received || 0);
          return `<tr>
            <td><input type="checkbox" class="rc-check" data-id="${r.id}"></td>
            <td>${escapeHtml(r.order_no)}</td>
            <td class="num">${fmtMoney(r.amount)}</td>
            <td class="num text-danger">${fmtMoney(bal)}</td>
            <td><input type="number" step="0.01" class="input rc-amt" data-max="${fenToYuan(bal)}" value="0"></td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="5" class="empty">该客户暂无未收完的应收</td></tr>';
    bindRows();
  };
  const bindRows = () => {
    tbody.querySelectorAll('.rc-check').forEach(cb => cb.addEventListener('change', () => {
      const tr = cb.closest('tr');
      if (cb.checked) tr.querySelector('.rc-amt').value = tr.querySelector('.rc-amt').dataset.max;
      else tr.querySelector('.rc-amt').value = 0;
      calc();
    }));
    tbody.querySelectorAll('.rc-amt').forEach(inp => inp.addEventListener('input', calc));
  };
  $('#rcCust').addEventListener('change', () => renderRecs(parseInt($('#rcCust').value, 10) || 0));
  $('#rcCancel').addEventListener('click', closeModal);
  $('#rcSave').addEventListener('click', async () => {
    const customer_id = parseInt($('#rcCust').value, 10);
    const account_id = parseInt($('#rcAcc').value, 10);
    if (!customer_id) { toast('请选择客户', 'error'); return; }
    const items = [];
    let total = 0;
    tbody.querySelectorAll('tr').forEach(tr => {
      const cb = tr.querySelector('.rc-check');
      if (cb && cb.checked) {
        const amt = parseFloat(tr.querySelector('.rc-amt').value) || 0;
        if (amt > 0) {
          items.push({ receivable_id: parseInt(cb.dataset.id, 10), amount: amt });
          total += amt;
        }
      }
    });
    if (!items.length) { toast('请选择核销明细', 'error'); return; }
    try {
      const res = await api('/api/receipts', 'POST', {
        customer_id, account_id, amount: total,
        method: $('#rcMethod').value,
        receipt_date: $('#rcDate').value,
        remark: $('#rcRemark').value.trim(),
        items
      });
      closeModal(); toast('回款成功：' + res.receipt_no);
      renderReceipts();
    } catch (e) {}
  });
}

async function renderPayments() {
  const list = await api('/api/payments');
  const rows = list.length ? list.map(r => `<tr>
      <td>${escapeHtml(r.payment_no)}</td>
      <td>${escapeHtml(r.supplier_name || '-')}</td>
      <td>${escapeHtml(r.account_name || '-')}</td>
      <td class="num">${fmtMoney(r.amount)}</td>
      <td>${escapeHtml(r.method || '-')}</td>
      <td>${escapeHtml(r.payment_date || '-')}</td>
    </tr>`).join('') : '<tr><td colspan="6" class="empty">暂无付款</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left"><strong>付款单</strong></div>
        <div class="toolbar-right"><button class="btn btn-primary" id="pyAdd">+ 登记付款</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>单号</th><th>供应商</th><th>付款账户</th><th class="num">金额</th>
          <th>方式</th><th>日期</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;

  $('#pyAdd').addEventListener('click', () => openPaymentModal());
}

async function openPaymentModal() {
  const [suppliers, accounts] = await Promise.all([
    api('/api/suppliers'), api('/api/fund_accounts')
  ]);
  if (!suppliers.length || !accounts.length) {
    toast('请先添加供应商和资金账户', 'error'); return;
  }
  const allPay = await api('/api/payables');
  const pending = allPay.filter(p => (p.amount || 0) - (p.paid || 0) > 0);

  openModal('付款登记',
    `<div class="form-row">
       <div class="form-group"><label>供应商 *</label>
         <select class="input" id="pySup"><option value="">-- 选择 --</option>
           ${suppliers.map(s => `<option value="${s.id}">${escapeHtml(s.code)} ${escapeHtml(s.name)}</option>`).join('')}
         </select></div>
       <div class="form-group"><label>账户 *</label>
         <select class="input" id="pyAcc">${accounts.map(a =>
           `<option value="${a.id}">${escapeHtml(a.name)}（余额 ${fmtMoney(a.balance)}）</option>`).join('')}</select></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>方式</label>
         <select class="input" id="pyMethod">
           <option value="银行转账">银行转账</option><option value="现金">现金</option><option value="支票">支票</option>
         </select></div>
       <div class="form-group"><label>日期</label>
         <input type="date" class="input" id="pyDate" value="${todayStr()}"></div>
     </div>
     <div class="form-group"><label>核销明细</label>
       <div style="max-height:260px;overflow:auto">
         <table class="detail-table">
           <thead><tr><th style="width:40px">选</th><th>订单号</th><th class="num">应付</th>
             <th class="num">余额</th><th style="width:120px">本次核销(元)</th></tr></thead>
           <tbody id="pyTbody"></tbody></table></div></div>
     <div class="form-row">
       <div class="form-group"><label>付款金额合计</label>
         <div class="total-amount" id="pyTotal">¥0.00</div></div>
       <div class="form-group"><label>备注</label>
         <input class="input" id="pyRemark"></div>
     </div>`,
    `<button class="btn" id="pyCancel">取消</button>
     <button class="btn btn-primary" id="pySave">提交</button>`, '860px');

  const tbody = $('#pyTbody');
  const calc = () => {
    let total = 0;
    tbody.querySelectorAll('tr').forEach(tr => {
      if (tr.querySelector('.py-check').checked) {
        total += yuanToFen(parseFloat(tr.querySelector('.py-amt').value) || 0);
      }
    });
    $('#pyTotal').textContent = fmtMoney(total);
  };
  const renderPays = (supId) => {
    const filtered = supId ? pending.filter(p => p.supplier_id === supId) : [];
    tbody.innerHTML = filtered.length
      ? filtered.map(p => {
          const bal = (p.amount || 0) - (p.paid || 0);
          return `<tr>
            <td><input type="checkbox" class="py-check" data-id="${p.id}"></td>
            <td>${escapeHtml(p.order_no)}</td>
            <td class="num">${fmtMoney(p.amount)}</td>
            <td class="num text-danger">${fmtMoney(bal)}</td>
            <td><input type="number" step="0.01" class="input py-amt" data-max="${fenToYuan(bal)}" value="0"></td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="5" class="empty">该供应商暂无未付完的应付</td></tr>';
    bindRows();
  };
  const bindRows = () => {
    tbody.querySelectorAll('.py-check').forEach(cb => cb.addEventListener('change', () => {
      const tr = cb.closest('tr');
      if (cb.checked) tr.querySelector('.py-amt').value = tr.querySelector('.py-amt').dataset.max;
      else tr.querySelector('.py-amt').value = 0;
      calc();
    }));
    tbody.querySelectorAll('.py-amt').forEach(inp => inp.addEventListener('input', calc));
  };
  $('#pySup').addEventListener('change', () => renderPays(parseInt($('#pySup').value, 10) || 0));
  $('#pyCancel').addEventListener('click', closeModal);
  $('#pySave').addEventListener('click', async () => {
    const supplier_id = parseInt($('#pySup').value, 10);
    const account_id = parseInt($('#pyAcc').value, 10);
    if (!supplier_id) { toast('请选择供应商', 'error'); return; }
    const items = [];
    let total = 0;
    tbody.querySelectorAll('tr').forEach(tr => {
      const cb = tr.querySelector('.py-check');
      if (cb && cb.checked) {
        const amt = parseFloat(tr.querySelector('.py-amt').value) || 0;
        if (amt > 0) {
          items.push({ payable_id: parseInt(cb.dataset.id, 10), amount: amt });
          total += amt;
        }
      }
    });
    if (!items.length) { toast('请选择核销明细', 'error'); return; }
    try {
      const res = await api('/api/payments', 'POST', {
        supplier_id, account_id, amount: total,
        method: $('#pyMethod').value,
        payment_date: $('#pyDate').value,
        remark: $('#pyRemark').value.trim(),
        items
      });
      closeModal(); toast('付款成功：' + res.payment_no);
      renderPayments();
    } catch (e) {}
  });
}

/* ==================== 资金账户 ==================== */
async function renderFund() {
  const [accounts, logs] = await Promise.all([
    api('/api/fund_accounts'), api('/api/fund_logs')
  ]);
  const accRows = accounts.map(a => `<tr>
      <td>${escapeHtml(a.code)}</td><td>${escapeHtml(a.name)}</td>
      <td>${escapeHtml(a.atype || '-')}</td>
      <td class="num ${a.balance >= 0 ? 'text-success' : 'text-danger'}">${fmtMoney(a.balance)}</td>
      <td>${currentUser.role === 'admin' ? `
        <button class="btn-link" data-act="edit" data-id="${a.id}">编辑</button>
        <button class="btn-link danger" data-act="del" data-id="${a.id}">删除</button>` : '-'}</td>
    </tr>`).join('');
  const logRows = logs.length ? logs.map(l => `<tr>
      <td>${escapeHtml(shortTime(l.created_at))}</td>
      <td>${escapeHtml(l.account_name || '-')}</td>
      <td><span class="badge ${l.amount >= 0 ? 'badge-success' : 'badge-danger'}">${escapeHtml(l.change_type)}</span></td>
      <td class="num ${l.amount >= 0 ? 'text-success' : 'text-danger'}">${l.amount >= 0 ? '+' : ''}${fmtMoney(l.amount)}</td>
      <td class="num">${fmtMoney(l.before_balance)}</td>
      <td class="num">${fmtMoney(l.after_balance)}</td>
      <td>${escapeHtml(l.ref_no || '-')}</td>
    </tr>`).join('') : '<tr><td colspan="7" class="empty">暂无流水</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left"><strong>资金账户</strong></div>
        <div class="toolbar-right">
          ${currentUser.role === 'admin' ? '<button class="btn btn-primary" id="faAdd">+ 新增账户</button>' : ''}
        </div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th>类型</th>
          <th class="num">余额</th><th>操作</th></tr></thead>
        <tbody>${accRows}</tbody></table></div>
    </div>
    <div class="card">
      <div class="card-title">资金日记账</div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>时间</th><th>账户</th><th>类型</th><th class="num">金额</th>
          <th class="num">变动前</th><th class="num">变动后</th><th>关联单号</th></tr></thead>
        <tbody>${logRows}</tbody></table></div>
    </div>`;

  const cache = {}; accounts.forEach(a => cache[a.id] = a);
  if (currentUser.role === 'admin') {
    $('#faAdd').addEventListener('click', () => openFundModal(null));
    $$('#content [data-act]').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      if (btn.dataset.act === 'edit') openFundModal(cache[id]);
      else confirmDialog(`删除账户「${cache[id].name}」？`, async () => {
        await api('/api/fund_accounts/' + id, 'DELETE');
        toast('已删除'); renderFund();
      });
    }));
  }
}

function openFundModal(a) {
  const isEdit = !!a;
  openModal(isEdit ? '编辑资金账户' : '新增资金账户',
    `<div class="form-row">
       <div class="form-group"><label>编码 *</label>
         <input class="input" id="faCode" value="${isEdit ? escapeHtml(a.code) : ''}"></div>
       <div class="form-group"><label>名称 *</label>
         <input class="input" id="faName" value="${isEdit ? escapeHtml(a.name) : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>类型</label>
         <select class="input" id="faType">
           <option value="银行" ${!isEdit || a.atype === '银行' ? 'selected' : ''}>银行</option>
           <option value="现金" ${isEdit && a.atype === '现金' ? 'selected' : ''}>现金</option>
           <option value="其他" ${isEdit && a.atype === '其他' ? 'selected' : ''}>其他</option>
         </select></div>
       ${isEdit ? '' : '<div class="form-group"><label>初始余额（元）</label><input type="number" step="0.01" class="input" id="faBalance" value="0"></div>'}
     </div>
     <div class="form-group"><label>备注</label>
       <input class="input" id="faRemark" value="${isEdit ? escapeHtml(a.remark || '') : ''}"></div>`,
    `<button class="btn" id="faCancel">取消</button>
     <button class="btn btn-primary" id="faSave">保存</button>`);
  $('#faCancel').addEventListener('click', closeModal);
  $('#faSave').addEventListener('click', async () => {
    const code = $('#faCode').value.trim(), name = $('#faName').value.trim();
    if (!code || !name) { toast('编码和名称不能为空', 'error'); return; }
    const payload = { code, name, atype: $('#faType').value, remark: $('#faRemark').value.trim() };
    if (!isEdit) payload.balance = parseFloat($('#faBalance').value) || 0;
    try {
      if (isEdit) await api('/api/fund_accounts/' + a.id, 'PUT', payload);
      else await api('/api/fund_accounts', 'POST', payload);
      closeModal(); toast('已保存'); renderFund();
    } catch (e) {}
  });
}

/* ==================== 利润分析 ==================== */
async function renderProfit() {
  $('#content').innerHTML = `
    <div class="card" id="smartAnalysisCard">
      <div class="section-title">智能分析（AI 经营洞察）</div>
      <div class="need-action-head" style="padding:0 0 10px">
        <div class="need-action-tab active" data-smart="customer">客户价值分层</div>
        <div class="need-action-tab" data-smart="product">商品 ABC 分类</div>
        <div class="need-action-tab" data-smart="inventory">库存周转</div>
      </div>
      <div id="smartContent"><div class="loading">加载中...</div></div>
    </div>
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <select class="input" id="pfDim">
            <option value="product">按商品</option>
            <option value="customer">按客户</option>
            <option value="category">按分类</option>
          </select>
          <input type="date" class="input" id="pfStart">
          <input type="date" class="input" id="pfEnd">
          <button class="btn btn-primary" id="pfSearch">查询</button>
        </div>
      </div>
      <div id="pfSummary" class="kpi-grid"></div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th class="num">销量</th>
          <th class="num">销售额</th><th class="num">成本</th>
          <th class="num">毛利</th><th class="num">毛利率</th></tr></thead>
        <tbody id="pfTbody"></tbody></table></div>
    </div>`;

  const search = async () => {
    const d = await api('/api/profit_report?dim=' + $('#pfDim').value +
      '&start=' + $('#pfStart').value + '&end=' + $('#pfEnd').value);
    $('#pfSummary').innerHTML = `
      <div class="kpi-card blue"><div class="kpi-icon">${ICONS.trend}</div>
        <div class="kpi-content"><div class="kpi-value">${fmtMoney(d.summary.sales_amount)}</div>
          <div class="kpi-label">销售额</div></div></div>
      <div class="kpi-card orange"><div class="kpi-icon">${ICONS.wallet}</div>
        <div class="kpi-content"><div class="kpi-value">${fmtMoney(d.summary.cost_amount)}</div>
          <div class="kpi-label">成本</div></div></div>
      <div class="kpi-card green"><div class="kpi-icon">${ICONS.trend}</div>
        <div class="kpi-content"><div class="kpi-value">${fmtMoney(d.summary.gross_profit)}</div>
          <div class="kpi-label">毛利</div></div></div>
      <div class="kpi-card cyan"><div class="kpi-icon">${svg('<line x1="5" y1="12" x2="19" y2="12"/><line x1="5" y1="12" x2="11" y2="5"/><line x1="19" y1="12" x2="13" y2="19"/>')}</div>
        <div class="kpi-content"><div class="kpi-value">${d.summary.gross_rate}%</div>
          <div class="kpi-label">毛利率</div></div></div>`;
    $('#pfTbody').innerHTML = d.details.length ? d.details.map(r => `<tr>
        <td>${escapeHtml(r.code || '-')}</td><td>${escapeHtml(r.name || '-')}</td>
        <td class="num">${fmtNum(r.qty)}</td>
        <td class="num">${fmtMoney(r.sales_amount)}</td>
        <td class="num">${fmtMoney(r.cost_amount)}</td>
        <td class="num ${r.gross_profit >= 0 ? 'text-success' : 'text-danger'}">${fmtMoney(r.gross_profit)}</td>
        <td class="num">${r.gross_rate}%</td>
      </tr>`).join('') : '<tr><td colspan="7" class="empty">暂无数据</td></tr>';
  };
  $('#pfSearch').addEventListener('click', search);
  search();

  // ---- 智能分析 ----
  let smartData = null;
  const renderSmart = (tab) => {
    const box = $('#smartContent');
    if (!smartData) { box.innerHTML = '<div class="loading">加载中...</div>'; return; }
    if (tab === 'customer') {
      const cl = smartData.customer_layers;
      box.innerHTML = `
        <div class="dash-kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px">
          <div class="kpi-card compact red"><div class="kpi-icon">${ICONS.users}</div>
            <div class="kpi-content"><div class="kpi-value">${cl.A.count}</div><div class="kpi-label">A类客户（高价值）</div>
            <div class="kpi-sub">贡献 ${fmtMoney(cl.A.sales)}</div></div></div>
          <div class="kpi-card compact orange"><div class="kpi-icon">${ICONS.users}</div>
            <div class="kpi-content"><div class="kpi-value">${cl.B.count}</div><div class="kpi-label">B类客户（成长）</div>
            <div class="kpi-sub">贡献 ${fmtMoney(cl.B.sales)}</div></div></div>
          <div class="kpi-card compact blue"><div class="kpi-icon">${ICONS.users}</div>
            <div class="kpi-content"><div class="kpi-value">${cl.C.count}</div><div class="kpi-label">C类客户（长尾）</div>
            <div class="kpi-sub">贡献 ${fmtMoney(cl.C.sales)}</div></div></div>
        </div>
        <div class="text-muted" style="font-size:12px;margin-bottom:6px">A类 Top 5（重点维护）</div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>客户</th><th class="num">累计销售额</th><th class="num">累计毛利</th><th class="num">订单数</th></tr></thead>
          <tbody>${cl.A.top.length ? cl.A.top.map(c => `<tr>
            <td>${escapeHtml(c.name)}</td><td class="num">${fmtMoney(c.total_sales)}</td>
            <td class="num ${c.total_profit >= 0 ? 'text-success' : 'text-danger'}">${fmtMoney(c.total_profit)}</td>
            <td class="num">${c.order_count}</td></tr>`).join('') : '<tr><td colspan="4" class="empty">暂无数据</td></tr>'}
          </tbody></table></div>`;
    } else if (tab === 'product') {
      const pa = smartData.product_abc;
      box.innerHTML = `
        <div class="dash-kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:12px">
          <div class="kpi-card compact red"><div class="kpi-icon">${ICONS.box}</div>
            <div class="kpi-content"><div class="kpi-value">${pa.A.count}</div><div class="kpi-label">A类商品（70%销售额）</div>
            <div class="kpi-sub">占比 ${pa.A.sales_ratio}%</div></div></div>
          <div class="kpi-card compact orange"><div class="kpi-icon">${ICONS.box}</div>
            <div class="kpi-content"><div class="kpi-value">${pa.B.count}</div><div class="kpi-label">B类商品（20%）</div>
            <div class="kpi-sub">占比 ${pa.B.sales_ratio}%</div></div></div>
          <div class="kpi-card compact blue"><div class="kpi-icon">${ICONS.box}</div>
            <div class="kpi-content"><div class="kpi-value">${pa.C.count}</div><div class="kpi-label">C类商品（10%）</div>
            <div class="kpi-sub">占比 ${pa.C.sales_ratio}%</div></div></div>
        </div>
        <div class="text-muted" style="font-size:12px;margin-bottom:6px">A类 Top 5（核心盈利品）</div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>商品</th><th class="num">累计销售额</th><th class="num">销量</th><th class="num">销售占比</th><th class="num">当前库存</th></tr></thead>
          <tbody>${pa.A.top.length ? pa.A.top.map(p => `<tr>
            <td>${escapeHtml(p.name)}</td><td class="num">${fmtMoney(p.total_sales)}</td>
            <td class="num">${fmtNum(p.total_qty)}</td><td class="num">${p.sales_ratio}%</td>
            <td class="num ${p.stock <= p.safety_stock ? 'text-danger' : ''}">${fmtNum(p.stock)}</td></tr>`).join('') : '<tr><td colspan="5" class="empty">暂无数据</td></tr>'}
          </tbody></table></div>`;
    } else {
      const it = smartData.inventory_turnover;
      box.innerHTML = `
        <div class="dash-kpi-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:12px">
          <div class="kpi-card compact blue"><div class="kpi-icon">${ICONS.box}</div>
            <div class="kpi-content"><div class="kpi-value">${it.total_products}</div><div class="kpi-label">在库商品</div></div></div>
          <div class="kpi-card compact green"><div class="kpi-icon">${ICONS.check}</div>
            <div class="kpi-content"><div class="kpi-value">${it.healthy}</div><div class="kpi-label">周转健康(≤30天)</div></div></div>
          <div class="kpi-card compact orange"><div class="kpi-icon">${ICONS.clock}</div>
            <div class="kpi-content"><div class="kpi-value">${it.slow}</div><div class="kpi-label">周转偏慢(30-90天)</div></div></div>
          <div class="kpi-card compact red"><div class="kpi-icon">${ICONS.alert}</div>
            <div class="kpi-content"><div class="kpi-value">${it.stagnant}</div><div class="kpi-label">呆滞(>90天)</div></div></div>
        </div>
        <div class="text-muted" style="font-size:12px;margin-bottom:6px">周转最慢 Top 10（建议促销清仓）</div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>商品</th><th class="num">当前库存</th><th class="num">90天销售成本</th><th class="num">周转天数</th><th>状态</th></tr></thead>
          <tbody>${it.top_slow.length ? it.top_slow.map(t => `<tr>
            <td>${escapeHtml(t.name)}</td><td class="num">${fmtNum(t.stock)}</td>
            <td class="num">${fmtMoney(t.cogs)}</td>
            <td class="num ${t.turnover_days > 90 ? 'text-danger' : (t.turnover_days > 30 ? 'text-warn' : 'text-success')}">${t.turnover_days >= 999 ? '∞' : t.turnover_days}</td>
            <td><span class="badge ${t.status === '健康' ? 'badge-success' : (t.status === '偏慢' ? 'badge-warn' : 'badge-danger')}">${t.status}</span></td></tr>`).join('') : '<tr><td colspan="5" class="empty">暂无数据</td></tr>'}
          </tbody></table></div>`;
    }
  };
  $$('[data-smart]').forEach(tab => tab.addEventListener('click', () => {
    $$('[data-smart]').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    renderSmart(tab.dataset.smart);
  }));
  try {
    smartData = await api('/api/analytics/smart');
    renderSmart('customer');
  } catch (e) {
    $('#smartContent').innerHTML = '<div class="empty">智能分析加载失败</div>';
  }
}

/* ==================== 库存流水 ==================== */
async function renderStock() {
  const [logs, products, whs] = await Promise.all([
    api('/api/stock_logs'), api('/api/products'), api('/api/warehouses')
  ]);
  const renderRows = (data) => data.length ? data.map(l => `<tr>
      <td>${escapeHtml(l.product_code || '-')}</td>
      <td>${escapeHtml(l.product_name || '-')}</td>
      <td>${escapeHtml(l.warehouse_name || '-')}</td>
      <td><span class="badge ${l.qty >= 0 ? 'badge-success' : 'badge-danger'}">${escapeHtml(l.change_type)}</span></td>
      <td class="num ${l.qty >= 0 ? 'text-success' : 'text-danger'}">${l.qty >= 0 ? '+' : ''}${fmtNum(l.qty)}</td>
      <td class="num">${fmtNum(l.before_stock)}</td>
      <td class="num">${fmtNum(l.after_stock)}</td>
      <td>${escapeHtml(l.ref_no || '-')}</td>
      <td>${escapeHtml(shortTime(l.created_at))}</td>
    </tr>`).join('') : '<tr><td colspan="9" class="empty">暂无流水</td></tr>';

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="stSearch" placeholder="搜索商品/单号">
          <select class="input" id="stType">
            <option value="">全部类型</option>
            <option value="期初库存">期初库存</option>
            <option value="销售出库">销售出库</option>
            <option value="销售退回">销售退回</option>
            <option value="采购入库">采购入库</option>
            <option value="采购退回">采购退回</option>
            <option value="库存调整">库存调整</option>
          </select>
          <button class="btn btn-primary" id="stSearchBtn">查询</button>
        </div>
        <div class="toolbar-right"><button class="btn btn-primary" id="stAdjust">+ 库存调整</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>编码</th><th>名称</th><th>仓库</th><th>类型</th>
          <th class="num">变动</th><th class="num">变动前</th><th class="num">变动后</th>
          <th>单号</th><th>时间</th></tr></thead>
        <tbody id="stTbody">${renderRows(logs)}</tbody></table></div>
    </div>`;

  $('#stSearchBtn').addEventListener('click', async () => {
    const kw = $('#stSearch').value.trim(), tp = $('#stType').value;
    const data = await api('/api/stock_logs?keyword=' + encodeURIComponent(kw) +
      '&change_type=' + encodeURIComponent(tp));
    $('#stTbody').innerHTML = renderRows(data);
  });
  $('#stAdjust').addEventListener('click', () => {
    if (!products.length) { toast('请先添加商品', 'error'); return; }
    openModal('库存调整',
      `<div class="form-row">
         <div class="form-group"><label>商品 *</label>
           <select class="input" id="adjProd"><option value="">-- 选择 --</option>
             ${products.map(p => `<option value="${p.id}">${escapeHtml(p.code)} ${escapeHtml(p.name)}（${p.stock}）</option>`).join('')}
           </select></div>
         <div class="form-group"><label>仓库 *</label>
           <select class="input" id="adjWh">${whs.map(w => `<option value="${w.id}">${escapeHtml(w.name)}</option>`).join('')}</select></div>
       </div>
       <div class="form-group"><label>数量（正数增加，负数减少）*</label>
         <input type="number" class="input" id="adjQty" value="0"></div>
       <div class="form-group"><label>原因</label>
         <input class="input" id="adjRemark"></div>`,
      `<button class="btn" id="adjCancel">取消</button>
       <button class="btn btn-primary" id="adjSave">确定</button>`, '540px');
    $('#adjCancel').addEventListener('click', closeModal);
    $('#adjSave').addEventListener('click', async () => {
      const pid = parseInt($('#adjProd').value, 10), wid = parseInt($('#adjWh').value, 10);
      const qty = parseInt($('#adjQty').value) || 0;
      if (!pid) { toast('请选择商品', 'error'); return; }
      if (qty === 0) { toast('数量不能为 0', 'error'); return; }
      try {
        await api('/api/stock/adjust', 'POST', {
          product_id: pid, warehouse_id: wid, qty,
          remark: $('#adjRemark').value.trim()
        });
        closeModal(); toast('调整成功'); renderStock();
      } catch (e) {}
    });
  });
}

/* ==================== 员工 ==================== */
async function renderEmployees() {
  const list = await api('/api/employees');
  const rows = list.map(e => `<tr>
      <td>${escapeHtml(e.code)}</td><td>${escapeHtml(e.name)}</td>
      <td>${escapeHtml(e.gender || '-')}</td><td>${escapeHtml(e.dept || '-')}</td>
      <td>${escapeHtml(e.position || '-')}</td><td>${escapeHtml(e.phone || '-')}</td>
      <td class="num">${fmtMoney(e.salary)}</td>
      <td><button class="btn-link" data-act="edit" data-id="${e.id}">编辑</button>
        <button class="btn-link danger" data-act="del" data-id="${e.id}">删除</button></td>
    </tr>`).join('');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left"><strong>员工档案</strong></div>
        <div class="toolbar-right"><button class="btn btn-primary" id="eAdd">+ 新增员工</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>工号</th><th>姓名</th><th>性别</th><th>部门</th><th>职位</th>
          <th>手机</th><th class="num">月薪</th><th style="width:140px">操作</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;

  const cache = {}; list.forEach(e => cache[e.id] = e);
  $('#eAdd').addEventListener('click', () => openEmpModal(null));
  $$('#content [data-act]').forEach(btn => btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id);
    if (btn.dataset.act === 'edit') openEmpModal(cache[id]);
    else confirmDialog(`删除员工「${cache[id].name}」？`, async () => {
      await api('/api/employees/' + id, 'DELETE');
      toast('已删除'); renderEmployees();
    });
  }));
}

function openEmpModal(e) {
  const isEdit = !!e;
  openModal(isEdit ? '编辑员工' : '新增员工',
    `<div class="form-row">
       <div class="form-group"><label>工号 *</label>
         <input class="input" id="eCode" value="${isEdit ? escapeHtml(e.code) : ''}"></div>
       <div class="form-group"><label>姓名 *</label>
         <input class="input" id="eName" value="${isEdit ? escapeHtml(e.name) : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>性别</label>
         <select class="input" id="eGender">
           <option value="男" ${!isEdit || e.gender === '男' ? 'selected' : ''}>男</option>
           <option value="女" ${isEdit && e.gender === '女' ? 'selected' : ''}>女</option>
         </select></div>
       <div class="form-group"><label>部门</label>
         <input class="input" id="eDept" value="${isEdit ? escapeHtml(e.dept || '') : ''}"></div>
       <div class="form-group"><label>职位</label>
         <input class="input" id="ePosition" value="${isEdit ? escapeHtml(e.position || '') : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>手机</label>
         <input class="input" id="ePhone" value="${isEdit ? escapeHtml(e.phone || '') : ''}"></div>
       <div class="form-group"><label>月薪（元）</label>
         <input type="number" step="0.01" class="input" id="eSalary"
                value="${isEdit ? fenToYuan(e.salary) : 0}"></div>
     </div>`,
    `<button class="btn" id="eCancel">取消</button>
     <button class="btn btn-primary" id="eSave">保存</button>`);
  $('#eCancel').addEventListener('click', closeModal);
  $('#eSave').addEventListener('click', async () => {
    const code = $('#eCode').value.trim(), name = $('#eName').value.trim();
    if (!code || !name) { toast('工号和姓名不能为空', 'error'); return; }
    const payload = {
      code, name, gender: $('#eGender').value,
      dept: $('#eDept').value.trim(),
      position: $('#ePosition').value.trim(),
      phone: $('#ePhone').value.trim(),
      salary: parseFloat($('#eSalary').value) || 0
    };
    try {
      if (isEdit) await api('/api/employees/' + e.id, 'PUT', payload);
      else await api('/api/employees', 'POST', payload);
      closeModal(); toast('已保存'); renderEmployees();
    } catch (e) {}
  });
}

/* ==================== 用户 ==================== */
async function renderUsers() {
  if (!currentUser || currentUser.role !== 'admin') {
    $('#content').innerHTML = '<div class="empty">无权限</div>'; return;
  }
  const list = await api('/api/users');
  const rows = list.map(u => `<tr>
      <td>${u.id}</td><td>${escapeHtml(u.username)}</td>
      <td>${escapeHtml(u.real_name || '-')}</td>
      <td>${u.role === 'admin' ? '<span class="badge badge-info">管理员</span>' : '<span class="badge badge-muted">普通员工</span>'}</td>
      <td>${u.status === 1 ? '<span class="badge badge-success">启用</span>' : '<span class="badge badge-danger">禁用</span>'}</td>
      <td>${escapeHtml(shortTime(u.created_at))}</td>
      <td><button class="btn-link" data-act="edit" data-id="${u.id}">编辑</button>
        <button class="btn-link" data-act="pwd" data-id="${u.id}">重置密码</button>
        <button class="btn-link danger" data-act="del" data-id="${u.id}">删除</button></td>
    </tr>`).join('');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left"><strong>系统用户</strong></div>
        <div class="toolbar-right"><button class="btn btn-primary" id="uAdd">+ 新增用户</button></div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th style="width:60px">ID</th><th>用户名</th><th>姓名</th><th>角色</th>
          <th>状态</th><th>创建时间</th><th style="width:200px">操作</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;

  const cache = {}; list.forEach(u => cache[u.id] = u);
  $('#uAdd').addEventListener('click', () => openUserModal(null));
  $$('#content [data-act]').forEach(btn => btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id), act = btn.dataset.act;
    if (act === 'edit') openUserModal(cache[id]);
    else if (act === 'pwd') openPwdModal(cache[id]);
    else confirmDialog(`删除用户「${cache[id].username}」？`, async () => {
      await api('/api/users/' + id, 'DELETE');
      toast('已删除'); renderUsers();
    });
  }));
}

function openUserModal(u) {
  const isEdit = !!u;
  openModal(isEdit ? '编辑用户' : '新增用户',
    `${isEdit ? '' : `<div class="form-row">
       <div class="form-group"><label>用户名 *</label>
         <input class="input" id="uUsername"></div>
       <div class="form-group"><label>初始密码 *</label>
         <input type="password" class="input" id="uPassword" placeholder="至少6位"></div>
     </div>`}
     <div class="form-row">
       <div class="form-group"><label>姓名</label>
         <input class="input" id="uRealName" value="${isEdit ? escapeHtml(u.real_name || '') : ''}"></div>
       <div class="form-group"><label>角色</label>
         <select class="input" id="uRole">
           <option value="staff" ${isEdit && u.role === 'staff' ? 'selected' : ''}>普通员工</option>
           <option value="admin" ${isEdit && u.role === 'admin' ? 'selected' : ''}>管理员</option>
         </select></div>
     </div>
     <div class="form-group"><label>状态</label>
       <select class="input" id="uStatus">
         <option value="1" ${!isEdit || u.status === 1 ? 'selected' : ''}>启用</option>
         <option value="0" ${isEdit && u.status === 0 ? 'selected' : ''}>禁用</option>
       </select></div>`,
    `<button class="btn" id="uCancel">取消</button>
     <button class="btn btn-primary" id="uSave">保存</button>`, '520px');
  $('#uCancel').addEventListener('click', closeModal);
  $('#uSave').addEventListener('click', async () => {
    try {
      if (isEdit) {
        await api('/api/users/' + u.id, 'PUT', {
          real_name: $('#uRealName').value.trim(),
          role: $('#uRole').value,
          status: parseInt($('#uStatus').value, 10)
        });
      } else {
        const username = $('#uUsername').value.trim();
        const password = $('#uPassword').value;
        if (!username || !password) { toast('用户名和密码不能为空', 'error'); return; }
        if (password.length < 6) { toast('密码至少6位', 'error'); return; }
        await api('/api/users', 'POST', {
          username, password,
          real_name: $('#uRealName').value.trim(),
          role: $('#uRole').value,
          status: parseInt($('#uStatus').value, 10)
        });
      }
      closeModal(); toast('已保存'); renderUsers();
    } catch (e) {}
  });
}

function openPwdModal(u) {
  openModal('重置密码 - ' + u.username,
    `<div class="form-group"><label>新密码 *</label>
       <input type="password" class="input" id="rpPwd1" placeholder="至少6位"></div>
     <div class="form-group"><label>确认密码 *</label>
       <input type="password" class="input" id="rpPwd2"></div>`,
    `<button class="btn" id="rpCancel">取消</button>
     <button class="btn btn-primary" id="rpSave">确定</button>`, '440px');
  $('#rpCancel').addEventListener('click', closeModal);
  $('#rpSave').addEventListener('click', async () => {
    const p1 = $('#rpPwd1').value, p2 = $('#rpPwd2').value;
    if (p1.length < 6) { toast('密码至少6位', 'error'); return; }
    if (p1 !== p2) { toast('两次密码不一致', 'error'); return; }
    await api('/api/users/' + u.id + '/password', 'POST', { password: p1 });
    closeModal(); toast('密码已重置');
  });
}

/* ==================== 发票管理 ==================== */
async function renderInvoices(type) {
  const [list, custs, sups] = await Promise.all([
    api('/api/invoices?invoice_type=' + encodeURIComponent(type)),
    api('/api/customers'), api('/api/suppliers')
  ]);
  const isInput = type === '进项';
  const partnerList = isInput ? sups : custs;
  const partnerType = isInput ? 'supplier' : 'customer';

  const renderRows = (data) => data.length ? data.map(r => `<tr>
      <td>${escapeHtml(r.invoice_no)}</td>
      <td>${escapeHtml(r.invoice_date)}</td>
      <td>${escapeHtml(r.partner_name || '-')}</td>
      <td class="num">${fmtMoney(r.amount)}</td>
      <td class="num">${r.tax_rate}%</td>
      <td class="num">${fmtMoney(r.tax_amount)}</td>
      <td class="num"><strong>${fmtMoney(r.total_amount)}</strong></td>
      <td><span class="badge ${r.status === '已作废' ? 'badge-muted' : 'badge-success'}">${escapeHtml(r.status)}</span></td>
      <td>${escapeHtml(r.related_order || '-')}</td>
      <td><button class="btn-link" data-act="edit" data-id="${r.id}">编辑</button>
        ${currentUser.role === 'admin' ? `<button class="btn-link danger" data-act="del" data-id="${r.id}">删除</button>` : ''}</td>
    </tr>`).join('') : `<tr><td colspan="10" class="empty">暂无${type}发票</td></tr>`;

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input class="input" id="invSearch" placeholder="搜索发票号/对方/关联单号">
          <input type="date" class="input" id="invStart">
          <input type="date" class="input" id="invEnd">
          <button class="btn btn-primary" id="invSearchBtn">查询</button>
          <button class="btn" id="invStats">统计税额</button>
        </div>
        <div class="toolbar-right">
          <button class="btn btn-primary" id="invAdd">+ 登记${type}发票</button>
        </div>
      </div>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>发票号</th><th>日期</th><th>对方</th><th class="num">不含税</th>
          <th class="num">税率</th><th class="num">税额</th><th class="num">价税合计</th>
          <th>状态</th><th>关联单号</th><th style="width:140px">操作</th></tr></thead>
        <tbody id="invTbody">${renderRows(list)}</tbody></table></div>
    </div>`;

  const cache = {}; list.forEach(r => cache[r.id] = r);
  const refresh = async () => {
    const kw = $('#invSearch').value.trim();
    const s = $('#invStart').value, e = $('#invEnd').value;
    const data = await api('/api/invoices?invoice_type=' + encodeURIComponent(type) +
      '&keyword=' + encodeURIComponent(kw) + '&start=' + s + '&end=' + e);
    data.forEach(r => cache[r.id] = r);
    $('#invTbody').innerHTML = renderRows(data); bind();
  };
  const bind = () => {
    $$('#invTbody [data-act]').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.id);
      if (btn.dataset.act === 'edit') openInvoiceModal(cache[id], type, partnerList, partnerType);
      else confirmDialog('确定删除该发票？', async () => {
        await api('/api/invoices/' + id, 'DELETE');
        toast('已删除'); refresh();
      });
    }));
  };
  $('#invSearchBtn').addEventListener('click', refresh);
  $('#invAdd').addEventListener('click', () => openInvoiceModal(null, type, partnerList, partnerType));
  $('#invStats').addEventListener('click', async () => {
    const s = $('#invStart').value, e = $('#invEnd').value;
    const d = await api('/api/invoices/stats?start=' + s + '&end=' + e);
    openModal('发票税额统计',
      `<div class="info-grid">
         <div><span class="info-label">销项金额：</span>${fmtMoney(d.output.amount)}</div>
         <div><span class="info-label">销项税额：</span>${fmtMoney(d.output.tax)}</div>
         <div><span class="info-label">进项金额：</span>${fmtMoney(d.input.amount)}</div>
         <div><span class="info-label">进项税额：</span>${fmtMoney(d.input.tax)}</div>
         <div style="grid-column:1/-1;font-size:16px;padding-top:10px;border-top:1px solid #eee">
           <span class="info-label">应缴增值税（销项-进项）：</span>
           <strong class="${d.diff_tax >= 0 ? 'text-danger' : 'text-success'}">${fmtMoney(d.diff_tax)}</strong>
         </div>
       </div>`,
      `<button class="btn" id="statClose">关闭</button>`, '560px');
    $('#statClose').addEventListener('click', closeModal);
  });
  bind();
}

function openInvoiceModal(inv, type, partners, partnerType) {
  const isEdit = !!inv;
  const pType = inv ? inv.partner_type : partnerType;
  openModal(isEdit ? '编辑发票' : '登记' + type + '发票',
    `<div class="form-row">
       <div class="form-group"><label>发票号 *</label>
         <input class="input" id="invNo" value="${isEdit ? escapeHtml(inv.invoice_no) : ''}"></div>
       <div class="form-group"><label>发票代码</label>
         <input class="input" id="invCode" value="${isEdit ? escapeHtml(inv.invoice_code || '') : ''}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>对方 *</label>
         <select class="input" id="invPartner" ${isEdit ? 'disabled' : ''}>
           <option value="">-- 请选择 --</option>
           ${partners.map(p => `<option value="${p.id}" ${isEdit && inv.partner_id === p.id ? 'selected' : ''}>${escapeHtml(p.code)} ${escapeHtml(p.name)}</option>`).join('')}
         </select></div>
       <div class="form-group"><label>日期</label>
         <input type="date" class="input" id="invDate" value="${isEdit ? inv.invoice_date : todayStr()}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>不含税金额（元）*</label>
         <input type="number" step="0.01" class="input" id="invAmount"
                value="${isEdit ? fenToYuan(inv.amount) : 0}"></div>
       <div class="form-group"><label>税率（%）</label>
         <input type="number" step="0.1" class="input" id="invRate"
                value="${isEdit ? inv.tax_rate : 13}"></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>税额（元）</label>
         <input type="number" step="0.01" class="input" id="invTax"
                value="${isEdit ? fenToYuan(inv.tax_amount) : 0}" readonly></div>
       <div class="form-group"><label>价税合计</label>
         <input type="text" class="input" id="invTotal"
                value="${isEdit ? fmtMoney(inv.total_amount) : '¥0.00'}" readonly></div>
     </div>
     <div class="form-row">
       <div class="form-group"><label>状态</label>
         <select class="input" id="invStatus">
           ${['已开', '已认证', '未认证', '已作废'].map(s =>
             `<option value="${s}" ${isEdit && inv.status === s ? 'selected' : ''}>${s}</option>`).join('')}
         </select></div>
       <div class="form-group"><label>关联单号</label>
         <input class="input" id="invRef"
                value="${isEdit ? escapeHtml(inv.related_order || '') : ''}"
                placeholder="如 SO202609290001"></div>
     </div>
     <div class="form-group"><label>备注</label>
       <input class="input" id="invRemark"
              value="${isEdit ? escapeHtml(inv.remark || '') : ''}"></div>`,
    `<button class="btn" id="invCancel">取消</button>
     <button class="btn btn-primary" id="invSave">保存</button>`);

  const updateCalc = () => {
    const a = yuanToFen(parseFloat($('#invAmount').value) || 0);
    const r = parseFloat($('#invRate').value) || 0;
    const tax = Math.round(a * r / 100);
    $('#invTax').value = fenToYuan(tax).toFixed(2);
    $('#invTotal').value = fmtMoney(a + tax);
  };
  $('#invAmount').addEventListener('input', updateCalc);
  $('#invRate').addEventListener('input', updateCalc);
  updateCalc();

  $('#invCancel').addEventListener('click', closeModal);
  $('#invSave').addEventListener('click', async () => {
    const no = $('#invNo').value.trim();
    const pid = parseInt($('#invPartner').value, 10);
    const amount = parseFloat($('#invAmount').value) || 0;
    if (!no) { toast('请输入发票号', 'error'); return; }
    if (!pid && !isEdit) { toast('请选择对方', 'error'); return; }
    if (amount <= 0) { toast('金额必须大于 0', 'error'); return; }

    const payload = {
      invoice_no: no,
      invoice_code: $('#invCode').value.trim(),
      invoice_type: type,
      partner_type: pType,
      partner_id: pid,
      amount,
      tax_rate: parseFloat($('#invRate').value) || 0,
      invoice_date: $('#invDate').value,
      status: $('#invStatus').value,
      related_order: $('#invRef').value.trim(),
      remark: $('#invRemark').value.trim()
    };
    try {
      if (isEdit) await api('/api/invoices/' + inv.id, 'PUT', payload);
      else await api('/api/invoices', 'POST', payload);
      closeModal(); toast('已保存'); renderInvoices(type);
    } catch (e) {}
  });
}

/* ==================== 会计凭证 ==================== */
async function renderVouchers() {
  const [maps] = await Promise.all([api('/api/account_mapping')]);
  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input type="date" class="input" id="vStart">
          <input type="date" class="input" id="vEnd">
          <select class="input" id="vType">
            <option value="all">全部业务</option>
            <option value="sales">仅销售</option>
            <option value="purchase">仅采购</option>
            <option value="receipt">仅回款</option>
            <option value="payment">仅付款</option>
          </select>
          <button class="btn btn-primary" id="vGen">生成凭证</button>
          <button class="btn btn-success" id="vExport">导出金蝶 CSV</button>
        </div>
        <div class="toolbar-right">
          <button class="btn" id="vMap">科目映射</button>
        </div>
      </div>
      <div id="vSummary" class="kpi-grid"></div>
      <div id="vList"></div>
    </div>`;

  $('#vGen').addEventListener('click', async () => {
    const s = $('#vStart').value, e = $('#vEnd').value, t = $('#vType').value;
    const d = await api('/api/vouchers/generate?start=' + s + '&end=' + e + '&type=' + t);
    renderVoucherData(d);
  });

  $('#vExport').addEventListener('click', () => {
    const s = $('#vStart').value;
    const e = $('#vEnd').value;
    const t = $('#vType').value;
    const ts = new Date().toISOString().slice(0, 10);
    downloadWithDialog(
      '/api/vouchers/export?start=' + encodeURIComponent(s) +
      '&end=' + encodeURIComponent(e) + '&type=' + encodeURIComponent(t),
      'vouchers_' + ts + '.csv'
    );
  });

  $('#vMap').addEventListener('click', () => openMapModal(maps));

  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  $('#vStart').value = `${y}-${m}-01`;
  $('#vEnd').value = todayStr();
  $('#vGen').click();
}

function renderVoucherData(d) {
  $('#vSummary').innerHTML = `
    <div class="kpi-card blue"><div class="kpi-icon">${ICONS.book}</div>
      <div class="kpi-content"><div class="kpi-value">${d.summary.count}</div>
        <div class="kpi-label">凭证张数</div></div></div>
    <div class="kpi-card green"><div class="kpi-icon">${ICONS.banknote}</div>
      <div class="kpi-content"><div class="kpi-value">${fmtMoney(d.summary.total_debit)}</div>
        <div class="kpi-label">借方合计</div></div></div>
    <div class="kpi-card orange"><div class="kpi-icon">${ICONS.wallet}</div>
      <div class="kpi-content"><div class="kpi-value">${fmtMoney(d.summary.total_credit)}</div>
        <div class="kpi-label">贷方合计</div></div></div>
    <div class="kpi-card ${d.summary.total_debit === d.summary.total_credit ? 'green' : 'red'}">
      <div class="kpi-icon">${d.summary.total_debit === d.summary.total_credit ? ICONS.check : ICONS.alert}</div>
      <div class="kpi-content">
        <div class="kpi-value">${d.summary.total_debit === d.summary.total_credit ? '借贷平衡' : '不平衡'}</div>
        <div class="kpi-label">校验</div>
      </div>
    </div>`;
  if (!d.vouchers.length) {
    $('#vList').innerHTML = '<div class="empty">该时间段内无凭证</div>';
    return;
  }
  $('#vList').innerHTML = d.vouchers.map((v, i) => `
    <div class="card" style="padding:14px 18px">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:13px">
        <span><strong>${i + 1}.</strong> ${escapeHtml(v.voucher_date)} · ${escapeHtml(v.summary)}</span>
        <span class="text-muted">${escapeHtml(v.biz_type)} · #${v.biz_id}</span>
      </div>
      <table class="detail-table">
        <thead><tr><th>摘要</th><th>科目编码</th><th>科目名称</th>
          <th class="num">借方</th><th class="num">贷方</th></tr></thead>
        <tbody>${v.entries.map(e => `<tr>
            <td>${escapeHtml(e.summary)}</td>
            <td>${escapeHtml(e.code)}</td>
            <td>${escapeHtml(e.name)}</td>
            <td class="num">${e.debit ? fmtMoney(e.debit) : '-'}</td>
            <td class="num">${e.credit ? fmtMoney(e.credit) : '-'}</td>
          </tr>`).join('')}</tbody>
      </table>
    </div>`).join('');
}

function openMapModal(maps) {
  openModal('会计科目映射',
    `<p class="text-muted" style="margin-bottom:12px;font-size:13px">
       如需调整，请与会计确认后修改。编码参考《企业会计准则》常用科目。
     </p>
     <table class="detail-table">
       <thead><tr><th>业务项</th><th>科目编码</th><th>科目名称</th></tr></thead>
       <tbody>${maps.map(m => `<tr>
           <td>${escapeHtml(m.biz_key)}</td>
           <td><input class="input" data-id="${m.id}" data-field="code"
                      value="${escapeHtml(m.code)}" style="padding:4px 8px"></td>
           <td><input class="input" data-id="${m.id}" data-field="name"
                      value="${escapeHtml(m.name)}" style="padding:4px 8px"></td>
         </tr>`).join('')}</tbody></table>`,
    `<button class="btn" id="mapCancel">取消</button>
     <button class="btn btn-primary" id="mapSave">保存</button>`, '720px');
  $('#mapCancel').addEventListener('click', closeModal);
  $('#mapSave').addEventListener('click', async () => {
    const rows = $$('#modalBody input[data-id]');
    const byId = {};
    rows.forEach(inp => {
      const id = inp.dataset.id;
      byId[id] = byId[id] || { id: Number(id) };
      byId[id][inp.dataset.field] = inp.value;
    });
    for (const id in byId) {
      await api('/api/account_mapping/' + id, 'PUT', byId[id]);
    }
    closeModal(); toast('已保存'); renderVouchers();
  });
}

/* ==================== 数据导入 ==================== */
async function renderDataImport() {
  const tpls = [
    { k: 'products', name: '商品', icon: ICONS.box, desc: '编码、名称必填；进价/售价按元填' },
    { k: 'customers', name: '客户', icon: ICONS.users, desc: '编码、名称必填；信用额度按元填' },
    { k: 'suppliers', name: '供应商', icon: ICONS.truck, desc: '编码、名称必填' },
    { k: 'stock', name: '库存调整', icon: ICONS.list, desc: '编码、仓库编码、数量；正数增加负数减少' }
  ];
  $('#content').innerHTML = `
    <div class="card">
      <div class="card-title">Excel 批量导入</div>
      <p class="text-muted" style="margin-bottom:16px;font-size:13px">
        支持 .xlsx 格式，第一行为表头，从第二行开始导入。
        <strong>编码重复时会自动更新</strong>。
      </p>
      <div class="import-grid">
        ${tpls.map(t => `
          <div class="import-card">
            <div class="import-icon">${t.icon}</div>
            <div class="import-name">${t.name}</div>
            <div class="import-desc">${t.desc}</div>
            <div style="display:flex;gap:8px;margin-top:6px">
              <button class="btn btn-sm" data-tpl="${t.k}">下载模板</button>
              <button class="btn btn-primary btn-sm" data-import="${t.k}">选择文件导入</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="card" id="importResult" style="display:none">
      <div class="card-title">导入结果</div>
      <div id="importResultBody"></div>
    </div>`;

  // 下载模板：改用原生另存为对话框
  $$('[data-tpl]').forEach(btn => btn.addEventListener('click', () => {
    const kind = btn.dataset.tpl;
    downloadWithDialog('/api/import/template/' + kind, 'template_' + kind + '.xlsx');
  }));

  // 导入文件
  $$('[data-import]').forEach(btn => btn.addEventListener('click', () => {
    const kind = btn.dataset.import;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx,.xls';
    input.onchange = async () => {
      if (!input.files.length) return;
      const fd = new FormData();
      fd.append('file', input.files[0]);
      const token = csrfToken;
      try {
        const res = await fetch('/api/import/' + kind, {
          method: 'POST',
          body: fd,
          credentials: 'same-origin',
          headers: token ? { 'X-CSRF-Token': token } : {}
        });
        const json = await res.json();
        if (json.code !== 0) { toast(json.msg, 'error'); return; }
        const d = json.data;
        $('#importResult').style.display = 'block';
        $('#importResultBody').innerHTML = `
          <div class="info-grid">
            <div><span class="info-label">新增：</span>
              <strong class="text-success">${d.success}</strong></div>
            <div><span class="info-label">更新：</span>
              <strong class="text-success">${d.updated || 0}</strong></div>
            <div><span class="info-label">失败：</span>
              <strong class="${d.errors.length ? 'text-danger' : ''}">${d.errors.length}</strong></div>
          </div>
          ${d.errors.length ? `<div style="max-height:260px;overflow:auto;margin-top:12px">
            <table class="detail-table">
              <thead><tr><th style="width:60px">序号</th><th>错误信息</th></tr></thead>
              <tbody>${d.errors.map((e, i) =>
                `<tr><td>${i + 1}</td><td class="text-danger">${escapeHtml(e)}</td></tr>`
              ).join('')}</tbody>
            </table></div>` : ''}`;
        toast(json.msg);
      } catch (e) {
        toast('导入失败：' + e.message, 'error');
      }
    };
    input.click();
  }));
}

/* ==================== 备份恢复 ==================== */
async function renderBackup() {
  if (!currentUser || currentUser.role !== 'admin') {
    $('#content').innerHTML = '<div class="empty">仅管理员可操作</div>';
    return;
  }
  $('#content').innerHTML = `
    <div class="card">
      <div class="card-title">数据备份</div>
      <p class="text-muted" style="margin-bottom:16px;font-size:13px">
        下载当前数据库文件（.db）。建议每周备份一次，保存到移动硬盘或云盘。
      </p>
      <button class="btn btn-primary" id="btnExport">导出数据库</button>
    </div>
    <div class="card">
      <div class="card-title">数据恢复</div>
      <p class="text-muted" style="margin-bottom:16px;font-size:13px">
        <strong class="text-danger">警告：</strong>恢复会覆盖当前所有数据！
        操作前系统会自动备份一份原库。恢复后需要<strong>重启程序</strong>才能生效。
      </p>
      <input type="file" id="restoreFile" accept=".db" style="margin-bottom:12px">
      <button class="btn btn-danger" id="btnImport">上传并恢复</button>
    </div>`;

  $('#btnExport').addEventListener('click', () => {
    const ts = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
    downloadWithDialog('/api/backup/export', 'erp_backup_' + ts + '.db');
  });

  $('#btnImport').addEventListener('click', () => {
    const f = $('#restoreFile').files[0];
    if (!f) { toast('请先选择 .db 文件', 'error'); return; }
    confirmDialog('确定要用该文件覆盖当前数据库吗？此操作不可撤销！', async () => {
      const fd = new FormData();
      fd.append('file', f);
      try {
        const res = await fetch('/api/backup/import', {
          method: 'POST',
          body: fd,
          credentials: 'same-origin',
          headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {}
        });
        const json = await res.json();
        if (json.code !== 0) { toast(json.msg, 'error'); return; }
        toast('恢复成功，请关闭程序后重新打开');
        setTimeout(() => location.reload(), 2000);
      } catch (e) {
        toast('恢复失败：' + e.message, 'error');
      }
    });
  });
}

/* ==================== 客户对账单 ==================== */
async function renderStatements() {
  const custs = await api('/api/customers');
  if (!custs.length) {
    $('#content').innerHTML = '<div class="empty">请先添加客户</div>';
    return;
  }

  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');

  $('#content').innerHTML = `
    <div class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <select class="input" id="stCust">
            <option value="">-- 选择客户 --</option>
            ${custs.map(c => `<option value="${c.id}">${escapeHtml(c.code)} ${escapeHtml(c.name)}</option>`).join('')}
          </select>
          <input type="date" class="input" id="stStart" value="${y}-${m}-01">
          <input type="date" class="input" id="stEnd" value="${todayStr()}">
          <button class="btn btn-primary" id="stQuery">查询</button>
          <button class="btn" id="stPrint">打印</button>
        </div>
      </div>
      <div id="stContent"><div class="empty">请选择客户和日期范围后点击查询</div></div>
    </div>`;

  let lastData = null;
  $('#stQuery').addEventListener('click', async () => {
    const cid = $('#stCust').value;
    if (!cid) { toast('请选择客户', 'error'); return; }
    const s = $('#stStart').value, e = $('#stEnd').value;
    lastData = await api('/api/statement/customer/' + cid + '?start=' + s + '&end=' + e);
    renderStatementContent(lastData);
  });

  $('#stPrint').addEventListener('click', async () => {
    if (!lastData) { toast('请先查询', 'error'); return; }
    const tpl = await api('/api/print_templates/default/statement');
    printStatement(lastData, tpl);
  });
}

function renderStatementContent(d) {
  const txnRows = d.transactions.length ? d.transactions.map(t => `<tr>
      <td>${escapeHtml(t.date)}</td>
      <td><span class="badge ${t.type === '销售' ? 'badge-info' : 'badge-success'}">${t.type}</span></td>
      <td>${escapeHtml(t.no)}</td>
      <td class="num">${t.debit ? fmtMoney(t.debit) : '-'}</td>
      <td class="num">${t.credit ? fmtMoney(t.credit) : '-'}</td>
      <td class="num"><strong>${fmtMoney(t.balance)}</strong></td>
    </tr>`).join('') : '<tr><td colspan="6" class="empty">该时间段无交易</td></tr>';

  $('#stContent').innerHTML = `
    <div class="info-grid" style="margin-top:8px">
      <div><span class="info-label">客户：</span>${escapeHtml(d.customer.name)}</div>
      <div><span class="info-label">联系人：</span>${escapeHtml(d.customer.contact || '-')}</div>
      <div><span class="info-label">电话：</span>${escapeHtml(d.customer.phone || '-')}</div>
      <div><span class="info-label">期间：</span>${d.period.start} ~ ${d.period.end}</div>
    </div>
    <div class="table-wrap"><table class="table">
      <thead><tr><th>日期</th><th>类型</th><th>单号</th>
        <th class="num">应收增加</th><th class="num">回款减少</th><th class="num">余额</th></tr></thead>
      <tbody>
        <tr style="background:#fafbfe;font-weight:600">
          <td colspan="5">期初余额</td>
          <td class="num">${fmtMoney(d.opening_balance)}</td>
        </tr>
        ${txnRows}
        <tr style="background:#fafbfe;font-weight:600">
          <td colspan="3">本期合计</td>
          <td class="num text-success">+${fmtMoney(d.total_debit)}</td>
          <td class="num text-danger">-${fmtMoney(d.total_credit)}</td>
          <td class="num"></td>
        </tr>
        <tr style="background:#fff7ed;font-weight:700;font-size:15px">
          <td colspan="5">期末余额</td>
          <td class="num text-danger">${fmtMoney(d.closing_balance)}</td>
        </tr>
      </tbody></table></div>`;
}

function printStatement(d, tpl) {
  const html = buildPrintHTML({
    title: tpl.header_text || '客户对账单',
    company: tpl.company_name || '',
    footer: tpl.footer_text || '',
    content: `
      <div style="margin-bottom:16px;font-size:14px">
        <div><strong>客户：</strong>${escapeHtml(d.customer.name)}</div>
        <div><strong>期间：</strong>${d.period.start} 至 ${d.period.end}</div>
      </div>
      <table class="pt">
        <thead><tr><th>日期</th><th>类型</th><th>单号</th>
          <th class="num">应收增加</th><th class="num">回款减少</th><th class="num">余额</th></tr></thead>
        <tbody>
          <tr><td colspan="5"><strong>期初余额</strong></td>
            <td class="num">${fmtMoney(d.opening_balance)}</td></tr>
          ${d.transactions.map(t => `<tr>
            <td>${escapeHtml(t.date)}</td><td>${t.type}</td><td>${escapeHtml(t.no)}</td>
            <td class="num">${t.debit ? fmtMoney(t.debit) : '-'}</td>
            <td class="num">${t.credit ? fmtMoney(t.credit) : '-'}</td>
            <td class="num">${fmtMoney(t.balance)}</td>
          </tr>`).join('')}
          <tr><td colspan="3"><strong>本期合计</strong></td>
            <td class="num">+${fmtMoney(d.total_debit)}</td>
            <td class="num">-${fmtMoney(d.total_credit)}</td>
            <td class="num"></td></tr>
          <tr><td colspan="5"><strong>期末余额</strong></td>
            <td class="num"><strong>${fmtMoney(d.closing_balance)}</strong></td></tr>
        </tbody>
      </table>`
  });
  doPrint(html);
}

/* ==================== 打印模板管理 ==================== */
async function renderPrintTemplates() {
  if (!currentUser || currentUser.role !== 'admin') {
    $('#content').innerHTML = '<div class="empty">仅管理员可操作</div>'; return;
  }
  const list = await api('/api/print_templates');
  const rows = list.map(t => `<tr>
      <td>${escapeHtml(t.name)}</td>
      <td>${({ delivery: '送货单', sales: '销售单', purchase: '采购入库单', statement: '对账单' })[t.ttype] || t.ttype}</td>
      <td>${escapeHtml(t.company_name || '-')}</td>
      <td>${escapeHtml(t.header_text || '-')}</td>
      <td><button class="btn-link" data-act="edit" data-id="${t.id}">编辑</button></td>
    </tr>`).join('');

  $('#content').innerHTML = `
    <div class="card">
      <div class="card-title">打印模板</div>
      <p class="text-muted" style="margin-bottom:14px;font-size:13px">
        修改公司抬头、单据标题、页脚说明。打印时自动套用。
      </p>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>模板名</th><th>类型</th><th>公司抬头</th>
          <th>单据标题</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;

  const cache = {}; list.forEach(t => cache[t.id] = t);
  $$('#content [data-act]').forEach(btn => btn.addEventListener('click', () => {
    const t = cache[Number(btn.dataset.id)];
    openModal('编辑打印模板',
      `<div class="form-group"><label>模板名称</label>
         <input class="input" id="tplName" value="${escapeHtml(t.name)}"></div>
       <div class="form-group"><label>公司抬头</label>
         <input class="input" id="tplCompany" value="${escapeHtml(t.company_name || '')}"></div>
       <div class="form-group"><label>单据标题</label>
         <input class="input" id="tplHeader" value="${escapeHtml(t.header_text || '')}"></div>
       <div class="form-group"><label>页脚（如签名栏）</label>
         <input class="input" id="tplFooter" value="${escapeHtml(t.footer_text || '')}"></div>`,
      `<button class="btn" id="tplCancel">取消</button>
       <button class="btn btn-primary" id="tplSave">保存</button>`);
    $('#tplCancel').addEventListener('click', closeModal);
    $('#tplSave').addEventListener('click', async () => {
      await api('/api/print_templates/' + t.id, 'PUT', {
        name: $('#tplName').value.trim(),
        company_name: $('#tplCompany').value.trim(),
        header_text: $('#tplHeader').value.trim(),
        footer_text: $('#tplFooter').value.trim()
      });
      closeModal(); toast('已保存'); renderPrintTemplates();
    });
  }));
}

/* ==================== 打印工具 ==================== */
function buildPrintHTML(opt) {
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>${escapeHtml(opt.title)}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    padding: 30px 40px; color: #222; font-size: 13px;
  }
  .header { text-align: center; margin-bottom: 20px;
            border-bottom: 2px solid #333; padding-bottom: 14px; }
  .company { font-size: 13px; color: #555; margin-bottom: 6px; }
  .title { font-size: 22px; font-weight: 700; letter-spacing: 2px; }
  .info { display: flex; justify-content: space-between;
          margin-bottom: 14px; font-size: 13px; }
  .pt { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
  .pt th, .pt td { border: 1px solid #333; padding: 6px 8px; font-size: 12.5px; }
  .pt th { background: #f0f0f0; font-weight: 600; }
  .pt .num { text-align: right; font-variant-numeric: tabular-nums; }
  .footer { margin-top: 30px; display: flex;
            justify-content: space-between; font-size: 13px; }
  @media print {
    body { padding: 15px 20px; }
    @page { size: A4; margin: 1cm; }
  }
</style>
</head>
<body>
  <div class="header">
    ${opt.company ? `<div class="company">${escapeHtml(opt.company)}</div>` : ''}
    <div class="title">${escapeHtml(opt.title)}</div>
  </div>
  ${opt.content}
  <div class="footer">
    <div>${escapeHtml(opt.footer || '')}</div>
    <div>打印时间：${new Date().toLocaleString('zh-CN')}</div>
  </div>
</body>
</html>`;
}

function doPrint(html) {
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.right = '0';
  iframe.style.bottom = '0';
  iframe.style.width = '0';
  iframe.style.height = '0';
  iframe.style.border = '0';
  document.body.appendChild(iframe);
  const doc = iframe.contentDocument || iframe.contentWindow.document;
  doc.open();
  doc.write(html);
  doc.close();
  setTimeout(() => {
    iframe.contentWindow.focus();
    iframe.contentWindow.print();
    setTimeout(() => document.body.removeChild(iframe), 1000);
  }, 300);
}

async function printSalesOrder(oid) {
  const [d, tpl] = await Promise.all([
    api('/api/sales_orders/' + oid),
    api('/api/print_templates/default/delivery')
  ]);
  const html = buildPrintHTML({
    title: tpl.header_text || '送货单',
    company: tpl.company_name || '',
    footer: tpl.footer_text || '',
    content: `
      <div class="info">
        <div><strong>单号：</strong>${escapeHtml(d.order_no)}</div>
        <div><strong>日期：</strong>${escapeHtml(d.order_date)}</div>
      </div>
      <div class="info">
        <div><strong>客户：</strong>${escapeHtml(d.customer_name || '')}</div>
        <div><strong>联系人：</strong>${escapeHtml(d.contact || '')}
          &nbsp; <strong>电话：</strong>${escapeHtml(d.phone || '')}</div>
      </div>
      <table class="pt">
        <thead><tr><th style="width:50px">序号</th><th>商品</th><th>规格</th>
          <th class="num">数量</th><th>单位</th><th class="num">单价</th>
          <th class="num">金额</th></tr></thead>
        <tbody>
          ${d.items.map((it, i) => `<tr>
            <td style="text-align:center">${i + 1}</td>
            <td>${escapeHtml(it.product_name || '')}</td>
            <td>${escapeHtml(it.unit || '')}</td>
            <td class="num">${it.qty}</td>
            <td>${escapeHtml(it.unit || '')}</td>
            <td class="num">${fmtMoney(it.price)}</td>
            <td class="num">${fmtMoney(it.amount)}</td>
          </tr>`).join('')}
          <tr><td colspan="6" class="num"><strong>合计</strong></td>
            <td class="num"><strong>${fmtMoney(d.total_amount)}</strong></td></tr>
          ${d.discount ? `<tr><td colspan="6" class="num">优惠</td>
            <td class="num">-${fmtMoney(d.discount)}</td></tr>` : ''}
          <tr><td colspan="6" class="num"><strong>实收</strong></td>
            <td class="num"><strong>${fmtMoney(d.final_amount)}</strong></td></tr>
        </tbody>
      </table>`
  });
  doPrint(html);
}

async function printPurchaseOrder(oid) {
  const [d, tpl] = await Promise.all([
    api('/api/purchase_orders/' + oid),
    api('/api/print_templates/default/purchase')
  ]);
  const html = buildPrintHTML({
    title: tpl.header_text || '采购入库单',
    company: tpl.company_name || '',
    footer: tpl.footer_text || '',
    content: `
      <div class="info">
        <div><strong>单号：</strong>${escapeHtml(d.order_no)}</div>
        <div><strong>日期：</strong>${escapeHtml(d.order_date)}</div>
      </div>
      <div class="info">
        <div><strong>供应商：</strong>${escapeHtml(d.supplier_name || '')}</div>
        <div><strong>仓库：</strong>${escapeHtml(d.warehouse_name || '')}</div>
      </div>
      <table class="pt">
        <thead><tr><th style="width:50px">序号</th><th>商品</th><th>批次</th>
          <th class="num">数量</th><th class="num">单价</th>
          <th class="num">金额</th></tr></thead>
        <tbody>
          ${d.items.map((it, i) => `<tr>
            <td style="text-align:center">${i + 1}</td>
            <td>${escapeHtml(it.product_name || '')}</td>
            <td>${escapeHtml(it.batch_no || '-')}</td>
            <td class="num">${it.qty}</td>
            <td class="num">${fmtMoney(it.price)}</td>
            <td class="num">${fmtMoney(it.amount)}</td>
          </tr>`).join('')}
          <tr><td colspan="5" class="num"><strong>合计</strong></td>
            <td class="num"><strong>${fmtMoney(d.final_amount)}</strong></td></tr>
        </tbody>
      </table>`
  });
  doPrint(html);
}

/* ==================== AI 设置（开关式接入） ==================== */
async function renderAISettings() {
  let st = { enabled: false, api_base: '', model: 'gpt-4o-mini', has_key: false, default_model: 'gpt-4o-mini' };
  let stats = null;
  try { st = await api('/api/ai/status'); } catch (e) {}
  try { stats = await api('/api/ai/stats'); } catch (e) {}

  const t = stats ? stats.today : { calls: 0, success: 0, failed: 0, cached: 0, prompt_tokens: 0, completion_tokens: 0, avg_ms: 0 };
  const tot = stats ? stats.total : { calls: 0, prompt_tokens: 0, completion_tokens: 0 };
  const statsHtml = stats ? `
    <div class="card">
      <div class="section-title">AI 调用统计</div>
      <div class="dash-kpi-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:12px">
        <div class="kpi-card compact blue"><div class="kpi-icon">${ICONS.spark}</div>
          <div class="kpi-content"><div class="kpi-value">${t.calls}</div><div class="kpi-label">今日调用</div></div></div>
        <div class="kpi-card compact green"><div class="kpi-icon">${ICONS.check}</div>
          <div class="kpi-content"><div class="kpi-value">${t.success}</div><div class="kpi-label">成功 / 缓存 ${t.cached}</div></div></div>
        <div class="kpi-card compact ${t.failed ? 'red' : 'cyan'}"><div class="kpi-icon">${ICONS.alert}</div>
          <div class="kpi-content"><div class="kpi-value">${t.failed}</div><div class="kpi-label">失败</div></div></div>
        <div class="kpi-card compact orange"><div class="kpi-icon">${ICONS.clock}</div>
          <div class="kpi-content"><div class="kpi-value">${t.avg_ms}ms</div><div class="kpi-label">平均耗时</div></div></div>
      </div>
      <div class="text-muted" style="font-size:12px">
        今日 Token：输入 ${t.prompt_tokens} + 输出 ${t.completion_tokens} ｜
        累计调用 ${tot.calls} 次，累计 Token ${tot.prompt_tokens + tot.completion_tokens}
      </div>
    </div>` : '';

  $('#content').innerHTML = `
  <div class="card">
    <div class="section-title">AI 接入设置</div>
    <p class="text-muted" style="margin-bottom:14px;font-size:13px">
      本系统预留了消耗 token 的 AI 接口位。填写下方任一兼容服务的接口信息并打开开关，
      工作台的「AI 经营摘要」将自动切换为大模型分析；未配置时使用内置规则摘要，不消耗任何 token。
    </p>

    <div class="switch-row">
      <div>
        <div class="switch-label">启用 AI（开关式接入）</div>
        <div class="switch-desc" id="aiStateDesc">当前：未启用，使用内置规则摘要</div>
      </div>
      <label class="switch">
        <input type="checkbox" id="aiEnabled" ${st.enabled ? 'checked' : ''}>
        <span class="track"></span>
      </label>
    </div>
    <div style="height:1px;background:var(--border);margin:4px 0 14px"></div>

    <div class="form-group">
      <label>API Base（接口地址）</label>
      <input class="input" id="aiApiBase" placeholder="https://api.openai.com/v1" value="${escapeHtml(st.api_base || '')}">
      <div class="text-muted" style="font-size:12px;margin-top:4px">
        常用：OpenAI https://api.openai.com/v1 ｜ DeepSeek https://api.deepseek.com/v1
        ｜ 通义 https://dashscope.aliyuncs.com/compatible-mode/v1 ｜ 本地 Ollama http://127.0.0.1:11434/v1
      </div>
    </div>
    <div class="form-group">
      <label>API Key（密钥）</label>
      <input type="password" class="input" id="aiApiKey" placeholder="${st.has_key ? '已配置（留空则保持不变）' : 'sk-...'}" autocomplete="off">
      <div class="text-muted" style="font-size:12px;margin-top:4px">密钥仅保存在本机数据库，不会上传到任何地方。</div>
    </div>
    <div class="form-group">
      <label>模型名称（Model）</label>
      <input class="input" id="aiModel" placeholder="${escapeHtml(st.default_model)}" value="${escapeHtml(st.model || '')}">
      <div class="text-muted" style="font-size:12px;margin-top:4px">
        常用：gpt-4o-mini ｜ deepseek-chat ｜ qwen-plus ｜ llama3.2（Ollama 本地）
      </div>
    </div>
    <div class="toolbar" style="margin-bottom:0">
      <div class="toolbar-left">
        <button class="btn btn-primary" id="aiSave">保存配置</button>
        <button class="btn" id="aiTest">测试连接</button>
        <button class="btn" id="aiTry">立即体验 →</button>
      </div>
      <div class="toolbar-right">
        <span class="badge ${st.enabled ? 'badge-success' : 'badge-muted'}" id="aiStateBadge">${st.enabled ? '已启用' : '未启用'}</span>
      </div>
    </div>
  </div>

  ${statsHtml}

  <div class="card">
    <div class="section-title">接入说明</div>
    <div class="ai-text" id="aiGuide" style="min-height:0"></div>
  </div>`;

  const guide = [
    '1. 在任一 AI 服务商（OpenAI / DeepSeek / 通义 / Moonshot 等）申请 API Key。',
    '2. 把「API Base」「API Key」「模型名称」填入上方，打开启用开关并保存。',
    '3. 点击「测试连接」验证链路；成功后回到工作台，AI 经营摘要将自动使用大模型生成。',
    '4. 关闭开关或留空 Key 即回到内置规则摘要，不消耗任何 token。'
  ].join('\n');
  revealText($('#aiGuide'), guide);

  const stateDesc = $('#aiStateDesc');
  const updDesc = () => {
    stateDesc.textContent = $('#aiEnabled').checked
      ? '当前：已启用，工作台摘要将由大模型生成（消耗 token）'
      : '当前：未启用，使用内置规则摘要（零消耗）';
  };
  $('#aiEnabled').addEventListener('change', updDesc);
  updDesc();

  $('#aiSave').addEventListener('click', async () => {
    try {
      await api('/api/ai/settings', 'PUT', {
        enabled: $('#aiEnabled').checked,
        api_base: $('#aiApiBase').value.trim(),
        api_key: $('#aiApiKey').value.trim(),
        model: $('#aiModel').value.trim()
      });
      toast('AI 配置已保存');
      renderAISettings();
    } catch (e) {}
  });

  $('#aiTest').addEventListener('click', async () => {
    const btn = $('#aiTest');
    btn.disabled = true;
    btn.textContent = '测试中...';
    try {
      const data = await api('/api/ai/test', 'POST', {});
      toast('AI 连接正常：' + (data.reply || ''), 'success');
    } catch (e) {
      toast('测试失败', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '测试连接';
    }
  });
  $('#aiTry').addEventListener('click', () => {
    navigate('dashboard');
    toast('已跳转到工作台，AI 经营摘要正在生成', 'success');
  });
}

/* ==================== 演示数据（P0：一键让系统“活”起来） ==================== */
async function renderDemo() {
  let st = { has_demo: false, backup_exists: false };
  try { st = await api('/api/demo/status'); } catch (e) {}

  $('#content').innerHTML = `
  <div class="card">
    <div class="section-title">一键演示数据</div>
    <p class="text-muted" style="margin-bottom:16px;font-size:13px">
      生成一套逼真的仿真业务数据，让工作台立刻「活」起来：6 个月销售趋势起伏、逾期应收、
      低库存预警、客户跟进提醒、资金流水。适合演示、测试与面试展示。
    </p>
    <div class="switch-row">
      <div>
        <div class="switch-label">当前状态</div>
        <div class="switch-desc" id="demoStateDesc">${st.has_demo ? '已生成演示数据' : '尚未生成（可一键生成）'}</div>
      </div>
      <span class="badge ${st.has_demo ? 'badge-success' : 'badge-muted'}" id="demoStateBadge">
        ${st.has_demo ? '已有演示数据' : '未生成'}</span>
    </div>
    <div class="toolbar" style="margin-bottom:0">
      <div class="toolbar-left">
        <button class="btn btn-primary" id="demoSeed" ${st.has_demo ? 'disabled' : ''}>一键生成演示数据</button>
        <button class="btn btn-danger" id="demoClear" ${st.has_demo ? '' : 'disabled'}>清理演示数据</button>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="section-title">生成内容</div>
    <div class="ai-text" id="demoGuide" style="min-height:0"></div>
  </div>`;

  const guide = [
    '1. 过去 6 个月销售订单（含本月），趋势图有起伏；对应采购入库与加权成本联动。',
    '2. 多笔逾期应收（未收 / 部分收款），工作台右侧出现红色紧急提醒。',
    '3. 中性笔、无线鼠标、冷轧钢板库存压到安全线以下，触发补货预警。',
    '4. 客户写入「最近跟进」备注，工作台出现客户跟进待办。',
    '5. 历史回款 / 付款与资金日记账，资金账户有真实动静。',
    '6. 安全机制：首次生成自动备份 erp.db → erp.db.demo_backup，「清理」一键还原现场，绝不残留。'
  ].join('\n');
  revealText($('#demoGuide'), guide);

  $('#demoSeed').addEventListener('click', async () => {
    const btn = $('#demoSeed');
    btn.disabled = true; btn.textContent = '生成中...';
    try {
      const r = await api('/api/demo/seed', 'POST', {});
      toast('生成完成，回到工作台查看效果', 'success');
      renderDemo();
    } catch (e) {} finally {
      btn.disabled = false; btn.textContent = '一键生成演示数据';
    }
  });

  $('#demoClear').addEventListener('click', () => {
    confirmDialog('清理演示数据将把数据库还原到生成前的状态（真实数据不受影响）。确定清理？', async () => {
      const msg = await api('/api/demo/clear', 'POST', {});
      toast(msg, 'success');
      renderDemo();
    });
  });
}

/* ==================== 开放接口文档（P2：RPA / 二次开发接入） ==================== */
async function renderOpenAPI() {
  const spec = await api('/api/openapi');
  const methodCls = { GET: 'badge-success', POST: 'badge-info', PUT: 'badge-warn', DELETE: 'badge-danger' };

  $('#content').innerHTML = `
  <div class="card">
    <div class="toolbar">
      <div class="toolbar-left">
        <div class="section-title" style="margin:0">开放接口文档</div>
      </div>
      <div class="toolbar-right">
        <span class="badge badge-info">共 ${spec.count} 个接口</span>
        <button class="btn" id="apiExport">导出 JSON</button>
      </div>
    </div>
    <p class="text-muted" style="font-size:13px;margin-bottom:14px">
      全部接口前缀 /api，需携带 Cookie 会话；写操作需附加请求头
      <code style="background:var(--table-head);padding:1px 6px;border-radius:4px">X-CSRF-Token</code>。
      可被影刀 / 按键精灵等 RPA 工具直接调用，实现机器人自动开单、抓取库存、批量对账。
    </p>
    ${Object.keys(spec.groups).map(g => `
      <div class="section-title">${escapeHtml(g)}</div>
      <div class="table-wrap" style="margin-bottom:14px"><table class="table">
        <thead><tr><th style="width:80px">方法</th><th style="width:42%">接口</th><th>说明 / 示例参数</th></tr></thead>
        <tbody>
          ${spec.groups[g].map(r => `<tr>
            <td>${r.methods.map(m => `<span class="badge ${methodCls[m] || 'badge-muted'}">${m}</span>`).join(' ')}</td>
            <td><code style="font-size:12px;color:var(--primary)">${escapeHtml(r.path)}</code></td>
            <td>
              <div>${escapeHtml(r.desc)}</div>
              ${r.params && r.params !== '-' ? `<div class="text-muted" style="font-size:12px;margin-top:2px">${escapeHtml(r.params)}</div>` : ''}
            </td>
          </tr>`).join('')}
        </tbody></table></div>
    `).join('')}
  </div>`;

  $('#apiExport').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify(spec, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'erp_openapi.json';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(a.href); }, 100);
  });
}