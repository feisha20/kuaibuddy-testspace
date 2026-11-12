"""使用合成数据验证关闭Bug及防重边界，不连接禅道。"""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('qa_close', Path(__file__).resolve().parents[1] / 'scripts/zentao_qa.py')
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


def operation():
    return {'key': 'bug-40-close', 'action': 'bug.close', 'targetId': 40,
            'expected': {'storyId': 10, 'status': 'resolved', 'lastEditedDate': '2026-11-12 10:00:00'},
            'data': {'comment': '按用户确认的关闭依据关闭。'}}


class Client:
    url = 'https://example.invalid/zentao'

    def __init__(self):
        self.bug = {'id': 40, 'story': 10, 'status': 'resolved', 'deleted': '0',
                    'lastEditedDate': '2026-11-12 10:00:00', 'resolution': 'fixed',
                    'pri': 1, 'severity': 2, 'type': 'codeerror'}
        self.writes = []
        self.uncertain = False
        self.bad_verify = False

    def detail(self, kind, oid):
        assert (kind, oid) == ('bug', 40)
        value = copy.deepcopy(self.bug)
        if self.bad_verify and self.writes:
            value['closedBy'] = ''
        return value

    def request(self, method, path, data):
        assert (method, path) == ('PUT', '/bugs/40/close')
        assert set(data) == {'comment'}
        self.writes.append(copy.deepcopy(data))
        self.bug.update(status='closed', assignedTo='closed', closedBy='alice', closedDate='2026-11-12 10:01:00')
        if self.uncertain:
            raise qa.QAError('UNCERTAIN_WRITE', '模拟响应丢失', uncertain=True)
        return {'status': 'success'}


class Tests(unittest.TestCase):
    def test_close_and_repeat(self):
        for status in ('active', 'resolved'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                client, op = Client(), operation()
                client.bug['status'] = op['expected']['status'] = status
                qa.validate_operation(op)
                journal = qa.Journal(Path(folder) / 'journal.sqlite3')
                plan = {'schemaVersion': 1, 'operations': [op]}
                self.assertTrue(qa.apply_plan(client, plan, journal, 'alice')['ok'])
                result = qa.apply_plan(client, plan, journal, 'alice')
                self.assertEqual(result['completed'][0]['state'], 'already_applied')
                self.assertEqual(len(client.writes), 1)
                self.assertEqual(client.bug['pri'], 1)

    def test_invalid_plan(self):
        for field in ('storyId', 'status', 'lastEditedDate'):
            op = operation()
            del op['expected'][field]
            with self.subTest(field=field), self.assertRaises(qa.QAError):
                qa.validate_operation(op)
        for value in ('', ' ', None, 1):
            op = operation()
            op['data']['comment'] = value
            with self.assertRaises(qa.QAError):
                qa.validate_operation(op)
        for field in ('status', 'resolution', 'closedBy', 'closedDate'):
            op = operation()
            op['data'][field] = '伪造值'
            with self.assertRaises(qa.QAError):
                qa.validate_operation(op)

    def test_conflicts_do_not_write(self):
        for field, value in (('status', 'closed'), ('story', 11), ('lastEditedDate', '新时间'), ('deleted', '1')):
            client = Client()
            client.bug[field] = value
            with self.subTest(field=field), self.assertRaises(qa.QAError):
                qa.submit(client, operation())
            self.assertEqual(client.writes, [])

    def test_verification_failure_only_rechecks(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Client()
            client.bad_verify = True
            journal = qa.Journal(Path(folder) / 'journal.sqlite3')
            plan = {'schemaVersion': 1, 'operations': [operation()]}
            result = qa.apply_plan(client, plan, journal, 'alice')
            self.assertEqual(result['failed']['code'], 'VERIFY_FAILED')
            client.bad_verify = False
            self.assertTrue(qa.apply_plan(client, plan, journal, 'alice')['ok'])
            self.assertEqual(len(client.writes), 1)

    def test_uncertain_write_never_resends(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Client()
            client.uncertain = True
            journal = qa.Journal(Path(folder) / 'journal.sqlite3')
            plan = {'schemaVersion': 1, 'operations': [operation()]}
            self.assertFalse(qa.apply_plan(client, plan, journal, 'alice')['ok'])
            with self.assertRaises(qa.QAError) as error:
                qa.apply_plan(client, plan, journal, 'alice')
            self.assertEqual(error.exception.code, 'UNCERTAIN_WRITE')
            self.assertEqual(len(client.writes), 1)

    def test_changed_original_field_fails_verification(self):
        client, op = Client(), operation()
        remote = qa.submit(client, op)
        client.bug['resolution'] = 'willnotfix'
        with self.assertRaises(qa.QAError) as error:
            qa.verify(client, op, remote)
        self.assertEqual(error.exception.code, 'VERIFY_FAILED')


if __name__ == '__main__':
    unittest.main()
