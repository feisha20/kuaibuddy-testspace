---
name: kb-suite-runner
description: 在 KuaiBuddy 测试、预生产或生产环境执行 KB-SUITE-001 回归测试集（单用例、局部组合或全量 CASE-01～CASE-10），联动 Langfuse/API/Nacos 采集多口径证据，并将结果校验渲染或合并为可离线分享的标准化 HTML 回归报告时使用。
---

# KuaiBuddy KB-SUITE-001 回归执行与报告生成

本技能用于在受控授权前提下编排执行 KuaiBuddy 核心回归测试集 [KB-SUITE-001.md](../../../tests/cases/KB-SUITE-001.md)（`CASE-01`～`CASE-10`，覆盖 `6` 大能力域 × `23` 项能力标签），采集对话 SSE、接口、Nacos 配置及 Langfuse 观测证据，并严格通过门禁校验生成可离线分享的单文件交互式 HTML 回归报告。

## 复用工作区资产（优先复用，不重复实现）

| 资产 | 用途 | 路径 |
|---|---|---|
| 测试集定义 | `CASE-01`～`CASE-10` 固定提示词、接口契约与双/四方验收标准 | [KB-SUITE-001.md](../../../tests/cases/KB-SUITE-001.md) |
| 固定报告模板 | 含能力图谱、环境配置 6 格、AI 总结与用例抽屉的单文件 HTML | [kb-suite-001-report.html](../../../tests/templates/kb-suite-001-report.html) |
| 报告校验与渲染器 | JSON Schema 校验、多 Run 合并与模板安全注入 | [render_suite_report.py](../../../tests/scripts/render_suite_report.py) |
| 报告数据样例 | `kb-suite-001-report.v1` 四态结构参考（非实测结果） | [kb-suite-001-report-sample.json](../../../tests/data/kb-suite-001-report-sample.json) |
| 多环境对话 CLI 与模板 | `kb_e2e.js` 登录/对话/回读与 `plan/execution/result` 模板 | [kb-test-execution](../kb-test-execution/SKILL.md) |
| 观测脚本 | `langfuse_fetch.py`、`local_config.py`（v2 observations 直连拉取） | [kb-bug-analyse](../kb-bug-analyse/SKILL.md) |
| 已确认经验与错误码 | `K-001`～`K-009` 口径校准、BizCode 全量表与环境说明 | [knowledge.md](../../../docs/knowledge.md) / [biz-codes.md](../../../docs/biz-codes.md) / [project.md](../../../docs/project.md) |

## 多环境配置与授权映射

执行前必须明确目标环境。目标环境、授权范围或账号角色不明确时，先确认再连接，禁止凭猜测连线或跨环境混用凭据。

| 目标环境 | 对话 CLI (`KB_ENV_FILE`) | Langfuse (`langfuseEnv`) | Nacos 连接 (DBX) | 业务库 (DBX) | 授权要求 |
|---|---|---|---|---|---|
| `test`（测试） | `.env.test` | `test` | `nacos-kuaibuddy-tkf` | `kuaibuddy-tkf` | 按任务确认测试数据与读写范围 |
| `preprod`（预生产） | `.env.preprod` | `prd`（与生产共用，须按 `runId`/`threadId` 过滤） | `nacos-kuaibuddy-预生产` | `kuaibuddy-生产`（共用库，须核实归属） | 按任务确认读写、配额及清理范围 |
| `prod`（生产） | `.env.prod` | `prd` | `nacos-kuaibuddy-生产` | `kuaibuddy-生产` | **必须获用户明确授权后方可连线与执行** |

## 端到端执行流程

### 步骤 1：范围确认与环境预检

1. 明确目标环境（`test` / `preprod` / `prod`）、本次执行的 Case 子集（支持单用例、局部组合或全量 10 项），以及是否复用长期 `TASK_ID`（默认单次请求不分配 `TASK_ID`）。
2. 执行一次登录刷新令牌缓存（禁止打印令牌原文）：
   ```bash
   KB_ENV_FILE=<ENV_FILE> node .agents/skills/kb-test-execution/scripts/kb_e2e.js login --force --json
   ```
   若包含 `CASE-08`，拍完 Step 0 基线后全程复用 `.runtime/cache/kuaibuddy-preprod/token.json` 中的 `accessToken`，不要再次登录以免影响积分基线核对。
3. **前置门禁与配置采集**：
   - 检查运维窗口 `GET /service/agent/api/v1/agent/maintenance`（须 `enabled == false`）与积分余额 `POST /web/agent/api/v1/points/account`（`CASE-08` 需 `> 10` 积分，`CASE-10` 需 `> 150` 积分）。
   - **环境配置采集（DBX MCP）**：通过 `dbx` 服务调用 `dbx_nacos_get_config`（在 DeepSeek Harness 中经 `call_mcp_tool` 传 `ServerName="dbx"`, `ToolName="dbx_nacos_get_config"`）只读读取 `data_id="service-agent.yaml"`、`group="DEFAULT_GROUP"`（`connection_name`：`test` 用 `nacos-kuaibuddy-tkf`，`preprod` 用 `nacos-kuaibuddy-预生产`，`prod` 仅在获授权后用 `nacos-kuaibuddy-生产`），提取 `envConfig` 六项展示字段与 `CASE-02` 压缩阈值。
   - **DBX 断连处理**：若预检阶段 `dbx` 返回 `disconnected` / 不可达，先明确提示用户检查当前会话的 DBX MCP 连接状态，必要时等待用户重连后再继续；如确认继续无 DBX 执行，则未知项统一标 `"未采集"`（可按 `events.json`/Langfuse 补充实测模型或触发点，禁止编造），待后续 DBX 恢复后通过 `check-and-render` 回补重渲染。
   - 前置条件或网络依赖不满足的用例直接标记为 `blocked`，不强行猜跑，继续可执行用例。

### 步骤 2：初始化独立 Run 目录

统一使用本技能脚本初始化（严禁覆盖历史目录）：

```bash
python3 .agents/skills/kb-suite-runner/scripts/suite_helper.py init-run \
  --summary "<对象模块+验证目标，如：预生产核心能力局部回归>" \
  --run-summary "<本次具体范围>" \
  --env <test|preprod|prod> \
  --init-report-json
```

若复用既有长期任务，补充 `--task-id TASK-xxx`。脚本会自动创建 `.runtime/requests/...` 或 `.runtime/tasks/...` 目录、`logs/ screenshots/ artifacts/`、填充 `plan.md / execution.md / result.md`、采集当前 `gitCommit` 与 `worktreeDirty`，并在 `artifacts/report-data.json` 生成初始骨架。随后补全 `plan.md` 中的范围、依据与清理边界。

### 步骤 3：按用例规范执行与多口径取证

严格按照 [KB-SUITE-001.md](../../../tests/cases/KB-SUITE-001.md) 中的**固定输入提示词**与 [用例执行速查与避坑指南](references/case-execution-guide.md) 逐项执行：

- **禁止修改固定契约**：各用例的 Exact Prompt、边界规格（如 `CASE-02` 中文+JSON 日志、`CASE-10` `K1`/`R_1_1`）及参数格式不得随意改写。
- **静默工具必须查 Langfuse**：`load_skill_through_path` 等静默工具不透出 SSE（参见 `K-003` / `K-008`），须通过 `langfuse_fetch.py` 复用逻辑（`ProxyHandler({})` 直连、`fields=core,basic,usage,model,time`）在根 Span 带 `endTime` 收口后统计全部 `GENERATION` 与 `TOOL`。
- **强自清理边界**：涉及写副作用的用例（`CASE-03 / CASE-05 / CASE-06 / CASE-07 / CASE-08 / CASE-09 / CASE-10`）必须在 `try ... finally` 中清理临时测试资产，并复核测试前既有基线数据完全无损。
- **实时落盘动作**：每次真实执行、时间窗（含 `+08:00` 或 UTC 时区）与脱敏证据路径实时记录到 `<RUN_DIR>/execution.md`，不预填成功。

### 步骤 4：整理 `result.md` 与 `artifacts/report-data.json`

1. 在 `<RUN_DIR>/result.md` 中严格按「通过 / 失败 / 阻塞 / 未执行」四种互斥状态统计结果（未执行不得记为通过），分清**已证实事实**、**待验证推断**与**证据缺口**，并按 [知识积累流程](../../../docs/knowledge-workflow.md) 链接候选文件或注明「无」。
2. 按 [报告数据结构与外发规范](references/report-schema-and-style.md) 更新 `<RUN_DIR>/artifacts/report-data.json`：
   - 仅写入本次**实际处理过（含阻塞/失败）的用例**，模板自动补齐未执行项并计为 `not_run`；`isPlaceholderDemo` 必须为 `false`。
   - `envConfig` 固定填写 6 项配置格，不使用 `extraItems` 撑高左卡。
   - `aiSummary` 面向外部分享，只写精炼结论、核心指标/问题与资源汇总，**严禁**出现本地工作区文件名、文档名、脚本名、知识编号（`K-008` 等）、`.runtime/` 路径或任何账号令牌。

### 步骤 5：三道门禁校验与 HTML 报告渲染／合并

**禁止手改模板 HTML 注入数据**，一律通过 `suite_helper.py check-and-render` 执行 Schema、外发脱敏、凭据与状态一致性检查并生成离线 HTML：

```bash
# 仅门禁检查（不写 HTML）
python3 .agents/skills/kb-suite-runner/scripts/suite_helper.py check-and-render \
  --data "<RUN_DIR>/artifacts/report-data.json" --check-only

# 校验并生成单次独立 HTML 报告
python3 .agents/skills/kb-suite-runner/scripts/suite_helper.py check-and-render \
  --data "<RUN_DIR>/artifacts/report-data.json" \
  --out "<RUN_DIR>/artifacts/report.html"

# 多次局部执行合并输出总览报告（后者覆盖同 ID 用例，自动重算汇总并清除单次 aiSummary）
python3 .agents/skills/kb-suite-runner/scripts/suite_helper.py check-and-render \
  --data "<RUN_A>/artifacts/report-data.json" \
  --data "<RUN_B>/artifacts/report-data.json" \
  --out "<RUN_DIR>/artifacts/merged-report.html"
```

### 步骤 6：交付结果与安全红线

- 向用户汇报：`TASK_ID`、`RUN_ID`、目标环境、通过/失败/阻塞/未执行计数、数据清理实况、知识候选状态，以及 `result.md`、`report-data.json`、`report.html` 的工作区相对路径链接（禁止使用 `file://` URL）。
- 安全红线：不在对话、脚本、日志或报告中输出凭据/Token/未经脱敏的生产客户信息；不擅自启动浏览器进行 UI 操作；不自动提交或推送 Git。
