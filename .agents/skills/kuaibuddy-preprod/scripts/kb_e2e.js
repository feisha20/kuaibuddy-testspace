#!/usr/bin/env node
'use strict';
/**
 * KuaiBuddy 预生产环境 E2E 工具：登录 + 发起对话 + 回读会话。
 *
 * 纯 Node 内置模块实现（crypto + fetch），无第三方依赖。
 * 登录密码按前端同款算法加密（md5 + AES-256-GCM），算法见 SKILL.md「登录密码加密」小节。
 *
 * 子命令：
 *   login                     仅登录，打印账号信息（不含密码/令牌明文）
 *   ask "<问题>"              登录 + 发起一轮对话，打印最终回复
 *   ask --file prompt.txt     从文件读取问题
 *   ask --session <id>        在已有会话上继续对话（多轮）
 *   ask --skill <name>        指定技能
 *   ask --agent-id <id>       指定 agent
 *   ask --expect "关键词"     断言回复包含关键词（可多次指定）
 *   ask --not-expect "关键词" 断言回复不包含关键词
 *   ask --out <目录>          保存事件流/回复/请求到目录
 *   batch <cases.jsonl>       批量跑用例，输出逐条断言结果
 *   sessions                  列出最近会话
 *   messages --session <id>   读某个会话的消息
 *   agents                    列出可用 agent
 *   skills                    列出可用技能
 *
 * 通用参数：
 *   --url <地址>              覆盖默认环境地址
 *   --timeout <秒>            单轮对话超时，默认 300
 *   --verbose                 打印 SSE 事件明细
 *   --json                    以 JSON 输出
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const DEFAULT_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36';
const WORKSPACE_ROOT = path.resolve(__dirname, '../../../..');
const CACHE_DIR = path.join(WORKSPACE_ROOT, '.runtime', 'cache', 'kuaibuddy-preprod');
const CACHE_FILE = path.join(CACHE_DIR, 'token.json');

/* ------------------------------------------------------------------ 工具函数 */

function die(msg, code = 1) {
  console.error(`[kb_e2e] ${msg}`);
  process.exit(code);
}

function md5(s) {
  return crypto.createHash('md5').update(s, 'utf8').digest('hex');
}

/** 在 buf 的 index 处插入 extra，返回新 Buffer */
function insertAt(buf, extra, index) {
  const out = Buffer.alloc(buf.length + extra.length);
  buf.copy(out, 0, 0, index);
  extra.copy(out, index);
  buf.copy(out, index + extra.length, index);
  return out;
}

function parseArgs(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      if (key === 'verbose' || key === 'json' || key === 'help') {
        flags[key] = true;
      } else {
        const next = argv[i + 1];
        if (next === undefined || next.startsWith('--')) flags[key] = true;
        else { flags[key] = next; i++; }
      }
    } else {
      positional.push(a);
    }
  }
  return { positional, flags };
}

/* ------------------------------------------------------------ 配置与凭据 */

/**
 * 读取指定的预生产配置文件，按注释块与平面键值解析。
 */
function parseEnvFile(file) {
  let raw;
  try {
    raw = fs.readFileSync(file, 'utf8');
  } catch {
    return { blocks: [], flat: {} };
  }
  const blocks = [];
  const flat = {};
  let comment = '';
  let current = null;
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith('#')) {
      comment = trimmed.replace(/^#+\s*/, '');
      current = { comment, vars: {} };
      blocks.push(current);
      continue;
    }
    const eq = trimmed.indexOf('=');
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (/^".*"$|^'.*'$/.test(value)) value = value.slice(1, -1);
    flat[key] = value;
    if (!current) { current = { comment: '', vars: {} }; blocks.push(current); }
    current.vars[key] = value;
  }
  return { blocks, flat };
}

function envFileCandidates() {
  return [process.env.KB_ENV_FILE || path.join(WORKSPACE_ROOT, '.env.preprod')];
}

function resolveConfig(flags) {
  let parsed = { blocks: [], flat: {} };
  let envFile = '';
  for (const f of envFileCandidates()) {
    if (!fs.existsSync(f)) continue;
    const p = parseEnvFile(f);
    const hasKb = p.blocks.some((b) => b.vars.companyid && b.vars.url) || (p.flat.companyid && p.flat.url);
    if (!hasKb && parsed.blocks.length === 0) continue; // 优先挑含预生产配置的 .env
    parsed = p;
    envFile = f;
    if (hasKb) break;
  }
  const preprod =
    parsed.blocks.find((b) => b.vars.companyid && b.vars.url && !b.vars.username) ||
    parsed.blocks.find((b) => b.vars.companyid && b.vars.url) ||
    { vars: parsed.flat };

  const v = preprod.vars || {};
  const rawUrl = flags.url || process.env.KB_URL || v.url || v.kb_url || '';
  // .env 里记的是前端页面地址（如 .../work/chat），API 挂在站点根路径，取 origin 即可
  let baseUrl = '';
  if (rawUrl) {
    try { baseUrl = new URL(rawUrl).origin; } catch { baseUrl = rawUrl.replace(/\/+$/, ''); }
  }
  const cfg = {
    baseUrl,
    companyId: process.env.KB_COMPANY_ID || v.companyid || v.kb_company_id || '',
    username: process.env.KB_USERNAME || v.usrname || v.kb_username || v.username || '',
    password: process.env.KB_PASSWORD || v.kb_password || v.password || '',
    ua: process.env.KB_UA || DEFAULT_UA,
    envFile,
  };
  if (!cfg.baseUrl) die('缺少环境地址：请设置 KB_URL 或在工作区 .env 中配置 url');
  if (!cfg.companyId) die('缺少公司 ID：请设置 KB_COMPANY_ID 或在 .env 中配置 companyid');
  if (!cfg.username) die('缺少登录名：请设置 KB_USERNAME 或在 .env 中配置 usrname');
  return cfg;
}

/* ---------------------------------------------------- 登录密码加密（同前端） */

/**
 * 前端算法（web-agent 前端 bundle）：
 *   key        = md5(userAgent + lt + companyId + md5(username))
 *   nonce      = 12 字节随机
 *   plaintext  = md5(password) + '§' + username
 *   ciphertext = AES-256-GCM(key, nonce, plaintext)  // 密文后跟 16 字节 tag
 *   插值       = 把 nonce 插到密文索引 l，把 8 字节大端 timestamp 插到索引 s
 *                i = lt[last] & (255 % len), a = lt[last-1] & (255 % len)
 *                s = min(i,a), l = max(i,a)
 *   password   = base64(插值后的字节)
 */
function encryptPassword({ password, companyId, username, ua, lt, timestamp }) {
  const key = md5(`${ua}${lt}${companyId}${md5(username)}`);
  const nonce = crypto.randomBytes(12);
  const plain = Buffer.from(md5(password) + '§' + username, 'utf8');
  const cipher = crypto.createCipheriv('aes-256-gcm', Buffer.from(key, 'utf8'), nonce);
  const ct = Buffer.concat([cipher.update(plain), cipher.final(), cipher.getAuthTag()]);

  const ts = Buffer.alloc(8);
  ts.writeBigUInt64BE(BigInt(timestamp));
  const mod = 255 % ct.length;
  const i = lt.charCodeAt(lt.length - 1) & mod;
  const a = lt.charCodeAt(lt.length - 2) & mod;
  return insertAt(insertAt(ct, nonce, Math.max(i, a)), ts, Math.min(i, a)).toString('base64');
}

/* ------------------------------------------------------------------ 登录 */

async function apiPostForm(baseUrl, urlPath, fields, ua) {
  const res = await fetch(`${baseUrl}${urlPath}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': ua,
      Accept: 'application/json, text/plain, */*',
    },
    body: new URLSearchParams(fields),
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = { code: -1, msg: text.slice(0, 300) }; }
  return { status: res.status, json };
}

async function login(cfg, { force = false } = {}) {
  if (!cfg.password) die('缺少密码：请设置 KB_PASSWORD 或在 .env 中配置 password');

  if (!force) {
    const cached = readTokenCache(cfg);
    if (cached) return cached;
  }

  const ltRes = await apiPostForm(cfg.baseUrl, '/web/agent/auth/lt', {
    cid: cfg.companyId,
    ln: md5(cfg.username),
    tt: 'pc',
    isIOS: '1',
    isWebCs: 'true',
  }, cfg.ua);
  if (ltRes.json.code !== 8 || !ltRes.json.data || !ltRes.json.data.lt) {
    die(`获取登录票据失败：${JSON.stringify(ltRes.json)}`);
  }
  const lt = ltRes.json.data.lt;
  const timestamp = ltRes.json.data.timestamp;

  const loginRes = await apiPostForm(cfg.baseUrl, '/web/agent/auth/login', {
    compId: cfg.companyId,
    loginName: md5(cfg.username),
    bindEmail: '',
    mobileVerifyCode: '',
    bindPhone: '',
    password: encryptPassword({
      password: cfg.password,
      companyId: cfg.companyId,
      username: cfg.username,
      ua: cfg.ua,
      lt,
      timestamp,
    }),
    customerMac: cfg.ua,
    dynamicNumber: '',
    verifyCode: '',
    curVersion: '9.64.10',
    csVersion: '9.64.10',
    os: 'Darwin',
    terminalType: 'pc',
    isIOS: '1',
    isWebCs: 'true',
  }, cfg.ua);

  if (loginRes.json.code !== 8 || !loginRes.json.data || !loginRes.json.data.accessToken) {
    const msg = loginRes.json.msg || '';
    const hint = loginRes.json.code === 1200 ? '（用户名或密码错误，或密码加密与前端不一致）' : '';
    die(`登录失败 code=${loginRes.json.code} msg=${msg}${hint}`);
  }
  const data = loginRes.json.data;
  const token = {
    accessToken: data.accessToken,
    refreshToken: data.refreshToken,
    expiresAt: Date.now() + (data.expiresIn || 86400) * 1000,
    userInfo: data.userInfo || {},
    baseUrl: cfg.baseUrl,
    companyId: cfg.companyId,
    username: cfg.username,
  };
  writeTokenCache(token);
  return token;
}

function readTokenCache(cfg) {
  try {
    const cached = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
    if (cached.baseUrl !== cfg.baseUrl || cached.companyId !== cfg.companyId || cached.username !== cfg.username) return null;
    if (!cached.accessToken || cached.expiresAt < Date.now() + 60_000) return null;
    return cached;
  } catch {
    return null;
  }
}

function writeTokenCache(token) {
  try {
    fs.mkdirSync(CACHE_DIR, { recursive: true });
    fs.writeFileSync(CACHE_FILE, JSON.stringify(token, null, 2), { mode: 0o600 });
  } catch {
    /* 缓存失败不影响使用 */
  }
}

async function apiPostJson(cfg, token, urlPath, payload) {
  const res = await fetch(`${cfg.baseUrl}${urlPath}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/plain, */*',
      Authorization: `Bearer ${token.accessToken}`,
      'User-Agent': cfg.ua,
    },
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  try { return JSON.parse(text); } catch { return { code: -1, msg: text.slice(0, 300) }; }
}

/* ------------------------------------------------------------------ 对话 */

/**
 * 发起一轮对话，SSE 事件流解析。
 * 返回 { threadId, runId, answer, reasoning, events, finished, error, elapsedMs }
 */
async function chat(cfg, token, { prompt, threadId, runId, skill, agentId, title, timeoutSec = 300, verbose = false }) {
  const thread = threadId || `thread_${crypto.randomUUID()}`;
  const run = runId || crypto.randomUUID();
  const payload = {
    threadId: thread,
    runId: run,
    message: { role: 'user', content: [{ type: 'text', text: prompt }] },
  };
  if (skill) payload.skillNames = [].concat(skill);
  if (agentId) payload.agentId = agentId;
  if (title) payload.title = title;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutSec * 1000);
  const startedAtMs = Date.now();
  const startedAt = new Date(startedAtMs).toISOString();

  let answer = '';
  let reasoning = '';
  const events = [];
  let serverThreadId = thread;
  let serverRunId = run;
  let finished = false;
  let error = null;

  try {
    const res = await fetch(`${cfg.baseUrl}/service/agent/api/v1/agent/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${token.accessToken}`,
        'User-Agent': cfg.ua,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) {
      const body = await res.text().catch(() => '');
      throw new Error(`对话接口返回 HTTP ${res.status}：${body.slice(0, 300)}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (!raw) continue;
        let ev;
        try { ev = JSON.parse(raw); } catch { continue; }
        events.push(ev);
        if (verbose) console.error(`[sse] ${raw.slice(0, 400)}`);
        if (ev.threadId) serverThreadId = ev.threadId;
        if (ev.runId) serverRunId = ev.runId;
        if (ev.type === 'TEXT_MESSAGE_CONTENT' && typeof ev.delta === 'string') answer += ev.delta;
        if (ev.type === 'REASONING_MESSAGE_CONTENT' && typeof ev.delta === 'string') reasoning += ev.delta;
        if (ev.type === 'RUN_FINISHED') finished = true;
        if (ev.type === 'RUN_FAILED' || ev.type === 'ERROR') {
          finished = true;
          error = ev.error || ev.message || ev.reason || JSON.stringify(ev).slice(0, 500);
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') error = `对话超时（${timeoutSec}s）`;
    else error = err.message;
  } finally {
    clearTimeout(timer);
  }

  return {
    threadId: serverThreadId,
    runId: serverRunId,
    answer,
    reasoning,
    events,
    finished,
    error,
    request: payload,
    startedAt,
    finishedAt: new Date().toISOString(),
    elapsedMs: Date.now() - startedAtMs,
  };
}

function assertExpectations(answer, { expect = [], notExpect = [] }) {
  const failures = [];
  for (const kw of expect) {
    if (!answer.includes(kw)) failures.push(`期望包含「${kw}」但未命中`);
  }
  for (const kw of notExpect) {
    if (answer.includes(kw)) failures.push(`期望不包含「${kw}」但命中`);
  }
  return failures;
}

function saveArtifacts(outDir, result, extra = {}) {
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'request.json'), JSON.stringify(result.request, null, 2));
  fs.writeFileSync(path.join(outDir, 'answer.txt'), result.answer || '');
  fs.writeFileSync(
    path.join(outDir, 'events.json'),
    JSON.stringify({ threadId: result.threadId, runId: result.runId, events: result.events }, null, 2),
  );
  fs.writeFileSync(
    path.join(outDir, 'result.json'),
    JSON.stringify({ ...result, events: undefined, ...extra }, null, 2),
  );
  return outDir;
}

/* -------------------------------------------------------------- 子命令实现 */

async function cmdLogin(cfg, flags) {
  const token = await login(cfg, { force: !!flags.force });
  const out = {
    ok: true,
    baseUrl: cfg.baseUrl,
    username: cfg.username,
    companyId: cfg.companyId,
    loginName: token.userInfo && token.userInfo.loginName,
    nickName: token.userInfo && token.userInfo.nickName,
    roleName: token.userInfo && token.userInfo.roleName,
    userId: token.userInfo && token.userInfo.userId,
    expiresAt: new Date(token.expiresAt).toISOString(),
  };
  console.log(flags.json ? JSON.stringify(out, null, 2) : formatLogin(out));
  return out;
}

function formatLogin(o) {
  return [
    `登录成功：${o.loginName || o.username}${o.nickName ? `（${o.nickName}）` : ''}`,
    `环境：${o.baseUrl}`,
    `公司 ID：${o.companyId}`,
    o.roleName ? `角色：${o.roleName}` : null,
    `令牌有效期至：${o.expiresAt}`,
  ].filter(Boolean).join('\n');
}

async function cmdAsk(cfg, flags, positional) {
  let prompt = positional.join(' ').trim();
  if (flags.file) prompt = fs.readFileSync(flags.file, 'utf8').trim();
  if (!prompt) die('缺少问题内容：用 ask "问题" 或 ask --file <文件>');

  const token = await login(cfg);
  const result = await chat(cfg, token, {
    prompt,
    threadId: flags.session,
    skill: flags.skill,
    agentId: flags['agent-id'],
    title: flags.title,
    timeoutSec: Number(flags.timeout || 300),
    verbose: !!flags.verbose,
  });

  const expect = [].concat(flags.expect || []);
  const notExpect = [].concat(flags['not-expect'] || []);
  const failures = assertExpectations(result.answer, { expect, notExpect });
  const ok = result.finished && !result.error && failures.length === 0;

  const out = {
    ok,
    threadId: result.threadId,
    runId: result.runId,
    answer: result.answer,
    error: result.error,
    failures,
    startedAt: result.startedAt,
    finishedAt: result.finishedAt,
    elapsedMs: result.elapsedMs,
  };
  if (flags.out) out.artifacts = saveArtifacts(flags.out, result, { ok, failures });

  if (flags.json) {
    console.log(JSON.stringify(out, null, 2));
  } else {
    console.log(result.answer || '(无回复)');
    if (result.error) console.error(`[错误] ${result.error}`);
    if (failures.length) console.error(`[断言失败] ${failures.join('；')}`);
    console.error(`\n[threadId] ${result.threadId}  [耗时] ${(result.elapsedMs / 1000).toFixed(1)}s`);
    if (flags.out) console.error(`[产物] ${out.artifacts}`);
  }
  if (!ok) process.exitCode = 2;
  return out;
}

/** 目录名清洗：保留中文、字母、数字、下划线、连字符、点 */
function safeDirName(name) {
  const cleaned = String(name).replace(/[^\w.\-一-鿿]/g, '_').replace(/^\.+/, '_');
  return cleaned.slice(0, 80) || 'case';
}

async function cmdBatch(cfg, flags, positional) {
  const file = positional[0];
  if (!file) die('缺少用例文件：batch <cases.jsonl>');
  const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/).filter((l) => l.trim() && !l.trim().startsWith('//'));
  const cases = lines.map((l, idx) => {
    try {
      const c = JSON.parse(l);
      c.name = c.name || `case-${idx + 1}`;
      return c;
    } catch (e) {
      die(`第 ${idx + 1} 行不是合法 JSON：${e.message}`);
    }
  });

  const outDir = flags.out || path.join(process.cwd(), 'kb-batch-' + Date.now());
  fs.mkdirSync(outDir, { recursive: true });
  const token = await login(cfg);
  const results = [];

  for (const c of cases) {
    const startedAt = Date.now();
    const result = await chat(cfg, token, {
      prompt: c.prompt,
      threadId: c.session,
      skill: c.skill,
      agentId: c.agentId,
      title: c.title || c.name,
      timeoutSec: Number(flags.timeout || c.timeout || 300),
      verbose: !!flags.verbose,
    });
    const failures = assertExpectations(result.answer, {
      expect: c.expect || [],
      notExpect: c.notExpect || [],
    });
    const ok = result.finished && !result.error && failures.length === 0;
    const item = {
      name: c.name,
      ok,
      threadId: result.threadId,
      answer: result.answer,
      error: result.error,
      failures,
      elapsedMs: Date.now() - startedAt,
    };
    saveArtifacts(path.join(outDir, safeDirName(c.name)), result, { name: c.name, ok, failures });
    results.push(item);
    console.error(`[${ok ? 'PASS' : 'FAIL'}] ${c.name} (${item.elapsedMs}ms)`);
  }

  const summary = {
    total: results.length,
    passed: results.filter((r) => r.ok).length,
    failed: results.filter((r) => !r.ok).length,
    results,
  };
  fs.writeFileSync(path.join(outDir, 'summary.json'), JSON.stringify(summary, null, 2));
  fs.writeFileSync(
    path.join(outDir, 'summary.csv'),
    ['name,ok,threadId,elapsedMs,failures,answer',
      ...results.map((r) => [r.name, r.ok, r.threadId, r.elapsedMs,
        `"${String(r.failures.join('；')).replace(/"/g, '""')}"`,
        `"${String(r.answer || '').replace(/"/g, '""').replace(/\n/g, ' ')}"`].join(','))].join('\n'),
  );
  if (flags.json) console.log(JSON.stringify(summary, null, 2));
  else {
    console.log(`共 ${summary.total} 条，通过 ${summary.passed}，失败 ${summary.failed}`);
    console.log(`产物目录：${outDir}`);
  }
  if (summary.failed > 0) process.exitCode = 2;
  return summary;
}

async function cmdSessions(cfg, flags) {
  const token = await login(cfg);
  const res = await apiPostJson(cfg, token, '/web/agent/api/v1/sessions/list', {
    curPage: Number(flags.page || 1),
    pageSize: Number(flags['page-size'] || 20),
  });
  if (res.code !== 8) die(`列会话失败：${JSON.stringify(res)}`);
  const list = (res.data && res.data.resultlist) || [];
  if (flags.json) { console.log(JSON.stringify(list, null, 2)); return list; }
  for (const s of list) {
    console.log(`${s.sessionId}\t${s.status}\t${s.title || ''}\t${s.createdAt || ''}`);
  }
  return list;
}

async function cmdMessages(cfg, flags) {
  if (!flags.session) die('缺少 --session <sessionId>');
  const token = await login(cfg);
  const res = await apiPostJson(cfg, token, '/web/agent/api/v1/messages/list', {
    sessionId: flags.session,
    limit: Number(flags.limit || 50),
  });
  if (res.code !== 8) die(`读消息失败：${JSON.stringify(res)}`);
  const data = res.data || {};
  const list = Array.isArray(data) ? data : data.messages || [];
  if (flags.json) { console.log(JSON.stringify(list, null, 2)); return list; }
  for (const m of list) {
    console.log(`[${m.role}] ${formatMessageContent(m.content)}`);
  }
  return list;
}

/** 消息正文是 JSON 字符串（形如 [{"type":"text","text":"..."}]），取文本部分 */
function formatMessageContent(content) {
  if (content == null) return '';
  if (typeof content !== 'string') return JSON.stringify(content);
  try {
    const parsed = JSON.parse(content);
    if (Array.isArray(parsed)) {
      return parsed.map((p) => (p && p.text) || JSON.stringify(p)).join('\n');
    }
    if (parsed && typeof parsed === 'object' && parsed.text) return parsed.text;
    return JSON.stringify(parsed);
  } catch {
    return content;
  }
}

// 单个辅助接口的业务失败只表示该接口失败，不推断对话接口不可用。
function requireApiSuccess(res, label) {
  if (!res || res.code !== 8) {
    const code = res && res.code != null ? String(res.code) : '无';
    throw new Error(`${label}失败：业务码 ${code}`);
  }
  return res;
}

async function cmdAgents(cfg, flags) {
  const token = await login(cfg);
  const res = await apiPostJson(cfg, token, '/web/agent/api/v1/agent/user/list', {});
  requireApiSuccess(res, '查询 Agent 列表');
  if (flags.json) { console.log(JSON.stringify(res, null, 2)); return res; }
  console.log(JSON.stringify(res.data || [], null, 2));
  return res;
}

async function cmdSkills(cfg, flags) {
  const token = await login(cfg);
  const res = await apiPostJson(cfg, token, '/web/agent/api/v1/skill/user/list', {});
  requireApiSuccess(res, '查询 Skill 列表');
  if (flags.json) { console.log(JSON.stringify(res, null, 2)); return res; }
  console.log(JSON.stringify(res.data || [], null, 2));
  return res;
}

/* ------------------------------------------------------------------ 入口 */

const USAGE = `用法：kb_e2e.js <子命令> [参数]

  login                              登录并打印账号信息
  ask "<问题>"                       登录 + 发起对话
  ask --file <文件>                  从文件读取问题
  ask --session <sessionId>          在已有会话上继续对话
  ask --skill <名称>                 指定技能
  ask --agent-id <id>                指定 agent
  ask --expect "关键词"              断言回复包含关键词（可重复）
  ask --not-expect "关键词"          断言回复不包含关键词（可重复）
  ask --out <目录>                   保存产物
  batch <cases.jsonl> [--out <目录>] 批量执行用例
  sessions [--page N] [--page-size N] 列出最近会话
  messages --session <sessionId>    读取会话消息
  agents                            列出可用 agent
  skills                            列出可用技能

通用：--url <地址> --timeout <秒> --verbose --json
`;

async function main() {
  const { positional, flags } = parseArgs(process.argv.slice(2));
  const cmd = positional.shift();
  if (!cmd || flags.help) { console.log(USAGE); process.exit(flags.help ? 0 : 1); }

  const cfg = resolveConfig(flags);
  switch (cmd) {
    case 'login': return cmdLogin(cfg, flags);
    case 'ask': return cmdAsk(cfg, flags, positional);
    case 'batch': return cmdBatch(cfg, flags, positional);
    case 'sessions': return cmdSessions(cfg, flags);
    case 'messages': return cmdMessages(cfg, flags);
    case 'agents': return cmdAgents(cfg, flags);
    case 'skills': return cmdSkills(cfg, flags);
    default:
      console.error(`未知子命令：${cmd}\n`);
      console.log(USAGE);
      process.exit(1);
  }
}

if (require.main === module) {
  main().catch((err) => {
    die(err && err.message ? err.message : String(err));
  });
}

module.exports = { chat, requireApiSuccess };
