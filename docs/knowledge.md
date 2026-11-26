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

## K-008：个人 Skill 软删复活沿用旧状态陷阱、隔离报错原文及 `_import` 静默加载口径
- 类型：排查经验／测试策略
- 验证状态：已确认（源码核查＋预生产实测）
- 适用模块与版本：`web-agent`（`AgentSkillStore.java`、`AgentSkillServiceImpl.java`）、`service-agent`（`UserSkillTool.java`），`beta` 分支及预生产当前部署
- 适用条件：涉及个人 Skill（`scope=3`）创建、覆盖、启停、删除自清理及跨会话触发加载验证的场景
- 结论或建议：
  1. **防软删停用复活**：`AgentSkillStore.findOwned` 查同名个人 Skill 包含软删行（`deleted=1`），`overwriteExisting` 复活时会沿用旧行的 `status`。若先 `userDisable`（`status=0`）后直接 `userDelete`，后续同名保存会复活为停用态。自动化测试须采用随机短名，且 `finally` 清理前若 `status != 1` 须先 `userEnable` 再 `userDelete`。
  2. **内置技能隔离报错原文**：对话内 `query_skill` 查询全局内置 Skill 时返回 `Error: Tool execution failed: Skill 不存在`（不含 `"4004"` 数字码，Langfuse Span `level="DEFAULT"`），自动化断言应匹配 `Skill 不存在`。
  3. **运行时 `_import` 静默加载**：个人 Skill 在新会话触发时，沿用 `K-003` 静默机制不透出 SSE `TOOL_CALL_START`，须在 Langfuse 中核验 `load_skill_through_path(skillId="<name>_import", path="SKILL.md")`；Web 导出 `/skill/userExport` 的 ZIP Base64 字段名为 `zipBase64`。
- 依据：`web-agent` `AgentSkillStore.java#L108-L150`、`SkillExportVO.java#L9-L12`、`service-agent` `UserSkillTool.java#L29-L71`；2026-11-26 预生产 `CASE-09` 全链路实测脱敏结论（`bad.txt` 返回 `4102`、全局重名返回 `4104`、新会话 Langfuse 命中 `<name>_import`、启停删除闭环通过）
- 关联任务／用例：[KB-SUITE-001.md](../tests/cases/KB-SUITE-001.md)（`CASE-09`）
- 确认人：用户确认沉淀（2026-11-26）
- 最近核对日期：2026-11-26
- 失效条件或复核提示：`AgentSkillStore.overwriteExisting` 状态沿用策略、个人 Skill 运行时 `skillId` 命名或 `ToolName.SILENT_TOOL_KEYS` 调整时复核

## K-009：AI 生图工具自动入库免二次保存、单张 K1 计费参考及文件库删后 COS 404 机制
- 类型：排查经验／测试策略
- 验证状态：已确认（源码核查＋预生产实测）
- 适用模块与版本：`service-agent`（`ImageGenTool.java`、`ImageGenPostProcessor.java`）、`web-agent`（`LibraryServiceImpl.java`），`beta` 分支及预生产当前部署
- 适用条件：涉及 `text_to_image` / `image_to_image` 生图测试、积分配额预估及文件库清理后的链接访问核查场景
- 结论或建议：
  1. **自动结算与入库**：`ImageGenPostProcessor.settleAndPersist` 在生图成功后自动触发积分扣减与永久 COS 入库并返回 `accessUrl`，工具契约要求无需再调用 `save_image_to_library`（回归校验其调用次数为 `0`）。
  2. **生图积分基线**：预生产实测单张最小规格（`count=1, resolution="K1", aspect_ratio="R_1_1"`）文生图与图生图均固定触发 1 笔独立 `-61.73` 积分 `DEDUCT`（两轮含推理共耗约 `125` 积分），含生图的回归测试建议账号余额门槛 `> 150` 积分。
  3. **文件库删除联动物理删 COS**：`LibraryServiceImpl.delete` 软删数据库记录后会紧接执行 `cosUtils.delete(a.getOssPath())` 物理删除 COS 对象；因此自清理完成后，原 `accessUrl` 返回 `HTTP 404` 属正常清理结果（历史聊天文本中遗留的链接会显示裂图，并非生图失败）；如需保留样图人工目视检查，应在清理前下载至本地 Run `artifacts/`。
- 依据：`service-agent` `ImageGenTool.java#L30-L85`、`ImageGenPostProcessor.java#L32-L39`、`web-agent` `LibraryServiceImpl.java#L83-L106`；2026-11-26 预生产 `CASE-10` 实测脱敏结论（清理前两图直连 `HTTP 200` `image/png`，清理后文件库为空且原 COS 链接均返 `HTTP 404`）
- 关联任务／用例：[KB-SUITE-001.md](../tests/cases/KB-SUITE-001.md)（`CASE-10`）
- 确认人：用户确认沉淀（2026-11-26）
- 最近核对日期：2026-11-26
- 失效条件或复核提示：生图模型候选池／积分定价调整，或 `LibraryServiceImpl.delete` 改为延迟异步清理 COS 时复核

其他成员无法直接访问本机 `.runtime/`。用于共享知识的关键依据应提供脱敏摘要或受控归档引用；失效条目保留编号并标记失效及替代条目。
