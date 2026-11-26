#!/usr/bin/env python3
"""KB-SUITE-001 固定 HTML 回归报告模板渲染器与结构校验脚本。

用法示例：
  python3 tests/scripts/render_suite_report.py --data report-data.json --out .runtime/.../report.html
  python3 tests/scripts/render_suite_report.py --data run1.json --data run2.json --out merged-report.html
  python3 tests/scripts/render_suite_report.py --data report-data.json --validate-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = ROOT / "tests" / "templates" / "kb-suite-001-report.html"

SCHEMA_VERSION = "kb-suite-001-report.v1"
VALID_CASE_IDS = {f"CASE-{i:02d}" for i in range(1, 11)}
VALID_STATUSES = {"passed", "failed", "blocked", "not_run"}
REQUIRED_META_FIELDS = ("suiteId", "runId", "env")

SLOT_PATTERN = re.compile(
    r'(<script\s+id="kb-report-data"\s+type="application/json"\s*>)(.*?)(</script>)',
    flags=re.DOTALL,
)


class ValidationError(ValueError):
    """报告数据格式不符合 kb-suite-001-report.v1 规范。"""


def validate_payload(data: object, source_label: str = "input") -> dict:
    """校验单份 report-data.json 是否满足 schemaVersion 与字段约束。"""
    if not isinstance(data, dict):
        raise ValidationError(f"[{source_label}] 根节点必须是 JSON 对象")
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValidationError(
            f"[{source_label}] schemaVersion 必须为 {SCHEMA_VERSION!r}，实际为 {data.get('schemaVersion')!r}"
        )

    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ValidationError(f"[{source_label}] meta 必须是对象")
    for field in REQUIRED_META_FIELDS:
        val = meta.get(field)
        if not isinstance(val, str) or not val.strip():
            raise ValidationError(f"[{source_label}] meta.{field} 必须是非空字符串")

    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValidationError(f"[{source_label}] cases 必须是数组")

    seen_ids: set[str] = set()
    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValidationError(f"[{source_label}] cases[{idx}] 必须是对象")
        cid = case.get("id")
        if cid not in VALID_CASE_IDS:
            raise ValidationError(f"[{source_label}] cases[{idx}].id 无效: {cid!r}（仅允许 CASE-01..CASE-10）")
        if cid in seen_ids:
            raise ValidationError(f"[{source_label}] cases 中存在重复用例 ID: {cid}")
        seen_ids.add(cid)

        st = case.get("status")
        if st not in VALID_STATUSES:
            raise ValidationError(
                f"[{source_label}] {cid}.status 无效: {st!r}（仅允许 {sorted(VALID_STATUSES)}）"
            )

        steps = case.get("steps")
        if steps is not None:
            if not isinstance(steps, list):
                raise ValidationError(f"[{source_label}] {cid}.steps 必须是数组")
            for s_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    raise ValidationError(f"[{source_label}] {cid}.steps[{s_idx}] 必须是对象")
                sst = step.get("status")
                if sst is not None and sst not in VALID_STATUSES:
                    raise ValidationError(f"[{source_label}] {cid}.steps[{s_idx}].status 无效: {sst!r}")

    return data


def merge_payloads(payloads: list[dict]) -> dict:
    """将多份校验通过的报告 JSON 合并为统一视角；同一 Case 后传入覆盖先传入。"""
    if len(payloads) == 1:
        merged = json.loads(json.dumps(payloads[0], ensure_ascii=False))
        merged.setdefault("isPlaceholderDemo", False)
        return merged

    merged_meta: dict = {}
    cases_by_id: dict[str, dict] = {}
    notes_merged: dict[str, list[str]] = {
        "facts": [],
        "inferences": [],
        "gaps": [],
        "calibrations": [],
    }
    total_points = 0.0
    has_points = False

    for p in payloads:
        m = p.get("meta") or {}
        for k, v in m.items():
            if v not in (None, ""):
                merged_meta[k] = v
        if isinstance(m.get("pointsConsumed"), (int, float)):
            total_points += float(m["pointsConsumed"])
            has_points = True
        for c in p.get("cases") or []:
            cases_by_id[c["id"]] = c
        notes = p.get("notes") or {}
        for nk in notes_merged:
            for line in notes.get(nk) or []:
                if isinstance(line, str) and line not in notes_merged[nk]:
                    notes_merged[nk].append(line)

    merged_meta["runId"] = " + ".join(
        dict.fromkeys(str((p.get("meta") or {}).get("runId") or "") for p in payloads if (p.get("meta") or {}).get("runId"))
    )
    if has_points:
        merged_meta["pointsConsumed"] = round(total_points, 4)

    ordered_cases = [cases_by_id[cid] for cid in sorted(cases_by_id)]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "isPlaceholderDemo": all(bool(p.get("isPlaceholderDemo")) for p in payloads),
        "meta": merged_meta,
        "cases": ordered_cases,
        "notes": notes_merged,
    }


def render_html(template_text: str, data: dict) -> str:
    """将校验后的 JSON 安全写入固定模板的 <script id="kb-report-data"> 槽位。"""
    if not SLOT_PATTERN.search(template_text):
        raise ValueError('模板缺少 <script id="kb-report-data" type="application/json"> 注入槽位')
    serialized = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return SLOT_PATTERN.sub(lambda m: f"{m.group(1)}{serialized}{m.group(3)}", template_text, count=1)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KB-SUITE-001 固定 HTML 报告渲染与校验工具")
    parser.add_argument(
        "--data",
        action="append",
        required=True,
        help="report-data JSON 文件路径（可多次传入并按用例 ID 自动合并）",
    )
    parser.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE),
        help=f"HTML 固定模板路径（默认：{DEFAULT_TEMPLATE.relative_to(ROOT)}）",
    )
    parser.add_argument(
        "--out",
        help="输出独立 HTML 报告路径（未设 --validate-only 时必填）",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="仅校验 JSON 数据格式，不写 HTML 输出文件",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not args.validate_only and not args.out:
        print("[render_suite_report] 错误：非 --validate-only 模式下必须提供 --out", file=sys.stderr)
        return 2

    payloads: list[dict] = []
    for raw_path in args.data:
        path = Path(raw_path)
        if not path.is_file():
            print(f"[render_suite_report] 错误：找不到数据文件 {path}", file=sys.stderr)
            return 2
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            payloads.append(validate_payload(doc, str(path)))
        except (json.JSONDecodeError, ValidationError) as exc:
            print(f"[render_suite_report] 校验失败：{exc}", file=sys.stderr)
            return 1

    merged = merge_payloads(payloads)
    executed = sum(1 for c in merged["cases"] if c.get("status") != "not_run")
    print(f"[render_suite_report] 校验通过：共 {len(merged['cases'])} 条用例记录（已执行 {executed} 项）")

    if args.validate_only:
        return 0

    tpl_path = Path(args.template)
    if not tpl_path.is_file():
        print(f"[render_suite_report] 错误：找不到模板文件 {tpl_path}", file=sys.stderr)
        return 2

    try:
        rendered = render_html(tpl_path.read_text(encoding="utf-8"), merged)
    except ValueError as exc:
        print(f"[render_suite_report] 渲染失败：{exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"[render_suite_report] 已生成报告：{out_path} ({len(rendered)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
