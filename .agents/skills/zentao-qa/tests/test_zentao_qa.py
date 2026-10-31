"""使用合成数据验证读写边界，不连接公司禅道。"""

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'zentao_qa.py'
SPEC = importlib.util.spec_from_file_location('zentao_qa', SCRIPT)
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


def case_op(key='story-10-v2-case-1'):
    return {'key': key, 'action': 'case.create', 'expected': {'storyVersion': 2},
            'data': {'productID': 1, 'story': 10, 'title': '校验手机号',
                     'steps': ['输入错误手机号'], 'expects': ['拒绝提交']}}


def result_op(key='batch-1-case-20'):
    return {'key': key, 'action': 'result.submit', 'data': {
        'caseId': 20, 'caseVersion': 1, 'testtaskId': 30, 'result': 'fail',
        'evidence': ['artifacts/result.json'],
        'startedAt': '2026-10-19T10:00:00+08:00',
        'finishedAt': '2026-10-19T10:00:01+08:00',
        'steps': [{'stepId': 50, 'result': 'fail', 'actual': '错误地允许提交'}]}}


def plan(*ops):
    return {'schemaVersion': 1, 'operations': list(ops)}


class FakeClient:
    url = 'https://example.invalid/zentao'

    def __init__(self):
        self.writes = []
        self.objects = {}
        self.results = []
        self.story_version = 2
        self.linked = True
        self.verify_fail = False
        self.write_fail = False
        self.review_required = False
        self.review_write_fail = False
        self.review_verify_fail = False
        self.bug = {'id': 40, 'title': '原Bug', 'lastEditedDate': '2026-10-19 10:00:00'}

    def detail(self, kind, oid):
        if kind == 'story':
            return {'id': oid, 'product': 1, 'version': self.story_version}
        if kind == 'execution':
            return {'id': oid, 'project': 2}
        if kind == 'bug' and oid == 40:
            return dict(self.bug)
        if kind == 'case' and oid == 20:
            return {'id': 20, 'product': 1, 'version': 1,
                    'steps': [{'id': 50, 'type': 'step', 'desc': '操作', 'expect': '预期'}]}
        if self.verify_fail:
            raise qa.QAError('NETWORK_ERROR', '模拟回读失败')
        return self.objects[(kind, oid)]

    def testtask(self, oid):
        return {'id': oid, 'product': 1, 'testcases': [{'id': 60, 'case': 20, 'version': 1}] if self.linked else []}

    def history(self, oid, run_id=0):
        return self.results

    def listing(self, path, key, all_pages=False, page=1, size=100):
        return {'items': [{'id': 10}], 'complete': True}

    def request(self, method, path, data=None, params=None, version=2, auth=True):
        if method == 'GET':
            if path.endswith('/review'):
                return {'status': 'success', 'testcaseID': int(path.split('/')[2]), 'actions': []}
            if path.startswith('/testcases/'):
                return {'status': 'success', 'testcase': self.detail('case', int(path.split('/')[2])), 'actions': []}
            return {'status': 'success', 'stories': [{'id': 10}], 'pager': {'pageTotal': 1}}
        self.writes.append((method, path, copy.deepcopy(data), params, version))
        if self.write_fail:
            raise qa.QAError('NETWORK_ERROR', '模拟写入超时', uncertain=True)
        if path.startswith('/tasks/') and path.endswith('/start'):
            task = self.objects[('task', int(path.split('/')[2]))]
            task.update(data, status='doing' if data['left'] > 0 else 'done')
            if task.get('parent'):
                self.objects[('task', task['parent'])]['status'] = task['status']
            return {'status': 'success'}
        if path.endswith('/review'):
            if not data.get('reviewedDate'):
                raise qa.QAError('BUSINESS_ERROR', '模拟22.2评审日期校验失败')
            if self.review_write_fail:
                raise qa.QAError('NETWORK_ERROR', '模拟评审提交超时', uncertain=True)
            case = self.objects[('case', int(path.split('/')[2]))]
            case.update(status='normal', reviewedBy=','.join(data['reviewedBy']), reviewedDate=data['reviewedDate'])
            if self.review_verify_fail:
                case['reviewedBy'] = ''
            return {'status': 'success'}
        if version == 1:
            self.results.append({'id': 70, 'run': 60, 'version': 1, 'caseResult': 'fail',
                                 'stepResults': data['steps']})
            return []
        oid = 100 + len(self.writes)
        if path.startswith('/bugs/'):
            # 模拟22.2：未提交的 pri/severity/type 按编辑表单默认值落库。
            stored = dict(data)
            for field, default in (('pri', 3), ('severity', 3), ('type', 'codeerror')):
                stored.setdefault(field, default)
            self.bug.update(stored)
            return {'status': 'success'}
        kind = {'/testcases': 'case', '/bugs': 'bug', '/testtasks': 'testtask', '/tasks': 'task'}[path]
        value = dict(data, id=oid)
        if 'productID' in value:
            value['product'] = value.pop('productID')
        if 'executionID' in value:
            value['execution'] = value.pop('executionID')
        if kind == 'case':
            value.update(status='wait' if self.review_required else 'normal', version=1, lastEditedDate='')
            if data.get('story'):
                value['storyVersion'] = self.story_version
            value['steps'] = [{'desc': s, 'expect': e} for s, e in zip(data['steps'], data['expects'])]
        if kind == 'task':
            value.update(status='wait', isParent=0)
            if data.get('parent'):
                self.objects[('task', data['parent'])]['isParent'] = 1
        self.objects[(kind, oid)] = value
        return {'status': 'success', 'id': oid}


class ValidationTests(unittest.TestCase):
    def test_用例计划与步骤校验(self):
        qa.validate_operation(case_op())
        op = case_op()
        op['data']['expects'] = []
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)

    def test_禁止未知字段和非测试任务(self):
        op = case_op()
        op['data']['password'] = '不应进入计划'
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)
        with self.assertRaises(qa.QAError):
            qa.validate_operation({'key': 'x', 'action': 'task.create', 'data': {'name': '任务', 'executionID': 1, 'type': 'devel'}})

    def test_需求关联必须锁定版本(self):
        op = case_op()
        del op['expected']
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)

    def test_Bug更新需要修改时间(self):
        with self.assertRaises(qa.QAError):
            qa.validate_operation({'key': 'edit', 'action': 'bug.update', 'targetId': 40, 'data': {'title': '更新'}})

    def test_场景ID不可冒充用例(self):
        self.assertEqual(qa.number_id('case_93'), 93)
        for value in ['scene_93', '0', None, True, '../93']:
            with self.assertRaises(qa.QAError):
                qa.number_id(value)

    def test_结果需要证据和真实时间(self):
        for field, value in [('evidence', []), ('result', 'pass'), ('startedAt', '2026-10-19T10:00:00')]:
            op = result_op()
            op['data'][field] = value
            with self.assertRaises(qa.QAError):
                qa.validate_operation(op)

    def test_模拟结果无需虚构时间但必须显式声明(self):
        op = result_op()
        del op['data']['startedAt'], op['data']['finishedAt']
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)
        op['data']['simulation'] = True
        qa.validate_operation(op)
        op['data']['startedAt'] = '2026-10-19T10:00:00+08:00'
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)
        del op['data']['startedAt']
        op['data']['simulation'] = 'true'
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)

    def test_离线计划不读取配置也不访问网络(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.json'
            path.write_text(json.dumps(plan(case_op())), encoding='utf-8')
            for command in ['plan', 'apply']:
                args = qa.parser().parse_args([command, '--file', str(path)])
                with patch.object(qa, 'configured', side_effect=AssertionError('离线不应读取配置')):
                    self.assertFalse(qa.run(args)['networkAccessed'])

    def test_整批先验证重复key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.json'
            path.write_text(json.dumps(plan(case_op(), case_op())), encoding='utf-8')
            with self.assertRaises(qa.QAError):
                qa.load_plan(path)

    def test_配置文件权限及不保存密码(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            qa.safe_write(path, {'token': '合成Token'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('password', qa.read_json(path))

    def test_更换站点不转发旧Token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            qa.safe_write(path, {'url': 'https://old.invalid', 'account': 'tester', 'token': '合成Token'})
            args = qa.parser().parse_args(['--config', str(path), '--url', 'https://new.invalid', 'doctor'])
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(qa.QAError) as ctx:
                    qa.configured(args)
            self.assertEqual(ctx.exception.code, 'AUTH_SCOPE_MISMATCH')

    def test_续期登录保留代理设置且不输出Token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            qa.safe_write(path, {'url': 'https://old.invalid', 'account': 'tester', 'token': '旧Token', 'noProxy': True})
            args = qa.parser().parse_args(['--config', str(path), 'login'])
            with patch.dict(os.environ, {'ZENTAO_PASSWORD': '合成密码'}, clear=True), patch.object(qa.Client, 'request', return_value={'status': 'success', 'token': '新Token', 'user': {'account': 'tester'}}):
                result = qa.run(args)
            config = qa.read_json(path)
            self.assertTrue(config['noProxy'])
            self.assertEqual(config['token'], '新Token')
            self.assertNotIn('合成密码', json.dumps(config))
            self.assertNotIn('新Token', json.dumps(result))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = qa.Journal(Path(self.tmp.name) / 'journal.sqlite3')
        self.client = FakeClient()

    def tearDown(self):
        self.tmp.cleanup()

    def apply(self, *ops):
        for op in ops:
            qa.validate_operation(op)
        return qa.apply_plan(self.client, plan(*ops), self.journal, '合成账号')

    def test_创建需求关联用例并回读防重(self):
        first = self.apply(case_op())
        self.assertTrue(first['ok'])
        second = self.apply(case_op())
        self.assertEqual(second['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 1)
        self.assertEqual(self.client.writes[0][2]['story'], 10)

    def test_同key不同内容拒绝(self):
        self.apply(case_op())
        op = case_op()
        op['data']['title'] = '新标题'
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(op)
        self.assertEqual(ctx.exception.code, 'KEY_CONFLICT')
        self.assertEqual(len(self.client.writes), 1)

    def test_整批预检需求冲突不写入(self):
        self.client.story_version = 3
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(case_op())
        self.assertEqual(ctx.exception.code, 'CONFLICT')
        self.assertEqual(self.client.writes, [])

    def test_需求未关联冲刺时拒绝写入(self):
        op = case_op()
        op['data']['execution'] = 3
        self.client.listing = lambda *a, **kw: {'items': [], 'complete': True}
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(op)
        self.assertEqual(ctx.exception.code, 'SCOPE_MISMATCH')
        self.assertEqual(self.client.writes, [])

    def test_回读失败后重跑不重发(self):
        self.client.verify_fail = True
        self.assertFalse(self.apply(case_op())['ok'])
        self.client.verify_fail = False
        self.assertTrue(self.apply(case_op())['ok'])
        self.assertEqual(len(self.client.writes), 1)

    def test_写入超时不允许重发(self):
        self.client.write_fail = True
        self.assertFalse(self.apply(case_op())['ok'])
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(case_op())
        self.assertEqual(ctx.exception.code, 'UNCERTAIN_WRITE')
        self.assertEqual(len(self.client.writes), 1)

    def test_部分成功后停止(self):
        original = self.client.request
        def request(*args, **kwargs):
            if len(self.client.writes) == 1:
                self.client.write_fail = True
            return original(*args, **kwargs)
        self.client.request = request
        result = self.apply(case_op('first'), case_op('second'), case_op('third'))
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['completed']), 1)
        self.assertEqual(result['remaining'], ['third'])

    def test_未关联测试单时不写结果(self):
        self.client.linked = False
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(result_op())
        self.assertEqual(ctx.exception.code, 'CASE_NOT_LINKED')
        self.assertFalse(self.client.writes)

    def test_步骤错序时不写结果(self):
        op = result_op()
        op['data']['steps'][0]['stepId'] = 51
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(op)
        self.assertEqual(ctx.exception.code, 'CONFLICT')

    def test_结果使用v1查询参数和逐步实际值(self):
        result = self.apply(result_op())
        self.assertTrue(result['ok'])
        method, path, body, params, version = self.client.writes[0]
        self.assertEqual((method, path, params, version), ('POST', '/testcases/20/results', {'testtask': 30, 'version': 1}, 1))
        self.assertIn('[zentao-qa:batch-1-case-20]', body['steps'][0]['real'])
        self.assertEqual(result['completed'][0]['remote']['id'], 70)

    def test_模拟逐步结果写入实际情况并保存调试标识(self):
        op = result_op('simulation-step-result')
        del op['data']['startedAt'], op['data']['finishedAt']
        op['data']['simulation'] = True
        result = self.apply(op)
        self.assertTrue(result['ok'])
        body = self.client.writes[0][2]
        self.assertEqual(body['steps'][0]['result'], 'fail')
        self.assertIn('错误地允许提交', body['steps'][0]['real'])
        self.assertIn('【调试模拟，非真实产品测试结果】', body['steps'][0]['real'])
        self.assertNotIn('执行时间：', body['steps'][0]['real'])

    def test_模拟标识丢失不能通过核验(self):
        op = result_op('simulation-label-lost')
        del op['data']['startedAt'], op['data']['finishedAt']
        op['data']['simulation'] = True
        old = self.client.history
        def history(*args):
            rows = copy.deepcopy(old(*args))
            for row in rows:
                for step in row['stepResults']:
                    step['real'] = step['real'].replace('【调试模拟，非真实产品测试结果】', '')
            return rows
        self.client.history = history
        result = self.apply(op)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed']['code'], 'VERIFY_FAILED')

    def test_错误测试单的执行结果不能通过核验(self):
        original = self.client.history
        def history(*args):
            rows = original(*args)
            for row in rows:
                row['run'] = 999
            return rows
        self.client.history = history
        result = self.apply(result_op())
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed']['code'], 'VERIFY_FAILED')

    def uncertain_result(self, op):
        qa.submit(self.client, op)
        scope = qa.digest({'url': self.client.url, 'account': '合成账号'})
        with self.journal.locked():
            self.journal.put(scope, op, 'uncertain')

    def test_响应异常但结果已写入时只读恢复账本(self):
        op = result_op('saved-with-bad-response')
        self.uncertain_result(op)
        result = qa.reconcile_result(self.client, plan(op), self.journal, '合成账号', op['key'])
        self.assertTrue(result['ok'])
        self.assertFalse(result['businessDataWritten'])
        self.assertEqual(result['remote']['id'], 70)
        self.assertEqual(self.apply(op)['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 1)

    def test_未找到或重复结果不能解除不确定状态(self):
        op = result_op('uncertain-records')
        self.uncertain_result(op)
        rows = self.client.results[:]
        for results in ([], rows * 2):
            self.client.results = results
            with self.assertRaises(qa.QAError):
                qa.reconcile_result(self.client, plan(op), self.journal, '合成账号', op['key'])
            with self.assertRaises(qa.QAError) as ctx:
                self.apply(op)
            self.assertEqual(ctx.exception.code, 'UNCERTAIN_WRITE')
        self.assertEqual(len(self.client.writes), 1)

    def test_结果核查不能使用修改后的计划(self):
        op = result_op('changed-uncertain')
        self.uncertain_result(op)
        op['data']['steps'][0]['actual'] = '被改写的实际情况'
        with self.assertRaises(qa.QAError) as ctx:
            qa.reconcile_result(self.client, plan(op), self.journal, '合成账号', op['key'])
        self.assertEqual(ctx.exception.code, 'CONFLICT')

    def test_步骤实际现象不一致不能通过核验(self):
        original = self.client.history
        def history(*args):
            rows = original(*args)
            for row in rows:
                row['stepResults'][0]['result'] = 'pass'
            return rows
        self.client.history = history
        result = self.apply(result_op())
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed']['code'], 'VERIFY_FAILED')

    def test_Bug并发修改拒绝(self):
        op = {'key': 'bug-40-edit', 'action': 'bug.update', 'targetId': 40,
              'expected': {'lastEditedDate': '旧时间'}, 'data': {'title': '修改'}}
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(op)
        self.assertEqual(ctx.exception.code, 'CONFLICT')

    def test_首次编辑Bug允许空修改时间但仍拦截并发变更(self):
        self.client.bug['lastEditedDate'] = ''
        op = {'key': 'first-bug-edit', 'action': 'bug.update', 'targetId': 40,
              'expected': {'lastEditedDate': ''}, 'data': {'steps': '<p>[步骤]</p><p>模拟操作</p><p>[结果]</p><p>模拟失败</p><p>[期望]</p><p>成功</p>'}}
        qa.validate_operation(op)
        self.client.bug['lastEditedDate'] = '2026-10-19 12:00:00'
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(op)
        self.assertEqual(ctx.exception.code, 'CONFLICT')
        self.assertFalse(self.client.writes)
        self.client.bug['lastEditedDate'] = None
        self.assertTrue(self.apply(op)['ok'])
        self.assertEqual(self.client.writes[0][2], op['data'])

    def test_Bug编辑与创建测试工作任务(self):
        edit = {'key': 'bug-40-edit', 'action': 'bug.update', 'targetId': 40,
                'expected': {'lastEditedDate': self.client.bug['lastEditedDate']}, 'data': {'title': '修改'}}
        task = {'key': 'task-1', 'action': 'task.create', 'data': {'name': '接口测试', 'executionID': 3}}
        self.assertTrue(self.apply(edit, task)['ok'])
        self.assertEqual(self.client.writes[1][2]['type'], 'test')

    def test_Bug创建时指派给指定账号并防重(self):
        op = {'key': 'assigned-bug', 'action': 'bug.create', 'data': {
            'productID': 1, 'title': '【调试模拟】撤销后状态未更新', 'openedBuild': [5],
            'steps': '【调试模拟】用于验证登记和指派链路。', 'assignedTo': 'tester'}}
        self.assertTrue(self.apply(op)['ok'])
        self.assertEqual(self.client.writes[0][2]['assignedTo'], 'tester')
        self.assertEqual(self.apply(op)['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 1)

    def test_Bug负责人回读不一致不能通过(self):
        op = {'key': 'wrong-assignee', 'action': 'bug.create', 'data': {
            'productID': 1, 'title': '模拟Bug', 'openedBuild': ['trunk'], 'steps': '模拟步骤', 'assignedTo': 'tester'}}
        original = self.client.detail
        def detail(kind, oid):
            value = copy.deepcopy(original(kind, oid))
            if kind == 'bug':
                value['assignedTo'] = {'account': 'other'}
            return value
        self.client.detail = detail
        result = self.apply(op)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed']['code'], 'VERIFY_FAILED')

    def test_Bug指派编辑支持账号对象回读(self):
        op = {'key': 'bug-assign', 'action': 'bug.update', 'targetId': 40,
              'expected': {'lastEditedDate': self.client.bug['lastEditedDate']}, 'data': {'assignedTo': 'tester'}}
        original = self.client.detail
        def detail(kind, oid):
            value = original(kind, oid)
            if kind == 'bug' and value.get('assignedTo'):
                value['assignedTo'] = {'account': value['assignedTo'], 'realname': '合成人员'}
            return value
        self.client.detail = detail
        self.assertTrue(self.apply(op)['ok'])
        self.assertEqual(self.client.writes[0][2], {'assignedTo': 'tester'})

    def test_Bug部分更新自动带回优先级等原值(self):
        self.client.bug.update(pri=1, severity=2, type='codeerror')
        op = {'key': 'bug-40-move', 'action': 'bug.update', 'targetId': 40,
              'expected': {'lastEditedDate': self.client.bug['lastEditedDate']},
              'data': {'execution': 852}}
        self.assertTrue(self.apply(op)['ok'])
        self.assertEqual(self.client.writes[0][2],
                         {'execution': 852, 'pri': 1, 'severity': 2, 'type': 'codeerror'})
        self.assertEqual(self.client.bug['pri'], 1)

    def test_Bug回读发现优先级被服务端改写时报错(self):
        self.client.bug.update(pri=1)
        original = self.client.request
        def request(method, path, data=None, params=None, version=2, auth=True):
            if method == 'PUT' and path.startswith('/bugs/'):
                data = dict(data, pri=3)
            return original(method, path, data, params, version, auth)
        self.client.request = request
        op = {'key': 'bug-40-reset', 'action': 'bug.update', 'targetId': 40,
              'expected': {'lastEditedDate': self.client.bug['lastEditedDate']},
              'data': {'execution': 852}}
        result = self.apply(op)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed']['code'], 'VERIFY_FAILED')

    def test_公司Bug自定义标签和责任人可回读核验(self):
        op = {'key': 'custom-bug', 'action': 'bug.create', 'data': {
            'productID': 1, 'title': '模拟Bug', 'openedBuild': ['trunk'], 'steps': '模拟步骤',
            'assignedTo': 'tester', 'responsible': 'tester', 'bugLabel': ['other']}}
        original = self.client.detail
        def detail(kind, oid):
            value = copy.deepcopy(original(kind, oid))
            if kind == 'bug':
                value['bugLabel'] = ','.join(value['bugLabel'])
            return value
        self.client.detail = detail
        self.assertTrue(self.apply(op)['ok'])
        self.assertEqual(self.client.writes[0][2]['responsible'], 'tester')
        self.assertEqual(self.client.writes[0][2]['bugLabel'], ['other'])
        for value in ['', [], [1]]:
            op['data']['bugLabel'] = value
            with self.assertRaises(qa.QAError):
                qa.validate_operation(op)

    def test_Bug编辑器块间换行规范化不影响核验(self):
        op = {'key': 'rich-bug', 'action': 'bug.create', 'data': {
            'productID': 1, 'title': '模拟Bug', 'openedBuild': ['trunk'],
            'steps': '<ol><li>模拟步骤</li></ol>\n<p>模拟实际结果</p>'}}
        original = self.client.detail
        def detail(kind, oid):
            value = copy.deepcopy(original(kind, oid))
            if kind == 'bug':
                value['steps'] = value['steps'].replace('</ol>\n<p>', '</ol><p>')
            return value
        self.client.detail = detail
        self.assertTrue(self.apply(op)['ok'])
        self.assertNotEqual(qa.normalized_bug_steps('<p>响应 A B</p>'), qa.normalized_bug_steps('<p>响应 AB</p>'))
        self.assertNotEqual(qa.normalized_bug_steps('<p>成功</p>'), qa.normalized_bug_steps('<p>失败</p>'))
        self.assertNotEqual(qa.normalized_bug_steps('<span>A</span> <span>B</span>'),
                            qa.normalized_bug_steps('<span>A</span><span>B</span>'))

    def test_测试单与Bug创建(self):
        task = {'key': 'testtask-1', 'action': 'testtask.create', 'data': {'productID': 1, 'name': '回归', 'build': 1, 'begin': '2026-10-19', 'end': '2026-10-20'}}
        bug = {'key': 'bug-1', 'action': 'bug.create', 'data': {'productID': 1, 'title': '接口500', 'openedBuild': ['trunk'], 'steps': '执行后500，预期200'}}
        self.assertTrue(self.apply(task, bug)['ok'])


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.client = qa.Client('https://example.invalid/zentao/', '合成Token', no_proxy=True)

    def response(self, value):
        return io.BytesIO(json.dumps(value).encode())

    def test_子路径认证头和查询参数保留(self):
        with patch.object(self.client.opener, 'open', return_value=self.response({'status': 'success'})) as call:
            self.client.request('GET', '/products', params={'pageID': 2})
        req = call.call_args.args[0]
        self.assertEqual(req.full_url, 'https://example.invalid/zentao/api.php/v2/products?pageID=2')
        self.assertEqual(req.get_header('Token'), '合成Token')

    def test_HTTP200业务失败不能算成功(self):
        with patch.object(self.client.opener, 'open', return_value=self.response({'status': 'fail', 'message': '合成敏感值'})):
            with self.assertRaises(qa.QAError) as ctx:
                self.client.request('GET', '/products')
        self.assertEqual(ctx.exception.code, 'BUSINESS_ERROR')
        self.assertNotIn('合成敏感值', str(ctx.exception))

    def test_登录页不作为成功JSON(self):
        with patch.object(self.client.opener, 'open', return_value=io.BytesIO(b'<html>login</html>')):
            with self.assertRaises(qa.QAError) as ctx:
                self.client.request('POST', '/bugs', {'title': '合成'})
        self.assertTrue(ctx.exception.uncertain)

    def test_权限错误与不存在区分(self):
        for status, expected in [(401, 'AUTH_FAILED'), (403, 'PERMISSION_DENIED'), (404, 'NOT_FOUND')]:
            with patch.object(self.client.opener, 'open', side_effect=urllib.error.HTTPError('https://example.invalid', status, '', {}, None)):
                with self.assertRaises(qa.QAError) as ctx:
                    self.client.request('GET', '/products')
                self.assertEqual(ctx.exception.code, expected)

    def test_重定向不转发凭据(self):
        self.assertIsNone(qa.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))

    def test_分页完整读取及重复页检测(self):
        pages = [{'status': 'success', 'testcases': [{'id': 'case_1'}], 'pager': {'pageTotal': 2}},
                 {'status': 'success', 'testcases': [{'id': 'case_2'}], 'pager': {'pageTotal': 2}}]
        with patch.object(self.client, 'request', side_effect=pages):
            result = self.client.listing('/products/1/testcases', 'testcases', True, size=1)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['items']), 2)
        with patch.object(self.client, 'request', return_value=pages[0]):
            with self.assertRaises(qa.QAError) as ctx:
                self.client.listing('/products/1/testcases', 'testcases', True, size=1)
        self.assertEqual(ctx.exception.code, 'PAGINATION_ERROR')


class PasswordAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / 'config.json'
        qa.safe_write(self.config, {'url': 'https://example.invalid/zentao',
                                    'account': 'tester', 'password': '合成密码',
                                    'token': '过期Token', 'noProxy': True})
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def client(self):
        return qa.configured(qa.parser().parse_args(['--config', str(self.config), 'doctor']))[0]

    def login_response(self):
        return {'status': 'success', 'token': '新Token', 'user': {'account': 'tester'}}

    def test_过期Token查询自动登录仅重试一次(self):
        client = self.client()
        with patch.object(client, '_request_once', side_effect=[qa.QAError('AUTH_FAILED', '过期'), self.login_response(), {'status': 'success'}]) as call:
            self.assertEqual(client.request('GET', '/products')['status'], 'success')
        self.assertEqual(call.call_count, 3)
        self.assertEqual(call.call_args_list[1].args[:2], ('POST', '/users/login'))
        saved = qa.read_json(self.config)
        self.assertEqual(saved['token'], '新Token')
        self.assertEqual(saved['password'], '合成密码')
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_无Token时用配置密码登录(self):
        saved = qa.read_json(self.config)
        saved['token'] = ''
        qa.safe_write(self.config, saved)
        client = self.client()
        with patch.object(client, '_request_once', side_effect=[self.login_response(), {'status': 'success'}]) as call:
            client.request('GET', '/products')
        self.assertEqual(call.call_count, 2)
        self.assertEqual(client.token, '新Token')

    def test_密码错误不循环登录(self):
        client = self.client()
        with patch.object(client, '_request_once', side_effect=[qa.QAError('AUTH_FAILED', '过期'), qa.QAError('AUTH_FAILED', '密码错误')]) as call:
            with self.assertRaises(qa.QAError):
                client.request('GET', '/products')
        self.assertEqual(call.call_count, 2)
        self.assertEqual(qa.read_json(self.config)['token'], '过期Token')

    def test_重登后仍未授权不再重试(self):
        client = self.client()
        with patch.object(client, '_request_once', side_effect=[qa.QAError('AUTH_FAILED', '过期'), self.login_response(), qa.QAError('AUTH_FAILED', '失败')]) as call:
            with self.assertRaises(qa.QAError):
                client.request('GET', '/products')
        self.assertEqual(call.call_count, 3)

    def test_写请求认证失败刷新但不重发(self):
        client = self.client()
        with patch.object(client, '_request_once', side_effect=[qa.QAError('AUTH_FAILED', '过期'), self.login_response()]) as call:
            with self.assertRaises(qa.QAError) as ctx:
                client.request('POST', '/bugs', {'title': '合成Bug'})
        self.assertEqual(ctx.exception.code, 'AUTH_REFRESHED_WRITE_STOPPED')
        self.assertEqual(call.call_count, 2)
        self.assertTrue(ctx.exception.uncertain)

    def test_权限或网络问题不重登(self):
        for code in ['PERMISSION_DENIED', 'NETWORK_ERROR', 'BUSINESS_ERROR']:
            client = self.client()
            with patch.object(client, '_request_once', side_effect=qa.QAError(code, '合成错误')) as call:
                with self.assertRaises(qa.QAError):
                    client.request('GET', '/products')
            self.assertEqual(call.call_count, 1)

    def test_环境Token不借用配置密码(self):
        with patch.dict(os.environ, {'ZENTAO_TOKEN': '显式Token'}):
            client = self.client()
        self.assertIsNone(client.reauthenticate)
        self.assertEqual(client.token, '显式Token')

    def test_更换站点不会转发保存的密码(self):
        saved = qa.read_json(self.config)
        saved['token'] = ''
        qa.safe_write(self.config, saved)
        args = qa.parser().parse_args(['--config', str(self.config), '--url', 'https://other.invalid', 'doctor'])
        with self.assertRaises(qa.QAError) as ctx:
            qa.configured(args)
        self.assertEqual(ctx.exception.code, 'AUTH_SCOPE_MISMATCH')

    def test_显式保存密码且输出不含凭据(self):
        args = qa.parser().parse_args(['--config', str(self.config), 'login', '--save-password'])
        with patch.object(qa.Client, '_request_once', return_value=self.login_response()):
            result = qa.run(args)
        self.assertTrue(result['passwordSaved'])
        self.assertNotIn('合成密码', json.dumps(result))
        self.assertNotIn('新Token', json.dumps(result))
        self.assertEqual(qa.read_json(self.config)['password'], '合成密码')


class CaseReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = qa.Journal(Path(self.tmp.name) / 'journal.sqlite3')
        self.client = FakeClient()
        self.client.objects[('case', 80)] = {'id': 80, 'version': 1, 'story': 10,
                                           'status': 'wait', 'lastEditedDate': '',
                                           'lastRunResult': ''}

    def tearDown(self):
        self.tmp.cleanup()

    def review_op(self):
        return {'key': 'review-case-80-v1', 'action': 'case.review', 'targetId': 80,
                'expected': {'caseVersion': 1, 'storyId': 10, 'lastEditedDate': ''},
                'data': {'result': 'pass', 'reviewedBy': ['tester'], 'comment': '评审通过'}}

    def apply(self, op):
        qa.validate_operation(op)
        return qa.apply_plan(self.client, plan(op), self.journal, 'tester')

    def test_正式评审通过并回读评审字段(self):
        result = self.apply(self.review_op())
        self.assertTrue(result['ok'])
        method, path, body, _, version = self.client.writes[0]
        self.assertEqual((method, path, version), ('PUT', '/testcases/80/review', 2))
        self.assertNotIn('status', body)
        self.assertEqual(len(body['reviewedDate']), 10)
        self.assertEqual(result['completed'][0]['remote']['reviewedBy'], ['tester'])
        self.assertEqual(self.client.objects[('case', 80)]['lastRunResult'], '')

    def test_评审版本或需求变更时停止(self):
        for field, value in [('version', 2), ('story', 11), ('lastEditedDate', '新修改时间')]:
            before = dict(self.client.objects[('case', 80)])
            self.client.objects[('case', 80)][field] = value
            with self.assertRaises(qa.QAError) as ctx:
                self.apply(self.review_op())
            self.assertEqual(ctx.exception.code, 'CONFLICT')
            self.client.objects[('case', 80)] = before
        self.assertFalse(self.client.writes)

    def test_不重复评审已经正常的用例(self):
        self.client.objects[('case', 80)]['status'] = 'normal'
        with self.assertRaises(qa.QAError):
            self.apply(self.review_op())
        self.assertFalse(self.client.writes)

    def test_评审动作仅支持通过(self):
        op = self.review_op()
        op['data']['result'] = 'fail'
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)

    def test_评审回读必须有评审人(self):
        self.client.review_verify_fail = True
        result = self.apply(self.review_op())
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed']['code'], 'VERIFY_FAILED')

    def test_新增待评审用例默认自动通过且防重(self):
        self.client.review_required = True
        result = self.apply(case_op())
        self.assertTrue(result['ok'])
        self.assertEqual([r[0] for r in self.client.writes], ['POST', 'PUT'])
        self.assertEqual(result['completed'][0]['remote']['status'], 'normal')
        self.assertEqual(self.apply(case_op())['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 2)

    def test_用户可明确保留待评审(self):
        self.client.review_required = True
        op = case_op()
        op['autoReview'] = False
        result = self.apply(op)
        self.assertTrue(result['ok'])
        self.assertEqual(len(self.client.writes), 1)
        self.assertEqual(self.client.objects[('case', result['completed'][0]['remote']['id'])]['status'], 'wait')

    def test_自动评审超时不重新创建也不重发评审(self):
        self.client.review_required = True
        self.client.review_write_fail = True
        first = self.apply(case_op())
        self.assertFalse(first['ok'])
        self.assertEqual(first['failed']['remoteId'], 101)
        second = self.apply(case_op())
        self.assertFalse(second['ok'])
        self.assertEqual(second['failed']['code'], 'UNCERTAIN_WRITE')
        self.assertEqual(len(self.client.writes), 2)

    def test_评审日期必须是日期而不是完整时间(self):
        op = self.review_op()
        op['data']['reviewedDate'] = '2026-10-19 10:00:00'
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)

    def test_可以显式指定评审日期(self):
        op = self.review_op()
        op['data']['reviewedDate'] = '2026-10-19'
        result = self.apply(op)
        self.assertTrue(result['ok'])
        self.assertEqual(result['completed'][0]['remote']['reviewedDate'], '2026-10-19')

    def test_仅未生效且没有历史的评审允许核查恢复(self):
        op = self.review_op()
        self.client.review_write_fail = True
        self.assertFalse(self.apply(op)['ok'])
        result = qa.reconcile_review(self.client, plan(op), self.journal, 'tester', op['key'])
        self.assertTrue(result['ok'])
        self.assertFalse(result['businessDataWritten'])
        self.client.review_write_fail = False
        self.assertTrue(self.apply(op)['ok'])

    def test_已有评审历史时不能恢复重发(self):
        op = self.review_op()
        self.client.review_write_fail = True
        self.apply(op)
        self.client.request = lambda *a, **kw: {'testcase': self.client.objects[('case', 80)], 'actions': [{'action': 'reviewed'}]}
        with self.assertRaises(qa.QAError):
            qa.reconcile_review(self.client, plan(op), self.journal, 'tester', op['key'])

    def test_用例创建等其他写入不能借评审核查解除账本(self):
        with self.assertRaises(qa.QAError):
            qa.reconcile_review(self.client, plan(case_op()), self.journal, 'tester', case_op()['key'])

    def test_自动评审回读失败后只重读(self):
        self.client.review_required = True
        self.client.review_verify_fail = True
        first = self.apply(case_op())
        self.assertFalse(first['ok'])
        self.client.objects[('case', 101)]['reviewedBy'] = 'tester'
        second = self.apply(case_op())
        self.assertTrue(second['ok'])
        self.assertEqual(len(self.client.writes), 2)


class TaskHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = qa.Journal(Path(self.tmp.name) / 'journal.sqlite3')
        self.client = FakeClient()
        self.client.objects[('task', 90)] = {'id': 90, 'execution': 3, 'type': 'test',
                                           'status': 'wait', 'isParent': 0}

    def tearDown(self):
        self.tmp.cleanup()

    def child_op(self):
        return {'key': 'child-task-10', 'action': 'task.create',
                'data': {'name': '需求测试子任务', 'executionID': 3, 'parent': 90}}

    def test_子任务建立原生父子关系并防重(self):
        op = self.child_op()
        qa.validate_operation(op)
        first = qa.apply_plan(self.client, plan(op), self.journal, 'tester')
        self.assertTrue(first['ok'])
        self.assertEqual(self.client.writes[0][2]['parent'], 90)
        self.assertEqual(self.client.objects[('task', 90)]['isParent'], 1)
        second = qa.apply_plan(self.client, plan(op), self.journal, 'tester')
        self.assertEqual(second['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 1)

    def test_父任务跨冲刺或类型不匹配时拒绝(self):
        for field, value in [('execution', 4), ('type', 'devel'), ('status', 'closed')]:
            original = dict(self.client.objects[('task', 90)])
            self.client.objects[('task', 90)][field] = value
            with self.assertRaises(qa.QAError):
                qa.preflight(self.client, self.child_op())
            self.client.objects[('task', 90)] = original
        self.assertFalse(self.client.writes)

    def test_父任务编号不允许负数或字符串(self):
        for parent in (-1, '90', True):
            op = self.child_op()
            op['data']['parent'] = parent
            with self.assertRaises(qa.QAError):
                qa.validate_operation(op)


class TaskStartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = qa.Journal(Path(self.tmp.name) / 'journal.sqlite3')
        self.client = FakeClient()
        self.client.objects[('task', 90)] = {'id': 90, 'status': 'wait'}
        self.client.objects[('task', 81)] = {'id': 81, 'type': 'test', 'isParent': 0,
                                           'status': 'wait', 'story': 10, 'parent': 90,
                                           'assignedTo': 'tester', 'consumed': 0, 'lastEditedDate': None}

    def tearDown(self):
        self.tmp.cleanup()

    def op(self):
        return {'key': 'start-task-81', 'action': 'task.start', 'targetId': 81,
                'expected': {'storyId': 10, 'lastEditedDate': ''},
                'data': {'left': 4, 'consumed': 0, 'assignedTo': 'tester'}}

    def test_启动子任务并核对父任务联动且不记虚假消耗(self):
        op = self.op()
        qa.validate_operation(op)
        first = qa.apply_plan(self.client, plan(op), self.journal, 'tester')
        self.assertTrue(first['ok'])
        self.assertEqual(first['completed'][0]['remote']['parentStatus'], 'doing')
        self.assertEqual(self.client.objects[('task', 81)]['consumed'], 0)
        self.assertEqual(self.client.writes[0][1], '/tasks/81/start')
        self.assertEqual(len(self.client.writes[0][2]['realStarted']), 19)
        second = qa.apply_plan(self.client, plan(op), self.journal, 'tester')
        self.assertEqual(second['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 1)

    def test_零或过小剩余工时不能误触发完成(self):
        for left in (0, -1, 0.001, True, '4'):
            op = self.op()
            op['data']['left'] = left
            with self.assertRaises(qa.QAError):
                qa.validate_operation(op)

    def test_任务状态负责人或消耗变化时不启动(self):
        for field, value in [('status', 'done'), ('assignedTo', 'other'), ('consumed', 1), ('story', 11), ('isParent', 1)]:
            old = dict(self.client.objects[('task', 81)])
            self.client.objects[('task', 81)][field] = value
            with self.assertRaises(qa.QAError):
                qa.preflight(self.client, self.op())
            self.client.objects[('task', 81)] = old
        self.assertFalse(self.client.writes)


class TesttaskExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = qa.Journal(Path(self.tmp.name) / 'journal.sqlite3')
        self.client = FakeClient()
        self.case = {'id': 21, 'product': 1, 'execution': 3, 'story': 10, 'version': 1,
                     'status': 'normal', 'lastRunResult': '',
                     'steps': [{'id': 51, 'type': 'step'}, {'id': 52, 'type': 'step'}]}
        self.task = {'id': 30, 'product': 1, 'execution': 3, 'status': 'doing',
                     'testcases': [{'id': 61, 'case': 99, 'version': 1, 'lastRunResult': 'pass'}]}
        self.client.objects[('case', 21)] = self.case
        self.client.testtask = lambda oid: copy.deepcopy(self.task)
        old_request = self.client.request
        def request(method, path, data=None, params=None, version=2, auth=True):
            if path.endswith('/linkCase') or path == '/testtasks/batchRun':
                self.client.writes.append((method, path, copy.deepcopy(data), params, version))
                if self.client.write_fail:
                    raise qa.QAError('NETWORK_ERROR', '模拟超时', uncertain=True)
                if path.endswith('/linkCase'):
                    self.task['testcases'].append({'id': 62, 'case': data['case'][0], 'version': data['version'][0]})
                else:
                    result = data['results']['21']
                    self.client.results.append({'id': 71, 'run': 62, 'version': 1, 'caseResult': result,
                                                'stepResults': [{'result': data['steps']['21'][i],
                                                                 'real': data['reals']['21'][i]} for i in ('51', '52')]})
                    self.case['lastRunResult'] = result
                    self.task['testcases'][-1]['lastRunResult'] = result
                return {'status': 'success'}
            return old_request(method, path, data, params, version, auth)
        self.client.request = request

    def tearDown(self):
        self.tmp.cleanup()

    def op(self, action='testtask.linkcase', key='link-21'):
        data = {'caseId': 21, 'caseVersion': 1, 'testtaskId': 30}
        if action == 'result.report':
            data.update(result='fail', report='调试模拟：用户授权写入示例失败结果，非实际测试证据。')
        return {'key': key, 'action': action, 'expected': {'storyId': 10}, 'data': data}

    def apply(self, op):
        qa.validate_operation(op)
        return qa.apply_plan(self.client, plan(op), self.journal, '合成账号')

    def test_追加关联保留已有执行结果且重复调用不写(self):
        self.assertTrue(self.apply(self.op())['ok'])
        self.assertEqual(self.task['testcases'][0]['lastRunResult'], 'pass')
        self.assertEqual(self.apply(self.op())['completed'][0]['state'], 'already_applied')
        self.assertTrue(self.apply(self.op(key='link-again'))['ok'])
        self.assertEqual(len(self.client.writes), 1)

    def test_关联冲刺产品需求版本及状态冲突不写(self):
        for field, value in [('execution', 4), ('product', 9), ('story', 11), ('version', 2), ('status', 'wait')]:
            old = self.case[field]
            self.case[field] = value
            with self.assertRaises(qa.QAError):
                self.apply(self.op())
            self.case[field] = old
        self.assertFalse(self.client.writes)

    def test_已有不同版本关联不可覆盖(self):
        self.task['testcases'].append({'id': 62, 'case': 21, 'version': 2})
        with self.assertRaises(qa.QAError):
            self.apply(self.op())
        self.assertFalse(self.client.writes)

    def test_整体失败来源明确且不伪造步骤结果或执行时间(self):
        self.apply(self.op())
        report = self.op('result.report', 'report-21')
        self.assertTrue(self.apply(report)['ok'])
        method, path, body, params, version = self.client.writes[-1]
        self.assertEqual((method, path, version), ('PUT', '/testtasks/batchRun', 2))
        self.assertEqual(list(params.values()), [1, 'id_desc', 'testtask', 30])
        self.assertEqual(body['steps']['21'], {'51': '', '52': ''})
        self.assertIn('调试模拟', body['reals']['21']['51'])
        self.assertNotIn('startedAt', body)
        self.assertEqual(self.task['testcases'][0]['lastRunResult'], 'pass')
        self.assertEqual(self.apply(report)['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 2)

    def test_整体报告未关联时停止(self):
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(self.op('result.report'))
        self.assertEqual(ctx.exception.code, 'CASE_NOT_LINKED')
        self.assertFalse(self.client.writes)

    def test_整体报告不接受通过或空说明(self):
        for field, value in [('result', 'pass'), ('result', []), ('report', '')]:
            op = self.op('result.report')
            op['data'][field] = value
            with self.assertRaises(qa.QAError):
                qa.validate_operation(op)

    def test_关联超时不可重发(self):
        self.client.write_fail = True
        self.assertFalse(self.apply(self.op())['ok'])
        with self.assertRaises(qa.QAError) as ctx:
            self.apply(self.op())
        self.assertEqual(ctx.exception.code, 'UNCERTAIN_WRITE')
        self.assertEqual(len(self.client.writes), 1)

    def test_结果回读失败后只重做核验(self):
        self.apply(self.op())
        history = self.client.history
        self.client.history = lambda *a: []
        report = self.op('result.report', 'report-retry')
        self.assertFalse(self.apply(report)['ok'])
        self.client.history = history
        self.assertTrue(self.apply(report)['ok'])
        self.assertEqual(len(self.client.writes), 2)

    def test_其他执行条目的历史不可作为成功证据(self):
        self.apply(self.op())
        report = self.op('result.report')
        qa.submit(self.client, report)
        self.client.results[-1]['run'] = 999
        with self.assertRaises(qa.QAError):
            qa.verify(self.client, report, {'runId': 62})


class BugAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'screenshot.png'
        self.content = b'\x89PNG\r\n\x1a\n' + b'fake-image-for-testing'
        self.path.write_bytes(self.content)
        self.op = {'key': 'attach-png', 'action': 'bug.attach', 'targetId': 40,
                   'expected': {'storyId': 10}, 'data': {'path': str(self.path), 'filename': 'bug-40.png',
                   'sha256': qa.hashlib.sha256(self.content).hexdigest(), 'size': len(self.content)}}
        self.client = FakeClient()
        self.client.bug.update(story=10, files={})
        self.client.probe_png = lambda path: {'url': 'https://example.invalid/zentao/data/upload/image', 'sha256': qa.hashlib.sha256(self.content).hexdigest(), 'size': len(self.content)}
        self.journal = qa.Journal(Path(self.tmp.name) / 'journal.sqlite3')
        def request(method, path, data=None, params=None, version=2, auth=True):
            self.client.writes.append((method, path, data))
            if self.client.write_fail:
                raise qa.QAError('NETWORK_ERROR', '模拟上传超时', uncertain=True)
            self.client.bug['files'] = {'90': {'id': 90, 'objectType': 'bug', 'objectID': 40, 'size': len(self.content), 'webPath': '/zentao/data/upload/image'}}
            return {'status': 'success', 'id': 90, 'url': '/zentao/file-read-90.png'}
        self.client.request = request

    def tearDown(self):
        self.tmp.cleanup()

    def apply(self):
        qa.validate_operation(self.op)
        return qa.apply_plan(self.client, plan(self.op), self.journal, 'tester')

    def test_上传真实二进制表单并原生关联防重(self):
        self.assertTrue(self.apply()['ok'])
        method, path, body = self.client.writes[0]
        self.assertEqual((method, path), ('POST', '/files'))
        self.assertIsInstance(body, qa.MultipartBody)
        self.assertIn(self.content, body.body)
        self.assertIn(b'name="objectType"\r\n\r\nbug', body.body)
        self.assertIn(b'name="objectID"\r\n\r\n40', body.body)
        self.assertIn(b'name="file"; filename="bug-40.png"', body.body)
        self.assertEqual(self.apply()['completed'][0]['state'], 'already_applied')
        self.assertEqual(len(self.client.writes), 1)

    def test_文件变化或扩展名不符时不写入(self):
        self.path.write_bytes(self.content + b'changed')
        with self.assertRaises(qa.QAError):
            self.apply()
        self.path.write_bytes(self.content)
        self.op['data']['filename'] = 'screenshot.jpg'
        with self.assertRaises(qa.QAError):
            self.apply()
        self.assertFalse(self.client.writes)

    def test_文件名注入和过大文件被拒绝(self):
        for filename in ['../x.png', 'x"\r\n.png']:
            self.op['data']['filename'] = filename
            with self.assertRaises(qa.QAError):
                qa.validate_operation(self.op)
        self.op['data']['filename'] = 'x.png'
        self.path.write_bytes(b'x' * (10 * 1024 * 1024 + 1))
        with self.assertRaises(qa.QAError):
            self.apply()

    def test_需求错配停止上传(self):
        self.client.bug['story'] = 11
        with self.assertRaises(qa.QAError):
            self.apply()
        self.assertFalse(self.client.writes)

    def test_上传超时禁止自动重传(self):
        self.client.write_fail = True
        self.assertFalse(self.apply()['ok'])
        with self.assertRaises(qa.QAError) as ctx:
            self.apply()
        self.assertEqual(ctx.exception.code, 'UNCERTAIN_WRITE')
        self.assertEqual(len(self.client.writes), 1)

    def test_已上传回读失败时重跑只核验(self):
        original = self.client.detail
        calls = [0]
        def detail(kind, oid):
            value = original(kind, oid)
            if self.client.writes and calls[0] == 0:
                calls[0] += 1
                return dict(value, files={})
            return value
        self.client.detail = detail
        self.assertFalse(self.apply()['ok'])
        self.assertTrue(self.apply()['ok'])
        self.assertEqual(len(self.client.writes), 1)

    def test_附件关联到其他Bug不能通过(self):
        remote = qa.submit(self.client, self.op)
        self.client.bug['files']['90']['objectID'] = 99
        with self.assertRaises(qa.QAError):
            qa.verify(self.client, self.op, remote)

    def test_远端图片不可读时保留提交状态不重传(self):
        def bad_image(path):
            raise qa.QAError('IMAGE_NOT_READABLE', '模拟返回HTML')
        self.client.probe_png = bad_image
        self.assertFalse(self.apply()['ok'])
        self.client.probe_png = lambda path: {'url': 'https://example.invalid/zentao/data/upload/image', 'sha256': self.op['data']['sha256'], 'size': len(self.content)}
        result = self.apply()
        self.assertTrue(result['ok'])
        self.assertTrue(result['completed'][0]['remote']['imageReadable'])
        self.assertEqual(len(self.client.writes), 1)

    def test_图片核验检查字节且不向静态路径发送Token(self):
        client = qa.Client('https://example.invalid/zentao', '合成Token', no_proxy=True)
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = self.content
        response.__enter__.return_value.headers = {}
        with patch.object(client.opener, 'open', return_value=response) as opened:
            result = client.probe_png('/zentao/data/upload/image')
        self.assertEqual(result['sha256'], self.op['data']['sha256'])
        self.assertIsNone(opened.call_args.args[0].get_header('Token'))
        response.__enter__.return_value.read.return_value = b'<html>login</html>'
        with patch.object(client.opener, 'open', return_value=response):
            with self.assertRaises(qa.QAError) as ctx:
                client.probe_png('/zentao/data/upload/image')
        self.assertEqual(ctx.exception.code, 'IMAGE_NOT_READABLE')
        for path in ['https://other.invalid/image', '/zentao/index.php?m=file', '/other/data/upload/image']:
            with self.assertRaises(qa.QAError):
                client.probe_png(path)

    def test_传输使用multipart而非JSON(self):
        client = qa.Client('https://example.invalid/zentao', '合成Token', no_proxy=True)
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"status":"success","id":90}'
        with patch.object(client.opener, 'open', return_value=response) as opened:
            client.request('POST', '/files', qa.image_multipart(self.op['data'], 40))
        req = opened.call_args.args[0]
        self.assertTrue(req.get_header('Content-type').startswith('multipart/form-data; boundary='))
        self.assertIn(self.content, req.data)
        self.assertEqual(req.get_header('Token'), '合成Token')


class UserLookupTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.users = [
            {'id': '8', 'account': 'hjl', 'realname': '黄景霖', 'pinyin': 'huangjinglin hjl',
             'nickname': '', 'role': 'dm', 'dept': '20', 'deleted': '0', 'ip': '192.168.110.52'},
            {'id': '449', 'account': 'linjt', 'realname': '林金堂', 'pinyin': 'linjintang ljt',
             'nickname': '', 'role': 'tm', 'dept': '22', 'deleted': '0'},
            {'id': '500', 'account': 'hcf', 'realname': '黄川峰', 'pinyin': 'huangchuanfeng hcf',
             'nickname': '', 'role': 'dev', 'dept': '20', 'deleted': '0'},
            {'id': '501', 'account': 'huangcf', 'realname': '黄川峰', 'pinyin': 'huangchuanfeng hcf',
             'nickname': '', 'role': 'dev', 'dept': '20', 'deleted': '0'},
        ]

    def read(self, *argv):
        self.client.listing = lambda path, key, all_pages=False, page=1, size=100: {
            'items': self.users, 'complete': all_pages, 'pager': {'recTotal': len(self.users)}}
        with patch.object(qa, 'configured', return_value=(self.client, 'tester')):
            return qa.run(qa.parser().parse_args(list(argv)))

    def test_按中文姓名查登录账号(self):
        result = self.read('read', 'users', '--kw', '黄景霖')
        self.assertEqual([u['account'] for u in result['items']], ['hjl'])
        self.assertEqual(result['items'][0]['realname'], '黄景霖')

    def test_按登录账号和拼音查(self):
        self.assertEqual([u['account'] for u in self.read('read', 'users', '--kw', 'hjl')['items']], ['hjl'])
        self.assertEqual([u['account'] for u in self.read('read', 'users', '--kw', 'linjintang')['items']], ['linjt'])

    def test_同名返回全部候选供人工确认(self):
        self.assertEqual([u['account'] for u in self.read('read', 'users', '--kw', '黄川峰')['items']],
                         ['hcf', 'huangcf'])

    def test_精确匹配不命中姓名片段(self):
        self.assertEqual(self.read('read', 'users', '--kw', '黄景', '--exact')['items'], [])
        self.assertEqual([u['account'] for u in self.read('read', 'users', '--kw', 'hjl', '--exact')['items']],
                         ['hjl'])

    def test_只返回识别所需字段(self):
        item = self.read('read', 'users', '--kw', 'hjl')['items'][0]
        self.assertEqual(set(item), set(qa.USER_FIELDS))
        self.assertNotIn('ip', item)

    def test_按编号读取单个用户(self):
        self.client.request = lambda method, path, data=None, params=None, version=2, auth=True: {
            'status': 'success', 'user': self.users[0]} if path == '/users/8' else {}
        self.assertEqual(self.read('read', 'user', '--id', '8')['data']['account'], 'hjl')

    def test_指派字段必须是登录账号(self):
        op = {'key': 'cn-assignee', 'action': 'bug.create', 'data': {
            'productID': 1, 'title': '模拟Bug', 'openedBuild': ['trunk'], 'steps': '模拟步骤',
            'assignedTo': '黄景霖'}}
        with self.assertRaises(qa.QAError) as ctx:
            qa.validate_operation(op)
        self.assertIn('read users', str(ctx.exception))
        op['data']['assignedTo'] = 'hjl'
        qa.validate_operation(op)
        op['data']['responsible'] = '林金堂'
        with self.assertRaises(qa.QAError):
            qa.validate_operation(op)


if __name__ == '__main__':
    unittest.main()
