#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
渲染脚本：读取扣子 Agent 生成的 agent.html，套用优化版模板 templates/weekly.html。

模板中使用 {{placeholder}} 占位，本脚本负责：
- {{title}} / {{date}} / {{team}} / {{data_period}} / {{sources}}
- {{overview}} {{markets}} {{policy}} {{oem}} {{research}} {{injection}} {{nextweek}}
并输出最终的 index.html。

输出严格遵循新模板的卡片类名体系：
- 本周总览：.key-points + .kp-card
- 市场区域：.section + .subsection.region-* + .region-card / .news-card
- 政策：.policy-card / 车企：.oem-card / 调研：.research-card
- 注塑：.injection-section + .inj-card / 下周：.section + .next-week
"""
import datetime
import os
import re
import sys
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(PROJECT_ROOT, "templates", "weekly.html")
AGENT_HTML_PATH = os.path.join(PROJECT_ROOT, "agent.html")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "index.html")

COZE_API_BASE = "https://api.coze.cn"
DEFAULT_TEAM = "YZM海外汽车行业拓展项目组"

REGIONS: List[Dict[str, str]] = [
    {"name": "中国", "key": "china", "en": "China", "cls": "region-cn"},
    {"name": "东南亚", "key": "sea", "en": "Southeast Asia", "cls": "region-sea"},
    {"name": "印尼", "key": "sea", "en": "Indonesia", "cls": "region-sea"},
    {"name": "泰国", "key": "sea", "en": "Thailand", "cls": "region-sea"},
    {"name": "马来西亚", "key": "sea", "en": "Malaysia", "cls": "region-sea"},
    {"name": "越南", "key": "sea", "en": "Vietnam", "cls": "region-sea"},
    {"name": "南美", "key": "sa", "en": "South America", "cls": "region-sa"},
    {"name": "巴西", "key": "sa", "en": "Brazil", "cls": "region-sa"},
    {"name": "欧洲", "key": "eu", "en": "Europe", "cls": "region-eu"},
    {"name": "欧盟", "key": "eu", "en": "EU", "cls": "region-eu"},
    {"name": "德国", "key": "eu", "en": "Germany", "cls": "region-eu"},
    {"name": "法国", "key": "eu", "en": "France", "cls": "region-eu"},
    {"name": "北美", "key": "na", "en": "North America", "cls": "region-na"},
    {"name": "美国", "key": "na", "en": "USA", "cls": "region-na"},
    {"name": "印度", "key": "other", "en": "India", "cls": "region-other"},
    {"name": "俄罗斯", "key": "other", "en": "Russia", "cls": "region-other"},
    {"name": "澳洲", "key": "other", "en": "Australia", "cls": "region-other"},
    {"name": "澳大利亚", "key": "other", "en": "Australia", "cls": "region-other"},
    {"name": "日本", "key": "other", "en": "Japan", "cls": "region-other"},
    {"name": "韩国", "key": "other", "en": "Korea", "cls": "region-other"},
    {"name": "日韩", "key": "other", "en": "Japan & Korea", "cls": "region-other"},
    {"name": "亚洲", "key": "other", "en": "Asia", "cls": "region-other"},
]

POLICY_KEYWORDS = ["政策", "法规", "关税", "补贴", "标准", "监管", "双反", "贸易", "合规"]
OEM_KEYWORDS = ["车企", "整车", "品牌", "主机厂", "比亚迪", "特斯拉", "吉利", "奇瑞",
                "长安", "长城", "丰田", "大众", "宝马", "奔驰", "宁德时代", "蔚来",
                "小鹏", "理想", "Stellantis", "现代", "起亚"]
RESEARCH_KEYWORDS = ["报告", "调研", "研报", "观点", "预测", "分析", "机构", "咨询",
                     "麦肯锡", "BCG", "贝恩", "德勤", "普华永道", "AlixPartners", "评级"]
NEXT_KEYWORDS = ["下周", "下周关注", "本周关注", "关注", "日程", "前瞻", "数据发布"]
INJECTION_KEYWORDS = ["注塑", "模具", "内饰件", "外饰件", "一体化压铸", "轻量化",
                      "工程塑料", "碳纤维", "复合材料", "改性塑料", "注塑机"]


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------
def clean_text(text: str) -> str:
    """清理多余空白。"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def escape_html(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def today_cn() -> str:
    today = datetime.date.today()
    return f"{today.year}年{today.month:02d}月{today.day:02d}日"


def get_last_week_range() -> str:
    today = datetime.date.today()
    this_monday = today - datetime.timedelta(days=today.weekday())
    last_monday = this_monday - datetime.timedelta(days=7)
    last_sunday = this_monday - datetime.timedelta(days=1)
    return f"{last_monday.month}月{last_monday.day}日 - {last_sunday.month}月{last_sunday.day}日"


def highlight_numbers(text: str) -> str:
    """对正文中的关键数据加粗高亮：百分比、带单位数字、增长/下降趋势。不高亮裸数字（如 8月）。"""
    safe = escape_html(text)
    number_with_unit = r"\d+(?:\.\d+)?\s?(?:%|％|万辆|万台|万套|亿元|万元|吨|GWh|GW|kg|千克)"
    trend = r"(?:同比|环比)?(?:增长|大增|激增|暴涨|上涨|提升|攀升|下滑|下降|下跌|回落|微增|微降|放缓)[^，。；,;]*"
    pattern = re.compile(f"(?:{number_with_unit})|(?:{trend})")
    return pattern.sub(lambda m: f"<strong>{m.group(0)}</strong>", safe)


# ---------------------------------------------------------------------------
# Agent HTML 解析
# ---------------------------------------------------------------------------
TITLE_RE = re.compile(
    r"<(h2|div)([^>]*)>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)


def split_sections_by_title(full_html: str) -> List[Dict[str, str]]:
    """按 Agent HTML 里的章节标题切块。兼容 <h2> 与 <div class="...section-title...">。"""
    matches: List[re.Match] = []
    for m in TITLE_RE.finditer(full_html):
        tag, attrs, inner = m.group(1).lower(), m.group(2), m.group(3)
        if tag == "h2":
            matches.append(m)
        elif "section-title" in attrs:
            matches.append(m)

    sections: List[Dict[str, str]] = []
    for i, m in enumerate(matches):
        title = clean_text(re.sub(r"<[^>]+>", "", m.group(3)))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_html)
        body = full_html[start:end]
        if title:
            sections.append({"title": title, "body": body})
    return sections


def get_section_by_keyword(sections: List[Dict[str, str]], keywords: List[str]) -> Optional[Dict[str, str]]:
    for sec in sections:
        title = sec["title"]
        if any(k in title for k in keywords):
            return sec
    return None


def get_overview_section(sections: List[Dict[str, str]], full_html: str) -> Dict[str, str]:
    for sec in sections:
        if any(k in sec["title"] for k in ["本周总览", "核心看点", "本周看点", "一周概览", "总览"]):
            return sec
    return {"title": "本周总览", "body": full_html[:6000]}


_LINK_CHECK_CACHE: Dict[str, bool] = {}
_LINK_TIMEOUT = 8
_LINK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def _is_fake_link_format(href: str) -> bool:
    """快速剔除明显伪造/无效的链接格式，避免占用网络校验。"""
    low = href.lower()
    if low.startswith(("javascript:", "#", "mailto:", "data:", "你的", "原文", "待核")):
        return True
    if any(dom in low for dom in ("example.com", "test.com", "yourlink", "placeholder", ".local")):
        return True
    if "//" not in href or "." not in href.split("/", 3)[2]:
        return True
    return False


def _link_is_reachable(href: str) -> bool:
    """探测链接是否真实可用（HEAD 优先，失败回退 GET），带缓存避免重复请求。"""
    key = href.strip()
    if key in _LINK_CHECK_CACHE:
        return _LINK_CHECK_CACHE[key]
    ok = False
    for method in ("HEAD", "GET"):
        try:
            resp = requests.request(method, key, headers=_LINK_HEADERS,
                                    timeout=_LINK_TIMEOUT, allow_redirects=True,
                                    stream=True)
            if resp.status_code < 400:
                ok = True
                break
        except Exception:
            continue
    _LINK_CHECK_CACHE[key] = ok
    return ok


def _first_link(el) -> str:
    """返回元素内第一个可信 http(s) 外部链接 href。
    对链接做可达性校验：死链、伪链返回空串（有缓存，避免重复请求）。
    """
    if el is None:
        return ""
    a = el.find("a", href=True)
    if a:
        href = a["href"].strip()
        if href.startswith(("http://", "https://")):
            if _is_fake_link_format(href):
                return ""
            if not _link_is_reachable(href):
                return ""
            return href
    return ""


def _link_html(link: str) -> str:
    """生成"原文"按钮 HTML；无链接返回空串。"""
    if not link:
        return ""
    href = escape_html(link)
    return (f'<a class="src-link" href="{href}" target="_blank" rel="noopener nofollow">'
            f'<span class="src-link-ico">🔗</span>原文</a>')


# ---- 三要点结构化（关键数据/影响分析/趋势判断）----
_POINT_LABELS = ("关键数据", "影响分析", "趋势判断")

def _split_points(body: str) -> Optional[Dict[str, str]]:
    """从正文解析出 关键数据/影响分析/趋势判断 三段；全部找到才返回，否则 None。"""
    hits: List[tuple] = []
    for lab in _POINT_LABELS:
        idx = body.find(lab)
        if idx == -1:
            return None
        sep = idx + len(lab)
        if body[sep:sep + 1] == "/" and body[sep + 1:sep + 3] == "事件":
            sep += 3
        while sep < len(body) and body[sep] in " ：:（）()/、\n":
            sep += 1
        hits.append((lab, idx, sep))
    hits.sort(key=lambda x: x[1])
    result: Dict[str, str] = {}
    for k, (lab, _, start) in enumerate(hits):
        end = hits[k + 1][1] if k + 1 < len(hits) else len(body)
        seg = body[start:end].strip(" ：:（）()/、\n")
        seg = re.sub(r"\s*原文\s*$", "", seg).strip()
        # 剥掉段末尾 Agent 自标的"来源：xxx"，避免与底部"数据来源"行重复
        seg = re.sub(r"\s*来源[:：]\s*\S+$", "", seg).strip()
        result[lab] = seg
    return result

def _render_points_html(body: str) -> Optional[str]:
    pts = _split_points(body)
    if not pts:
        return None
    label_map = {
        "关键数据": ("point-key", "📊", "关键数据 / 事件"),
        "影响分析": ("point-impact", "🔍", "影响分析"),
        "趋势判断": ("point-trend", "📈", "趋势判断"),
    }
    rows = []
    for lab in _POINT_LABELS:
        val = pts.get(lab, "")
        if not val:
            continue
        cls, icon, head = label_map[lab]
        rows.append(
            f'<div class="point {cls}">'
            f'<span class="point-head">{icon} {escape_html(head)}</span>'
            f'<span class="point-text">{highlight_numbers(val)}</span>'
            f'</div>'
        )
    if not rows:
        return None
    return '<div class="points-block">' + "".join(rows) + '</div>'

def _card_rich_body(body: str) -> str:
    """优先三要点结构；无三点标记回落高亮普通正文。"""
    rich = _render_points_html(body)
    if rich:
        return rich
    return highlight_numbers(re.sub(r"\s*原文$", "", body).strip())


# ---- 数据来源识别 ----
_SOURCE_BY_HOST = {
    "marklines.com": "MarkLines",
    "caam.org.cn": "中汽协(CAAM)",
    "cpcadata.com": "乘联会(CPCA)",
    "acea.auto": "欧洲汽车制造商协会(ACEA)",
    "gaikindo.or.id": "印尼汽车工业协会(GAIKINDO)",
    "anfavea.com.br": "巴西汽车工业协会(ANFAVEA)",
    "siam.in": "印度汽车制造商协会(SIAM)",
    "acma.in": "印度ACMA",
    "motownindia.com": "Motown India",
    "autonews.com": "Automotive News",
    "insideevs.com": "InsideEVs",
    "electrive.com": "Electrive",
    "reuters.com": "路透社",
    "bloomberg.com": "彭博社",
    "gov.cn": "中国政府网",
    "mofcom.gov.cn": "商务部",
    "mil.gov.cn": "工信部",
    "36kr.com": "36氪",
    "geekcar.com": "盖世汽车",
    "huanqiu.com": "环球网",
}
_SOURCE_DEFAULT = "来源待核"

def _source_label(href: str) -> str:
    if not href:
        return _SOURCE_DEFAULT
    try:
        from urllib.parse import urlparse
        host = urlparse(href).netloc.lower().lstrip("www.")
    except Exception:
        host = ""
    for dom, name in _SOURCE_BY_HOST.items():
        if dom in host:
            return name
    if host:
        return host.split(".")[0].capitalize() or _SOURCE_DEFAULT
    return _SOURCE_DEFAULT

def _body_source(body: str) -> str:
    m = re.search(r"来源[:：]\s*([^\s，,。；;|]+)", body or "")
    return m.group(1).strip() if m else ""

def _source_html(link: str, body: str = "") -> str:
    src = _body_source(body) or _source_label(link)
    return f'<div class="news-source">📌 数据来源：{escape_html(src)}</div>'


def _el_text(el) -> str:
    return clean_text(el.get_text(" ", strip=True)) if el is not None else ""


def _card_title(c) -> str:
    """从一张卡片中提取标题，兼容 Agent 真实类名与通用标签。"""
    for sel in (".hotspot-title", ".card-title"):
        el = c.select_one(sel)
        if el:
            clone = BeautifulSoup(str(el), "html.parser").find()
            for sp in clone.find_all("span"):
                sp.decompose()
            return _el_text(clone)
    for tag in ("h3", "h4", "h5"):
        el = c.find(tag)
        if el:
            return _el_text(el)
    strong = c.find(["strong", "b"])
    return _el_text(strong)


def _card_body(c) -> str:
    """从一张卡片中提取正文，兼容 .card-content / .hotspot-desc / .news-body 及整体文本。"""
    for sel in (".card-content", ".hotspot-desc", ".news-body"):
        el = c.select_one(sel)
        if el:
            return _el_text(el)
    clone_root = BeautifulSoup(str(c), "html.parser").find()
    if clone_root:
        for sel in (".hotspot-title", ".card-title", ".hotspot-tag", ".tag",
                    ".tag-trend", ".tag-policy", ".tag-risk", ".news-source"):
            for el in clone_root.select(sel):
                el.decompose()
        return _el_text(clone_root)
    return _el_text(c)


def _split_card_by_links(card_el) -> List[Dict[str, object]]:
    """当一张卡片里含 >=2 个原文链接时，按链接把内容拆成多条。

    Agent 偶发会把多条独立动态合并进一张 .card（正文用"原文"分隔，每条跟一个链接）。
    策略：按文档顺序遍历，链接之前累积的文本归属该链接，文本末尾的"原文"去除。
    """
    anchors = card_el.find_all("a")
    links = [a.get("href", "").strip() for a in anchors if a.get("href", "").startswith("http")]
    if len(links) < 2:
        return []

    # 正文文本：取 .card-content/.hotspot-desc/.news-body 优先，否则整卡
    content_el = card_el.select_one(".card-content, .hotspot-desc, .news-body")
    if content_el:
        body_raw = str(content_el)
    else:
        body_raw = str(card_el)
    # 去掉正文内可能的链接标签，保留纯文本与换行边界
    body_text = re.sub(r"<a[^>]*>.*?</a>", " ", body_raw, flags=re.DOTALL)
    body_text = re.sub(r"<br\s*/?>", "\n", body_text)
    body_text = re.sub(r"</(p|div|li)>", "\n", body_text)
    body_text = clean_text(re.sub(r"<[^>]+>", "\n", body_text))

    # 拆分多条动态：按换行切，再把过短碎片并入上一条
    raw_lines = [ln.strip() for ln in re.split(r"[\n]+", body_text) if ln.strip()]
    # 去掉"原文"残留与纯标签词
    lines: List[str] = []
    for ln in raw_lines:
        ln = re.sub(r"\s*原文\s*$", "", ln).strip()
        ln = re.sub(r"^原文\s*", "", ln).strip()
        if len(ln) < 6:
            continue
        lines.append(ln)
    # 若没有换行边界，则按"。原文"或句号粗拆（保守，仅在明显多条时）
    if len(lines) < len(links) and len(links) >= 2:
        flat = " ".join(lines)
        # 按中文句号切，保留句号
        sents = re.split(r"(?<=。)", flat)
        lines = [s.strip() for s in sents if len(s.strip()) >= 10]

    if len(lines) < 2:
        return []

    # 链接按顺序配对到每一条动态
    results: List[Dict[str, object]] = []
    seen = set()
    for i, t in enumerate(lines):
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 8 or t in seen:
            continue
        seen.add(t)
        item: Dict[str, object] = {"title": "", "body": t}
        if i < len(links):
            item["link"] = links[i]
        results.append(item)
    return results


def extract_cards_from_body(body: str) -> List[Dict[str, object]]:
    """从一段 HTML 中提取标题+正文+原文链接。

    兼容 Agent 真实结构：.hotspot-card(.hotspot-title/.hotspot-desc/.hotspot-source)、
    .card(.card-title/.card-content/.source-link)，以及模板卡片类、li、p。
    """
    soup = BeautifulSoup(body, "html.parser")
    cards: List[Dict[str, object]] = []

    candidates = soup.select(
        ".card, .hotspot-card, .news-card, .region-card, .policy-card, "
        ".oem-card, .research-card, .inj-card, .kp-card"
    )
    for c in candidates:
        # 跳过 .card-grid / .hotspot-grid 等容器（类名前缀误匹配）
        if c.get("class") and any(x in c.get("class", []) for x in ("card-grid", "hotspot-grid", "kp-grid", "overview-grid")):
            continue
        title = _card_title(c)
        body_text = _card_body(c)
        if title and body_text.startswith(title):
            body_text = body_text[len(title):].strip(" -—:：|")

        # 一张卡片里若含多个原文链接（Agent 偶发把多条动态合并进一张卡），
        # 按链接把正文拆成多条，链接就近归属其前面的文本。
        chunks = _split_card_by_links(c)
        if chunks:
            cards.extend(chunks)
            continue

        if not title and len(body_text) >= 12:
            title = body_text[:24]
        if title or body_text:
            item: Dict[str, object] = {"title": title or "", "body": body_text}
            link = _first_link(c)
            if link:
                item["link"] = link
            cards.append(item)

    if cards:
        return cards

    # 其次：li 列表（政策/车企/调研常用 ul.styled-list > li）
    li_cards: List[Dict[str, object]] = []
    for li in soup.find_all("li"):
        txt = _el_text(li)
        if len(txt) < 10:
            continue
        item: Dict[str, object] = {"title": "", "body": txt}
        link = _first_link(li)
        if link:
            item["link"] = link
        li_cards.append(item)
    if li_cards:
        return li_cards

    # 最后：p 段落（总览引言等）
    for p in soup.find_all("p"):
        txt = _el_text(p)
        if len(txt) < 20:
            continue
        item = {"title": "", "body": txt}
        link = _first_link(p)
        if link:
            item["link"] = link
        cards.append(item)
    return cards


def extract_hotspot_cards(full_html: str) -> List[Dict[str, object]]:
    """提取 Agent 总览热点卡（.hotspot-grid > .hotspot-card）。

    这类卡片位于所有 <section> 之前，需从完整 HTML 单独解析。
    返回 title/body/link/tags。
    """
    soup = BeautifulSoup(full_html, "html.parser")
    out: List[Dict[str, object]] = []
    for c in soup.select(".hotspot-card"):
        title = _el_text(c.select_one(".hotspot-title"))
        desc = _el_text(c.select_one(".hotspot-desc"))
        tags = [_el_text(t) for t in c.select(".hotspot-tag")]
        if not title:
            continue
        item: Dict[str, object] = {"title": title, "body": desc, "tags": tags}
        link = _first_link(c)
        if link:
            item["link"] = link
        out.append(item)
    return out


def extract_li_items(body: str) -> List[str]:
    soup = BeautifulSoup(body, "html.parser")
    items: List[str] = []
    for li in soup.find_all("li"):
        txt = clean_text(li.get_text(" ", strip=True))
        if len(txt) >= 8:
            items.append(txt)
    if items:
        return items
    for p in soup.find_all("p"):
        txt = clean_text(p.get_text(" ", strip=True))
        if len(txt) >= 12:
            items.append(txt)
    return items


def extract_summary(overview_body: str) -> str:
    soup = BeautifulSoup(overview_body, "html.parser")
    for p in soup.find_all("p"):
        txt = clean_text(p.get_text(" ", strip=True))
        if len(txt) >= 30:
            return txt[:220]
    text = clean_text(soup.get_text(" ", strip=True))
    return text[:220] if text else "本周全球汽车行业动态汇总。"


# ---------------------------------------------------------------------------
# 区块 HTML 生成（严格对齐新模板类名）
# ---------------------------------------------------------------------------
def build_key_points_html(overview: Dict[str, str], hotspots: List[Dict[str, object]] | None = None) -> str:
    """本周总览：.key-points > .kp-grid > .kp-card（注塑相关用 .injection）。

    优先使用 Agent 的总览热点卡（.hotspot-card，通常 3 张）；
    兜底使用 overview 区块内解析出的卡片。
    """
    cards = list(hotspots or [])
    if not cards:
        cards = extract_cards_from_body(overview["body"])
    if not cards:
        cards = [{"title": "本周要点", "body": extract_summary(overview["body"])}]

    cards_html: List[str] = []
    for idx, c in enumerate(cards, start=1):
        title = str(c.get("title", "")) or f"要点{idx}"
        body = str(c.get("body", "")) or ""
        is_inj = any(k in title + body for k in INJECTION_KEYWORDS)
        cls = "kp-card injection" if is_inj else "kp-card"
        badge = '<span class="injection-badge">⚡ 注塑机会</span>' if is_inj else ""
        lk = _link_html(str(c.get("link", "")))
        src = _source_html(str(c.get("link", "")), body)
        foot = f'<div class="news-foot">{src}{lk}</div>' if (src or lk) else ""
        cards_html.append(f'''    <div class="{cls}">
      <span class="kp-num">{idx:02d}</span>
      {badge}
      <h3>{escape_html(title)}</h3>
      <p>{highlight_numbers(body)}</p>
      {foot}
    </div>''')

    # 引言段（overview 区块内的 <p>，hotspot 卡已在 section 之外单独处理）
    soup = BeautifulSoup(overview["body"], "html.parser")
    intro = ""
    for p in soup.find_all("p"):
        txt = clean_text(p.get_text(" ", strip=True))
        if len(txt) >= 30:
            intro = txt
            break
    intro_html = f'    <p style="margin-bottom:24px;color:var(--text-soft);">{highlight_numbers(intro)}</p>\n' if intro else ""

    return f'''  <!-- Key Points -->
  <section class="key-points" id="overview">
    <div class="key-points-header">
      <h2>本周总览</h2>
      <span class="line"></span>
    </div>
{intro_html}    <div class="kp-grid">
{chr(10).join(cards_html)}
    </div>
  </section>
'''


def _match_region(name: str) -> Dict[str, str]:
    for r in REGIONS:
        if r["name"] in name:
            return r
    return {"name": name, "key": "other", "en": name, "cls": "region-other"}


# 区域分组顺序与展示信息
REGION_ORDER: List[Dict[str, str]] = [
    {"key": "china", "label": "中国市场", "cls": "region-cn"},
    {"key": "sea", "label": "东南亚市场", "cls": "region-sea"},
    {"key": "sa", "label": "南美市场", "cls": "region-sa"},
    {"key": "eu", "label": "欧洲市场", "cls": "region-eu"},
    {"key": "na", "label": "北美市场", "cls": "region-na"},
    {"key": "other", "label": "其他市场", "cls": "region-other"},
]


def classify_region(text: str) -> str:
    """根据一段文本（卡片标题/正文）判断所属区域 key。"""
    for r in REGIONS:
        if r["name"] in text:
            return r["key"]
    return "other"


def _strip_region_prefix(title: str) -> str:
    """去掉卡片标题开头的区域名前缀，如"欧洲 大众集团..." -> "大众集团..."。"""
    t = title.strip()
    for r in sorted(REGIONS, key=lambda x: -len(x["name"])):
        for prefix in (r["name"] + " ", r["name"] + "　", r["name"] + "：", r["name"] + ":"):
            if t.startswith(prefix):
                return t[len(prefix):].strip()
    return t


def build_markets_html(markets: Optional[Dict[str, str]]) -> str:
    """各地市场动态：.section#markets 内含多个 .subsection.region-* + .news-card。"""
    subsections: List[str] = []

    if markets:
        full = markets["body"]
        # 先提取所有市场卡片（Agent 用 .card-grid>.card，标题以区域名开头）
        all_cards = extract_cards_from_body(full)

        # 若存在显式区域小标题（h3/h4 为区域名），按块分组；否则按卡片文本关键词归类
        head_pattern = re.compile(r"<(h3|h4)([^>]*)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
        hm = [m for m in head_pattern.finditer(full)
              if len(clean_text(re.sub(r"<[^>]+>", "", m.group(3)))) <= 12]

        region_cards: Dict[str, List[Dict[str, object]]] = {r["key"]: [] for r in REGION_ORDER}
        if hm:
            for i, m in enumerate(hm):
                name = clean_text(re.sub(r"<[^>]+>", "", m.group(3)))
                key = _match_region(name)["key"]
                start = m.end()
                end = hm[i + 1].start() if i + 1 < len(hm) else len(full)
                region_cards[key].extend(extract_cards_from_body(full[start:end]))
        else:
            def region_by_prefix(t: str) -> str:
                for r in sorted(REGIONS, key=lambda x: -len(x["name"])):
                    if t == r["name"] or t.startswith(r["name"] + " ") or t.startswith(r["name"]):
                        # 仅当前缀是区域名（其后紧跟空白/标点/tag）
                        rest = t[len(r["name"]):]
                        if rest == "" or rest[0] in " 　:：（(":
                            return r["key"]
                return ""

            for c in all_cards:
                title = str(c.get("title", "")).strip()
                key = region_by_prefix(title)
                if key:
                    c["title"] = ""  # 区域名已作为 subsection 标题，卡片不再重复
                else:
                    key = classify_region(title + str(c.get("body", "")))
                region_cards[key].append(c)

        for r in REGION_ORDER:
            key, label, cls = r["key"], r["label"], r["cls"]
            cards_html: List[str] = []
            for c in region_cards[key][:6]:
                title = _strip_region_prefix(str(c.get("title", "")))
                body_text = str(c.get("body", "")).strip()
                if not title:
                    # 区域汇总卡：无卡片标题，直接展示正文（去掉末尾"原文"）
                    body_text = re.sub(r"\s*原文$", "", body_text)
                    b = _card_rich_body(body_text)
                    lk = _link_html(str(c.get("link", "")))
                    src = _source_html(str(c.get("link", "")), body_text)
                    cards_html.append(
                        f'      <div class="news-card"><div class="news-body rich">{b}</div>'
                        f'<div class="news-foot">{src}{lk}</div></div>'
                    )
                else:
                    t = escape_html(title)
                    b = _card_rich_body(body_text)
                    lk = _link_html(str(c.get("link", "")))
                    src = _source_html(str(c.get("link", "")), body_text)
                    cards_html.append(
                        f'      <div class="news-card"><h4>{t}</h4>'
                        f'<div class="news-body">{b}</div>'
                        f'<div class="news-foot">{src}{lk}</div></div>'
                    )
            if not cards_html:
                cards_html.append(
                    '      <div class="news-card"><div class="news-body">本周该区域暂无重大新增动态，持续跟踪。</div></div>'
                )
            subsections.append(f'''    <div class="subsection {cls}" id="{key}">
      <h3 class="subsection-title"><span class="region-dot"></span>{label}</h3>
{chr(10).join(cards_html)}
    </div>''')

    body_html = "\n".join(subsections) if subsections else (
        '    <div class="subsection region-other" id="other">'
        '<div class="news-card"><div class="news-body">本周暂无更多区域市场明细数据。</div></div></div>'
    )

    return f'''  <!-- Markets -->
  <section class="section" id="markets">
    <div class="section-header">
      <h2>各地市场动态</h2>
      <span class="sec-num">REGIONAL</span>
      <span class="sec-line"></span>
    </div>
{body_html}
  </section>
'''


def _derive_title(card: Dict[str, object], max_len: int = 24) -> str:
    """无标题卡片（li/p 列表）时，从正文首句提炼一个精简标题。"""
    title = str(card.get("title", "")).strip()
    if title:
        return title
    body = str(card.get("body", "")).strip()
    # 优先按中文逗号/分号/冒号切出前段
    for sep in ("。", "；", ";", "，", "：", ":"):
        if sep in body:
            head = body.split(sep)[0].strip()
            if 6 <= len(head) <= max_len:
                return head
    return body[:max_len]


def build_simple_card_section(sec: Optional[Dict[str, str]], *, section_id: str,
                              title: str, num: str, card_class: str,
                              keywords: List[str], empty_text: str) -> str:
    """政策/车企/调研通用：.section > 多个对应卡片。"""
    cards_html: List[str] = []
    if sec:
        cards = extract_cards_from_body(sec["body"])
        for c in cards[:8]:
            title_text = re.sub(r"^(动态|利好|风险|关注|机会|政策|调研|观点)\s*", "",
                                _derive_title(c)).strip()
            t = escape_html(title_text)
            body_text = str(c.get("body", ""))
            # 正文若以标题开头，去掉重复标题
            tt = str(c.get("title", "")).strip()
            if not tt and body_text.startswith(_derive_title(c)):
                body_text = body_text[len(_derive_title(c)):].strip(" ，。；;：:")
            b = _card_rich_body(body_text)
            lk = _link_html(str(c.get("link", "")))
            src = _source_html(str(c.get("link", "")), body_text)
            if card_class == "oem-card":
                cards_html.append(
                    f'    <div class="oem-card"><h3><span class="oem-tag">动态</span>{t}</h3>'
                    f'<div class="news-body rich">{b}</div><div class="news-foot">{src}{lk}</div></div>'
                )
            elif card_class == "policy-card":
                cards_html.append(f'    <div class="policy-card"><h3>{t}</h3><div class="news-body rich">{b}</div>'
                                  f'<div class="news-foot">{src}{lk}</div></div>')
            else:
                cards_html.append(f'    <div class="research-card"><h3>{t}</h3><div class="news-body rich">{b}</div>'
                                  f'<div class="news-foot">{src}{lk}</div></div>')
    if not cards_html:
        if card_class == "oem-card":
            cards_html.append(f'    <div class="oem-card"><p>{escape_html(empty_text)}</p></div>')
        elif card_class == "policy-card":
            cards_html.append(f'    <div class="policy-card"><p>{escape_html(empty_text)}</p></div>')
        else:
            cards_html.append(f'    <div class="research-card"><p>{escape_html(empty_text)}</p></div>')

    return f'''  <!-- {title} -->
  <section class="section" id="{section_id}">
    <div class="section-header">
      <h2>{title}</h2>
      <span class="sec-num">{num}</span>
      <span class="sec-line"></span>
    </div>
{chr(10).join(cards_html)}
  </section>
'''


def build_injection_html(sec: Optional[Dict[str, str]]) -> str:
    cards_html: List[str] = []
    if sec:
        cards = extract_cards_from_body(sec["body"])
        for c in cards[:6]:
            t = escape_html(str(c.get("title", "")))
            b = _card_rich_body(str(c.get("body", "")))
            lk = _link_html(str(c.get("link", "")))
            body_text = str(c.get("body", ""))
            src = _source_html(str(c.get("link", "")), body_text)
            cards_html.append(f'      <div class="inj-card"><h3>⚡ {t}</h3><div class="news-body rich">{b}</div>'
                              f'<div class="news-foot">{src}{lk}</div></div>')
    if not cards_html:
        cards_html.append(
            '      <div class="inj-card"><h3>⚡ 持续关注</h3>'
            '<p>本周暂无明确注塑机订单数据，持续跟踪一体化压铸、内饰轻量化、工程塑料替代等结构性机会。</p></div>'
        )
    return f'''  <!-- Injection -->
  <section class="injection-section" id="injection">
    <div class="section-header">
      <h2>注塑机会专题</h2>
      <span class="sec-num" style="color:var(--accent-orange);background:rgba(255,138,61,.14);border:1px solid rgba(255,138,61,.4)">INJECTION</span>
      <span class="sec-line"></span>
    </div>
{chr(10).join(cards_html)}
  </section>
'''


def build_next_week_html(sec: Optional[Dict[str, str]]) -> str:
    items = extract_li_items(sec["body"]) if sec else []
    if not items:
        items = [
            "中国月度新能源汽车销量及渗透率数据发布",
            "欧盟关税政策与对华贸易谈判进展",
            "主要车企三季度交付与出口数据",
            "一体化压铸及内饰轻量化订单动态",
        ]
    li_html = "\n".join(f"      <li><strong>{escape_html(it)}</strong></li>" for it in items[:6])
    return f'''  <!-- Next week -->
  <section class="section" id="nextweek">
    <div class="section-header">
      <h2>下周关注</h2>
      <span class="sec-num">NEXT</span>
      <span class="sec-line"></span>
    </div>
    <div class="next-week">
      <ul>
{li_html}
      </ul>
    </div>
  </section>
'''


# ---------------------------------------------------------------------------
# Agent 获取
# ---------------------------------------------------------------------------
def fetch_agent_html() -> str:
    """调用扣子 Agent 生成周报 HTML；失败时回退到已有 agent.html。"""
    token = os.environ.get("COZE_WORKLOAD_API_TOKEN", "").strip()
    bot_id = os.environ.get("COZE_BOT_ID", "").strip()

    if token and bot_id:
        try:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            create = requests.post(
                f"{COZE_API_BASE}/v3/chat",
                headers=headers,
                json={
                    "bot_id": bot_id,
                    "user_id": "weekly-report-bot",
                    "stream": False,
                    "auto_save_history": True,
                    "additional_messages": [{
                        "role": "user",
                        "content": "请生成本周全球汽车行业周报的完整 HTML，包含本周总览、各地市场动态、政策动态、车企动态、调研报告、注塑机会专题、下周关注。",
                        "content_type": "text",
                    }],
                },
                timeout=60,
            )
            create.raise_for_status()
            data = create.json().get("data", {})
            chat_id = data.get("id")
            conv_id = data.get("conversation_id")
            if chat_id and conv_id:
                import time
                for _ in range(60):
                    time.sleep(5)
                    r = requests.get(
                        f"{COZE_API_BASE}/v3/chat/retrieve",
                        headers=headers,
                        params={"chat_id": chat_id, "conversation_id": conv_id},
                        timeout=30,
                    )
                    info = r.json().get("data", {})
                    status = info.get("status")
                    if status in ("completed", "failed", "requires_action"):
                        break
                if status == "completed":
                    mr = requests.get(
                        f"{COZE_API_BASE}/v3/chat/message/list",
                        headers=headers,
                        params={"chat_id": chat_id, "conversation_id": conv_id},
                        timeout=30,
                    )
                    for msg in mr.json().get("data", []):
                        if msg.get("type") == "answer" and msg.get("content"):
                            content = msg["content"]
                            m = re.search(r"<!DOCTYPE html>.*?</html>", content, re.DOTALL | re.IGNORECASE)
                            return m.group(0) if m else content
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Agent API 调用失败，回退本地 agent.html：{exc}", file=sys.stderr)

    if os.path.exists(AGENT_HTML_PATH):
        with open(AGENT_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    raise RuntimeError("无法获取 Agent HTML：API 调用失败且本地无 agent.html")


# ---------------------------------------------------------------------------
# 主渲染
# ---------------------------------------------------------------------------
def render(agent_html: str, *, team: str = DEFAULT_TEAM) -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    full_html = agent_html
    if "<body" in full_html.lower():
        body_match = re.search(r"<body[^>]*>(.*?)</body>", full_html, re.DOTALL | re.IGNORECASE)
        if body_match:
            full_html = body_match.group(1)

    sections = split_sections_by_title(full_html)
    overview = get_overview_section(sections, full_html)
    markets = get_section_by_keyword(sections, ["各地市场", "市场动态", "区域市场", "市场"])
    policy = get_section_by_keyword(sections, POLICY_KEYWORDS)
    oem = get_section_by_keyword(sections, OEM_KEYWORDS)
    research = get_section_by_keyword(sections, RESEARCH_KEYWORDS)
    injection = get_section_by_keyword(sections, INJECTION_KEYWORDS)
    nextweek = get_section_by_keyword(sections, NEXT_KEYWORDS)

    summary = extract_summary(overview["body"])

    # Agent 总览热点卡（.hotspot-grid > .hotspot-card），位于所有 section 之前
    hotspots = extract_hotspot_cards(full_html)

    overview_html = build_key_points_html(overview, hotspots)
    markets_html = build_markets_html(markets)
    policy_html = build_simple_card_section(
        policy, section_id="policy", title="政策动态", num="POLICY",
        card_class="policy-card", keywords=POLICY_KEYWORDS,
        empty_text="本周暂无重大新增政策，持续关注关税、双反及新能源补贴细则。")
    oem_html = build_simple_card_section(
        oem, section_id="oem", title="车企动态", num="OEM",
        card_class="oem-card", keywords=OEM_KEYWORDS,
        empty_text="本周暂无重点车企更新。")
    research_html = build_simple_card_section(
        research, section_id="research", title="调研报告 / 机构观点", num="RESEARCH",
        card_class="research-card", keywords=RESEARCH_KEYWORDS,
        empty_text="本周暂无新增重磅机构研报。")
    injection_html = build_injection_html(injection)
    nextweek_html = build_next_week_html(nextweek)

    date_str = today_cn()
    period_str = f"数据周期：{get_last_week_range()}"
    sources_str = "MarkLines、乘联会(CPCA)、中汽协(CAAM)、ACEA、GAIKINDO、TAI/FTI、ANFAVEA/Fenabrave、SIAM、AEB、盖世汽车、36氪、界面新闻、AlixPartners、麦肯锡、Maybank、爱建证券"

    result = template
    result = result.replace("{{title}}", "全球汽车行业深度周报")
    result = result.replace("{{date}}", date_str)
    result = result.replace("{{team}}", team)
    result = result.replace("{{data_period}}", period_str)
    result = result.replace("{{sources}}", sources_str)
    result = result.replace("{{overview}}", overview_html.rstrip())
    result = result.replace("{{markets}}", markets_html.rstrip())
    result = result.replace("{{policy}}", policy_html.rstrip())
    result = result.replace("{{oem}}", oem_html.rstrip())
    result = result.replace("{{research}}", research_html.rstrip())
    result = result.replace("{{injection}}", injection_html.rstrip())
    result = result.replace("{{nextweek}}", nextweek_html.rstrip())

    # 兜底：清理残留硬编码周期
    result = re.sub(r"数据周期：[^<\n{]+", period_str, result)
    # 未替换的占位符清空
    result = re.sub(r"\{\{[a-z_]+\}\}", "", result)
    return result


def main() -> None:
    agent_html = fetch_agent_html()
    final_html = render(agent_html)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(final_html)
    print(f"[render] 已生成 {OUTPUT_PATH}（{len(final_html)} 字符）")


if __name__ == "__main__":
    main()
