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
2. 检索任务和已有测试资产。已有目标复用原任务；没有合适任务时直接记录本地请求并创建 Run，无需先创建任务文件或分配 TASK_ID。
3. 选用项目技能；任务设计与测试执行分开进行。当前 [TASK-001](tasks/TASK-001-基础对话回归.md) 是对话回归任务，关联用例尚待正式规则补齐，不能直接当作已验证用例执行。
4. 明确执行范围后，让 Agent 新建唯一 Run，填入三个运行模板并记录真实动作。
5. 核对 result.md；有可复用成果时，经工程师确认后更新长期资产，通过 Git 人工评审。

## 任务进入 Git 的规则

- `tasks/` 保存可重复使用的任务定义，继续进入 Git；日常请求默认只记录到 `.runtime/`，执行本身不要求产生 Git 变更。
- 任务目标明确、步骤稳定、能够跨日期或由其他成员复用时，Agent 可提出沉淀建议；经确认后再复制 [任务模板](tasks/_template.md)，分配未使用的 TASK_ID。用户明确要求沉淀时可直接实施。
- 长期任务写通用目标、范围、前置条件、步骤、验收标准和资产引用；具体日期、授权核实、筛选条件、进度和结果写入各自 Run。同类每日分析复用一个任务定义。
- 日志、截图、生产原始数据和本次报告保持在 Runtime；团队需保留的关键证据另行归档至受控位置。Git 提交和推送仍由用户决定。

可向 Agent 发送：

> 请依据 AGENTS.md 执行 tasks/TASK-001-基础对话回归.md。先检索相关资料和资产，核实前置条件；创建独立 Run 并记录计划、实际动作、结果及证据。缺失依据的场景标记阻塞，不启动浏览器。可沉淀的成果先提出建议。

## 手工创建运行目录

收到任务后，Agent 会先总结中文概要，再创建目录。例如：

```text
# 没有长期任务定义的单次请求
.runtime/requests/生产环境昨日异常对话分析/
└── 20261103T010000Z-无回复场景排查-a1b2c3/

# 复用已有长期任务
.runtime/tasks/TASK-001-基础对话回归/
└── 20261102T140000Z-多轮追问上下文验证-a1b2c3/
    ├── plan.md
    ├── execution.md
    ├── result.md
    ├── logs/
    ├── screenshots/
    └── artifacts/
```

两类 Run 均保存上述三个记录文件和三个子目录。任务概要说明长期目标，本次概要说明这一轮的具体范围；两者一致时可使用相同概要。命名、历史目录兼容和敏感信息边界以 [AGENTS.md](AGENTS.md#任务与执行) 为准。长期任务文件使用“编号＋中文概要”，例如 `tasks/TASK-004-生产环境指定周期对话质量分析.md`；TASK_ID 仍为 `TASK-004`，不包含概要。单次请求不分配任务编号，模板的 Task ID 填“无（单次请求）”。

在仓库根目录使用 macOS 的 `python3`，无需安装依赖。示例只创建本地目录和模板，不连接环境、不执行业务测试。默认 `task_id = None` 表示单次请求；复用长期任务时改为已存在的任务编号，并填写 Agent 根据任务内容总结的中文概要。

```bash
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets

task_id = None  # 单次请求不分配编号；复用长期任务时填写如 "TASK-001"
task_summary = "生产环境昨日异常对话分析"
run_summary = "无回复场景排查"
for summary in (task_summary, run_summary):
    assert re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9-]{1,40}", summary), "概要应为中文短语，可含字母、数字和连字符，最多 40 字符"
    assert re.search(r"[\u4e00-\u9fff]", summary), "概要须包含中文"
if task_id is None:
    task_dir = Path(".runtime/requests") / task_summary
else:
    assert re.fullmatch(r"TASK-[0-9]{3,}", task_id), "任务编号格式错误"
    definitions = [path for path in Path("tasks").glob(f"{task_id}-*.md") if path.is_file()]
    assert len(definitions) == 1, "任务定义不存在或同一编号对应多个文件，请先核对"
    task_root = Path(".runtime/tasks")
    existing = sorted(
        path for path in task_root.glob(f"{task_id}*")
        if path.is_dir() and (path.name == task_id or path.name.startswith(task_id + "-"))
    )
    assert len(existing) <= 1, "同一任务编号存在多个目录，请先核对，避免拆分历史记录"
    task_dir = existing[0] if existing else task_root / f"{task_id}-{task_summary}"
run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + run_summary + "-" + secrets.token_hex(3)
run = task_dir / run_id
run.mkdir(parents=True, exist_ok=False)
templates = Path(".agents/skills/kb-test-execution/assets")
for name in ("plan.md", "execution.md", "result.md"):
    content = (templates / name).read_text(encoding="utf-8")
    content = content.replace("{{TASK_ID}}", task_id or "无（单次请求）").replace("{{RUN_ID}}", run_id)
    (run / name).write_text(content, encoding="utf-8")
for name in ("logs", "screenshots", "artifacts"):
    (run / name).mkdir()
print(run)
PY
```

Run ID 使用 UTC，记录展示时间须写明时区。初始化已建立 `.runtime/tasks/`、`scratch/`、`cache/`；其他成员 Clone 后按需重建，Git 不保存空目录。

## 本机账号与禅道配置

个人配置放仓库根目录 `.env`，变量名参照 [.env.example](.env.example)。新成员可复制该示例后在本机填写；已有 `.env` 不要覆盖。共享文档只保存变量名、用途和权限需求，不保存真实账号或凭据。

| 变量 | 用途 |
|---|---|
| `ZENTAO_URL` | 禅道服务入口 |
| `ZENTAO_ACCOUNT` | 个人登录账号 |
| `ZENTAO_PASSWORD` | 个人密码，通过进程环境提供 |
| `ZENTAO_TOKEN` | 可选的已有 Token；显式设置后不使用密码自动续期，通常无需填写 |

项目内 `zentao-qa` 技能支持以上环境变量，但不会自动读取项目 `.env`。执行相关任务时，由本地加载器读取所需变量并传给工具，不能用 `cat .env`、打印环境或命令参数展示凭据。若选择在终端使用 `source .env`，文件必须是自己维护的可信 shell 赋值文件，含特殊字符的值需正确引用；配合 `set -a` 才会向子进程导出变量，且不要开启 `set -x`。普通 dotenv 文件应使用支持其语法的加载器，不能一律当 shell 脚本执行。

调用技能脚本时显式指定 `--config .runtime/cache/zentao/config.json`（相对于仓库根目录），默认防重账本随配置保存在同目录。该目录按站点和账号固定复用；如有多个身份，在 `zentao/` 下分别设子目录。先创建父目录；配置含 Token，属于本机敏感数据，不应随意清理或共享。密码已由环境提供时，无需额外使用 `--save-password` 再保存一份。

这里的 `cache/zentao/` 是持久状态例外：防重账本不能按普通缓存随意删除，写入状态不确定时须按技能规则核查远端。

具体登录、查询和写入流程遵循项目内 [zentao-qa 技能](.agents/skills/zentao-qa/SKILL.md)，脚本入口为 `.agents/skills/zentao-qa/scripts/zentao_qa.py`，仅依赖 Python 3.9+ 标准库，同事无需另行安装同名全局技能。该副本来源于本机技能，仅复制通用说明、脚本、参考资料、测试和空值配置示例，不含个人配置与运行数据；后续更新需人工核对差异。填写 `.env` 只代表完成本机配置，不代表账号有效、权限足够或已获外部写入授权；首次实际使用时再验证并记录结果。

## Git 与证据管理

- 提交长期资产；禁止提交 Runtime、密码、Token、浏览器会话及未经脱敏的数据。新增脚本时将输出定向到当前 Run。
- 用 `git check-ignore -v .runtime/example.log` 检查忽略规则，用 `git status --short` 和 `git diff` 自查变更；忽略规则不会取消已跟踪文件。
- 可用 `codex/任务名称` 分支管理变更；提交说明使用中文，不自动提交或推送。
- 关键证据保留至结论复核、缺陷处理或交付完成；团队保留期限和受控归档位置尚待补充。其他成员无法从 Git 获取本机执行记录。

## 当前初始化范围

已提供目录、规则、两个项目技能、任务与用例模板、一个待完善的对话回归任务和用例，以及 Run 模板。当前没有已验证业务规则、自动化测试脚本或真实业务测试结果；未连接环境，未启动浏览器。

项目负责人、正式需求、环境入口及证据归档约定见 docs/project.md，待团队填写。不包含 CI/CD、集中平台、自动调度或 Docker 构建。
