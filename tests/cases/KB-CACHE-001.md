# KB-CACHE-001：预生产环境 Prompt Cache 缓存命中率回归测试用例

## 1. 测试目标
验证 KuaiBuddy 预生产环境在多轮对话、跨会话前缀复用、工具调用及**多个人 MCP 连接器账号**场景下的 LLM 前缀缓存（Prompt Cache）命中率是否稳定达标，重点回归「个人 MCP 使用状态」连接器顺序抖动导致前缀缓存失效的问题。

## 2. 前置条件
- **环境**：预生产环境 `https://test-kuaibuddy.dingningtalk.com`（公司 ID：`232679`）
- **测试账号**：
  - **多 MCP 账号（回归重点）**：`.env.preprod`（`testpro`，绑定 ≥ 2 个个人 MCP 连接器）
  - **无 MCP 对照账号**：`testpro2`（未绑定个人 MCP 连接器）
- **可观测数据源**：Langfuse `prd` 环境（通过 `.env.observability` + `.agents/skills/kb-bug-analyse/scripts/local_config.py` 读取）
- **缓存命中率计算口径**：
  - 总输入 tokens = `input + input_cached_tokens`
  - 缓存命中率 = `input_cached_tokens / (input + input_cached_tokens) × 100%`

---

## 3. 回归测试用例清单

### TC-01：多 MCP 账号连续 3 轮纯模型对话（核心回归）
- **目的**：验证绑定多个个人 MCP 连接器的账号（`testpro`）在连续多轮对话中，System Prompt 内「个人 MCP 使用状态」顺序是否固定，第 2、3 轮是否稳定命中完整前缀缓存。
- **执行命令**：
  ```bash
  # 1. 强制登录多 MCP 账号（使用 .env.preprod）
  KB_ENV_FILE=.env.preprod node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force

  # 2. 第 1 轮（记录输出的 threadId 和 runId）
  KB_ENV_FILE=.env.preprod node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "请用约800字介绍一下企业微信私域运营的核心流程（纯模型输出，不要调用任何工具或skill）。" \
    --json > /tmp/cache_r1.json

  THREAD_ID=$(python3 -c "import json; print(json.load(open('/tmp/cache_r1.json'))['threadId'])")

  # 3. 第 2 轮
  KB_ENV_FILE=.env.preprod node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    --session "$THREAD_ID" \
    "基于上面的内容，再补充3条落地时的常见避坑建议，约300字（纯模型输出，不要调用任何工具或skill）。" \
    --json > /tmp/cache_r2.json

  # 4. 第 3 轮
  KB_ENV_FILE=.env.preprod node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    --session "$THREAD_ID" \
    "把上面所有内容提炼成一张5行的要点清单（纯模型输出，不要调用任何工具或skill）。" \
    --json > /tmp/cache_r3.json
  ```
- **通过标准**：
  - 第 2 轮缓存命中率 **≥ 90%**（修复前为 ~7.16% 或 ~63%）。
  - 第 3 轮缓存命中率 **≥ 90%**。
  - 3 轮 `input` 原文中的「个人 MCP 使用状态」连接器顺序完全一致。

---

### TC-02：无 MCP 对照账号连续 3 轮纯模型对话（基线对照）
- **目的**：验证未绑定个人 MCP 连接器的账号（`testpro2`）缓存命中率保持基线水平。
- **执行命令**：
  ```bash
  # 先从本机可信配置加载对照账号的 KB_URL、KB_COMPANY_ID、KB_USERNAME、KB_PASSWORD。
  # 本用例使用进程变量方式，先取消当前 shell 中的 KB_ENV_FILE。
  unset KB_ENV_FILE
  node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force
  # 后续 3 轮 ask 命令同 TC-01，每次使用已加载的对照账号进程变量，省略 KB_ENV_FILE=.env.preprod
  ```
- **通过标准**：
  - 第 2 轮缓存命中率 **≥ 90%**。
  - 第 3 轮缓存命中率 **≥ 95%**。

---

### TC-03：同账号跨会话首轮 System Prompt 复用
- **目的**：验证同一账号在短时间内（1 分钟内）新开第 2 个会话时，首轮即可复用 System Prompt 前缀缓存。
- **执行命令**：
  ```bash
  # 在 TC-01 完成后 1 分钟内，不传 --session 新开会话
  KB_ENV_FILE=.env.preprod node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "用100字说明企业微信客户标签的作用（纯模型输出，不要调用工具）" \
    --json > /tmp/cache_new_s1.json
  ```
- **通过标准**：
  - 新会话第 1 轮缓存命中率 **≥ 60%**（`input_cached_tokens` 覆盖 System Prompt 主体）。

---

### TC-04：单轮工具调用场景（多步 Generation 缓存复用）
- **目的**：验证单轮内触发多次工具调用时，后续推理步能够复用前面步骤的上下文缓存。
- **执行命令**：
  ```bash
  KB_ENV_FILE=.env.preprod node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "帮我查一下当前有哪些可用的客户标签或群发任务（如需调用工具请正常调用）" \
    --json > /tmp/cache_tool.json
  ```
- **通过标准**：
  - 同一 `runId` 下，Step 2 及后续 `GENERATION` 缓存命中率逐步提升并稳定在 **85%–99%**，不出现因 System Prompt 抖动导致的归零（`0.00%`）。

---

## 4. 一键统计脚本（Langfuse 命中率 + 前缀 Diff 检查）

执行完上述用例后，运行以下脚本即可自动统计各 `runId` 的缓存命中率，并检查 `R1` 与 `R2` 的 System Prompt 前缀是否一致：

```bash
python3 - <<'PY'
import os, sys, json, urllib.request, urllib.parse, base64
sys.path.insert(0, '.agents/skills/kb-bug-analyse/scripts')
import local_config

local_config.load_local_config()
host = os.environ['KB_LANGFUSE_PRD_URL'].rstrip('/')
pub = os.environ['KB_LANGFUSE_PRD_PUBLIC_KEY']
sec = os.environ['KB_LANGFUSE_PRD_SECRET_KEY']
auth = base64.b64encode(f'{pub}:{sec}'.encode()).decode()

files = [
    ('TC-01 R1', '/tmp/cache_r1.json'),
    ('TC-01 R2', '/tmp/cache_r2.json'),
    ('TC-01 R3', '/tmp/cache_r3.json'),
]

inputs = {}
for label, path in files:
    if not os.path.exists(path):
        continue
    rid = json.load(open(path))['runId']
    flt = json.dumps([{'type': 'stringObject', 'column': 'metadata', 'key': 'run_id', 'operator': '=', 'value': rid}])
    url = f'{host}/api/public/v2/observations?fields=core,usage,io&filter={urllib.parse.quote(flt)}'
    req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    gens = sorted([o for o in data.get('data', []) if o.get('type') == 'GENERATION'], key=lambda x: x.get('startTime', ''))
    for idx, o in enumerate(gens, 1):
        u = o.get('usageDetails') or o.get('usage') or {}
        inp = u.get('input', 0)
        cached = u.get('input_cached_tokens', 0)
        tot_in = inp + cached
        out = u.get('output', 0)
        rate = (cached / tot_in * 100) if tot_in else 0.0
        print(f'{label} Step{idx} ({rid}): input={inp} cached={cached} total_in={tot_in} output={out} hit_rate={rate:.2f}%')
        if idx == 1 and o.get('input'):
            inputs[label] = o['input']

if 'TC-01 R1' in inputs and 'TC-01 R2' in inputs:
    s1, s2 = inputs['TC-01 R1'], inputs['TC-01 R2']
    pos = next((k for k, (a, b) in enumerate(zip(s1, s2)) if a != b), min(len(s1), len(s2)))
    print(f'\n[Prefix Diff] TC-01 R1 vs R2 first diff at char {pos} / {len(s1)}')
    if pos < 10000:
        print('  WARNING: Diff occurred in System Prompt! Check MCP order or dynamic prefix:')
        print('  R1:', repr(s1[max(0, pos-40):pos+80]))
        print('  R2:', repr(s2[max(0, pos-40):pos+80]))
    else:
        print('  OK: System Prompt prefix is 100% identical.')
PY
```
