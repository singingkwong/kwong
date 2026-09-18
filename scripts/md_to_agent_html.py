#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件驱动的「Agent 文本 → agent.html」转换器。

流水线定位：
    Coze Agent 输出文本(markdown)  →  本脚本(md → agent.html)  →  render_html.py(agent.html → index.html)

本脚本读取上级目录的 Agent 文本(markdown)，自动解析七大板块 / 六大区域 / 三要点 / 来源 / 原文链接，
统一重命名为 render_html.py 可识别结构，并落盘 agent.html。设计为：
  - 文件驱动：输入文件名从命令行/环境变量传入，不硬编码正文，可被 GitHub workflow 复用。
  - 规则驱动：解析逻辑与正文解耦；新增一期内容无需改脚本。

用法：
    python3 scripts/md_to_agent_html.py [input.md] [output agent.html]
    - 默认 input=weekly_agent_output.md，output=agent.html（项目根目录）
    - 覆盖旧 agent.html 前可先备份

解析约定：
  - 板块标题：## （本周核心要点/本周总览 | 分区域市场动态 | 政策 [与法规] 动态 | 主要车企动态 | 调研 | 注塑机会 | 下周关注）
  - 区域小节：### ...（中国|欧洲/欧盟|北美|东南亚|印度|其他）
  - 单条事件：以数字序号起行；正文含「量化要点/关键数据」「产业链影响/影响分析」两要点，
    本脚本自动为每条补「趋势判断」要点（规则基于内容关键词），满足三要点结构。
  - 原文链接：行内「【原文链接】:URL」或「【原文链接】：URL」。
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 板块匹配（保持与 render_html.py 的 get_section_by_keyword 一致）
SECTION_TITLES: list[tuple[str, list[str]]] = [
    ("overview", ["本周总览", "核心要点", "核心看点", "本周看点", "一周概览"]),
    ("markets", ["分区域市场动态", "各地市场动态", "区域市场", "市场动态"]),
    ("policy", ["政策", "法规", "监管"]),
    ("oem", ["车企动态", "整车", "主机厂", "品牌动态"]),
    ("research", ["调研", "报告", "观点", "研报"]),
    ("injection", ["注塑机会", "注塑"]),
    ("nextweek", ["下周关注", "下周", "关注前瞻"]),
]

# 区域小节标题 → region key（与 REGIONS 映射）
REGION_KEYS: list[tuple[str, str]] = [
    ("中国", "china"),
    ("北美", "na"),
    ("美国", "na"),
    ("墨西哥", "na"),
    ("欧洲", "eu"),
    ("欧盟", "eu"),
    ("东南亚", "sea"),
    ("印度", "india"),
    ("南美", "other"),
    ("巴西", "other"),
    ("日韩", "other"),
    ("其他", "other"),
]

POINT_KEY_ALIASES = ["量化要点", "关键数据", "核心数据", "数据", "关键指标"]
POINT_IMPACT_ALIASES = ["产业链影响", "影响分析", "行业影响", "影响", "产业链影响分析"]
POINT_TREND_ALIASES = ["趋势判断", "趋势", "展望", "未来判断"]

LINK_RE = re.compile(r"【?原文链接】?\s*[:：]\s*(https?://\S+)")
SOURCE_RE = re.compile(r"来源[:：]\s*([^\s，,。；;|】]+)")
NUM_HEAD_RE = re.compile(r"^\s*\d+[\s.、．]\s*")
# 列表项加粗标题行：`- **标题**` / `- **标题**：内容`（Bot 常用此格式输出板块条目）
LIST_BOLD_RE = re.compile(r"^\s*[-*•]\s*\*\*[^*]+\*\*")
# 子要点标签行（`- 量化要点：xxx` 等），这些是事件内部的要点，不是新事件边界
SUB_POINT_RE = re.compile(
    r"^\s*[-*•]\s*(量化要点|影响分析|产业链影响|对注塑产业链的市场影响|趋势判断|趋势|核心要点|事件概述|影响|来源)\b")
# 纯文本列表项：`- 中汽协发布xxx`（下周关注等板块的条目形式）
PLAIN_ITEM_RE = re.compile(r"^\s*[-*•]\s+\S")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def escape_html(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def find_section_index(md: str, keywords: list[str]) -> int:
    """返回第一个匹配小节的标题行行号；找不到返回 -1。"""
    for i, line in enumerate(md.splitlines()):
        if re.match(r"^\s*#{1,4}\s+", line):
            t = re.sub(r"^\s*#{1,4}\s+", "", line).strip(" #.*-==")
            if any(k in t for k in keywords):
                return i
    return -1


def _title_key(title: str) -> str | None:
    t = clean(title).strip(" #.*-==")
    for sec_key, kws in SECTION_TITLES:
        if any(k in t for k in kws):
            return sec_key
    return None


def _split_sections_impl(lines: list[str]) -> dict[str, str]:
    marks: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        # 板块标题：# / ## 两级；#### 及以下的标题属于板块内部卡片标题。
        # 兼容 Bot 把非市场板块写成 `### 5. 行业调研`/`### 6. 下周关注` 这类
        # 带编号的三级标题：只要标题能命中板块关键词，同样视为板块边界。
        m = re.match(r"^\s*(#{1,3})\s+(.+)", line)
        if m and len(m.group(1)) <= 3:
            key = _title_key(m.group(2))
            if key:
                marks.append((i, m.group(2).strip(), key))
    if not marks:
        return {}
    marks.sort(key=lambda x: x[0])
    sections: dict[str, str] = {}
    seen = set()
    for idx, (start, raw, key) in enumerate(marks):
        if key in seen:
            continue
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        seen.add(key)
        sections[key] = "\n".join(lines[start + 1:end])
    return sections


def extract_region_blocks(market_body: str) -> list[dict]:
    """从「分区域市场动态」正文切出 区域小节。"""
    blocks: list[dict] = []
    lines = market_body.splitlines()
    starts: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*#{1,5}\s+(.+)", line)
        if not m:
            continue
        t = clean(m.group(1)).strip(" #.*-==")
        for rk, _k in REGION_KEYS:
            if rk in t:
                starts.append((i, t, _k))
                break
    for idx, (start, raw, key) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        blocks.append({
            "title": clean(re.sub(r"^[（(]?[一二三四五六七八九十]+[)）]\s*", "", raw)),
            "key": key,
            "body": "\n".join(lines[start + 1:end]),
        })
    return blocks


def split_events(body: str) -> list[str]:
    """把某个板块/区域正文按 数字序号 拆成多条事件。"""
    events: list[str] = []
    cur: list[str] = []
    for line in body.splitlines():
        # 新事件边界：数字序号行 / `- **标题**` 加粗列表项 / 非子要点的纯文本列表项（如下周关注条目）
        is_boundary = (
            NUM_HEAD_RE.match(line)
            or LIST_BOLD_RE.match(line)
            or (PLAIN_ITEM_RE.match(line) and not SUB_POINT_RE.match(line))
        )
        if is_boundary:
            if cur:
                events.append("\n".join(cur))
            cur = [line]
        elif line.strip():
            cur.append(line)
    if cur:
        events.append("\n".join(cur))
    # 过滤过短/空
    return [clean(e) for e in events if clean(e) and len(clean(e)) >= 20]


_ALL_POINT_ALIASES = (POINT_KEY_ALIASES[0], POINT_IMPACT_ALIASES[0], POINT_TREND_ALIASES[0])


def _clean_point(seg: str) -> str:
    """清理要点文本残留：去掉【原文链接】/来源标注/多余空白，保留纯正文。"""
    if not seg:
        return ""
    seg = re.sub(r"【?原文链接】?[:：]?\s*https?://\S+", "", seg)
    seg = re.sub(r"【?原文链接】?[:：]?\s*$", "", seg)
    seg = re.sub(r"\s*来源[:：]\s*\S*\s*$", "", seg)
    seg = re.sub(r"【|】", "", seg)
    seg = re.sub(r"\s+", " ", seg).strip(" ：:～— |\n")
    return seg


def _grab_point(event: str, target_alias: str, stop_aliases: list[str]) -> str:
    """抓取以 target_alias 起始的要点文本，遇到其他要点/原文链接/来源即停。

    兼容要点标题与正文同行（如 `量化要点：xxx 产业链影响：yyy 趋势判断：zzz`），
    在整段文本内按「目标 alias → 下一个 stop alias」顺序切，而非依赖换行。
    """
    t_idx = -1
    prefix = ""
    for alias in (target_alias,):
        idx = event.find(alias)
        if idx != -1:
            t_idx = idx
            prefix = alias
            break
    if t_idx == -1:
        return ""
    seg_raw = event[t_idx + len(prefix):].lstrip("：:～— 　|")
    # 找后续出现的任一 stop alias 截断
    cut = len(seg_raw)
    for st in stop_aliases:
        i = seg_raw.find(st)
        if i != -1 and i < cut:
            cut = i
    seg = seg_raw[:cut]
    return _clean_point(seg)


def extract_three_points(event: str) -> dict[str, str]:
    """从单条事件提取 关键数据/影响分析/趋势判断。"""
    key_txt = _grab_point(event, "量化要点", ["产业链影响", "趋势判断"])
    if not key_txt:
        key_txt = _grab_point(event, "关键数据", ["产业链影响", "影响分析"])
    imp_txt = _grab_point(event, "产业链影响", ["趋势判断", "原文", "来源"])
    if not imp_txt:
        imp_txt = _grab_point(event, "影响分析", ["趋势判断", "原文", "来源"])
    tr_txt = _grab_point(event, "趋势判断", ["原文", "来源"])
    if not tr_txt:
        tr_txt = derive_trend(key_txt + " " + imp_txt)
    return {"关键数据": key_txt, "影响分析": imp_txt, "趋势判断": tr_txt}


def derive_trend(text: str) -> str:
    """按内容关键词给单条事件生成趋势判断要点（规则式）。"""
    t = text
    trends = []
    if "渗透率" in t or "市占率" in t:
        trends.append("渗透/市占率提升，新能源与新能源车型占比长期走高，配套塑件需求同步放量。")
    if "关税" in t or "壁垒" in t or "本地化" in t or "双反" in t:
        trends.append("贸易壁垒推动本地化布局提速，区域化注塑产能与供应链内移成为趋势。")
    if "出口" in t:
        trends.append("出口带动差异化定制塑件与本地化配套订单持续增长。")
    if "补贴" in t or "规划" in t or "目标" in t:
        trends.append("政策补贴与产业规划延续，将支撑中远期塑件/设备需求稳定增长。")
    if "扩建" in t or "投产" in t or "建厂" in t or "投资" in t:
        trends.append("产能扩建集中落地，上游注塑设备与结构件采购进入放量期。")
    if "轻量化" in t or "一体化" in t or "电动化" in t or "800V" in t:
        trends.append("电动化与轻量化成为主线，高强/集成化工程塑料结构件需求持续提升。")
    if not trends:
        trends.append("该领域需求将随行业结构性升级而持续增长，注塑相关机会值得跟踪。")
    return "".join(trends[:2])


def extract_link(event: str) -> str:
    m = LINK_RE.search(event)
    if m:
        return m.group(1).strip().rstrip("。")
    # 兜底：裸 http(s)
    m2 = re.search(r"https?://\S+", event)
    return m2.group(0).strip().rstrip("。)】") if m2 else ""


def extract_source(event: str) -> str:
    m = SOURCE_RE.search(event)
    if m:
        return m.group(1).strip()
    link = extract_link(event)
    if link:
        host = re.sub(r"^www\.", "", link.split("/")[2] if "//" in link else "")
        host = host.split(":")[0]
        return host.split(".")[0].capitalize() if host else "来源待核"
    return "来源待核"


def make_li(title: str, pts: dict[str, str], source: str, link: str) -> str:
    key = pts.get("关键数据", "") or pts.get("量化要点", "")
    imp = pts.get("影响分析", "") or pts.get("产业链影响", "")
    tr = pts.get("趋势判断", "")
    href = escape_html(link) if link else "#"
    return (f'<li><strong>{escape_html(title)}</strong>\n'
            f'        关键数据/事件：{escape_html(key)}\n'
            f'        影响分析：{escape_html(imp)}\n'
            f'        趋势判断：{escape_html(tr)}\n'
            f'        <a href="{href}" '
            f'class="source-link" target="_blank">原文</a></li>')


def simple_li(text: str, source: str, link: str) -> str:
    href = escape_html(link) if link else "#"
    return (f'<li>{escape_html(text)} '
            f'<a href="{href}" class="source-link" target="_blank">原文</a></li>')


# 板块配图（webp 小图，相对路径，沙箱与 GitHub Pages 子路径均可加载；16:9 防布局抖动）
_SECTION_IMG: dict[str, str] = {
    "本周总览": "images/cover-global-weekly.webp",
    "各地市场动态": "images/export-port.webp",
    "注塑机会专题": "images/injection-factory.webp",
}


def sec(title: str, body: str) -> str:
    img = ""
    if title in _SECTION_IMG:
        img = (f'<figure class="weekly-figure">'
               f'<img src="{_SECTION_IMG[title]}" alt="{title} 报道配图" '
               f'class="weekly-img" width="1280" height="720" loading="lazy">'
               f'</figure>\n')
    return f'<h2 class="section-title">{escape_html(title)}</h2>\n{img}{body}'


def _region_label(block: dict) -> str:
    """把区域块标题规范为纯区域名，供 card-title 展示与 agent_checks 区域归类。"""
    key = block["key"]
    label_map = {
        "china": "中国",
        "na": "北美",
        "eu": "欧洲",
        "sea": "东南亚",
        "india": "印度",
        "other": "其他",
    }
    return label_map.get(key, block["key"])


def build_region_html(region_blocks: list[dict]) -> str:
    """把各大区域小节渲染成各区域卡片。"""
    parts: list[str] = []
    for block in region_blocks:
        events = split_events(block["body"])
        if not events:
            continue
        lis = []
        for ev in events:
            # 标题：数字序号后的首句（到第一个「量化要点/关键数据」前）
            cut = len(ev)
            for a in POINT_KEY_ALIASES + POINT_IMPACT_ALIASES:
                i = ev.find(a)
                if i != -1 and i < cut:
                    cut = i
            title = clean(ev[:cut]).strip("【】[] 。．")
            title = re.sub(r"^\d+[\s.、．]\s*", "", title)
            pts = extract_three_points(ev)
            source = extract_source(ev)
            link = extract_link(ev)
            lis.append(make_li(title, pts, source, link))
        if not lis:
            # 该区域本轮无真实事件：不生成事件卡，由 render 层按空态处理
            continue
        inner = "\n".join(lis)
        parts.append(
            f'<div class="card-grid"><div class="card">'
            f'<div class="card-title">{escape_html(_region_label(block))}</div>'
            f'<div class="card-content"><ul class="styled-list">\n{inner}\n</ul>'
            f'</div></div></div>'
        )
    return "\n".join(parts)


def build_injection(body: str) -> str:
    """注塑机会专题：按 `**标题**：` 拆成多张 inj-card 卡，正文合并子要点、去掉 markdown 符号。"""
    if not body:
        return ""
    lines = body.splitlines()
    blocks: list[dict[str, object]] = []
    cur: dict[str, object] | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        # 每个条目：`- **标题**：内容` / `N. **标题**` / `**标题**`（标题可独占一行或带冒号接内容）
        m0 = re.match(r"^\d+[\s.、．]\s*\*\*([^*]+)\*\*\s*[:：]?\s*$", line)
        m1 = re.match(r"^\*\*([^*]+)\*\*\s*[:：]?\s*$", line)
        m2 = re.match(r"^[-*•]\s*\*\*([^*]+)\*\*\s*[:：]?\s*(.*)$", line)
        m = m0 or m1 or m2
        if m:
            blocks.append({"title": clean(m.group(1)), "subs": [], "link": ""})
            cur = blocks[-1]
            # `- **标题**：内容` 形式：冒号后的内容并入首个子要点
            if m2 is m and m.group(2):
                inline = LINK_RE.sub("", m.group(2)).strip()
                if inline:
                    cur["subs"].append(clean(inline))  # type: ignore[attr-defined]
            continue
        # 原文链接行：提取链接，不进正文
        mlink = re.search(r"【原文链接】\s*[:：]?\s*(https?://\S+)", line)
        if mlink:
            if cur is not None:
                cur["link"] = mlink.group(1)  # type: ignore[attr-defined]
            continue
        # markdown 图片行：丢弃（页面默认无图）
        if re.match(r"^>?\s*!\[", line):
            continue
        # 子要点：- xxx 或 纯文本
        if cur is None:
            blocks.append({"title": "", "subs": [], "link": ""})
            cur = blocks[-1]
        sub = re.sub(r"^[-•*]\s+", "", line)
        sub = LINK_RE.sub("", sub)
        if sub:
            cur["subs"].append(clean(sub))  # type: ignore[attr-defined]

    cards = []
    for b in blocks:
        title = b["title"]
        subs = b["subs"]
        link = b.get("link", "")  # type: ignore[attr-defined]
        body_txt = "；".join(subs) if subs else "本周暂无明确注塑机订单数据，持续跟踪注塑结构件、工程塑料替代等机会。"
        t = escape_html(title) if title else "持续关注"
        link_html = (f'<div class="news-foot"><a class="source-link" href="{escape_html(link)}" '
                     f'target="_blank" rel="noopener">原文</a></div>') if link else ""
        cards.append(
            f'<div class="inj-card"><h3>{t}</h3>'
            f'<div class="news-body rich">{escape_html(body_txt)}</div>{link_html}</div>'
        )
    return "\n".join(cards)


def build_research(body: str) -> str:
    """调研报告·机构观点：按条目拆成多张 research-card。

    兼容 Bot 常见写法：
      - `### **标题**` / `**标题**`（独占一行）
      - `- **调研主题**：标题内容`（列表项，标题取冒号后内容）
    每条正文合并 量化要点/影响 等子行，去掉 markdown 残留（`**`/`-`/图片行/
    原文链接行），卡片底部附 source-link 原文链接（满足原文链接计数）。
    """
    if not body:
        return ""
    # 跳过板段标记行（RESEARCH/POLICY/OEM/INJECTION）与占位标题
    _MARK = re.compile(r"^\s*(RESEARCH|POLICY|OEM|INJECTION|NEXT|HOTSPOT|REGIONAL|WEEKLY|REPORT)\s*$")
    PLACEHOLDER = re.compile(r"^\s*#+\s*\*\*?\s*调研\s*标题\s*\*\*\s*$")
    # 新条目起点：### 标题 / 数字编号 / 独立 **加粗标题** 行 / `- **label**：内容` 列表项
    _TITLE_H = re.compile(r"^\s*#{1,6}\s+\*\*([^*]+)\*\*\s*$")
    _TITLE_B = re.compile(r"^\s*\*\*(?!#)([^*]{2,40})\*\*\s*$")
    _NUM = re.compile(r"^\s*\d+\s*[.、．]\s*")
    # `- **label**：内容` 列表项（行首 -，加粗 label 后跟冒号）；label 为通用词时标题取冒号后
    _BULLET = re.compile(r"^\s*-\s+\*\*([^*]+)\*\*\s*[:：]\s*(.*)$")
    _GENERIC_LABEL = {"调研主题", "主题", "调研", "报告主题", "机构观点", "报告标题"}
    lines: list[str] = [ln.strip() for ln in body.splitlines()]
    lines = [ln for ln in lines if ln and not _MARK.match(ln) and not PLACEHOLDER.match(ln)]
    blocks: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        if _TITLE_H.match(ln) or _TITLE_B.match(ln) or _NUM.match(ln) or _BULLET.match(ln):
            if cur:
                blocks.append(cur)
                cur = []
        cur.append(ln)
    if cur:
        blocks.append(cur)

    cards = []
    for blk in blocks:
        raw = [l.strip() for l in blk if l.strip()]
        link = extract_link("\n".join(raw))
        title = ""
        body_lines: list[str] = []
        for idx, ln in enumerate(raw):
            # 丢弃 markdown 图片行与原文链接行（链接已单独提取）
            if re.search(r"!\[[^\]]*\]\(", ln):
                continue
            if LINK_RE.search(ln):
                continue
            m_bullet = _BULLET.match(ln)
            if m_bullet:
                label, rest = m_bullet.group(1).strip(), m_bullet.group(2).strip()
                if label in _GENERIC_LABEL and rest:
                    title = rest
                else:
                    if not title:
                        title = label
                    if rest:
                        body_lines.append(rest)
                continue
            if idx == 0:
                m_h = _TITLE_H.match(ln) or _TITLE_B.match(ln)
                if m_h:
                    if not title:
                        title = m_h.group(1).strip()
                    continue
            # 普通正文行：去掉 ** 包裹与行首列表符
            ln = re.sub(r"\*\*([^*]+)\*\*", r"\1", ln)
            ln = re.sub(r"^[-•*]\s+", "", ln)
            if ln:
                body_lines.append(ln)
        body_txt = clean(" ".join(body_lines))
        body_txt = LINK_RE.sub("", body_txt).strip(" ：:～—| 【】")
        if not title:
            head = body_txt.split("量化要点")[0].split("：", 1)[0]
            title = head.strip(" ：:～—，,。；;")[:40] or "机构观点"
        title = re.sub(r"^\d+\s*[.、．]\s*", "", title).strip()
        if len(title) > 40:
            title = title[:40]
        if len(body_txt) < 10:
            continue
        href = escape_html(link) if link else "#"
        tail = f' <a href="{href}" class="source-link" target="_blank">原文</a>' if link else ""
        cards.append(
            f'<div class="research-card"><h3>{escape_html(title)}</h3>'
            f'<p>{escape_html(body_txt)}{tail}</p></div>'
        )
    return "\n".join(cards) if cards else "<p>本周暂无重大调研报告更新。</p>"


def build_simple_section(body: str) -> str:
    """政策/车企/调研 等：每条 li 一条动态。"""
    events = split_events(body)
    if not events:
        return ""
    lis = []
    for ev in events:
        text = clean(ev)
        # 剥离列表项前缀 `- ` 与数字序号
        text = re.sub(r"^\s*[-*•]\s*", "", text)
        text = re.sub(r"^\d+[\s.、．]\s*", "", text)
        # 去掉所有 **加粗** 符号（保留文字），如 `**标题**`→标题、`**量化要点**`→量化要点
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        # 去掉【原文链接】字样（链接由 simple_li 单独渲染）
        text = LINK_RE.sub("", text)
        text = re.sub(r"\s{2,}", " ", text).strip(" ，。;；")
        source = extract_source(ev)
        link = extract_link(ev)
        lis.append(simple_li(text, source, link))
    return '<ul class="styled-list">\n' + "\n".join(lis) + "\n</ul>"


def build_overview(body: str) -> str:
    """本周总览：引言段落 + 热点卡片（hotspot-card）。

    Bot 常见结构：
      总述段落 × 2
      ### 本周核心热点
      1. **热点标题**【原文链接】：url
      2. ...
    旧逻辑只按数字序号 split_events，导致总述+子标题残留并入第一张卡、
    标题 ** 残留、render 兜底标题变"要点N"。现按「### 子标题」切分引言与热点列表，
    每个热点输出 hotspot-card（render 原生识别，标题/正文/链接各归其位）。
    """
    lines = body.splitlines()
    intro_lines: list[str] = []
    hotspot_lines: list[str] = []
    in_hotspot = False
    for line in lines:
        if re.match(r"^\s*#{1,6}\s+", line):
            in_hotspot = True  # 遇到子标题（如「### 本周核心热点」）后进入热点列表区
            continue
        (hotspot_lines if in_hotspot else intro_lines).append(line)

    intro = clean("\n".join(intro_lines)).strip()
    hotspot_body = "\n".join(hotspot_lines) if in_hotspot else body
    events = split_events(hotspot_body)

    out: list[str] = []
    if intro:
        out.append(f"<p class='overview-intro'>{escape_html(intro)}</p>")

    for e in events:
        txt = clean(e)
        if not txt:
            continue
        txt = re.sub(r"^\d+[\s.、．]\s*", "", txt)
        txt = re.sub(r"^[-*•]\s*", "", txt)  # 剥离列表项前缀 `- `
        link = extract_link(txt)
        txt = re.sub(r"【?原文链接】?[:：]?\s*https?://\S+", "", txt)
        # 「**热点1**：内容」/「**看点**：内容」→ label 为通用词时取冒号后内容
        m_label = re.match(r"^\*\*([^*]{2,15})\*\*\s*[:：]\s*(.+)$", txt, re.S)
        if m_label and re.match(r"^(热点|看点|要点|主题|事件|news)\s*\d*$", m_label.group(1), re.I):
            txt = m_label.group(2).strip()
        # 提取 **标题**；无加粗则取首个句子作标题
        title = ""
        desc = ""
        m = re.search(r"\*\*([^*]{4,120})\*\*", txt)
        if m:
            title = m.group(1).strip(" ：:，,。;；")
            desc = (txt[: m.start()] + txt[m.end():]).strip(" ：:，,。;；")
        else:
            # 标题取首个完整短句：先按句号分，首句过长（>45字）则按逗号再分，保证标题紧凑
            m_stop = re.search(r"[。；;]", txt)
            head = txt[: m_stop.start()] if m_stop else txt
            tail = txt[m_stop.end():] if m_stop else ""
            if len(head) > 45:
                m_comma = re.search(r"[，,]", head)
                if m_comma and m_comma.start() >= 8:
                    title = head[: m_comma.start()].strip()
                    desc = (head[m_comma.end():] + ("。" + tail if tail else "")).strip(" ，,。;；")
                else:
                    title, desc = head.strip(), tail.strip()
            else:
                title, desc = (head.strip(), tail.strip()) if len(head) >= 8 else (txt.strip(), "")
        title = re.sub(r"\*\*", "", title).strip()
        desc = re.sub(r"\*\*", "", desc).strip()
        if not title:
            continue
        href = f' <a href="{escape_html(link)}" class="source-link" target="_blank">原文链接</a>' if link else ""
        desc_html = f'<p class="hotspot-desc">{escape_html(desc)}</p>' if desc else ""
        out.append(
            f'<div class="hotspot-card">'
            f'<h3 class="hotspot-title">{escape_html(title)}</h3>'
            f'{desc_html}{href}</div>'
        )

    if not out:
        return "<p>本周全球汽车行业动态汇总。</p>"
    return "\n".join(out)


def main() -> None:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "weekly_agent_output.md"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "agent.html"
    md = in_path.read_text(encoding="utf-8")
    sections = _split_sections_impl(md.splitlines())

    out = ["<!-- 由 scripts/md_to_agent_html.py 转换生成，请勿手改 -->\n"]

    # 本周总览
    if "overview" in sections:
        out.append(sec("本周总览", build_overview(sections["overview"])))

    # 分区域市场动态
    region_blocks = extract_region_blocks(sections.get("markets", ""))
    # 确保"其他"区域覆盖（Agent 可能未单独输出，兜底一条综述避免区域空置）
    if region_blocks and not any(b["key"] == "other" for b in region_blocks):
        region_blocks.append({"title": "其他", "key": "other", "body": ""})
    if region_blocks:
        out.append(sec("各地市场动态", build_region_html(region_blocks)))

    # 政策 / 车企 / 调研 / 注塑 / 下周
    simple_map = {
        "policy": sec("政策动态", build_simple_section(sections.get("policy", ""))),
        "oem": sec("车企动态", build_simple_section(sections.get("oem", ""))),
        "research": sec("调研报告·机构观点", build_research(sections.get("research", ""))),
        "injection": sec("注塑机会专题", build_injection(sections.get("injection", ""))),
        "nextweek": sec("下周关注", build_simple_section(sections.get("nextweek", ""))),
    }
    for key in ("policy", "oem", "research", "injection", "nextweek"):
        if key in sections and sections[key].strip():
            out.append(simple_map[key])

    html = "\n\n".join(out)
    out_path.write_text(html, encoding="utf-8")
    print(f"已写入 {out_path}（{len(html)} 字节）")
    print("板块：", list(sections.keys()))


if __name__ == "__main__":
    main()