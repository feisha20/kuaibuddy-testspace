#!/usr/bin/env python3
"""KB-SUITE-001 执行工作流辅助与外发报告门禁脚本。

提供两个子命令（纯 Python 3.9+ 标准库实现）：
  1. init-run          按 AGENTS.md / README.md 创建独立 Run 目录与报告初始骨架
  2. check-and-render  执行三道门禁检查并调用 render_suite_report.py 渲染或合并 HTML 报告
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys

DEFAULT_ROOT = Path(__file__).resolve().parents[4]

SUMMARY_ALLOWED_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9-]{1,40}$")
SUMMARY_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TASK_ID_RE = re.compile(r"^TASK-[0-9]{3,}$")

VALID_ENVS = {"test", "preprod", "prod"}
VALID_CLEANUP_STATUSES = {"passed", "failed", "partial", "not_needed", "unknown"}

BANNED_EXTERNAL_TOKENS = (
    "KB-SUITE-001.md",
    "docs/knowledge.md",
    "render_suite_report",
    "K-008",
    "K-009",
    ".runtime/",
    "AGENTS.md",
    "Agent 实测归纳",
    ".agents/skills/",
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Bearer Token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("Langfuse Key", re.compile(r"\b(?:sk|pk)-lf-[A-Za-z0-9_\-]{8,}\b")),
    (
        "明文敏感凭据字段",
        re.compile(
            r'"(?:accessToken|refreshToken|password|secretKey|apiKey|authorization)"\s*:\s*"(?![\s*<])[^"]{6,}"',
            re.IGNORECASE,
        ),
    ),
)


def load_render_module(root: Path):
    """动态加载工作区唯一的 tests/scripts/render_suite_report.py，不复制逻辑。"""
    candidate = root / "tests" / "scripts" / "render_suite_report.py"
    if not candidate.is_file():
        candidate = DEFAULT_ROOT / "tests" / "scripts" / "render_suite_report.py"
    if not candidate.is_file():
        raise FileNotFoundError(f"找不到报告渲染脚本：{candidate}")
    spec = importlib.util.spec_from_file_location("kb_render_suite_report", str(candidate))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块 spec：{candidate}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate_summary_text(value: str, label: str) -> None:
    """校验中文概要字符范围（仅中文、英文字母、数字和连字符，1-40 字且含中文）。"""
    if not SUMMARY_ALLOWED_RE.fullmatch(value):
        raise ValueError(f"{label} 格式非法（仅允许 1~40 位中文/英文字母/数字/连字符）：{value!r}")
    if not SUMMARY_CJK_RE.search(value):
        raise ValueError(f"{label} 必须包含至少一个中文字符：{value!r}")


def collect_git_info(root: Path) -> tuple[str, bool | None]:
    """只读采集目标工作区当前完整 Git 提交号与工作树脏状态。"""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode != 0 or not head.stdout.strip():
            return "unknown", None
        commit = head.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        return commit, dirty
    except OSError:
        return "unknown", None


def format_local_timestamp() -> str:
    """生成带冒号偏移的本地当前时间字符串（例如 2026-11-26 11:20:00 +08:00）。"""
    now = datetime.now().astimezone()
    tz_raw = now.strftime("%z") or "+0000"
    tz_fmt = f"{tz_raw[:3]}:{tz_raw[3:]}" if len(tz_raw) == 5 else tz_raw
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {tz_fmt}"


def cmd_init_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    summary = args.summary.strip()
    run_summary = (args.run_summary or summary).strip()

    try:
        validate_summary_text(summary, "--summary")
        validate_summary_text(run_summary, "--run-summary")
    except ValueError as exc:
        print(f"[suite_helper] 参数错误：{exc}", file=sys.stderr)
        return 2

    task_id = args.task_id.strip() if args.task_id else None
    if task_id is None:
        task_dir = root / ".runtime" / "requests" / summary
        task_id_label = "无（单次请求）"
    else:
        if not TASK_ID_RE.fullmatch(task_id):
            print(f"[suite_helper] 参数错误：--task-id 格式非法（应如 TASK-001）：{task_id!r}", file=sys.stderr)
            return 2
        tasks_dir = root / "tasks"
        definitions = [p for p in tasks_dir.glob(f"{task_id}-*.md") if p.is_file()] if tasks_dir.is_dir() else []
        if len(definitions) != 1:
            print(
                f"[suite_helper] 错误：任务定义不存在或同一编号对应多个文件（找到 {len(definitions)} 个）：{task_id}",
                file=sys.stderr,
            )
            return 2
        task_root = root / ".runtime" / "tasks"
        task_root.mkdir(parents=True, exist_ok=True)
        existing = sorted(
            p
            for p in task_root.glob(f"{task_id}*")
            if p.is_dir() and (p.name == task_id or p.name.startswith(task_id + "-"))
        )
        if len(existing) > 1:
            print(f"[suite_helper] 错误：存在多个同编号目录，请先人工核对：{existing}", file=sys.stderr)
            return 2
        task_dir = existing[0] if existing else (task_root / f"{task_id}-{summary}")
        task_id_label = task_id

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + run_summary + "-" + secrets.token_hex(3)
    run_dir = task_dir / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"[suite_helper] 错误：Run 目录已存在，禁止覆盖：{run_dir}", file=sys.stderr)
        return 2

    template_dir = root / ".agents" / "skills" / "kb-test-execution" / "assets"
    if not template_dir.is_dir():
        template_dir = DEFAULT_ROOT / ".agents" / "skills" / "kb-test-execution" / "assets"

    for name in ("plan.md", "execution.md", "result.md"):
        src = template_dir / name
        if not src.is_file():
            print(f"[suite_helper] 错误：缺少 Run 模板文件 {src}", file=sys.stderr)
            return 2
        content = src.read_text(encoding="utf-8")
        content = content.replace("{{TASK_ID}}", task_id_label).replace("{{RUN_ID}}", run_id)
        (run_dir / name).write_text(content, encoding="utf-8")

    for sub in ("logs", "screenshots", "artifacts"):
        (run_dir / sub).mkdir()

    git_commit, worktree_dirty = collect_git_info(root)
    started_at = format_local_timestamp()
    langfuse_env = "test" if args.env == "test" else "prd"

    report_data_rel: str | None = None
    if args.init_report_json:
        render_mod = load_render_module(root)
        skeleton = {
            "schemaVersion": render_mod.SCHEMA_VERSION,
            "isPlaceholderDemo": False,
            "meta": {
                "suiteId": "KB-SUITE-001",
                "taskId": task_id_label,
                "runId": run_id,
                "env": args.env,
                "langfuseEnv": langfuse_env,
                "startedAt": started_at,
                "gitCommit": git_commit,
                "worktreeDirty": worktree_dirty,
                "cleanupStatus": "unknown",
                "cleanupNote": "初始化骨架，待执行并填充实测结果后覆盖",
            },
            "cases": [],
            "envConfig": {
                "source": f"{args.env.upper()} 环境配置（待采集）",
                "primaryModel": "未采集",
                "fallbackModel": "未采集",
                "imageGenModel": "未采集",
                "visionFollowupModel": "未采集",
                "compactionThreshold": "未采集",
                "toolLimits": "未采集",
            },
            "notes": {
                "facts": [],
                "inferences": [],
                "gaps": [],
                "calibrations": [],
            },
        }
        render_mod.validate_payload(skeleton, "init-skeleton")
        report_file = run_dir / "artifacts" / "report-data.json"
        report_file.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_data_rel = str(report_file.relative_to(root))

    result = {
        "taskId": task_id_label,
        "runId": run_id,
        "env": args.env,
        "langfuseEnv": langfuse_env,
        "startedAt": started_at,
        "gitCommit": git_commit,
        "worktreeDirty": worktree_dirty,
        "runDirRelative": str(run_dir.relative_to(root)),
        "runDir": str(run_dir),
        "reportDataPath": report_data_rel,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_quality_gates(doc: dict, source_label: str, render_mod) -> list[str]:
    """对单份报告 JSON 执行三道门禁检查，返回问题描述列表（空列表表示通过）。"""
    errors: list[str] = []

    # Gate 1：Schema 结构校验（复用 render_suite_report.py）
    try:
        render_mod.validate_payload(doc, source_label)
    except render_mod.ValidationError as exc:
        errors.append(f"[Schema] {exc}")
        return errors

    # Gate 2：外发板块（aiSummary / envConfig）内部引用拦截 + 全文件凭据正则拦截
    for section_key in ("aiSummary", "envConfig"):
        section_val = doc.get(section_key)
        if section_val is not None:
            section_text = json.dumps(section_val, ensure_ascii=False)
            for token in BANNED_EXTERNAL_TOKENS:
                if token in section_text:
                    errors.append(
                        f"[外发脱敏][{source_label}] {section_key} 禁止包含工作区内部引用 {token!r}"
                    )

    full_text = json.dumps(doc, ensure_ascii=False)
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(full_text):
            errors.append(f"[凭据红线][{source_label}] 检测到疑似 {label}，禁止写入报告数据")

    # Gate 3：业务状态与枚举一致性校验
    meta = doc.get("meta") or {}
    env_val = meta.get("env")
    if env_val not in VALID_ENVS:
        errors.append(
            f"[状态一致性][{source_label}] meta.env 必须为小写 {sorted(VALID_ENVS)} 之一，实际为 {env_val!r}"
        )

    cleanup_status = meta.get("cleanupStatus")
    if cleanup_status is not None and cleanup_status not in VALID_CLEANUP_STATUSES:
        errors.append(
            f"[状态一致性][{source_label}] meta.cleanupStatus 无效：{cleanup_status!r}（仅允许 {sorted(VALID_CLEANUP_STATUSES)}）"
        )

    for case in doc.get("cases") or []:
        cid = case.get("id")
        cst = case.get("status")
        steps = case.get("steps") or []
        step_statuses = [s.get("status") for s in steps if isinstance(s, dict) and s.get("status") is not None]
        if cst == "passed" and any(st in {"failed", "blocked"} for st in step_statuses):
            errors.append(
                f"[状态一致性][{source_label}] {cid}.status='passed' 但 steps 存在 failed/blocked 步骤，逻辑矛盾"
            )
        if cst == "not_run" and any(st in {"passed", "failed", "blocked"} for st in step_statuses):
            errors.append(
                f"[状态一致性][{source_label}] {cid}.status='not_run' 但 steps 存在已执行结果，逻辑矛盾"
            )

    if doc.get("isPlaceholderDemo") is True:
        print(
            f"[WARN] [{source_label}] isPlaceholderDemo=true（仅适用于结构演示样例，不作为实测报告交付）",
            file=sys.stderr,
        )

    return errors


def cmd_check_and_render(args: argparse.Namespace) -> int:
    if not args.check_only and not args.out:
        print("[suite_helper] 错误：未设 --check-only 时必须提供 --out", file=sys.stderr)
        return 2

    try:
        render_mod = load_render_module(DEFAULT_ROOT)
    except Exception as exc:  # noqa: BLE001
        print(f"[suite_helper] 错误：{exc}", file=sys.stderr)
        return 2

    payloads: list[dict] = []
    all_errors: list[str] = []

    for raw_path in args.data:
        path = Path(raw_path)
        if not path.is_file():
            print(f"[suite_helper] 错误：找不到数据文件 {path}", file=sys.stderr)
            return 2
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            all_errors.append(f"[JSON解析][{path}] 第 {exc.lineno} 行解析失败：{exc.msg}")
            continue
        errs = run_quality_gates(doc, str(path), render_mod)
        if errs:
            all_errors.extend(errs)
        else:
            payloads.append(doc)

    if all_errors:
        print(f"[suite_helper] 门禁校验失败（共 {len(all_errors)} 项问题）：", file=sys.stderr)
        for item in all_errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    merged = render_mod.merge_payloads(payloads)
    cases = merged.get("cases") or []
    executed = sum(1 for c in cases if c.get("status") != "not_run")

    if args.check_only:
        print(
            f"[suite_helper] 三道门禁全部通过：{len(args.data)} 份输入，"
            f"合并后 {len(cases)} 条用例记录（已执行 {executed} 项）"
        )
        return 0

    tpl_path = Path(args.template) if args.template else render_mod.DEFAULT_TEMPLATE
    if not tpl_path.is_file():
        print(f"[suite_helper] 错误：找不到 HTML 模板 {tpl_path}", file=sys.stderr)
        return 2

    template_text = tpl_path.read_text(encoding="utf-8")
    try:
        rendered_html = render_mod.render_html(template_text, merged)
    except ValueError as exc:
        print(f"[suite_helper] 渲染失败：{exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered_html, encoding="utf-8")

    # 回读落盘 HTML 并校验内嵌 JSON 完整性
    written_text = out_path.read_text(encoding="utf-8")
    match = render_mod.SLOT_PATTERN.search(written_text)
    if not match:
        print(f"[suite_helper] 错误：落盘回读未找到报告数据槽位：{out_path}", file=sys.stderr)
        return 2
    try:
        embedded = json.loads(match.group(2))
        render_mod.validate_payload(embedded, f"{out_path}#embedded")
    except (json.JSONDecodeError, render_mod.ValidationError) as exc:
        print(f"[suite_helper] 错误：落盘 HTML 内嵌 JSON 校验失败：{exc}", file=sys.stderr)
        return 1

    print(
        f"[suite_helper] 门禁校验与 HTML 渲染成功：{out_path} "
        f"({out_path.stat().st_size} bytes, 用例={len(cases)}, 已执行={executed})"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suite_helper.py",
        description="KB-SUITE-001 回归执行辅助与报告门禁工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-run", help="按 AGENTS.md 规范创建独立 Run 目录与报告初始骨架")
    p_init.add_argument("--summary", required=True, help="任务/请求中文概要（1-40字，含中文，仅中英文数字连字符）")
    p_init.add_argument("--run-summary", help="本次 Run 中文概要（默认复用 --summary）")
    p_init.add_argument("--task-id", help="复用长期任务编号（如 TASK-001）；未传则为单次请求")
    p_init.add_argument("--env", default="preprod", choices=sorted(VALID_ENVS), help="目标环境（默认 preprod）")
    p_init.add_argument("--init-report-json", action="store_true", help="同时生成 artifacts/report-data.json 初始骨架")
    p_init.add_argument("--root", help="工作区根目录覆盖（用于隔离测试）")

    p_render = sub.add_parser("check-and-render", help="三道门禁校验并渲染/合并生成标准化 HTML 报告")
    p_render.add_argument("--data", action="append", required=True, help="report-data JSON 路径（可重复传入合并）")
    p_render.add_argument("--out", help="输出 HTML 路径（未设 --check-only 时必填）")
    p_render.add_argument("--template", help="HTML 模板路径覆盖")
    p_render.add_argument("--check-only", action="store_true", help="仅执行门禁校验，不写出 HTML 文件")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "init-run":
        return cmd_init_run(args)
    if args.command == "check-and-render":
        return cmd_check_and_render(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
