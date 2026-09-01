#!/usr/bin/env python3
"""
企业微信机器人推送：汽车行业周报图文卡片。
从生成的 Markdown 文件中自动提取标题和热点，发送企微图文消息。
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

WECOM_WEBHOOK_KEY = os.environ.get("WECOM_WEBHOOK_KEY")
GITHUB_USER = os.environ.get("GITHUB_USER", os.environ.get("GITHUB_REPOSITORY_OWNER", "<你的用户名>"))
GITHUB_REPO = os.environ.get("GITHUB_REPO", os.environ.get("GITHUB_REPOSITORY_NAME", "<你的仓库名>"))

BASE_URL = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}"
DEFAULT_COVER_URL = f"{BASE_URL}/cover.png"


def find_latest_md() -> Path:
    md_files = sorted(ROOT.glob("weekly_*.md"))
    if not md_files:
        raise FileNotFoundError("未找到 weekly_*.md 文件")
    return md_files[-1]


def extract_cover_image(md_content: str) -> str:
    """从 Markdown 中提取封面图 URL，如果没有则使用默认封面。"""
    match = re.search(r"^cover_image:\s*(.+)$", md_content, re.MULTILINE | re.IGNORECASE)
    if match:
        url = match.group(1).strip()
        if url and url.lower() != "default":
            return url
    return DEFAULT_COVER_URL


def extract_title(md_content: str) -> str:
    match = re.search(r"^#\s+(.+)$", md_content, re.MULTILINE)
    title = match.group(1).strip() if match else "全球汽车行业周报"
    # 如果标题没有日期，加上当天日期
    if not re.search(r"\d{4}", title):
        today = datetime.now().strftime("%Y年%m月%d日")
        title = f"{title} | {today}"
    return title


def extract_summary(md_content: str) -> str:
    """提取 Markdown 第一段非空文字作为摘要。"""
    lines = [line.strip() for line in md_content.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("#") or line.startswith("!") or line.startswith("["):
            continue
        if re.match(r"^cover_image:\s*", line, re.IGNORECASE):
            continue
        return line[:160]
    return "本周全球汽车市场深度解读，点击查看完整报告。"


def extract_hotspots(md_content: str, count: int = 3) -> list:
    """
    从 Markdown 中提取热点条目。
    策略：匹配 ## 或 ### 标题，取标题下的第一段正文作为描述。
    """
    hotspots = []
    # 按标题拆分
    sections = re.split(r"\n(?=##\s+|###\s+)", md_content)

    for section in sections:
        title_match = re.match(r"#{2,3}\s+(.+)$", section, re.MULTILINE)
        if not title_match:
            continue

        title = title_match.group(1).strip()
        # 过滤掉不合适的标题
        if any(skip in title for skip in ["来源", "配图", "原文链接", "周报", "简报", "总览"]):
            continue

        # 提取标题下的第一段正文
        body_lines = []
        for line in section.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!") or line.startswith("["):
                continue
            body_lines.append(line)
            if len(body_lines) >= 2:
                break

        if body_lines:
            description = " ".join(body_lines)[:150]
            hotspots.append({"title": title, "description": description})

        if len(hotspots) >= count:
            break

    return hotspots


def build_payload(title: str, summary: str, hotspots: list, cover_url: str) -> dict:
    articles = [
        {
            "title": title,
            "description": summary,
            "url": BASE_URL,
            "picurl": cover_url,
        }
    ]

    for idx, hotspot in enumerate(hotspots[:3], start=1):
        articles.append(
            {
                "title": f"热点{idx}：{hotspot['title']}",
                "description": hotspot["description"],
                "url": BASE_URL,
                "picurl": cover_url,
            }
        )

    return {"msgtype": "news", "news": {"articles": articles}}


def send(payload: dict):
    if not WECOM_WEBHOOK_KEY or WECOM_WEBHOOK_KEY == "你的企业微信机器人KEY":
        print("错误：未设置 WECOM_WEBHOOK_KEY 环境变量")
        raise SystemExit(1)

    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WECOM_WEBHOOK_KEY}"
    resp = requests.post(url, json=payload, timeout=10)
    data = resp.json()

    if data.get("errcode") == 0:
        print("企微推送成功")
    else:
        print(f"企微推送失败：{data}")
        raise SystemExit(1)


def main():
    md_path = find_latest_md()
    print(f"读取周报: {md_path}")

    md_content = md_path.read_text(encoding="utf-8")
    title = extract_title(md_content)
    cover_url = extract_cover_image(md_content)
    summary = extract_summary(md_content)
    hotspots = extract_hotspots(md_content)

    print(f"标题: {title}")
    print(f"封面图: {cover_url}")
    print(f"摘要: {summary}")
    print(f"热点数: {len(hotspots)}")
    for i, h in enumerate(hotspots, 1):
        print(f"  热点{i}: {h['title']}")

    payload = build_payload(title, summary, hotspots, cover_url)
    print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))

    send(payload)


if __name__ == "__main__":
    main()
