#!/usr/bin/env python3
"""
企业微信机器人推送：汽车行业周报图文卡片。
从生成的 HTML 文件中自动提取标题和热点，发送企微图文消息。
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
COVER_URL = f"{BASE_URL}/cover.png"


def find_html() -> Path:
    html_path = ROOT / "index.html"
    if not html_path.exists():
        raise FileNotFoundError("未找到 index.html 文件")
    return html_path


def strip_html_tags(text: str) -> str:
    """去除 HTML 标签并压缩空白。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(html_content: str) -> str:
    """从 HTML <title> 或 <h1> 中提取标题。"""
    match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    if match:
        title = strip_html_tags(match.group(1))
        if title:
            return title

    match = re.search(r"<h1[^>]*>(.*?)</h1>", html_content, re.IGNORECASE | re.DOTALL)
    if match:
        title = strip_html_tags(match.group(1))
        if title:
            return title

    return "全球汽车行业周报"


def extract_summary(html_content: str) -> str:
    """从 HTML 中提取第一段有意义的正文作为摘要。"""
    # 移除 script/style 标签及其内容
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = strip_html_tags(text)

    # 按句子拆分，找到第一段超过 30 个字的描述性文字
    sentences = re.split(r"(?<=[。！？.!?])\s+", text)
    for s in sentences:
        s = s.strip()
        if len(s) >= 30 and not s.startswith("全球汽车行业") and not s.startswith("报告日期"):
            return s[:160]

    return "本周全球汽车市场深度解读，点击查看完整报告。"


def extract_hotspots(html_content: str, count: int = 3) -> list:
    """
    从 HTML 的 <h2> 标题中提取热点条目。
    策略：取 <h2> 标题及之后的第一段正文作为描述。
    """
    hotspots = []
    # 移除 script/style
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.IGNORECASE | re.DOTALL)

    # 找到所有 h2 标题及其位置
    h2_pattern = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
    matches = list(h2_pattern.finditer(text))

    for i, match in enumerate(matches):
        title = strip_html_tags(match.group(1))
        if not title:
            continue

        # 过滤不合适的标题
        if any(skip in title for skip in ["来源", "配图", "原文链接", "周报", "简报", "总览", "关于我们"]):
            continue

        # 提取该 h2 之后到下一个 h2 之前的正文
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]

        # 取 section 中的第一段非空文本
        section_text = strip_html_tags(section)
        sentences = re.split(r"(?<=[。！？.!?])\s+", section_text)
        description = ""
        for s in sentences:
            s = s.strip()
            if len(s) >= 20:
                description = s[:150]
                break

        if description:
            hotspots.append({"title": title, "description": description})

        if len(hotspots) >= count:
            break

    return hotspots


def build_payload(title: str, summary: str, hotspots: list) -> dict:
    articles = [
        {
            "title": title,
            "description": summary,
            "url": BASE_URL,
            "picurl": COVER_URL,
        }
    ]

    for idx, hotspot in enumerate(hotspots[:3], start=1):
        articles.append(
            {
                "title": f"热点{idx}：{hotspot['title']}",
                "description": hotspot["description"],
                "url": BASE_URL,
                "picurl": COVER_URL,
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
    html_path = find_html()
    print(f"读取周报 HTML: {html_path}")

    html_content = html_path.read_text(encoding="utf-8")
    title = extract_title(html_content)
    summary = extract_summary(html_content)
    hotspots = extract_hotspots(html_content)

    print(f"标题: {title}")
    print(f"摘要: {summary}")
    print(f"热点数: {len(hotspots)}")
    for i, h in enumerate(hotspots, 1):
        print(f"  热点{i}: {h['title']}")

    payload = build_payload(title, summary, hotspots)
    print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))

    send(payload)


if __name__ == "__main__":
    main()
