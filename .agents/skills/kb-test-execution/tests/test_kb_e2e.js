'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chat, requireApiSuccess, resolveConfig } = require('../scripts/kb_e2e.js');

test('辅助接口返回业务错误时不当作成功，也不输出服务正文', () => {
  assert.throws(() => requireApiSuccess({ code: 9001, msg: '可能含敏感数据' }, '查询 Agent 列表'),
    (error) => error.message === '查询 Agent 列表失败：业务码 9001');
  assert.throws(() => requireApiSuccess(null, '查询 Skill 列表'), /业务码 无/);
  assert.deepEqual(requireApiSuccess({ code: 8, data: [] }, '查询 Agent 列表').data, []);
});

test('单轮请求记录实际 UTC 起止时间及正常终态', async () => {
  const original = global.fetch;
  const encoder = new TextEncoder();
  global.fetch = async () => ({ ok: true, body: new ReadableStream({ start(c) {
    c.enqueue(encoder.encode('data: {"type":"TEXT_MESSAGE_CONTENT","delta":"13"}\n' +
      'data: {"type":"RUN_FINISHED","threadId":"thread-test","runId":"run-test"}\n'));
    c.close();
  } }) });
  try {
    const before = Date.now();
    const value = await chat({ baseUrl: 'http://127.0.0.1', ua: 'test' }, { accessToken: 'fake' }, { prompt: '8+5' });
    const after = Date.now();
    assert.equal(value.answer, '13'); assert.equal(value.finished, true); assert.equal(value.error, null);
    assert.ok(Date.parse(value.startedAt) >= before && Date.parse(value.finishedAt) <= after);
    assert.ok(Date.parse(value.finishedAt) >= Date.parse(value.startedAt));
    assert.match(value.startedAt, /Z$/); assert.match(value.finishedAt, /Z$/);
  } finally { global.fetch = original; }
});

test('对话失败时仍记录起止时间且不标记正常完成', async () => {
  const original = global.fetch; global.fetch = async () => { throw new Error('模拟网络错误'); };
  try {
    const value = await chat({ baseUrl: 'http://127.0.0.1', ua: 'test' }, { accessToken: 'fake' }, { prompt: '8+5' });
    assert.equal(value.finished, false); assert.equal(value.error, '模拟网络错误');
    assert.ok(Date.parse(value.finishedAt) >= Date.parse(value.startedAt));
  } finally { global.fetch = original; }
});

test('三套环境分别从指定文件读取，站点使用 URL 的 origin', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-config-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  for (const env of ['test', 'preprod', 'prod']) {
    const file = path.join(dir, `.env.${env}`);
    const origin = `https://${env}.example.invalid`;
    fs.writeFileSync(file, [
      '# 本地单测使用的模拟配置',
      `url=${origin}/work/chat`,
      `companyid=company-${env}`,
      `usrname=user-${env}`,
      'password=dummy',
    ].join('\n'));
    const config = resolveConfig({}, { KB_ENV_FILE: file });
    assert.equal(config.baseUrl, origin);
    assert.equal(config.companyId, `company-${env}`);
    assert.equal(config.username, `user-${env}`);
  }
});

test('缺少环境、文件无法读取或配置冲突时在请求前失败', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-config-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, '.env.test');
  assert.throws(() => resolveConfig({}, {}), /未明确配置目标环境/);
  assert.throws(() => resolveConfig({}, { KB_ENV_FILE: file }), /无法读取/);
  assert.throws(
    () => resolveConfig({}, { KB_ENV_FILE: file, KB_URL: 'https://prod.example.invalid' }),
    /配置冲突/,
  );
  assert.throws(
    () => resolveConfig({ url: 'https://prod.example.invalid' }, { KB_ENV_FILE: file }),
    /配置冲突/,
  );
  fs.writeFileSync(file, 'url=https://test.example.invalid');
  assert.throws(() => resolveConfig({}, { KB_ENV_FILE: file }), /环境文件缺少登录所需字段/);
});

test('直接配置保留独立账号调用方式，拒绝不完整或无效的地址', () => {
  const env = {
    KB_URL: 'https://preprod.example.invalid',
    KB_COMPANY_ID: 'company-fixture',
    KB_USERNAME: 'control-fixture',
    KB_PASSWORD: 'dummy',
  };
  assert.equal(resolveConfig({}, env).username, env.KB_USERNAME);
  assert.equal(resolveConfig({ url: 'https://override.example.invalid' }, env).baseUrl,
    'https://override.example.invalid');
  assert.throws(() => resolveConfig({}, { ...env, KB_PASSWORD: '' }), /未明确配置目标环境/);
  assert.throws(() => resolveConfig({}, { ...env, KB_URL: 'file:///tmp' }), /须使用 HTTP 或 HTTPS/);
});
