#!/usr/bin/env python3
"""KB-SUITE-001 固定 HTML 回归报告渲染器与结构校验脚本（单 Markdown 真源驱动）。

用法示例：
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --check-suite
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --preview-suite --out .runtime/.../suite-view.html
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --data report-data.json --out .runtime/.../report.html
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --data run1.json --data run2.json --out merged-report.html
  python3 .agents/skills/kb-suite-runner/scripts/render_suite_report.py --data report-data.json --validate-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TEMPLATE = SKILL_DIR / "assets" / "kb-suite-001-report.html"
DEFAULT_SUITE = ROOT / "tests" / "cases" / "KB-SUITE-001.md"

SCHEMA_VERSION = "kb-suite-001-report.v1"
VALID_STATUSES = {"passed", "failed", "blocked", "not_run"}
REQUIRED_META_FIELDS = ("suiteId", "runId", "env")

KNOWN_DOMAIN_IDS = {
    "核心对话与缓存引擎": "core-chat",
    "长上下文与记忆底座": "memory-context",
    "运行治理与积分安全": "runtime-billing",
    "沙箱工程与联网工具": "sandbox-tools",
    "多模态与自动化执行": "multimodal-auto",
    "开放连接与个人资产": "open-assets",
}

SLOT_PATTERN = re.compile(
    r'(<script\s+id="kb-report-data"\s+type="application/json"\s*>)(.*?)(</script>)',
    flags=re.DOTALL,
)
CATALOG_SLOT_PATTERN = re.compile(
    r'(<script\s+id="kb-suite-catalog"\s+type="application/json"\s*>)(.*?)(</script>)',
    flags=re.DOTALL,
)

CLEANUP_SEVERITY = {"failed": 4, "partial": 3, "unknown": 2, "passed": 1, "not_needed": 0}


class ValidationError(ValueError):
    """测试集 Markdown 或报告数据格式不符合 KB-SUITE-001 / kb-suite-001-report.v1 规范。"""


def case_sort_key(case_id: str) -> tuple[int, str]:
    """按 CASE- 后的数值自然排序（例如 CASE-09 < CASE-10 < CASE-11）。"""
    m = re.match(r"^CASE-(\d+)$", str(case_id))
    return (int(m.group(1)) if m else 10**9, str(case_id))


def _strip_md_inline(text: str) -> str:
    """清理行内 Markdown 修饰（粗体/斜体/代码反引号）保留纯文本。"""
    cleaned = re.sub(r"`([^`]*)`", r"\1", text.strip())
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_domain_cell(raw_domain: str) -> tuple[str, str, str]:
    """解析『全称（简称）』能力域列，返回 (domainId, name, shortName)。"""
    text = _strip_md_inline(raw_domain)
    m = re.fullmatch(r"(.+?)[（(]([^()（）]+)[）)]", text)
    if m:
        name = m.group(1).strip()
        short_name = m.group(2).strip()
    else:
        name = text
        short_name = text
    dom_id = KNOWN_DOMAIN_IDS.get(name)
    if not dom_id:
        dom_id = f"domain-{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"
    return dom_id, name, short_name


def _extract_section_slice(md_text: str, heading_pattern: str, next_heading_level: int = 3) -> str:
    """截取指定标题到下一个同级或更高级标题之间的 Markdown 正文（忽略代码块内注释）。"""
    head_re = re.compile(heading_pattern)
    stop_re = re.compile(rf"^\s*#{{1,{next_heading_level}}}\s+")
    in_fence = False
    collecting = False
    out_lines: list[str] = []

    for line in md_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            if collecting:
                out_lines.append(line)
            continue
        if not in_fence:
            if not collecting:
                if head_re.match(line):
                    collecting = True
                continue
            if stop_re.match(line):
                break
        if collecting:
            out_lines.append(line)
    return "\n".join(out_lines)


def _split_case_sections(sec4_text: str) -> list[tuple[str, str, str]]:
    """从第 4 节拆出全部 CASE-xx 子章节（忽略代码块内 # 注释），返回 [(case_id, heading_title, body)]。"""
    case_head_re = re.compile(r"^###\s+(CASE-\d+)[：:]\s*(.+)$")
    in_fence = False
    results: list[tuple[str, str, list[str]]] = []
    current: tuple[str, str, list[str]] | None = None

    for line in sec4_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            if current is not None:
                current[2].append(line)
            continue
        if not in_fence:
            m = case_head_re.match(line)
            if m:
                if current is not None:
                    results.append(current)
                current = (m.group(1), m.group(2), [])
                continue
        if current is not None:
            current[2].append(line)

    if current is not None:
        results.append(current)
    return [(cid, title, "\n".join(lines)) for cid, title, lines in results]


def _parse_markdown_table(section_text: str, section_label: str) -> tuple[list[str], list[list[str]]]:
    """解析章节中的第一个 Markdown 表格，返回 (headers, rows)。"""
    lines = section_text.splitlines()
    table_lines: list[str] = []
    started = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("|") and "|" in stripped[1:]:
            started = True
            table_lines.append(stripped)
        elif started:
            break

    if len(table_lines) < 3:
        raise ValidationError(f"[{section_label}] 未找到有效的 Markdown 表格（至少需要表头、分隔行与 1 行数据）")

    def split_row(line: str) -> list[str]:
        inner = line.strip()
        if inner.startswith("|"):
            inner = inner[1:]
        if inner.endswith("|"):
            inner = inner[:-1]
        return [c.strip() for c in inner.split("|")]

    headers = split_row(table_lines[0])
    sep_cells = split_row(table_lines[1])
    if len(sep_cells) != len(headers) or not all(re.fullmatch(r":?-{3,}:?", c or "") for c in sep_cells):
        raise ValidationError(f"[{section_label}] 表格分隔行格式非法：{table_lines[1]}")

    rows: list[list[str]] = []
    for row_line in table_lines[2:]:
        cells = split_row(row_line)
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        elif len(cells) > len(headers):
            cells = cells[: len(headers)]
        rows.append(cells)
    return headers, rows


def _derive_case_short_label(
    explicit_short: str | None,
    title: str,
    tags: list[str],
    tag_meta_by_name: dict[str, dict],
) -> str:
    """推导 AI 摘要与索引展示用的精炼用例简称。"""
    if explicit_short:
        return explicit_short
    if len(tags) == 1 and tags[0] in tag_meta_by_name:
        return tag_meta_by_name[tags[0]]["label"]
    clean = re.sub(r"[（(][^()（）]*[）)]", "", title)
    clean = re.sub(r"验证$", "", clean).strip(" ：:—-")
    return clean[:14] if len(clean) > 14 else (clean or title)


def _extract_cmd_template(case_body: str, case_id: str, suite_rel: str) -> str:
    """从第 4 节 bash 代码块提取首条未注释的 kb_e2e.js ask 命令模板。"""
    for block in re.findall(r"```(?:bash|sh)?\s*\n(.*?)```", case_body, flags=re.S):
        joined = re.sub(r"\\\s*\n\s*", " ", block)
        for line in joined.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "kb_e2e.js ask" in s:
                s = re.sub(r"\s+", " ", s)
                m_prompt = re.search(r'(kb_e2e\.js ask\s+)(["\'])(.+?)\2', s)
                if m_prompt and len(m_prompt.group(3)) > 26:
                    short_prompt = m_prompt.group(3)[:24] + "..."
                    s = (
                        s[: m_prompt.start()]
                        + m_prompt.group(1)
                        + m_prompt.group(2)
                        + short_prompt
                        + m_prompt.group(2)
                        + s[m_prompt.end() :]
                    )
                return s
    return f"参照 {suite_rel} {case_id} 执行模板"


def parse_suite_catalog(suite_path: Path = DEFAULT_SUITE) -> dict:
    """从 KB-SUITE-001.md 自动解析能力域、标准化能力标签与测试用例目录。"""
    if not suite_path.is_file():
        raise ValidationError(f"找不到测试集文件：{suite_path}")

    text = suite_path.read_text(encoding="utf-8")
    try:
        suite_rel = str(suite_path.resolve().relative_to(ROOT))
    except ValueError:
        suite_rel = suite_path.name

    # 1. 解析 3.1 能力覆盖总览
    sec_31 = _extract_section_slice(text, r"^###\s+3\.1\b.*$", next_heading_level=3)
    h31, rows31 = _parse_markdown_table(sec_31, "3.1 能力覆盖总览")
    col_map_31 = {h: idx for idx, h in enumerate(h31)}
    for req_col in ("所属能力域", "能力标签", "已覆盖用例"):
        if req_col not in col_map_31:
            raise ValidationError(f"[3.1 能力覆盖总览] 缺少必填列 {req_col!r}，当前表头：{h31}")

    domains_by_id: dict[str, dict] = {}
    domain_order: list[str] = []
    tag_meta_by_name: dict[str, dict] = {}

    for r_idx, row in enumerate(rows31, 1):
        raw_domain = row[col_map_31["所属能力域"]]
        raw_tag = row[col_map_31["能力标签"]]
        raw_short = row[col_map_31["能力简称"]] if "能力简称" in col_map_31 else ""
        raw_desc = row[col_map_31["能力说明"]] if "能力说明" in col_map_31 else ""
        raw_cov = row[col_map_31["已覆盖用例"]]

        if not raw_domain.strip():
            raise ValidationError(f"[3.1 能力覆盖总览] 第 {r_idx} 行『所属能力域』为空")

        tag_m = re.search(r"#([a-z0-9][a-z0-9-]*)", raw_tag)
        if not tag_m:
            raise ValidationError(f"[3.1 能力覆盖总览] 第 {r_idx} 行未包含有效 #能力标签：{raw_tag!r}")
        tag_name = tag_m.group(1)
        if tag_name in tag_meta_by_name:
            raise ValidationError(f"[3.1 能力覆盖总览] 存在重复能力标签 #{tag_name}")

        dom_id, dom_name, dom_short = _parse_domain_cell(raw_domain)
        if dom_id not in domains_by_id:
            domains_by_id[dom_id] = {
                "id": dom_id,
                "name": dom_name,
                "shortName": dom_short,
                "tags": [],
            }
            domain_order.append(dom_id)

        covered_ids = re.findall(r"\b(CASE-\d+)\b", raw_cov)
        tag_label = _strip_md_inline(raw_short) or _strip_md_inline(raw_desc)[:12] or tag_name

        tag_entry = {
            "tag": tag_name,
            "label": tag_label,
            "caseId": covered_ids[0] if covered_ids else None,
        }
        domains_by_id[dom_id]["tags"].append(tag_entry)
        tag_meta_by_name[tag_name] = {
            "domainId": dom_id,
            "label": tag_label,
            "coveredCaseIds": covered_ids,
        }

    # 2. 解析 3.2 测试用例索引
    sec_32 = _extract_section_slice(text, r"^###\s+3\.2\b.*$", next_heading_level=2)
    h32, rows32 = _parse_markdown_table(sec_32, "3.2 测试用例索引")
    col_map_32 = {h: idx for idx, h in enumerate(h32)}
    for req_col in ("用例编号", "用例名称", "覆盖标签", "优先级"):
        if req_col not in col_map_32:
            raise ValidationError(f"[3.2 测试用例索引] 缺少必填列 {req_col!r}，当前表头：{h32}")

    index_cases: dict[str, dict] = {}
    for row in rows32:
        cid_m = re.search(r"\b(CASE-\d+)\b", row[col_map_32["用例编号"]])
        if not cid_m:
            continue  # 跳过 *后续扩展* 等说明行
        cid = cid_m.group(1)
        if cid in index_cases:
            raise ValidationError(f"[3.2 测试用例索引] 存在重复用例编号 {cid}")
        title = _strip_md_inline(row[col_map_32["用例名称"]])
        tags = re.findall(r"#([a-z0-9][a-z0-9-]*)", row[col_map_32["覆盖标签"]])
        if not tags:
            raise ValidationError(f"[3.2 测试用例索引] {cid} 未声明任何 #覆盖标签")
        priority = _strip_md_inline(row[col_map_32["优先级"]]) or "P1"
        index_cases[cid] = {
            "id": cid,
            "title": title,
            "tags": tags,
            "priority": priority,
        }

    if not index_cases:
        raise ValidationError("[3.2 测试用例索引] 未解析到任何 CASE-xx 用例记录")

    # 3. 解析第 4 节用例明细（目标、可选简称、执行命令模板）
    sec_4 = _extract_section_slice(text, r"^##\s+4\.\s+.*$", next_heading_level=2)
    section4_cases: dict[str, dict] = {}
    for cid, heading_title, body in _split_case_sections(sec_4):
        goal_m = re.search(r"^\s*-\s*\*\*测试目标\*\*[：:]\s*(.+)$", body, flags=re.M)
        goal = _strip_md_inline(goal_m.group(1)) if goal_m else _strip_md_inline(heading_title)

        short_m = re.search(r"^\s*-\s*\*\*简称\*\*[：:]\s*(.+)$", body, flags=re.M)
        explicit_short = _strip_md_inline(short_m.group(1)) if short_m else None

        section4_cases[cid] = {
            "goal": goal,
            "explicitShort": explicit_short,
            "cmdTemplate": _extract_cmd_template(body, cid, suite_rel),
        }

    # 4. 自洽交叉校验
    for tag_name, tmeta in tag_meta_by_name.items():
        for cov_cid in tmeta["coveredCaseIds"]:
            if cov_cid not in index_cases:
                raise ValidationError(
                    f"[交叉校验失败] 3.1 中 #{tag_name} 引用了 {cov_cid}，但 3.2 用例索引中不存在该编号"
                )

    catalog_cases: list[dict] = []
    for cid in sorted(index_cases, key=case_sort_key):
        idx_item = index_cases[cid]
        for t in idx_item["tags"]:
            if t not in tag_meta_by_name:
                raise ValidationError(
                    f"[交叉校验失败] 3.2 中 {cid} 声明了 #{t}，但 3.1 能力覆盖总览中未定义该标签"
                )
            covered_list = tag_meta_by_name[t]["coveredCaseIds"]
            if covered_list and cid not in covered_list:
                raise ValidationError(
                    f"[交叉校验失败] 3.2 中 {cid} 关联 #{t}，但 3.1 将该标签标注为由 {covered_list} 覆盖"
                )

        if cid not in section4_cases:
            raise ValidationError(f"[交叉校验失败] 3.2 中的 {cid} 在第 4 节缺少对应 '### {cid}：...' 明细小节")

        sec4_item = section4_cases[cid]
        first_domain_id = tag_meta_by_name[idx_item["tags"][0]]["domainId"]
        catalog_cases.append(
            {
                "id": cid,
                "title": idx_item["title"],
                "shortLabel": _derive_case_short_label(
                    sec4_item["explicitShort"],
                    idx_item["title"],
                    idx_item["tags"],
                    tag_meta_by_name,
                ),
                "priority": idx_item["priority"],
                "domainId": first_domain_id,
                "tags": idx_item["tags"],
                "goal": sec4_item["goal"],
                "cmdTemplate": sec4_item["cmdTemplate"],
            }
        )

    return {
        "suiteId": "KB-SUITE-001",
        "source": suite_rel,
        "domains": [domains_by_id[did] for did in domain_order],
        "cases": catalog_cases,
    }


def validate_payload(data: object, source_label: str = "input", catalog: dict | None = None) -> dict:
    """校验单份 report-data.json 是否满足 schemaVersion 与动态目录约束。"""
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

    active_catalog = catalog if catalog is not None else parse_suite_catalog(DEFAULT_SUITE)
    valid_case_ids = {c["id"] for c in active_catalog["cases"]}

    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValidationError(f"[{source_label}] cases 必须是数组")

    seen_ids: set[str] = set()
    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValidationError(f"[{source_label}] cases[{idx}] 必须是对象")
        cid = case.get("id")
        if cid not in valid_case_ids:
            ordered_sample = sorted(valid_case_ids, key=case_sort_key)
            raise ValidationError(
                f"[{source_label}] cases[{idx}].id 无效: {cid!r}（当前测试集允许 {ordered_sample}）"
            )
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

    ai_summary = data.get("aiSummary")
    if ai_summary is not None:
        if not isinstance(ai_summary, dict):
            raise ValidationError(f"[{source_label}] aiSummary 必须是对象")
        for s_field in ("source", "headline", "recommendation"):
            val = ai_summary.get(s_field)
            if val is not None and not isinstance(val, str):
                raise ValidationError(f"[{source_label}] aiSummary.{s_field} 必须是字符串")
        highlights = ai_summary.get("highlights")
        if highlights is not None:
            if not isinstance(highlights, list) or not all(isinstance(item, str) for item in highlights):
                raise ValidationError(f"[{source_label}] aiSummary.highlights 必须是字符串数组")
        sections = ai_summary.get("sections")
        if sections is not None:
            if not isinstance(sections, list):
                raise ValidationError(f"[{source_label}] aiSummary.sections 必须是数组")
            for sec_idx, sec in enumerate(sections):
                if not isinstance(sec, dict):
                    raise ValidationError(f"[{source_label}] aiSummary.sections[{sec_idx}] 必须是对象")
                if not isinstance(sec.get("title"), str) or not sec["title"].strip():
                    raise ValidationError(f"[{source_label}] aiSummary.sections[{sec_idx}].title 必须是非空字符串")
                sec_items = sec.get("items")
                if not isinstance(sec_items, list) or not all(isinstance(it, str) for it in sec_items):
                    raise ValidationError(f"[{source_label}] aiSummary.sections[{sec_idx}].items 必须是字符串数组")

    env_cfg = data.get("envConfig")
    if env_cfg is not None:
        if not isinstance(env_cfg, dict):
            raise ValidationError(f"[{source_label}] envConfig 必须是对象")
        for c_field in (
            "source",
            "primaryModel",
            "fallbackModel",
            "imageGenModel",
            "visionFollowupModel",
            "compactionThreshold",
            "toolLimits",
        ):
            c_val = env_cfg.get(c_field)
            if c_val is not None and not isinstance(c_val, str):
                raise ValidationError(f"[{source_label}] envConfig.{c_field} 必须是字符串")
        extra_items = env_cfg.get("extraItems")
        if extra_items is not None:
            if not isinstance(extra_items, list):
                raise ValidationError(f"[{source_label}] envConfig.extraItems 必须是数组")
            for ex_idx, ex in enumerate(extra_items):
                if not isinstance(ex, dict):
                    raise ValidationError(f"[{source_label}] envConfig.extraItems[{ex_idx}] 必须是对象")
                if not isinstance(ex.get("label"), str) or not ex["label"].strip():
                    raise ValidationError(f"[{source_label}] envConfig.extraItems[{ex_idx}].label 必须是非空字符串")
                if not isinstance(ex.get("value"), str):
                    raise ValidationError(f"[{source_label}] envConfig.extraItems[{ex_idx}].value 必须是字符串")

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
    total_duration = 0
    has_duration = False
    models_seen: list[str] = []
    cleanup_notes_seen: list[str] = []
    worst_cleanup: str | None = None
    merged_env_cfg: dict = {}
    extra_items_by_label: dict[str, dict] = {}

    for p in payloads:
        m = p.get("meta") or {}
        for k, v in m.items():
            if v not in (None, ""):
                merged_meta[k] = v
        if isinstance(m.get("pointsConsumed"), (int, float)):
            total_points += float(m["pointsConsumed"])
            has_points = True
        if isinstance(m.get("durationMs"), (int, float)):
            total_duration += int(m["durationMs"])
            has_duration = True
        ms = str(m.get("modelSummary") or "").strip()
        if ms and ms not in models_seen:
            models_seen.append(ms)
        cs = str(m.get("cleanupStatus") or "").strip()
        if cs and (worst_cleanup is None or CLEANUP_SEVERITY.get(cs, 2) > CLEANUP_SEVERITY.get(worst_cleanup, 2)):
            worst_cleanup = cs
        cn = str(m.get("cleanupNote") or "").strip()
        if cn and cn not in cleanup_notes_seen:
            cleanup_notes_seen.append(cn)

        cfg = p.get("envConfig")
        if isinstance(cfg, dict):
            for ck, cv in cfg.items():
                if ck == "extraItems" and isinstance(cv, list):
                    for ex in cv:
                        if isinstance(ex, dict) and ex.get("label"):
                            extra_items_by_label[ex["label"]] = ex
                elif cv not in (None, ""):
                    merged_env_cfg[ck] = cv

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
    merged_meta.pop("pointsBefore", None)
    merged_meta.pop("pointsAfter", None)
    if has_duration:
        merged_meta["durationMs"] = total_duration
    if models_seen:
        merged_meta["modelSummary"] = " / ".join(models_seen)
    if worst_cleanup:
        merged_meta["cleanupStatus"] = worst_cleanup
    if cleanup_notes_seen:
        merged_meta["cleanupNote"] = "；".join(cleanup_notes_seen)

    if extra_items_by_label:
        merged_env_cfg["extraItems"] = list(extra_items_by_label.values())

    ordered_cases = [cases_by_id[cid] for cid in sorted(cases_by_id, key=case_sort_key)]
    # 多份 Run 合并后不沿用单份 aiSummary，交由前端根据合并全集自动重新归纳
    out = {
        "schemaVersion": SCHEMA_VERSION,
        "isPlaceholderDemo": all(bool(p.get("isPlaceholderDemo")) for p in payloads),
        "meta": merged_meta,
        "cases": ordered_cases,
        "notes": notes_merged,
    }
    if merged_env_cfg:
        out["envConfig"] = merged_env_cfg
    return out


def inject_catalog_only(template_text: str, catalog: dict) -> str:
    """仅将目录快照写入固定模板的 <script id="kb-suite-catalog"> 槽位。"""
    if not CATALOG_SLOT_PATTERN.search(template_text):
        raise ValueError('模板缺少 <script id="kb-suite-catalog" type="application/json"> 注入槽位')
    cat_serialized = json.dumps(catalog, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return CATALOG_SLOT_PATTERN.sub(lambda m: f"{m.group(1)}{cat_serialized}{m.group(3)}", template_text, count=1)


def render_html(template_text: str, data: dict, catalog: dict | None = None) -> str:
    """将测试集目录与校验后的运行数据安全写入固定 HTML 模板双槽位。"""
    active_catalog = catalog if catalog is not None else parse_suite_catalog(DEFAULT_SUITE)
    if not CATALOG_SLOT_PATTERN.search(template_text):
        raise ValueError('模板缺少 <script id="kb-suite-catalog" type="application/json"> 注入槽位')
    if not SLOT_PATTERN.search(template_text):
        raise ValueError('模板缺少 <script id="kb-report-data" type="application/json"> 注入槽位')
    html = inject_catalog_only(template_text, active_catalog)
    serialized = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return SLOT_PATTERN.sub(lambda m: f"{m.group(1)}{serialized}{m.group(3)}", html, count=1)


def build_suite_preview_payload(catalog: dict) -> dict:
    """基于解析后的 Markdown 测试集目录构造 0 已执行用例浏览视图数据。"""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "isPlaceholderDemo": False,
        "meta": {
            "suiteId": catalog.get("suiteId") or "KB-SUITE-001",
            "taskId": "无（测试集目录视图）",
            "runId": "SUITE-CATALOG-VIEW",
            "env": "preprod",
            "langfuseEnv": "prd",
            "cleanupStatus": "not_needed",
            "cleanupNote": "测试集目录浏览视图（尚无运行数据）",
        },
        "cases": [],
        "notes": {
            "facts": [f"目录自动解析自 {catalog.get('source', 'KB-SUITE-001.md')}"],
            "inferences": [],
            "gaps": [],
            "calibrations": [],
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KB-SUITE-001 固定 HTML 报告渲染与单真源目录校验工具")
    parser.add_argument(
        "--suite",
        default=str(DEFAULT_SUITE),
        help=f"测试集 Markdown 真源路径（默认：{DEFAULT_SUITE.relative_to(ROOT)}）",
    )
    parser.add_argument(
        "--data",
        action="append",
        help="report-data JSON 文件路径（可多次传入并按用例 ID 自动合并）",
    )
    parser.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE),
        help=f"HTML 固定模板路径（默认：{DEFAULT_TEMPLATE.relative_to(ROOT)}）",
    )
    parser.add_argument(
        "--out",
        help="输出独立 HTML 报告路径",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="仅校验 JSON 数据格式与测试集自洽性，不写 HTML 输出文件",
    )
    parser.add_argument(
        "--check-suite",
        action="store_true",
        help="仅解析并校验 Markdown 测试集自洽性，无需传入 --data",
    )
    parser.add_argument(
        "--preview-suite",
        action="store_true",
        help="直接基于 Markdown 测试集生成 0 已执行用例的交互式浏览 HTML（需搭配 --out）",
    )
    parser.add_argument(
        "--sync-template",
        action="store_true",
        help="仅将当前 Markdown 测试集目录同步写入 HTML 模板的默认 <script id=\"kb-suite-catalog\"> 槽位",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    suite_path = Path(args.suite)
    try:
        catalog = parse_suite_catalog(suite_path)
    except ValidationError as exc:
        print(f"[render_suite_report] 测试集解析/校验失败：{exc}", file=sys.stderr)
        return 1

    tag_count = sum(len(d["tags"]) for d in catalog["domains"])

    if args.check_suite:
        print(
            f"[render_suite_report] 测试集自洽校验通过（{catalog['source']}）："
            f"{len(catalog['domains'])} 个能力域、{len(catalog['cases'])} 个用例、{tag_count} 项能力标签"
        )
        return 0

    if args.sync_template:
        tpl_path = Path(args.template)
        if not tpl_path.is_file():
            print(f"[render_suite_report] 错误：找不到模板文件 {tpl_path}", file=sys.stderr)
            return 2
        try:
            updated = inject_catalog_only(tpl_path.read_text(encoding="utf-8"), catalog)
        except ValueError as exc:
            print(f"[render_suite_report] 同步失败：{exc}", file=sys.stderr)
            return 2
        tpl_path.write_text(updated, encoding="utf-8")
        print(
            f"[render_suite_report] 已同步模板默认目录：{tpl_path} "
            f"({len(catalog['domains'])} 域 / {len(catalog['cases'])} 用例 / {tag_count} 标签)"
        )
        return 0

    if args.preview_suite:
        if not args.out:
            print("[render_suite_report] 错误：--preview-suite 模式下必须提供 --out", file=sys.stderr)
            return 2
        tpl_path = Path(args.template)
        if not tpl_path.is_file():
            print(f"[render_suite_report] 错误：找不到模板文件 {tpl_path}", file=sys.stderr)
            return 2
        preview_payload = validate_payload(build_suite_preview_payload(catalog), "preview-suite", catalog=catalog)
        try:
            rendered = render_html(tpl_path.read_text(encoding="utf-8"), preview_payload, catalog=catalog)
        except ValueError as exc:
            print(f"[render_suite_report] 渲染失败：{exc}", file=sys.stderr)
            return 2
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(
            f"[render_suite_report] 已生成测试集浏览报告：{out_path} "
            f"({len(catalog['cases'])} 用例 / {tag_count} 标签, {len(rendered)} chars)"
        )
        return 0

    if not args.data:
        print("[render_suite_report] 错误：必须提供 --data（或改用 --check-suite / --preview-suite / --sync-template）", file=sys.stderr)
        return 2
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
            payloads.append(validate_payload(doc, str(path), catalog=catalog))
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
        rendered = render_html(tpl_path.read_text(encoding="utf-8"), merged, catalog=catalog)
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
