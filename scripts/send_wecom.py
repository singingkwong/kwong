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
from bs4 import BeautifulSoup

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
    """从 HTML 的"本周总览"区域提取摘要，否则取第一段有意义的正文。"""
    soup = BeautifulSoup(html_content, "html.parser")

    # 优先从"本周总览"section 中提取 report-summary 或第一个段落
    overview_section = soup.find("section", {"id": "section-1"})
    if overview_section:
        # 先尝试 report-summary 概述
        summary_div = overview_section.find("div", class_=lambda x: x and "report-summary" in x)
        if summary_div:
            text = summary_div.get_text(strip=True)
            if len(text) >= 30:
                return text[:200]

        # 再尝试"核心摘要"段落
        for p in overview_section.find_all("p"):
            text = p.get_text(strip=True)
            if "核心摘要" in text or len(text) >= 40:
                clean = re.sub(r"^核心摘要[：:]\s*", "", text)
                if len(clean) >= 30:
                    return clean[:200]

    # 回退：取 body 中第一个有意义的段落
    body = soup.find("body") or soup
    for p in body.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) >= 40 and not text.startswith("全球汽车行业") and not text.startswith("报告日期"):
            return text[:160]

    return "本周全球汽车市场深度解读，点击查看完整报告。"


def extract_hotspots(html_content: str, count: int = 3) -> list:
    """
    从 HTML "本周总览" 区域的数据指标卡片中提取热点。
    优先匹配：指标名称 + 指标数值/描述。
    若未找到，则回退到 <h2> 章节标题策略。
    """
    hotspots = []
    soup = BeautifulSoup(html_content, "html.parser")

    # 策略 A：从"本周总览"区域提取 stat-card 指标
    overview_section = soup.find("section", {"id": "section-1"})
    if overview_section:
        stat_cards = overview_section.find_all("div", class_=lambda x: x and "stat-card" in x)
        for card in stat_cards:
            label = card.find("div", class_=lambda x: x and "stat-label" in x)
            value = card.find("div", class_=lambda x: x and "stat-value" in x)
            desc = card.find("p")

            name = label.get_text(strip=True) if label else ""
            val_text = value.get_text(strip=True) if value else ""
            desc_text = desc.get_text(strip=True) if desc else ""

            if name and val_text and len(name) < 50:
                description = f"{val_text} {desc_text}".strip()
                hotspots.append({
                    "title": name,
                    "description": description[:150],
                })
            if len(hotspots) >= count:
                return hotspots

    # 策略 B：回退到 <h2> 章节标题
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.IGNORECASE | re.DOTALL)

    h2_pattern = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
    matches = list(h2_pattern.finditer(text))

    for i, match in enumerate(matches):
        title = strip_html_tags(match.group(1))
        if not title:
            continue

        if any(skip in title for skip in ["来源", "配图", "原文链接", "周报", "简报", "关于我们"]):
            continue

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]

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
