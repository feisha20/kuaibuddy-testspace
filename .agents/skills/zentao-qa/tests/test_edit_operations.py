"""编辑操作的合成数据测试，不连接禅道。"""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('qaedit', Path(__file__).resolve().parents[1] / 'scripts/zentao_qa.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class Client:
    def __init__(self):
        self.case = {'id': 11, 'story': '0', 'version': '1', 'lastEditedDate': '', 'deleted': '0',
                     'title': '原题', 'precondition': '原前置', 'pri': '2', 'type': 'feature', 'module': '0',
                     'steps': [{'id': 77, 'type': 'step', 'desc': '操作', 'expect': '预期'}]}
        self.task = {'id': 12, 'story': '0', 'lastEditedDate': '', 'deleted': '0', 'name': '旧任务',
                     'type': 'test', 'execution': '4', 'parent': '0', 'status': 'wait', 'consumed': '0.00', 'left': '0.00', 'assignedTo': ''}
        self.sent = None
    def detail(self, kind, oid):
        return copy.deepcopy(self.case if kind == 'case' else self.task)
    def request(self, method, path, data):
        self.sent = copy.deepcopy(data)
        target = self.case if 'testcases' in path else self.task
        if 'testcases' in path:
            target.update({k: v for k, v in data.items() if k not in ('steps', 'expects', 'stepType')})
            target['steps'] = [{'type': typ, 'desc': s, 'expect': e} for s,e,typ in zip(data['steps'],data['expects'],data['stepType'])]
        else: target.update(data)
        return {'status': 'success'}


class EditTests(unittest.TestCase):
    def test_case_title_preserves_steps_and_fields(self):
        c = Client(); op = {'key': 'edit-case', 'action': 'case.update', 'targetId': 11,
            'expected': {'caseVersion': 1, 'storyId': 0, 'lastEditedDate': ''}, 'data': {'title': '新题'}}
        qa.validate_operation(op); qa.preflight(c, op); remote = qa.submit(c, op); qa.verify(c, op, remote)
        self.assertEqual(c.sent['steps'], ['操作']); self.assertEqual(c.sent['stepType'], ['step'])
        self.assertEqual(c.case['precondition'], '原前置'); self.assertEqual(c.case['title'], '新题')
    def test_case_step_edit_resizes_types_and_keeps_all_steps(self):
        c = Client(); op = {'key': 'edit-case-steps', 'action': 'case.update', 'targetId': 11,
            'expected': {'caseVersion': 1, 'storyId': 0, 'lastEditedDate': ''},
            'data': {'steps': ['打开入口', '填写信息', '提交并查看'], 'expects': ['入口可见', '内容正确', '显示结果']}}
        qa.validate_operation(op); remote = qa.submit(c, op); qa.verify(c, op, remote)
        self.assertEqual(c.sent['stepType'], ['step'] * 3)
        self.assertEqual([step['desc'] for step in c.case['steps']], op['data']['steps'])
    def test_task_rename_assign_preserves_state(self):
        c = Client(); op = {'key': 'edit-task', 'action': 'task.update', 'targetId': 12,
            'expected': {'storyId': 0, 'lastEditedDate': ''}, 'data': {'name': '新任务', 'assignedTo': 'user'}}
        qa.validate_operation(op); remote = qa.submit(c, op); qa.verify(c, op, remote)
        self.assertEqual(c.task['status'], 'wait'); self.assertEqual(c.task['left'], '0.00')
    def test_stale_case_version_and_group_steps_rejected(self):
        c = Client(); op = {'key': 'stale', 'action': 'case.update', 'targetId': 11,
            'expected': {'caseVersion': 2, 'storyId': 0, 'lastEditedDate': ''}, 'data': {'title': '新题'}}
        with self.assertRaises(qa.QAError): qa.preflight(c, op)
        op['expected']['caseVersion'] = 1; c.case['steps'][0]['type'] = 'group'
        with self.assertRaises(qa.QAError): qa.preflight(c, op)
        self.assertIsNone(c.sent)
    def test_detect_unrequested_task_state_change(self):
        c = Client(); op = {'key': 'edit', 'action': 'task.update', 'targetId': 12,
            'expected': {'storyId': 0, 'lastEditedDate': ''}, 'data': {'name': '新任务'}}
        remote = qa.submit(c, op); c.task['left'] = '5.00'
        with self.assertRaises(qa.QAError): qa.verify(c, op, remote)
    def test_step_edit_must_include_expectations(self):
        op = {'key': 'edit', 'action': 'case.update', 'targetId': 11,
            'expected': {'caseVersion': 1, 'storyId': 0, 'lastEditedDate': ''}, 'data': {'steps': ['新步骤']}}
        with self.assertRaises(qa.QAError): qa.validate_operation(op)

if __name__ == '__main__':
    unittest.main()
