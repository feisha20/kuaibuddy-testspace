# KuaiBuddy 已确认测试知识

本文件收录有正式资料、源码核查或可追溯实测依据的测试经验。新增条目前先核对依据及适用条件；未确认观察、排查猜测和原始日志保留在 `.runtime/`。

## K-001：SSE 断连不中断后端 Agent 执行，需通过 observe/active 恢复或 cancel 取消
- 类型：排查经验
- 验证状态：已确认（源码核查）
- 适用模块与版本：`service-agent`（`beta` 分支 `3b72b2b`）、`ui-kuai-buddy`（`beta` 分支 `e9427a1`）
- 适用条件：所有通过 `/api/v1/agent/run` 发起的 Agent 执行会话
- 结论或建议：后端 `RunLifecycle` 独立订阅执行，`RunObservation` 负责 SSE 旁路转发与事件缓存。客户端断开 SSE 连接或刷新页面不会停止 Run，也不会改变 Run 终态（`RUNNING` → `SUCCEEDED`/`FAILED`/`CANCELLED`）。恢复观察应调用 `/api/v1/agent/run/observe?threadId=...` 或 `/api/v1/agent/run/active`，中止执行需显式调用 `/api/v1/agent/run/cancel`。测试并发或重连场景时不能将“断开请求”等同于“取消执行”。
- 依据：`service-agent` `AgentServiceImpl.java`、`RunLifecycle.java`、`RunObservation.java`、`AgentController.java`；`ui-kuai-buddy/CONTEXT.md`
- 关联任务／用例：[TASK-001](../tasks/TASK-001-基础对话回归.md)、[KB-DIALOG-001](../tests/cases/KB-DIALOG-001.md)
- 确认人：Agent 代码核查（用户授权知识沉淀）
- 最近核对日期：2026-11-18
- 失效条件或复核提示：若后续调整 `RunObservation` 断连取消策略需重新核对

## K-002：主模型采用会话粘性与异常冷却单向迁移机制
- 类型：测试策略
- 验证状态：已确认（源码核查）
- 适用模块与版本：`service-agent` `ModelSelector.java`（`beta` 分支 `3b72b2b`）
- 适用条件：多轮对话及并发压测场景
- 结论或建议：`ModelSelector` 按 `CompanyUserKey + threadId` 在 Redis 缓存主模型绑定（`PIN_TTL = 3 小时`），并校验候选模型并发容量与冷却状态；若当前模型异常触发 `markCooldown`，会话会单向迁移至下一个未冷却候选，且 `AgentFactory` 另行装配 `FALLBACK` 备模型。排查同一会话回复风格或能力突变时，应按单个 `runId` 核查 Langfuse 中的实际模型，不能假设整段会话始终使用同一模型。
- 依据：`service-agent` `ModelSelector.java`、`AgentFactory.java`
- 关联任务／用例：[TASK-001](../tasks/TASK-001-基础对话回归.md)
- 确认人：Agent 代码核查（用户授权知识沉淀）
- 最近核对日期：2026-11-18
- 失效条件或复核提示：模型路由策略或 `PIN_TTL` 配置变更时需复核

## K-003：静默工具调用不落库且不透出 SSE，排查需查 Langfuse/ELK
- 类型：排查经验
- 验证状态：已确认（源码核查）
- 适用模块与版本：`base` `ToolName.java`（`beta` 分支 `6deda08`）、`service-agent`
- 适用条件：涉及 Skill 加载或千锤 MCP 协同的对话排查
- 结论或建议：`ToolName.SILENT_TOOL_KEYS` 中的工具（`load_skill_through_path`、`qianchui_get_mcp_token`、`qianchui_load_diagnosis_card`、`ping`）为静默工具，执行结果不落消息库、不通过 SSE 透出到前端。测试验证技能加载或千锤取令牌是否实际触发时，不能仅看前端对话展示或 `/api/v1/messages`，须通过 Langfuse trace 或 ELK 日志核实。
- 依据：`base` `ToolName.java#L168-L173`
- 关联任务／用例：[kb-bug-analyse](../.agents/skills/kb-bug-analyse/SKILL.md)
- 确认人：Agent 代码核查（用户授权知识沉淀）
- 最近核对日期：2026-11-18
- 失效条件或复核提示：`ToolName.SILENT_TOOL_KEYS` 名单增删时同步更新

## K-004：预生产与测试环境 `agents` 列表接口返回业务码 9001 不代表对话不可用
- 类型：已知缺陷 / 排查经验
- 验证状态：已确认（只读实测）
- 适用模块与版本：`preprod`（`.env.preprod`）与 `test`（`.env.test`）环境，通过 `kb_e2e.js` 调用
- 适用条件：使用 `kb-test-execution` 的对话 CLI 查询辅助列表时
- 结论或建议：实测在 `preprod` 与 `test` 环境执行 `kb_e2e.js agents` 均返回 `业务码 9001`（`SYSTEM_ERROR`），而同期 `kb_e2e.js skills` 可正常返回可用技能清单（`scope=0` 全局及 `scope=3` 个人技能）。排查或自动化脚本执行时不应因 `agents` 接口报错直接判定环境或默认助手不可用。
- 依据：2026-11-18 只读实测（`.runtime/scratch/20261118-beta代码扫描与环境核查.md`）及现行 [多环境对话 CLI 说明](../.agents/skills/kb-test-execution/references/kuai-buddy-cli.md)
- 关联任务／用例：[kb-test-execution](../.agents/skills/kb-test-execution/SKILL.md)
- 确认人：Agent 只读实测（2026-11-18）
- 最近核对日期：2026-11-18
- 失效条件或复核提示：待后续版本修复 `agents` 接口后复核

## K-005：Langfuse Trace 与 KuaiBuddy 业务标识精确映射规则
- 类型：排查经验
- 验证状态：已确认（源码核查）
- 适用模块与版本：`service-agent` `BizTraceField.java`（`beta` 分支 `3b72b2b`）
- 适用条件：使用 `kb-bug-analyse` 或 Langfuse 检索生产/预生产/测试运行轨迹时
- 结论或建议：`BizTraceField` 是 OTel 上下文到 Langfuse 属性的唯一映射源：会话 `threadId` 映射 `langfuse.session.id`；单次执行 `runId` 映射 `langfuse.metadata.run_id`；`userId` 映射 `langfuse.user.id`；`compId`、`agentId`、`agentCode` 分别映射 `langfuse.metadata.comp_id`、`agent_id`、`agent_code`。检索时优先使用 `runId` 或 `threadId` 精确过滤，避免在共享观测环境中混淆生产与预生产数据。
- 依据：`service-agent` `BizTraceField.java#L13-L38`
- 关联任务／用例：[kb-bug-analyse](../.agents/skills/kb-bug-analyse/SKILL.md)
- 确认人：Agent 代码核查（用户授权知识沉淀）
- 最近核对日期：2026-11-18
- 失效条件或复核提示：`BizTraceField.java` 字段变更时同步更新

## K-006：业务错误码（BizCode）全量映射与高频排查定位指南
- 类型：排查经验
- 验证状态：已确认（源码核查）
- 适用模块与版本：`base` `BizCode.java`（`beta` 分支 `6deda08`）及全网关/后端服务
- 适用条件：接口返回非 `8` 业务码、前端弹窗提示异常、或使用 `kb-bug-analyse` / `kb-test-execution` 排查失败原因时
- 结论或建议：KuaiBuddy 统一以 `8` 表示成功，错误码按千位分段归属不同业务域（全量对照表见 [业务错误码全量映射](biz-codes.md)）：
  - `1001–1999`：通用参数错误（`1001` 参数错误、`1002` 缺少参数）。
  - `2001–2104`：认证、订阅/席位及外部 Exchange 签名（`2004` refreshToken 重用告警、`2005/2006` 订阅或席位未开通、`2008` Staff Key 无效）。
  - `3001`：会话不存在。
  - `4001–4499`：Agent 与核心业务，细分关注 `4006` 并发对话冲突、`4010/4013` 岗位因成员归属禁止停用/删除、`4050–4057` 运行控制/运维窗口(`4051`)/沙箱异常(`4052`/`4053`)/上下文超限(`4054`)/长期记忆(`4055–4057`)、`4201–4216` 灵感/Marketplace 导入、`4301–4318` 视频制作、`4401–4410` 公开内容查询。
  - `5001–5008`：文件上传与文件库配额/权限。
  - `6001–6003`：积分账户与余额不足（`6001`）。
  - `7001–7006`：定时任务与团队任务权限（`7004` 企业任务成员只读）。
  - `8001–8012`：连接器与个人 MCP（`8007` 认证失败、`8008` 30s 超时、`8010/8012` 工具定义变化）。
  - `9001`：系统繁忙（`SYSTEM_ERROR`）。
  - `10001–10005`：渠道机器人与扫码登录；`11001–11003`：广告授权上游异常。
- 依据：`base` `src/main/java/cn/kst/kuaibuddy/base/enums/BizCode.java`（`6deda08`），已整理至 [biz-codes.md](biz-codes.md)
- 关联任务／用例：[kb-bug-analyse](../.agents/skills/kb-bug-analyse/SKILL.md)、[kb-test-execution](../.agents/skills/kb-test-execution/SKILL.md)
- 确认人：Agent 代码核查（用户授权知识沉淀）
- 最近核对日期：2026-11-22
- 失效条件或复核提示：`BizCode.java` 枚举增删或文案调整时同步更新 [biz-codes.md](biz-codes.md)

## 知识条目模板（不是已确认知识）

```markdown
## K-<唯一编号>：<标题>
- 类型：风险经验／已知缺陷／排查经验／测试策略
- 验证状态：已确认
- 适用模块与版本：<填写>
- 适用条件：<触发条件与边界>
- 结论或建议：<可复用内容>
- 依据：<正式资料、可访问的缺陷链接、受控证据归档及必要 Run 标识>
- 关联任务／用例：<仓库内路径或编号>
- 确认人：<填写>
- 最近核对日期：<YYYY-MM-DD>
- 失效条件或复核提示：<版本、规则变更等>
```

## K-007：ego-browser 截图保存须使用 copyFileSync 复制临时文件路径
- 类型：工具经验
- 验证状态：已确认（实测验证）
- 适用模块与版本：`ego-browser` v2.2.1（macOS）
- 适用条件：使用 `ego-browser nodejs` 执行 `await page.screenshot()` 保存截图至本地目录时
- 结论或建议：`page.screenshot()` 返回的是临时 PNG 文件路径字符串，而非图片二进制 `Buffer`。切勿直接 `fs.writeFileSync(targetPath, await page.screenshot())`（会写入 76B 路径字符串导致图片损坏），应使用 `fs.copyFileSync(await page.screenshot(), targetPath)` 并可用 `file` 命令校验 PNG 文件头。
- 依据：2026-11-25 `MAN-004` 预生产 UI 测试实测验证（`PNG image data, 1500 x 798`）。
- 关联任务／用例：[KB-RELEASE-MANUAL-001.md](tests/cases/KB-RELEASE-MANUAL-001.md)
- 确认人：用户确认沉淀
- 最近核对日期：2026-11-25
- 失效条件或复核提示：`ego-browser` 升级并变更 `page.screenshot()` 返回值类型时复核

其他成员无法直接访问本机 `.runtime/`。用于共享知识的关键依据应提供脱敏摘要或受控归档引用；失效条目保留编号并标记失效及替代条目。
