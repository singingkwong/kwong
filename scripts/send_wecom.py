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


def _find_overview_section(soup: BeautifulSoup):
    """查找"本周总览"区域，支持 overview / section-1 两种 id。"""
    for section_id in ("overview", "section-1"):
        section = soup.find("section", {"id": section_id})
        if section:
            return section
    return None


def extract_summary(html_content: str) -> str:
    """从 HTML 的"本周总览"区域提取摘要，否则取第一段有意义的正文。"""
    soup = BeautifulSoup(html_content, "html.parser")

    overview_section = _find_overview_section(soup)
    if overview_section:
        # 先尝试 report-summary 概述
        summary_div = overview_section.find("div", class_=lambda x: x and "report-summary" in x)
        if summary_div:
            text = summary_div.get_text(strip=True)
            if len(text) >= 30:
                return text[:200]

        # 再尝试第一个有意义的段落
        for p in overview_section.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) >= 40:
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


def _find_section_anchor(soup: BeautifulSoup, title_text: str) -> str:
    """根据标题文本查找对应 section 的 id 作为锚点。"""
    title_text = title_text.strip()
    for section in soup.find_all("section"):
        h2 = section.find("h2")
        if not h2:
            continue
        section_title = h2.get_text(strip=True)
        section_title = re.sub(r"\s*\w+\s*Overview\s*$", "", section_title, flags=re.IGNORECASE)
        if section_title == title_text:
            return section.get("id", "")
    return ""


def extract_hotspots(html_content: str, count: int = 3) -> list:
    """
    从 HTML "本周总览" 区域的数据指标中提取热点。
    支持多种结构：stat-card / stat-value+stat-label / grid 布局。
    若未找到，则回退到 section-title / h2 章节标题。
    返回的字典包含 title / description / anchor。
    """
    hotspots = []
    soup = BeautifulSoup(html_content, "html.parser")

    overview_section = _find_overview_section(soup)
    if overview_section:
        overview_id = overview_section.get("id", "overview") or "overview"
        # 策略 A-1：class="stat-card" 结构
        stat_cards = overview_section.find_all("div", class_=lambda x: x and "stat-card" in x)
        for card in stat_cards:
            label = card.find("div", class_=lambda x: x and "stat-label" in x)
            value = card.find("div", class_=lambda x: x and "stat-value" in x)
            desc = card.find("p")

            name = label.get_text(strip=True) if label else ""
            val_text = value.get_text(strip=True) if value else ""
            desc_text = desc.get_text(strip=True) if desc else ""

            if name and val_text and len(name) < 60:
                description = f"{val_text} {desc_text}".strip()
                hotspots.append({
                    "title": name,
                    "description": description[:150],
                    "anchor": overview_id,
                })
            if len(hotspots) >= count:
                return hotspots

        # 策略 A-2：单独的 stat-value + stat-label 结构（无 stat-card 外层）
        if not hotspots:
            value_divs = overview_section.find_all("div", class_=lambda x: x and "stat-value" in x)
            for value_div in value_divs:
                label_div = value_div.find_next_sibling("div")
                if label_div and "stat-label" in " ".join(label_div.get("class", [])):
                    name = label_div.get_text(strip=True)
                    val_text = value_div.get_text(strip=True)
                    if name and val_text and len(name) < 60:
                        hotspots.append({
                            "title": name,
                            "description": val_text[:150],
                            "anchor": overview_id,
                        })
                if len(hotspots) >= count:
                    return hotspots

    # 策略 B：回退到 section-title / h2 章节标题
    if len(hotspots) < count:
        needed = count - len(hotspots)
        text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
        soup2 = BeautifulSoup(text, "html.parser")

        titles = []
        for elem in soup2.find_all(["h2", "div"]):
            if elem.name == "div" and "section-title" not in " ".join(elem.get("class", [])):
                continue
            title_text = elem.get_text(strip=True)
            title_text = re.sub(r"\s*\w+\s*Overview\s*$", "", title_text, flags=re.IGNORECASE)
            if title_text and title_text not in ["本周总览", "Weekly Overview"] and title_text not in [t["title"] for t in titles]:
                anchor = _find_section_anchor(soup2, title_text)
                titles.append({"title": title_text, "description": "点击查看详情", "anchor": anchor})
            if len(titles) >= needed:
                break

        hotspots.extend(titles)

    return hotspots[:count]


def build_payload(title: str, summary: str, hotspots: list) -> dict:
    """构建企微图文消息 payload。热点卡片 url 带章节锚点。"""
    articles = [
        {
            "title": title,
            "description": summary,
            "url": BASE_URL,
            "picurl": COVER_URL,
        }
    ]

    for idx, hotspot in enumerate(hotspots, start=1):
        anchor = hotspot.get("anchor", "")
        url = f"{BASE_URL}#{anchor}" if anchor else BASE_URL
        articles.append({
            "title": f"热点{idx}：{hotspot['title']}",
            "description": hotspot["description"],
            "url": url,
            "picurl": COVER_URL,
        })

    return {"msgtype": "news", "news": {"articles": articles}}


def send_message(payload: dict) -> dict:
    """调用企业微信机器人 Webhook 发送消息。"""
    if not WECOM_WEBHOOK_KEY:
        raise ValueError("缺少环境变量 WECOM_WEBHOOK_KEY")

    webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WECOM_WEBHOOK_KEY}"
    response = requests.post(webhook_url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def main() -> None:
    html_path = find_html()
    print(f"读取周报 HTML: {html_path}")

    html_content = html_path.read_text(encoding="utf-8")
    title = extract_title(html_content)
    summary = extract_summary(html_content)
    hotspots = extract_hotspots(html_content, count=3)

    print(f"标题: {title}")
    print(f"摘要: {summary}")
    print(f"热点数: {len(hotspots)}")

    payload = build_payload(title, summary, hotspots)
    print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))

    result = send_message(payload)
    print("企微推送结果:", result)

    if result.get("errcode") != 0:
        raise RuntimeError(f"企微推送失败：{result}")

    print("企微推送成功")


if __name__ == "__main__":
    main()
