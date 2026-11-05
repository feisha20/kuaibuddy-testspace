#!/usr/bin/env python3
"""跨环境探测 runId / sessionId 在 Langfuse 中的落点。

实测（2026-11-05）：prd / test / dev 三环境均为 Langfuse v4 events_only，
唯一读端点 /api/public/v2/observations，run_id 通过 metadata.run_id 过滤检索。
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from langfuse_fetch import (LANGFUSE_CONFIG, api_get, fetch_v4_observations,
                            normalize_ts, run_id_filter)

# Windows 控制台默认 GBK，强制 UTF-8 避免中文/符号输出崩溃
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 探测顺序：prd 优先，dev 复用 test 实例
ENV_ORDER = ["prd", "test", "dev"]


def default_probe_window():
    # 默认近 7 天
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"), (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def probe_env_by_run_id(env, run_id, time_from=None, time_to=None):
    """按 run_id 过滤 observations，归组出 trace。"""
    cfg = LANGFUSE_CONFIG[env]
    params = {"filter": run_id_filter(run_id)}
    if time_from:
        params["fromStartTime"] = time_from
    if time_to:
        params["toStartTime"] = time_to
    try:
        observations = fetch_v4_observations(cfg, params)
    except SystemExit:
        return {"reachable": False}

    groups = {}
    for obs in observations:
        groups.setdefault(obs.get("traceId", ""), []).append(obs)

    traces = []
    for tid, g in groups.items():
        roots = [o for o in g if o.get("isRootObservation")]
        root = roots[0] if roots else None
        sessions = sorted({o.get("sessionId", "") for o in g if o.get("sessionId")})
        traces.append({
            "id": tid,
            "name": (root or {}).get("name", ""),
            "sessionId": sessions[0] if sessions else "",
            "timestamp": min(o.get("startTime", "") for o in g),
            "endTime": max(o.get("endTime", "") for o in g),
            "observations": len(g),
            "main": bool(root) and root.get("type") == "AGENT" and (root.get("name") or "").startswith("invoke_agent"),
        })
    traces.sort(key=lambda t: t["timestamp"])
    return {"reachable": True, "hit": bool(traces), "count": len(traces), "traces": traces}


def probe_env_by_session(env, session_id, time_from, time_to):
    """按 sessionId + 时间窗列根 trace。"""
    cfg = LANGFUSE_CONFIG[env]
    params = {"sessionId": session_id, "fromStartTime": time_from, "toStartTime": time_to}
    try:
        observations = fetch_v4_observations(cfg, params)
    except SystemExit:
        return {"reachable": False}

    groups = {}
    for obs in observations:
        groups.setdefault(obs.get("traceId", ""), []).append(obs)

    traces = []
    for tid, g in groups.items():
        roots = [o for o in g if o.get("isRootObservation")]
        root = roots[0] if roots else None
        traces.append({
            "id": tid,
            "name": (root or {}).get("name", ""),
            "sessionId": session_id,
            "timestamp": min(o.get("startTime", "") for o in g),
            "endTime": max(o.get("endTime", "") for o in g),
            "observations": len(g),
            "main": bool(root) and root.get("type") == "AGENT" and (root.get("name") or "").startswith("invoke_agent"),
        })
    traces.sort(key=lambda t: t["timestamp"])
    return {"reachable": True, "hit": bool(traces), "count": len(traces), "traces": traces}


def print_result(env, r):
    if not r.get("reachable"):
        print(f"- {env}: [DOWN] 不可达")
    elif not r.get("hit"):
        print(f"- {env}: [MISS] 未命中")
    else:
        mains = [t for t in r["traces"] if t["main"]]
        sides = [t for t in r["traces"] if not t["main"]]
        print(f"- {env}: [HIT] 共 {r['count']} 条 trace（主run {len(mains)}，旁路 {len(sides)}）")
        for t in r["traces"]:
            tag = "主run" if t["main"] else "旁路"
            print(f"         {t['id']} ({t['name']}) [{tag}] obs={t['observations']} ts={t['timestamp']}~{t['endTime']}")
        if mains:
            print(f"         Langfuse: {LANGFUSE_CONFIG[env]['url']}/trace/{mains[0]['id']}")


def main():
    parser = argparse.ArgumentParser(
        description="Probe a runId/sessionId across Langfuse envs (v4 events_only：/api/public/v2/observations)")
    parser.add_argument("--run-id", help="runId（走 metadata.run_id 过滤）")
    parser.add_argument("--session-id", help="threadId/sessionId（配合时间窗）")
    parser.add_argument("--time-from", help="时间窗起点（ISO 带 Z，默认近 7 天）")
    parser.add_argument("--time-to", help="时间窗终点（ISO 带 Z）")
    parser.add_argument("--env", choices=["prd", "test", "dev"], required=True,
                        help="只查询明确指定的环境")
    opts = parser.parse_args()
    if not all(LANGFUSE_CONFIG[opts.env].get(k) for k in ("url", "public_key", "secret_key")):
        parser.error("缺少当前环境的 Langfuse 配置；请检查本机环境变量。")

    if not opts.run_id and not opts.session_id:
        parser.error("需提供 --run-id 或 --session-id")

    envs = ENV_ORDER if opts.env == "all" else [opts.env]
    hits = []

    if opts.run_id:
        print(f"Probing runId: {opts.run_id}  envs: {envs}")
        for env in envs:
            r = probe_env_by_run_id(env, opts.run_id, opts.time_from, opts.time_to)
            print_result(env, r)
            if r.get("reachable") and r.get("hit"):
                hits.append((env, r))
    else:
        d_from, d_to = default_probe_window()
        time_from = normalize_ts(opts.time_from) if opts.time_from else d_from
        time_to = normalize_ts(opts.time_to) if opts.time_to else d_to
        if not opts.time_from or not opts.time_to:
            print(f"时间窗未全指定，未指定侧使用默认: {time_from} ~ {time_to}")
        print(f"Probing sessionId: {opts.session_id}  envs: {envs}")
        print(f"时间窗: {time_from} ~ {time_to}")
        for env in envs:
            r = probe_env_by_session(env, opts.session_id, time_from, time_to)
            print_result(env, r)
            if r.get("reachable") and r.get("hit"):
                hits.append((env, r))

    print("---")
    if not hits:
        print("结论：所有环境均未命中；请核对 runId/sessionId，或放宽时间窗后重试")
        return 1
    env, r = hits[0]
    mains = [t for t in r["traces"] if t["main"]]
    note = "（dev 复用 test 实例，二者同源）" if env == "dev" else ""
    print(f"结论：命中环境 = {env}{note}")
    if opts.run_id:
        print(f"      runId     = {opts.run_id}")
    else:
        print(f"      sessionId = {opts.session_id}")
    print(f"      根 trace  = {r['count']} 条（主run {len(mains)}）")
    if len(mains) > 1:
        print("      ⚠ 多个主 run trace，请按时间对齐锁定目标（langfuse_fetch 会全部落盘并列清单）")
    elif not mains:
        print("      ⚠ 无主 run（仅旁路），确认时间窗是否覆盖主 run")
    print(f"后续 langfuse_fetch / elk_search 请使用 --env {env}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
