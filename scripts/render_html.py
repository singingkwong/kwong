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
from bs4 import BeautifulSoup, Tag

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
]

MARKETS_TITLE = "各地市场动态"
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


def extract_cards_from_body(body: str) -> List[Dict[str, object]]:
    """从一段 HTML 中提取标题+正文（优先 .card / .news-card，其次 li / p）。"""
    soup = BeautifulSoup(body, "html.parser")
    cards: List[Dict[str, object]] = []

    # 优先识别带 card 类的块
    candidates = soup.select(".card, .news-card, .region-card, .policy-card, .oem-card, .research-card, .inj-card, .kp-card")
    for c in candidates:
        title_el = c.find(["h3", "h4", "h5", "strong", "b"])
        title = clean_text(title_el.get_text()) if title_el else ""
        body_text = clean_text(c.get_text(" ", strip=True))
        if title and body_text:
            if body_text.startswith(title):
                body_text = body_text[len(title):].strip(" -—:：")
            cards.append({"title": title, "body": body_text})

    if cards:
        return cards

    # 其次：li 列表
    li_cards: List[Dict[str, object]] = []
    for li in soup.find_all("li"):
        txt = clean_text(li.get_text(" ", strip=True))
        if len(txt) < 12:
            continue
        strong = li.find(["strong", "b"])
        title = clean_text(strong.get_text()) if strong else ""
        if title and txt.startswith(title):
            body_txt = txt[len(title):].strip(" -—:：")
        else:
            title = txt[:28]
            body_txt = txt
        li_cards.append({"title": title, "body": body_txt})
    if li_cards:
        return li_cards

    # 最后：p 段落
    for p in soup.find_all("p"):
        txt = clean_text(p.get_text(" ", strip=True))
        if len(txt) < 20:
            continue
        strong = p.find(["strong", "b"])
        title = clean_text(strong.get_text()) if strong else txt[:28]
        body_txt = txt if not strong or not txt.startswith(title) else txt[len(title):].strip(" -—:：")
        cards.append({"title": title, "body": body_txt})
    return cards


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
def build_key_points_html(overview: Dict[str, str]) -> str:
    """本周总览：.key-points > .kp-grid > .kp-card（注塑相关用 .injection）。"""
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
        cards_html.append(f'''    <div class="{cls}">
      <span class="kp-num">{idx:02d}</span>
      {badge}
      <h3>{escape_html(title)}</h3>
      <p>{highlight_numbers(body)}</p>
    </div>''')

    return f'''  <!-- Key Points -->
  <section class="key-points" id="overview">
    <div class="key-points-header">
      <h2>本周总览</h2>
      <span class="line"></span>
    </div>
    <div class="kp-grid">
{chr(10).join(cards_html)}
    </div>
  </section>
'''


def _match_region(name: str) -> Dict[str, str]:
    for r in REGIONS:
        if r["name"] in name:
            return r
    return {"name": name, "key": "other", "en": name, "cls": "region-other"}


def build_markets_html(markets: Optional[Dict[str, str]]) -> str:
    """各地市场动态：.section#markets 内含多个 .subsection.region-* + .news-card。"""
    subsections: List[str] = []

    if markets:
        grouped: List[Dict[str, str]] = []
        full = markets["body"]
        head_pattern = re.compile(r"<(h3)([^>]*)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
        hm = list(head_pattern.finditer(full))
        # 仅当 h3 是区域名（较短、不以句号结尾）时才作为分组标题
        valid = [m for m in hm if len(clean_text(re.sub(r"<[^>]+>", "", m.group(3)))) <= 20]
        if valid:
            for i, m in enumerate(valid):
                name = clean_text(re.sub(r"<[^>]+>", "", m.group(3)))
                start = m.end()
                end = valid[i + 1].start() if i + 1 < len(valid) else len(full)
                grouped.append({"name": name, "body": full[start:end]})
        else:
            grouped = [{"name": "其他市场", "body": full}]

        # region key -> 展示信息
        region_order = [
            ("china", "中国市场", "region-cn"),
            ("sea", "东南亚市场", "region-sea"),
            ("sa", "南美市场", "region-sa"),
            ("eu", "欧洲市场", "region-eu"),
            ("na", "北美市场", "region-na"),
            ("other", "其他市场", "region-other"),
        ]
        grouped_map: Dict[str, Dict[str, str]] = {}
        for g in grouped:
            region = _match_region(g["name"])
            grouped_map.setdefault(region["key"], g)

        for key, label, cls in region_order:
            g = grouped_map.get(key)
            cards_html: List[str] = []
            if g:
                cards = extract_cards_from_body(g["body"])
                for c in cards[:5]:
                    t = escape_html(str(c.get("title", "")))
                    b = highlight_numbers(str(c.get("body", "")))
                    cards_html.append(
                        f'      <div class="news-card"><h4>{t}</h4>'
                        f'<div class="news-body">{b}</div></div>'
                    )
                if not cards_html:
                    for it in extract_li_items(g["body"])[:5]:
                        cards_html.append(
                            f'      <div class="news-card"><div class="news-body">{highlight_numbers(it)}</div></div>'
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


def build_simple_card_section(sec: Optional[Dict[str, str]], *, section_id: str,
                              title: str, num: str, card_class: str,
                              keywords: List[str], empty_text: str) -> str:
    """政策/车企/调研通用：.section > 多个对应卡片。"""
    cards_html: List[str] = []
    if sec:
        cards = extract_cards_from_body(sec["body"])
        for c in cards[:8]:
            t = escape_html(str(c.get("title", "")))
            b = highlight_numbers(str(c.get("body", "")))
            if card_class == "oem-card":
                cards_html.append(
                    f'    <div class="oem-card"><h3><span class="oem-tag">动态</span>{t}</h3>'
                    f'<p>{b}</p></div>'
                )
            elif card_class == "policy-card":
                cards_html.append(f'    <div class="policy-card"><h3>{t}</h3><p>{b}</p></div>')
            else:
                cards_html.append(f'    <div class="research-card"><h3>{t}</h3><p>{b}</p></div>')
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
            b = highlight_numbers(str(c.get("body", "")))
            cards_html.append(f'      <div class="inj-card"><h3>⚡ {t}</h3><p>{b}</p></div>')
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

    overview_html = build_key_points_html(overview)
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
