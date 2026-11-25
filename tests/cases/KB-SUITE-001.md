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
| `#context-compaction` | 达到阈值触发上下文压缩、关键信息保真及压缩后缓存重建 | `CASE-02` | ✅ 已覆盖 |
| `#large-file-read` | 大体积工具输出 / 大文件读取（受 `read-file-max-chars` 约束） | `CASE-02` | ✅ 已覆盖 |
| `#agent-switch` | 指定 Agent 切换与子 Agent 协作 | — | ⬜ 待补充 |

### 3.2 测试用例索引

| 用例编号 | 用例名称 | 覆盖标签 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| [CASE-01](#case-01skill-加载与多轮工具调用-prompt-缓存命中率验证) | Skill 加载与多轮工具调用 Prompt 缓存命中率验证 | `#prompt-cache` `#skill-load` `#tool-execute` `#multi-turn-context` `#no-redundant-tool` `#sse-stream-followup` | P1 | 已验证 |
| [CASE-02](#case-02上下文压缩触发与关键信息保真验证) | 上下文压缩触发与关键信息保真验证 | `#context-compaction` `#large-file-read` | P1 | 已验证 |
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

### CASE-02：上下文压缩触发与关键信息保真验证
- **覆盖标签**：`#context-compaction` `#large-file-read`
- **测试目标**：验证当对话历史估算 Token 数达到目标环境配置阈值时，是否精准触发上下文压缩（Compaction）；压缩后初始关键业务实体是否完整保留不失忆，且上下文体积回落后能正常继续对话与重建缓存。
- **配置与口径核对（执行前必查）**：
  - 从目标环境 Nacos `service-agent.yaml` 核对 `compaction` 与 `tool` 配置项：
    - `compaction.trigger-messages`：按消息条数触发阈值（预生产/测试环境当前均为 `0`，即关闭按条数过早触发）
    - `compaction.trigger-tokens`：按 Token 数触发阈值（预生产/生产当前为 `400000`；若测试环境未显式配置，则取 `AgentProperties` 代码默认值 `240000`）
    - `tool.read-file-max-chars`：单次读文件字符上限（预生产/测试环境当前均为 `64000`）
  - **框架估算口径说明（已核实）**：
    - 后端框架使用 `mixed-text-2.5chars-media-2048-v1`（纯文本按 **2.5 字符 = 1 token**）进行本地静态估算，在每轮 `context_build` SSE 事件中输出 `estimatedInputTokens`。
    - `trigger-tokens` **仅统计对话历史消息**，不包含第 1 轮基准固定开销（System Prompt + Tools Schema + 运行时上下文，预生产约 `33,500` 估算 tokens）。
    - **禁止使用纯随机 ASCII 乱码填充**：随机乱码在 BPE 分词下的密度（~1.44 字符/token）远高于日常业务文本，会导致模型实际 `total_in` 虚高至配置值的 ~1.7 倍；本用例固定采用结构化**中文 + JSON 仿真业务日志**。

| 轮次 | 场景类型 | 固定输入提示词（Exact Prompt，执行时不可自由改写） | 预期交互行为 | 预期双口径观测指标（`events.json` + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **第 1 轮** | 植入关键锚点实体 | `请记住以下本次任务的三个核心锚点信息，后续无论如何总结都不能丢失：1）客户编号 CUST-20261125；2）订单号 ORD-998877；3）退款上限 3480.00元。只需回复“已记住”，不要调用任何工具。` | 回复确认已记住 3 个核心锚点 | 记录 `events.json` 中 `context_build.estimatedInputTokens` 作为固定开销基准 `EST_BASE`（约 `33.5k`），以及 Langfuse `total_in` |
| **填充轮**<br>(`k = 1, 2, ...`) | 确定性填充中文+JSON 业务日志至触发压缩 | 每次将 `<BATCH_NO>` 替换为递增整数 `1, 2, 3...` 串行发送以下固定提示词，直到 `events.json` 出现 `transforms: ["history_compaction"]` 后停止：<br>`请用 execute 工具执行 python3 -c "import json; rows=[json.dumps({'batch':<BATCH_NO>,'seq':i,'ts':f'2026-11-25T10:{i%60:02d}:00','custId':f'C-<BATCH_NO>-{i:04d}','orderId':f'ORD-20261125-<BATCH_NO>-{i:04d}','channel':'官网网页','intent':'售后退货进度与赔付核对','summary':f'访客第{i}次咨询订单物流拦截与部分退款处理状态，客服核实仓库尚未出库并已登记加急备注。'},ensure_ascii=False) for i in range(420)]; open('/tmp/pad_<BATCH_NO>.txt','w').write('\n'.join(rows)[:50000])" 生成日志，再用 read_file 读取 /tmp/pad_<BATCH_NO>.txt 的全文，最后只回复“第<BATCH_NO>批已读取”。` | 沙箱生成 50,000 字符中文+JSON 仿真业务日志并分页读入上下文，回复确认 | 每轮扣除 `EST_BASE` 后的历史估算 `est - EST_BASE` 稳定增加约 `20k`；当 `est - EST_BASE >= trigger-tokens` 时，`context_build` 触发 `transforms: ["history_compaction"]` |
| **校验轮 A**<br>（压缩后） | 验证锚点保真 + 压缩生效 | `现在请完整复述第 1 轮我让你记住的三个核心锚点信息（客户编号、订单号、退款上限），不要调用工具，一字不差输出。` | 准确复述 `CUST-20261125`、`ORD-998877`、`3480.00元`，无丢失或篡改 | 1. **压缩生效**：本轮 `est` 与 Langfuse `total_in` 均较填充峰值**显著回落**；<br>2. **触发精准度**：历史估算在跨越 `trigger-tokens` 当步立即压缩 |
| **校验轮 B**<br>（紧接轮 A） | 验证压缩后缓存重建 | `基于以上对话，用50字以内总结本次测试任务的核心要求，不要调用工具。` | 正常输出简短总结 | **缓存重建**：本轮 `input_cached_tokens` 命中压缩后的新前缀，命中率恢复至 **≥ 80%** |

- **通过标准（双口径验收）**：
  1. 未达 `trigger-tokens` 前不提前触发按条数压缩（当 `trigger-messages == 0` 时）。
  2. 当 `events.json` 历史估算（`estimatedInputTokens - EST_BASE`）首次达到 `trigger-tokens` 时精准触发 `transforms: ["history_compaction"]`，压缩后 `total_in` 显著回落，不报 `ContextBudgetExceededException`（`BizCode 4054`）。
  3. 第 1 轮植入的 3 个关键实体 100% 准确保留，无丢失或篡改。
  4. 校验轮 B 的 Prompt Cache 命中率恢复至 **≥ 80%**。

---

## 5. 执行与产物规范
- 每次按本测试集执行时，在 `.runtime/requests/<中文请求概要>/<RUN_ID>/`（或对应长期任务目录）记录实际环境、`threadId`、`runId` 与实测结果，不直接修改本测试集文件写入单次结果。
