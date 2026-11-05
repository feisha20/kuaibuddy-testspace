#!/usr/bin/env python3
import argparse
import os
from local_config import load_local_config
load_local_config()
import json
import urllib.request
import urllib.error
import base64
from pathlib import Path
from datetime import datetime, timezone

ES_CONFIG = {env: {'url': os.environ.get(f"KB_ELK_{env.upper()}_URL", ""), 'user': os.environ.get(f"KB_ELK_{env.upper()}_USER", ""), 'password': os.environ.get(f"KB_ELK_{env.upper()}_PASSWORD", ""), 'index': os.environ.get(f"KB_ELK_{env.upper()}_INDEX", "")} for env in ('prd', 'test', 'dev')}


def make_auth_header(cfg):
    token = base64.b64encode(f"{cfg['user']}:{cfg['password']}".encode()).decode()
    return "Basic " + token


# 强制直连：urllib 默认读系统代理，本机代理软件不转发内网地址
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def es_search(cfg, body):
    url = f"{cfg['url']}/{cfg['index']}/_search"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": make_auth_header(cfg), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with OPENER.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        print(f"ERROR: HTTP {e.code} from ES: {body_text}")
        raise SystemExit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Cannot reach ES at {cfg['url']}: {e.reason}")
        raise SystemExit(1)


def build_query(keywords, mode, time_from, time_to, logger=None, level=None):
    must_clauses = []
    if time_from or time_to:
        time_range = {}
        if time_from:
            time_range["gte"] = time_from
        if time_to:
            time_range["lte"] = time_to
        must_clauses.append({"range": {"@timestamp": time_range}})

    # 框架层日志（io.agentscope.*）不带 runId/threadId，按 logger 前缀 + level 过滤
    if logger:
        must_clauses.append({"wildcard": {"logger.keyword": logger + "*"}})
    if level:
        must_clauses.append({"match_phrase": {"loglevel": level}})

    if keywords:
        if mode == "and":
            for kw in keywords:
                must_clauses.append({"match_phrase": {"message": kw}})
        else:
            should = [{"match_phrase": {"message": kw}} for kw in keywords]
            must_clauses.append({"bool": {"should": should, "minimum_should_match": 1}})

    return {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}


def fetch_logs(cfg, keywords, mode, time_from, time_to, max_lines, logger=None, level=None):
    query = build_query(keywords, mode, time_from, time_to, logger, level)
    body = {
        "query": query,
        "size": min(max_lines, 500),
        "sort": [{"@timestamp": "asc"}],
        "_source": ["@timestamp", "message"],
    }

    all_hits = []
    total_count = 0
    while len(all_hits) < max_lines:
        remaining = max_lines - len(all_hits)
        body["size"] = min(remaining, 500)
        result = es_search(cfg, body)
        if not total_count:
            total_raw = result.get("hits", {}).get("total", 0)
            total_count = total_raw.get("value", 0) if isinstance(total_raw, dict) else int(total_raw)
            print(f"Total matching: {total_count}, fetching up to {max_lines}")
        hits = result.get("hits", {}).get("hits", [])
        if not hits:
            break
        all_hits.extend(hits)
        if len(hits) < body["size"]:
            break
        last_sort = hits[-1].get("sort")
        if last_sort:
            body["search_after"] = last_sort
        else:
            break

    return all_hits, total_count


def main():
    parser = argparse.ArgumentParser(description="Search ELK logs for service-agent")
    parser.add_argument("--env", choices=["prd", "test", "dev"], required=True,
                        help="Environment: prd, test or dev (default: prd)")
    parser.add_argument("--keywords", nargs="*", default=None, help="Search keywords (optional when using --logger/--level)")
    parser.add_argument("--mode", choices=["and", "or"], default="and")
    parser.add_argument("--time-from", default=None, help="ISO timestamp start")
    parser.add_argument("--time-to", default=None, help="ISO timestamp end")
    parser.add_argument("--logger", default=None,
                        help="Filter by logger name prefix (e.g. io.agentscope), matched on logger.keyword — 用于捞框架层日志（不带 runId）")
    parser.add_argument("--level", default=None,
                        help="Filter by log level (e.g. WARN, ERROR), matched on loglevel")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--max-lines", type=int, default=500)
    opts = parser.parse_args()

    cfg = ES_CONFIG[opts.env]
    if not all(cfg.get(k) for k in ("url", "user", "password", "index")):
        parser.error("缺少当前环境的 ELK 配置；请检查本机环境变量。")
    output_dir = Path(opts.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Using ELK env: {opts.env} ({cfg['url']}, index: {cfg['index']})")
    print(f"Searching ELK: keywords={opts.keywords} mode={opts.mode}")
    if opts.logger:
        print(f"  logger~: {opts.logger}*")
    if opts.level:
        print(f"  level: {opts.level}")
    if opts.time_from:
        print(f"  time-from: {opts.time_from}")
    if opts.time_to:
        print(f"  time-to: {opts.time_to}")

    hits, total_count = fetch_logs(cfg, opts.keywords, opts.mode, opts.time_from, opts.time_to,
                                   opts.max_lines, opts.logger, opts.level)
    print(f"Fetched {len(hits)} log entries (total matching: {total_count})")

    elk_file = output_dir / "elk.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = f"\n---\n\n## 查询 ({now})\n\n"
    header += f"- env: {opts.env}\n"
    header += f"- keywords: {opts.keywords}\n"
    header += f"- mode: {opts.mode}\n"
    if opts.logger:
        header += f"- logger~: {opts.logger}*\n"
    if opts.level:
        header += f"- level: {opts.level}\n"
    if opts.time_from:
        header += f"- time-from: {opts.time_from}\n"
    if opts.time_to:
        header += f"- time-to: {opts.time_to}\n"
    header += f"- 结果: {len(hits)}/{total_count} 条\n\n```\n"

    log_lines = []
    for hit in hits:
        src = hit.get("_source", {})
        ts = src.get("@timestamp", "")
        msg = src.get("message", "")
        log_lines.append(f"[{ts}] {msg}")

    content = header + "\n".join(log_lines) + "\n```\n"

    with open(elk_file, "a", encoding="utf-8") as f:
        f.write(content)
    print(f"Appended to: {elk_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
