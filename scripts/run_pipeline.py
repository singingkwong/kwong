#!/usr/bin/env python3
"""
周报生成流水线统一入口（本地 & GitHub Actions 通用，文件驱动）。

流程：
  1) 调用扣子 Agent 抓取 Markdown 文本     -> scripts/fetch_weekly_text.py  → ROOT/weekly_YYYYMMDD.md
  2) 文本(markdown) → agent.html          -> scripts/md_to_agent_html.py   → ROOT/agent.html
  3) agent.html → index.html（成品渲染）   -> scripts/render_html.py        → ROOT/index.html
  4) 注入板块配图（默认关闭，--with-images 开启） -> scripts/inject_images.py
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

# 与 fetch_weekly_text.py 约定的鉴权失败退出码
AUTH_EXIT_CODE = 3


class CozeAuthPipelineError(RuntimeError):
    """fetch 阶段 Coze 鉴权失败，应触发告警并阻断周报推送。"""


def _notify_coze_auth_failure(detail: str) -> None:
    """鉴权失败时向 Coze 反馈告警（提示 token 过期、请修复后手动触发）。

    告警发送失败不影响主流程：主流程仍会以非 0 退出使 workflow 失败。
    """
    print(
        "\n[告警] Coze 鉴权失败，向 Coze 反馈告警（提示 token 过期，修复后请手动触发）...",
        flush=True,
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "coze_alert.py")],
        cwd=ROOT,
        text=True,
    )
    if proc.returncode == 0:
        print("[告警] Coze 告警已发送（或未配置告警 Bot 已跳过）", flush=True)
    else:
        print("[告警] Coze 告警发送失败，详情见上方 coze_alert 输出", flush=True)


def run(cmd: list[str], step: str) -> None:
    print(f"\n[step] {step}")
    print("  $ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, text=True)
    if proc.returncode == AUTH_EXIT_CODE:
        raise CozeAuthPipelineError(
            f"步骤失败({step}): Coze 鉴权失败（token 过期/无效/无权限），已中止后续流程。"
        )
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

    # 4) 注入配图（默认关闭；仅显式传 --with-images 时注入，配图来自 Agent md 中的远程图片）
    if "--with-images" in sys.argv:
        run([sys.executable, str(SCRIPTS / "inject_images.py"), str(index_path), f"--md={md}"], "注入板块配图")
    else:
        print("[skip] 配图注入已默认关闭（如需启用请加 --with-images）")

    # 5) 推送企微（可选）
    if do_push:
        key = os.environ.get("WECOM_WEBHOOK_KEY", "").strip()
        if not key:
            print("\n[skip] 未配置 WECOM_WEBHOOK_KEY，跳过企微推送。可在 GitHub Secrets 或环境变量中配置后手动触发。")
        else:
            run([sys.executable, str(SCRIPTS / "send_wecom.py")], "推送企业微信")

    print("\n✅ 流水线完成：agent.html + index.html 已就绪。")


if __name__ == "__main__":
    try:
        main()
    except CozeAuthPipelineError as exc:
        print(f"\n[告警] {exc}", flush=True)
        _notify_coze_auth_failure(str(exc))
        sys.exit(1)