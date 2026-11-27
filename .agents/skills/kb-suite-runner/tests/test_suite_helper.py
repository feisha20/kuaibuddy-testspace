#!/usr/bin/env python3
"""kb-suite-runner/scripts/suite_helper.py 单元测试（全隔离临时目录）。"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / ".agents" / "skills" / "kb-suite-runner" / "scripts" / "suite_helper.py"
RENDER_SCRIPT_PATH = REPO_ROOT / ".agents" / "skills" / "kb-suite-runner" / "scripts" / "render_suite_report.py"
SAMPLE_JSON = REPO_ROOT / "tests" / "data" / "kb-suite-001-report-sample.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def make_valid_payload(run_id: str = "RUN-TEST-01", case_id: str = "CASE-01") -> dict:
    return {
        "schemaVersion": "kb-suite-001-report.v1",
        "isPlaceholderDemo": False,
        "meta": {
            "suiteId": "KB-SUITE-001",
            "taskId": "无（单次请求）",
            "runId": run_id,
            "env": "preprod",
            "langfuseEnv": "prd",
            "startedAt": "2026-11-26 11:00:00 +08:00",
            "finishedAt": "2026-11-26 11:02:00 +08:00",
            "durationMs": 60000,
            "gitCommit": "0" * 40,
            "worktreeDirty": False,
            "modelSummary": "kimi-k2.8-preview",
            "pointsBefore": 500.0,
            "pointsAfter": 490.0,
            "pointsConsumed": 10.0,
            "cleanupStatus": "passed",
            "cleanupNote": "测试残留已清理",
        },
        "cases": [
            {
                "id": case_id,
                "status": "passed",
                "summary": "单测合成合法通过用例",
                "durationMs": 60000,
                "steps": [
                    {
                        "name": "Step 1",
                        "status": "passed",
                        "expected": "ok",
                        "actual": "ok",
                        "evidence": "unit test",
                    }
                ],
            }
        ],
        "envConfig": {
            "source": "PREPROD Nacos 配置",
            "primaryModel": "kimi-k2.8-preview (1M)",
            "fallbackModel": "deepseek-v4-1-flash (1M)",
            "imageGenModel": "gpt-image-26-sunburst",
            "visionFollowupModel": "MiniMax-M3",
            "compactionThreshold": "400,000 tokens · trigger-messages=0",
            "toolLimits": "read_file <= 64,000 字符 · 沙箱 180s",
        },
        "aiSummary": {
            "source": "实测总结",
            "headline": "预生产单用例验证通过，主链路表现正常。",
            "sections": [
                {
                    "title": "核心结论",
                    "items": ["缓存命中与工具调用符合预期。"],
                },
                {
                    "title": "效能与资源",
                    "items": ["总耗时 1m 0s，消耗 10 积分，已清理无残留。"],
                },
            ],
            "recommendation": "可按需补测其余场景。",
        },
    }


class SuiteHelperTests(unittest.TestCase):
    def test_init_run_single_request_with_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = run_cli(
                "init-run",
                "--summary",
                "预生产局部回归验证",
                "--run-summary",
                "首轮回归",
                "--env",
                "test",
                "--init-report-json",
                "--root",
                str(root),
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            info = json.loads(res.stdout)
            self.assertEqual(info["taskId"], "无（单次请求）")
            self.assertEqual(info["env"], "test")
            self.assertEqual(info["langfuseEnv"], "test")

            run_dir = Path(info["runDir"])
            self.assertTrue((run_dir / "logs").is_dir())
            self.assertTrue((run_dir / "screenshots").is_dir())
            self.assertTrue((run_dir / "artifacts").is_dir())

            for md_name in ("plan.md", "execution.md", "result.md"):
                txt = (run_dir / md_name).read_text(encoding="utf-8")
                self.assertNotIn("{{TASK_ID}}", txt)
                self.assertNotIn("{{RUN_ID}}", txt)
                self.assertIn(info["runId"], txt)

            skeleton_path = run_dir / "artifacts" / "report-data.json"
            self.assertTrue(skeleton_path.is_file())
            chk = run_cli("check-and-render", "--check-only", "--data", str(skeleton_path))
            self.assertEqual(chk.returncode, 0, chk.stderr)

    def test_init_run_rejects_invalid_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            res1 = run_cli("init-run", "--summary", "pure-english-only", "--root", tmp)
            self.assertNotEqual(res1.returncode, 0)

            res2 = run_cli("init-run", "--summary", "非法/路径字符", "--root", tmp)
            self.assertNotEqual(res2.returncode, 0)

    def test_init_run_reuses_task_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tasks").mkdir(parents=True)
            (root / "tasks" / "TASK-999-示例任务.md").write_text("# TASK-999\n", encoding="utf-8")

            r1 = run_cli("init-run", "--summary", "示例任务", "--task-id", "TASK-999", "--root", tmp)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            r2 = run_cli("init-run", "--summary", "示例任务", "--task-id", "TASK-999", "--root", tmp)
            self.assertEqual(r2.returncode, 0, r2.stderr)

            i1, i2 = json.loads(r1.stdout), json.loads(r2.stdout)
            self.assertEqual(Path(i1["runDir"]).parent, Path(i2["runDir"]).parent)
            self.assertNotEqual(i1["runId"], i2["runId"])
            self.assertEqual(Path(i1["runDir"]).parent.name, "TASK-999-示例任务")

    def test_check_only_accepts_repo_sample(self) -> None:
        res = run_cli("check-and-render", "--check-only", "--data", str(SAMPLE_JSON))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("三道门禁全部通过", res.stdout)

    def test_merge_and_render_html_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p1 = root / "run1.json"
            p2 = root / "run2.json"
            out_html = root / "out" / "merged.html"

            d1 = make_valid_payload("RUN-A", "CASE-01")
            d1["meta"]["durationMs"] = 30000
            d1["meta"]["pointsConsumed"] = 5.5
            d1["meta"]["cleanupStatus"] = "not_needed"

            d2 = make_valid_payload("RUN-B", "CASE-09")
            d2["meta"]["durationMs"] = 45000
            d2["meta"]["pointsConsumed"] = 12.25
            d2["meta"]["cleanupStatus"] = "failed"

            p1.write_text(json.dumps(d1, ensure_ascii=False), encoding="utf-8")
            p2.write_text(json.dumps(d2, ensure_ascii=False), encoding="utf-8")

            res = run_cli("check-and-render", "--data", str(p1), "--data", str(p2), "--out", str(out_html))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out_html.is_file())

            html_txt = out_html.read_text(encoding="utf-8")
            m = re.search(r'<script\s+id="kb-report-data"\s+type="application/json"\s*>(.*?)</script>', html_txt, re.S)
            self.assertIsNotNone(m)
            embedded = json.loads(m.group(1))
            self.assertEqual(embedded["meta"]["durationMs"], 75000)
            self.assertEqual(embedded["meta"]["pointsConsumed"], 17.75)
            self.assertEqual(embedded["meta"]["cleanupStatus"], "failed")
            self.assertNotIn("pointsBefore", embedded["meta"])
            self.assertNotIn("pointsAfter", embedded["meta"])
            self.assertNotIn("aiSummary", embedded)
            self.assertEqual([c["id"] for c in embedded["cases"]], ["CASE-01", "CASE-09"])

    def test_hygiene_blocks_workspace_refs_in_ai_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for label, mutator in [
                ("knowledge-md", lambda d: d["aiSummary"]["sections"][0]["items"].append("详见 docs/knowledge.md")),
                ("k-008", lambda d: d["aiSummary"].update({"recommendation": "参考 K-008 处理"})),
                ("agent-label", lambda d: d["aiSummary"].update({"source": "Agent 实测归纳"})),
                ("runtime-in-env", lambda d: d["envConfig"].update({"source": ".runtime/cache/nacos.yaml"})),
            ]:
                doc = make_valid_payload()
                mutator(doc)
                fp = root / f"{label}.json"
                fp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                res = run_cli("check-and-render", "--check-only", "--data", str(fp))
                self.assertEqual(res.returncode, 1, f"{label} 应被门禁阻断: {res.stdout} {res.stderr}")

    def test_hygiene_blocks_secrets_and_status_contradiction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # 1) JWT secret
            d_jwt = make_valid_payload()
            d_jwt["cases"][0]["summary"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
            p_jwt = root / "jwt.json"
            p_jwt.write_text(json.dumps(d_jwt, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run_cli("check-and-render", "--check-only", "--data", str(p_jwt)).returncode, 1)

            # 2) Bearer token & sk-lf key
            d_bearer = make_valid_payload()
            d_bearer["meta"]["cleanupNote"] = "Authorization: Bearer abcdef1234567890_secret"
            p_bearer = root / "bearer.json"
            p_bearer.write_text(json.dumps(d_bearer, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run_cli("check-and-render", "--check-only", "--data", str(p_bearer)).returncode, 1)

            d_lf = make_valid_payload()
            d_lf["meta"]["cleanupNote"] = "key sk-lf-12345678abcdef"
            p_lf = root / "lf.json"
            p_lf.write_text(json.dumps(d_lf, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run_cli("check-and-render", "--check-only", "--data", str(p_lf)).returncode, 1)

            # 3) Status contradiction: passed case with failed step
            d_contra = make_valid_payload()
            d_contra["cases"][0]["steps"][0]["status"] = "failed"
            p_contra = root / "contra.json"
            p_contra.write_text(json.dumps(d_contra, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run_cli("check-and-render", "--check-only", "--data", str(p_contra)).returncode, 1)

            # 4) Invalid meta.env
            d_env = make_valid_payload()
            d_env["meta"]["env"] = "PREPROD"
            p_env = root / "bad_env.json"
            p_env.write_text(json.dumps(d_env, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(run_cli("check-and-render", "--check-only", "--data", str(p_env)).returncode, 1)

            # 5) "400,000 tokens" must NOT be false-positived as secret
            d_ok = make_valid_payload()
            d_ok["envConfig"]["compactionThreshold"] = "400,000 tokens · trigger-messages=0"
            p_ok = root / "ok.json"
            p_ok.write_text(json.dumps(d_ok, ensure_ascii=False), encoding="utf-8")
            res_ok = run_cli("check-and-render", "--check-only", "--data", str(p_ok))
            self.assertEqual(res_ok.returncode, 0, res_ok.stderr)

    def test_dynamic_markdown_suite_add_case11_and_new_domain(self) -> None:
        base_suite = (REPO_ROOT / "tests" / "cases" / "KB-SUITE-001.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_md = base_suite.replace(
                "| 开放连接与个人资产（MCP与个人Skill） | `#user-skill-crud`",
                "| 语音交互与实时通话（实时语音） | `#voice-call` | 实时语音通话 | 实时语音连麦与打断恢复 | `CASE-11` | ✅ 已覆盖 |\n| 开放连接与个人资产（MCP与个人Skill） | `#user-skill-crud`",
                1,
            ).replace(
                "| *后续扩展*",
                "| [CASE-11](#case-11-voice) | 实时语音连麦与打断恢复验证 | `#voice-call` | P1 | 已验证 |\n| *后续扩展*",
                1,
            ).replace(
                "## 5. 执行与产物规范",
                (
                    "### CASE-11：实时语音连麦与打断恢复验证\n"
                    "- **测试目标**：验证实时语音通道创建与语音打断收敛。\n\n"
                    "```bash\n"
                    "KB_ENV_FILE=.env.<ENV> node .agents/skills/kb-test-execution/scripts/kb_e2e.js ask \"发起测试语音\" --out \"<OUT_DIR>/turn-1\" --json\n"
                    "```\n\n"
                    "---\n\n"
                    "## 5. 执行与产物规范"
                ),
                1,
            )
            suite_file = root / "KB-SUITE-CUSTOM.md"
            suite_file.write_text(mod_md, encoding="utf-8")

            d11 = make_valid_payload("RUN-VOICE-11", "CASE-11")
            data_file = root / "run11.json"
            data_file.write_text(json.dumps(d11, ensure_ascii=False), encoding="utf-8")
            out_html = root / "report11.html"

            res = run_cli(
                "check-and-render",
                "--suite",
                str(suite_file),
                "--data",
                str(data_file),
                "--out",
                str(out_html),
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out_html.is_file())

            html_txt = out_html.read_text(encoding="utf-8")
            cat_m = re.search(r'<script\s+id="kb-suite-catalog"\s+type="application/json"\s*>(.*?)</script>', html_txt, re.S)
            self.assertIsNotNone(cat_m)
            cat = json.loads(cat_m.group(1))
            self.assertEqual(len(cat["cases"]), 11)
            self.assertEqual(cat["cases"][-1]["id"], "CASE-11")
            all_tags = [t["tag"] for d in cat["domains"] for t in d["tags"]]
            self.assertEqual(len(all_tags), 23)
            self.assertIn("voice-call", all_tags)

    def test_render_script_default_paths_in_skill(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("kb_render_mod_check", str(RENDER_SCRIPT_PATH))
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        expected_tpl = REPO_ROOT / ".agents" / "skills" / "kb-suite-runner" / "assets" / "kb-suite-001-report.html"
        self.assertEqual(mod.ROOT, REPO_ROOT)
        self.assertEqual(mod.DEFAULT_TEMPLATE, expected_tpl)
        self.assertTrue(mod.DEFAULT_TEMPLATE.is_file())
        self.assertEqual(mod.DEFAULT_SUITE, REPO_ROOT / "tests" / "cases" / "KB-SUITE-001.md")

        res = subprocess.run(
            [sys.executable, str(RENDER_SCRIPT_PATH), "--check-suite"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("测试集自洽校验通过", res.stdout)

    def test_check_suite_detects_table_mismatch(self) -> None:
        base_suite = (REPO_ROOT / "tests" / "cases" / "KB-SUITE-001.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            bad_md = base_suite.replace("`#image-gen` | P1", "`#not-defined-tag` | P1", 1)
            bad_file = Path(tmp) / "BAD-SUITE.md"
            bad_file.write_text(bad_md, encoding="utf-8")

            res = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_SCRIPT_PATH),
                    "--check-suite",
                    "--suite",
                    str(bad_file),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("交叉校验失败", res.stderr)


if __name__ == "__main__":
    unittest.main()
