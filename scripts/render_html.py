#!/usr/bin/env python3
"""Render Agent-generated HTML into a polished weekly report template."""

from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "templates" / "weekly.html"
INPUT_PATH = ROOT / "agent.html"
OUTPUT_PATH = ROOT / "index.html"

SECTION_MAP = {
    "本周总览": "overview",
    "一周总览": "overview",
    "总览": "overview",
    "overview": "overview",
    "各地市场动态": "markets",
    "市场动态": "markets",
    "全球市场": "markets",
    "区域市场": "markets",
    "政策动态": "policy",
    "政策法规": "policy",
    "车企动态": "oem",
    "企业动态": "oem",
    "调研报告": "research",
    "机构观点": "research",
    "调研报告/机构观点": "research",
    "行业研究": "research",
    "注塑机会": "injection",
    "注塑机": "injection",
    "注塑机会专题": "injection",
    "下周关注": "nextweek",
    "下周展望": "nextweek",
    "未来展望": "nextweek",
}


TITLE_PATTERNS = [
    re.compile(r"汽车行业.*周报", re.I),
    re.compile(r"全球汽车.*周报", re.I),
]


def extract_title(soup: BeautifulSoup) -> str:
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        title = title_tag.get_text(strip=True)
    else:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    title = re.sub(r"[\-–—]\s*\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2}[日]?\s*$", "", title).strip()
    if title:
        return title
    return "全球汽车行业深度周报"


def extract_date(soup: BeautifulSoup) -> str:
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2}[日]?)", text)
    if m:
        return m.group(1)
    return ""


def classify_section(title: str) -> str:
    title = title.strip().lower().replace(" ", "").replace("/", "")
    for key, val in SECTION_MAP.items():
        if key.lower().replace(" ", "").replace("/", "") in title:
            return val
    return ""


def _is_structural(tag) -> bool:
    classes = tag.get("class") or []
    return any(re.search(r"title|content|header|footer|meta", cls) for cls in classes)


def _is_wrapper(tag) -> bool:
    classes = tag.get("class") or []
    return any(
        any(w in cls for w in ["grid", "cards", "items", "container", "list"])
        for cls in classes
    )


def find_top_cards(soup: BeautifulSoup, card_pattern: re.Pattern) -> list:
    """Find top-level cards inside a section, expanding grid wrappers when needed."""
    candidates = soup.find_all(class_=card_pattern)
    cards = [c for c in candidates if not _is_structural(c)]
    # Keep only top-level cards (remove nested ones)
    top_cards = []
    for c in cards:
        if not any(c != p and c in p.descendants for p in cards):
            top_cards.append(c)
    # If a single wrapper remains, expand it
    if len(top_cards) == 1 and _is_wrapper(top_cards[0]):
        inner = top_cards[0].find_all(class_=card_pattern, recursive=False)
        inner = [c for c in inner if not _is_structural(c)]
        if inner:
            return inner
        inner2 = top_cards[0].find_all(["div", "article"], recursive=False)
        if inner2:
            return inner2
    return top_cards


def _is_tag_or_label(child) -> bool:
    """Filter out tag/label/badge/pill elements."""
    cls = " ".join(child.get("class") or [])
    if re.search(r"tag|label|badge|pill|chip|meta", cls):
        return True
    if child.name == "span" and len(child.find_all()) == 0:
        txt = child.get_text(strip=True)
        if len(txt) <= 6 and ("机会" in txt or "政策" in txt or "原文" in txt or "注塑" in txt or "风险" in txt):
            return True
    return False


def extract_card_text(card: BeautifulSoup) -> tuple:
    """Extract (title, content) from a card element."""
    title = ""
    # Try explicit title class
    for t in card.find_all(["div", "h3", "h4", "span"], class_=re.compile(r"title|heading"), recursive=False):
        title = t.get_text(strip=True)
        break
    # Try strong/b as title
    if not title:
        strong = card.find(["strong", "b"], recursive=False)
        if strong:
            title = strong.get_text(strip=True)
    # Fallback: first line of text
    if not title:
        title = card.get_text(" ", strip=True).split("。")[0].split("\n")[0][:50]

    content = ""
    for child in card.find_all(recursive=False):
        if _is_tag_or_label(child):
            continue
        if child.get_text(strip=True) == title:
            continue
        if child.name in ("h3", "h4") and not child.get("class"):
            continue
        if child.get("class") and any(re.search(r"title|heading", c) for c in child.get("class", [])):
            continue
        content += " " + child.get_text(" ", strip=True)
    content = content.strip()
    if not content:
        content = card.get_text(" ", strip=True).replace(title, "", 1).strip()
    return title, content


def extract_sections(soup) -> dict:
    if isinstance(soup, str):
        soup = BeautifulSoup(soup, "html.parser")
    sections = {}
    body = soup.body or soup

    # Strategy 1: sections/divs with id like section-N or semantic id
    candidates = []
    for tag in body.find_all(["section", "div"]):
        sec_id = tag.get("id", "")
        if sec_id.startswith("section-") or sec_id in set(SECTION_MAP.values()):
            candidates.append(tag)

    # Strategy 2: any container whose first h2 matches a known title
    if not candidates:
        for tag in body.find_all(["section", "div"]):
            h2 = tag.find("h2")
            if h2 and classify_section(h2.get_text(strip=True)):
                candidates.append(tag)

    for tag in candidates:
        sec_id = tag.get("id", "")
        key = ""
        if sec_id.startswith("section-"):
            heading = tag.find(["h2", "h3"])
            if heading:
                key = classify_section(heading.get_text(strip=True))
        else:
            key = sec_id if sec_id in set(SECTION_MAP.values()) else ""

        if not key:
            heading = tag.find(["h2", "h3"])
            if heading:
                key = classify_section(heading.get_text(strip=True))

        if key:
            inner = ""
            for child in tag.find_all(recursive=False):
                if child.name in ("h2", "h3"):
                    continue
                inner += str(child)
            sections[key] = inner

    return sections


def render_overview(inner_html: str) -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    cards = find_top_cards(soup, re.compile(r"hotspot|stat|overview-card"))
    cards_html = []
    for i, card in enumerate(cards[:6], 1):
        title, desc = extract_card_text(card)
        cards_html.append(
            f'<div class="overview-card">'
            f'<div class="card-number">{i:02d}</div>'
            f'<h3>{title}</h3><p>{desc}</p></div>'
        )
    ul = soup.find("ul")
    bullets = str(ul) if ul else ""
    if cards_html:
        return '<div class="overview-grid">\n' + "\n".join(cards_html) + "\n</div>\n" + bullets
    return inner_html


def render_markets(inner_html: str) -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    cards = find_top_cards(soup, re.compile(r"card|region|market"))
    if not cards:
        cards = soup.find_all(["h3"])

    region_keywords = {
        "中国": "region-cn", "北美": "region-na", "美国": "region-na", "加拿大": "region-na",
        "欧洲": "region-eu", "欧盟": "region-eu", "德国": "region-eu",
        "东南亚": "region-sea", "泰国": "region-sea", "印尼": "region-sea", "越南": "region-sea",
        "南美": "region-sa", "巴西": "region-sa", "墨西哥": "region-sa", "阿根廷": "region-sa",
        "印度": "region-in", "俄罗斯": "region-ru", "澳洲": "region-au", "澳大利亚": "region-au",
        "日韩": "region-jp", "日本": "region-jp", "韩国": "region-jp",
    }
    used = set()
    cards_html = []
    for card in cards:
        title, content = extract_card_text(card)
        region_cls = "region-global"
        for kw, cls in region_keywords.items():
            if kw in title and cls not in used:
                region_cls = cls
                used.add(cls)
                break
        cards_html.append(
            f'<article class="region-card {region_cls}">'
            f'<div class="region-tag">{title}</div>'
            f'<div class="region-content"><p>{content}</p></div>'
            f'</article>'
        )
    if cards_html:
        return '<div class="markets-grid">\n' + "\n".join(cards_html) + "\n</div>"
    return inner_html


def render_generic_cards(inner_html: str, key: str) -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    cards = find_top_cards(soup, re.compile(r"card|item"))
    if not cards:
        # If no card wrappers, treat h3 subsections as cards
        cards = []
        for h3 in soup.find_all("h3"):
            # Collect following siblings until next h3 or h2
            content_html = ""
            for sib in h3.find_next_siblings():
                if sib.name in ("h3", "h2"):
                    break
                content_html += " " + sib.get_text(" ", strip=True)
            wrapper = BeautifulSoup(f'<div><div class="card-title">{h3.get_text(strip=True)}</div>'
                                    f'<div class="card-content">{content_html}</div></div>', "html.parser")
            cards.append(wrapper.div)

    cards_html = []
    card_cls = f"{key}-card"
    grid_cls = f"{key}-grid"
    for card in cards:
        title, content = extract_card_text(card)
        cards_html.append(
            f'<article class="{card_cls}">'
            f'<div class="{card_cls}-title">{title}</div>'
            f'<div class="{card_cls}-content">{content}</div>'
            f'</article>'
        )
    if cards_html:
        return f'<div class="{grid_cls}">\n' + "\n".join(cards_html) + "\n</div>"
    return inner_html


def render_nextweek(inner_html: str) -> str:
    soup = BeautifulSoup(inner_html, "html.parser")
    ul = soup.find("ul")
    if ul:
        return f'<div class="next-week">\n{str(ul)}\n</div>'
    text = soup.get_text("\n", strip=True)
    if not text:
        text = "• 持续关注主要市场月度销量数据\n• 跟踪欧盟对华电动车关税后续进展\n• 关注固态电池与一体化压铸技术落地动态"
    return f'<div class="next-week"><ul>\n<li>{"</li>\n<li>".join(line.lstrip("•- ") for line in text.splitlines() if line.strip())}</li>\n</ul></div>'


def render_section_html(key: str, inner_html: str) -> str:
    if not inner_html.strip():
        return ""
    if key == "overview":
        return render_overview(inner_html)
    if key == "markets":
        return render_markets(inner_html)
    if key in ("policy", "oem", "research", "injection"):
        return render_generic_cards(inner_html, key)
    if key == "nextweek":
        return render_nextweek(inner_html)
    return inner_html


def build_sources_text() -> str:
    return (
        "MarkLines、乘联会(CPCA)、中汽协(CAAM)、ACEA、GAIKINDO、"
        "TAI/FTI、ANFAVEA/Fenabrave、SIAM、AEB、盖世汽车、36氪、"
        "界面新闻、AlixPartners、麦肯锡、Maybank、爱建证券"
    )


def render():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"未找到 Agent 生成的 HTML: {INPUT_PATH}")
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"未找到模板: {TEMPLATE_PATH}")

    html = INPUT_PATH.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    title = extract_title(soup)
    date = extract_date(soup)
    team = "YZM海外汽车行业拓展项目组"

    sections = extract_sections(soup)

    rendered = {}
    for key in ["overview", "markets", "policy", "oem", "research", "injection", "nextweek"]:
        rendered[key] = render_section_html(key, sections.get(key, ""))

    section_titles = {
        "overview": ("本周总览", "Overview"),
        "markets": ("各地市场动态", "Markets"),
        "policy": ("政策动态", "Policy"),
        "oem": ("车企动态", "OEM"),
        "research": ("调研报告/机构观点", "Research"),
        "injection": ("注塑机会专题", "Injection"),
        "nextweek": ("下周关注", "Next Week"),
    }

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    template = template.replace("{{title}}", title)
    template = template.replace("{{date}}", date)
    template = template.replace("{{team}}", team)
    for key, val in rendered.items():
        cn, en = section_titles[key]
        wrapped = f'<section class="section" id="{key}">\n<h2 class="section-title"><span>{en}</span>{cn}</h2>\n{val}\n</section>\n'
        template = template.replace(f"{{{{{key}}}}}", wrapped)
    template = template.replace("{{sources}}", build_sources_text())

    OUTPUT_PATH.write_text(template, encoding="utf-8")
    print(f"HTML 已渲染：{OUTPUT_PATH}")


if __name__ == "__main__":
    render()
