# KB-SUITE-001 用例执行速查与避坑指南

本参考提炼 [KB-SUITE-001.md](../../../../tests/cases/KB-SUITE-001.md)（`CASE-01`～`CASE-10`）与 [docs/knowledge.md](../../../../docs/knowledge.md)（`K-001`～`K-009`）的关键执行参数、双/四方验收口径与常见陷阱。各用例精确输入提示词与接口路径请以原测试集文档为准，执行时不得自由改写固定提示词。

## 1. 全集 10 用例总览表

| 用例 | 能力标签（共 23 项） | 主要驱动方式 | 前置与余额门槛 | 核心观测源 | 强制自清理目标 |
|---|---|---|---|---|---|
| `CASE-01` | `#prompt-cache` `#skill-load` `#tool-execute` `#multi-turn-context` `#no-redundant-tool` `#sse-stream-followup` | `kb_e2e.js ask` 串行 5 轮 | 目标 Skill 可用（默认 `/快商通 IM 助手`），同会话轮间 `< 1m` | `events.json` + Langfuse `GENERATION` | 无（只读查询） |
| `CASE-02` | `#context-compaction` `#large-file-read` | `kb_e2e.js ask` 锚点 + 填充 + 双校验 | 先查 Nacos `trigger-tokens` / `trigger-messages` | `events.json` (`context_build`) + Langfuse | 无（沙箱内临时 `/tmp`） |
| `CASE-03` | `#long-memory` `#error-fallback` `#write-confirm` | 跨会话 A/B `kb_e2e.js ask` | 已有长期记忆 `< 100`，`user_memory` 表可用 | `events.json` + Langfuse `sysPrompt` | 会话 B 第 2 轮 `memory_delete` 清测试记忆 |
| `CASE-04` | `#agent-switch` `#multimodal-file` | 同会话 2 轮 `kb_e2e.js ask` | 内置 `agent_spawn`/`save_*`/`analyze_image` | `events.json` + Langfuse `TOOL` + `accessUrl` | 视文件库/工作区需要清理产物 |
| `CASE-05` | `#mcp-connector` | Python API + `kb_e2e.js ask` | 无鉴权测试 MCP（默认 `https://api.sondahub.com/mcp`） | 个人 MCP Web API + Langfuse `sysPrompt`/`TOOL` | `finally` 按最新 `revision` 删临时连接器 |
| `CASE-06` | `#scheduled-task` | `kb_e2e.js ask` + Python 轮询 | 允许 Cron 触发或显式 `/schedule/trigger` | `/schedule/{scheduled,executions}` + Langfuse | 第 4 轮删除 + `finally` `/schedule/delete` |
| `CASE-07` | `#fs-code-tools` `#web-fetch` `#todo-plan` `#tool-result-eviction` | 同会话 3 轮 `kb_e2e.js ask` | 沙箱可出站访问 `https://example.com` | Langfuse 工具清单 + 预览 Token + 文件列表 | 第 3 轮删 `case07_tmp` 与卸载文件 |
| `CASE-08` | `#run-control` `#points-billing` | Python 原始 HTTP/SSE 流 | 无运维窗口，`balance > 10`，**拍基线后不重登** | `/run*` SSE + `/points/*` + Langfuse | `finally` 检查防 `case08_cancel_should_not_exist.txt` 泄漏 |
| `CASE-09` | `#user-skill-crud` | Python Web API + `kb_e2e.js ask` | 技能广场至少 1 个全局 Skill，随机短名 | `/skill/*` + `zipBase64` 解包 + Langfuse | `finally` 若 `status != 1` **先启用再删除** |
| `CASE-10` | `#image-gen` | `kb_e2e.js ask` + HTTP/API 校验 | 生图模型池可用 + COS，`balance > 150` | HTTP GET 图 + `/library/*` + `/points/records` + Langfuse | Step 3 删前先存本地图，删后验证 `404` |

## 2. 通用执行与观测规则

- **登录态缓存与已知无害报错**：`kb_e2e.js login --force --json` 将凭证缓存至 `.runtime/cache/kuaibuddy-preprod/token.json`（Bearer 字段为 `accessToken`），注意不要跨环境复用旧缓存。已知 `kb_e2e.js agents` 在预生产/测试环境可能返回 `9001`（`K-004`），不影响正常对话与 `skills`。
- **Langfuse v2 Observations 核对方式**（`K-003`、`K-005`）：
  - 直接复用 [kb-bug-analyse](../../kb-bug-analyse/SKILL.md) 下的 `local_config.py` 与 `langfuse_fetch.py`（内网直连使用 `ProxyHandler({})`）。
  - 请求 `/api/public/v2/observations` 时建议传 `fields=core,basic,usage,model,time`（包含 `basic` 才能读取 span `name`），按 `metadata.run_id` 或 `sessionId` 过滤。
  - 多步推理须等待根 `AGENT` Span 带 `endTime` 收口后再汇总，防止漏掉尾随 Span。

## 3. 逐用例关键验收点与高频避坑

### CASE-01：Skill 加载与 Prompt 缓存命中率
- **缓存公式**：`input_cached_tokens / (input + input_cached_tokens) × 100%`。
- **关键节点**：第 1 轮冷启动后轮内上升至 `75%～99%`；第 3 轮（工具结果入历史后纯文本追问）与第 5 轮**跨轮首步缓存命中率须 `≥ 95%`**，且不重复调用工具，`input_cached_tokens` 在第 5 轮达到单调递增峰值。
- **静默校验**：`load_skill_through_path` 属于 `SILENT_TOOL_KEYS`（`K-003`），SSE 中不会出现工具事件，必须在 Langfuse 中确认命中。

### CASE-02：上下文压缩与关键信息保真
- **先查配置**：通过 DBX 读取 Nacos `service-agent.yaml` 核对 `compaction.trigger-messages`（当前 `0`）、`compaction.trigger-tokens`（预生产 `400000`；未配默认 `240000`）与 `tool.read-file-max-chars`（`64000`）。
- **严谨填充禁止乱码**：第 1 轮记录 `events.json` 中 `context_build.estimatedInputTokens` 作为固定基线 `EST_BASE`；后续严格使用测试集规定的「中文 + JSON 仿真业务日志（50k/批）」填充，禁止用纯随机 ASCII 乱码（会因 BPE 密度虚高导致 `total_in` 提前冲顶或误报 `4054`）。
- **验收要点**：当 `est - EST_BASE >= trigger-tokens` 时精准触发 `transforms: ["history_compaction"]`；校验轮 A `total_in` 显著回落且完整复述 `CUST-20261125`、`ORD-998877`、`3480.00元`；紧接轮 B 缓存命中恢复 `≥ 80%`。

### CASE-03：跨会话长期记忆与异常越权兜底
- **绕过确认模式的测法**：平台当前处于 `PermissionMode.BYPASS`，`#write-confirm` 重点通过 `delete_schedule(999999999)` 验证后端返回 `TASK_NOT_FOUND_ORBIDDEN`（`❌ 任务不存在或无权限操作`），并用 `read_file` 不存在文件验证工具错误不死循环（重试 `≤ 2` 次）且不编造成功。
- **跨会话验证**：会话 B 第 1 轮**不传 `--session`**，核对 Langfuse `sysPrompt` 末尾注入 `## 长期记忆索引` 与 `KB-SUITE-MEM-TAG`，回复自动携带 `售后小助手-8848`；第 2 轮先 `memory_read` 再精准 `memory_delete`，勿删原有记忆。

### CASE-04：子 Agent 派发、识图与产物交付
- **工作区路径限制**：`save_to_library` / `save_image_to_library` 仅接受工作区相对路径（如 `artifacts/case04_vision.png`），不可写入 `/tmp`。
- **双轮验证**：第 1 轮核实 Langfuse `agent_spawn`（`general-purpose`）以及两个入库工具返回真实 `http(s)` `accessUrl`；第 2 轮核实调用 `analyze_image`（`image_refs` 为第 1 轮 URL）并准确识别数字 `8848`。

### CASE-05：个人 MCP 连接器全生命周期
- **Step 0 负向**：环回 `https://127.0.0.1/mcp` 与 URL 带 `?token=abc` 提交 `/mcp-connector/test` 均返回 `code = 8004`。
- **Step 1 最小授权陷阱**：保存时 `toolAuthorizationMode: "SELECTED"`，只传 `selectedTools: ["add", "echo", "fail"]`；**切勿**同时传 `excludedTools` 或无鉴权模式传 `token`/`clientSecret`（否则触发 `8005`）。
- **Step 2–4 隔离与清理**：须包在 `try ... finally` 中；Step 2 验证 `GENERATION.input` 中有 `add`/`echo`/`fail` 且无未勾选 `whoami`；Step 3 实录 `fail` 报错且缓存 `≥ 90%`；Step 4 `set-enabled=false` 后新会话 `0` 次 `<prefix>__*` 调用；Step 5 获取最新 `revision` 后 `/mcp-connector/delete` 删除并核验存量无损。

### CASE-06：定时任务全生命周期与触发隔离
- **远期建任务再改频**：第 1 轮先建 `DAILY 23:59` 防止中途误触发；第 3 轮按东八区当前时间取 `T+2m`（`now.second <= 38`）或 `T+3m` 执行 `update_schedule_frequency`。
- **接口字段与隔离断言**：`/web/agent/api/v1/schedule/{scheduled,executions}` 列表字段均为 **`data.resultlist`**；触发后取得 `sched_*` 会话 ID，核对消息含 `KB-SUITE-SCHED-OK-8848`，并在 Langfuse 验证该定时会话 `sysPrompt` **不含** `## 长期记忆索引`，工具列表**不含** `memory_*` 与 `*_schedule`；`finally` 兜底调用 `/schedule/delete?taskId=<TASK_ID>`。

### CASE-07：框架文件检索、规划、联网与大输出卸载
- **第 1 轮专用工具链**：Langfuse 须全部命中 `todo_write`、`web_fetch`、`write_file`、`edit_file`、`list_files`、`glob_files`、`grep_files` 7 类工具，且确认 `web_search` 未出现在 `tools` 中。
- **第 2 轮双边界**：`execute` 输出约 `90,000` 字符（带 `EVICT-HEAD-8848` / `EVICT-TAIL-7777`）触发卸载至 `large_tool_results/` 且不报 `4054`；紧接 `execute(..., timeout=600)` 在命令启动前触发预算前置拦截（含 `PT10M` / `命令未启动`）；首步缓存保持 `≥ 90%`。
- **第 3 轮清理**：删干净 `case07_tmp` 与本会话卸载文件并确认 `list_files` 不再可见。

### CASE-08：运行态控制与积分四方对账
- **严禁重登刷新**：仅在 Step 0 调一次 `login --force`，拍完 `/points/account` 基线后**绝不再重登**，且执行期间同账号避免并发其他会话。
- **运行态四契约**：
  1. Step 1 收到首个工具事件后主动断开 SSE，验证 `/run/active` 仍在队列；并发发同 `threadId` 请求被拦截（SSE `RUN_ERROR` `code="4006"`）；`/run/observe` 从 `RUN_STARTED` 完整重放并交付 `CASE08-OBSERVE-OK-8848` 与 `RUN_FINISHED`。
  2. Step 2 两步写任务触发首工具后立即 `/run/cancel`，收尾于 `CUSTOM(cancelled)`（非 `RUN_FINISHED`）；Langfuse 允许 `GENERATION <= 2`（第 2 次若存在必为 `output == 0`），`write_file == 0`。
  3. Step 3 立即同会话续问，无 `4006`/`4050` 锁死，工具检查输出 `ABSENT`。
- **积分四方对账公式**（`POST /web/agent/api/v1/points/{account,consumptions,records}`，列表 `data.resultlist`）：
  - `balance_before - balance_after == todayConsumed_after - todayConsumed_before == P1 + P2 + P3 > 0`；
  - `RUN_1`/`RUN_3` 状态 `SUCCEEDED`、`RUN_2` 状态 `CANCELLED`（取消态不下发 `CUSTOM(usage)` 属正常设计）、`RUN_4006` 在 `/consumptions`、`/records` 与 Langfuse 均为 `0` 条；
  - `/points/records` 中 `DEDUCT` 扣款看负值 `balanceChange`，`CONSUME` 看正值 `pointsDeducted`（每轮严格 `1` 条幂等）；`DEDUCT` 条数 `= count(run_id 下 output > 0 的有效 GENERATION) + (1 if SSE 含 CUSTOM(follow_up_suggestions) else 0)`。

### CASE-09：个人 Skill 全生命周期与隔离边界（`K-008`）
- **命名与动态参照**：先 `POST /skill/hub/list` 动态取首个 `<GLOBAL_SKILL>` 名称，测试技能用随机短名 `kb-suite-09-<6hex>`。
- **关键校准断言**：
  - `/skill/userSave` 非法 `bad.txt` 返 `4102`，与全局重名返 `4104`。
  - 对话内 `query_skill(name="<GLOBAL_SKILL>")` 返回原文 **`Error: Tool execution failed: Skill 不存在`**（不含 `"4004"`、Langfuse `level="DEFAULT"`）。
  - Step 2 新会话通过 `--skill <name>` 触发，必须查 Langfuse 验证静默工具 `load_skill_through_path(skillId="<name>_import", path="SKILL.md")`。
  - Web `/skill/userExport` 返回字段名 `zipBase64`，解码验证 V1/V2 `SKILL.md` 内容。
- **防软删停用复活清理**：Step 4 验证 `userDisable` → `userEnable` → `finally` 兜底删；若清理前 `status != 1`，**必须先调用 `userEnable` 再调用 `userDelete`**（否则后续同名重建会继承停用状态），最后对照 Step 0 存量无损。

### CASE-10：AI 图像生成、自动入库与 COS 物理删除（`K-009`）
- **配额门槛与自动入库**：账户积分须 `> 150`（单张 `K1`/`R_1_1` 生图后处理固定扣 `-61.73` 积分，两轮总耗约 `125～130` 积分）。两轮均须验证 Langfuse 中 **`save_image_to_library == 0`**。
- **大小写差异注意**：`list_attachments` 入参 `file_category="IMAGE"`（大写），而 `/web/agent/api/v1/library/list-by-session` 返回 `fileCategory="image"`（小写）、`source="agent"`、`taskRole="ARTIFACT"`。
- **物理清理与 404 核验**：Step 3 调用 `/library/delete` 前先将两张图 GET `200` 字节保存至 `<RUN_DIR>/artifacts/` 备用；删除后确认列表为 `[]` 且再次 GET 原 `accessUrl` 均返回 **`HTTP 404`**（说明底层 COS 对象已物理删除，属于正常闭环）。
