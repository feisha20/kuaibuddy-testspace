#!/usr/bin/env python3
"""禅道 22.2 测试协作工具；仅依赖 Python3 标准库。"""

import argparse
import contextlib
import datetime as dt
import getpass
import hashlib
import html
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
import tempfile
import secrets
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / '.local' / 'config.json'
CASE_FIELDS = {'productID', 'title', 'module', 'story', 'pri', 'type', 'precondition',
               'steps', 'expects', 'stepType', 'project', 'execution'}
BUG_FIELDS = {'productID', 'title', 'openedBuild', 'project', 'execution', 'severity',
              'pri', 'type', 'steps', 'story', 'assignedTo', 'bugLabel', 'responsible'}
# 22.2 的 Bug 编辑对未提交字段按表单默认值处理（pri/severity 为3、type为codeerror），
# 只改执行等单个字段时会把优先级静默打回默认值；部分更新必须显式带回原值。
BUG_CARRY_FIELDS = ('pri', 'severity', 'type')
TASK_FIELDS = {'name', 'executionID', 'type', 'assignedTo', 'estStarted', 'deadline',
               'pri', 'estimate', 'module', 'story', 'desc', 'parent'}
TESTTASK_FIELDS = {'productID', 'name', 'build', 'execution', 'type', 'owner',
                   'status', 'begin', 'end', 'desc'}
ACTIONS = {'case.create', 'case.review', 'bug.create', 'bug.update', 'bug.attach', 'task.create', 'task.start',
           'testtask.create', 'testtask.linkcase', 'result.submit', 'result.report', 'task.update', 'case.update', 'task.finish', 'task.activate'}
RESULTS = {'pass', 'fail', 'blocked'}


class QAError(Exception):
    def __init__(self, code, message, uncertain=False):
        super().__init__(message)
        self.code, self.uncertain = code, uncertain


class MultipartBody:
    def __init__(self, body, content_type):
        self.body, self.content_type = body, content_type


def attachment_bytes(data):
    path = Path(data['path'])
    require(path.is_absolute() and path.is_file(), '截图需为存在的本地绝对文件路径。')
    with path.open('rb') as f:
        content = f.read(10 * 1024 * 1024 + 1)
    require(0 < len(content) <= 10 * 1024 * 1024 and len(content) == data['size'] and
            hashlib.sha256(content).hexdigest() == data['sha256'], '截图内容或大小已改变，停止上传。', 'CONFLICT')
    extension = Path(data['filename']).suffix.lower()
    require(extension == '.png' and content.startswith(b'\x89PNG\r\n\x1a\n'), '当前截图上传仅支持PNG原图，扩展名需与文件内容匹配。')
    return content


def image_multipart(data, bug_id):
    content = attachment_bytes(data)
    boundary = 'zentaoqa' + secrets.token_hex(24)
    mime = 'image/png'
    parts = []
    for name, value in [('objectType', 'bug'), ('objectID', str(bug_id))]:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{data["filename"]}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    parts.extend([content, f'\r\n--{boundary}--\r\n'.encode()])
    return MultipartBody(b''.join(parts), 'multipart/form-data; boundary=' + boundary)


def require(condition, message, code='INVALID_INPUT'):
    if not condition:
        raise QAError(code, message)


def positive(value):
    return type(value) is int and value > 0


def number_id(value):
    """列表可能同时包含 case_93 和 scene_93；场景不能作为用例。"""
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'(?:case_)?[1-9]\d*', value):
        return int(value.removeprefix('case_'))
    raise QAError('INVALID_ID', '需要真实对象编号，不能使用场景编号或空编号。')


# 用户列表只回传识别与指派所需的字段，不带登录IP、访问次数等无关信息。
USER_FIELDS = ('id', 'account', 'realname', 'pinyin', 'role', 'dept')


def public_user(user):
    return {field: user.get(field, '') for field in USER_FIELDS}


def user_matches(user, keyword, exact=False):
    """禅道按姓名指派前需换成登录账号；账号、姓名、拼音均可匹配。"""
    keyword = keyword.strip().lower()
    if not keyword:
        return True
    names = [str(user.get(k) or '').lower() for k in ('account', 'realname', 'nickname')]
    pinyin = str(user.get('pinyin') or '').lower().split()
    if exact:
        return keyword in names or keyword in pinyin
    return any(keyword in value for value in names + pinyin)


def require_login_account(data):
    """禅道按登录账号指派；中文姓名直接提交会落成不存在的账号。"""
    for field in ('assignedTo', 'responsible'):
        if field in data:
            require(data[field].isascii(),
                    f'{field} 必须填禅道登录账号，不能填中文姓名；请先运行 read users --kw 姓名 查询账号。')


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        raise QAError('LOCAL_FILE_ERROR', '无法读取 JSON 文件，请检查路径、权限和格式。') from None


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def safe_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.config-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 不把 Token 或写入请求自动转发到登录页或其他站点。
        return None


class Client:
    def __init__(self, url, token='', no_proxy=False, timeout=20):
        require(isinstance(url, str) and isinstance(token, str), '站点地址和Token必须是字符串。')
        parts = urllib.parse.urlsplit(url)
        require(parts.scheme in {'http', 'https'} and parts.hostname and
                not parts.username and not parts.password and not parts.query and
                not parts.fragment, '禅道地址必须是 http/https 站点根路径，不含凭据或查询参数。')
        self.url = url.rstrip('/')
        self.token = token
        self.no_proxy = no_proxy
        self.timeout = timeout
        self.reauthenticate = None
        self.last_failure = None
        self.private_values = []
        handlers = [NoRedirect()]
        if no_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def request(self, method, path, data=None, params=None, version=2, auth=True):
        self.last_failure = None
        refreshed = False
        if auth and not self.token and self.reauthenticate:
            self.reauthenticate()
            refreshed = True
        try:
            return self._request_once(method, path, data, params, version, auth)
        except QAError as e:
            if not (auth and e.code == 'AUTH_FAILED' and self.reauthenticate and not refreshed):
                raise
            self.reauthenticate()
            if method != 'GET':
                raise QAError('AUTH_REFRESHED_WRITE_STOPPED',
                              '已自动重新登录，但未重发写请求。请先核查远端是否已写入，并保留账本。', uncertain=True) from None
            return self._request_once(method, path, data, params, version, auth)

    def login(self, account, password):
        self.private_values.append(password)
        result = self.request('POST', '/users/login', {'account': account, 'password': password}, auth=False)
        require(result.get('status') == 'success' and isinstance(result.get('token'), str) and result['token'], '登录响应缺少Token。', 'AUTH_FAILED')
        if isinstance(result.get('user'), dict) and result['user'].get('account'):
            require(result['user']['account'] == account, '登录返回账号与请求不一致，未保存Token。', 'AUTH_FAILED')
        self.token = result['token']

    def probe_png(self, web_path):
        """按附件元数据读取同站点上传图片；不发送Token，不跟随跳转。"""
        require(isinstance(web_path, str) and web_path, '附件缺少webPath。', 'INVALID_RESPONSE')
        url = urllib.parse.urljoin(self.url + '/', web_path)
        base, target = urllib.parse.urlsplit(self.url), urllib.parse.urlsplit(url)
        require((base.scheme, base.netloc) == (target.scheme, target.netloc) and
                target.path.startswith(base.path.rstrip('/') + '/data/upload/') and
                not target.query and not target.fragment,
                '只允许核验当前站点附件元数据中的上传图片路径。', 'INVALID_RESPONSE')
        req = urllib.request.Request(url, headers={'Accept': 'image/png'}, method='GET')
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                content_type = response.headers.get('Content-Type', '')
                content = response.read(10 * 1024 * 1024 + 1)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise QAError('IMAGE_NOT_READABLE', '附件图片地址读取失败；已上传的文件不能自动重传。') from None
        require(0 < len(content) <= 10 * 1024 * 1024 and content.startswith(b'\x89PNG\r\n\x1a\n'),
                '图片地址未返回有效PNG字节，不能用于正文图片。', 'IMAGE_NOT_READABLE')
        return {'url': url, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                'contentType': content_type, 'isPNG': True}

    def _request_once(self, method, path, data=None, params=None, version=2, auth=True):
        require(path.startswith('/') and '?' not in path, '接口路径格式错误。')
        url = self.url + f'/api.php/v{version}' + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        headers = {'Accept': 'application/json'}
        if auth:
            require(self.token, '缺少 Token，请先登录或设置 ZENTAO_TOKEN。', 'AUTH_REQUIRED')
            headers['Token'] = self.token
        body = None
        if isinstance(data, MultipartBody):
            headers['Content-Type'] = data.content_type
            body = data.body
        elif data is not None:
            headers['Content-Type'] = 'application/json; charset=utf-8'
            body = json.dumps(data, ensure_ascii=False).encode()
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        mutating = method != 'GET'
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                require(len(raw) <= 16 * 1024 * 1024, '响应过大，结果不确定。', 'INVALID_RESPONSE')
        except urllib.error.HTTPError as e:
            code = 'AUTH_FAILED' if e.code == 401 else 'PERMISSION_DENIED' if e.code == 403 else 'NOT_FOUND' if e.code == 404 else 'HTTP_ERROR'
            e.close()
            raise QAError(code, f'禅道接口返回 HTTP {e.code}；{method} v{version}{path}。',
                          uncertain=mutating and e.code not in {401, 403, 404, 405}) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            raise QAError('NETWORK_ERROR', '连接失败或超时；写请求可能已送达，请先核查再处理。' if mutating else '连接失败或超时，请检查地址、代理及网络。', uncertain=mutating) from None
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise QAError('INVALID_RESPONSE', '接口未返回 JSON，可能是登录页或不支持的路由。', uncertain=mutating) from None
        if isinstance(result, dict):
            if result.get('status') == 'fail' or result.get('result') == 'fail' or result.get('error'):
                message = result.get('message', result.get('error', '业务接口拒绝，未提供原因。'))
                message = message if isinstance(message, str) else canonical(message)
                for secret in [self.token, *self.private_values]:
                    if secret:
                        message = message.replace(secret, '[已隐藏]')
                self.last_failure = {'message': message[:1200]}
                # 不回显原始响应，以免接口错误包含凭据或业务正文。
                raise QAError('BUSINESS_ERROR', f'禅道拒绝本次操作；{method} v{version}{path}。', uncertain=mutating)
        else:
            # 22.2 v1 提交执行结果成功时返回 []。
            if not (version == 1 and method == 'POST' and result == []):
                raise QAError('INVALID_RESPONSE', '接口响应结构不符合约定。', uncertain=mutating)
        return result

    def detail(self, kind, object_id):
        object_id = number_id(object_id)
        paths = {'story': ('stories', 'story', 2), 'case': ('testcases', 'testcase', 2),
                 'bug': ('bugs', 'bug', 2), 'execution': ('executions', 'execution', 2),
                 'project': ('projects', 'project', 2), 'task': ('tasks', 'task', 2),
                 'testtask': ('testtasks', None, 1)}
        path, key, version = paths[kind]
        result = self.request('GET', f'/{path}/{object_id}', version=version)
        value = result.get(key) if key else result
        require(isinstance(value, dict) and str(value.get('id')) == str(object_id),
                '详情缺少匹配的对象编号，不能认定查询成功。', 'INVALID_RESPONSE')
        return value

    def listing(self, path, key, all_pages=False, page=1, size=100):
        require(not all_pages or page == 1, '完整清单必须从第1页开始读取。')
        records, seen = [], set()
        pager = None
        for _ in range(1000):
            result = self.request('GET', path, params={'pageID': page, 'recPerPage': size})
            values = result.get(key)
            require(isinstance(values, (list, dict)), f'响应缺少 {key} 列表。', 'INVALID_RESPONSE')
            values = list(values.values()) if isinstance(values, dict) else values
            require(all(isinstance(x, dict) for x in values), '列表包含异常条目。', 'INVALID_RESPONSE')
            fingerprint = digest(values)
            require(not values or fingerprint not in seen, '接口重复返回同一页，已停止，不能认定列表完整。', 'PAGINATION_ERROR')
            seen.add(fingerprint)
            records.extend(values)
            pager = result.get('pager')
            if not all_pages:
                return {'items': records, 'pager': pager, 'complete': False}
            if not values:
                return {'items': records, 'pager': pager, 'complete': True}
            if isinstance(pager, dict) and pager.get('pageTotal') is not None:
                if page >= int(pager['pageTotal']):
                    return {'items': records, 'pager': pager, 'complete': True}
            elif len(values) < size:
                return {'items': records, 'pager': pager, 'complete': True}
            page += 1
        raise QAError('PAGINATION_ERROR', '超过分页上限，不能认定列表完整。')

    def testtask(self, task_id):
        """v1 测试单详情的 testcases 也分页，不能只检查第一页。"""
        records, seen = [], set()
        task_id = number_id(task_id)
        for page in range(1, 1001):
            value = self.request('GET', f'/testtasks/{task_id}',
                                 params={'page': page, 'limit': 100}, version=1)
            require(str(value.get('id')) == str(task_id) and isinstance(value.get('testcases'), list),
                    '测试单详情格式异常。', 'INVALID_RESPONSE')
            rows = value['testcases']
            fingerprint = digest(rows)
            require(not rows or fingerprint not in seen, '测试单重复返回同一页。', 'PAGINATION_ERROR')
            seen.add(fingerprint)
            records.extend(rows)
            if len(rows) < 100:
                value['testcases'] = records
                return value
        raise QAError('PAGINATION_ERROR', '测试单用例超出分页上限。')

    def history(self, case_id, run_id=0):
        params = {'runID': run_id} if run_id else None
        value = self.request('GET', f'/testcases/{number_id(case_id)}/results', params=params, version=1)
        require(isinstance(value.get('results'), list), '执行历史格式异常。', 'INVALID_RESPONSE')
        return value['results']


def validate_operation(op):
    require(isinstance(op, dict), '每项操作必须为对象。')
    require(set(op) <= {'key', 'action', 'targetId', 'data', 'expected', 'autoReview'}, '操作含有未知字段。')
    require(isinstance(op.get('key'), str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}', op['key']), 'key 必须是稳定的英文、数字或 . _ : - 标识，最长120字符。')
    action, data = op.get('action'), op.get('data')
    require(isinstance(action, str) and action in ACTIONS, '不支持该操作。')
    require(isinstance(data, dict) and data, 'data 必须是非空对象。')
    if 'autoReview' in op:
        require(action == 'case.create' and type(op['autoReview']) is bool, 'autoReview仅适用于case.create，且必须为布尔值。')
    expected = op.get('expected', {})
    require(isinstance(expected, dict) and set(expected) <= {'storyVersion', 'lastEditedDate', 'caseVersion', 'storyId'}, 'expected 仅支持 storyVersion、lastEditedDate、caseVersion、storyId。')
    if 'storyVersion' in expected:
        require(positive(expected['storyVersion']), 'storyVersion 必须为正整数。')
    if action in {'testtask.linkcase', 'result.report'}:
        require(type(expected.get('storyId')) is int and expected['storyId'] >= 0,
                '关联用例或记录整体结果需提供expected.storyId。')
    if action == 'bug.attach':
        require(positive(op.get('targetId')) and type(expected.get('storyId')) is int and expected['storyId'] >= 0,
                '截图上传需要Bug targetId与expected.storyId。')
    elif action == 'bug.update':
        require(positive(op.get('targetId')) and isinstance(expected.get('lastEditedDate'), str),
                '修改 Bug 需 targetId 和读取时的 expected.lastEditedDate；未编辑过时可为空字符串。')
    elif action in {'case.review', 'case.update'}:
        require(positive(op.get('targetId')) and positive(expected.get('caseVersion')) and
                type(expected.get('storyId')) is int and expected['storyId'] >= 0 and
                isinstance(expected.get('lastEditedDate'), str),
                '用例评审需要targetId及expected.caseVersion/storyId/lastEditedDate，未修改用例的lastEditedDate可为空字符串。')
    elif action in {'task.start', 'task.update', 'task.finish', 'task.activate'}:
        require(positive(op.get('targetId')) and type(expected.get('storyId')) is int and
                expected['storyId'] >= 0 and isinstance(expected.get('lastEditedDate'), str),
                '启动任务需要targetId及expected.storyId/lastEditedDate，未修改时lastEditedDate用空字符串。')
    else:
        require('targetId' not in op, '仅 bug.update、case.review 和 task.start 接受 targetId。')
    fields, required = {
        'case.create': (CASE_FIELDS, {'productID', 'title', 'steps', 'expects'}),
        'case.update': ({'title', 'precondition', 'pri', 'type', 'steps', 'expects'}, set()),
        'task.update': ({'name', 'assignedTo', 'desc', 'pri', 'estimate', 'estStarted', 'deadline'}, set()),
        'case.review': ({'result', 'reviewedBy', 'reviewedDate', 'comment'}, {'result', 'reviewedBy'}),
        'bug.create': (BUG_FIELDS, {'productID', 'title', 'openedBuild', 'steps'}),
        'bug.update': (BUG_FIELDS - {'productID'}, set()),
        'bug.attach': ({'path', 'filename', 'sha256', 'size'}, {'path', 'filename', 'sha256', 'size'}),
        'task.create': (TASK_FIELDS, {'name', 'executionID'}),
        'task.start': ({'left', 'consumed', 'assignedTo', 'realStarted', 'comment'}, {'left', 'consumed', 'assignedTo'}),
        'task.finish': ({'currentConsumed', 'consumed', 'assignedTo', 'realStarted', 'comment'}, {'currentConsumed', 'consumed', 'assignedTo', 'realStarted'}),
        'task.activate': ({'left', 'assignedTo', 'consumed', 'comment'}, {'left', 'assignedTo', 'consumed'}),
        'testtask.create': (TESTTASK_FIELDS, {'productID', 'name', 'build', 'begin', 'end'}),
        'testtask.linkcase': ({'caseId', 'caseVersion', 'testtaskId'}, {'caseId', 'caseVersion', 'testtaskId'}),
        'result.report': ({'caseId', 'caseVersion', 'testtaskId', 'result', 'report'}, {'caseId', 'caseVersion', 'testtaskId', 'result', 'report'}),
        'result.submit': ({'caseId', 'caseVersion', 'testtaskId', 'steps', 'result', 'evidence', 'startedAt', 'finishedAt', 'simulation'}, {'caseId', 'caseVersion', 'testtaskId', 'steps', 'result', 'evidence'})
    }[action]
    require(set(data) <= fields and required <= set(data), 'data 存在未知字段或缺少必填字段，请查 references/commands.md。')
    if action == 'bug.attach':
        require(isinstance(data['path'], str) and isinstance(data['filename'], str) and
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', data['filename']) and
                isinstance(data['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', data['sha256']) and
                positive(data['size']), '截图需绝对路径、安全文件名、SHA256及正整数size。')
        attachment_bytes(data)
    for field in ('productID', 'executionID', 'caseId', 'caseVersion', 'testtaskId', 'build'):
        if field in data:
            require(positive(data[field]), f'{field} 必须是正整数。')
    for field in ('story', 'module', 'project', 'execution', 'parent'):
        if field in data:
            require(type(data[field]) is int and data[field] >= 0, f'{field} 必须是非负整数。')
    for field in ('title', 'name', 'steps'):
        if field in data and field != 'steps':
            require(isinstance(data[field], str) and data[field].strip(), f'{field} 不能为空。')
    for field in ('pri', 'severity'):
        if field in data:
            require(type(data[field]) is int and data[field] in {1, 2, 3, 4}, f'{field} 范围为1至4。')
    for field in ('precondition', 'desc', 'assignedTo', 'responsible', 'owner', 'estStarted', 'deadline'):
        if field in data:
            require(isinstance(data[field], str), f'{field} 必须为字符串。')
    if 'estimate' in data:
        import math
        require(type(data['estimate']) in {int, float} and math.isfinite(data['estimate']) and data['estimate'] >= 0, '预计工时必须是有限的非负数。')
    if 'type' in data and action != 'testtask.create':
        require(isinstance(data['type'], str), 'type必须为字符串。')
    if data.get('story'):
        require(positive(expected.get('storyVersion')), '关联需求的写入需 expected.storyVersion，防止使用旧需求。')
    if action == 'case.review':
        require(data['result'] == 'pass', '当前仅支持按用户明确确认进行评审通过，result必须为pass。')
        require(isinstance(data['reviewedBy'], list) and len(data['reviewedBy']) == 1 and
                isinstance(data['reviewedBy'][0], str) and data['reviewedBy'][0].strip(),
                'reviewedBy必须包含一个实际评审账号。')
        require(isinstance(data.get('comment', ''), str), '评审意见comment必须为字符串。')
        if 'reviewedDate' in data:
            try:
                require(isinstance(data['reviewedDate'], str) and dt.date.fromisoformat(data['reviewedDate']).isoformat() == data['reviewedDate'],
                        'reviewedDate必须为YYYY-MM-DD日期。')
            except (TypeError, ValueError):
                raise QAError('INVALID_INPUT', 'reviewedDate必须为YYYY-MM-DD日期。') from None
    if action == 'case.update':
        if 'type' in data:
            require(data['type'] in {'unit', 'interface', 'feature', 'install', 'config', 'performance', 'security', 'other'}, '不支持的用例类型。')
        require(('steps' in data) == ('expects' in data), '修改步骤须同时提供steps与expects。')
    if action == 'case.create' or (action == 'case.update' and 'steps' in data):
        steps, expects = data['steps'], data['expects']
        require(isinstance(steps, list) and steps and isinstance(expects, list) and len(steps) == len(expects), '用例步骤与预期必须是长度一致的非空数组。')
        require(all(isinstance(x, str) and x.strip() for x in steps + expects), '步骤与预期不能为空。')
        require(data.get('stepType', ['step'] * len(steps)) == ['step'] * len(steps), 'MVP 仅支持平铺步骤，不支持步骤分组。')
        require(data.get('type', 'feature') in {'unit', 'interface', 'feature', 'install', 'config', 'performance', 'security', 'other'}, '不支持的用例类型。')
    if action.startswith('bug.'):
        if 'bugLabel' in data:
            require(isinstance(data['bugLabel'], list) and data['bugLabel'] and
                    all(isinstance(x, str) and x.strip() for x in data['bugLabel']),
                    '公司自定义bugLabel使用非空字符串数组，值需从实例现有记录或表单核实。')
        if 'openedBuild' in data:
            require(isinstance(data['openedBuild'], list) and data['openedBuild'] and all(positive(x) or x == 'trunk' for x in data['openedBuild']), 'openedBuild 使用非空数组，元素为数字构建ID或 trunk。')
        if 'steps' in data:
            require(isinstance(data['steps'], str) and data['steps'].strip(), 'Bug 重现步骤不能为空。')
        require_login_account(data)
    if action == 'task.update':
        require_login_account(data)
        if 'assignedTo' in data:
            require(bool(data['assignedTo'].strip()), '负责人不能为空。')
    if action == 'task.create':
        require(data.get('type', 'test') == 'test', '本 Skill 仅创建 type=test 的测试工作任务。')
        require_login_account(data)
    if action == 'task.activate':
        import math
        require_login_account(data)
        require(isinstance(data['assignedTo'], str) and bool(data['assignedTo'].strip()), '需提供实际负责人。')
        require(type(data['left']) in {int, float} and math.isfinite(data['left']) and data['left'] > 0, '预计剩余工时必须为正数。')
        require(type(data['consumed']) in {int, float} and math.isfinite(data['consumed']) and data['consumed'] >= 0, '已消耗工时必须为非负数。')
        require(isinstance(data.get('comment', ''), str), '备注必须为字符串。')
    if action == 'task.finish':
        import math
        require_login_account(data)
        for field in ('currentConsumed', 'consumed'):
            require(type(data[field]) in {int, float} and math.isfinite(data[field]) and data[field] >= 0,
                    '实际工时必须是有限非负数。')
        require(bool(data['assignedTo'].strip()) and isinstance(data.get('comment', ''), str), '需提供实际负责人。')
        try:
            dt.datetime.strptime(data['realStarted'], '%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            raise QAError('INVALID_INPUT', '实际开始时间必须是原任务的时间。') from None
    if action == 'task.start':
        import math
        require(type(data['left']) in {int, float} and math.isfinite(data['left']) and data['left'] >= 0.01,
                '预计剩余工时必须由用户确认且至少0.01小时；禅道剩余工时为0会直接完成任务。')
        require(type(data['consumed']) in {int, float} and math.isfinite(data['consumed']) and data['consumed'] >= 0,
                'consumed必须是读取到的现有总消耗工时。')
        require(bool(data['assignedTo'].strip()) and isinstance(data.get('comment', ''), str), '需要实际负责人，备注必须为字符串。')
        if 'realStarted' in data:
            try:
                require(dt.datetime.strptime(data['realStarted'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S') == data['realStarted'],
                        'realStarted必须精确到秒。')
            except (TypeError, ValueError):
                raise QAError('INVALID_INPUT', 'realStarted必须为YYYY-MM-DD HH:MM:SS。') from None
    if action == 'testtask.create':
        if 'type' in data:
            require(isinstance(data['type'], list) and data['type'] and all(isinstance(x, str) and x in {'integrate', 'system', 'acceptance', 'performance', 'safety'} for x in data['type']), '测试单type必须是有效类型的非空数组。')
        if 'status' in data:
            require(isinstance(data['status'], str) and data['status'] in {'wait', 'doing', 'done', 'blocked'}, '测试单status无效。')
        try:
            require(dt.date.fromisoformat(data['begin']) <= dt.date.fromisoformat(data['end']), '结束日期不能早于开始日期。')
        except (ValueError, TypeError):
            raise QAError('INVALID_INPUT', '测试单日期必须为 YYYY-MM-DD。') from None
    if action == 'result.report':
        require(isinstance(data['result'], str) and data['result'] in {'fail', 'blocked'} and isinstance(data['report'], str) and data['report'].strip(),
                '整体报告仅支持明确报告的fail/blocked，且需非空来源说明；逐步结果使用result.submit。')
    if action == 'result.submit':
        require(isinstance(data['result'], str) and data['result'] in RESULTS, 'MVP 执行结果仅支持 pass/fail/blocked；跳过和未执行不提交。')
        require(isinstance(data['evidence'], list) and data['evidence'] and all(isinstance(x, str) and x.strip() for x in data['evidence']), '执行结果需要非空的证据路径或证据说明数组。')
        require(type(data.get('simulation', False)) is bool, 'simulation必须为布尔值。')
        if data.get('simulation', False):
            require('startedAt' not in data and 'finishedAt' not in data, '模拟调试不填写真实执行起止时间。')
        else:
            require('startedAt' in data and 'finishedAt' in data, '真实执行结果需要原始起止时间；仅用户明确授权模拟时使用simulation=true。')
            try:
                begin = dt.datetime.fromisoformat(data['startedAt'])
                end = dt.datetime.fromisoformat(data['finishedAt'])
                require(begin.tzinfo is not None and end.tzinfo is not None and end >= begin, '执行时间需含时区且结束不早于开始。')
            except (ValueError, TypeError):
                raise QAError('INVALID_INPUT', '执行时间必须使用含时区的 ISO 日期。') from None
        require(isinstance(data['steps'], list) and data['steps'], '执行结果需逐步结果。')
        for step in data['steps']:
            require(isinstance(step, dict) and set(step) == {'stepId', 'result', 'actual'}, '每步必须且仅包含 stepId/result/actual。')
            require(positive(step['stepId']) and isinstance(step['result'], str) and step['result'] in RESULTS and isinstance(step['actual'], str) and step['actual'].strip(), '步骤ID、结果或实际现象无效。')
        states = {s['result'] for s in data['steps']}
        overall = 'fail' if 'fail' in states else 'blocked' if 'blocked' in states else 'pass'
        require(data['result'] == overall, '整体结果与步骤结果不一致。')


def load_plan(path):
    plan = read_json(path)
    require(isinstance(plan, dict) and set(plan) == {'schemaVersion', 'operations'} and type(plan.get('schemaVersion')) is int and plan.get('schemaVersion') == 1,
            '计划需包含 schemaVersion=1 和 operations。')
    ops = plan['operations']
    require(isinstance(ops, list) and 1 <= len(ops) <= 100, '每批操作数为1至100。')
    keys = set()
    for op in ops:
        validate_operation(op)
        require(op['key'] not in keys, '同一批次操作 key 不能重复。')
        keys.add(op['key'])
    return plan


def preflight(client, op):
    data, action = op['data'], op['action']
    if action in {'task.update', 'case.update'}:
        kind = action.split('.')[0]
        current = client.detail(kind, op['targetId'])
        require(str(current.get('story') or 0) == str(op['expected']['storyId']) and
                (current.get('lastEditedDate') or '') == op['expected']['lastEditedDate'],
                '对象关联需求或修改时间已变化，停止编辑。', 'CONFLICT')
        require(str(current.get('deleted', 0)) in {'0', 'False', 'false'}, '对象已删除。', 'CONFLICT')
        if kind == 'case':
            require(str(current.get('version')) == str(op['expected']['caseVersion']), '用例版本已变化。', 'CONFLICT')
            steps = current.get('steps')
            require(isinstance(steps, list) and steps and all(x.get('type', 'step') == 'step' and
                    isinstance(x.get('desc'), str) and isinstance(x.get('expect'), str) for x in steps),
                    '仅支持完整读取的平铺用例步骤，停止编辑。', 'SCOPE_MISMATCH')
            for field in ('title', 'precondition', 'pri', 'type', 'module', 'story'):
                require(field in current and current[field] is not None, '用例原字段不完整，停止编辑。', 'INVALID_RESPONSE')
        else:
            require(current.get('type') == 'test', '仅支持编辑测试工作任务。', 'SCOPE_MISMATCH')
        return {'before': current}
    if action == 'bug.attach':
        attachment_bytes(data)
        bug = client.detail('bug', op['targetId'])
        require(str(bug.get('story')) == str(op['expected']['storyId']) and
                str(bug.get('deleted', 0)) in {'0', 'False'}, '目标Bug需求不匹配或已删除。', 'SCOPE_MISMATCH')
        return {}
    if action in {'testtask.linkcase', 'result.report'}:
        case, task, runs = execution_context(client, op)
        if action == 'result.report':
            require(len(runs) == 1, '测试单尚未关联该用例，请先关联。', 'CASE_NOT_LINKED')
        return {'runId': number_id(runs[0]['id']) if runs else 0, 'productId': number_id(case['product']),
                'stepIds': [number_id(s['id']) for s in case.get('steps', [])]}
    if action == 'task.activate':
        task = client.detail('task', op['targetId'])
        require(task.get('type') == 'test' and task.get('status') == 'done', '仅支持激活已完成测试任务。', 'CONFLICT')
        require(str(task.get('story') or 0) == str(op['expected']['storyId']) and
                (task.get('lastEditedDate') or '') == op['expected']['lastEditedDate'], '任务已变化。', 'CONFLICT')
        require(task.get('assignedTo') == data['assignedTo'] and float(task.get('consumed', 0)) == data['consumed'],
                '负责人或已消耗工时已变化。', 'CONFLICT')
        return {}
    if action == 'task.finish':
        task = client.detail('task', op['targetId'])
        require(task.get('type') == 'test' and str(task.get('isParent', 0)) == '0' and task.get('status') == 'doing',
                '仅支持完成进行中的叶子测试任务。', 'CONFLICT')
        require(str(task.get('story') or 0) == str(op['expected']['storyId']) and
                (task.get('lastEditedDate') or '') == op['expected']['lastEditedDate'], '任务已变化。', 'CONFLICT')
        require(task.get('assignedTo') == data['assignedTo'] and float(task.get('consumed', 0)) == data['consumed'] and
                task.get('realStarted') == data['realStarted'], '负责人、已消耗工时或实际开始时间已变化。', 'CONFLICT')
        return {}
    if action == 'task.start':
        task = client.detail('task', op['targetId'])
        require(task.get('type') == 'test' and str(task.get('isParent', 0)) == '0', '仅支持启动叶子测试任务。', 'SCOPE_MISMATCH')
        require(task.get('status') == 'wait', '任务当前不是未开始状态，停止重复启动。', 'CONFLICT')
        require(str(task.get('story')) == str(op['expected']['storyId']) and
                (task.get('lastEditedDate') or '') == op['expected']['lastEditedDate'], '任务需求或修改时间已变化。', 'CONFLICT')
        require(task.get('assignedTo') == data['assignedTo'] and float(task.get('consumed', 0)) == data['consumed'],
                '任务负责人或已消耗工时已变化，停止启动。', 'CONFLICT')
        return {}
    if action == 'case.review':
        case = client.detail('case', op['targetId'])
        expected = op['expected']
        require(str(case.get('version')) == str(expected['caseVersion']) and
                str(case.get('story')) == str(expected['storyId']) and
                (case.get('lastEditedDate') or '') == expected['lastEditedDate'],
                '用例版本、关联需求或修改时间已变化，请重新读取并确认评审。', 'CONFLICT')
        require(case.get('status') == 'wait', '该用例当前不是待评审状态，停止重复评审。', 'CONFLICT')
        return {}
    if data.get('story'):
        story = client.detail('story', data['story'])
        require(int(story.get('version', 0)) == op['expected']['storyVersion'], '需求版本已变化，请重新设计并生成计划。', 'CONFLICT')
        if data.get('productID'):
            require(str(story.get('product')) == str(data['productID']), '需求与产品不一致。', 'SCOPE_MISMATCH')
    if data.get('executionID') or data.get('execution'):
        execution_id = data.get('executionID', data.get('execution'))
        execution = client.detail('execution', execution_id)
        if data.get('project'):
            require(str(execution.get('project')) == str(data['project']), '冲刺与项目不一致。', 'SCOPE_MISMATCH')
        if data.get('story'):
            stories = client.listing(f'/executions/{execution_id}/stories', 'stories', True)
            require(any(str(s.get('id')) == str(data['story']) for s in stories['items']),
                    '该需求未关联所选冲刺，停止写入。', 'SCOPE_MISMATCH')
    if action == 'bug.update':
        current = client.detail('bug', op['targetId'])
        require((current.get('lastEditedDate') or '') == op['expected']['lastEditedDate'], 'Bug 已被修改，请重新读取并生成变更计划。', 'CONFLICT')
    if action == 'task.create' and data.get('parent'):
        parent = client.detail('task', data['parent'])
        require(str(parent.get('execution')) == str(data['executionID']), '父任务与子任务不在同一冲刺。', 'SCOPE_MISMATCH')
        require(parent.get('type') == 'test', '测试子任务只能关联测试类型的父任务。', 'SCOPE_MISMATCH')
        require(parent.get('status') in {'wait', 'doing', 'pause'}, '父任务已完成、取消或关闭，停止新增子任务。', 'CONFLICT')
    if action == 'result.submit':
        case = client.detail('case', data['caseId'])
        require(int(case.get('version', 0)) == data['caseVersion'], '用例版本已变化，停止回写。', 'CONFLICT')
        steps = case.get('steps', [])
        require(isinstance(steps, list) and all(s.get('type', 'step') == 'step' for s in steps), 'MVP 不支持分组步骤的结果回写。')
        require([int(s['id']) for s in steps] == [s['stepId'] for s in data['steps']], '步骤ID、顺序或数量与当前用例不一致。', 'CONFLICT')
        task = client.testtask(data['testtaskId'])
        require(str(task.get('product')) == str(case.get('product')), '测试单与用例产品不一致。', 'SCOPE_MISMATCH')
        runs = [r for r in task['testcases'] if str(r.get('case')) == str(data['caseId'])]
        require(len(runs) == 1 and int(runs[0].get('version', 0)) == data['caseVersion'],
                '测试单尚未关联该用例，或关联版本不同。请先使用testtask.linkcase完成关联。', 'CASE_NOT_LINKED')
        return {'runId': number_id(runs[0]['id'])}
    return {}


def execution_context(client, op):
    """仅向同产品、同需求的当前正常用例追加关联或明确报告的结果。"""
    data = op['data']
    case = client.detail('case', data['caseId'])
    require(str(case.get('version')) == str(data['caseVersion']) and
            str(case.get('story')) == str(op['expected']['storyId']), '用例版本或需求已变化。', 'CONFLICT')
    require(case.get('status') == 'normal' and str(case.get('deleted', 0)) in {'0', 'False'},
            '仅支持正常且未删除的用例。', 'CONFLICT')
    task = client.testtask(data['testtaskId'])
    require(task.get('status') in {'wait', 'doing'} and str(task.get('deleted', 0)) in {'0', 'False'},
            '测试单已结束、阻塞或删除，停止写入。', 'CONFLICT')
    require(str(task.get('product')) == str(case.get('product')), '测试单与用例产品不一致。', 'SCOPE_MISMATCH')
    if int(case.get('execution') or 0):
        require(str(task.get('execution')) == str(case['execution']), '测试单与用例冲刺不一致。', 'SCOPE_MISMATCH')
    runs = [r for r in task['testcases'] if str(r.get('case')) == str(data['caseId'])]
    require(len(runs) <= 1 and all(str(r.get('version')) == str(data['caseVersion']) for r in runs),
            '已有重复关联或版本不同，禁止覆盖执行条目。', 'CONFLICT')
    require(all(s.get('type', 'step') == 'step' for s in case.get('steps', [])), 'MVP不支持分组步骤。')
    return case, task, runs


def submit(client, op):
    action, data = op['action'], dict(op['data'])
    if action in {'task.update', 'case.update'}:
        current = preflight(client, op)['before']
        if action == 'case.update':
            payload = {field: current[field] for field in ('title', 'precondition', 'pri', 'type', 'module', 'story')}
            payload.update({'steps': [x['desc'] for x in current['steps']],
                            'expects': [x['expect'] for x in current['steps']],
                            'stepType': ['step'] * len(current['steps'])})
            payload.update(data)
            for field in ('module', 'story', 'pri'):
                payload[field] = int(payload[field])
            path = f"/testcases/{op['targetId']}"
        else:
            payload = {field: current[field] for field in ('name', 'type', 'pri', 'estimate', 'module', 'story', 'desc') if current.get(field) is not None}
            for field in ('pri', 'module', 'story'):
                if field in payload: payload[field] = int(payload[field])
            if 'estimate' in payload: payload['estimate'] = float(payload['estimate'])
            payload.update(data)
            path = f"/tasks/{op['targetId']}"
        response = client.request('PUT', path, payload)
        require(isinstance(response, dict) and response.get('status') == 'success',
                '编辑响应未明确成功，需核查远端。', 'INVALID_RESPONSE')
        return {'id': op['targetId'], 'before': current, 'sent': payload}
    if action == 'bug.attach':
        response = client.request('POST', '/files', image_multipart(data, op['targetId']))
        require(response.get('status') == 'success' and response.get('id') and isinstance(response.get('url'), str),
                '上传响应未明确返回文件ID和URL，请核查远端附件。', 'INVALID_RESPONSE')
        url = urllib.parse.urljoin(client.url + '/', response['url'])
        origin, target = urllib.parse.urlsplit(client.url), urllib.parse.urlsplit(url)
        require((origin.scheme, origin.netloc) == (target.scheme, target.netloc) and not target.fragment,
                '上传返回的图片URL不属于当前站点，停止使用。', 'INVALID_RESPONSE')
        return {'id': number_id(response['id']), 'url': url, 'bugId': op['targetId']}
    if action == 'testtask.linkcase':
        context = preflight(client, op)
        if not context['runId']:
            response = client.request('PUT', f"/testtasks/{data['testtaskId']}/linkCase",
                                      {'case': [data['caseId']], 'version': [data['caseVersion']]})
            require(response.get('status') == 'success', '关联响应未明确成功，需要核查远端。', 'INVALID_RESPONSE')
        return {'id': data['testtaskId']}
    if action == 'result.report':
        context = preflight(client, op)
        key = str(data['caseId'])
        note = f"用户报告整体结果：{data['result']}。{data['report']}\n步骤结果未提供；未记录原始执行时间。\n[zentao-qa:{op['key']}]"
        # batchRun独立保存caseResult；空步骤结果避免把整例失败误记为每步失败。
        step_ids = context['stepIds'] or [0]
        response = client.request('PUT', '/testtasks/batchRun',
                                  {'results': {key: data['result']}, 'version': {key: data['caseVersion']},
                                   'steps': {key: {str(s): '' for s in step_ids}},
                                   'reals': {key: {str(s): note for s in step_ids}}},
                                  params={'productID': context['productId'], 'orderBy': 'id_desc',
                                          'from': 'testtask', 'testtaskID': data['testtaskId']})
        require(response.get('status') == 'success', '整体结果响应未明确成功，需要核查远端。', 'INVALID_RESPONSE')
        return {'id': data['caseId'], 'runId': context['runId'], 'note': note}
    if action == 'task.activate':
        preflight(client, op)
        payload = {key: value for key, value in data.items() if key != 'consumed'}
        response = client.request('PUT', f"/tasks/{op['targetId']}/activate", payload)
        require(isinstance(response, dict) and response.get('status') == 'success', '激活响应未明确成功，需要核查。', 'INVALID_RESPONSE')
        return {'id': op['targetId']}
    if action == 'task.finish':
        preflight(client, op)
        data['finishedDate'] = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        data['consumed'] = data['consumed'] + data['currentConsumed']
        response = client.request('PUT', f"/tasks/{op['targetId']}/finish", data)
        require(isinstance(response, dict) and response.get('status') == 'success', '完成响应未明确成功，需要核查。', 'INVALID_RESPONSE')
        return {'id': op['targetId'], 'finishedDate': data['finishedDate']}
    if action == 'task.start':
        data.setdefault('realStarted', dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'))
        response = client.request('PUT', f"/tasks/{op['targetId']}/start", data)
        require(isinstance(response, dict) and response.get('status') == 'success', '启动响应未明确成功，需要核查远端。', 'INVALID_RESPONSE')
        return {'id': op['targetId'], 'realStarted': data['realStarted']}
    if action == 'case.review':
        # 22.2表单默认值可能为完整时间戳，必须显式发送日期以通过服务端日期校验。
        data.setdefault('reviewedDate', dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat())
        response = client.request('PUT', f"/testcases/{op['targetId']}/review", data)
        require(isinstance(response, dict) and response.get('status') == 'success',
                '评审响应未明确成功，需要核查远端。', 'INVALID_RESPONSE')
        return {'id': op['targetId']}
    if action == 'result.submit':
        marker = f"[zentao-qa:{op['key']}]"
        time_note = ('【调试模拟，非真实产品测试结果】未执行实际产品操作，未记录真实执行起止时间。'
                     if data.get('simulation', False) else f"执行时间：{data['startedAt']} 至 {data['finishedAt']}")
        context = '\n'.join([marker, time_note, '证据/来源：' + '；'.join(data['evidence'])])
        steps = [{'result': s['result'], 'real': s['actual'] + '\n' + context} for s in data['steps']]
        client.request('POST', f"/testcases/{data['caseId']}/results", {'steps': steps},
                       params={'testtask': data['testtaskId'], 'version': data['caseVersion']}, version=1)
        return {'id': data['caseId']}
    if action == 'case.create':
        data.setdefault('type', 'feature')
        data.setdefault('pri', 3)
        data.setdefault('stepType', ['step'] * len(data['steps']))
    if action == 'task.create':
        data.setdefault('type', 'test')
    if action == 'bug.update':
        current = client.detail('bug', op['targetId'])
        carried = {}
        for field in BUG_CARRY_FIELDS:
            value = current.get(field)
            if field in data or value in (None, '', 0, '0'):
                continue
            carried[field] = int(value) if field in {'pri', 'severity'} else str(value)
        data.update(carried)
        response = client.request('PUT', f"/bugs/{op['targetId']}", data)
        require(isinstance(response, dict) and response.get('status') == 'success', '写入响应没有明确成功状态，需要核查。', 'INVALID_RESPONSE')
        return {'id': op['targetId'], 'carried': carried}
    path = {'case.create': '/testcases', 'bug.create': '/bugs', 'task.create': '/tasks',
            'testtask.create': '/testtasks'}[action]
    response = client.request('POST', path, data)
    require(isinstance(response, dict) and response.get('status') == 'success', '写入响应没有明确成功状态，需要核查。', 'INVALID_RESPONSE')
    require(positive(response.get('id')) or (isinstance(response.get('id'), str) and response['id'].isdigit()),
            '创建响应缺少对象ID，需要核查。', 'INVALID_RESPONSE')
    return {'id': number_id(response['id'])}


def normalized_text(value):
    if value is None:
        return ''
    value = html.unescape(str(value)).replace('\r\n', '\n')
    return value.strip()


def normalized_bug_steps(value):
    # 编辑器会移除相邻块元素间的换行；保留段内文字、空格及内联标签。
    value = normalized_text(value)
    return re.sub(r'(</(?:p|ol|ul|li|div|h[1-6])>)\s+(?=<(?:p|ol|ul|li|div|h[1-6])(?:\s|>))',
                  r'\1', value, flags=re.I)


def verify(client, op, remote):
    action, data = op['action'], op['data']
    if action == 'task.activate':
        task = client.detail('task', op['targetId'])
        require(task.get('status') in {'wait', 'doing'} and task.get('assignedTo') == data['assignedTo'] and
                abs(float(task.get('consumed', -1)) - data['consumed']) < 0.00001,
                '激活后状态、负责人或历史工时回读不一致。', 'VERIFY_FAILED')
        return {'id': number_id(task['id']), 'status': task['status'], 'consumed': task['consumed'], 'left': task.get('left')}
    if action == 'task.finish':
        task = client.detail('task', op['targetId'])
        require(task.get('status') == 'done' and abs(float(task.get('consumed', -1)) -
                (data['consumed'] + data['currentConsumed'])) < 0.00001 and float(task.get('left', -1)) == 0,
                '任务状态或工时回读不一致。', 'VERIFY_FAILED')
        parent_id = number_id(task.get('parent') or 0)
        parent = client.detail('task', parent_id) if parent_id else {}
        return {'id': number_id(task['id']), 'status': task['status'], 'consumed': task['consumed'],
                'finishedDate': task.get('finishedDate'), 'parentId': parent_id, 'parentStatus': parent.get('status')}
    if action == 'bug.attach':
        bug = client.detail('bug', op['targetId'])
        files = bug.get('files')
        files = list(files.values()) if isinstance(files, dict) else files
        require(isinstance(files, list), 'Bug附件列表结构不可核实。', 'VERIFY_FAILED')
        matches = [f for f in files if str(f.get('id')) == str(remote['id'])]
        require(len(matches) == 1 and str(matches[0].get('objectID')) == str(op['targetId']) and
                matches[0].get('objectType') == 'bug' and int(matches[0].get('size', -1)) == data['size'],
                '回读附件ID、Bug关联或大小不一致。', 'VERIFY_FAILED')
        image = client.probe_png(matches[0].get('webPath'))
        require(image['sha256'] == data['sha256'] and image['size'] == data['size'],
                '远端PNG字节与上传原图不一致。', 'VERIFY_FAILED')
        return dict(remote, uploadUrl=remote['url'], url=image['url'], sha256=image['sha256'], imageReadable=True)
    if action == 'testtask.linkcase':
        context = preflight(client, op)
        require(context['runId'] > 0, '回读未找到关联条目，已提交操作不会自动重发。', 'VERIFY_FAILED')
        return {'id': data['testtaskId'], 'caseId': data['caseId'], 'runId': context['runId']}
    if action == 'result.report':
        context = preflight(client, op)
        require(context['runId'] == remote['runId'], '执行条目已被替换，停止核验。', 'VERIFY_FAILED')
        marker = f"[zentao-qa:{op['key']}]"
        matches = [r for r in client.history(data['caseId'], context['runId'])
                   if marker in canonical(r) and str(r.get('version')) == str(data['caseVersion'])
                   and str(r.get('run')) == str(context['runId'])]
        require(len(matches) == 1 and matches[0].get('caseResult') == data['result'],
                '未找到唯一且结果一致的整体执行记录。', 'VERIFY_FAILED')
        steps = matches[0].get('stepResults')
        require(isinstance(steps, list) and len(steps) == max(1, len(context['stepIds'])) and
                all(s.get('result') == ('' if context['stepIds'] else data['result']) and
                    remote['note'] in html.unescape(str(s.get('real', ''))) for s in steps),
                '步骤留空状态或来源说明不一致。', 'VERIFY_FAILED')
        case, task, runs = execution_context(client, op)
        require(case.get('lastRunResult') == data['result'] and runs[0].get('lastRunResult') == data['result'],
                '用例或测试单的最新执行结果不一致。', 'VERIFY_FAILED')
        return {'id': number_id(matches[0]['id']), 'caseId': data['caseId'], 'runId': context['runId'],
                'result': data['result'], 'source': 'user_report'}
    if action == 'task.start':
        task = client.detail('task', remote['id'])
        require(task.get('status') == 'doing' and task.get('realStarted') == remote.get('realStarted') and
                str(task.get('story')) == str(op['expected']['storyId']) and task.get('assignedTo') == data['assignedTo'] and
                float(task.get('consumed', -1)) == data['consumed'] and float(task.get('left', -1)) == round(data['left'], 2),
                '回读启动状态、开始时间、负责人或工时不一致。', 'VERIFY_FAILED')
        verified = {'id': number_id(task['id']), 'status': task['status'], 'realStarted': task['realStarted']}
        if int(task.get('parent') or 0) > 0:
            parent = client.detail('task', int(task['parent']))
            require(parent.get('status') == 'doing', '子任务已启动，父任务未联动到进行中，请核查。', 'VERIFY_FAILED')
            verified.update(parentId=number_id(parent['id']), parentStatus=parent['status'])
        return verified
    if action == 'case.review':
        case = client.detail('case', remote['id'])
        require(str(case.get('version')) == str(op['expected']['caseVersion']) and
                str(case.get('story')) == str(op['expected']['storyId']),
                '回读用例版本或关联需求不一致。', 'VERIFY_FAILED')
        reviewers = case.get('reviewedBy', '')
        reviewers = reviewers.split(',') if isinstance(reviewers, str) else reviewers
        require(case.get('status') == 'normal' and reviewers == data['reviewedBy'] and
                bool(case.get('reviewedDate')), '回读评审状态、评审人或日期不一致。', 'VERIFY_FAILED')
        if data.get('reviewedDate'):
            require(case['reviewedDate'] == data['reviewedDate'], '回读评审日期与计划不一致。', 'VERIFY_FAILED')
        return {'id': number_id(case['id']), 'status': case['status'],
                'reviewedBy': reviewers, 'reviewedDate': case['reviewedDate']}
    if action == 'result.submit':
        context = preflight(client, op)
        marker = f"[zentao-qa:{op['key']}]"
        matches = [r for r in client.history(data['caseId'], context['runId'])
                   if marker in canonical(r) and str(r.get('version')) == str(data['caseVersion'])
                   and str(r.get('run')) == str(context['runId'])]
        require(len(matches) == 1, '未找到唯一的执行记录，已提交操作不会自动重发。', 'VERIFY_FAILED')
        require(matches[0].get('caseResult') == data['result'], '回读执行结果与计划不一致。', 'VERIFY_FAILED')
        steps = matches[0].get('stepResults')
        require(isinstance(steps, list) and len(steps) == len(data['steps']), '回读执行步骤数量不一致。', 'VERIFY_FAILED')
        for actual, wanted in zip(steps, data['steps']):
            require(actual.get('result') == wanted['result'] and
                    wanted['actual'] in html.unescape(str(actual.get('real', ''))) and
                    marker in str(actual.get('real', '')), '回读步骤结果或实际现象不一致。', 'VERIFY_FAILED')
        if data.get('simulation', False):
            require(all('【调试模拟，非真实产品测试结果】' in str(s.get('real', '')) for s in steps),
                    '回读缺少模拟调试标识。', 'VERIFY_FAILED')
        return {'id': number_id(matches[0]['id']), 'caseId': data['caseId'], 'runId': context['runId']}
    if action in {'task.update', 'case.update'}:
        kind = action.split('.')[0]
        current = client.detail(kind, remote['id'])
        before, sent = remote['before'], remote['sent']
        for field in data:
            if field in {'steps', 'expects'}:
                continue
            require(normalized_text(current.get(field)) == normalized_text(sent[field]),
                    f'回读字段 {field} 不一致。', 'VERIFY_FAILED')
        if kind == 'case':
            steps = current.get('steps', [])
            require([normalized_text(x.get('desc')) for x in steps] == [normalized_text(x) for x in sent['steps']] and
                    [normalized_text(x.get('expect')) for x in steps] == [normalized_text(x) for x in sent['expects']] and
                    all(x.get('type', 'step') == 'step' for x in steps), '用例步骤回读不一致。', 'VERIFY_FAILED')
            for field in ('module', 'story', 'pri', 'type', 'precondition', 'title'):
                require(normalized_text(current.get(field)) == normalized_text(sent[field]), f'用例字段 {field} 回读不一致。', 'VERIFY_FAILED')
        else:
            for field in ('execution', 'parent', 'story', 'type', 'status', 'consumed', 'left'):
                require(normalized_text(current.get(field)) == normalized_text(before.get(field)),
                        f'未请求修改的任务字段 {field} 已改变。', 'VERIFY_FAILED')
        return {'id': number_id(current['id']), 'version': current.get('version'),
                'lastEditedDate': current.get('lastEditedDate')}
    kind = action.split('.')[0]
    value = client.detail(kind, remote['id'])
    for field, wanted in data.items():
        if field in {'steps', 'expects', 'stepType'} and action == 'case.create':
            continue
        read_field = {'productID': 'product', 'executionID': 'execution'}.get(field, field)
        actual = value.get(read_field)
        if field in {'type', 'openedBuild', 'bugLabel'} and isinstance(wanted, list):
            actual = actual.split(',') if isinstance(actual, str) else actual
            require(isinstance(actual, list) and {str(x) for x in actual} == {str(x) for x in wanted}, f'回读字段 {field} 不一致。', 'VERIFY_FAILED')
        elif isinstance(actual, dict) and 'account' in actual:
            require(actual['account'] == wanted, f'回读字段 {field} 不一致。', 'VERIFY_FAILED')
        elif action.startswith('bug.') and field == 'steps':
            require(normalized_bug_steps(actual) == normalized_bug_steps(wanted),
                    '回读Bug重现步骤内容不一致。', 'VERIFY_FAILED')
        else:
            require(normalized_text(actual) == normalized_text(wanted), f'回读字段 {field} 不一致。', 'VERIFY_FAILED')
    if action == 'bug.update':
        for field, wanted in remote.get('carried', {}).items():
            require(normalized_text(value.get(field)) == normalized_text(wanted),
                    f'回读字段 {field} 与修改前不一致。', 'VERIFY_FAILED')
    if action == 'case.create':
        if data.get('story'):
            require(str(value.get('storyVersion')) == str(op['expected']['storyVersion']),
                    '回读用例的关联需求版本不一致。', 'VERIFY_FAILED')
        steps = value.get('steps', [])
        require([normalized_text(s.get('desc')) for s in steps] == [normalized_text(s) for s in data['steps']] and
                [normalized_text(s.get('expect')) for s in steps] == [normalized_text(s) for s in data['expects']], '回读用例步骤与预期不一致。', 'VERIFY_FAILED')
    if action == 'task.create' and data.get('parent'):
        parent = client.detail('task', data['parent'])
        require(str(parent.get('execution')) == str(data['executionID']) and
                str(parent.get('isParent')) == '1', '父任务未正确形成父子任务关系。', 'VERIFY_FAILED')
    return {'id': number_id(value['id'])}


class Journal:
    def __init__(self, path):
        self.path = Path(path)

    @contextlib.contextmanager
    def locked(self):
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise QAError('BUSY', '另一个写入进程正在运行，请稍后重试。') from None
        try:
            self.db = sqlite3.connect(self.path)
            os.chmod(self.path, 0o600)
            self.db.execute('CREATE TABLE IF NOT EXISTS operations (scope TEXT, key TEXT, hash TEXT, state TEXT, remote TEXT, PRIMARY KEY(scope,key))')
            self.db.commit()
            yield self
        finally:
            if hasattr(self, 'db'):
                self.db.close()
            os.close(fd)

    def get(self, scope, key):
        row = self.db.execute('SELECT hash,state,remote FROM operations WHERE scope=? AND key=?', (scope, key)).fetchone()
        return {'hash': row[0], 'state': row[1], 'remote': json.loads(row[2])} if row else None

    def put(self, scope, op, state, remote=None):
        self.db.execute('INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?)',
                        (scope, op['key'], digest(op), state, canonical(remote or {})))
        self.db.commit()


def apply_one(client, op, journal, scope, account):
    """创建与自动评审分开记账；评审失败后不会重新创建用例。"""
    old = journal.get(scope, op['key'])
    if old:
        require(old['hash'] == digest(op), '同一操作key已用于不同内容。', 'KEY_CONFLICT')
        require(old['state'] not in {'pending', 'uncertain'}, '该操作存在未确认写入，禁止重发。请先人工核查远端记录，保留本地账本。', 'UNCERTAIN_WRITE')
        if old['state'] == 'verified':
            return {'key': op['key'], 'state': 'already_applied', 'remote': old['remote']}
    if old and old['state'] == 'submitted':
        remote = old['remote']
    else:
        preflight(client, op)
        journal.put(scope, op, 'pending')
        try:
            remote = submit(client, op)
        except QAError:
            journal.put(scope, op, 'uncertain')
            raise
        journal.put(scope, op, 'submitted', remote)
    verified = verify(client, op, remote)
    if op['action'] == 'case.create' and op.get('autoReview', True):
        review_op = remote.get('reviewOperation')
        if not review_op:
            case = client.detail('case', remote['id'])
            if case.get('status') == 'wait':
                review_op = {
                    'key': 'auto-review-' + digest(op)[:32], 'action': 'case.review',
                    'targetId': number_id(case['id']),
                    'expected': {'caseVersion': int(case['version']), 'storyId': int(case.get('story') or 0),
                                 'lastEditedDate': case.get('lastEditedDate') or ''},
                    'data': {'result': 'pass', 'reviewedBy': [account],
                             'comment': '按用户配置，新增测试用例默认评审通过。'}
                }
                validate_operation(review_op)
                remote['reviewOperation'] = review_op
                journal.put(scope, op, 'submitted', remote)
            else:
                require(case.get('status') == 'normal', '新用例状态异常，未完成自动评审。', 'VERIFY_FAILED')
                verified['status'] = 'normal'
        if review_op:
            reviewed = apply_one(client, review_op, journal, scope, account)
            verified.update(reviewed['remote'])
    journal.put(scope, op, 'verified', verified)
    return {'key': op['key'], 'state': 'verified', 'remote': verified}


def apply_plan(client, plan, journal, account):
    scope = digest({'url': client.url, 'account': account})
    completed = []
    with journal.locked():
        # 先检查整批操作，避免已知冲突导致前半批不必要的写入。
        for op in plan['operations']:
            old = journal.get(scope, op['key'])
            if old:
                require(old['hash'] == digest(op), '同一操作 key 已用于不同内容，请使用新的 key。', 'KEY_CONFLICT')
                require(old['state'] not in {'pending', 'uncertain'}, '该操作存在未确认写入，禁止重发。请先人工核查远端记录，保留本地账本。', 'UNCERTAIN_WRITE')
            if not old:
                preflight(client, op)
        for op in plan['operations']:
            try:
                completed.append(apply_one(client, op, journal, scope, account))
            except QAError as e:
                entry = journal.get(scope, op['key'])
                return {'ok': False, 'completed': completed,
                        'failed': {'key': op['key'], 'code': e.code, 'message': str(e),
                                   'remoteId': entry['remote'].get('id') if entry else None,
                                   'details': getattr(client, 'last_failure', None)},
                        'remaining': [x['key'] for x in plan['operations'][len(completed) + 1:]]}
    return {'ok': True, 'completed': completed}


def review_info(client, case_id):
    # 已评审的用例不能再进入review表单；从详情读取完整操作历史。
    value = client.request('GET', f'/testcases/{number_id(case_id)}')
    case, actions = value.get('testcase'), value.get('actions')
    require(isinstance(case, dict) and str(case.get('id')) == str(case_id) and isinstance(actions, (list, dict)),
            '用例详情或评审历史不可核实。', 'INVALID_RESPONSE')
    actions = list(actions.values()) if isinstance(actions, dict) else actions
    return {'caseId': case['id'], 'status': case.get('status'), 'reviewedBy': case.get('reviewedBy'),
            'reviewedDate': case.get('reviewedDate'),
            'reviewedActions': [{k: a.get(k) for k in ('id', 'actor', 'action', 'extra', 'date')}
                                for a in actions if str(a.get('action', '')).lower() == 'reviewed']}


def reconcile_review(client, plan, journal, account, key):
    """仅在待评审状态、原版本匹配且无评审历史时恢复被拒绝的评审。"""
    ops = [op for op in plan['operations'] if op['key'] == key]
    require(len(ops) == 1 and ops[0]['action'] == 'case.review', '仅支持核查计划中指定的case.review操作。')
    op = ops[0]
    scope = digest({'url': client.url, 'account': account})
    with journal.locked():
        old = journal.get(scope, key)
        require(old and old['hash'] == digest(op) and old['state'] in {'pending', 'uncertain'},
                '账本状态或计划内容不符合评审核查条件。', 'CONFLICT')
        preflight(client, op)
        case = client.detail('case', op['targetId'])
        require(not case.get('reviewedBy') and not case.get('reviewedDate'), '用例已有评审信息，不能恢复提交。', 'CONFLICT')
        view = review_info(client, op['targetId'])
        require(not view['reviewedActions'],
                '用例已有正式评审历史，不能恢复提交。', 'CONFLICT')
        journal.put(scope, op, 'not_applied', {'id': op['targetId'], 'reconciled': {
            'status': case['status'], 'version': case['version'], 'reviewedActions': 0,
            'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat()}})
    return {'ok': True, 'key': key, 'state': 'not_applied', 'businessDataWritten': False}


def reconcile_result(client, plan, journal, account, key):
    """仅通过完整回读证明结果已写入，不重发请求，不恢复为可提交。"""
    ops = [op for op in plan['operations'] if op['key'] == key]
    require(len(ops) == 1 and ops[0]['action'] == 'result.submit', '仅支持核查指定的result.submit操作。')
    op = ops[0]
    scope = digest({'url': client.url, 'account': account})
    with journal.locked():
        old = journal.get(scope, key)
        require(old and old['hash'] == digest(op) and old['state'] in {'pending', 'uncertain'},
                '账本状态或原计划不符合结果核查条件。', 'CONFLICT')
        verified = verify(client, op, {})
        journal.put(scope, op, 'verified', verified)
    return {'ok': True, 'key': key, 'state': 'verified', 'remote': verified, 'businessDataWritten': False}


def configured(args):
    config = read_json(args.config) if Path(args.config).exists() else {}
    require(isinstance(config, dict), '本地配置必须是JSON对象。')
    url = args.url or os.environ.get('ZENTAO_URL') or config.get('url')
    env_token = os.environ.get('ZENTAO_TOKEN', '')
    env_password = os.environ.get('ZENTAO_PASSWORD', '')
    token = env_token or config.get('token', '')
    account = args.account or os.environ.get('ZENTAO_ACCOUNT') or config.get('account', '')
    require(url, '请通过 --url、ZENTAO_URL 或本地配置指定禅道地址。')
    require(isinstance(account, str) and type(config.get('noProxy', False)) is bool, '账号必须是字符串，noProxy必须是布尔值。')
    require(isinstance(config.get('password', ''), str), '本地password必须是字符串。')
    same_scope = (isinstance(url, str) and url.rstrip('/') == str(config.get('url', '')).rstrip('/') and
                  account == config.get('account', ''))
    if args.command == 'login':
        token = ''
    elif not env_token:
        if env_password and not same_scope:
            token = ''
        elif config.get('token') or config.get('password'):
            require(same_scope, '站点或账号已改变，不能沿用原配置凭据；请重新登录或提供匹配的环境凭据。', 'AUTH_SCOPE_MISMATCH')
    client = Client(url, token, args.no_proxy or config.get('noProxy', False))
    password = env_password or (config.get('password', '') if same_scope else '')
    if args.command != 'login' and not env_token and password:
        require(account, '账号密码自动登录需要配置account。', 'AUTH_REQUIRED')
        def reauthenticate():
            client.login(account, password)
            if same_scope:
                latest = read_json(args.config)
                require(isinstance(latest, dict) and latest.get('url', '').rstrip('/') == client.url and
                        latest.get('account') == account and latest.get('password', '') == config.get('password', ''),
                        '登录期间本地配置已改变，未覆盖配置，请重新运行。', 'CONFIG_CONFLICT')
                latest['token'] = client.token
                safe_write(args.config, latest)
        client.reauthenticate = reauthenticate
    return client, account


def parser():
    p = argparse.ArgumentParser(description='禅道22.2测试协作：查询、离线计划、显式写入。')
    p.add_argument('--config', default=str(DEFAULT_CONFIG), help='本地配置路径，默认 Skill 下 .local/config.json')
    p.add_argument('--url', help='禅道根地址，保留 /zentao 子路径')
    p.add_argument('--account', help='操作账号标识')
    p.add_argument('--no-proxy', action='store_true', help='仅本次请求绕过环境代理')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='只读检查登录、产品和项目接口')
    login = sub.add_parser('login', help='登录并保存Token，可选择保存密码供自动登录')
    login.add_argument('--password-env', default='ZENTAO_PASSWORD')
    login.add_argument('--save-password', action='store_true', help='将密码保存在本机0600配置，支持自动重新登录')
    read = sub.add_parser('read', help='读取列表、详情或需求上下文')
    read.add_argument('resource', choices=['products', 'projects', 'executions', 'stories', 'story', 'context', 'cases', 'case', 'review', 'bugs', 'bug', 'bugform', 'bugimage', 'testtasks', 'testtask', 'results', 'builds', 'tasks', 'task', 'users', 'user'])
    read.add_argument('--id', type=int)
    read.add_argument('--scope', choices=['product', 'project', 'execution'])
    read.add_argument('--scope-id', type=int)
    read.add_argument('--story-id', type=int, help='跨页读取后按需求过滤')
    read.add_argument('--kw', help='users 按账号、姓名或拼音过滤；提供后自动读取全部分页')
    read.add_argument('--exact', action='store_true', help='users 关键字需与账号、姓名或拼音分词完全一致')
    read.add_argument('--all', action='store_true', help='读取全部分页')
    read.add_argument('--page', type=int, default=1)
    read.add_argument('--size', type=int, default=100)
    for command in ('plan', 'apply'):
        cp = sub.add_parser(command, help='离线验证计划' if command == 'plan' else '提交计划，默认仅离线预览')
        cp.add_argument('--file', required=True)
        if command == 'apply':
            cp.add_argument('--commit', action='store_true', help='显式执行写入；需已获得用户授权')
            cp.add_argument('--journal', help='本地防重账本路径，默认随配置存放')
    for command, help_text in [('reconcile-review', '只读核查未生效的评审，再恢复本地账本的可提交状态'),
                               ('reconcile-result', '只读核查结果已成功写入，确认后将本地账本记为已验证，不重发')]:
        reconcile = sub.add_parser(command, help=help_text)
        reconcile.add_argument('--file', required=True)
        reconcile.add_argument('--key', required=True)
        reconcile.add_argument('--journal')
    return p


def run(args):
    if args.command in {'reconcile-review', 'reconcile-result'}:
        plan = load_plan(args.file)
        client, account = configured(args)
        require(account, '核查账本需要账号标识。')
        reconcile = reconcile_review if args.command == 'reconcile-review' else reconcile_result
        return reconcile(client, plan, Journal(args.journal or Path(args.config).parent / 'journal.sqlite3'), account, args.key)
    if args.command in {'plan', 'apply'}:
        plan = load_plan(args.file)
        if args.command == 'plan' or not args.commit:
            return {'ok': True, 'mode': 'offline_preview', 'networkAccessed': False, 'plan': plan}
        client, account = configured(args)
        require(account, '写入需设置账号标识，以隔离本地防重账本。')
        journal = Journal(args.journal or Path(args.config).parent / 'journal.sqlite3')
        return apply_plan(client, plan, journal, account)
    client, account = configured(args)
    if args.command == 'login':
        require(account, '登录需要 --account 或 ZENTAO_ACCOUNT。')
        password = os.environ.get(args.password_env)
        saved = read_json(args.config) if Path(args.config).exists() else {}
        same_scope = (isinstance(saved, dict) and saved.get('url', '').rstrip('/') == client.url and
                      saved.get('account') == account)
        if not password and same_scope:
            password = saved.get('password')
        if not password and sys.stdin.isatty():
            password = getpass.getpass('禅道密码：')
        require(password, '请通过指定环境变量或终端交互提供密码。')
        client.login(account, password)
        value = {'url': client.url, 'account': account, 'token': client.token, 'noProxy': client.no_proxy}
        save_password = args.save_password or (same_scope and bool(saved.get('password')))
        if save_password:
            value['password'] = password
        safe_write(args.config, value)
        return {'ok': True, 'account': account, 'config': str(Path(args.config).resolve()), 'passwordSaved': bool(save_password)}
    if args.command == 'doctor':
        checks = []
        for path, key in [('/products', 'products'), ('/projects', 'projects')]:
            try:
                value = client.listing(path, key, size=1)
                checks.append({'interface': path, 'ok': True, 'returned': len(value['items'])})
            except QAError as e:
                checks.append({'interface': path, 'ok': False, 'code': e.code, 'message': str(e)})
        return {'ok': all(x['ok'] for x in checks), 'url': client.url, 'account': account,
                'transport': urllib.parse.urlsplit(client.url).scheme, 'checks': checks,
                'limitations': ['仅追加关联当前版本正常用例，不覆盖已有执行条目', '逐步结果与整体报告分别提交；模拟调试数据必须明确标注']}
    resource = args.resource
    require(args.page >= 1 and 1 <= args.size <= 1000, 'page从1开始，size范围1至1000。')
    if resource == 'users':
        value = client.listing('/users', 'users', args.all or bool(args.kw), args.page, args.size)
        items = [u for u in value['items'] if str(u.get('deleted', 0)) in {'0', '', 'False'}]
        if args.kw:
            items = [u for u in items if user_matches(u, args.kw, args.exact)]
        return {'ok': True, 'items': [public_user(u) for u in items], 'complete': value['complete'],
                'pager': value['pager'], 'keyword': args.kw or '', 'exact': bool(args.kw and args.exact)}
    if resource == 'user':
        require(positive(args.id), '读取单个用户需要 --id。')
        value = client.request('GET', f'/users/{number_id(args.id)}')
        user = value.get('user') if isinstance(value, dict) else None
        require(isinstance(user, dict) and str(user.get('id')) == str(args.id),
                '用户详情缺少匹配编号，不能认定查询成功。', 'INVALID_RESPONSE')
        return {'ok': True, 'data': public_user(user)}
    if resource == 'bugimage':
        bug_id, file_id = number_id(args.scope_id), number_id(args.id)
        bug = client.detail('bug', bug_id)
        files = bug.get('files')
        files = list(files.values()) if isinstance(files, dict) else files
        require(isinstance(files, list), 'Bug附件列表不可核实。', 'INVALID_RESPONSE')
        matches = [f for f in files if str(f.get('id')) == str(file_id) and
                   str(f.get('objectID')) == str(bug_id) and f.get('objectType') == 'bug']
        require(len(matches) == 1 and matches[0].get('extension') == 'png', '未找到该Bug唯一关联的PNG附件。')
        return {'ok': True, 'bugId': bug_id, 'fileId': file_id, 'data': client.probe_png(matches[0].get('webPath'))}
    if resource == 'bugform':
        require(args.scope == 'product' and positive(args.scope_id), 'Bug创建表单需要产品范围。')
        return {'ok': True, 'data': client.request('GET', '/bugs/create', params={'productID': args.scope_id})}
    if resource == 'review':
        case_id = number_id(args.id)
        try:
            return {'ok': True, 'data': review_info(client, case_id)}
        except QAError as e:
            return {'ok': False, 'error': {'code': e.code, 'message': str(e),
                                          'details': client.last_failure}}
    if resource in {'story', 'case', 'bug', 'task'}:
        return {'ok': True, 'data': client.detail(resource, args.id)}
    if resource == 'testtask':
        return {'ok': True, 'data': client.testtask(args.id)}
    if resource == 'results':
        return {'ok': True, 'data': client.history(args.id)}
    if resource == 'context':
        story = client.detail('story', args.id)
        pid = number_id(story['product'])
        cases = client.listing(f'/products/{pid}/testcases', 'testcases', True)
        bugs = client.listing(f'/products/{pid}/bugs', 'bugs', True)
        return {'ok': True, 'story': story,
                'cases': [x for x in cases['items'] if str(x.get('story')) == str(args.id)],
                'bugs': [x for x in bugs['items'] if str(x.get('story')) == str(args.id)],
                'attachmentsDownloaded': False, 'complete': True}
    if resource in {'products', 'projects'}:
        path = '/' + resource
    else:
        allowed = {'executions': {'project'}, 'stories': {'product', 'project', 'execution'},
                   'cases': {'product', 'project', 'execution'}, 'bugs': {'product', 'project', 'execution'},
                   'testtasks': {'product', 'project', 'execution'}, 'builds': {'project', 'execution'},
                   'tasks': {'execution'}}
        require(args.scope in allowed[resource] and positive(args.scope_id), '请指定正确的 --scope 和 --scope-id。')
        suffix = 'testcases' if resource == 'cases' else resource
        path = f'/{args.scope}s/{args.scope_id}/{suffix}'
    key = 'testcases' if resource == 'cases' else resource
    value = client.listing(path, key, args.all or bool(args.story_id), args.page, args.size)
    if args.story_id:
        require(resource in {'cases', 'bugs'} and positive(args.story_id) and args.page == 1, '--story-id 仅支持 cases/bugs，需从第1页开始。')
        value['items'] = [x for x in value['items'] if str(x.get('story')) == str(args.story_id)]
    return {'ok': True, **value}


def main():
    try:
        result = run(parser().parse_args())
        emit(result)
        return 0 if result.get('ok', True) else 1
    except QAError as e:
        emit({'ok': False, 'error': {'code': e.code, 'message': str(e), 'uncertain': e.uncertain}})
        return 1
    except (OSError, sqlite3.Error):
        emit({'ok': False, 'error': {'code': 'LOCAL_STATE_ERROR', 'message': '本地文件或账本读写失败，请检查权限；如正在提交写入，先核查远端，不要删除账本重试。'}})
        return 1


if __name__ == '__main__':
    sys.exit(main())
