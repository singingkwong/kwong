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
    """从 HTML <title> 或 <h1> 中提取标题，并把日期放到括号里。"""
    # 优先用 <title>，通常包含日期
    match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    if match:
        title = strip_html_tags(match.group(1))
        if title:
            # 清理前缀符号和多余空白
            title = re.sub(r"^[\-\|\s]+", "", title).strip()
            # 如果包含竖线，取主标题部分
            if "|" in title:
                parts = [p.strip() for p in title.split("|")]
                # 日期部分：匹配 YYYY年MM月DD日
                date_part = next((p for p in parts if re.search(r"\d{4}年\d{2}月\d{2}日", p)), "")
                # 主标题：包含"周报"且不包含完整日期，或最长的非日期部分
                main_part = next(
                    (p for p in parts if ("周报" in p or "汽车行业" in p) and not re.search(r"\d{4}年\d{2}月\d{2}日", p)),
                    parts[0]
                )
                # 去掉主标题前可能残留的短日期前缀（如"09月10日 "）
                main_part = re.sub(r"^\d{1,2}月\d{1,2}日\s*", "", main_part).strip()
                # 如果主标题已包含日期范围，直接返回，避免重复拼接
                if re.search(r"\d{4}[年.]\d{2}[月.]\d{2}", main_part):
                    return main_part
                if date_part:
                    return f"{main_part}（{date_part}）"
                return main_part
            m = re.search(r"(\d{4}年\d{2}月\d{2}日)\s*(.+)", title)
            if m:
                return f"{m.group(2)}（{m.group(1)}）"
            return title

    # 回退到 <h1>
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
    """从 HTML 的"本周总览"区域提取摘要。"""
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

        # 如果只有卡片，把前 2-3 张卡片的描述拼接成摘要
        cards = overview_section.find_all("div", class_=lambda x: x and "card" in x.split())
        parts = []
        for card in cards[:3]:
            content = card.find("div", class_=lambda x: x and "card-content" in x)
            if content:
                parts.append(content.get_text(strip=True))
        if parts:
            summary = " ".join(parts)
            return summary[:200]

    # 回退：取 body 中第一个有意义的段落
    body = soup.find("body") or soup
    for p in body.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) >= 40 and not text.startswith("全球汽车行业") and not text.startswith("报告日期"):
            return text[:160]

    return "本周全球汽车市场深度解读，点击查看完整报告。"


def _clean_section_title(title: str) -> str:
    """清理章节标题中的英文前缀/后缀，如 'Markets各地市场动态' -> '各地市场动态'。"""
    title = title.strip()
    title = re.sub(r"^[A-Za-z]+\s*", "", title).strip()
    title = re.sub(r"\s*[A-Za-z]+\s*$", "", title).strip()
    return title


def _find_section_anchor(soup: BeautifulSoup, title_text: str) -> str:
    """根据标题文本查找对应 section 的 id 作为锚点。"""
    title_text = _clean_section_title(title_text)
    for section in soup.find_all("section"):
        h2 = section.find("h2")
        if not h2:
            continue
        section_title = _clean_section_title(h2.get_text(strip=True))
        if section_title == title_text:
            return section.get("id", "")
    return ""


def _find_section_by_title(soup: BeautifulSoup, title_text: str) -> str:
    """根据标题文本查找 section 的 id 作为锚点。"""
    title_text = _clean_section_title(title_text)
    for section in soup.find_all("section"):
        for tag in ["h2", "h3", "div"]:
            heading = section.find(tag, class_=lambda x: x and ("section-title" in x or "title" in x))
            if not heading:
                heading = section.find(tag)
            if heading:
                section_title = _clean_section_title(heading.get_text(strip=True))
                if section_title == title_text:
                    return section.get("id", "")
    return ""


def _infer_anchor(title: str, tag: str = "") -> str:
    """根据热点标题/标签推断新模板中的章节锚点 id。

    新模板锚点：overview / china / sea / sa / eu / na / other /
    policy / oem / research / injection / nextweek。
    """
    t = f"{title} {tag}".lower()

    def has(*words: str) -> bool:
        return any(w.lower() in t for w in words)

    if has("注塑", "模具", "压铸", "轻量化", "碳纤维", "复合材料", "工程塑料", "改性塑料", "注塑机"):
        return "injection"
    if has("政策", "法规", "关税", "补贴", "双反", "监管", "新规", "合规", "贸易"):
        return "policy"
    if has("车企", "整车", "主机厂", "品牌", "比亚迪", "特斯拉", "丰田", "大众",
           "宝马", "奔驰", "吉利", "奇瑞", "长安", "长城", "宁德时代", "蔚来",
           "小鹏", "理想", "stellantis", "现代", "起亚", "oem"):
        return "oem"
    if has("报告", "调研", "研报", "机构", "麦肯锡", "bcg", "贝恩", "德勤",
           "普华永道", "alixpartners", "评级", "预测", "观点", "research"):
        return "research"
    if has("下周", "前瞻", "日程", "关注", "数据发布", "nextweek"):
        return "nextweek"
    # 区域市场：按关键词定位到具体区域锚点
    if has("巴西", "南美", "argentina", "阿根廷"):
        return "sa"
    if has("泰国", "印尼", "越南", "马来", "东南亚", "东盟", "sea"):
        return "sea"
    if has("欧洲", "欧盟", "德国", "法国", "意大利", "西班牙", "acea", "eu"):
        return "eu"
    if has("北美", "美国", "加拿大", "墨西哥", "na", "u.s"):
        return "na"
    if has("印度", "俄罗斯", "澳洲", "澳大利亚", "日本", "韩国", "中东", "非洲"):
        return "other"
    if has("中国", "国内", "乘联会", "中汽协", "cpca", "caam", "china"):
        return "china"
    if has("销量", "同比", "环比", "渗透率", "市场", "%", "出口"):
        return "overview"
    return "overview"


def extract_hotspots(html_content: str, count: int = 3) -> list:
    """
    从 HTML 中提取 3 个本周热点，用于企微图文消息小卡片。
    新模板优先读取 .key-points#overview 下的 .kp-card（本周总览核心看点）；
    回退到 .overview-card、旧版 hotspot-card / stat-card 或章节标题。
    返回的字典包含 title / description / anchor。
    """
    hotspots = []
    soup = BeautifulSoup(html_content, "html.parser")

    # 策略 0（新模板优先）：.key-points#overview > .kp-grid > .kp-card
    key_points = soup.find("section", id="overview")
    if key_points:
        kp_cards = key_points.find_all("div", class_=lambda x: x and "kp-card" in (x or ""))
        for card in kp_cards:
            title_elem = card.find(["h3", "h4"])
            desc_elem = card.find("p")
            badge = card.find("span", class_=lambda x: x and "injection-badge" in (x or ""))
            tag_text = badge.get_text(strip=True) if badge else ""

            title = title_elem.get_text(strip=True) if title_elem else ""
            title = re.sub(r"^\d+[\.、\s]+\s*", "", title).strip()
            title = re.sub(r"^[A-Za-z]+\s*", "", title).strip()
            description = desc_elem.get_text(strip=True) if desc_elem else "点击查看详情"

            if title and len(title) < 60:
                hotspots.append({
                    "title": title,
                    "description": description[:150],
                    "anchor": _infer_anchor(title, tag_text),
                    "source_url": "",
                })
            if len(hotspots) >= count:
                return hotspots[:count]

    # 策略 A：旧版 Agent 显式生成的 hotspot-card
    hotspot_cards = soup.find_all("div", class_=lambda x: x and "hotspot-card" in x)
    for card in hotspot_cards:
        title_elem = card.find(["div", "h3", "h4"], class_=lambda x: x and "hotspot-title" in x)
        desc_elem = card.find("div", class_=lambda x: x and "hotspot-desc" in x)
        tag_elem = card.find("span", class_=lambda x: x and "hotspot-tag" in x)

        title = title_elem.get_text(strip=True) if title_elem else ""
        title = re.sub(r"^[A-Za-z]+\s*", "", title).strip()
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        tag = tag_elem.get_text(strip=True) if tag_elem else ""

        if title and description:
            # 从标题中推断锚点：政策 -> section-3，车企 -> section-4，注塑 -> section-6，默认 section-2
            anchor = _infer_anchor(title, tag)

            # 如果热点卡片内显式提供了原文链接，优先使用原文链接
            source_url = ""
            source_link = card.find("a", class_=lambda x: x and "hotspot-source" in x)
            if source_link and source_link.get("href"):
                source_url = source_link["href"].strip()

            hotspots.append({
                "title": title,
                "description": description[:150],
                "anchor": anchor,
                "source_url": source_url,
            })
        if len(hotspots) >= count:
            return hotspots

    # 策略 B：从"本周总览"区域的数据指标中提取
    if len(hotspots) < count:
        overview_section = _find_overview_section(soup)
        if overview_section:
            overview_id = overview_section.get("id", "overview") or "overview"
            stat_cards = overview_section.find_all("div", class_=lambda x: x and "stat-card" in x)
            for card in stat_cards:
                label = card.find("div", class_=lambda x: x and "stat-label" in x)
                value = card.find("div", class_=lambda x: x and "stat-value" in x)
                desc = card.find("p")

                name = label.get_text(strip=True) if label else ""
                name = re.sub(r"^[A-Za-z]+\s*", "", name).strip()
                val_text = value.get_text(strip=True) if value else ""
                desc_text = desc.get_text(strip=True) if desc else ""

                if name and val_text and len(name) < 60:
                    description = f"{val_text} {desc_text}".strip()
                    hotspots.append({
                        "title": name,
                        "description": description[:150],
                        "anchor": _infer_anchor(name),
                    })
                if len(hotspots) >= count:
                    return hotspots

            # 单独的 stat-value + stat-label 结构
            if len(hotspots) < count:
                value_divs = overview_section.find_all("div", class_=lambda x: x and "stat-value" in x)
                for value_div in value_divs:
                    label_div = value_div.find_next_sibling("div")
                    if label_div and "stat-label" in " ".join(label_div.get("class", [])):
                        name = label_div.get_text(strip=True)
                        name = re.sub(r"^[A-Za-z]+\s*", "", name).strip()
                        val_text = value_div.get_text(strip=True)
                        if name and val_text and len(name) < 60:
                            hotspots.append({
                                "title": name,
                                "description": val_text[:150],
                                "anchor": overview_id,
                            })
                    if len(hotspots) >= count:
                        return hotspots

    # 策略 B2：从"本周总览"的 .card 卡片中提取（a4276fa 等旧版样式）
    if len(hotspots) < count:
        overview_section = _find_overview_section(soup)
        if overview_section:
            overview_id = overview_section.get("id", "overview") or "overview"
            cards = overview_section.find_all("div", class_=lambda x: x and "card" in x.split() and "hotspot-card" not in x and "stat-card" not in x)
            for card in cards:
                title_elem = card.find("div", class_=lambda x: x and "card-title" in x)
                desc_elem = card.find("div", class_=lambda x: x and "card-content" in x)
                if not title_elem:
                    continue
                # 复制标题元素并移除 tag，避免把 tag 文本算进标题
                title_copy = BeautifulSoup(str(title_elem), "html.parser").find()
                for tag in title_copy.find_all("span", class_=lambda x: x and "tag" in x):
                    tag.decompose()
                title_clean = title_copy.get_text(strip=True)
                if not title_clean:
                    title_clean = title_elem.get_text(strip=True)
                # 去掉标题中常见的英文前缀，如 "Overview本周总览" -> "本周总览"
                title_clean = re.sub(r"^[A-Za-z]+\s*", "", title_clean).strip()
                description = desc_elem.get_text(strip=True) if desc_elem else "点击查看详情"
                if title_clean and len(title_clean) < 60:
                    hotspots.append({
                        "title": title_clean,
                        "description": description[:150],
                        "anchor": overview_id,
                    })
                if len(hotspots) >= count:
                    return hotspots

    # 策略 B3：从新版 overview-card 卡片中提取（用户指定：对应本周总览一二三点，加原文锚点）
    if len(hotspots) < count:
        overview_section = _find_overview_section(soup)
        if overview_section:
            overview_id = overview_section.get("id", "overview") or "overview"
            cards = overview_section.find_all(["article", "div"], class_=lambda x: x and "overview-card" in (x or "").split())
            for card in cards:
                title_elem = card.find(["h3", "h4", "div"], class_=lambda x: x and "title" in (x or ""))
                desc_elem = card.find("p")
                if not title_elem:
                    title_elem = card.find(["h3", "h4"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                # 去掉序号前缀 "01 "、"02 " 等
                title = re.sub(r"^\d+[\.、\s]+\s*", "", title).strip()
                title = re.sub(r"^[A-Za-z]+\s*", "", title).strip()
                description = desc_elem.get_text(strip=True) if desc_elem else "点击查看详情"

                # 根据标签/标题关键词推断原文章节锚点（对齐新模板 id）
                tag_elem = card.find("span", class_=lambda x: x and "tag" in (x or ""))
                tag_text = tag_elem.get_text(strip=True) if tag_elem else ""
                anchor = _infer_anchor(title, tag_text)

                # 如果卡片内有显式原文链接，优先使用
                source_url = ""
                source_link = card.find("a", class_=lambda x: x and "hotspot-source" in (x or ""))
                if source_link and source_link.get("href"):
                    source_url = source_link["href"].strip()

                if title and len(title) < 60:
                    hotspots.append({
                        "title": title,
                        "description": description[:150],
                        "anchor": anchor,
                        "source_url": source_url,
                    })
                if len(hotspots) >= count:
                    return hotspots

    # 策略 C：回退到 section-title / h2 章节标题
    if len(hotspots) < count:
        needed = count - len(hotspots)
        text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
        soup2 = BeautifulSoup(text, "html.parser")

        titles = []
        for elem in soup2.find_all(["h2", "div"]):
            if elem.name == "div" and "section-title" not in " ".join(elem.get("class", [])):
                continue
            title_text = elem.get_text(strip=True)
            # 去掉开头或结尾常见的英文前缀/后缀，如 "Markets各地市场动态" -> "各地市场动态"
            title_text = re.sub(r"^[A-Za-z]+\s*", "", title_text).strip()
            title_text = re.sub(r"\s*[A-Za-z]+\s*$", "", title_text).strip()
            if title_text and title_text not in ["本周总览"] and title_text not in [t["title"] for t in titles]:
                anchor = _find_section_by_title(soup2, title_text)
                titles.append({"title": title_text, "description": "点击查看详情", "anchor": anchor})
            if len(titles) >= needed:
                break

        hotspots.extend(titles)

    return hotspots[:count]


def _polish_hotspot_title(idx: int, title: str) -> str:
    """精简吸睛的热点卡片标题：用 ①②③ 序号对应本周总览一二三点，直接接原标题。"""
    title = title.strip()
    # 去掉已有前缀避免重复（"热点1｜"、"热点1："、"① " 等）
    title = re.sub(r"^[热点]*\d*\s*[｜|:：.、]\s*", "", title)
    title = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", title)
    title = title.strip()
    # 圆圈序号，明确对应本周总览第 1/2/3 点
    circled = "①②③④⑤⑥⑦⑧⑨⑩"
    prefix = circled[idx - 1] if 1 <= idx <= len(circled) else str(idx)
    # 限制长度：企微标题过长会被截断（序号占 1 字，正文留 23 字）
    if len(title) > 23:
        title = title[:22] + "…"
    return f"{prefix} {title}"


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
        # 如果热点有原文链接，优先跳转到原文；否则跳转到周报页面章节锚点
        source_url = hotspot.get("source_url", "").strip()
        if source_url and source_url.startswith(("http://", "https://")):
            url = source_url
        else:
            anchor = hotspot.get("anchor", "")
            url = f"{BASE_URL}#{anchor}" if anchor else BASE_URL
        description = hotspot.get("description", "点击查看详情").strip()
        # 企微描述过长会折叠，控制在 45 字以内更醒目
        if len(description) > 45:
            description = description[:44] + "…"
        articles.append({
            "title": _polish_hotspot_title(idx, hotspot["title"]),
            "description": description,
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
