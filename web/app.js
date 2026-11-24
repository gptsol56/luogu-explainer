/* 洛谷题目自动讲解 —— 前端逻辑 (无构建、无第三方库、无外部 CDN) */
(function () {
  'use strict';

  /* 反引号用 fromCharCode 构造, 源码里不出现字面量 */
  var TICK = String.fromCharCode(96);
  var FENCE_OPEN = new RegExp('^\\s*' + TICK + '{3,}\\s*([\\w+#.-]*)\\s*$');
  var FENCE_CLOSE = new RegExp('^\\s*' + TICK + '{3,}\\s*$');
  var CODE_SPAN = new RegExp(TICK + '([^' + TICK + ']+)' + TICK, 'g');
  var BOLD_STAR = /\*\*([^*]+)\*\*/g;
  var BOLD_UNDER = /__([^_]+)__/g;
  var ITALIC = /(^|[^\w*])\*([^*\n]+)\*/g;
  var LINK = /\[([^\]]+)\]\(([^)\s]+)\)/g;
  var LIST_ITEM = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
  var HEADING = /^(#{1,6})\s+(.*)$/;

  var KEY_STORE = "luogu-explainer.byok";
  var MODE = { LOCAL: "local", BYOK: "byok" };
  var currentMode = null;
  var currentMarkdown = "";
  var currentTitle = "讲解";
  var providerTable = null;   // explainer/providers.json 的内容
  var currentProvider = null; // 当前选中的厂商 id
  var lastHealth = null;      // 最近一次 /api/health 的结果

  function $(sel) { return document.querySelector(sel); }
  function byId(id) { return document.getElementById(id); }

  /* --------------------------------------------------------------
   * 极简 Markdown 渲染器
   * 支持: 标题 / 有序无序列表 / 代码块 / 表格 / 粗体 / 斜体 /
   *       行内代码 / 引用 / 水平线 / 链接
   * 所有文本先转义再拼接, 防注入
   * -------------------------------------------------------------- */
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&')
      .replace(/</g, '<')
      .replace(/>/g, '>')
      .replace(/"/g, '"')
      .replace(/'/g, '&#39;');
  }

  function safeLink(label, rawUrl) {
    var url = String(rawUrl).replace(/&/g, '&').trim();
    if (/^(https?:\/\/|mailto:|#|\/|\.\/|\.\.\/)/i.test(url)) {
      return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>';
    }
    return label; // 危险协议 (javascript: 等) 一律降级成纯文本
  }

  function renderInline(text) {
    var out = escapeHtml(text);
    var codes = [];
    out = out.replace(CODE_SPAN, function (whole, code) {
      codes.push(code);
      return '\x00C' + (codes.length - 1) + '\x00';
    });
    out = out.replace(BOLD_STAR, '<strong>$1</strong>');
    out = out.replace(BOLD_UNDER, '<strong>$1</strong>');
    out = out.replace(ITALIC, '$1<em>$2</em>');
    out = out.replace(LINK, function (whole, label, url) {
      return safeLink(label, url);
    });
    out = out.replace(/\x00C(\d+)\x00/g, function (whole, index) {
      var value = codes[Number(index)];
      return value === undefined ? '' : '<code>' + value + '</code>';
    });
    return out;
  }

  function isTableSeparator(line) {
    var s = String(line || '').trim();
    if (!s || s.indexOf('-') === -1) { return false; }
    return /^[|\s:-]+$/.test(s);
  }

  function splitTableRow(line) {
    var s = String(line || '').trim();
    if (s.charAt(0) === '|') { s = s.slice(1); }
    if (s.charAt(s.length - 1) === '|') { s = s.slice(0, -1); }
    return s.split('|').map(function (cell) { return cell.trim(); });
  }

  function renderMarkdown(src) {
    var lines = String(src == null ? '' : src).replace(/\r\n?/g, '\n').split('\n');
    var html = [];
    var i = 0;

    while (i < lines.length) {
      var line = lines[i];

      /* 围栏代码块 */
      var fence = line.match(FENCE_OPEN);
      if (fence) {
        var lang = fence[1] || '';
        var buf = [];
        i += 1;
        while (i < lines.length && !FENCE_CLOSE.test(lines[i])) {
          buf.push(lines[i]);
          i += 1;
        }
        if (i < lines.length) { i += 1; }
        var cls = lang ? ' class="lang-' + escapeHtml(lang) + '"' : '';
        html.push('<pre' + cls + '><code>' + escapeHtml(buf.join('\n')) + '</code></pre>');
        continue;
      }

      if (!line.trim()) { i += 1; continue; }

      /* 水平线 */
      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
        html.push('<hr>');
        i += 1;
        continue;
      }

      /* 标题 */
      var heading = line.match(HEADING);
      if (heading) {
        var level = heading[1].length;
        html.push('<h' + level + '>' + renderInline(heading[2]) + '</h' + level + '>');
        i += 1;
        continue;
      }

      /* 表格: 本行含 | 且下一行是分隔行 */
      if (line.indexOf('|') !== -1 && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
        var header = splitTableRow(line);
        i += 2;
        var rows = [];
        while (i < lines.length && lines[i].indexOf('|') !== -1 && lines[i].trim()) {
          rows.push(splitTableRow(lines[i]));
          i += 1;
        }
        var table = '<table><thead><tr>';
        header.forEach(function (cell) { table += '<th>' + renderInline(cell) + '</th>'; });
        table += '</tr></thead><tbody>';
        rows.forEach(function (row) {
          table += '<tr>';
          header.forEach(function (_, index) { table += '<td>' + renderInline(row[index] || '') + '</td>'; });
          table += '</tr>';
        });
        table += '</tbody></table>';
        html.push(table);
        continue;
      }

      /* 引用 */
      if (/^\s*>\s?/.test(line)) {
        var quoted = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          quoted.push(lines[i].replace(/^\s*>\s?/, ''));
          i += 1;
        }
        html.push('<blockquote>' + renderMarkdown(quoted.join('\n')) + '</blockquote>');
        continue;
      }

      /* 列表 */
      var listItem = line.match(LIST_ITEM);
      if (listItem) {
        var ordered = /\d/.test(listItem[1]);
        var items = [];
        while (i < lines.length) {
          var item = lines[i].match(LIST_ITEM);
          if (!item) {
            if (items.length && lines[i].trim() && !LIST_ITEM.test(lines[i])) {
              items[items.length - 1] += ' ' + lines[i].trim();
              i += 1;
              continue;
            }
            break;
          }
          if (/\d/.test(item[1]) !== ordered) { break; }
          items.push(item[2]);
          i += 1;
        }
        var tag = ordered ? 'ol' : 'ul';
        var listHtml = '<' + tag + '>';
        items.forEach(function (entry) { listHtml += '<li>' + renderInline(entry) + '</li>'; });
        listHtml += '</' + tag + '>';
        html.push(listHtml);
        continue;
      }

      /* 段落 */
      var paragraph = [];
      while (i < lines.length && lines[i].trim() &&
             !LIST_ITEM.test(lines[i]) &&
             !HEADING.test(lines[i]) &&
             !FENCE_OPEN.test(lines[i]) &&
             !/^\s*>\s?/.test(lines[i]) &&
             !/^\s*([-*_])(\s*\1){2,}\s*$/.test(lines[i])) {
        paragraph.push(lines[i]);
        i += 1;
      }
      if (paragraph.length) {
        html.push('<p>' + renderInline(paragraph.join('\n')).replace(/\n/g, '<br>') + '</p>');
      } else {
        i += 1;
      }
    }
    return html.join('\n');
  }

  /* --------------------------------------------------------------
   * 工具
   * -------------------------------------------------------------- */
  function showError(id, message) {
    var box = byId(id);
    if (!box) { return; }
    box.textContent = message;
    box.hidden = false;
  }

  function clearError(id) {
    var box = byId(id);
    if (box) { box.hidden = true; box.textContent = ''; }
  }

  function fetchJson(url, options, timeoutMs) {
    var controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = null;
    var opts = options || {};
    if (controller) { opts.signal = controller.signal; }
    if (timeoutMs) {
      timer = setTimeout(function () { if (controller) { controller.abort(); } }, timeoutMs);
    }
    return fetch(url, opts).then(function (resp) {
      return resp.json().catch(function () {
        throw new Error('服务端返回的不是 JSON (HTTP ' + resp.status + ')');
      });
    }).then(function (data) {
      if (timer) { clearTimeout(timer); }
      return data;
    }, function (err) {
      if (timer) { clearTimeout(timer); }
      if (err && err.name === 'AbortError') {
        throw new Error('请求超时');
      }
      throw err;
    });
  }

  /* --------------------------------------------------------------
   * BYOK 配置存取 (只存本机 localStorage)
   * -------------------------------------------------------------- */
  function loadByok() {
    try {
      var raw = window.localStorage.getItem(KEY_STORE);
      if (!raw) { return null; }
      var data = JSON.parse(raw);
      if (!data || !data.api_key) { return null; }
      return data;
    } catch (err) {
      return null;
    }
  }

  function saveByok(data) {
    try {
      window.localStorage.setItem(KEY_STORE, JSON.stringify(data));
      return true;
    } catch (err) {
      return false;
    }
  }

  function clearByok() {
    try { window.localStorage.removeItem(KEY_STORE); } catch (err) { /* 忽略 */ }
  }

  function refreshKeyState() {
    var state = byId('key-state');
    var saved = loadByok();
    if (!state) { return; }
    if (saved) {
      state.textContent = '已在本机保存密钥 (模型 ' + (saved.model || '-') + '), 只存在浏览器 localStorage 里';
      state.classList.remove('is-bad');
      var keyInput = byId('key-input');
      if (keyInput && !keyInput.value) { keyInput.value = saved.api_key; }
      var baseInput = byId('base-input');
      if (baseInput && saved.base_url) { baseInput.value = saved.base_url; }
      var modelInput = byId('model-input');
      if (modelInput && saved.model) { modelInput.value = saved.model; }
      var protocolSelect = byId('protocol-select');
      if (protocolSelect && saved.protocol) { protocolSelect.value = saved.protocol; }
    } else {
      state.textContent = '未保存密钥';
      state.classList.add('is-bad');
    }
  }

  /* --------------------------------------------------------------
   * 模型厂商预设
   * 唯一真源是 explainer/providers.json —— 后端读它, 前端也读它, 两端不会漂。
   * 本机代理模式走 /api/providers, 静态站走同目录的 providers.json。
   * -------------------------------------------------------------- */
  function loadProviders() {
    var urls = ['/api/providers', 'providers.json'];
    function attempt(index) {
      if (index >= urls.length) {
        return Promise.reject(new Error('模型预设表读取失败'));
      }
      return fetch(urls[index]).then(function (resp) {
        if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
        return resp.json();
      }).catch(function () { return attempt(index + 1); });
    }
    return attempt(0).then(function (data) {
      if (!data || !data.providers || !data.providers.length) {
        throw new Error('模型预设表内容不完整');
      }
      providerTable = data;
      return data;
    });
  }

  function findProviderSpec(id) {
    if (!providerTable || !id) { return null; }
    for (var i = 0; i < providerTable.providers.length; i++) {
      if (providerTable.providers[i].id === id) { return providerTable.providers[i]; }
    }
    return null;
  }

  function renderProviderOptions() {
    var select = byId('provider-select');
    if (!select || !providerTable) { return; }
    select.innerHTML = '';
    providerTable.providers.forEach(function (spec) {
      var option = document.createElement('option');
      option.value = spec.id;
      option.textContent = spec.label;
      select.appendChild(option);
    });
    var saved = loadByok();
    var wanted = (saved && saved.provider) || providerTable.default_provider;
    if (!findProviderSpec(wanted)) { wanted = providerTable.default_provider; }
    select.value = wanted;
    currentProvider = wanted;
  }

  function renderDirectList() {
    var el = byId('byok-direct');
    if (!el || !providerTable) { return; }
    var ok = [];
    var bad = [];
    var unknown = [];
    providerTable.providers.forEach(function (spec) {
      if (spec.browser_direct === true) { ok.push(spec.label); }
      else if (spec.browser_direct === false) { bad.push(spec.label); }
      else { unknown.push(spec.label); }
    });
    var parts = [];
    if (ok.length) { parts.push('浏览器能直连: ' + ok.join('、') + '。'); }
    if (bad.length) { parts.push('静态站里会被浏览器拦下: ' + bad.join('、') + '。'); }
    if (unknown.length) { parts.push(unknown.join('、') + ' 得看你自己的服务有没有发 CORS 头。'); }
    el.textContent = parts.join('');
  }

  function applyProviderToByok() {
    var spec = findProviderSpec(currentProvider);
    if (!spec) { return; }
    var base = byId('base-input');
    var model = byId('model-input');
    var protocol = byId('protocol-select');
    if (base && spec.base_url) { base.value = spec.base_url; }
    if (model && spec.model) { model.value = spec.model; }
    if (protocol && spec.protocol) { protocol.value = spec.protocol; }
  }

  /* --------------------------------------------------------------
   * 浏览器直连模型 (只有自带密钥模式走这条路)
   * 两种接口形状: Anthropic 风格与 OpenAI 风格。
   * -------------------------------------------------------------- */
  function joinEndpoint(baseUrl, suffix) {
    var base = String(baseUrl || '').replace(/\/+$/, '');
    if (!base) { throw new Error('接口地址为空'); }
    if (base.slice(-suffix.length) === suffix) { return base; }
    return base + suffix;
  }

  function callModelDirect(baseUrl, apiKey, model, protocol, prompt) {
    var url;
    var headers;
    if (protocol === 'openai') {
      url = joinEndpoint(baseUrl, '/chat/completions');
      headers = {
        'content-type': 'application/json',
        'Authorization': 'Bearer ' + apiKey
      };
    } else {
      url = joinEndpoint(baseUrl, '/v1/messages');
      headers = {
        'content-type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      };
    }
    var body = {
      model: model,
      max_tokens: 4096,
      messages: [{ role: 'user', content: prompt }]
    };
    return fetch(url, { method: 'POST', headers: headers, body: JSON.stringify(body) })
      .then(function (resp) {
        return resp.text().then(function (textBody) {
          var data;
          try { data = JSON.parse(textBody); } catch (err) {
            throw new Error('接口返回的不是 JSON (HTTP ' + resp.status + ')');
          }
          if (!resp.ok) {
            var detail = (data && data.error && (data.error.message || data.error))
              ? (data.error.message || data.error)
              : textBody.slice(0, 200);
            throw new Error('HTTP ' + resp.status + ': ' + detail);
          }
          return data;
        });
      });
  }

  function extractContent(data, protocol) {
    if (protocol === 'openai') {
      var choices = (data && data.choices) || [];
      if (choices.length && choices[0] && choices[0].message) {
        return String(choices[0].message.content || '');
      }
      return '';
    }
    var chunks = (data && data.content) || [];
    return chunks.map(function (chunk) { return chunk.text || ''; }).join('');
  }

  function extractUsage(data, protocol) {
    var usage = (data && data.usage) || {};
    if (protocol === 'openai') {
      return { input: usage.prompt_tokens, output: usage.completion_tokens };
    }
    return { input: usage.input_tokens, output: usage.output_tokens };
  }

  /* --------------------------------------------------------------
   * 运行模式检测
   * -------------------------------------------------------------- */
  function detectMode() {
    return fetchJson('/api/health', {}, 2500).then(function (data) {
      if (data && data.ok) {
        return { mode: MODE.LOCAL, health: data };
      }
      throw new Error('健康检查未通过');
    }).catch(function () {
      return { mode: MODE.BYOK, health: null };
    });
  }

  function applyMode(result) {
    currentMode = result.mode;
    lastHealth = result.health || null;
    var meta = byId('header-meta');
    var keyPanel = byId('key-panel');
    var hint = byId('input-hint');
    var service = byId('status-service');
    var creds = byId('status-creds');
    if (result.mode === MODE.LOCAL) {
      var h = result.health;
      if (meta) {
        meta.textContent = '本机代理模式 · 模型 ' + (h.model || '-') + ' · 接口 ' + (h.base_host || '-') +
          ' · 密钥 ' + (h.has_key ? '在服务端' : '缺失') + ' · 版本 ' + (h.version || '-') +
          ' · 可选厂商 ' + ((h.providers || []).length) + ' 家';
      }
      if (keyPanel) { keyPanel.hidden = true; }
      if (hint) {
        hint.textContent = '题号与题面二选一。填题号会先请求洛谷接口 (需要登录态, 未登录时会给出提示), 拿不到题面时可直接改用「粘贴题面」。';
      }
      if (service) { service.textContent = '在线 · 模型 ' + (h.model || '-'); }
      if (creds) {
        if (h.punch_ready) {
          creds.textContent = '已配置 (LUOGU_CLIENT_ID / LUOGU_UID)';
          creds.classList.remove('is-bad');
        } else {
          creds.textContent = '未配置, 请设置 LUOGU_CLIENT_ID 与 LUOGU_UID';
          creds.classList.add('is-bad');
        }
      }
      return;
    }
    /* 静态模式 (GitHub Pages): 没有后端代理 */
    if (meta) {
      meta.textContent = '静态站点模式 · 密钥只保存在本机浏览器 · 演示样例可用';
    }
    if (keyPanel) { keyPanel.hidden = false; }
    if (hint) {
      hint.textContent = '当前是 GitHub Pages 静态站, 没有后端代理: 填题号无法自动抓取洛谷题面, 请粘贴题面; 讲解需要你自己的模型密钥。';
    }
    if (service) { service.textContent = '静态站 (无后端代理) · 打卡请用命令行'; service.classList.add('is-bad'); }
    if (creds) { creds.textContent = '静态站无法打卡, 请用命令行工具'; creds.classList.add('is-bad'); }
    var punchBtn = byId('punch-btn');
    if (punchBtn) { punchBtn.disabled = true; punchBtn.title = '静态站没有后端, 打卡请用命令行工具'; }
    refreshKeyState();
  }

  /* --------------------------------------------------------------
   * 提示词模板 (与 explainer 读的是同一份文件)
   * -------------------------------------------------------------- */
  var templateCache = null;

  function loadTemplate() {
    if (templateCache) { return Promise.resolve(templateCache); }
    var urls = ['/prompt_template.json', 'prompt_template.json'];
    function attempt(index) {
      if (index >= urls.length) {
        return Promise.reject(new Error('提示词模板读取失败'));
      }
      return fetch(urls[index]).then(function (resp) {
        if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
        return resp.json();
      }).catch(function () { return attempt(index + 1); });
    }
    return attempt(0).then(function (data) {
      if (!data || !data.user_prompt_template) {
        throw new Error('提示词模板字段缺失');
      }
      templateCache = data;
      return data;
    });
  }

  function buildPrompt(template, problemText, style) {
    var sections = (template.required_sections || []).map(function (name) {
      return '## ' + name;
    }).join('\n');
    return String(template.user_prompt_template)
      .replace(/\{\{style\}\}/g, style)
      .replace(/\{\{sections\}\}/g, sections)
      .replace(/\{\{problem\}\}/g, problemText);
  }

  /* --------------------------------------------------------------
   * 题目讲解
   * -------------------------------------------------------------- */
  function initExplain() {
    byId('explain-btn').addEventListener('click', doExplain);
    byId('provider-select').addEventListener('change', function () {
      currentProvider = byId('provider-select').value;
      applyProviderToByok();
    });
    byId('demo-btn').addEventListener('click', doDemo);
    byId('copy-btn').addEventListener('click', doCopy);
    byId('download-btn').addEventListener('click', doDownload);
    byId('save-key-btn').addEventListener('click', doSaveKey);
    byId('clear-key-btn').addEventListener('click', doClearKey);
  }

  function showResult(title, markdown, metaText) {
    currentMarkdown = markdown || '';
    currentTitle = title || '讲解';
    byId('result-title').textContent = currentTitle;
    byId('result-body').innerHTML = renderMarkdown(currentMarkdown);
    byId('result-meta').textContent = metaText || '';
    byId('explain-result').hidden = false;
    byId('explain-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function doExplain() {
    var pid = byId('pid-input').value.trim();
    var text = byId('text-input').value.trim();
    var style = byId('style-select').value;
    if (!pid && !text) {
      showError('explain-error', '请填写题号, 或者直接粘贴题面。');
      return;
    }
    clearError('explain-error');
    var button = byId('explain-btn');
    button.disabled = true;
    button.textContent = '生成中……';

    if (currentMode === MODE.LOCAL) {
      return fetchJson('/api/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pid, text: text, style: style, provider: currentProvider })
      }, 180000).then(function (data) {
        if (!data.ok) {
          showError('explain-error', data.error || '讲解失败');
          return;
        }
        var usage = data.usage || {};
        showResult(data.title, data.markdown,
          '来源: ' + (data.source === 'luogu' ? '洛谷题号' : '粘贴题面') +
          '　模型: ' + (data.model || '-') +
          '　用时: ' + (data.elapsed_ms || 0) + ' ms' +
          '　tokens: 输入 ' + (usage.input_tokens == null ? '-' : usage.input_tokens) +
          ' / 输出 ' + (usage.output_tokens == null ? '-' : usage.output_tokens));
      }).catch(function (err) {
        showError('explain-error', '请求失败: ' + err.message);
      }).then(function () {
        button.disabled = false;
        button.textContent = '生成讲解';
      });
    }

    /* 静态模式: 浏览器直连模型 */
    if (!text) {
      showError('explain-error',
        '静态站没有后端代理, 无法自动抓取洛谷题面 —— 请把题面粘贴进来, 或在本机运行 server/app.py。');
      button.disabled = false;
      button.textContent = '生成讲解';
      return;
    }
    var saved = loadByok();
    var keyInput = byId('key-input').value.trim();
    var spec = findProviderSpec(currentProvider);
    var baseInput = byId('base-input').value.trim() || (spec ? (spec.base_url || '') : '');
    var modelInput = byId('model-input').value.trim() || (spec ? (spec.model || '') : '');
    var protocol = byId('protocol-select').value.trim() || 'anthropic';
    var apiKey = keyInput || (saved ? saved.api_key : '');
    if (!apiKey) {
      showError('explain-error', '请先在上方填入 API Key 并点「保存到本机」, 或直接看演示样例。');
      button.disabled = false;
      button.textContent = '生成讲解';
      return;
    }
    loadTemplate().then(function (template) {
      var prompt = buildPrompt(template, text, style);
      return callModelDirect(baseInput, apiKey, modelInput, protocol, prompt);
    }).then(function (data) {
      var markdown = extractContent(data, protocol).trim();
      if (!markdown) { throw new Error('模型返回了空内容'); }
      var usage = extractUsage(data, protocol);
      showResult(text.split('\n')[0].slice(0, 60) || '讲解', markdown,
        '来源: 粘贴题面 (浏览器直连)' +
        '　模型: ' + (modelInput || '-') +
        '　tokens: 输入 ' + (usage.input == null ? '-' : usage.input) +
        ' / 输出 ' + (usage.output == null ? '-' : usage.output));
    }).catch(function (err) {
      showError('explain-error', '讲解失败: ' + err.message);
    }).then(function () {
      button.disabled = false;
      button.textContent = '生成讲解';
    });
    return undefined;
  }

  function doDemo() {
    clearError('explain-error');
    fetch('sample-explanation.json').then(function (resp) {
      if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
      return resp.json();
    }).then(function (data) {
      showResult(data.title || '演示样例', data.markdown || '',
        (data.meta || '演示样例') + '　注意: 这是预先生成的样例, 不是实时调用');
    }).catch(function (err) {
      showError('explain-error', '演示样例读取失败: ' + err.message);
    });
  }

  function doSaveKey() {
    var key = byId('key-input').value.trim();
    if (!key) {
      showError('explain-error', '请先填入 API Key。');
      return;
    }
    var ok = saveByok({
      api_key: key,
      base_url: byId('base-input').value.trim(),
      model: byId('model-input').value.trim(),
      protocol: byId('protocol-select').value.trim() || 'anthropic',
      provider: currentProvider
    });
    if (!ok) {
      showError('explain-error', '保存失败: 浏览器拒绝写入 localStorage。');
      return;
    }
    clearError('explain-error');
    refreshKeyState();
  }

  function doClearKey() {
    clearByok();
    byId('key-input').value = '';
    refreshKeyState();
  }

  function doCopy() {
    if (!currentMarkdown) { return; }
    copyText(currentMarkdown).then(function () {
      var button = byId('copy-btn');
      var old = button.textContent;
      button.textContent = '已复制';
      setTimeout(function () { button.textContent = old; }, 1500);
    }).catch(function () {
      showError('explain-error', '复制失败, 请手动选中讲解内容复制。');
    });
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try {
        var ok = document.execCommand('copy');
        document.body.removeChild(area);
        if (ok) { resolve(); } else { reject(new Error('execCommand 失败')); }
      } catch (err) {
        document.body.removeChild(area);
        reject(err);
      }
    });
  }

  function doDownload() {
    if (!currentMarkdown) { return; }
    var name = (currentTitle || '讲解').replace(/[\\/:*?"<>|]/g, '_').slice(0, 40);
    var blob = new Blob([currentMarkdown], { type: 'text/markdown;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = name + '.md';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /* --------------------------------------------------------------
   * 每日打卡 (仅本机代理模式可用)
   * -------------------------------------------------------------- */
  function doPunch() {
    if (currentMode !== MODE.LOCAL) {
      showError('punch-error', '静态站没有后端代理, 打卡请用命令行工具: python luogu_punch.py');
      return;
    }
    clearError('punch-error');
    var button = byId('punch-btn');
    button.disabled = true;
    button.textContent = '打卡中……';
    fetchJson('/api/punch', { method: 'POST' }, 60000).then(function (data) {
      var box = byId('punch-result');
      box.hidden = false;
      var ok = byId('punch-ok');
      ok.textContent = data.ok ? '成功' : '失败';
      ok.className = 'result-val ' + (data.ok ? '' : 'is-bad');
      byId('punch-code').textContent =
        (data.code === null || data.code === undefined) ? '-' : String(data.code);
      byId('punch-message').textContent = data.message || '';
      byId('punch-elapsed').textContent = (data.elapsed_ms || 0) + ' ms';
      if (!data.ok) { showError('punch-error', data.message || '打卡失败'); }
    }).catch(function (err) {
      showError('punch-error', '打卡请求失败: ' + err.message);
    }).then(function () {
      button.disabled = false;
      button.textContent = '立即打卡';
    });
  }

  /* --------------------------------------------------------------
   * 标签页与启动
   * -------------------------------------------------------------- */
  function initTabs() {
    var tabs = document.querySelectorAll('.tab');
    Array.prototype.forEach.call(tabs, function (tab) {
      tab.addEventListener('click', function () {
        Array.prototype.forEach.call(tabs, function (other) {
          var isActive = other === tab;
          other.classList.toggle('is-active', isActive);
          other.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        var panels = document.querySelectorAll('.panel');
        Array.prototype.forEach.call(panels, function (panel) {
          panel.classList.toggle('is-active', panel.id === tab.dataset.panel);
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initExplain();
    byId('punch-btn').addEventListener('click', doPunch);
    detectMode().then(applyMode).catch(function (err) {
      var meta = byId('header-meta');
      if (meta) { meta.textContent = '模式检测失败: ' + err.message; }
    });
    loadProviders().then(function () {
      renderProviderOptions();
      renderDirectList();
    }).catch(function (err) {
      var select = byId('provider-select');
      if (select) {
        select.disabled = true;
        select.title = '模型预设表读取失败: ' + err.message;
      }
      if (window.console && window.console.error) { window.console.error('[providers] 预设表读取失败', err); }
    });
  });
})();
