# KB-SUITE-001 通用执行纪律与观测踩坑指南

> **单真源读取原则**：本指南仅记录跨用例通用的平台机制、鉴权/观测方式与已证实的工程踩坑，不重复抄录用例清单或具体提示词。每次执行任意 `CASE-xx` 前，直接读取 [KB-SUITE-001.md](../../../../tests/cases/KB-SUITE-001.md) 的对应小节获取最新 Exact Prompt、参数规格与通过标准。

## 1. 对话驱动与环境鉴权纪律

- **刷新令牌与单次锁定**：每轮任务启动时执行 `KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json` 刷新 `.runtime/cache/kuaibuddy-preprod/token.json`（Bearer 字段为 **`accessToken`**），禁止跨环境复用旧缓存或在任何文本中打印令牌。
- **积分基线保护**：涉及账户积分前后差值对账的用例（如运行控制与积分对账验证），拍完初始 `/points/account` 基线后**全程不要再次登录**，并避免同账号同时并发执行其他对话。
- **已知无害辅助接口失败（`K-004`）**：`kb_e2e.js agents` 在测试/预生产环境返回 `9001`（`SYSTEM_ERROR`）不代表对话引擎或个人技能不可用，可改用 `kb_e2e.js skills` 校验技能就绪状态。

## 2. 多口径观测与 Langfuse 采集约定（`K-003`、`K-005`）

- **直连拉取与字段要求**：复用 [kb-bug-analyse](../../kb-bug-analyse/SKILL.md) 下的 `local_config.py` 与 `langfuse_fetch.py`（使用 `ProxyHandler({})` 直连内网观测地址）。请求 `/api/public/v2/observations` 时须传 `fields=core,basic,usage,model,time`（包含 `basic` 才返回 span `name`），按 `metadata.run_id` 或 `sessionId` 精准过滤（预生产与生产共用 `prd` Langfuse，严禁仅靠时间范围混算）。
- **静默工具核验**：`load_skill_through_path` 等内置静默工具（`ToolName.SILENT_TOOL_KEYS`）**不会**出现在 SSE `TOOL_CALL_START` 或消息库中；验证 Skill（包含个人 Skill `<name>_import`）是否真正加载，必须在 Langfuse 中检查 `load_skill_through_path` span。
- **等待根 Span 收口**：多步推理存在尾部 span 异步上报，须等待根 `AGENT` span 出现 `endTime` 后再统计全部 `GENERATION` 与 `TOOL` 计数。
- **Cache 命中率统一公式**：`input_cached_tokens / (input + input_cached_tokens) × 100%`。

## 3. 平台工具契约、安全边界与已知工程陷阱

### 3.1 通用 Web 接口与协议约定
- 网关业务成功码统一为 **`code = 8`**（常见错误分段见 [biz-codes.md](../../../../docs/biz-codes.md)）。
- 积分中心（`/web/agent/api/v1/points/{account,consumptions,records}`）与定时任务分页接口（`/web/agent/api/v1/schedule/{scheduled,executions}`）的列表字段名为 **`data.resultlist`**。

### 3.2 关键踩坑备忘（对照 `KB-SUITE-001.md` 具体小节核对）
- **上下文压缩静态填充口径**：`service-agent` 按 `mixed-text-2.5chars-media-2048-v1` 在 `context_build` 估算历史消息 `estimatedInputTokens`（不含首轮基准开销 `EST_BASE`），未显式配置 `compaction.trigger-tokens` 时走代码默认 `240000`。填充用例不可使用纯随机 ASCII 乱码（BPE 密度虚高会导致 `total_in` 虚高触发 `4054`），须使用结构化中文+JSON 仿真日志。
- **工作区文件入库 vs 图片链接入库**：`save_to_library` 接收工作区相对路径（禁止 `/tmp` 等工作区外路径）；`save_image_to_library` **仅接受 `http/https` 图片 URL**，直接传工作区相对路径会报协议不合法；`analyze_image` 仅接受入库后的有效 `http(s)` URL。
- **个人 MCP 最小授权参数边界**：当 `toolAuthorizationMode="SELECTED"` 时只传 `selectedTools`，不要同时传 `excludedTools`；无鉴权（`auth="NONE"`）时不要传 `token`/`clientSecret`（否则触发 `8005`）。
- **运行态取消与积分流水区分（`K-001`）**：SSE 断连不中断后台 Run，须通过 `/run/observe` 重放或 `/run/cancel` 中止。`/run/cancel` 触发框架中断后允许 Langfuse 出现第 2 次 `GENERATION`（但 `output` 必为 `0` 且无后续工具写盘与扣费）；取消终态收尾于 `CUSTOM(cancelled)` 且不下发 `CUSTOM(usage)`。`/points/records` 中 `DEDUCT` 扣减看负值 `balanceChange`（含主调用与 `follow_up_suggestions` 独立扣费），`CONSUME` 看正值 `pointsDeducted`（每轮严格 1 条幂等）。
- **个人 Skill 隔离报错与防软删停用复活（`K-008`）**：对话内 `query_skill` 读取全局内置技能返回原文 **`Error: Tool execution failed: Skill 不存在`**（不含 `"4004"`、Langfuse `level="DEFAULT"`）。Web 导出 `/skill/userExport` 的 Base64 字段名为 `zipBase64`。由于同名覆盖会沿用软删行的旧 `status`，清理测试 Skill 前若当前 `status != 1`，**必须先调用 `userEnable` 再调用 `userDelete`**。
- **AI 生图自动入库与 COS 物理删除（`K-009`）**：`text_to_image`/`image_to_image` 成功后由后处理器自动结算扣费并永久入库 COS，**不应**再调用 `save_image_to_library`；`list_attachments` 参数 `file_category="IMAGE"`（大写），而 `/library/list-by-session` 返回 `fileCategory="image"`（小写）。调用 `/library/delete` 会同步物理删除底层 COS 对象，删除后原 `accessUrl` 返回 **`HTTP 404`** 属正常清理闭环（如需目视检查图片，务必在删除前先 GET `200` 保存至当前 Run `artifacts/`）。

## 4. 强自清理与基线无损原则

- 所有写入型用例（记忆、连接器、定时任务、沙箱临时目录、测试个人 Skill、生图附件）**必须包入 `try ... finally`** 执行清理；即便中间某轮失败或超时中断，也要确保在 `finally` 中移除测试残留并复核执行前既有个体资产完好。
- 只读查询类或仅使用沙箱 `/tmp` 的用例无需额外接口清理，如实记录清理状态为 `not_needed`。
