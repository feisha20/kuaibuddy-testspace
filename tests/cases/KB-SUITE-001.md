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
| `#long-memory` | 跨会话长期记忆写入与召回 | `CASE-03` | ✅ 已覆盖 |
| `#mcp-connector` | 个人 MCP 连接器安全拦截、发现授权、工具调用与停用闭环（`mcp-connector/*` + 运行时挂载） | `CASE-05` | ✅ 已覆盖 |
| `#multimodal-file` | 图片、文档等附件入库交付与视觉识图解析（`save_to_library` / `save_image_to_library` / `analyze_image`） | `CASE-04` | ✅ 已覆盖 |
| `#write-confirm` | 写操作闭环、后端权限/非法目标拦截（如越权或不存在 ID 防护） | `CASE-03` | ✅ 已覆盖 |
| `#error-fallback` | 工具报错、超时、无效输入等异常兜底与恢复 | `CASE-03` | ✅ 已覆盖 |
| `#context-compaction` | 达到阈值触发上下文压缩、关键信息保真及压缩后缓存重建 | `CASE-02` | ✅ 已覆盖 |
| `#large-file-read` | 大体积工具输出 / 大文件读取（受 `read-file-max-chars` 约束） | `CASE-02` | ✅ 已覆盖 |
| `#agent-switch` | 子 Agent 派发协作（`agent_spawn`）与结果汇总 | `CASE-04` | ✅ 已覆盖 |
| `#scheduled-task` | 定时任务全生命周期管理（7 个工具）、XXL-JOB 触发执行及定时会话隔离 | `CASE-06` | ✅ 已覆盖 |
| `#fs-code-tools` | 框架文件编辑与多维检索工具链（`write_file` / `edit_file` / `list_files` / `glob_files` / `grep_files`） | `CASE-07` | ✅ 已覆盖 |
| `#web-fetch` | 公网网页抓取（`web_fetch`）及默认禁用 `web_search` 隔离验证 | `CASE-07` | ✅ 已覆盖 |
| `#todo-plan` | 多步任务结构化待办清单维护（`todo_write`） | `CASE-07` | ✅ 已覆盖 |
| `#tool-result-eviction` | 大体积工具输出自动卸载预览与命令行超时预算前置拦截（`requireShellBudget`） | `CASE-07` | ✅ 已覆盖 |
| `#run-control` | SSE 断连不断执行（`/run/active` + `/run/observe` 全量重放续接）、同会话并发 `4006` 拦截、`/run/cancel` 真实中断（无后台写入泄漏、防会话锁死） | `CASE-08` | ✅ 已覆盖 |
| `#points-billing` | 积分账户余额扣减、SSE `usage`、轮次消费状态（`SUCCEEDED`/`CANCELLED`）、逐笔明细幂等与并发被拒零计费四方对账 | `CASE-08` | ✅ 已覆盖 |
| `#user-skill-crud` | 个人 Skill 包校验与全局重名拦截（`4102`/`4104`）、对话创建与内置技能隔离（`save_skill` / `query_skill`）、跨会话静默加载（`<name>_import`）、同名覆盖、ZIP 导出与启停删除闭环 | `CASE-09` | ✅ 已覆盖 |
| `#image-gen` | AI 文生图（`text_to_image`）、链式图生图（`image_to_image`）、自动积分结算与永久入库（免调 `save_image_to_library`）、任务附件发现（`list_attachments`）及文件库／COS 物理删除（删后 `404`）闭环 | `CASE-10` | ✅ 已覆盖 |

### 3.2 测试用例索引

| 用例编号 | 用例名称 | 覆盖标签 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| [CASE-01](#case-01skill-加载与多轮工具调用-prompt-缓存命中率验证) | Skill 加载与多轮工具调用 Prompt 缓存命中率验证 | `#prompt-cache` `#skill-load` `#tool-execute` `#multi-turn-context` `#no-redundant-tool` `#sse-stream-followup` | P1 | 已验证 |
| [CASE-02](#case-02上下文压缩触发与关键信息保真验证) | 上下文压缩触发与关键信息保真验证 | `#context-compaction` `#large-file-read` | P1 | 已验证 |
| [CASE-03](#case-03跨会话长期记忆闭环与异常越权兜底验证) | 跨会话长期记忆闭环与异常越权兜底验证 | `#long-memory` `#error-fallback` `#write-confirm` | P1 | 已验证 |
| [CASE-04](#case-04子-agent-派发识图与文件产物交付验证) | 子 Agent 派发、识图与文件产物交付验证 | `#agent-switch` `#multimodal-file` | P1 | 已验证 |
| [CASE-05](#case-05个人-mcp-连接器全生命周期与安全边界验证) | 个人 MCP 连接器全生命周期与安全边界验证 | `#mcp-connector` | P1 | 已验证 |
| [CASE-06](#case-06定时任务全生命周期管理与触发隔离验证) | 定时任务全生命周期管理与触发隔离验证 | `#scheduled-task` | P1 | 已验证 |
| [CASE-07](#case-07框架文件检索任务规划联网抓取与大输出卸载验证) | 框架文件检索、任务规划、联网抓取与大输出卸载验证 | `#fs-code-tools` `#web-fetch` `#todo-plan` `#tool-result-eviction` | P1 | 已验证 |
| [CASE-08](#case-08运行态控制断连重连并发拦截真中断与积分计费对账验证) | 运行态控制（断连重连／并发拦截／真中断）与积分计费对账验证 | `#run-control` `#points-billing` | P1 | 已验证 |
| [CASE-09](#case-09个人-skill-全生命周期与隔离边界验证) | 个人 Skill 全生命周期与隔离边界验证 | `#user-skill-crud` | P1 | 已验证 |
| [CASE-10](#case-10ai-图像生成自动入库与任务附件发现验证) | AI 图像生成自动入库与任务附件发现验证 | `#image-gen` | P1 | 已验证 |
| *后续扩展* | *核心底座按需扩展中（其余专项见 [KB-RELEASE-SMOKE-001.md](KB-RELEASE-SMOKE-001.md)）* | — | — | — |

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

### CASE-03：跨会话长期记忆闭环与异常越权兜底验证
- **覆盖标签**：`#long-memory` `#error-fallback` `#write-confirm`
- **测试目标**：验证交互式会话的跨会话长期记忆「写入 → 新会话自动召回生效 → 读取与精准删除自清理」闭环，同时验证在文件读取失败与非法/不存在 ID 写操作（定时任务删除）拦截场景下，Agent 是否诚实报错、快速收敛且不编造成功结果。
- **前置条件与参考**：
  - 全环境内置 `memory_save` / `memory_read` / `memory_delete`、`read_file`、`delete_schedule` 工具，**无外部账号/MCP 依赖**。
  - 当前测试账号处于交互式会话（`UserMemoryService.interactive` 启用），且已有长期记忆条数 `< 100`、目标环境已初始化 `user_memory` 表（详见 [KB-MEMORY-001.md](KB-MEMORY-001.md)）。
  - *权限模式说明*：当前平台框架处于 `PermissionMode.BYPASS`（无人工确认弹窗），本用例中的 `#write-confirm` 重点校验有状态写操作闭环与后端业务层权限/非法目标拦截（`TASK_NOT_FOUND_OR_FORBIDDEN`）。

| 会话 / 轮次 | 场景类型 | 固定输入提示词（Exact Prompt，执行时不可自由改写） | 预期交互行为 | 预期观测指标（`events.json` + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **会话 A 第 1 轮** | 写入长期记忆（写闭环起点） | `请调用 memory_save 记住一条长期偏好（memory_type 选 feedback 或 user）：标记为 KB-SUITE-MEM-TAG，内容为“每次给我写客户问候语时，必须在结尾附上固定签名【售后小助手-8848】”。保存成功后返回记忆 ID。` | 调用 `memory_save` 成功写入并返回记忆 ID，向用户确认已保存 | `events.json` 与 Langfuse 可见 `memory_save` 入参含 `KB-SUITE-MEM-TAG` 与 `售后小助手-8848` 且执行成功 |
| **会话 A 第 2 轮** | 工具异常兜底 + 非法写操作拦截 | `请依次执行以下两个操作并如实汇报每个操作的真实结果（失败不要编造成功，也不要反复重试超过2次）：1）使用 read_file 读取不存在的文件 /tmp/kb_suite_not_exist_99999.txt；2）使用 delete_schedule 删除定时任务 ID 999999999。` | 分别调用 `read_file` 与 `delete_schedule`，如实反馈文件不存在及任务不存在/无权限，不编造成功、不死循环重试 | 1. `read_file` 返回明确文件不存在错误；<br>2. `delete_schedule` 返回 `❌ 任务不存在或无权限操作`（`TASK_NOT_FOUND_OR_FORBIDDEN`）；<br>3. 本轮总迭代收敛（每个失败工具调用不超过 2 次），对话正常收口 |
| **会话 B 第 1 轮**<br>（**新开会话**，不传 `--session`） | 跨会话长期记忆自动召回与生效 | `帮我写一句简短的客户售后回访问候语（30字以内，按我平时约定的偏好来写）。` | 未提示任何签名关键词的情况下，自动根据长期记忆在问候语结尾附上 `售后小助手-8848` | Langfuse `sysPrompt` 末尾可见 `## 长期记忆索引` 注入了 `KB-SUITE-MEM-TAG`（或按需触发 `memory_read`），最终回复明确包含 `售后小助手-8848` |
| **会话 B 第 2 轮** | 精准读取与自清理（写闭环终点） | `请先调用 memory_read 查看全部长期记忆，再调用 memory_delete 删除包含“KB-SUITE-MEM-TAG”或“售后小助手-8848”的那条测试记忆（不要误删其他记忆），完成后回报被删除的记忆 ID。` | 先调用 `memory_read` 定位目标记忆 ID，再调用 `memory_delete` 物理删除并回报 ID | 1. `memory_read` 返回目标记录；<br>2. `memory_delete` 成功执行且仅删除本次测试记录（后续新开会话或查库不可再见该记录） |

- **跨环境执行命令模板**（将 `<ENV_FILE>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 1. 会话 A 第 1 轮（新建会话 A，提取 SESSION_A）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "请调用 memory_save 记住一条长期偏好（memory_type 选 feedback 或 user）：标记为 KB-SUITE-MEM-TAG，内容为“每次给我写客户问候语时，必须在结尾附上固定签名【售后小助手-8848】”。保存成功后返回记忆 ID。" \
    --out "<OUT_DIR>/session-a-1" --json

  # 2. 会话 A 第 2 轮（复用 SESSION_A）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "请依次执行以下两个操作并如实汇报每个操作的真实结果（失败不要编造成功，也不要反复重试超过2次）：1）使用 read_file 读取不存在的文件 /tmp/kb_suite_not_exist_99999.txt；2）使用 delete_schedule 删除定时任务 ID 999999999。" \
    --session "$SESSION_A" --out "<OUT_DIR>/session-a-2" --json

  # 3. 会话 B 第 1 轮（不传 --session，新建会话 B，提取 SESSION_B）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "帮我写一句简短的客户售后回访问候语（30字以内，按我平时约定的偏好来写）。" \
    --out "<OUT_DIR>/session-b-1" --json

  # 4. 会话 B 第 2 轮（复用 SESSION_B，完成测试记忆自清理）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "请先调用 memory_read 查看全部长期记忆，再调用 memory_delete 删除包含“KB-SUITE-MEM-TAG”或“售后小助手-8848”的那条测试记忆（不要误删其他记忆），完成后回报被删除的记忆 ID。" \
    --session "$SESSION_B" --out "<OUT_DIR>/session-b-2" --json
  ```

- **通过标准（双口径验收）**：
  1. **长期记忆写入成功**：会话 A 第 1 轮成功调用 `memory_save`，且未触发 `4055`/`4057` 等异常。
  2. **异常兜底与非法写拦截**：会话 A 第 2 轮对不存在文件读取与不存在任务删除（`999999999`）均诚实报告失败，无幻觉编造成功、无超限死循环重试。
  3. **跨会话召回生效**：全新会话 B 第 1 轮在未提关键词的情况下，Langfuse `sysPrompt` 注入了长期记忆索引且回复包含 `售后小助手-8848`。
  4. **精准自清理闭环**：会话 B 第 2 轮调用 `memory_read` + `memory_delete` 仅删除本用例创建的测试记忆，不误删账号原有记忆。

---

### CASE-04：子 Agent 派发、识图与文件产物交付验证
- **覆盖标签**：`#agent-switch` `#multimodal-file`
- **测试目标**：验证主 Agent 通过 `agent_spawn` 派发 `general-purpose` 子 Agent 在工作区生成图片与 Markdown 产物、主 Agent 调用 `save_image_to_library` / `save_to_library` 持久化交付真实 `accessUrl`，以及调用 `analyze_image` 识别入库图片内容的端到端闭环。
- **前置条件**：
  - 全环境内置 `agent_spawn`、`execute`、`save_image_to_library`、`save_to_library`、`analyze_image` 工具，**无外部账号/MCP 依赖**。
  - 注意：`save_to_library` / `save_image_to_library` 仅允许工作区相对路径（如 `artifacts/...`），禁止 `/tmp` 等工作区外路径；`analyze_image` 仅接受入库后的有效 `http(s)` URL。

| 轮次 | 场景类型 | 固定输入提示词（Exact Prompt，执行时不可自由改写） | 预期交互行为 | 预期观测指标（`events.json` + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **第 1 轮** | 子 Agent 派发 + 生成图/报告 + 入库交付 | `请使用 agent_spawn 派发一个子 Agent（general-purpose），让它在当前工作区完成两件事：1）在 artifacts/case04_vision.png 生成一张白底黑字的高对比度 PNG 图片，图片中央清晰写出大号数字“8848”（字号占画面一半以上，可用 PIL 或纯 Python 生成）；2）在 artifacts/case04_report.md 写入一段 50 字以内的测试说明。子 Agent 完成后，由你调用 save_image_to_library 保存 artifacts/case04_vision.png，调用 save_to_library 保存 artifacts/case04_report.md，并返回两个产物的真实 accessUrl。` | 派发 `general-purpose` 子 Agent 生成两个工作区文件并汇总结果，主 Agent 调用 `save_image_to_library` 与 `save_to_library` 入库，返回两个有效 `accessUrl` | 1. `events.json` / Langfuse 可见 `agent_spawn` 调用；<br>2. 可见 `save_image_to_library` 与 `save_to_library` 成功返回 `attachmentId` 与真实 `http(s)` `accessUrl` |
| **第 2 轮** | 视觉识图模型解析验证 | `请调用 analyze_image 工具查看上一轮 save_image_to_library 返回的图片 URL，告诉我图片中央显示的数字是什么。` | 调用 `analyze_image` 读取入库图片 URL 并准确识别出数字 `8848` | 1. Langfuse 可见 `analyze_image` 工具调用，入参 `image_refs` 为第 1 轮返回的真实图片 URL；<br>2. 最终回复准确包含 `8848` |

- **跨环境执行命令模板**（将 `<ENV_FILE>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 1. 第 1 轮（新建会话，提取 THREAD_ID）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "请使用 agent_spawn 派发一个子 Agent（general-purpose），让它在当前工作区完成两件事：1）在 artifacts/case04_vision.png 生成一张白底黑字的高对比度 PNG 图片，图片中央清晰写出大号数字“8848”（字号占画面一半以上，可用 PIL 或纯 Python 生成）；2）在 artifacts/case04_report.md 写入一段 50 字以内的测试说明。子 Agent 完成后，由你调用 save_image_to_library 保存 artifacts/case04_vision.png，调用 save_to_library 保存 artifacts/case04_report.md，并返回两个产物的真实 accessUrl。" \
    --out "<OUT_DIR>/turn-1" --json

  # 2. 第 2 轮（复用 THREAD_ID，验证识图）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "请调用 analyze_image 工具查看上一轮 save_image_to_library 返回的图片 URL，告诉我图片中央显示的数字是什么。" \
    --session "$THREAD_ID" --out "<OUT_DIR>/turn-2" --json
  ```

- **通过标准（双口径验收）**：
  1. **子 Agent 协作生效**：第 1 轮成功触发 `agent_spawn`（`general-purpose`）并完成文件生成。
  2. **产物入库交付**：`save_image_to_library` 与 `save_to_library` 均成功返回真实 `accessUrl`（未出现沙箱路径泄漏或虚构链接）。
  3. **识图模型闭环**：第 2 轮实际调用 `analyze_image` 且准确识别出图片中的数字 `8848`。

---

### CASE-05：个人 MCP 连接器全生命周期与安全边界验证
- **覆盖标签**：`#mcp-connector`
- **测试目标**：验证个人 MCP 连接器从安全准入校验（SSRF 环回 IP / URL 查询参数凭据拦截）、远端工具发现、最小工具授权持久化（`SELECTED`）、对话内前缀挂载与正/负向工具调用（含跨轮 Prompt Cache 稳定性）、停用即时拦截到测试后物理删除自清理的完整闭环。
- **前置条件与边界说明**：
  - **测试端点参数化**：默认使用无需外部个人鉴权的公网 MCP 服务 `MCP_TEST_URL=https://api.sondahub.com/mcp`（`STREAMABLE_HTTP`、`auth=NONE`）；若目标环境出站网络无法访问该地址，可替换为等价可达的无鉴权 HTTPS MCP 端点并在当次 Run 中注明。
  - **登录态刷新**：执行前必须运行 `KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json` 刷新目标环境令牌缓存（`.runtime/cache/kuaibuddy-preprod/token.json`），避免跨环境复用旧环境缓存令牌；严禁将令牌写入日志、源码或报告。
  - **为何不纳入平台/专家级 MCP（`scope=1`）**：平台或专家级 MCP（如 `kicp`、`kst-mcp-online`）强绑定特定 `agent_id` 及租户 `Third-Token` 与外部业务数据，不适合零依赖跨环境基础回归。
  - **最小授权与防撞名**：临时连接器固定命名为 `kb-suite-case05-mcp`，保存时 `toolAuthorizationMode` 设为 `"SELECTED"` 且 `selectedTools` 仅勾选 `["add", "echo", "fail"]`（**不得**同时传 `excludedTools`，也不要传 `token` / `clientSecret` 否则触发 `8005`），并在提示词中显式指定 `#<CONNECTOR_ID>`，避免与账号下既有连接器冲突。
  - **强制自清理**：`Step 2 ~ Step 4` 必须在 `try ... finally` 中执行，无论中间成功或报错均执行 `Step 5` 按最新 `revision` 删除临时连接器。

| 阶段 / 轮次 | 场景类型 | 固定输入提示词 / API 操作（执行时保持固定） | 预期交互行为 | 预期观测指标（API + `events.json` + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **Step 0**<br>（API 负向） | SSRF 环回地址与 URL 鉴权材料拦截 | 调用 `POST /web/agent/api/v1/mcp-connector/test` 分别提交：<br>1）`config.url = "https://127.0.0.1/mcp"`；<br>2）`config.url = "<MCP_TEST_URL>?token=abc"`（均设 `transport: "STREAMABLE_HTTP"`, `auth: "NONE"`, `tokenMode: "BEARER"`, `preserveCredentials: false`） | 两次请求均在服务端前置校验阶段被拒绝，无草稿或连接器落库 | 两次响应业务码均为 **`8004`（`MCP_CONFIG_INVALID`）**（其中 URL 带 `token` 返回「认证材料不能放入服务器 URL」） |
| **Step 1**<br>（API 正向） | 远端工具发现、最小授权保存与列表核对 | 1）`POST /web/agent/api/v1/mcp-connector/test` 探测 `<MCP_TEST_URL>` 获取 `draftId` 与工具目录；<br>2）`POST /web/agent/api/v1/mcp-connector/save` 创建 `name: "kb-suite-case05-mcp"`，`toolAuthorizationMode: "SELECTED"`，`selectedTools: ["add", "echo", "fail"]`，记录 `CONNECTOR_ID`；<br>3）`GET /web/agent/api/v1/mcp-connector/list` 复核 | 发现远端工具并仅持久化所选 3 个工具，状态为启用且同步成功 | 1. `/test`、`/save`、`/list` 均返回 `code = 8`；<br>2. `enabled = true`、`toolSyncStatus = "SUCCESS"`；<br>3. `tools` 集合严格等于 `["add", "echo", "fail"]`，未勾选工具（如 `whoami`）不在授权列表中 |
| **Step 2**<br>（会话 A 第 1 轮，新开会话） | 对话内连接器发现、作用域隔离与正向工具调用 | `请使用我的个人 MCP 连接器 #<CONNECTOR_ID>（名称 kb-suite-case05-mcp）对应的工具完成两件事：1）调用 add 工具计算 1234 加 5678；2）调用 echo 工具原样回显文本 KB-SUITE-CASE05-8848。请直接调用对应 MCP 工具并汇报真实返回结果，不要自己口算或编造。` | 识别连接器 `#<CONNECTOR_ID>` 前缀并真实调用 `add` 与 `echo`，汇报结果 | 1. Langfuse `sysPrompt` 含 `工具前缀 personal_mcp_<uuid>__ 属于连接器 #<CONNECTOR_ID>`；<br>2. `GENERATION.input` 包含 `<prefix>__add` 且**不包含**未授权的 `<prefix>__whoami`；<br>3. Langfuse 实录 `<prefix>__add` 与 `<prefix>__echo` 调用成功；<br>4. 回复准确包含 `6912` 与 `KB-SUITE-CASE05-8848` |
| **Step 3**<br>（会话 A 第 2 轮，同会话） | MCP 工具失败兜底与多连接器缓存稳定性 | `请继续使用同一个个人 MCP 连接器 #<CONNECTOR_ID> 的 fail 工具执行一次调用，并如实汇报工具返回的真实错误结果（不要编造成功，也不要反复重试超过 2 次）。` | 调用 `fail` 工具并如实回报上游错误，不伪造成功、不死循环重试 | 1. Langfuse 实录 `<prefix>__fail` 调用 `1~2` 次且返回错误文本；<br>2. 回复如实说明失败；<br>3. 观察个人 MCP 挂载下第 2 轮 Prompt Cache 命中率保持 **≥ 90%** |
| **Step 4**<br>（停用 + 会话 B 第 1 轮，**新开会话**） | 连接器停用后运行时隔离与拒绝伪造 | 1）`GET /list` 取最新 `revision`，调 `POST /web/agent/api/v1/mcp-connector/set-enabled` 设 `enabled: false`；<br>2）新开会话发送：`请使用我的个人 MCP 连接器 #<CONNECTOR_ID>（名称 kb-suite-case05-mcp）的 add 工具计算 11 加 22，并汇报工具调用结果；如果该连接器当前不可用或已停用，请直接明确说明，不要自行口算冒充工具调用成功。` | 停用后运行时不再装配 `#<CONNECTOR_ID>` 工具；助手明确反馈连接器已停用/不可用且拒绝伪造调用结果 | 1. Langfuse `sysPrompt` 注入 `连接器 #<CONNECTOR_ID> 已停用，需要此连接器时应明确反馈不可用。`；<br>2. 本轮 **0 次** `<prefix>__*` 工具调用（输入基线 Token 因未装配该连接器工具 Schema 而回落）；<br>3. 回复明确说明连接器不可用/已停用（*注：仅校验未调工具与停用说明，不强校验拒绝理由中的附带示例算术措辞*） |
| **Step 5**<br>（API 自清理） | 物理删除临时连接器并核验存量无损 | `finally` 中 `GET /list` 获取 `#<CONNECTOR_ID>` 最新 `revision`，调 `POST /web/agent/api/v1/mcp-connector/delete` 删除，并再次调 `GET /list` 核验 | 临时连接器被彻底清除，账号下原有连接器未受任何影响 | 1. `/delete` 返回 `code = 8`；<br>2. 删后 `/list` 中已无 `kb-suite-case05-mcp`（`#<CONNECTOR_ID>`）；<br>3. 执行前已存在的连接器 ID、启停状态与 `revision` 均保持原样 |

- **跨环境执行命令模板**（将 `<ENV_FILE>`、`<LF_ENV>`、`<MCP_TEST_URL>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 1. 强制刷新目标环境登录态（token 缓存在 .runtime/cache/kuaibuddy-preprod/token.json，严禁打印令牌）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json > "<OUT_DIR>/login.json"

  # 2. 推荐通过 Python 自动化脚本串联 Step 0 ~ Step 5（将 Step 2~4 纳入 try...finally 确保 Step 5 自清理）
  # 说明：
  # - 个人 MCP API 统一走 <BASE_URL>/web/agent/api/v1/mcp-connector/{list,test,save,set-enabled,delete}
  # - Step 2 / Step 3 / Step 4 对话分别调用：
  #   Turn 1: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<TURN_1_PROMPT>" --out "<OUT_DIR>/turn-1" --json
  #   Turn 2: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<TURN_2_PROMPT>" --session "$SESSION_A" --out "<OUT_DIR>/turn-2" --json
  #   Turn 3: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<TURN_3_PROMPT>" --out "<OUT_DIR>/turn-3" --json
  # - Langfuse <LF_ENV> 核对多步轨迹时，需等待根 AGENT Span 落盘收口（带 endTime）后再统计全部 Step 的 GENERATION 与 TOOL，避免过早轮询漏掉尾随 Span
  ```

- **通过标准（双口径验收）**：
  1. **安全准入拦截**：环回 IP 与 URL 查询参数携带 `token` 两次 `/test` 均被拦截并返回 `code = 8004`。
  2. **发现与最小授权生效**：`/test` 与 `/save`（`SELECTED`）成功，`/list` 及 Langfuse `GENERATION.input` 仅包含已选工具（`add`/`echo`/`fail`），未勾选工具（如 `whoami`）不可见。
  3. **对话调用闭环**：Turn 1 在 Langfuse 成功记录 `<prefix>__add` 与 `<prefix>__echo` 调用，回复准确包含 `6912` 与 `KB-SUITE-CASE05-8848`。
  4. **异常兜底与缓存稳定**：Turn 2 实际调用 `<prefix>__fail`（不超过 2 次）并如实报错，不编造成功；同时跨轮 Prompt Cache 命中率稳定达标（**≥ 90%**）。
  5. **停用即时隔离**：Turn 3 的 Langfuse `sysPrompt` 注入停用提示、`<prefix>__*` 工具调用次数为 `0`，回复明确反馈连接器不可用。
  6. **无残留自清理**：Step 5 删除后 `/list` 不再包含 `kb-suite-case05-mcp`，原有连接器全部完好保留。

---

### CASE-06：定时任务全生命周期管理与触发隔离验证
- **覆盖标签**：`#scheduled-task`
- **测试目标**：验证定时任务 7 个内置管理工具（`create_schedule` / `list_schedules` / `update_schedule_info` / `pause_schedule` / `resume_schedule` / `update_schedule_frequency` / `delete_schedule`）的完整闭环，校验 XXL-JOB 真实到点触发执行与新指令生效，并审计定时会话的隔离边界（不挂载长期记忆与定时任务工具）。
- **前置条件与边界说明**：
  - **调度器周期规则**：`ScheduleTool` 仅支持 `DAILY` / `WEEKLY` / `MONTHLY` / `YEARLY`，无一次性模式。第 1 轮先创建远期 `DAILY 23:59`，避免中途修改与暂停阶段意外触发；第 3 轮再改频为近期 `T+2` 或 `T+3` 分钟（东八区 `now.second <= 38` 取 `T+2`，否则取 `T+3`）以验证真实 Cron 触发。
  - **定时会话隔离口径**：定时触发使用 `SessionSource.SCHEDULED`（`threadId` 前缀 `sched_`），后端在 `AgentFactory` 与 `ToolkitFactory` 中显式不挂载 `## 长期记忆索引`、`memory_*` 工具与 `*_schedule` 工具（防止定时任务自建递归循环）。
  - **Web 分页字段与兜底清理**：`POST /web/agent/api/v1/schedule/scheduled` 与 `/executions` 返回 `RespByPage` 列表字段名为 **`data.resultlist`**；脚本须在 `finally` 中检查 `data.resultlist` 并兜底调用 `POST /web/agent/api/v1/schedule/delete?taskId=<TASK_ID>`，防止遗留周期扣费任务。

| 阶段 / 轮次 | 场景类型 | 固定输入提示词 / 操作（执行时除动态 `<TASK_ID>` 与 `<HOUR>/<MINUTE>` 外保持固定） | 预期交互行为 | 预期观测指标（API + `events.json` + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **第 1 轮**<br>（新建会话） | 创建与列表查询<br>(`create_schedule` + `list_schedules`) | `请调用 create_schedule 创建一个每日定时任务：名称为「KB-SUITE-06-初版」，频率类型 DAILY，时间为每天 23:59，执行指令为“只回复初版文案，不要调用任何工具”。创建完成后立即调用 list_schedules 查询我的定时任务列表，并返回该任务的任务 ID 和当前状态。` | 创建 `DAILY 23:59` 定时任务并查询列表，提取 `<TASK_ID>` 与 `运行中` 状态 | 1. Langfuse 实录 `create_schedule` 与 `list_schedules` 成功；<br>2. `/web/agent/api/v1/schedule/scheduled` `data.resultlist` 查到 `<TASK_ID>` 且 `triggerStatus = "RUNNING"` |
| **第 2 轮**<br>（同会话） | 改信息→暂停→查状态→恢复<br>(`update_schedule_info` / `pause_schedule` / `list_schedules` / `resume_schedule`) | `请对刚才创建的定时任务 ID <TASK_ID> 依次执行以下 4 步并汇报每步结果：1）调用 update_schedule_info 将名称改为「KB-SUITE-06-更新版」，并将执行指令改为“只回复固定暗号 KB-SUITE-SCHED-OK-8848，不要调用任何工具”；2）调用 pause_schedule 暂停该任务；3）调用 list_schedules 确认其状态已变为已暂停；4）调用 resume_schedule 恢复该任务运行。` | 顺序执行 4 步变更，第 3 步列表显式展示「已暂停」，第 4 步成功恢复运行 | 1. Langfuse 按序实录 `update_schedule_info` → `pause_schedule` → `list_schedules`（输出含 `已暂停`）→ `resume_schedule` 均成功；<br>2. 回复逐项汇报 4 步状态变化 |
| **第 3 轮**<br>（同会话） | 修改触发频率<br>(`update_schedule_frequency`) | 按东八区 `target_dt = now + (2m if now.second <= 38 else 3m)` 计算 `<HOUR>`、`<MINUTE>`，发送：<br>`请调用 update_schedule_frequency 将定时任务 ID <TASK_ID> 的执行频率更新为 DAILY、每天 <HOUR> 点 <MINUTE> 分，并返回更新后的下次执行时间。` | 更新为近期触发时间并返回新的下次执行时间 | Langfuse 实录 `update_schedule_frequency` 返回 `✅ 频率已更新`，`/schedule/scheduled` 确认时间与状态 `RUNNING` |
| **Step 4**<br>（异步触发与隔离核验） | 真实 Cron 到点触发 + 新指令输出 + **定时会话隔离** | 轮询 `POST /web/agent/api/v1/schedule/executions`（入参 `{"pageNum":1,"pageSize":20}`）等待目标分钟到点触发（*注：若目标环境仅验证执行器、不等待 Cron，可用 `POST /web/agent/api/v1/schedule/trigger?taskId=<TASK_ID>` 触发并在 Run 中注明*） | XXL-JOB 准时触发生成 `sched_*` 会话并按第 2 轮更新后的指令回复 | 1. `data.resultlist` 中 `<TASK_ID>` 状态为 `"success"`，取得 `<SCHED_THREAD_ID>`；<br>2. `kb_e2e.js messages --session <SCHED_THREAD_ID>` 回读准确包含 `KB-SUITE-SCHED-OK-8848`；<br>3. Langfuse 按 `sessionId=<SCHED_THREAD_ID>` 核验：`sysPrompt` **不含** `## 长期记忆索引`，`tools` **不含** `memory_*` 与 `*_schedule` |
| **第 4 轮**<br>（同原会话 + `finally`） | 对话删除与存量任务保护<br>(`delete_schedule` + `list_schedules`) | `请调用 delete_schedule 删除定时任务 ID <TASK_ID>，再调用 list_schedules 确认该任务已从列表中移除。` | 删除测试任务并查询确认移除，原有定时任务保持原样 | 1. Langfuse 实录 `delete_schedule` 与 `list_schedules`（已无 `<TASK_ID>`）；<br>2. `/schedule/scheduled` 复核 `data.resultlist` 已无残留且原有任务状态不变 |

- **跨环境执行命令模板**（将 `<ENV_FILE>`、`<LF_ENV>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 1. 刷新登录态（严禁打印令牌）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json > "<OUT_DIR>/login.json"

  # 2. 第 1~3 轮与第 4 轮在同一交互会话 <THREAD_ID> 中串行调用（推荐用 Python 脚本包入 try...finally 兜底删除）：
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<TURN_1_PROMPT>" --out "<OUT_DIR>/turn-1" --json
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<TURN_2_PROMPT>" --session "$THREAD_ID" --out "<OUT_DIR>/turn-2" --json
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<TURN_3_PROMPT>" --session "$THREAD_ID" --out "<OUT_DIR>/turn-3" --json

  # 3. Step 4 轮询 POST /web/agent/api/v1/schedule/executions 读取 data.resultlist 取得 sched_* 会话，回读消息并用 Langfuse sessionId 核验隔离：
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js messages --session "$SCHED_THREAD_ID" --json > "<OUT_DIR>/sched_messages.json"

  # 4. 第 4 轮对话删除（并在脚本 finally 中兜底调用 POST /web/agent/api/v1/schedule/delete?taskId=$TASK_ID）：
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<TURN_4_PROMPT>" --session "$THREAD_ID" --out "<OUT_DIR>/turn-4" --json
  ```

- **通过标准（双口径验收）**：
  1. **全量工具覆盖**：第 1～4 轮在 Langfuse 中依次成功命中 `create_schedule`、`list_schedules`、`update_schedule_info`、`pause_schedule`、`resume_schedule`、`update_schedule_frequency`、`delete_schedule` 全部 7 个工具。
  2. **调度触发与指令更新生效**：XXL-JOB 到点执行成功（`status="success"`），`sched_*` 会话准确输出第 2 轮改写后的暗号 `KB-SUITE-SCHED-OK-8848`（非初版文案）。
  3. **定时会话隔离有效**：Langfuse 中 `<SCHED_THREAD_ID>` 的 `GENERATION.input` 不含 `## 长期记忆索引`，工具列表中不含任何 `memory_*` 与 `*_schedule` 工具。
  4. **无残留自清理**：第 4 轮删除后 `/schedule/scheduled` `data.resultlist` 不再包含 `<TASK_ID>`，且账号下既有定时任务状态保持原样。

---

### CASE-07：框架文件检索、任务规划、联网抓取与大输出卸载验证
- **覆盖标签**：`#fs-code-tools` `#web-fetch` `#todo-plan` `#tool-result-eviction`
- **测试目标**：验证框架自带文件编辑与检索工具链（`write_file` / `edit_file` / `list_files` / `glob_files` / `grep_files`）、结构化待办维护（`todo_write`）、网页抓取（`web_fetch` 及 `web_search` 默认禁用隔离）、超长命令输出自动卸载（`ToolResultEviction`）与命令行超时预算前置拦截（`requireShellBudget`）。
- **前置条件与边界说明**：
  - 全环境内置上述工具，**无外部账号/MCP 依赖**，仅需目标环境沙箱/服务具备访问 `https://example.com` 的出站网络权限。
  - **阈值依据**：未显式覆盖 Nacos 配置时生效 `AgentProperties` 默认值——`tool-result-eviction.max-result-chars = 60,000`、`preview-chars = 6,000`，`tool.execution-timeout = PT10M`（`600s`，校验 `timeout + 30s < PT10M`）；第 2 轮构造约 `90,000` 字符输出触发卸载，传 `timeout = 600` 触发前置拒绝。
  - **网页标题说明**：`https://example.com` 页面可能仅提供 `<title>` 而无 `<h1>`，提示词统一按「`title` 或 `h1`」提取，避免多余改写步骤。

| 轮次 | 场景类型 | 固定输入提示词（Exact Prompt，执行时不可自由改写） | 预期交互行为 | 预期观测指标（`events.json` + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **第 1 轮**<br>（新建会话） | 规划 + 联网抓取 + 文件编辑检索全套 | `请先调用 todo_write 创建包含 4 个步骤的待办清单并在推进时更新状态，依次完成以下操作（必须使用对应专用工具，不要用 execute 代替文件/检索操作）：1）调用 web_fetch 抓取 https://example.com，提取页面标题（title 或 h1）；2）用 write_file 在 case07_tmp/notes.md 写入两行内容：第一行为“标题: <抓取到的页面标题>”，第二行为“状态: DRAFT-1001”，另用 write_file 写入 case07_tmp/sub/info.txt 内容为“锚点: KB-CASE07-GREP-8848”；3）用 edit_file 将 case07_tmp/notes.md 中的“DRAFT-1001”精确替换为“DONE-2002”；4）依次调用 list_files（查看 case07_tmp）、glob_files（在 case07_tmp 下查找所有 .txt 文件）、grep_files（在 case07_tmp 下搜索字面量 KB-CASE07-GREP-8848）。最后将待办全部标为 completed，并汇报页面标题、替换后状态、glob 与 grep 命中路径。` | 按待办推进，全部使用专用工具完成网页抓取、文件写改及列表/Glob/Grep 检索 | 1. Langfuse 实录 `todo_write`、`web_fetch`、`write_file`、`edit_file`、`list_files`、`glob_files`、`grep_files` **7 类工具均成功**；<br>2. `GENERATION.input` 工具列表中**不含 `web_search`**，无误调 `web_search`；<br>3. 回复准确包含 `Example Domain`、`DONE-2002` 与 `case07_tmp/sub/info.txt` |
| **第 2 轮**<br>（同会话） | 大工具输出自动卸载 + 超时预算前置拦截 | `请执行以下两项沙箱边界验证并如实汇报结果（每项失败不要反复重试）：1）调用 execute 执行命令 python3 -c "print('EVICT-HEAD-8848 ' + 'A'*45000 + ' EVICT-MID-9999 ' + 'B'*45000 + ' EVICT-TAIL-7777')"（总输出约 90,000 字符），观察输出是否被截断/卸载，并汇报你实际看到的头尾标记或卸载文件引用；2）调用 execute 执行 echo budget_check，但刻意将参数 timeout 设为 600（不要调小重试），如实汇报平台返回的参数校验错误。` | 第 1 次命令成功且输出落盘至 `large_tool_results/`，回复准确识别头尾锚点与卸载路径；第 2 次命令未启动即报错且不擅自重试 | 1. Langfuse 实录 90k 输出落盘（不报 `4054`），后续 `GENERATION` 仅增预览 Token、可见头 `EVICT-HEAD-8848` 与尾 `EVICT-TAIL-7777`；<br>2. `execute(timeout=600)` 前置报错含 `命令未启动` / `PT10M30S` / `PT10M`，`budget_check` 未执行；<br>3. 第 2 轮首步 Prompt Cache 正常命中（**≥ 90%**） |
| **第 3 轮**<br>（同会话） | 沙箱测试残留清理 | `请删除工作区临时目录 case07_tmp 以及本会话第 2 轮在 large_tool_results/ 下生成的超长输出卸载文件（仅删除这几项本次测试产物，勿动其他文件），并调用 list_files 检查当前工作区确认 case07_tmp 已不存在。` | 清理 `case07_tmp` 与第 2 轮卸载文件并复核工作区干净 | `list_files` 确认 `case07_tmp` 已不存在且未误删其他目录/文件 |

- **跨环境执行命令模板**（将 `<ENV_FILE>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 第 1 轮（新建会话，提取 THREAD_ID）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "<第1轮固定提示词>" --out "<OUT_DIR>/turn-1" --json

  # 第 2~3 轮（复用 THREAD_ID 串行执行）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "<第2轮固定提示词>" --session "$THREAD_ID" --out "<OUT_DIR>/turn-2" --json

  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \
    "<第3轮固定提示词>" --session "$THREAD_ID" --out "<OUT_DIR>/turn-3" --json
  ```

- **通过标准（双口径验收）**：
  1. **专用工具链完整**：第 1 轮在 Langfuse 命中 `todo_write`、`web_fetch`、`write_file`、`edit_file`、`list_files`、`glob_files`、`grep_files` 7 类工具，且 `web_search` 未挂载。
  2. **超长输出卸载生效**：第 2 轮 90k `execute` 输出触发卸载至 `large_tool_results/`、保留首尾 `6,000` 字符预览且不触发 `4054` 上下文超限。
  3. **预算参数拦截生效**：`execute(timeout=600)` 在命令启动前即返回总预算校验错误且未重试执行。
  4. **无残留自清理**：第 3 轮删除 `case07_tmp` 及本会话生成的卸载文件，工作区恢复干净。

---

### CASE-08：运行态控制（断连重连／并发拦截／真中断）与积分计费对账验证
- **覆盖标签**：`#run-control` `#points-billing`
- **测试目标**：验证交互式运行态控制 4 项核心契约（SSE 断连不断执行与 `/run/observe` 全量重放续接、同会话并发 `4006` 拦截且不扰乱原 Run、`/run/cancel` 真实打断多步写任务不泄漏后台写入、取消后立即续问不锁死会话），并在同一组执行上完成积分账户余额、SSE `usage`、轮次消费汇总 `/points/consumptions`、逐笔流水 `/points/records` 与 Langfuse `LF_ENV` 调用轨迹的四方精确对账。
- **前置条件与边界说明**：
  - **零外部依赖与余额要求**：全环境内置 `execute`、`write_file` 与运行控制／积分中心接口，仅要求目标测试账号积分余额 `> 10` 且当前无运维窗口拦截（`GET /service/agent/api/v1/agent/maintenance` 返回 `enabled: false`）。
  - **网关前缀与响应字段**：运行控制统一走 `<BASE_URL>/service/agent/api/v1/agent/run*`（均为 `POST`，其中 `/observe` 与 `/cancel` 的 `threadId` 为 URL Query 参数），积分中心统一走 `<BASE_URL>/web/agent/api/v1/points/{account,consumptions,records}`（均为 `POST`，分页列表字段为 **`data.resultlist`**，业务成功码 `code = 8`）；令牌缓存 `.runtime/cache/kuaibuddy-preprod/token.json` 的 Bearer 字段名为 **`accessToken`**。
  - **基线锁定与非破坏边界**：执行前先运行 `kb_e2e.js login --force --json` 刷新登录态，**拍完 Step 0 基线后全程不再重复登录**（防内部虚拟账号重置余额干扰前后差值）。本用例**不测**打空余额 `6001`（防破坏公共测试账号）及 `/points/claim`（每日一次不幂等），同时执行期间避免同一账号并发跑其他对话干扰前后差值。
  - **沙箱防泄漏守卫**：正常通过路径不会在沙箱生成 `case08_cancel_should_not_exist.txt`；自动化脚本需在 `finally` 中兜底检查，若发现意外泄漏则清理该测试文件并明确判失败。
  - **已实测校准的关键平台口径**：
    1. **取消中断与 Langfuse `GENERATION` 计数**：`InterruptMiddleware.onReasoning` 检测到取消信号并触发 `agentInterruptor.interrupt` 后仍可能放行至框架 `untilInterrupted` 截断，因此 Langfuse 中 `RUN_2` 允许出现 `1～2` 次 `GENERATION`；若出现第 2 次 `GENERATION`，其 `output` 必须为 `0` 且不产生 `DEDUCT` 扣费、不触发 `write_file`。
    2. **追问建议对 `DEDUCT` 与 Langfuse 计数的影响**：`FollowupSuggestions` 使用独立 `ReActAgent("Followup")` 发起调用，其 OTel Trace（`invoke_agent Followup`）默认不携带 `sessionId` 与 `metadata.run_id`，但仍通过 `onToolUsageEnd` 将扣费归入主 Run。因此主 Run 下 `DEDUCT` 条数公式为：`count(run_id 下 output > 0 的有效 GENERATION) + (1 if SSE 含 CUSTOM(follow_up_suggestions) else 0)`。
    3. **积分流水正负字段区分与取消态 `usage` 事件**：`/points/records` 中，`DEDUCT` 扣减金额记录在负值 **`balanceChange`**（`pointsDeducted = 0`），而 `CONSUME` 轮次汇总记录在正值 **`pointsDeducted`**（`balanceChange = 0`，每轮严格 1 条幂等）；当前实现中 `RunUsageEvents` 仅在 `RUN_FINISHED` 前下发 `CUSTOM(usage)`，取消终态（`CUSTOM(cancelled)`）不下发 `usage` SSE 事件，仅通过终态对账落入 `CONSUME` 与 `/consumptions`。
    4. **Langfuse v4 字段组**：查询 `/api/public/v2/observations` 时建议传 `fields=core,basic,usage,model,time`（包含 `basic` 才会返回 span `name`），并通过 `langfuse_fetch.py`（`ProxyHandler({})`）直连内网观测地址。

| 阶段 / 轮次 | 场景类型 | 固定输入提示词 / API 操作（Exact Prompt，执行时保持固定） | 预期交互行为 | 预期四方观测指标（API + SSE + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **Step 0**<br>（API 基线） | 刷新登录态与积分／活跃基线快照 | 1）`kb_e2e.js login --force --json`（之后全程复用 `accessToken`）；<br>2）`GET /service/agent/api/v1/agent/maintenance`；<br>3）`POST /web/agent/api/v1/points/account`（`{}`）记录 `balance_before`、`todayConsumed_before`；<br>4）`POST /service/agent/api/v1/agent/run/active`（`{}`） | 登录成功、无运维窗口、余额充足 | `code = 8`，`enabled = false`，`balance_before > 10` |
| **Step 1**<br>（Turn 1，新开 `THREAD_ID`） | SSE 断连不断执行 + `/run/active` + 并发 `4006` + `/run/observe` 全量重放至完结 | 1）向 `POST /service/agent/api/v1/agent/run` 发起新会话：`请调用 execute 执行命令 python3 -c "import time; time.sleep(8); print('CASE08_OBS_STEP_DONE')"，命令完成后回复固定暗号 CASE08-OBSERVE-OK-8848，不要执行其他操作。`（记录 `RUN_1`）；<br>2）收到 `RUN_STARTED` 与首个 `TOOL_CALL_START`～`TOOL_CALL_END` 后**主动关闭 HTTP 响应流模拟 SSE 断连**；<br>3）调 `POST /service/agent/api/v1/agent/run/active`；<br>4）向**同一 `THREAD_ID`** 并发发起 `POST /service/agent/api/v1/agent/run`（文本：`并发冲突探测消息`，记录 `RUN_4006`）；<br>5）调 `POST /service/agent/api/v1/agent/run/observe?threadId=<THREAD_ID>` 持续读流至结束；<br>6）结束后等待 1s 再查 `/run/active` | 断连后沙箱与后台正常跑完；并发请求在 `gate()` 被拦截且不扰乱原 Run；`/observe` 从头重放并尾随交付暗号，结束后释放活跃态 | 1. 断连后 `/run/active` **包含** `THREAD_ID`；<br>2. 并发请求返回 `HTTP 200` SSE `RUN_ERROR` 且 **`code == "4006"`**；<br>3. `/run/observe` 从 `RUN_STARTED` 逐条一致重放断连前事件并尾随 `TOOL_CALL_RESULT`、回复含 **`CASE08-OBSERVE-OK-8848`**、`CUSTOM(usage)`（记 `sse_points_1 > 0`）与 **`RUN_FINISHED`**；<br>4. 结束后 `/run/active` **不再包含** `THREAD_ID` |
| **Step 2**<br>（Turn 2，同 `THREAD_ID`） | 两步写入型任务运行中 `/run/cancel` 真中断（防 `#93411`） | 1）同会话发送：`请严格按顺序分两步执行（禁止合并到同一条命令里）：第一步，先只调用 execute 执行命令 python3 -c "import time; time.sleep(10); print('CASE08_CANCEL_STEP1')"；第二步，等第一步工具返回结果后，再调用 write_file 在当前工作区写入文件 case08_cancel_should_not_exist.txt，内容为 SHOULD_NOT_EXIST，完成后再回复我。`（记录 `RUN_2`）；<br>2）首次收到 `TOOL_CALL_START` 时立即调用 `POST /service/agent/api/v1/agent/run/cancel?threadId=<THREAD_ID>`；<br>3）持续读取原 SSE 流至结束，等待 1.5s 再查 `/run/active` | `/run/cancel` 立即受理；第一步命令结束后在进入第二步推理前触发框架中断，不调用 `write_file`、以取消终态收尾并清除活跃登记 | 1. `/run/cancel` 返回 `code = 8`；<br>2. SSE 收到终态 **`CUSTOM(name="cancelled")`**（非 `RUN_FINISHED`/`RUN_ERROR`），工具列表仅 1 次 `运行命令`；<br>3. 结束后 `/run/active` **不再包含** `THREAD_ID`；<br>4. Langfuse（`fields=core,basic,usage,model,time`）`run_id=RUN_2` 实录 `GENERATION <= 2`（若为 2 则第 2 次 **`output == 0`**），**`write_file` 工具调用为 `0`** |
| **Step 3**<br>（Turn 3，同 `THREAD_ID`） | 取消后立即续问防锁死（`#92963`）+ 沙箱无泄漏实证 | 紧接 Step 2 结束后立即向同 `THREAD_ID` 发送：`请调用 execute 执行命令 python3 -c "import os; print('ABSENT' if not os.path.exists('case08_cancel_should_not_exist.txt') else 'LEAKED')" 检查当前工作区，如实汇报输出；若输出 ABSENT 请明确回复“未生成且会话正常”。`（记录 `RUN_3`） | 立即正常受理并执行命令（无会话占用锁死），检查确认哨兵文件不存在后正常回复 | 1. 无 `4006` / `4050` / `RUN_ERROR`；<br>2. 工具输出包含 **`ABSENT`**（不含 `LEAKED`），回复包含 **`未生成且会话正常`**；<br>3. SSE 含 `CUSTOM(usage)`（记 `sse_points_3 > 0`）并以 `RUN_FINISHED` 结束 |
| **Step 4**<br>（API + Langfuse 四方对账） | 积分余额、轮次状态、逐笔流水与被拒零计费核验 | 等待 3s 待终态对账落盘后查询：<br>1）`POST /web/agent/api/v1/points/account`（`{}`）；<br>2）`POST /web/agent/api/v1/points/consumptions`（`{"curPage":1,"pageSize":30}`）；<br>3）按 `queryId = RUN_1 / RUN_2 / RUN_3 / RUN_4006` 分别查 `POST /web/agent/api/v1/points/records` | 账户净扣等于三轮之和，三轮消费状态精准，每轮幂等仅 1 条 `CONSUME`，被拒并发请求零记录 | 1. **总账闭环**：`balance_before - balance_after == todayConsumed_after - todayConsumed_before == P1 + P2 + P3 > 0`；<br>2. **轮次状态**（`/consumptions` `data.resultlist`）：`RUN_1`/`RUN_3` 为 **`SUCCEEDED`**、`RUN_2` 为 **`CANCELLED`**，`RUN_4006` **不存在**；<br>3. **逐笔幂等与数量匹配**（`/records` `data.resultlist`）：`RUN_1`/`RUN_2`/`RUN_3` 各自**恰有 1 条 `CONSUME`**（`status="success"`）；每轮 `sum(-DEDUCT.balanceChange) == CONSUME.pointsDeducted == consumptions.pointsDeducted`（`RUN_1`/`RUN_3` 亦等于 SSE `CUSTOM(usage).value.points`）；每轮 `DEDUCT` 条数等于 `run_id` 下 `output > 0` 的 `GENERATION` 数（若 SSE 含 `follow_up_suggestions` 则额外 `+1`）；<br>4. **零误扣**：`RUN_4006` 在 `/records` 与 Langfuse 均为 **0 条** |

- **跨环境执行命令模板**（将 `<ENV_FILE>`、`<LF_ENV>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 1. 刷新目标环境登录态（仅执行一次，Step 0 ~ Step 4 复用 .runtime/cache/kuaibuddy-preprod/token.json 中的 accessToken，严禁打印令牌）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json > "<OUT_DIR>/login.json"

  # 2. 通过自动化 Python 脚本串联执行 Step 0 ~ Step 4（纳入 try...finally 兜底清理可能泄漏的 case08_cancel_should_not_exist.txt）：
  # - 运行控制接口：<BASE_URL>/service/agent/api/v1/agent/{maintenance,run,run/active,run/observe?threadId=...,run/cancel?threadId=...}
  # - 积分账本接口：<BASE_URL>/web/agent/api/v1/points/{account,consumptions,records}（读取 data.resultlist）
  # - Langfuse <LF_ENV> 对账（使用 ProxyHandler({}) 直连）：
  #   FILTER='[{"column":"metadata","key":"run_id","operator":"=","value":"<RUN_ID>","type":"stringObject"}]'
  #   GET <LANGFUSE_URL>/api/public/v2/observations?fields=core,basic,usage,model,time&filter=<URLENCODE(FILTER)>&limit=100
  #   # 注：若某轮存在 CUSTOM(follow_up_suggestions) 且需要查追问子调用，可按当轮结束前后 3s 时间窗检索 name="invoke_agent Followup"
  ```

- **通过标准（双口径／四方验收）**：
  1. **断连不中断与重放续接**：Step 1 断连后 `/run/active` 可见 `THREAD_ID`，`/run/observe` 从 `RUN_STARTED` 无损重放至 `CASE08-OBSERVE-OK-8848` 与 `RUN_FINISHED`，结束后 `/run/active` 清空。
  2. **并发冲突拦截**：活跃期同会话并发 `/run` 返回 SSE `RUN_ERROR`（`code="4006"`），且不影响 `RUN_1` 正常完成。
  3. **取消真实中断（防 `#93411`）**：Step 2 调用 `/run/cancel` 后收尾于 `CUSTOM(cancelled)`、`/run/active` 清空；Langfuse `RUN_2` `GENERATION <= 2`（第 2 次若存在则 `output == 0`）且 `write_file == 0`；Step 3 检查输出 `ABSENT`。
  4. **取消不锁会话（防 `#92963`）**：Step 3 紧接取消后立即同会话发起可正常回复 `未生成且会话正常`，无 `4006`/`4050` 卡死。
  5. **账本四方精确一致**：`/points/account` 净扣减与今日增量、`CUSTOM(usage)`（正常完结轮）、`/points/consumptions`（含 `SUCCEEDED` 与 `CANCELLED`）、`/points/records`（单 `CONSUME` 幂等 + `DEDUCT` 扣款与有效调用+追问次数匹配）金额完全闭合。
  6. **异常请求零误扣**：被 `4006` 拒绝的 `RUN_4006` 在 `/points/consumptions`、`/points/records` 与 Langfuse `LF_ENV` 均为 `0` 条记录。

---

### CASE-09：个人 Skill 全生命周期与隔离边界验证
- **覆盖标签**：`#user-skill-crud`
- **测试目标**：验证个人 Skill（`scope=3`）从 HTTP 包校验与全局重名拦截（`4102`/`4104`）、对话内创建／查询／ZIP 导出（`save_skill` / `query_skill`）、内置全局 Skill 读取隔离、跨会话动态加载生效、同名覆盖更新、Web 启停实时可见性隔离到安全自清理的完整闭环。
- **前置条件与已校准口径**：
  - **零外部依赖**：全环境内置 `write_file`、`save_skill`、`query_skill` 与 Web Skill 接口，仅要求技能广场存在至少 1 个全局 Skill（通过 `POST /web/agent/api/v1/skill/hub/list` 动态选取首个可用名称记为 `<GLOBAL_SKILL>`，禁止写死特定技能名称）。
  - **动态随机命名**：每次执行生成唯一名称 `<SKILL_NAME> = kb-suite-09-<6位十六进制>`（长度 `18 <= 30` 字上限，说明不超过 `120` 字），避免并发或历史残留撞名。
  - **隔离报错文本与静默加载口径（预生产实测校准）**：
    1. 对话内调用 `query_skill(name="<GLOBAL_SKILL>")` 时，工具返回原文为 **`Error: Tool execution failed: Skill 不存在`**（不会在文本中打印 `"4004"` 数字码，且 Langfuse Span `level` 仍为 `"DEFAULT"`）；断言须匹配包含 **`Skill 不存在`**。
    2. 新会话传入 `skillNames: ["<SKILL_NAME>"]` 激活个人 Skill 时，框架调用的 `load_skill_through_path` 属于静默工具（SSE 无 `TOOL_CALL_START` 事件），须在 Langfuse `LF_ENV` 中核验命中 **`load_skill_through_path(skillId="<SKILL_NAME>_import", path="SKILL.md")`**（`Source: import`）。
    3. Web 导出接口 `POST /web/agent/api/v1/skill/userExport` 返回 ZIP 的 Base64 字段名为 **`zipBase64`**。
  - **防“软删停用复活”陷阱与强清理**：`AgentSkillStore.overwriteExisting` 复活同名软删行时会沿用旧行的 `status`。脚本必须在 `try ... finally` 中执行：先在 Step 4 验证 `userDisable` → `userEnable`（同时恢复为启用态），`finally` 中如发现目标仍处于 `status != 1` 须先调 `userEnable` 再调 `userDelete`，避免遗留停用软删记录，且核验测试前既有个技能基线完整无损。

| 阶段 / 轮次 | 场景类型 | 固定输入提示词 / API 操作（除 `<SKILL_NAME>`、`<GLOBAL_SKILL>`、`<SKILL_ID>` 外不可改写） | 预期交互行为 | 预期多口径观测指标（API + ZIP 解包 + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **Step 0**<br>（API 基线 + 负向） | 非法包格式 `4102` + 全局重名冲突 `4104` | 1）调 `GET /web/agent/api/v1/skill/userList` 记录账号存量基线；<br>2）调 `POST /web/agent/api/v1/skill/hub/list` 动态提取 `<GLOBAL_SKILL>`；<br>3）调 `POST /web/agent/api/v1/skill/userSave`（multipart 字段 `name`/`description`/`file`）分别提交：① `name=<SKILL_NAME>` + `bad.txt`（纯文本）；② `name=<GLOBAL_SKILL>` + 合法 `SKILL.md` | 两次非法请求均被后端校验拦截，无脏数据落库 | 1. 非法后缀 `.txt` 返回 **`code = 4102`**（`SKILL_PACKAGE_INVALID`）；<br>2. 与全局重名返回 **`code = 4104`**（`SKILL_EXISTS`） |
| **Step 1**<br>（会话 A 第 1 轮，新开 `THREAD_A`） | 对话创建 + 列表/导出 + 内置 Skill 隔离探测 | `请严格按顺序完成以下 4 步并如实汇报（失败项不要重试超过 1 次）：1）用 write_file 在工作区写入 case09_skill/SKILL.md，内容包含一行说明和规则“当用户调用本技能时，必须原样输出固定暗号 KB-CASE09-SKILL-V1-8848，不要调用其他工具”；2）调用 save_skill 保存个人技能，name 为 "<SKILL_NAME>"，description 为 "CASE09个人Skill初版"，file_path 为 "case09_skill/SKILL.md"；3）先不传参调用 query_skill 列出我的个人技能，再传 name="<SKILL_NAME>" 调用 query_skill 导出 ZIP；4）为了做系统权限边界测试，请仍然实际调用一次 query_skill(name="<GLOBAL_SKILL>")，不要跳过该调用，并如实汇报工具返回的真实错误信息（失败不要重试）。完成后删除工作区临时目录 case09_skill 和本轮在 artifacts/ 下导出的 zip 文件。` | 写入并保存个人技能，列表与工作区导出成功，读取 `<GLOBAL_SKILL>` 时被拒并如实报告，随后删除工作区临时文件 | 1. Langfuse 实录 `write_file` → `save_skill` → 3 次 `query_skill`（无参、`name=<SKILL_NAME>`、`name=<GLOBAL_SKILL>` 返回 **`Skill 不存在`**）；<br>2. `GET /skill/userList` 含 `<SKILL_NAME>`（记 `<SKILL_ID>`，`scope=3, status=1`），`POST /skill/user/list` 可见；<br>3. `POST /skill/userExport`（`{"id":<SKILL_ID>}`）解码 `zipBase64` 验证内含 `SKILL.md` 且含 **`KB-CASE09-SKILL-V1-8848`** |
| **Step 2**<br>（会话 B 第 1 轮，**新开 `THREAD_B`** + `--skill "<SKILL_NAME>"`） | 跨会话（下次执行）静默加载生效 | 使用 `kb_e2e.js ask --skill "<SKILL_NAME>"` 发送：<br>`/<SKILL_NAME> 请严格按该技能要求输出当前固定暗号，不要调用其他无关工具。` | 新会话动态加载个人 Skill 并按 V1 规则输出暗号 | 1. Langfuse 实录 **`load_skill_through_path(skillId="<SKILL_NAME>_import", path="SKILL.md")`**（注：SSE 无工具事件属静默正常现象）；<br>2. 最终回复准确包含 **`KB-CASE09-SKILL-V1-8848`** |
| **Step 3**<br>（会话 B 第 2 轮，复用 `THREAD_B`） | 同名覆盖（Upsert V2）与防残留清理 | `请修改我的个人技能 "<SKILL_NAME>"：先用 write_file 写入 case09_skill_v2/SKILL.md，将固定暗号改为 "KB-CASE09-SKILL-V2-9966"；再调用 save_skill 以相同 name="<SKILL_NAME>"、description="CASE09个人Skill覆盖V2"、file_path="case09_skill_v2/SKILL.md" 覆盖保存；保存成功后删除工作区临时目录 case09_skill_v2 并回报技能 id。注意不要额外调用 query_skill 导出 ZIP（如已导出 artifacts/*.zip 请一并删除）。` | 原地覆盖正文与说明，技能 ID 与启用状态保持不变，临时文件全部清理 | 1. Langfuse 实录 `write_file` 与 `save_skill` 成功；<br>2. `GET /skill/userList` 保持同一 `<SKILL_ID>`、`status=1`、`description="CASE09个人Skill覆盖V2"`；<br>3. `POST /skill/userExport` 解码 `zipBase64` 确认 `SKILL.md` 已更新为 **`KB-CASE09-SKILL-V2-9966`**（不含 V1） |
| **Step 4**<br>（API 启停隔离 + `finally` 删除） | 停用隔离 → 启用恢复 → 物理删除与存量核验 | 1）`POST /web/agent/api/v1/skill/userDisable`（`{"id":<SKILL_ID>}`）→ 复查 `/skill/userList` 与 `/skill/user/list`；<br>2）`POST /web/agent/api/v1/skill/userEnable`（`{"id":<SKILL_ID>}`）→ 复查 `/skill/userList` 与 `/skill/user/list`；<br>3）`finally` 中调用 `POST /web/agent/api/v1/skill/userDelete`（`{"id":<SKILL_ID>}`）并复查基线 | 停用后运行时立即可见列表剔除，启用后恢复，删除后无残留且存量完好 | 1. `userDisable` 后 `/skill/userList` `status=0` 且 `/skill/user/list` **不含** `<SKILL_NAME>`；<br>2. `userEnable` 后恢复 `status=1` 且 `/skill/user/list` **恢复包含**；<br>3. `userDelete` 后两个列表均不含 `<SKILL_NAME>`，既有个人 Skill 与 Step 0 基线一致 |

- **跨环境执行命令模板**（将 `<ENV_FILE>`、`<LF_ENV>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 1. 刷新目标环境登录态（token 缓存在 .runtime/cache/kuaibuddy-preprod/token.json，严禁打印令牌）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json > "<OUT_DIR>/login.json"

  # 2. 推荐通过 Python 自动化脚本串联 Step 0 ~ Step 4（纳入 try...finally 确保先启用后删除）
  # - Skill Web 接口：<BASE_URL>/web/agent/api/v1/skill/{userList,hub/list,userSave,user/list,userExport,userDisable,userEnable,userDelete}
  # - 对话轮次（Step 1 / Step 2 / Step 3）：
  #   Turn 1: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<STEP_1_PROMPT>" --out "<OUT_DIR>/turn-1" --json
  #   Turn 2: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<STEP_2_PROMPT>" --skill "$SKILL_NAME" --out "<OUT_DIR>/turn-2" --json
  #   Turn 3: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<STEP_3_PROMPT>" --session "$THREAD_B" --out "<OUT_DIR>/turn-3" --json
  ```

- **通过标准（多口径验收）**：
  1. **负向准入拦截**：`/skill/userSave` 非法 `.txt` 返回 `4102`，与全局 Skill 重名返回 `4104`。
  2. **对话创建与隔离**：Step 1 在 Langfuse 命中 `write_file`、`save_skill`、`query_skill`（列表、导出、全局隔离返回 `Skill 不存在`）；Web `/skill/userExport` 解包含 V1 暗号。
  3. **跨会话静默加载生效**：Step 2 新会话在 Langfuse 命中 `load_skill_through_path(skillId="<SKILL_NAME>_import")` 且回复准确输出 `KB-CASE09-SKILL-V1-8848`。
  4. **同名覆盖保留身份**：Step 3 覆盖后保持同一 `<SKILL_ID>` 与 `status=1`，导出包内容已更新为 `KB-CASE09-SKILL-V2-9966`。
  5. **启停隔离与无损清理**：`userDisable` 运行时剔除、`userEnable` 恢复、`userDelete` 彻底清除且账号既有个人 Skill 完全无损。

---

### CASE-10：AI 图像生成自动入库与任务附件发现验证
- **覆盖标签**：`#image-gen`
- **测试目标**：验证 `text_to_image`（文生图）与 `image_to_image`（基于前图 URL 链式参考图生图）结合 `ImageGenPostProcessor` 自动积分结算与永久 COS 入库（无需再调用 `save_image_to_library`）、`list_attachments` 任务附件发现，以及 `/library/delete` 同时软删数据库记录与物理删除 COS 对象（删后 `HTTP 404`）的端到端闭环。
- **前置条件与已校准口径**：
  - **生图配置与积分门槛**：要求目标环境已配置可用 `text-to-image` 模型候选池及 COS 存储，且账号积分余额 **`> 150`**。预生产实测单张 `K1`/`R_1_1` 生图后处理固定触发 1 笔 **`-61.73`** 积分 `DEDUCT`（加上每轮推理与追问建议，2 轮生图总消耗约 **`125～130`** 积分）。
  - **规格与自动入库防重调约束**：两轮均固定最小规格 `count=1`、`resolution="K1"`、`aspect_ratio="R_1_1"`；`ImageGenTool` 返回永久 `accessUrl` 与 `attachmentId`，提示词显式要求**不调用 `save_image_to_library`**，并在 Langfuse 验证调用次数为 `0`。
  - **附件类别与文件库字段差异**：`list_attachments` 工具入参 `file_category` 枚举为大写 **`IMAGE`**；Web 接口 `POST /web/agent/api/v1/library/list-by-session` 返回的 `LibraryItemVO` 中 `fileCategory` 为小写 **`"image"`**、`source` 为 **`"agent"`**、`taskRole` 为 **`"ARTIFACT"`**。
  - **证据留存与删后 `404` 说明**：`LibraryServiceImpl.delete` 会同步物理删除 COS 对象；清理完成后历史会话文本里保留的原链接访问 `HTTP 404` 属正常清理结果。建议在 `Step 3` 删除前先将直连 GET `200` 的两张图片二进制顺手保存至 `<OUT_DIR>/case10_t2i.png` 与 `<OUT_DIR>/case10_i2i.png` 供人工按需查看成像。

| 阶段 / 轮次 | 场景类型 | 固定输入提示词 / API 操作 | 预期交互行为 | 预期多口径观测指标（HTTP + 文件库 + 积分 + Langfuse `LF_ENV`） |
| :--- | :--- | :--- | :--- | :--- |
| **Step 1**<br>（会话 A 第 1 轮，新开 `THREAD_A`） | 文生图 + 自动永久入库（免调 `save_image_to_library`） | `请调用 text_to_image 生成 1 张极简测试图：内容为纯深蓝色背景正中央一颗清晰白色五角星；参数固定为 title="CASE10文生图测试"、file_name="case10_t2i.png"、count=1、resolution="K1"、aspect_ratio="R_1_1"。注意图片已自动入库，不要调用 save_image_to_library，完成后请原样返回 attachmentId 和 accessUrl。` | 调用 `text_to_image` 生成 1 张图，直接返回真实 `attachmentId`（记 `ATT_1`）与永久 `accessUrl`（记 `URL_1`） | 1. Langfuse 实录 `text_to_image` 成功，**`save_image_to_library == 0`**；<br>2. 对 `URL_1` 直连 GET 返回 **`HTTP 200`**、`Content-Type: image/*`、体积 `> 0`（PNG 头 `89504e470d0a1a0a`，保存本地备份）；<br>3. `/library/list-by-session` 含 `ATT_1`；`/points/records` 含生图独立 `DEDUCT` 扣费 |
| **Step 2**<br>（会话 A 第 2 轮，复用 `THREAD_A`） | 链式图生图 + 任务附件发现（`list_attachments`） | `请依次完成两件事：1）调用 image_to_image，以你上一轮返回的 accessUrl 作为 image_urls（仅传这 1 张参考图），将背景改为温暖日落橙色并保留中央白色五角星，参数固定为 title="CASE10图生图测试"、file_name="case10_i2i.png"、count=1、resolution="K1"、aspect_ratio="R_1_1"（不要调用 save_image_to_library）；2）生成完成后立即调用 list_attachments（file_category 选 IMAGE）列出本会话全部图片附件，并原样汇报两张图的 attachmentId 与 accessUrl。` | 以 `URL_1` 为唯一参考图生成 `ATT_2` / `URL_2`，再调 `list_attachments` 枚举当前会话两张图片并完整回报 | 1. Langfuse 实录 `image_to_image`（入参 `image_urls` 准确含 `URL_1`）与 `list_attachments(file_category="IMAGE")` 均成功，**`save_image_to_library == 0`**；<br>2. `URL_2` 直连 GET 返回 **`HTTP 200`**、`image/*`、体积 `> 0`（与 `URL_1` 不同，保存本地备份）；<br>3. `/library/list-by-session` 包含 `ATT_1` 与 `ATT_2`（均 `fileCategory="image"`, `source="agent"`, `fileSize > 0`）；`/points/records` 含 `DEDUCT` |
| **Step 3**<br>（API 自清理，`finally`） | 文件库 + COS 物理删除闭环验证 | 1）对 `ATT_1`、`ATT_2` 调用 `POST /web/agent/api/v1/library/delete`（`{"attachmentId":"<ID>"}`）；<br>2）复查 `POST /web/agent/api/v1/library/list-by-session`；<br>3）再次对 `URL_1` 与 `URL_2` 发 HTTP GET | 文件库与底层 COS 对象均被清除 | 1. 两次 `/library/delete` 均返回 `code = 8`；<br>2. `/library/list-by-session` 返回空列表 `[]`；<br>3. 复测 `URL_1` 与 `URL_2` 均返回 **`HTTP 404`**（验证 COS 已物理清理） |

- **跨环境执行命令模板**（将 `<ENV_FILE>`、`<LF_ENV>` 与 `<OUT_DIR>` 替换为实际值）：
  ```bash
  # 1. 刷新目标环境登录态（token 缓存在 .runtime/cache/kuaibuddy-preprod/token.json，严禁打印令牌）
  KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json > "<OUT_DIR>/login.json"

  # 2. 通过 Python 自动化脚本串联 Step 1 ~ Step 3（纳入 try...finally 兜底删图与删后 404 校验）：
  # - Turn 1: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<STEP_1_PROMPT>" --out "<OUT_DIR>/turn-1" --json
  # - Turn 2: KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask "<STEP_2_PROMPT>" --session "$THREAD_A" --out "<OUT_DIR>/turn-2" --json
  # - 文件库与积分核验：<BASE_URL>/web/agent/api/v1/library/{list-by-session,delete}、/web/agent/api/v1/points/records
  ```

- **通过标准（多口径验收）**：
  1. **文生图与图生图链式生效**：两轮分别在 Langfuse 命中 `text_to_image` 与 `image_to_image`（`image_urls` 精准传递 `URL_1`），两张图片均可直连 `HTTP 200` 读取有效图片字节。
  2. **自动入库免重复保存**：两轮 Langfuse 轨迹中 `save_image_to_library` 均为 **`0`** 次，且 `/library/list-by-session` 与 `list_attachments` 均返回全部 `2` 条 `agent` 图片产物。
  3. **积分独立扣费入账**：`/points/records` 在 `RUN_1` 与 `RUN_2` 下均准确记录生图 `DEDUCT` 扣费明细与汇总 `CONSUME`。
  4. **文件库与 COS 双清闭环**：Step 3 `/library/delete` 后 `/library/list-by-session` 为空 `[]`，且原 `URL_1`/`URL_2` 复测返回 `HTTP 404`。

---

## 5. 执行与产物规范
- 每次按本测试集执行时，在 `.runtime/requests/<中文请求概要>/<RUN_ID>/`（或对应长期任务目录）记录实际环境、`threadId`、`runId` 与实测结果，不直接修改本测试集文件写入单次结果。
- 每次执行结束后（无论仅执行 `1` 个、部分组合还是全量 `10` 个 Case），可将脱敏后的运行结果整理为 `report-data.json`（格式见 [kb-suite-001-report-sample.json](../data/kb-suite-001-report-sample.json)），调用 `python3 tests/scripts/render_suite_report.py --data <report-data.json> --out <RUN_DIR>/artifacts/report.html` 注入固定面板模板 [kb-suite-001-report.html](../templates/kb-suite-001-report.html)（支持多次 `--data` 合并展示；未执行 Case 自动显示为「未执行」，不拉低本次通过率）。
- Agent 执行本测试集与生成外发 HTML 报告可直接调用 [kb-suite-runner](../../.agents/skills/kb-suite-runner/SKILL.md) 技能，配合 `.agents/skills/kb-suite-runner/scripts/suite_helper.py` 完成 Run 目录初始化、三道外发脱敏门禁校验与 HTML 报告渲染。
