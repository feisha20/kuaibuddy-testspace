# KB-SUITE-001 报告数据结构与外发规范

本规范约定 `report-data.json`（Schema `kb-suite-001-report.v1`）的数据结构、Nacos 环境配置采集口径、`aiSummary` 外发写作规范，以及多 Run 合并与三道门禁规则。固定模板见 [kb-suite-001-report.html](../assets/kb-suite-001-report.html)，底层渲染器见 [render_suite_report.py](../scripts/render_suite_report.py)，结构样例见 [kb-suite-001-report-sample.json](../../../../tests/data/kb-suite-001-report-sample.json)。

## 1. JSON 顶层结构（`kb-suite-001-report.v1`）

```json
{
  "schemaVersion": "kb-suite-001-report.v1",
  "isPlaceholderDemo": false,
  "meta": { ... },
  "cases": [ ... ],
  "envConfig": { ... },
  "aiSummary": { ... },
  "notes": { ... }
}
```

- `isPlaceholderDemo`：真实执行 Run **必须**置为 `false`（仅人工演示样例设 `true`）。
- `cases`：**仅写入本次实际执行或受阻塞失败的用例**（ID 唯一且须存在于 [KB-SUITE-001.md](../../../../tests/cases/KB-SUITE-001.md) 测试集目录中），未执行的用例由前端模板自动补齐为「未执行」，不拉低本次通过率。

### 1.1 `meta` 字段说明

| 字段 | 是否必填 | 类型/合法值 | 说明 |
|---|---|---|---|
| `suiteId` | 必填 | `"KB-SUITE-001"` | 测试集固定标识 |
| `runId` | 必填 | 非空字符串 | UTC 时间戳 + 中文本次概要 + 6 位随机后缀 |
| `env` | 必填 | `"test"` / `"preprod"` / `"prod"` | **必须使用小写**，与面板顶部环境徽章一致 |
| `taskId` | 推荐 | `"TASK-xxx"` 或 `"无（单次请求）"` | 单次请求严禁虚构 `TASK_ID` |
| `langfuseEnv` | 推荐 | `"test"` / `"prd"` | 测试填 `test`，预生产/生产填 `prd` |
| `startedAt` / `finishedAt` | 推荐 | `"YYYY-MM-DD HH:MM:SS +08:00"` | 必须携带明确时区 |
| `durationMs` | 推荐 | 整数（毫秒） | 本次耗时；多 Run 合并时自动累加 |
| `gitCommit` | 推荐 | 完整 40 位 Git SHA | 由 `suite_helper.py init-run` 自动采集 |
| `worktreeDirty` | 推荐 | 布尔值 `true` / `false` | 反映工作树是否存在未提交改动 |
| `modelSummary` | 推荐 | 字符串 | 实测主用模型概要 |
| `pointsBefore` / `pointsAfter` / `pointsConsumed` | 可选 | 数值 | 账号前/后/净消耗积分（合并时自动移除前后余额，只保留累计净消耗） |
| `cleanupStatus` | 推荐 | `"passed"` / `"failed"` / `"partial"` / `"not_needed"` / `"unknown"` | 多 Run 合并时取最严重等级：`failed > partial > unknown > passed > not_needed` |
| `cleanupNote` | 可选 | 字符串 | 数据清理实况说明（脱敏） |

### 1.2 `cases[*]` 字段说明

- `id`：属于 [KB-SUITE-001.md](../../../../tests/cases/KB-SUITE-001.md) 目录中已定义的 `CASE-xx` 编号（由 `render_suite_report.py` 在校验/渲染时自动从该 Markdown 解析校验，不写死上限）。
- `status`：`"passed"` / `"failed"` / `"blocked"` / `"not_run"`。
  - **一致性约束**：`status == "passed"` 时，`steps[*].status` 不得包含 `failed` 或 `blocked`；`status == "not_run"` 时，`steps[*].status` 不得包含 `passed`/`failed`/`blocked`。
- `summary`：单用例精炼实测结论（1～2 句，脱敏）。
- `startedAt`、`durationMs`、`threadIds`、`runIds`：真实执行时间窗、会话 ID 与 Langfuse `runId` 列表。
- `metrics`：`{ "cacheHitRate": 97.44, "points": 34.59, "extra": "..." }`（字段按需填写；并行执行多用例时，可从各轮 `events.json` 中 `type == "CUSTOM" && name == "usage"` 事件的 `value.points` 累加得到单用例 `points`）。
- `cleanup`：`{ "status": "<枚举同上>", "note": "..." }`。
- `steps`：`[{ "name": "...", "status": "passed|failed|blocked|not_run", "expected": "...", "actual": "...", "evidence": "..." }]`。
- `calibrations`、`evidencePaths`：单用例实测校准说明与相对证据路径列表（仅放脱敏路径）。

## 2. `envConfig` 固定 6 格与 Nacos 采集映射

前端左侧 Hero「测试环境关键配置」锁定为固定高度的 6 项配置格（**不要使用 `extraItems` 撑高左卡**）：

| JSON 键 | 面板标签 | Nacos `service-agent.yaml` 参考路径 | 缺失占位 |
|---|---|---|---|
| `source` | 面板右上来源标签 | 例如 `"Nacos service-agent.yaml (<env>)"` | `"<ENV> 环境配置（未采集）"` |
| `primaryModel` | 主模型（Primary） | `model.defaults.main.candidates` + `model.<...>.context-window-size` | `"未采集"` |
| `fallbackModel` | 备模型（Fallback） | `model.defaults.fallback` + 窗口大小 | `"未采集"` |
| `imageGenModel` | 生图模型（Image Gen） | `model.defaults.text-to-image.candidates` 模型候选池 | `"未采集"` |
| `visionFollowupModel` | 视觉 / 追问模型 | `model.defaults.vision.candidates` / `model.defaults.followup.model` | `"未采集"` |
| `compactionThreshold` | 上下文压缩阈值 | `agent.compaction.trigger-tokens`（未显式配置时走代码默认 `240,000`）与 `agent.compaction.trigger-messages` | `"未采集"` |
| `toolLimits` | 文件读取 / 沙箱限额 | `agent.tool.read-file-max-chars` 与 `agent.filesystem.sandbox` | `"未采集"` |

**通过 DBX MCP 只读查询 Nacos**：
- 通过 `dbx` 服务调用 `dbx_nacos_get_config`（如在 DeepSeek Harness 中经 `call_mcp_tool` 调用 `ServerName="dbx"`, `ToolName="dbx_nacos_get_config"`）：
  - `test`：`connection_name="nacos-kuaibuddy-tkf"`, `data_id="service-agent.yaml"`, `group="DEFAULT_GROUP"`
  - `preprod`：`connection_name="nacos-kuaibuddy-预生产"`, `data_id="service-agent.yaml"`, `group="DEFAULT_GROUP"`
  - `prod`（仅授权后）：`connection_name="nacos-kuaibuddy-生产"`, `data_id="service-agent.yaml"`, `group="DEFAULT_GROUP"`
- 仅提取上述非敏感模型名与数值阈值；严禁将 Nacos 中的任何内网密钥、数据库连接串、AK/SK 或鉴权头写入 `envConfig`。若预检时 `dbx` 返回断连（`disconnected`），先提示用户检查连接状态，必要时等待重连；无法连接时保留 `"未采集"` 并禁止编造，事后可补采重渲染。

## 3. `aiSummary` 外发写作规范与脱敏门禁

报告经常直接用于跨团队分享或外发评审，右侧 `AI 总结分析` 与左侧 `测试环境关键配置` **必须完全干净、面向业务与质量读者**：

### 3.1 推荐结构（控制高度、直给结论与问题）

```json
"aiSummary": {
  "source": "实测总结",
  "headline": "预生产 CASE-01（5 轮串行）全部通过，Skill 加载、多步工具与 Prompt 缓存命中率均达标。",
  "sections": [
    {
      "title": "核心结论",
      "items": [
        "1～2 句直接给核心验证结果、关键指标峰值或失败/阻塞定位"
      ]
    },
    {
      "title": "效能与资源",
      "items": [
        "主模型、总耗时、积分消耗与数据清理闭环结果"
      ]
    },
    {
      "title": "待关注项",
      "items": [
        "仅记录客观业务/环境待确认事项或未覆盖提醒，无则省略此分组"
      ]
    }
  ],
  "recommendation": "一句话给出当前质量放行评估或下一步优先补跑用例。"
}
```

### 3.2 严格禁用项（脚本自动门禁拦截）

以下内部工程信息**严禁出现**在 `aiSummary` 与 `envConfig` 的任何字段中（一旦包含将被 `suite_helper.py check-and-render` 阻断，退出码 `1`）：
- `KB-SUITE-001.md`
- `docs/knowledge.md`
- `render_suite_report`
- `K-008`、`K-009`
- `.runtime/`
- `AGENTS.md`
- `Agent 实测归纳`
- `.agents/skills/`

**全文件凭据红线**：`report-data.json` 任意字段中均不可包含 Bearer Token、JWT（`eyJ...`）、Langfuse 密钥（`sk-lf-`/`pk-lf-`）、明文 `accessToken`/`refreshToken`/`password`/`secretKey`/`apiKey`/`authorization` 值或未脱敏客户隐私数据。

## 4. 单真源目录注入与多 Run 合并行为说明

每次通过 `suite_helper.py check-and-render` 或 [render_suite_report.py](../scripts/render_suite_report.py) 渲染报告时：
- 工具自动解析 `--suite`（默认 [KB-SUITE-001.md](../../../../tests/cases/KB-SUITE-001.md)）生成最新能力域、标签与用例目录，同时注入模板的 `<script id="kb-suite-catalog">` 槽位；可用 `--check-suite` 单独校验测试集 3.1/3.2/第 4 节自洽性，或用 `--preview-suite` 一键导出 0 已执行用例的交互式浏览 HTML，用 `--sync-template` 刷新模板内置兜底快照。

当向 `suite_helper.py check-and-render` 传入多个 `--data` 时，底层调用 [render_suite_report.py](../scripts/render_suite_report.py) 的 `merge_payloads` 执行：
1. 同一 `CASE-xx` 由**后传入的数据覆盖先传入的数据**，因此按从旧到新顺序传参即可保留最新复测结论。
2. `durationMs` 与 `pointsConsumed` 自动累加；单次运行的 `pointsBefore`、`pointsAfter` 与单份 `aiSummary` 自动丢弃，改由前端 `buildAutoAiSummary()` 根据合并后的全集自动生成干净的 `核心结论 / 效能与资源 / 覆盖缺口` 摘要。
3. `cleanupStatus` 自动取全部入参中的最差状态，防止“某轮清理失败被后续轮覆盖成通过”。
4. `envConfig` 非空字段按后者覆盖前者合并。
