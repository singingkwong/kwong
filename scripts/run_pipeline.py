#!/usr/bin/env python3
"""
周报生成流水线统一入口（本地 & GitHub Actions 通用，文件驱动）。

流程：
  1) 调用扣子 Agent 抓取 Markdown 文本     -> scripts/fetch_weekly_text.py  → ROOT/weekly_YYYYMMDD.md
  2) 文本(markdown) → agent.html          -> scripts/md_to_agent_html.py   → ROOT/agent.html
  3) agent.html → index.html（成品渲染）   -> scripts/render_html.py        → ROOT/index.html
  4) 注入板块配图                         -> scripts/inject_images.py      → ROOT/index.html（配图 ≥3 张）
  5) 推送企业微信图文（可选）              -> scripts/send_wecom.py         需要 WECOM_WEBHOOK_KEY

用法：
  python3 scripts/run_pipeline.py            # 完整流水线（含企微推送，缺 key 时跳过推送）
  python3 scripts/run_pipeline.py --no-fetch # 跳过 Bot 抓取，使用已有 weekly_*.md
  python3 scripts/run_pipeline.py --no-push  # 不推送企微
  python3 scripts/run_pipeline.py --md xxx.md # 显式指定 markdown 输入
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str], step: str) -> None:
    print(f"\n[step] {step}")
    print("  $ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"步骤失败({step}): exit={proc.returncode}")
    print(f"[ok] {step}\n")


def find_latest_md(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    today = ROOT / f"weekly_{datetime.now().strftime('%Y%m%d')}.md"
    if today.exists():
        return today
    mds = sorted(ROOT.glob("weekly_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mds[0] if mds else None


def main() -> None:
    do_fetch = "--no-fetch" not in sys.argv
    do_push = "--no-push" not in sys.argv
    explicit = None
    for a in sys.argv[1:]:
        if a.startswith("--md="):
            explicit = a[len("--md="):]

    agent_path = ROOT / "agent.html"
    index_path = ROOT / "index.html"

    # 1) 抓取（可选）
    if do_fetch:
        run([sys.executable, str(SCRIPTS / "fetch_weekly_text.py")], "抓取 Agent Markdown 文本")
        md = find_latest_md(explicit)
        if md is None:
            raise RuntimeError("抓取后未找到 weekly_*.md")
    else:
        md = find_latest_md(explicit)
        if md is None:
            raise RuntimeError("未指定 --md 且项目根无 weekly_*.md")
    print(f"使用输入 markdown: {md}")

    # 2) 文本 → agent.html
    run([sys.executable, str(SCRIPTS / "md_to_agent_html.py"), str(md), str(agent_path)], "文本 → agent.html")

    # 3) 渲染 index.html
    run([sys.executable, str(SCRIPTS / "render_html.py"), str(agent_path)], "渲染 index.html")

    # 4) 注入配图
    run([sys.executable, str(SCRIPTS / "inject_images.py"), str(index_path)], "注入板块配图")

    # 5) 推送企微（可选）
    if do_push:
        key = os.environ.get("WECOM_WEBHOOK_KEY", "").strip()
        if not key:
            print("\n[skip] 未配置 WECOM_WEBHOOK_KEY，跳过企微推送。可在 GitHub Secrets 或环境变量中配置后手动触发。")
        else:
            run([sys.executable, str(SCRIPTS / "send_wecom.py")], "推送企业微信")

    print("\n✅ 流水线完成：agent.html + index.html（含配图）已就绪。")


if __name__ == "__main__":
    main()