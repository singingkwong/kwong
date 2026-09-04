#!/usr/bin/env python3
"""
Render weekly report HTML from Agent-generated HTML using the original visual template.

Workflow:
1. Read templates/weekly.html (the original beautiful design).
2. Read agent.html (Agent generated).
3. Extract sections from agent.html by h2/section id.
4. Convert each section's content into the template's card structure.
5. Replace placeholders in the template and write index.html.
"""

import re
from pathlib import Path
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
AGENT_HTML_PATH = ROOT / "agent.html"
TEMPLATE_PATH = ROOT / "templates" / "weekly.html"
OUTPUT_PATH = ROOT / "index.html"

TITLE_SUFFIX_RE = re.compile(r"[\-–—]\s*\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2}[日]?\s*$")
TRAILING_JUNK_RE = re.compile(r"\s*(原文|政策|市场|车企|注塑机会|来源：.*?)\s*$")

SECTION_KEYWORDS = {
    "overview": ["本周总览", "本周概览", "本周看点", "核心看点"],
    "markets": ["各地市场动态", "市场动态", "全球市场", "区域市场"],
    "policy": ["政策动态", "政策法规", "政策"],
    "oem": ["车企动态", "整车企业", "车企", "OEM"],
    "research": ["调研报告", "机构观点", "研究报告", "机构研报"],
    "injection": ["注塑机会", "注塑", "机会专题"],
    "nextweek": ["下周关注", "下周看点", "下周"],
}


def map_section_key(title: str) -> str:
    title = title.strip().lower()
    for key, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in title:
                return key
    return ""


def extract_title(agent_html: str) -> str:
    soup = BeautifulSoup(agent_html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "全球汽车行业深度周报"
    title = TITLE_SUFFIX_RE.sub("", title).strip()
    title = re.sub(r"\s*-\s*$", "", title).strip()
    if not title:
        title = "全球汽车行业深度周报"
    return title


def extract_date(agent_html: str) -> str:
    soup = BeautifulSoup(agent_html, "html.parser")
    # Try header
    for cls in ["hero-date", "report-date", "date"]:
        tag = soup.find(class_=cls)
        if tag:
            return tag.get_text(strip=True)
    # Try title
    title_tag = soup.find("title")
    if title_tag:
        m = re.search(r"(\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2}[日]?)", title_tag.get_text())
        if m:
            return normalize_date(m.group(1))
    # Default
    from datetime import datetime
    return datetime.now().strftime("%Y年%m月%d日")


def normalize_date(date_str: str) -> str:
    m = re.search(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})[日]?", date_str)
    if m:
        return f"{m.group(1)}年{int(m.group(2)):02d}月{int(m.group(3)):02d}日"
    return date_str


def extract_team(agent_html: str) -> str:
    soup = BeautifulSoup(agent_html, "html.parser")
    for cls in ["hero-team", "report-team", "team"]:
        tag = soup.find(class_=cls)
        if tag:
            return tag.get_text(strip=True).replace("编制团队：", "").strip()
    header = soup.find("header") or soup.find(class_="header")
    if header:
        text = header.get_text(" ", strip=True)
        m = re.search(r"编制团队[：:]\s*(.+)", text)
        if m:
            return m.group(1).strip()
    return "YZM海外汽车行业拓展项目组"


def extract_sections(agent_html: str) -> dict:
    soup = BeautifulSoup(agent_html, "html.parser")
    body = soup.body
    if not body:
        return {}

    sections = {}
    # Try explicit sections with h2
    for section in body.find_all("section"):
        h2 = section.find("h2")
        if not h2:
            continue
        key = map_section_key(h2.get_text(strip=True))
        if not key:
            continue
        # Remove h2 from inner html to avoid duplication
        inner = "".join(str(child) for child in section.children if not (getattr(child, "name", None) == "h2"))
        sections[key] = inner.strip()

    # Fallback: any h2 that is not inside a section
    for h2 in body.find_all("h2"):
        key = map_section_key(h2.get_text(strip=True))
        if not key or key in sections:
            continue
        inner = ""
        for sib in h2.find_next_siblings():
            if sib.name in ("h2",):
                break
            inner += str(sib)
        sections[key] = inner.strip()

    return sections


def _is_structural(tag) -> bool:
    cls = " ".join(tag.get("class") or [])
    return any(k in cls for k in ["title", "header", "heading", "label", "tag"])


def _is_wrapper(tag) -> bool:
    cls = " ".join(tag.get("class") or [])
    return any(w in cls for w in ["grid", "cards", "items", "container", "list"])


def _is_tag_or_label(tag) -> bool:
    cls = " ".join(tag.get("class") or [])
    if any(k in cls for k in ["tag", "label", "badge", "source", "meta"]):
        return True
    return False


def find_top_cards(soup, card_pattern):
    candidates = soup.find_all(class_=card_pattern)
    # Filter out structural labels
    cards = [c for c in candidates if not _is_structural(c)]
    # Keep only top-level among remaining
    top_cards = []
    for c in cards:
        if not any(c != p and c in p.descendants for p in cards):
            top_cards.append(c)
    # If only one top-level and it's a wrapper, expand it
    if len(top_cards) == 1 and _is_wrapper(top_cards[0]):
        inner = top_cards[0].find_all(class_=card_pattern, recursive=False)
        inner = [c for c in inner if not _is_structural(c)]
        if inner:
            return inner
        # Fallback: any direct div children
        inner2 = top_cards[0].find_all(["div", "article"], recursive=False)
        inner2 = [c for c in inner2 if not _is_structural(c)]
        if inner2:
            return inner2
    return top_cards


def extract_card_text(card):
    title = ""
    content = ""

    # Try title classes
    title_tag = card.find(class_=re.compile(r"title|heading|header"))
    if title_tag and not _is_tag_or_label(title_tag):
        title = title_tag.get_text(" ", strip=True)
        title_tag.extract()

    # Try content classes
    content_tag = card.find(class_=re.compile(r"content|body|desc|summary|detail"))
    if content_tag:
        content = content_tag.get_text(" ", strip=True)
    else:
        # Remove tag/label children first
        for junk in card.find_all(class_=re.compile(r"tag|label|badge|source|meta")):
            junk.extract()
        content = card.get_text(" ", strip=True)

    title = re.sub(r"^\d+[\.、]\s*", "", title)
    content = TRAILING_JUNK_RE.sub("", content).strip()
    # Remove duplicated title prefix in content
    if title and content.startswith(title):
        content = content[len(title):].strip()
    return title, content


def render_overview(inner_html: str) -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    cards = find_top_cards(soup, re.compile(r"hotspot|stat|overview-card"))
    cards_html = []
    for idx, card in enumerate(cards[:4], 1):
        title, content = extract_card_text(card)
        # If title is just a number/ordinal, derive from content
        if not title or re.match(r"^\d+$", title) or len(title) < 8:
            if content:
                parts = re.split(r"[。；;]", content, 1)
                if len(parts) > 1 and len(parts[0]) > 8:
                    title = parts[0].strip()
                    content = parts[1].strip()
                else:
                    title = content[:40]
                    content = content[40:].strip()
        if not title:
            title = f"热点{idx}"
        cards_html.append(
            f'<article class="overview-card">'
            f'<div class="card-number">{idx:02d}</div>'
            f'<h3 class="overview-card-title">{title}</h3>'
            f'<p class="overview-card-desc">{content}</p>'
            f'</article>'
        )
    # Core highlights list
    ul = soup.find("ul")
    highlights_html = ""
    if ul:
        highlights_html = f'<div class="core-highlights"><h3>核心看点</h3>\n{str(ul)}\n</div>'
    grid = '<div class="overview-grid">\n' + "\n".join(cards_html) + "\n</div>" if cards_html else ""
    return grid + "\n" + highlights_html


def render_markets(inner_html: str) -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    cards = find_top_cards(soup, re.compile(r"card|region|market"))
    if not cards:
        cards = soup.find_all("h3")
    region_keywords = {
        "中国": "region-cn", "北美": "region-na", "美国": "region-na", "加拿大": "region-na",
        "欧洲": "region-eu", "欧盟": "region-eu", "德国": "region-eu",
        "东南亚": "region-sea", "泰国": "region-sea", "印尼": "region-sea", "越南": "region-sea",
        "南美": "region-sa", "巴西": "region-sa", "墨西哥": "region-sa", "阿根廷": "region-sa",
        "印度": "region-in", "俄罗斯": "region-ru", "澳洲": "region-au", "澳大利亚": "region-au",
        "日韩": "region-jp", "日本": "region-jp", "韩国": "region-jp",
    }
    region_ids = {
        "region-cn": "china", "region-na": "na", "region-eu": "eu", "region-sea": "sea",
        "region-sa": "sa", "region-in": "india", "region-ru": "russia", "region-au": "australia",
        "region-jp": "japan-korea", "region-global": "global",
    }
    used = set()
    cards_html = []
    for card in cards:
        if card.name == "h3":
            title = card.get_text(strip=True)
            content = ""
            for sib in card.find_next_siblings():
                if sib.name in ("h3", "h2"):
                    break
                content += " " + sib.get_text(" ", strip=True)
        else:
            title, content = extract_card_text(card)
        if not title.strip():
            continue
        region_cls = "region-global"
        for kw, cls in region_keywords.items():
            if kw in title and cls not in used:
                region_cls = cls
                used.add(cls)
                break
        region_id = region_ids.get(region_cls, "")
        id_attr = f' id="{region_id}"' if region_id else ""
        cards_html.append(
            f'<article class="region-card {region_cls}"{id_attr}>'
            f'<div class="region-tag">{title}</div>'
            f'<div class="region-content"><p>{content}</p></div>'
            f'</article>'
        )
    if cards_html:
        return '<div class="markets-grid">\n' + "\n".join(cards_html) + "\n</div>"
    return inner_html


def _card_items_from_list(card, section_title: str):
    """Expand a single card that contains a list into multiple items."""
    items = []
    ul = card.find(["ul", "ol"])
    if ul:
        for li in ul.find_all("li", recursive=False):
            text = li.get_text(" ", strip=True)
            # Try to split "Region: content"
            m = re.match(r"^([^：:;]+)[：:;]\s*(.+)$", text, re.DOTALL)
            if m:
                items.append((m.group(1).strip(), m.group(2).strip()))
            else:
                items.append((section_title or "要点", text))
        return items
    return []


def render_generic_cards(inner_html: str, key: str, section_title: str = "") -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    cards = find_top_cards(soup, re.compile(r"card|item"))
    if not cards:
        # If no card wrappers, treat h3 subsections as cards
        cards = []
        for h3 in soup.find_all("h3"):
            content_html = ""
            for sib in h3.find_next_siblings():
                if sib.name in ("h3", "h2"):
                    break
                content_html += " " + sib.get_text(" ", strip=True)
            wrapper = BeautifulSoup(f'<div><div class="card-title">{h3.get_text(strip=True)}</div>'
                                    f'<div class="card-content">{content_html}</div></div>', "html.parser")
            cards.append(wrapper.div)

    items = []
    for card in cards:
        # If a card contains a list with multiple items, expand them
        expanded = _card_items_from_list(card, section_title)
        if len(expanded) > 1:
            items.extend(expanded)
        else:
            title, content = extract_card_text(card)
            if not title.strip() or title.strip() == content.strip():
                title = section_title or "详情"
            items.append((title, content))

    if not items:
        return inner_html

    card_cls = f"{key}-card"
    grid_cls = f"{key}-grid"
    cards_html = []
    for title, content in items:
        cards_html.append(
            f'<article class="{card_cls}">'
            f'<div class="{card_cls}-title">{title}</div>'
            f'<div class="{card_cls}-content">{content}</div>'
            f'</article>'
        )
    return f'<div class="{grid_cls}">\n' + "\n".join(cards_html) + "\n</div>"


def render_nextweek(inner_html: str) -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    ul = soup.find("ul")
    if ul:
        return f'<div class="next-week">\n{str(ul)}\n</div>'
    text = soup.get_text("\n", strip=True)
    if not text:
        text = "• 持续关注主要市场月度销量数据\n• 跟踪欧盟对华电动车关税后续进展\n• 关注固态电池与一体化压铸技术落地动态"
    return f'<div class="next-week"><ul>\n<li>{"</li>\n<li>".join(line.lstrip("•- ") for line in text.splitlines() if line.strip())}</li>\n</ul></div>'


def render_section_html(key: str, inner_html: str, section_title: str = "") -> str:
    if key == "nextweek":
        return render_nextweek(inner_html)
    if not inner_html.strip():
        return ""
    if key == "overview":
        return render_overview(inner_html)
    if key == "markets":
        return render_markets(inner_html)
    return render_generic_cards(inner_html, key, section_title)


def render_html(agent_html: str, template: str) -> str:
    title = extract_title(agent_html)
    date = extract_date(agent_html)
    team = extract_team(agent_html)
    sections = extract_sections(agent_html)

    rendered = {}
    title_map = {
        "overview": "本周总览",
        "markets": "各地市场动态",
        "policy": "政策动态",
        "oem": "车企动态",
        "research": "调研报告/机构观点",
        "injection": "注塑机会专题",
        "nextweek": "下周关注",
    }
    for key in ["overview", "markets", "policy", "oem", "research", "injection", "nextweek"]:
        section_title = title_map.get(key, "")
        rendered[key] = render_section_html(key, sections.get(key, ""), section_title)

    # Build sources section
    sources = sections.get("sources", "")
    if not sources:
        sources = (
            "MarkLines、乘联会(CPCA)、中汽协(CAAM)、ACEA、GAIKINDO、TAI/FTI、"
            "ANFAVEA/Fenabrave、SIAM、AEB、盖世汽车、36氪、界面新闻、AlixPartners、麦肯锡、Maybank、爱建证券"
        )
    sources_html = render_generic_cards(sources, "sources", "数据来源") if "<" in sources else f'<p>{sources}</p>'
    if "<" not in sources_html:
        sources_html = f'<p>{sources_html}</p>'

    # Compose full HTML with section wrappers
    section_order = [
        ("overview", "本周总览", "Overview"),
        ("markets", "各地市场动态", "Markets"),
        ("policy", "政策动态", "Policy"),
        ("oem", "车企动态", "OEMs"),
        ("research", "调研报告/机构观点", "Research"),
        ("injection", "注塑机会专题", "Injection"),
        ("nextweek", "下周关注", "Next Week"),
    ]
    sections_html = ""
    for key, cn, en in section_order:
        content = rendered.get(key, "")
        if not content.strip():
            continue
        sections_html += (
            f'<section class="section" id="{key}">\n'
            f'<h2 class="section-title"><span>{en}</span>{cn}</h2>\n'
            f'{content}\n'
            f'</section>\n'
        )
    sections_html += (
        f'<section class="section" id="sources">\n'
        f'<h2 class="section-title"><span>Sources</span>数据来源</h2>\n'
        f'<div class="sources-grid">\n{sources_html}\n</div>\n'
        f'</section>\n'
    )

    # Replace placeholders in template
    result = template
    result = result.replace("{{title}}", title)
    result = result.replace("{{date}}", date)
    result = result.replace("{{team}}", team)
    result = result.replace("{{overview}}", "")
    result = result.replace("{{markets}}", "")
    result = result.replace("{{policy}}", "")
    result = result.replace("{{oem}}", "")
    result = result.replace("{{research}}", "")
    result = result.replace("{{injection}}", "")
    result = result.replace("{{nextweek}}", "")
    result = result.replace("{{sources}}", "")

    # Insert sections into the main area: right after <main ...>
    main_start = result.find("<main")
    if main_start != -1:
        main_end = result.find(">", main_start)
        insert_pos = main_end + 1
        result = result[:insert_pos] + "\n" + sections_html + result[insert_pos:]
    else:
        # Fallback: before footer
        footer_pos = result.find("<footer>")
        if footer_pos != -1:
            result = result[:footer_pos] + sections_html + "\n" + result[footer_pos:]
        else:
            result += "\n" + sections_html

    # Clean up possible duplicated titles in hero
    result = re.sub(r'<h1[^>]*>.*?</h1>', f'<h1>{title}</h1>', result)
    return result


def main():
    agent_html = AGENT_HTML_PATH.read_text(encoding="utf-8")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    output = render_html(agent_html, template)
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"HTML rendered: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
