'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { chat, requireApiSuccess } = require('../scripts/kb_e2e.js');

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
