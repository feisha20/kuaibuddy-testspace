#!/usr/bin/env python3
"""Langfuse 轨迹抓取（Langfuse v4 events_only 模式）。

实测结论（2026-11-05，prd / test / dev 三环境一致）：
- 唯一可用读端点：GET /api/public/v2/observations
- 已 404 的端点：/api/public/traces、/api/public/observations、/api/public/v2/traces、
  /api/public/v2/observations/{id}、/api/public/otel/v1/*(GET)
- 分页用 meta.cursor，不是 page（page 参数被忽略，page=1 与 page=2 返回相同数据）
- run_id 可检索：filter=[{column:"metadata",key:"run_id",operator:"=",value:<run_id>,type:"stringObject"}]
- observations 列表不含 input/output/metadata/usage，只有结构/时间/状态/价格
"""
import argparse
import os
from local_config import load_local_config
load_local_config()
import json
import sys
import urllib.request
import urllib.error
import urllib.parse
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 避免中文/符号输出崩溃
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LANGFUSE_CONFIG = {env: {'url': os.environ.get(f"KB_LANGFUSE_{env.upper()}_URL", ""), 'public_key': os.environ.get(f"KB_LANGFUSE_{env.upper()}_PUBLIC_KEY", ""), 'secret_key': os.environ.get(f"KB_LANGFUSE_{env.upper()}_SECRET_KEY", "")} for env in ('prd', 'test', 'dev')}

V2_OBSERVATIONS_PATH = "/api/public/v2/observations"
V4_PAGE_LIMIT = 100
MAX_CURSOR_PAGES = 300
MAX_SESSION_TRACES = 20
V4_NOTE = "> 注：本脚本默认只整理 observations 的结构、时间和状态；未请求或未输出 input/output，不能据此断言服务不提供这些字段。"


def make_auth_header(cfg):
    token = base64.b64encode(f"{cfg['public_key']}:{cfg['secret_key']}".encode()).decode()
    return "Basic " + token


# 强制直连：urllib 默认读系统代理，本机代理软件不转发内网地址
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api_get(cfg, path, params=None):
    if not all(cfg.get(k) for k in ("url", "public_key", "secret_key")):
        raise SystemExit("缺少当前环境的 Langfuse 配置；请检查本机环境变量。")
    url = cfg["url"] + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": make_auth_header(cfg)})
    try:
        with OPENER.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        print(f"ERROR: HTTP {e.code} from Langfuse {path}: {body_text}")
        raise SystemExit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Cannot reach Langfuse at {cfg['url']}: {e.reason}")
        raise SystemExit(1)


def fetch_v4_observations(cfg, params):
    """按 cursor 翻页拉全量 observations。

    page 参数在 v2 端点被忽略（page=1 与 page=2 返回相同数据），必须用 meta.cursor。
    """
    all_data = []
    cursor = None
    seen_cursor = set()
    for _ in range(MAX_CURSOR_PAGES):
        p = {**params, "limit": V4_PAGE_LIMIT}
        if cursor:
            p["cursor"] = cursor
        result = api_get(cfg, V2_OBSERVATIONS_PATH, p)
        data = result.get("data") or []
        if not data:
            break
        all_data.extend(data)
        cursor = (result.get("meta") or {}).get("cursor")
        if not cursor:
            break
        if cursor in seen_cursor:
            print("WARN: cursor 重复出现，提前终止分页")
            break
        seen_cursor.add(cursor)
    return all_data


def normalize_ts(ts):
    # API 要求 ISO 带 Z（已带 Z 或时区偏移则原样）
    ts = ts.strip()
    return ts if ("Z" in ts or "+" in ts) else ts + "Z"


def default_v4_window():
    # 默认当天前后各放宽一天，避免边界漏数据
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start - timedelta(days=1), now + timedelta(days=1)


def run_id_filter(run_id):
    """构造 metadata.run_id 过滤条件（v2 端点实测生效）。"""
    return json.dumps([{
        "type": "stringObject",
        "key": "run_id",
        "operator": "=",
        "value": run_id,
        "column": "metadata",
    }])


def is_main_run_group(group):
    # 主 run：组内含 AGENT 根且 name 以 invoke_agent 开头
    return any(o.get("type") == "AGENT" and (o.get("name") or "").startswith("invoke_agent") for o in group)


def group_time_range(group):
    starts = [o.get("startTime", "") for o in group if o.get("startTime")]
    ends = [o.get("endTime", "") for o in group if o.get("endTime")]
    if not starts:
        return ("", "")
    return (min(starts), max(ends) if ends else "")


def format_observation(obs):
    lines = []
    name = obs.get("name", "unnamed")
    obs_type = obs.get("type", "UNKNOWN")
    start = obs.get("startTime", "")
    end = obs.get("endTime", "")
    status = obs.get("statusMessage") or ""
    level = obs.get("level", "")
    model = obs.get("model") or obs.get("modelId") or ""

    header = f"### [{obs_type}] {name}"
    if model:
        header += f" (model: {model})"
    if obs.get("isRootObservation"):
        header += " [root]"
    lines.append(header)
    lines.append(f"- 时间: {start} -> {end}")
    if obs.get("parentObservationId"):
        lines.append(f"- 父: {obs.get('parentObservationId')}")
    if level:
        lines.append(f"- 级别: {level}")
    if status:
        lines.append(f"- 状态: {status}")
    if obs.get("latency") is not None:
        lines.append(f"- 耗时: {obs.get('latency')}")
    if obs.get("timeToFirstToken") is not None:
        lines.append(f"- TTFT: {obs.get('timeToFirstToken')}")
    if obs.get("totalPrice") is not None:
        lines.append(f"- 价格: total={obs.get('totalPrice')} input={obs.get('inputPrice')} output={obs.get('outputPrice')}")
    return "\n".join(lines)


def format_v4_trace(trace_id, session_id, observations):
    # v4 无 trace 详情端点，用 observations 重建 trace 结构
    lines = [f"# Trace: {trace_id}", V4_NOTE, f"- sessionId: {session_id}"]
    rng = group_time_range(observations)
    if rng[0]:
        lines.append(f"- 时间范围: {rng[0]} -> {rng[1]}")
    types = {}
    for obs in observations:
        types[obs.get("type", "UNKNOWN")] = types.get(obs.get("type", "UNKNOWN"), 0) + 1
    if types:
        lines.append("- observation 类型统计: " + ", ".join(f"{k}={v}" for k, v in sorted(types.items())))
    lines.append(f"\n## Observations ({len(observations)})\n")
    for obs in sorted(observations, key=lambda o: o.get("startTime", "")):
        lines.append(format_observation(obs))
        lines.append("")
    return "\n".join(lines)


def write_trace_groups(groups, session_id, output_dir, prefix="langfuse_trace"):
    """按 traceId 分组落盘：主 run 一份明细，其余进 _side.md。"""
    main_groups = {tid: g for tid, g in groups.items() if is_main_run_group(g)}
    side_groups = {tid: g for tid, g in groups.items() if not is_main_run_group(g)}

    written_main = []
    for tid, g in sorted(main_groups.items(), key=lambda kv: group_time_range(kv[1])[0]):
        f = output_dir / f"{prefix}_{tid}.md"
        f.write_text(format_v4_trace(tid, session_id, g), encoding="utf-8")
        written_main.append((tid, g, f))
        print(f"Written: {f}")

    if not written_main:
        print("⚠ 未发现主 run（无 AGENT/invoke_agent 根），可能为旁路触发或时间窗/过滤条件未覆盖主 run")
    elif len(written_main) > 1:
        print(f"⚠ 共 {len(written_main)} 个主 run trace，已全部落盘，请按时间对齐锁定目标：")
        for tid, g, _ in written_main:
            rng = group_time_range(g)
            print(f"   - {tid}  {rng[0]} ~ {rng[1]}  ({len(g)} observations)")

    if side_groups:
        side_lines = [
            f"# Side traces (session: {session_id})\n",
            f"{V4_NOTE}\n",
            f"共 {len(side_groups)} 条旁路 trace（记忆提取/上下文压缩等子调用，非主分析对象）\n",
        ]
        for tid, g in sorted(side_groups.items(), key=lambda kv: group_time_range(kv[1])[0]):
            side_lines.append(format_v4_trace(tid, session_id, g))
            side_lines.append("\n---\n")
        side_file = output_dir / f"{prefix}_side.md"
        side_file.write_text("\n".join(side_lines), encoding="utf-8")
        print(f"Written: {side_file}")

    return written_main


def run_by_run_id(cfg, opts, output_dir):
    """按 run_id 检索：v2 observations 的 metadata.run_id 过滤（实测生效）。"""
    params = {"filter": run_id_filter(opts.run_id)}
    if opts.time_from:
        params["fromStartTime"] = normalize_ts(opts.time_from)
    if opts.time_to:
        params["toStartTime"] = normalize_ts(opts.time_to)

    print(f"v4 模式：run_id={opts.run_id}，"
          f"时间窗 {params.get('fromStartTime', '(不限)')} ~ {params.get('toStartTime', '(不限)')}")
    observations = fetch_v4_observations(cfg, params)
    if not observations:
        print("ERROR: 未命中任何 observations；请核对 runId，或放宽时间窗后重试")
        return 1
    print(f"Fetched {len(observations)} observations")

    groups = {}
    for obs in observations:
        groups.setdefault(obs.get("traceId", "unknown"), []).append(obs)
    sessions = sorted({o.get("sessionId", "") for o in observations if o.get("sessionId")})
    session_id = sessions[0] if sessions else ""
    if len(sessions) > 1:
        print(f"⚠ 命中多个 sessionId: {sessions}")

    # filter 命中的 observation 可能不含根 observation，按 traceId 补齐整条 trace
    for tid in list(groups):
        full = fetch_v4_observations(cfg, {"traceId": tid})
        if len(full) > len(groups[tid]):
            groups[tid] = full
        sessions = sessions or []
    if sessions:
        session_id = sessions[0]

    written_main = write_trace_groups(groups, session_id, output_dir,
                                      prefix=f"langfuse_runId_{opts.run_id}")
    return 0 if written_main else 1


def run_by_session_id(cfg, opts, output_dir):
    """按 sessionId + 时间窗检索。"""
    d_from, d_to = default_v4_window()
    time_from = normalize_ts(opts.time_from) if opts.time_from else d_from.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_to = normalize_ts(opts.time_to) if opts.time_to else d_to.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not opts.time_from or not opts.time_to:
        print(f"时间窗未全指定，未指定侧使用默认: {time_from} ~ {time_to}")

    print(f"v4 模式：sessionId={opts.session_id}，时间窗 {time_from} ~ {time_to}")
    observations = fetch_v4_observations(cfg, {
        "sessionId": opts.session_id,
        "fromStartTime": time_from,
        "toStartTime": time_to,
    })
    if not observations:
        print("ERROR: 时间窗内该 session 无 observations；请放宽 --time-from/--time-to 或核对 sessionId")
        return 1
    print(f"Fetched {len(observations)} observations")

    groups = {}
    for obs in observations:
        groups.setdefault(obs.get("traceId", "unknown"), []).append(obs)
    if len(groups) > MAX_SESSION_TRACES:
        print(f"共 {len(groups)} 条 trace，仅保留最近 {MAX_SESSION_TRACES} 条")
        keep = sorted(groups.items(), key=lambda kv: group_time_range(kv[1])[0])[-MAX_SESSION_TRACES:]
        groups = dict(keep)

    written_main = write_trace_groups(groups, opts.session_id, output_dir)
    return 0 if written_main else 1


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Langfuse trace data (v4 events_only：唯一读端点 /api/public/v2/observations)")
    parser.add_argument("--env", choices=["prd", "test", "dev"], required=True,
                        help="Environment: prd, test or dev (default: prd)")
    parser.add_argument("--run-id", help="run_id（走 metadata.run_id 过滤，实测 v2 端点生效）")
    parser.add_argument("--session-id", help="threadId/sessionId（配合 --time-from/--time-to）")
    parser.add_argument("--time-from", help="时间窗起点（ISO 带 Z）")
    parser.add_argument("--time-to", help="时间窗终点（ISO 带 Z）")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    opts = parser.parse_args()

    cfg = LANGFUSE_CONFIG[opts.env]
    output_dir = Path(opts.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Using Langfuse env: {opts.env} ({cfg['url']})")

    if opts.run_id and opts.session_id:
        parser.error("--run-id 与 --session-id 只能二选一")

    if opts.run_id:
        return run_by_run_id(cfg, opts, output_dir)
    if opts.session_id:
        return run_by_session_id(cfg, opts, output_dir)

    parser.error("需提供 --run-id 或 --session-id")


if __name__ == "__main__":
    raise SystemExit(main())
