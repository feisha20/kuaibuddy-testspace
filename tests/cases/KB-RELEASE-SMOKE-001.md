# KB-RELEASE-SMOKE-001：KuaiBuddy 发版准出冒烟测试用例（可执行操作版）

- **状态**：可执行草案（基于 `beta` 分支源码及工具链编写，可直接交由 Agent 或测试人员逐条执行；正式发版阈值待团队确认）
- **所属模块**：KuaiBuddy 核心底座与高频业务链路
- **优先级**：P0（发版准出必跑）
- **适用对象**：既支持 **Agent 通过 CLI + 脚本全自动执行与取证**，也支持 **人工在工作台 Web 端逐项操作验证**
- **关联资产**：[architecture.md](../../docs/architecture.md)、[knowledge.md](../../docs/knowledge.md)、[KB-CACHE-001.md](KB-CACHE-001.md)、[KB-MEMORY-001.md](KB-MEMORY-001.md)

---

## 0. 执行前统一初始化（Agent / 自动化执行必跑）

在仓库根目录执行以下命令，选定目标环境与独立 Run 目录（**禁止覆盖历史 Run，禁止输出任何密码/Token**）：

```bash
# 1. 选择目标环境（预生产：.env.preprod + prd；测试：.env.test + test；生产需明确授权：.env.prod + prd）
export KB_ENV_FILE=".env.preprod"
export OBS_ENV="prd"   # prd 对应预生产/生产 Langfuse；test 对应测试 Langfuse

# 2. 创建本次发版冒烟独立 Run 目录
export RUN_DIR=$(python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import secrets

run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + "发版准出冒烟-" + secrets.token_hex(3)
run = Path(".runtime/requests/发版准出冒烟") / run_id
run.mkdir(parents=True, exist_ok=False)
templates = Path(".agents/skills/kb-test-execution/assets")
for name in ("plan.md", "execution.md", "result.md"):
    content = (templates / name).read_text(encoding="utf-8")
    content = content.replace("{{TASK_ID}}", "无（单次请求）").replace("{{RUN_ID}}", run_id)
    (run / name).write_text(content, encoding="utf-8")
for name in ("logs", "screenshots", "artifacts"):
    (run / name).mkdir()
print(run)
PY
)
echo "RUN_DIR=$RUN_DIR"

# 3. 强制登录并刷新 Token（缓存至 .runtime/cache/kuaibuddy-preprod/token.json）
node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json > "$RUN_DIR/artifacts/login_check.json"

# 4. 查询当前可用技能，挑出 1 个中文名称只读技能用于 SMOKE-002
node .agents/skills/kb-test-execution/scripts/kb_e2e.js skills --json > "$RUN_DIR/artifacts/skills.json"
python3 -c "
import json
data = json.load(open('$RUN_DIR/artifacts/skills.json'))
items = data if isinstance(data, list) else data.get('data') or data.get('skills') or []
for s in items[:20]:
    print(s.get('name') or s.get('skillName'), '| scope=', s.get('scope'))
"
```

> **辅助工具约定**：下文脚本统一从 `.runtime/cache/kuaibuddy-preprod/token.json` 读取 `token` 与 `baseUrl`（仅在进程内存中发起请求，不打印凭据），并从 `.env.observability` 读取对应 `OBS_ENV` 的 Langfuse 凭据。

---

## SMOKE-001：【基础对话与运行控制】多轮对话、Prompt Cache 命中率及断连/取消收口

- **覆盖目标**：① 正常对话发起；② 第 2~3 轮 Prompt Cache 命中率达标且 System Prompt 无抖动；③ SSE 断连后 `/run/active` 与 `/run/observe` 可续接；④ `/run/cancel` 停止后会话不锁死（防 `#92963`）。
- **前置条件**：已完成第 0 节登录；具备 Langfuse 查询权限。

### 执行步骤（Agent / CLI 方式）

```bash
# Step 1: 发起第 1 轮对话
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "请用约600字介绍企业微信私域运营的三个核心阶段（纯模型输出，不要调用任何工具或技能）。" \
  --out "$RUN_DIR/artifacts/smoke001_r1" --json > "$RUN_DIR/artifacts/smoke001_r1.json"

export S1_THREAD=$(python3 -c "import json; print(json.load(open('$RUN_DIR/artifacts/smoke001_r1.json'))['threadId'])")
export S1_RUN1=$(python3 -c "import json; print(json.load(open('$RUN_DIR/artifacts/smoke001_r1.json'))['runId'])")

# Step 2: 同一会话发起第 2、3 轮对话
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S1_THREAD" \
  "基于上面内容，补充3条落地避坑建议，约250字（纯模型输出，不要调用任何工具或技能）。" \
  --out "$RUN_DIR/artifacts/smoke001_r2" --json > "$RUN_DIR/artifacts/smoke001_r2.json"

node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S1_THREAD" \
  "把前面两轮内容提炼为5行要点清单（纯模型输出，不要调用任何工具或技能）。" \
  --out "$RUN_DIR/artifacts/smoke001_r3" --json > "$RUN_DIR/artifacts/smoke001_r3.json"

# Step 3: 核验 Langfuse 第 2、3 轮 Prompt Cache 命中率与 System Prompt 前缀一致性
python3 - <<'PY'
import os, sys, json, urllib.request, urllib.parse, base64
sys.path.insert(0, '.agents/skills/kb-bug-analyse/scripts')
import local_config

local_config.load_local_config()
env_key = os.environ.get('OBS_ENV', 'prd').upper()
host = os.environ[f'KB_LANGFUSE_{env_key}_URL'].rstrip('/')
pub = os.environ[f'KB_LANGFUSE_{env_key}_PUBLIC_KEY']
sec = os.environ[f'KB_LANGFUSE_{env_key}_SECRET_KEY']
auth = base64.b64encode(f'{pub}:{sec}'.encode()).decode()
run_dir = os.environ['RUN_DIR']

inputs = {}
for idx in (1, 2, 3):
    rid = json.load(open(f'{run_dir}/artifacts/smoke001_r{idx}.json'))['runId']
    flt = json.dumps([{'type': 'stringObject', 'column': 'metadata', 'key': 'run_id', 'operator': '=', 'value': rid}])
    url = f'{host}/api/public/v2/observations?fields=core,usage,io&filter={urllib.parse.quote(flt)}'
    req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    gens = sorted([o for o in data.get('data', []) if o.get('type') == 'GENERATION'], key=lambda x: x.get('startTime', ''))
    assert gens, f'R{idx} ({rid}) 未查到 GENERATION'
    u = gens[0].get('usageDetails') or gens[0].get('usage') or {}
    inp, cached = u.get('input', 0), u.get('input_cached_tokens', 0)
    tot = inp + cached
    rate = (cached / tot * 100) if tot else 0.0
    print(f'R{idx} ({rid}): input={inp}, cached={cached}, hit_rate={rate:.2f}%')
    if gens[0].get('input'):
        inputs[idx] = json.dumps(gens[0]['input'], ensure_ascii=False) if not isinstance(gens[0]['input'], str) else gens[0]['input']

if 1 in inputs and 2 in inputs:
    s1, s2 = inputs[1], inputs[2]
    pos = next((k for k, (a, b) in enumerate(zip(s1, s2)) if a != b), min(len(s1), len(s2)))
    print(f'R1 vs R2 首个差异字符位置: {pos} / {len(s1)}')
PY

# Step 4: 发起长文本 Run → 2 秒后主动断开 SSE → 调 active & observe 验证续接 → 调 cancel 中止
python3 - <<'PY'
import json, os, time, urllib.request

cache = json.load(open('.runtime/cache/kuaibuddy-preprod/token.json'))
base = cache['baseUrl'].rstrip('/')
token = cache['token']
thread_id = os.environ['S1_THREAD']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# 4.1 发起长文本请求并在读到前 3 个 SSE chunk 后主动断开连接
body = json.dumps({
    'threadId': thread_id,
    'messages': [{'role': 'user', 'content': '请详细编写一份3000字的电商大促全流程客服SOP，包含售前、售中、售后每个环节的完整话术示例（纯模型输出）。'}]
}).encode()
req = urllib.request.Request(f'{base}/api/v1/agent/run', data=body, headers=headers, method='POST')
with urllib.request.urlopen(req, timeout=30) as resp:
    chunks = 0
    for line in resp:
        if line.strip():
            chunks += 1
        if chunks >= 5:
            break  # 模拟客户端 SSE 断连
print(f'[4.1] 已收到 {chunks} 行 SSE 并模拟断连')

# 4.2 查询活跃 Run（验证断连未中断后端执行）
req_act = urllib.request.Request(f'{base}/api/v1/agent/run/active', data=b'{}', headers=headers, method='POST')
with urllib.request.urlopen(req_act, timeout=15) as resp:
    act = json.loads(resp.read().decode())
print('[4.2] /run/active:', act)

# 4.3 调用 observe 续接事件流（读到 3 行事件即证明可重连）
req_obs = urllib.request.Request(f'{base}/api/v1/agent/run/observe?threadId={thread_id}', data=b'{}', headers=headers, method='POST')
with urllib.request.urlopen(req_obs, timeout=20) as resp:
    obs_lines = 0
    for line in resp:
        if line.strip():
            obs_lines += 1
        if obs_lines >= 3:
            break
print(f'[4.3] /run/observe 续接成功，收到 {obs_lines} 行事件')

# 4.4 调用 cancel 中止执行
req_can = urllib.request.Request(f'{base}/api/v1/agent/run/cancel?threadId={thread_id}', data=b'{}', headers=headers, method='POST')
with urllib.request.urlopen(req_can, timeout=15) as resp:
    can = json.loads(resp.read().decode())
print('[4.4] /run/cancel:', can)
time.sleep(3)
PY

# Step 5: 取消后立即在同一会话发第 5 轮，验证会话未锁死
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S1_THREAD" \
  "只回复两个字：正常" \
  --expect "正常" \
  --out "$RUN_DIR/artifacts/smoke001_r5" --json > "$RUN_DIR/artifacts/smoke001_r5.json"
```

### 人工 Web 端操作步骤（备选）
1. 登录工作台，点击「新建任务」，依次发送上述第 1、2、3 轮提示词，确认回复完整且承接上文；
2. 发送第 4 轮 3000 字 SOP 提示词，开始吐字 2 秒后直接按 `F5` 刷新页面，观察是否自动恢复流式输出（不断流）；
3. 恢复吐字后点击输入框右侧「停止生成」按钮，等待 2 秒；
4. 立即发送 `只回复两个字：正常`，确认可立刻回复“正常”且无“会话运行中”报错；
5. 由测试/研发在 Langfuse 中按本次 `runId` 核对第 2、3 轮缓存命中率。

### 判定标准（全部勾选为通过）
- [ ] **[L1]** 第 1~3 轮均正常完整返回，无 `RunError` / `9001` / `4051`。
- [ ] **[L2]** 第 2 轮与第 3 轮 Prompt Cache 命中率均 **≥ 90%**（待确认：换模型时按新基线校准），且 R1/R2 System Prompt 前缀无异常抖动。
- [ ] **[L1]** SSE 断连后 `/run/active` 包含当前 `threadId`，且 `/run/observe` 可续接事件流。
- [ ] **[L1/L3]** `/run/cancel` 后 3 秒内，第 5 轮可正常发起并包含「正常」，会话未锁死。

---

## SMOKE-002：【复合长链路】中文 Skill Slash 加载 + 沙箱读写与 CLI + 产物交付与计费

- **覆盖目标**：① 中文名 Skill Slash 直接加载（防 `#93140`）+ Langfuse 核查静默工具 `load_skill_through_path`；② K8s 沙箱写文件 + 执行 Python CLI + 读文件；③ 产物入文件库且保留工作区源文件；④ 积分扣减收口。
- **前置条件**：从第 0 节 `skills.json` 中选定 1 个**中文名称只读技能**，写入环境变量 `export CN_SKILL="<实际中文技能名>"`。

### 执行步骤（Agent / CLI 方式）

```bash
# 请先替换为 skills.json 中实际存在的中文只读技能名
export CN_SKILL="<替换为实际中文技能名>"

# Step 1: 记录执行前积分余额
python3 - <<'PY' > "$RUN_DIR/artifacts/smoke002_points_before.json"
import json, urllib.request
cache = json.load(open('.runtime/cache/kuaibuddy-preprod/token.json'))
req = urllib.request.Request(
    f"{cache['baseUrl'].rstrip('/')}/api/v1/points/account",
    data=b'{}',
    headers={'Authorization': f"Bearer {cache['token']}", 'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req, timeout=15) as resp:
    print(resp.read().decode())
PY

# Step 2: 第 1 轮——触发中文 Skill + 沙箱写 CSV + Python 统计 + 写/读报告
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "/$CN_SKILL 请先按该技能做一次简短只读说明；然后在工作区新建目录 smoke_release_tmp，写入文件 smoke_release_tmp/input.csv（内容为三行数据：id,name,score\n1,张三,88\n2,李四,95\n3,王五,72），用 python3 脚本计算平均分和最高分，把结果写入 smoke_release_tmp/smoke_report.md，最后读取 smoke_report.md 并把平均分和最高分回复给我。" \
  --expect "85" --expect "李四" --expect "95" \
  --out "$RUN_DIR/artifacts/smoke002_r1" --json > "$RUN_DIR/artifacts/smoke002_r1.json"

export S2_THREAD=$(python3 -c "import json; print(json.load(open('$RUN_DIR/artifacts/smoke002_r1.json'))['threadId'])")

# Step 3: 第 2 轮——保存产物到文件库，并核验工作区源文件仍保留
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S2_THREAD" \
  "把刚才生成的 smoke_release_tmp/smoke_report.md 保存到我的文件库，然后用命令检查工作区里的 smoke_release_tmp/smoke_report.md 源文件是否仍然存在并明确告诉我。" \
  --expect "存在" \
  --out "$RUN_DIR/artifacts/smoke002_r2" --json > "$RUN_DIR/artifacts/smoke002_r2.json"

# Step 4: Langfuse 核查静默工具 load_skill_through_path 与沙箱工具链
python3 - <<'PY'
import os, sys, json, urllib.request, urllib.parse, base64
sys.path.insert(0, '.agents/skills/kb-bug-analyse/scripts')
import local_config

local_config.load_local_config()
env_key = os.environ.get('OBS_ENV', 'prd').upper()
host = os.environ[f'KB_LANGFUSE_{env_key}_URL'].rstrip('/')
auth = base64.b64encode(f"{os.environ[f'KB_LANGFUSE_{env_key}_PUBLIC_KEY']}:{os.environ[f'KB_LANGFUSE_{env_key}_SECRET_KEY']}".encode()).decode()
rid = json.load(open(f"{os.environ['RUN_DIR']}/artifacts/smoke002_r1.json"))['runId']

flt = json.dumps([{'type': 'stringObject', 'column': 'metadata', 'key': 'run_id', 'operator': '=', 'value': rid}])
url = f'{host}/api/public/v2/observations?fields=core,usage,io&filter={urllib.parse.quote(flt)}'
req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
with urllib.request.urlopen(req, timeout=20) as resp:
    obs = json.loads(resp.read().decode()).get('data', [])

tools = [(o.get('name'), o.get('level'), o.get('statusMessage')) for o in obs if o.get('type') != 'GENERATION']
print(f'SMOKE-002 R1 ({rid}) 非 GENERATION Span 清单:')
for name, lvl, msg in tools:
    print(f'  - {name} | level={lvl} | status={msg}')
PY

# Step 5: 核对文件库落库 & 执行后积分余额变化
python3 - <<'PY'
import json, os, urllib.request

cache = json.load(open('.runtime/cache/kuaibuddy-preprod/token.json'))
base, token = cache['baseUrl'].rstrip('/'), cache['token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# 5.1 按会话查文件库产物
req_lib = urllib.request.Request(
    f'{base}/api/v1/library/list-by-session',
    data=json.dumps({'sessionId': os.environ['S2_THREAD']}).encode(),
    headers=headers, method='POST'
)
with urllib.request.urlopen(req_lib, timeout=15) as resp:
    lib_data = json.loads(resp.read().decode())
print('[5.1] 文件库产物:', json.dumps(lib_data, ensure_ascii=False)[:500])

# 5.2 积分前后对比
before = json.load(open(f"{os.environ['RUN_DIR']}/artifacts/smoke002_points_before.json"))
req_pts = urllib.request.Request(f'{base}/api/v1/points/account', data=b'{}', headers=headers, method='POST')
with urllib.request.urlopen(req_pts, timeout=15) as resp:
    after = json.loads(resp.read().decode())
print('[5.2] 积分前:', before.get('data'))
print('[5.2] 积分后:', after.get('data'))
PY

# Step 6: 清理工作区临时目录（文件库测试文件可通过 /api/v1/library/delete 按返回 id 清理）
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S2_THREAD" \
  "请删除工作区里的临时目录 smoke_release_tmp。" \
  --out "$RUN_DIR/artifacts/smoke002_cleanup" --json > "$RUN_DIR/artifacts/smoke002_cleanup.json"
```

### 人工 Web 端操作步骤（备选）
1. 进入工作台「积分中心」记录当前积分余额；
2. 新建会话，在输入框键入 `/` 确认下拉出现中文名称技能并选中，发送上述第 1 轮提示词，核对回复含平均分 `85`、最高分 `李四/95`；
3. 发送第 2 轮提示词，打开右侧产物抽屉或「文件库」确认 `smoke_report.md` 可预览/下载，且回复确认工作区源文件仍存在；
4. 刷新「积分中心」确认积分有扣减且流水正常；清理临时目录与测试文件库条目。

### 判定标准
- [ ] **[L1]** 第 1 轮回复包含正确统计结果（平均分 `85`、最高分 `李四`/`95`），无沙箱报错（`4052`/`4053`）。
- [ ] **[L2]** Langfuse 中可明确看到 `load_skill_through_path` 成功加载中文技能正文（非 `skill-<id>` 失败），且包含文件写、命令执行、文件读 Span。
- [ ] **[L1/L3]** 文件库接口 `/api/v1/library/list-by-session` 查到 `smoke_report.md`；工作区源文件确认保留。
- [ ] **[L3]** 执行后积分余额较执行前合理扣减，无异常负值或零扣减。

---

## SMOKE-003：【联网能力】`web_fetch` 公开网页抓取与内容提炼

- **覆盖目标**：验证内置 `web_fetch` 抓取外网页面可用且准确提炼，同时确认未误调已默认禁用的 `web_search`（见 `AgentFactory.java#L139`）。
- **前置条件**：目标环境具备访问 `https://example.com` 的出站网络权限（若纯内网环境则替换为内部稳定页面 URL 并在 Run 中注明）。

### 执行步骤（Agent / CLI 方式）

```bash
# Step 1: 发起网页抓取请求
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "请直接抓取网页 https://example.com 的正文内容，原样提取页面主标题（h1）和第一段英文正文，并说明你调用的工具名称。" \
  --expect "Example Domain" \
  --out "$RUN_DIR/artifacts/smoke003" --json > "$RUN_DIR/artifacts/smoke003.json"

# Step 2: Langfuse 核查实际调用 web_fetch 且未触发 web_search 报错
python3 - <<'PY'
import os, sys, json, urllib.request, urllib.parse, base64
sys.path.insert(0, '.agents/skills/kb-bug-analyse/scripts')
import local_config

local_config.load_local_config()
env_key = os.environ.get('OBS_ENV', 'prd').upper()
host = os.environ[f'KB_LANGFUSE_{env_key}_URL'].rstrip('/')
auth = base64.b64encode(f"{os.environ[f'KB_LANGFUSE_{env_key}_PUBLIC_KEY']}:{os.environ[f'KB_LANGFUSE_{env_key}_SECRET_KEY']}".encode()).decode()
rid = json.load(open(f"{os.environ['RUN_DIR']}/artifacts/smoke003.json"))['runId']

flt = json.dumps([{'type': 'stringObject', 'column': 'metadata', 'key': 'run_id', 'operator': '=', 'value': rid}])
url = f'{host}/api/public/v2/observations?fields=core,io&filter={urllib.parse.quote(flt)}'
req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
with urllib.request.urlopen(req, timeout=20) as resp:
    obs = json.loads(resp.read().decode()).get('data', [])

for o in obs:
    if o.get('type') != 'GENERATION':
        print(f"  - {o.get('name')} | level={o.get('level')} | status={o.get('statusMessage')}")
PY
```

### 人工 Web 端操作步骤（备选）
1. 新建会话发送上述提示词；
2. 观察消息流中的工具调用卡片显示抓取工具成功完成，且回复中准确提取 `Example Domain` 及第一段英文原文，无“无法联网”或编造内容。

### 判定标准
- [ ] **[L1]** 回复准确包含 `Example Domain` 及页面第一段英文正文。
- [ ] **[L2]** Langfuse 轨迹确认实际调用 `web_fetch`（或等效网页抓取工具）且成功返回，未出现调用 `web_search` 失败报错。

---

## SMOKE-004：【多模态与产物】文生图生成、可用性验证与文件库保存

- **覆盖目标**：验证文生图工具（`text_to_image`）生成、图片链接可访问、保存到文件库（`save_image_to_library`）及积分扣减。
- **前置条件**：账号积分余额充足。

### 执行步骤（Agent / CLI 方式）

```bash
# Step 1: 发起文生图请求
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "请生成一张16:9的极简科技风浅蓝背景横幅图，画面中不要出现任何文字，适合作为客服团队早会封面。" \
  --out "$RUN_DIR/artifacts/smoke004_r1" --json > "$RUN_DIR/artifacts/smoke004_r1.json"

export S4_THREAD=$(python3 -c "import json; print(json.load(open('$RUN_DIR/artifacts/smoke004_r1.json'))['threadId'])")

# Step 2: 回读消息提取图片 URL 并验证 HTTP 200 可访问
node .agents/skills/kb-test-execution/scripts/kb_e2e.js messages --session "$S4_THREAD" --json > "$RUN_DIR/artifacts/smoke004_msgs.json"
python3 - <<'PY'
import json, os, re, urllib.request
raw = open(f"{os.environ['RUN_DIR']}/artifacts/smoke004_msgs.json").read()
urls = sorted(set(re.findall(r'https?://[^\s"\'<>)]+\.(?:png|jpg|jpeg|webp)[^\s"\'<>)]*', raw, re.I)))
print('提取到的图片 URL 数量:', len(urls))
for u in urls[:3]:
    req = urllib.request.Request(u, method='HEAD')
    with urllib.request.urlopen(req, timeout=15) as resp:
        print('  HTTP', resp.status, 'Content-Type:', resp.headers.get('Content-Type'), 'Length:', resp.headers.get('Content-Length'))
PY

# Step 3: 保存生成的图片到文件库并验证入库
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S4_THREAD" \
  "把刚才生成的这张图片保存到我的文件库，命名为 smoke-banner-test。" \
  --out "$RUN_DIR/artifacts/smoke004_r2" --json > "$RUN_DIR/artifacts/smoke004_r2.json"

python3 - <<'PY'
import json, os, urllib.request
cache = json.load(open('.runtime/cache/kuaibuddy-preprod/token.json'))
req = urllib.request.Request(
    f"{cache['baseUrl'].rstrip('/')}/api/v1/library/list-by-session",
    data=json.dumps({'sessionId': os.environ['S4_THREAD']}).encode(),
    headers={'Authorization': f"Bearer {cache['token']}", 'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req, timeout=15) as resp:
    print('文件库图片记录:', resp.read().decode()[:500])
PY
```

### 人工 Web 端操作步骤（备选）
1. 新建会话发送上述文生图提示词，确认对话内正常渲染出浅蓝极简风格图片且无裂图、产物计数正常；
2. 继续发送保存指令，进入「文件库」确认可查到 `smoke-banner-test` 并可预览大图；验证完后手动删除测试图片。

### 判定标准
- [ ] **[L1]** 对话返回有效图片 URL，HTTP 探测为 `200` 且 `Content-Type` 为图片类型、大小 > 0。
- [ ] **[L2]** Langfuse 确认 `text_to_image` 工具调用成功。
- [ ] **[L3]** `/api/v1/library/list-by-session` 查到 `smoke-banner-test`；清理后无残留。

---

## SMOKE-005：【定时任务】创建近期定时任务、到点触发执行、终态收口与清理

- **覆盖目标**：① 创建定时任务；② XXL-JOB 到点实际触发并产生有效输出（防 `#92895` 零执行）；③ 终态正常未被空闲暂停覆盖（防 `#92897`）；④ 验证定时任务未挂载长期记忆；⑤ 清理测试任务。
- **前置条件**：`service-job` 运行正常，测试账号积分账户正常。

### 执行步骤（Agent / CLI 方式）

```bash
# Step 1: 计算东八区 T+3 分钟时间并创建一次性定时任务
export TRIGGER_HM=$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
t = datetime.now(timezone(timedelta(hours=8))) + timedelta(minutes=3)
print(t.strftime("%H:%M"))
PY
)
echo "计划触发时间(Asia/Shanghai): $TRIGGER_HM"

node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "帮我创建一个一次性定时任务，名称为「发版冒烟定时验证-可删」，在今天 $TRIGGER_HM 执行一次，执行内容为：用50字总结“定时任务冒烟触发成功”，不要调用任何其他工具。" \
  --expect "发版冒烟定时验证-可删" \
  --out "$RUN_DIR/artifacts/smoke005_create" --json > "$RUN_DIR/artifacts/smoke005_create.json"

export S5_THREAD=$(python3 -c "import json; print(json.load(open('$RUN_DIR/artifacts/smoke005_create.json'))['threadId'])")

# Step 2: 等待到点后约 1 分钟（建议先跑 SMOKE-006 再回头核验，节省等待时间），查询任务与执行记录
python3 - <<'PY'
import json, urllib.request
cache = json.load(open('.runtime/cache/kuaibuddy-preprod/token.json'))
base, token = cache['baseUrl'].rstrip('/'), cache['token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

req = urllib.request.Request(f'{base}/api/v1/schedule/scheduled', data=json.dumps({'page': 1, 'pageSize': 20}).encode(), headers=headers, method='POST')
with urllib.request.urlopen(req, timeout=15) as resp:
    tasks = json.loads(resp.read().decode())
print('定时任务列表（截取）:', json.dumps(tasks, ensure_ascii=False)[:800])

req_ex = urllib.request.Request(f'{base}/api/v1/schedule/executions', data=json.dumps({'page': 1, 'pageSize': 10}).encode(), headers=headers, method='POST')
with urllib.request.urlopen(req_ex, timeout=15) as resp:
    execs = json.loads(resp.read().decode())
print('最近执行记录（截取）:', json.dumps(execs, ensure_ascii=False)[:800])
PY

# Step 3: 拿执行记录中的定时 sessionId/runId 核验 Langfuse 未注入长期记忆
# （将 <SCHEDULED_RUN_ID> 替换为 Step 2 查到的定时执行 runId）
python3 - <<'PY'
import os, sys, json, urllib.request, urllib.parse, base64
rid = os.environ.get('SCHEDULED_RUN_ID', '')
if not rid:
    print('请先设置 export SCHEDULED_RUN_ID=<Step2查到的runId> 再执行本核验')
    raise SystemExit(0)
sys.path.insert(0, '.agents/skills/kb-bug-analyse/scripts')
import local_config
local_config.load_local_config()
env_key = os.environ.get('OBS_ENV', 'prd').upper()
host = os.environ[f'KB_LANGFUSE_{env_key}_URL'].rstrip('/')
auth = base64.b64encode(f"{os.environ[f'KB_LANGFUSE_{env_key}_PUBLIC_KEY']}:{os.environ[f'KB_LANGFUSE_{env_key}_SECRET_KEY']}".encode()).decode()
flt = json.dumps([{'type': 'stringObject', 'column': 'metadata', 'key': 'run_id', 'operator': '=', 'value': rid}])
url = f'{host}/api/public/v2/observations?fields=core,io&filter={urllib.parse.quote(flt)}'
req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
with urllib.request.urlopen(req, timeout=20) as resp:
    obs = json.loads(resp.read().decode()).get('data', [])
gens = [o for o in obs if o.get('type') == 'GENERATION']
inp_str = json.dumps(gens[0].get('input'), ensure_ascii=False) if gens else ''
print('是否误含长期记忆索引:', '## 长期记忆索引' in inp_str)
print('是否误含 memory_save 工具:', 'memory_save' in inp_str)
PY

# Step 4: 删除测试定时任务
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S5_THREAD" \
  "帮我删除刚才创建的定时任务「发版冒烟定时验证-可删」。" \
  --out "$RUN_DIR/artifacts/smoke005_cleanup" --json > "$RUN_DIR/artifacts/smoke005_cleanup.json"
```

### 人工 Web 端操作步骤（备选）
1. 在对话中发送上述创建定时任务指令（时间填当前时间 + 3 分钟），确认助手返回创建成功；
2. 到点后 1 分钟进入「自动化 / 定时任务」查看「发版冒烟定时验证-可删」的执行记录，点击进入对应会话，确认有实际生成“定时任务冒烟触发成功”回复，状态为成功且未报「未登录」；
3. 删除「发版冒烟定时验证-可删」任务。

### 判定标准
- [ ] **[L1]** 创建定时任务成功，`/api/v1/schedule/scheduled` 可查到任务。
- [ ] **[L1/L3]** 到点后 `/api/v1/schedule/executions` 有执行记录，对应定时会话有实际输出文本，无零执行、无「未登录」误报、终态非异常覆盖。
- [ ] **[L2]** 定时执行 `runId` 的 Langfuse `input` 中 **不包含** `## 长期记忆索引` 与 `memory_save` 工具。
- [ ] **[L3]** 清理后任务列表不再包含该测试任务。

---

## SMOKE-006：【长期记忆】跨会话写入召回、Cache 稳定性与记忆清理

- **覆盖目标**：① 交互式会话写入长期记忆并落库；② 新会话召回偏好且 `sysPrompt` 注入 `## 长期记忆索引`；③ 同一新会话第 2 轮 Cache 命中率不被打穿；④ 删除后物理清理干净。
- **前置条件**：目标环境已执行 `user_memory` 建表 DDL（若报错 `4055` 则直接判环境阻塞）；账号当前记忆条数 `< 100`。

### 执行步骤（Agent / CLI 方式）

```bash
# Step 1: 会话 A 写入测试记忆
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "请记住我的发版冒烟测试偏好：以后写周报时统一用【结论先行+三点列表】格式，并在结尾标注暗号 SMOKE-MEM-2026。" \
  --out "$RUN_DIR/artifacts/smoke006_a" --json > "$RUN_DIR/artifacts/smoke006_a.json"

# 核对 Web API 记忆列表已落库
python3 - <<'PY'
import json, urllib.request
cache = json.load(open('.runtime/cache/kuaibuddy-preprod/token.json'))
req = urllib.request.Request(
    f"{cache['baseUrl'].rstrip('/')}/api/v1/memory/list",
    headers={'Authorization': f"Bearer {cache['token']}"},
    method='GET'
)
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode())
items = data.get('data') or []
hits = [m for m in items if 'SMOKE-MEM-2026' in json.dumps(m, ensure_ascii=False)]
print('命中测试记忆条数:', len(hits))
for h in hits:
    print('  id=', h.get('id'), 'type=', h.get('memoryType'), 'summary=', h.get('summary'))
PY

# Step 2: 新建会话 B 第 1 轮——验证跨会话召回
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "帮我写一段100字以内的本周测试进展周报，按我的个人偏好格式输出。" \
  --expect "SMOKE-MEM-2026" \
  --out "$RUN_DIR/artifacts/smoke006_b1" --json > "$RUN_DIR/artifacts/smoke006_b1.json"

export S6_THREAD_B=$(python3 -c "import json; print(json.load(open('$RUN_DIR/artifacts/smoke006_b1.json'))['threadId'])")

# Step 3: 会话 B 第 2 轮——验证带长期记忆索引时的 Prompt Cache 命中率
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  --session "$S6_THREAD_B" \
  "把刚才这段周报精简到60字以内（纯模型输出，不要调用任何工具）。" \
  --out "$RUN_DIR/artifacts/smoke006_b2" --json > "$RUN_DIR/artifacts/smoke006_b2.json"

python3 - <<'PY'
import os, sys, json, urllib.request, urllib.parse, base64
sys.path.insert(0, '.agents/skills/kb-bug-analyse/scripts')
import local_config
local_config.load_local_config()
env_key = os.environ.get('OBS_ENV', 'prd').upper()
host = os.environ[f'KB_LANGFUSE_{env_key}_URL'].rstrip('/')
auth = base64.b64encode(f"{os.environ[f'KB_LANGFUSE_{env_key}_PUBLIC_KEY']}:{os.environ[f'KB_LANGFUSE_{env_key}_SECRET_KEY']}".encode()).decode()

for tag, fn in (('B1', 'smoke006_b1.json'), ('B2', 'smoke006_b2.json')):
    rid = json.load(open(f"{os.environ['RUN_DIR']}/artifacts/{fn}"))['runId']
    flt = json.dumps([{'type': 'stringObject', 'column': 'metadata', 'key': 'run_id', 'operator': '=', 'value': rid}])
    url = f'{host}/api/public/v2/observations?fields=core,usage,io&filter={urllib.parse.quote(flt)}'
    req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        gens = sorted([o for o in json.loads(resp.read().decode()).get('data', []) if o.get('type') == 'GENERATION'], key=lambda x: x.get('startTime', ''))
    u = gens[0].get('usageDetails') or gens[0].get('usage') or {}
    inp, cached = u.get('input', 0), u.get('input_cached_tokens', 0)
    rate = (cached / (inp + cached) * 100) if (inp + cached) else 0.0
    has_idx = '## 长期记忆索引' in json.dumps(gens[0].get('input'), ensure_ascii=False)
    print(f'{tag} ({rid}): has_memory_index={has_idx}, input={inp}, cached={cached}, hit_rate={rate:.2f}%')
PY

# Step 4: 新建会话 C 清理测试记忆，并核对 API 已物理删除
node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
  "忘记我之前让你记住的包含暗号 SMOKE-MEM-2026 的发版冒烟测试偏好。" \
  --out "$RUN_DIR/artifacts/smoke006_c" --json > "$RUN_DIR/artifacts/smoke006_c.json"

python3 - <<'PY'
import json, urllib.request
cache = json.load(open('.runtime/cache/kuaibuddy-preprod/token.json'))
req = urllib.request.Request(
    f"{cache['baseUrl'].rstrip('/')}/api/v1/memory/list",
    headers={'Authorization': f"Bearer {cache['token']}"},
    method='GET'
)
with urllib.request.urlopen(req, timeout=15) as resp:
    items = json.loads(resp.read().decode()).get('data') or []
hits = [m for m in items if 'SMOKE-MEM-2026' in json.dumps(m, ensure_ascii=False)]
print('清理后剩余测试记忆条数(应为0):', len(hits))
PY
```

### 人工 Web 端操作步骤（备选）
1. 新建会话 A 发送写入偏好提示词，确认助手回复已记住；点击左下角账户菜单「长期记忆」，确认列表中出现包含 `SMOKE-MEM-2026` 的新记录；
2. 新建会话 B 发送写周报提示词，确认回复采用“结论先行+三点列表”且末尾含 `SMOKE-MEM-2026`；
3. 新建会话 C 发送忘记偏好提示词，刷新「长期记忆」列表确认该条记录已删除。

### 判定标准
- [ ] **[L1/L3]** 会话 A 写入后，`GET /api/v1/memory/list` 可查到包含 `SMOKE-MEM-2026` 的记录。
- [ ] **[L1/L2]** 会话 B 第 1 轮回复含 `SMOKE-MEM-2026`，且 Langfuse 确认 `sysPrompt` 包含 `## 长期记忆索引`。
- [ ] **[L2]** 会话 B 第 2 轮 Prompt Cache 命中率 **≥ 90%**（待确认：按当前模型基线校准）。
- [ ] **[L3]** 会话 C 删除后，`GET /api/v1/memory/list` 不再包含 `SMOKE-MEM-2026` 记录（剩余为 0）。

---

## 附：汇总填报要求
执行完成后，在 `$RUN_DIR/result.md` 中逐条汇总 `SMOKE-001` ~ `SMOKE-006` 的状态（**通过 / 失败 / 阻塞 / 未执行**），并附上关键证据：`threadId`、`runId`、Cache 命中率数值、积分前后余额及所有测试脏数据清理确认。
