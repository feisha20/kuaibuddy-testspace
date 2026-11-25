# KB-SUITE-001：KuaiBuddy 多环境通用回归测试集

- 状态：演进中（持续补充）
- 所属模块：KuaiBuddy 全功能回归
- 优先级：P1
- 适用环境：`test`（测试）／`preprod`（预生产）／`prod`（生产，需单独授权）

## 1. 测试集定位
本测试集用于沉淀 KuaiBuddy 核心能力的**跨环境可复用测试用例**，覆盖多轮对话、Skill 与工具调用、缓存命中率、记忆、MCP 连接器及异常边界等场景。所有 Case 均采用环境参数化设计，不绑定单一环境或写死特定 Run 结果。

---

## 2. 多环境执行与观测配置

执行前先根据目标环境确定以下两个变量（具体凭据仅从本机对应 `.env.*` 文件加载，禁止写入命令或报告）：

| 目标环境 | `ENV_FILE`（对话 CLI） | `LF_ENV`（Langfuse 观测） | 适用说明 |
| :--- | :--- | :--- | :--- |
| **测试环境 (`test`)** | `.env.test` | `test` | 日常开发自测与回归 |
| **预生产环境 (`preprod`)** | `.env.preprod` | `prd` | 发布前验证（与生产共用 Langfuse 观测） |
| **生产环境 (`prod`)** | `.env.prod` | `prd` | 仅在获明确授权后执行，注意配额与数据脱敏 |

**通用前置检查**：
```bash
# 确认目标环境登录可用
KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login

# 确认当前环境可用 Skill / Agent 列表（按需选用）
KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js skills
```

---

## 3. 能力标签与覆盖矩阵（防重复设计）

为用**尽可能少的用例**覆盖 KuaiBuddy 核心能力，所有 Case 均挂载标准化能力标签；新增 Case 前先核对下表，**优先补齐“未覆盖”标签**，避免重复校验已覆盖能力。

### 3.1 能力覆盖总览

| 能力标签 | 能力说明 | 已覆盖用例 | 覆盖状态 |
| :--- | :--- | :--- | :--- |
| `#prompt-cache` | 跨轮与轮内多步 Prompt 前缀缓存命中率 | `CASE-01` | ✅ 已覆盖 |
| `#skill-load` | `/技能名` 触发与 Skill 说明动态加载 | `CASE-01` | ✅ 已覆盖 |
| `#tool-execute` | 命令行/内置工具调用及多步循环（Agentic Loop） | `CASE-01` | ✅ 已覆盖 |
| `#multi-turn-context` | 多轮上下文记忆、指代消解与跨轮数据融合 | `CASE-01` | ✅ 已覆盖 |
| `#no-redundant-tool` | 历史已有结果时直接推理、不重复调工具 | `CASE-01` | ✅ 已覆盖 |
| `#sse-stream-followup` | 思考链/正文流式分离与 Followup 追问生成 | `CASE-01` | ✅ 已覆盖 |
| `#long-memory` | 跨会话长期记忆写入与召回 | — | ⬜ 待补充 |
| `#mcp-connector` | 个人/团队 MCP 连接器发现与工具调用 | — | ⬜ 待补充 |
| `#multimodal-file` | 图片、文档等附件上传与解析 | — | ⬜ 待补充 |
| `#write-confirm` | 写操作/变更类动作的二次确认与权限拦截 | — | ⬜ 待补充 |
| `#error-fallback` | 工具报错、超时、无效输入等异常兜底与恢复 | — | ⬜ 待补充 |
| `#agent-switch` | 指定 Agent 切换与子 Agent 协作 | — | ⬜ 待补充 |

### 3.2 测试用例索引

| 用例编号 | 用例名称 | 覆盖标签 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| [CASE-01](#case-01skill-加载与多轮工具调用-prompt-缓存命中率验证) | Skill 加载与多轮工具调用 Prompt 缓存命中率验证 | `#prompt-cache` `#skill-load` `#tool-execute` `#multi-turn-context` `#no-redundant-tool` `#sse-stream-followup` | P1 | 已验证 |
| *后续新增* | *按 3.1 中 ⬜ 待补充标签逐步设计* | — | — | — |

---

## 4. 用例明细

### CASE-01：Skill 加载与多轮工具调用 Prompt 缓存命中率验证
- **测试目标**：验证在加载 Skill、连续多轮工具调用、工具结果入历史后纯文本追问、长上下文二次工具调用等真实场景下，LLM 前缀缓存（Prompt Cache）的跨轮与轮内命中率是否稳定。
- **最少轮次要求**：建议 **5 轮**（最低不少于 3 轮：第 1 轮冷启动、第 2 轮验证首次跨轮命中、第 3 轮验证工具结果入历史后连续命中）。
- **前置要求**：
  - 在目标环境中确认被测 Skill 可用（默认示例使用 `/快商通 IM 助手`，如目标环境未配置该 Skill，可替换为目标环境已启用的等价查询类 Skill 并同步调整第 2、4 轮问法）。
  - 全程在同一全新会话（`threadId`）内**串行**发送，轮间间隔建议 **< 1 分钟**（避免超过模型缓存 TTL 窗口）。
- **观测口径**：
  - 缓存命中率 = `input_cached_tokens / (input + input_cached_tokens) × 100%`

| 轮次 | 场景类型 | 输入内容（以「快商通 IM 助手」为例） | 预期交互行为 | 预期缓存指标（Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **第 1 轮** | Skill 加载冷启动 + 环境探测 | `/快商通 IM 助手` | 加载 Skill 说明，执行环境/鉴权检查并输出能力清单 | 首步冷启动写入；轮内后续 Step 命中率迅速上升至 **75%～99%** |
| **第 2 轮** | 跨轮首次业务查询（多步工具调用） | `查下今天各渠道的对话量和开口率` | 调用对应 CLI/工具查询数据并汇总 | 在 TTL 内首步命中第 1 轮前缀；轮内后续多步推理命中率 **90%～99%** |
| **第 3 轮** | 工具结果入历史后的纯文本追问 | `把上面查到的数据，帮我总结成 3 条核心要点` | 不重复调用工具，直接基于第 2 轮结果总结 | **关键检查点**：跨轮首步命中率 **≥ 95%**，`input_cached_tokens` 大于第 2 轮 |
| **第 4 轮** | 长上下文下二次发起新工具调用 | `再查一下昨天网页站点的数据，和前天对比一下` | 再次调用工具拉取对比数据并输出 | 跨轮首步及轮内工具返回后命中率保持 **95%～99%** |
| **第 5 轮** | 多轮累积后的纯文本汇总 | `综合刚才查到的渠道和网页站点数据，给一条简短的运营建议` | 基于全量历史直接输出建议 | 跨轮命中率保持 **≥ 95%**，`input_cached_tokens` 达到本会话峰值且单调递增 |

- **跨环境执行命令模板**（将 `<ENV_FILE>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 第 1 轮（新建会话并获取 threadId）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "/快商通 IM 助手" --out "<OUT_DIR>/turn-1" --json

  # 第 2~5 轮（使用第 1 轮返回的 THREAD_ID 串行执行）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "查下今天各渠道的对话量和开口率" --session "$THREAD_ID" --out "<OUT_DIR>/turn-2" --json

  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "把上面查到的数据，帮我总结成 3 条核心要点" --session "$THREAD_ID" --out "<OUT_DIR>/turn-3" --json

  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "再查一下昨天网页站点的数据，和前天对比一下" --session "$THREAD_ID" --out "<OUT_DIR>/turn-4" --json

  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "综合刚才查到的渠道和网页站点数据，给一条简短的运营建议" --session "$THREAD_ID" --out "<OUT_DIR>/turn-5" --json
  ```

- **Langfuse 用量核对命令**（将 `<LF_ENV>` 替换为 `test` 或 `prd`，`<RUN_ID_LIST>` 为各轮 `runId`）：
  ```bash
  python3 - <<'PY'
  import sys, json
  sys.path.insert(0, ".agents/skills/kb-bug-analyse/scripts")
  from local_config import load_local_config
  load_local_config()
  import langfuse_fetch as lf

  cfg = lf.LANGFUSE_CONFIG["<LF_ENV>"]
  run_ids = ["<TURN_1_RUN_ID>", "<TURN_2_RUN_ID>", "<TURN_3_RUN_ID>", "<TURN_4_RUN_ID>", "<TURN_5_RUN_ID>"]
  for idx, rid in enumerate(run_ids, 1):
      flt = json.dumps([{"column":"metadata","key":"run_id","operator":"=","value":rid,"type":"stringObject"}])
      res = lf.api_get(cfg, lf.V2_OBSERVATIONS_PATH, {"filter": flt, "fields": "core,usage,model,time", "limit": 100})
      gens = sorted([o for o in res.get("data", []) if o.get("type") == "GENERATION"], key=lambda x: x.get("startTime") or "")
      for s, g in enumerate(gens, 1):
          u = g.get("usageDetails") or {}
          inp, cached = u.get("input", 0), u.get("input_cached_tokens", 0)
          tot = inp + cached
          rate = (cached / tot * 100) if tot else 0.0
          print(f"Turn {idx} Step {s}: input={inp} cached={cached} total_in={tot} hit_rate={rate:.2f}%")
  PY
  ```

---

## 5. 执行与产物规范
- 每次按本测试集执行时，在 `.runtime/requests/<中文请求概要>/<RUN_ID>/`（或对应长期任务目录）记录实际环境、`threadId`、`runId` 与实测结果，不直接修改本测试集文件写入单次结果。
