#!/usr/bin/env python3
"""
将 Agent 生成的 weekly.md 渲染成 index.html。
使用 templates/weekly.html 作为样式模板。
"""
import re
from datetime import datetime
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "templates" / "weekly.html"
MD_PATH = ROOT / "weekly.md"
OUT_PATH = ROOT / "index.html"

SECTION_MAP = {
    "一、本周总览": "overview",
    "二、各地市场动态": "markets",
    "三、政策动态": "policy",
    "四、车企动态": "oem",
    "五、调研报告/机构观点": "research",
    "六、注塑机会专题": "injection",
    "七、下周关注": "nextweek",
    "八、数据来源": "sources",
}

REGION_MAP = {
    "中国": "region-cn",
    "东南亚": "region-sea",
    "南亚": "region-sa",
    "印度": "region-sa",
    "南美": "region-sa2",
    "北美": "region-na",
    "欧洲": "region-eu",
    "俄罗斯": "region-ru",
    "中东": "region-ru",
    "非洲": "region-ru",
    "日韩": "region-jk",
    "日本": "region-jk",
    "澳洲": "region-au",
}


def parse_sections(md_text: str) -> dict:
    """按二级标题把 Markdown 分割成章节。"""
    sections = {}
    current_key = None
    current_lines = []

    for line in md_text.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            title = m.group(1).strip()
            current_key = SECTION_MAP.get(title, title)
            current_lines = []
        else:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def extract_meta(md_text: str) -> dict:
    """提取标题、日期、团队。"""
    title = "全球汽车行业深度周报"
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    if m:
        title = m.group(1).strip()

    date = datetime.now().strftime("%Y年%m月%d日")
    m = re.search(r"\*\*报告日期\*\*[:：]\s*(.+?)(?:\n|\r)", md_text)
    if m:
        date = m.group(1).strip()

    team = "YZM海外汽车行业拓展项目组"
    m = re.search(r"\*\*编制团队\*\*[:：]\s*(.+?)(?:\n|\r)", md_text)
    if m:
        team = m.group(1).strip()

    return {"title": title, "date": date, "team": team}


def md_to_html(md_text: str) -> str:
    """Markdown 转 HTML。"""
    return markdown.markdown(md_text, extensions=["tables", "fenced_code"])


def clean_html_tags(html: str) -> str:
    """去掉外层 p 标签等简单包装。"""
    html = html.strip()
    if html.startswith("<p>") and html.count("<p>") == 1 and html.endswith("</p>"):
        html = html[3:-4]
    return html.strip()


def render_overview(md_text: str) -> str:
    """渲染本周总览：3 个热点卡片 + 核心看点。"""
    html = md_to_html(md_text)
    soup = BeautifulSoup(html, "html.parser")

    cards_html = []
    content_html = []

    # 尝试提取热点（可能在同一个 p 中，也可能分散）
    hotspots = []
    for p in list(soup.find_all("p")):
        text = p.get_text(strip=True)
        found = []
        # 多个热点可能在同一个 p 中，按“热点n：”分割
        parts = re.split(r"(?=热点\d+[:：])", text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m = re.match(r"热点\d+[:：]\s*(.+)", part)
            if m:
                rest = m.group(1)
                if "｜" in rest:
                    title, desc = rest.split("｜", 1)
                elif "|" in rest:
                    title, desc = rest.split("|", 1)
                else:
                    title = rest[:30]
                    desc = rest[30:]
                found.append((title.strip(), desc.strip()))
        if found:
            hotspots.extend(found)
            p.decompose()

    if len(hotspots) >= 3:
        for idx, (htitle, hdesc) in enumerate(hotspots[:3], 1):
            cards_html.append(
                f'''<div class="overview-card">
                    <div class="card-number">0{idx}</div>
                    <h3>{htitle}</h3>
                    <p>{hdesc}</p>
                </div>'''
            )

    # 核心看点列表
    content_html.append(str(soup))

    if cards_html:
        cards_section = '<div class="overview-grid">\n' + "\n".join(cards_html) + "\n</div>"
    else:
        cards_section = ""

    content_section = "\n".join(content_html)

    return f'''<section class="section" id="overview">
            <div class="section-header">
                <h2 class="section-title">本周总览 <span>Weekly Overview</span></h2>
                <p class="section-desc">把握本周全球汽车行业核心脉络与注塑机会</p>
            </div>
            {cards_section}
            {content_section}
        </section>'''


def render_markets(md_text: str) -> str:
    """渲染各地市场动态：按子标题分成 region-card。"""
    lines = md_text.splitlines()
    subsections = []
    current_title = None
    current_lines = []

    for line in lines:
        m = re.match(r"^###\s+(.+)$", line)
        if m:
            if current_title is not None:
                subsections.append((current_title, "\n".join(current_lines).strip()))
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title is not None:
        subsections.append((current_title, "\n".join(current_lines).strip()))

    region_htmls = []
    for title, body in subsections:
        region_class = "region-global"
        for key, cls in REGION_MAP.items():
            if key in title:
                region_class = cls
                break
        # 提取来源后从 body 中移除
        source_match = re.search(r"来源[：:]\s*(.+?)(?:\n|$)", body)
        source_html = ""
        if source_match:
            source_html = f'<div class="news-source">来源：{source_match.group(1).strip()}</div>'
            body = re.sub(r"\n?来源[：:]\s*(.+?)(?:\n|$)", "\n", body)
        body_html = md_to_html(body)
        region_htmls.append(
            f'''<div class="region-card">
                <div class="region-tag {region_class}">{title}</div>
                <div class="region-content">{body_html}</div>
                {source_html}
            </div>'''
        )

    grid = '<div class="markets-grid">\n' + "\n".join(region_htmls) + "\n</div>" if region_htmls else md_to_html(md_text)

    return f'''<section class="section" id="markets">
            <div class="section-header">
                <h2 class="section-title">各地市场动态 <span>Regional Markets</span></h2>
                <p class="section-desc">全球主要汽车市场销量、政策与趋势扫描</p>
            </div>
            {grid}
        </section>'''


def render_list_section(md_text: str, section_id: str, title_zh: str, title_en: str, desc: str, card_class: str) -> str:
    """通用渲染带三级标题的章节（政策、车企、报告、注塑机会）。"""
    lines = md_text.splitlines()
    subsections = []
    current_title = None
    current_lines = []

    for line in lines:
        m = re.match(r"^###\s+(.+)$", line)
        if m:
            if current_title is not None:
                subsections.append((current_title, "\n".join(current_lines).strip()))
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title is not None:
        subsections.append((current_title, "\n".join(current_lines).strip()))

    cards = []
    for title, body in subsections:
        source_match = re.search(r"来源[：:]\s*(.+?)(?:\n|$)", body)
        source_html = ""
        if source_match:
            source_html = f'<div class="news-source">来源：{source_match.group(1).strip()}</div>'
            body = re.sub(r"\n?来源[：:]\s*(.+?)(?:\n|$)", "\n", body)
        body_html = md_to_html(body)
        cards.append(
            f'''<div class="{card_class}">
                <h3>{title}</h3>
                {body_html}
                {source_html}
            </div>'''
        )

    grid = f'<div class="{card_class}s-grid">\n' + "\n".join(cards) + "\n</div>" if cards else md_to_html(md_text)

    return f'''<section class="section" id="{section_id}">
            <div class="section-header">
                <h2 class="section-title">{title_zh} <span>{title_en}</span></h2>
                <p class="section-desc">{desc}</p>
            </div>
            {grid}
        </section>'''


def render_nextweek(md_text: str) -> str:
    """渲染下周关注。"""
    html = md_to_html(md_text)
    return f'''<section class="section" id="outlook">
            <div class="section-header">
                <h2 class="section-title">下周关注 <span>Next Week Focus</span></h2>
                <p class="section-desc">下周值得重点跟踪的行业事件与数据发布</p>
            </div>
            <div class="outlook-list">
                {html}
            </div>
        </section>'''


def render_sources(md_text: str) -> str:
    """渲染数据来源，供 footer 使用。"""
    text = md_to_html(md_text)
    soup = BeautifulSoup(text, "html.parser")
    plain = soup.get_text(", ")
    return plain.strip()


def render_all() -> str:
    if not MD_PATH.exists():
        raise FileNotFoundError(f"找不到 Markdown 文件: {MD_PATH}")
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"找不到模板文件: {TEMPLATE_PATH}")

    md_text = MD_PATH.read_text(encoding="utf-8")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    meta = extract_meta(md_text)
    sections = parse_sections(md_text)

    rendered = {
        "title": meta["title"],
        "date": meta["date"],
        "team": meta["team"],
        "overview": render_overview(sections.get("overview", "")),
        "markets": render_markets(sections.get("markets", "")),
        "policy": render_list_section(
            sections.get("policy", ""),
            "policy",
            "政策动态",
            "Policy Updates",
            "全球主要汽车相关政策、法规与补贴变化",
            "policy-card",
        ),
        "oem": render_list_section(
            sections.get("oem", ""),
            "oem",
            "车企动态",
            "OEM Updates",
            "主流车企战略、产品、产能与合作动态",
            "oem-card",
        ),
        "research": render_list_section(
            sections.get("research", ""),
            "reports",
            "调研报告/机构观点",
            "Research & Insights",
            "投行、咨询机构与行业协会的核心观点",
            "research-card",
        ),
        "injection": render_list_section(
            sections.get("injection", ""),
            "injection",
            "注塑机会专题",
            "Injection Molding Opportunities",
            "面向注塑设备、模具与材料商的专项机会",
            "inj-card",
        ),
        "nextweek": render_nextweek(sections.get("nextweek", "")),
        "sources": render_sources(sections.get("sources", "")),
    }

    for key, value in rendered.items():
        placeholder = "{{" + key + "}}"
        template = template.replace(placeholder, value)

    # 清理未替换的占位符
    template = re.sub(r"\{\{[a-zA-Z0-9_]+\}\}", "", template)

    return template


def main():
    html = render_all()
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"HTML 已渲染: {OUT_PATH}")


if __name__ == "__main__":
    main()
