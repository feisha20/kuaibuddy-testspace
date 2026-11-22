# KuaiBuddy 系统架构与核心机制（beta 分支）

> 本文档基于 `/Users/linjt/Documents/kst-projects/kuaibuddy-projects/` 各仓库 `beta` 分支源码扫描整理，最近核对日期：`2026-11-18`。仅记录代码中可验证的结构、契约与机制，不替代正式产品需求。

## 1. 仓库与服务全景

| 仓库 | 定位 | 技术栈 | 默认端口 / 部署路径 | 核对版本（`beta`） |
|---|---|---|---|---|
| `base` | 公共基础库（DTO/VO/Entity、枚举、`BizCode`、`ToolName`、Dubbo API） | Java 21 / Maven | 库依赖 | `6deda08` |
| `gateway` | 统一网关（路由转发、JWT 验签、Redis 黑名单、身份头注入） | Spring Cloud Gateway | `9900` | `9972f46` |
| `service-agent` | 核心 Agent 运行引擎（ReAct 执行、AG-UI SSE、沙箱、记忆、MCP、追踪） | Spring Boot 3.5.14 / Java 21 / AgentScope `2026.11.06-3-kst` | `9903` | `3b72b2b` |
| `web-agent` | 业务 BFF 与管理接口（会话、消息、定时任务、文件、积分、后台管理） | Spring Boot / Java 21 | `9902` | `1dbbe01` |
| `service-job` | 定时任务与周期结算（XXL-JOB 执行、空闲沙箱回收、执行看门狗、会话暂停） | Spring Boot / Java 21 / XXL-JOB | `9901` | `134b895` |
| `ui-kuai-buddy` | 员工/客服工作台前端（对话、灵感、自动化、文件库、视频、记忆、Tauri 桌面） | React 18 / Vite 6 / Antd 5 / `@agentscope-ai/chat` / `@ag-ui/client` / Tauri 2 | `/work`、`/console` | `e9427a1` |
| `ui-admin` | 公司管理后台（看板、客服账号、岗位、Skill、专家、模板、团队定时任务、订阅） | React 19 / Vite 8 / Tailwind 4 / shadcn / Redux Toolkit | `/admin` | `4c2a5ea` |

- **配置与注册中心**：后端服务统一通过 `kb-nacos:8848` 加载 `common.yaml` 与 `${spring.application.name}.yaml`。

## 2. 网关鉴权与身份模型

依据 `gateway/.../AuthGlobalFilter.java`：
1. 白名单路径直接放行。
2. 非白名单请求校验 `Authorization: Bearer <token>` JWT 签名，并检查 Redis 黑名单 `buddy:auth:blacklist:<jti>`。
3. 校验 `userId` 与 `compId` 为非零整数声明（**允许负数 `userId` 作为内部虚拟用户**，例如千锤 `userId = -1`）。
4. 清除客户端可能伪造的 `X-User-Id`、`X-Comp-Id`、`X-Dept-Id`、`X-Role-Id`、`X-Login-Name`、`X-Is-Default`、`X-Admin-Access` 等请求头后，由网关重新注入可信身份头转发下游。
5. 管理后台 `ui-admin`（`/admin`）与工作台 `ui-kuai-buddy`（`/work/`）共享登录 Token。

## 3. Agent 运行生命周期与 AG-UI 协议

### 3.1 核心入口（`service-agent`）
`AgentController`（`/api/v1/agent`）：
- `POST /api/v1/agent/run`：发起 Agent 执行，返回 `text/event-stream`（AG-UI 事件流）。`runId` 由服务端通过 `IdUtil.fastSimpleUUID()` 生成，不依赖前端传入。
- `POST /api/v1/agent/run/observe?threadId=...`：重连/刷新后观察会话当前活跃 Run（事件重放 + 尾随 + 心跳）。
- `POST /api/v1/agent/run/cancel?threadId=...`：写取消意图，由中间件中断执行。
- `POST /api/v1/agent/run/active`：查询当前用户所有活跃 `threadId`（浏览器恢复入口）。
- `GET /api/v1/agent/maintenance`：查询平台运维窗口状态（升级期间拦截新 Run，返回 `BizCode.AGENT_MAINTENANCE = 4051`）。

### 3.2 执行与观察解耦（`RunLifecycle` / `RunObservation` / `RunRegistry`）
- `RunLifecycle` 按 `闸门（gate）→ Guard → Prepare → Execute → Cleanup` 阶段编排，独立订阅执行。
- `RunObservation` 负责 SSE 旁路转发与事件缓存，**浏览器刷新或 SSE 断连不会中断后端 Run 执行**，也不会改变 Run 终态（`RUNNING` → `SUCCEEDED` / `FAILED` / `CANCELLED`）。
- 定时任务执行走 `runScheduled`，挂载 `Execution(taskId, executionId)` 并启用挂钟软/硬超时控制（`withScheduledTimeout`）。

### 3.3 自定义 AG-UI 事件（`AguiCustomEvent.java`）
`agent_result`、`exceed_max_iters`、`hint_block`、`data_block_start`、`data_block_delta`、`data_block_end`、`tool_result_data`、`user_message_saved`、`request_stop`、`points_exhausted`、`usage`、`heartbeat`、`cancelled`、`follow_up_suggestions`。

## 4. 模型选择、上下文与容灾

依据 `ModelSelector.java` 与 `AgentFactory.java`：
- **会话粘性与容量控制**：按 `CompanyUserKey + threadId` 在 Redis 维护主模型粘性绑定（`PIN_TTL = 3 小时`），同时按候选列表偏好序检查并发占用与冷却状态；若主模型异常触发 `markCooldown`，则单向迁移至下一个未冷却候选。
- **主备模型与上下文窗口**：每次装配同时构建 `PRIMARY` 与 `FALLBACK` 两个 `OpenAIChatModel`，默认上下文窗口 `128,000` tokens，并配置上下文压缩（`CompactionConfig`）与工具结果驱逐（`ToolResultEvictionConfig`）；超限时抛出 `ContextBudgetExceededException`（`BizCode 4054`）。

## 5. 工具、Skill、沙箱与长期记忆

### 5.1 工具分类与静默工具（`ToolName.java`）
- **核心工具域**：
  - 定时任务：`create_schedule` / `update_schedule_info` / `update_schedule_frequency` / `delete_schedule` / `pause_schedule` / `resume_schedule` / `list_schedules`
  - 公开内容查询：`get_public_data_capabilities` / `search_public_content` / `get_public_account` / `list_public_account_posts` / `get_public_content` / `list_public_comments`
  - 视频制作：`import_video_links` / `get_video_capabilities` / `prepare_video` / `list_attachments` / `list_video_assets` / `get_video_plan` / `analyze_video_asset`
  - 图片与识图：`text_to_image` / `image_to_image` / `analyze_image`
  - 文件与产物：`save_to_library` / `save_image_to_library` / `deliver_artifact`、`read_file` / `write_file` / `edit_file` / `grep_files` / `glob_files` / `list_files`
  - 命令执行：`execute_shell_command` / `execute`（运行于 K8s 沙箱）
  - 技能：`query_skill` / `save_skill` / `load_skill_through_path` / `skill_manage` / `propose_skill`
  - 计划与待办：`plan_enter` / `plan_write` / `plan_exit`、`todo_write`
  - 记忆与会话：`memory_search` / `memory_get` / `memory_save`、`session_search` / `session_list` / `session_history`
  - 异步与多代理：`task_output` / `task_cancel` / `task_list` / `wait_async_results`、`agent_spawn` / `agent_send` / `agent_list` / `agent_generate`、`team`
  - 千锤与在线配置助手（MCP + 本地工具）：`dialog_process_*`、`dialog_record_query`、`dialog_query_records`、`script_diagnostic_strategy_get_latest`、`faq_robot_template_*`、`qianchui_get_mcp_token`、`qianchui_diagnosis_ready`、`qianchui_load_diagnosis_card`、`qianchui_optimized_configs_ready`、`allocation_rule_query`、`agent_info_query`、`schedule_query`、`visitor_query`、`operation_log_query`、`robot_channel_query`、`kb_query`、`huolian_rule_query`、`sop_query`、`channel_auth_query`、`role_permission_query`、`channel_shop_query`、`ping`
- **静默工具（`SILENT_TOOL_KEYS`）**：`load_skill_through_path`、`qianchui_get_mcp_token`、`qianchui_load_diagnosis_card`、`ping` —— **不落库、不透出 SSE**。
- **默认禁用**：`AgentFactory` 默认将 `web_search` 加入 `deny` 列表（未提供服务凭据时禁用）。

### 5.2 Skill 作用域（`Scope.java`）
- `0 = GLOBAL`（全局内置）
- `1 = EXPERT`（专家内置）
- `2 = COMPANY`（公司自建）
- `3 = USER`（个人）
- Skill 元数据存 MySQL，运行时资源通过 `CosSkillRuntimeResourceLoader` 从 COS 水合加载。

### 5.3 沙箱与长期记忆
- **K8s 沙箱**：`K8sSandboxAdapter` / `SandboxKeeper` / `SandboxRunGuard` 管理并发冷启动复用（防止同账号并发创建多个沙箱）、环境变量注入与 `service-job` 空闲回收（`EvictIdleSandboxesJob`）。
- **长期记忆（`beta` 新增）**：仅交互式对话（`UserMemoryService.interactive(run)` 且非定时任务）挂载 `UserMemoryTool`，并在 System Prompt 末尾注入 `## 长期记忆索引`。支持公司成员级长期记忆增删改查。

## 6. 前端与业务功能域

### 6.1 工作台 `ui-kuai-buddy`（`/work`、`/console`）
- `/chat/*`（`/chatnew/*`）：主对话控制台、晨报/经营速览、引导浮层（首次登录五步引导）、对话产物抽屉、视频工作区、消息内音频/视频内嵌播放、千锤诊断与优化配置卡片。
- `/automation`：定时任务与公共模板（支持钉钉/企业微信/飞书群机器人 Webhook 及公众号推送）。
- `/inspiration`（含案例收藏与复用，以提示词初始化新任务草稿）、`/library` & `/my-files`（文件库与个人文件）、`/points`（积分中心）、`/connectors`（连接器与个人 MCP）、`/channel-config`（渠道配置）、`/skill-manage`（技能管理）、`/ima-config`、`/advertiser-authorization`。

### 6.2 公司管理后台 `ui-admin`（`/admin`）
- `/`：公司数据看板（账号统计、调用量、积分消费趋势、排行榜）。
- `/members`：客服账号只读展示与岗位归属维护。
- `/subscription`：订阅方案、席位与本周期积分使用率。
- `/positions`：岗位管理（有成员归属时禁止停用/删除，后端返回 `4010`/`4013`）。
- `/skills`、`experts`、`templates`：能力资产启停与导入（单专家 `.codebuddy-plugin` ZIP、独立 Skill ZIP 校验 `SKILL.md`）。
- `/team-schedules`：团队定时任务管理（`7004` 成员仅可查看）。

## 7. 可观测性与业务错误码

### 7.1 Langfuse 属性映射（`BizTraceField.java`）
| 业务字段 | OTel ContextKey | Langfuse 属性名 |
|---|---|---|
| `agentId` | `kuaibuddy.agentId` | `langfuse.metadata.agent_id` |
| `agentCode` | `kuaibuddy.agentCode` | `langfuse.metadata.agent_code` |
| `compId` | `kuaibuddy.compId` | `langfuse.metadata.comp_id` |
| `userId` | `kuaibuddy.userId` | `langfuse.user.id` |
| `threadId` | `kuaibuddy.threadId` | `langfuse.session.id` |
| `runId` | `kuaibuddy.runId` | `langfuse.metadata.run_id` |

### 7.2 业务错误码分段（`BizCode.java`）
全量逐条映射见 [业务错误码全量映射](biz-codes.md)（最近核对：`2026-11-22`）：
- `8`：操作成功（`SUCCESS`）
- `1001–1999`：通用参数错误
- `2001–2999`：认证、RefreshToken、订阅/席位、StaffKey、Exchange 签名
- `3001–3999`：会话（`3001` 会话不存在）
- `4001–4499`：Agent 运行与维护（`4051` 运维窗口、`4052/4053` 沙箱异常、`4054` 上下文超限、`4055–4057` 长期记忆）、岗位/专家/模板/Skill/灵感/视频/公开数据
- `5001–5999`：文件上传与文件库配额
- `6001–6999`：积分账户与余额不足（`6001`）
- `7001–7999`：定时任务与团队定时任务
- `8001–8999`：连接器与个人 MCP（超时 30s、工具变更等）
- `9001`：系统繁忙（`SYSTEM_ERROR`）
- `10001–10999`：渠道机器人配置与扫码
- `11001–11999`：广告授权
