# KuaiBuddy Agent 测试工作区

管理项目事实、已确认经验、测试用例、脚本、非敏感数据和可复用任务。每位成员独立开展测试；单次执行过程留在本机 `.runtime/`。

## 目录与入口

| 路径 | 用途 |
|---|---|
| [AGENTS.md](AGENTS.md) | Agent 工作规范 |
| [.agents/skills/](.agents/skills/) | 项目测试设计与执行方法 |
| [docs/project.md](docs/project.md) | 项目事实、资料入口、环境与待补充信息 |
| [docs/knowledge.md](docs/knowledge.md) | 有依据且已确认的测试经验 |
| [tests/cases/](tests/cases/) | 可复用用例及模板 |
| [tests/scripts/](tests/scripts/) | 经验证的自动化脚本 |
| [tests/data/](tests/data/) | 非敏感样例与数据约定 |
| [tasks/](tasks/) | 可复用任务定义 |
| `.runtime/` | 本机计划、执行记录、结果、日志、截图、报告与缓存；整体忽略 |
| [设计方案](Agent测试工作区规划设计方案.md) | 本工作区的设计依据，示例业务并非 KuaiBuddy 规则 |

## 首次使用

1. 阅读 AGENTS.md 和 docs/project.md，补齐本次任务需要的正式需求、环境与权限。
2. 检索任务和已有测试资产。已有目标可复用原任务；新任务复制 [tasks/_template.md](tasks/_template.md)，分配未使用的 TASK_ID。
3. 选用项目技能；任务设计与测试执行分开进行。当前 [TASK-001](tasks/TASK-001.md) 是对话回归任务，关联用例尚待正式规则补齐，不能直接当作已验证用例执行。
4. 明确执行范围后，让 Agent 新建唯一 Run，填入三个运行模板并记录真实动作。
5. 核对 result.md；有可复用成果时，经工程师确认后更新长期资产，通过 Git 人工评审。

可向 Agent 发送：

> 请依据 AGENTS.md 执行 tasks/TASK-001.md。先检索相关资料和资产，核实前置条件；创建独立 Run 并记录计划、实际动作、结果及证据。缺失依据的场景标记阻塞，不启动浏览器。可沉淀的成果先提出建议。

## 手工创建运行目录

在仓库根目录使用 macOS 的 `python3`，无需安装依赖。示例只创建本地目录和模板，不连接环境、不执行业务测试。运行前将 `task_id` 改为已存在的任务编号。

```bash
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets

task_id = "TASK-001"
assert re.fullmatch(r"TASK-[0-9]{3,}", task_id), "任务编号格式错误"
assert Path(f"tasks/{task_id}.md").is_file(), "任务定义不存在"
run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(3)
run = Path(".runtime/tasks") / task_id / run_id
run.mkdir(parents=True, exist_ok=False)
templates = Path(".agents/skills/kb-test-execution/assets")
for name in ("plan.md", "execution.md", "result.md"):
    content = (templates / name).read_text(encoding="utf-8")
    content = content.replace("{{TASK_ID}}", task_id).replace("{{RUN_ID}}", run_id)
    (run / name).write_text(content, encoding="utf-8")
for name in ("logs", "screenshots", "artifacts"):
    (run / name).mkdir()
print(run)
PY
```

Run ID 使用 UTC，记录展示时间须写明时区。初始化已建立 `.runtime/tasks/`、`scratch/`、`cache/`；其他成员 Clone 后按需重建，Git 不保存空目录。

## Git 与证据管理

- 提交长期资产；禁止提交 Runtime、密码、Token、浏览器会话及未经脱敏的数据。新增脚本时将输出定向到当前 Run。
- 用 `git check-ignore -v .runtime/example.log` 检查忽略规则，用 `git status --short` 和 `git diff` 自查变更；忽略规则不会取消已跟踪文件。
- 可用 `codex/任务名称` 分支管理变更；提交说明使用中文，不自动提交或推送。
- 关键证据保留至结论复核、缺陷处理或交付完成；团队保留期限和受控归档位置尚待补充。其他成员无法从 Git 获取本机执行记录。

## 当前初始化范围

已提供目录、规则、两个项目技能、任务与用例模板、一个待完善的对话回归任务和用例，以及 Run 模板。当前没有已验证业务规则、自动化测试脚本或真实业务测试结果；未连接环境，未启动浏览器。

项目负责人、正式需求、环境入口及证据归档约定见 docs/project.md，待团队填写。不包含 CI/CD、集中平台、自动调度或 Docker 构建。
