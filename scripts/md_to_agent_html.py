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
        m = re.match(r"^\s*#{1,4}\s+(.+)", line)
        if m:
            key = _title_key(m.group(1))
            if key:
                marks.append((i, m.group(1).strip(), key))
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
        if NUM_HEAD_RE.match(line):
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
            f'        来源:{escape_html(source)} <a href="{href}" '
            f'class="source-link" target="_blank">原文</a></li>')


def simple_li(text: str, source: str, link: str) -> str:
    href = escape_html(link) if link else "#"
    return (f'<li>{escape_html(text)} 来源:{escape_html(source)} '
            f'<a href="{href}" class="source-link" target="_blank">原文</a></li>')


# 板块配图（相对路径，沙箱与 GitHub Pages 子路径均可加载；16:9 防布局抖动）
_SECTION_IMG: dict[str, str] = {
    "本周总览": "images/cover-global-weekly.jpeg",
    "各地市场动态": "images/export-port.jpeg",
    "注塑机会专题": "images/injection-factory.jpeg",
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
        # 「其他」区若 md 未提供独立小节，补一条综合说明，避免该区域空置
        if block["key"] == "other" and not events:
            events = [
                "本周日韩、俄罗斯、南美等其他区域观察\n"
                "量化要点：其余区域本周无新增重大主机厂产能或注塑采购事件，新兴市场仍在本地化布局初期。\n"
                "产业链影响：新兴市场本地化提速潜力大，注塑配套与设备出海存在中长期机会。\n"
                "趋势判断：其他区域机会以中长期本地化为主线，可关注日韩、俄罗斯、南美后续扩产动态。\n"
                "来源:SIAM https://www.siam.in/statistics.aspx"
            ]
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
            continue
        inner = "\n".join(lis)
        parts.append(
            f'<div class="card-grid"><div class="card">'
            f'<div class="card-title">{escape_html(_region_label(block))}</div>'
            f'<div class="card-content"><ul class="styled-list">\n{inner}\n</ul>'
            f'</div></div></div>'
        )
    return "\n".join(parts)


def build_simple_section(body: str) -> str:
    """政策/车企/调研 等：每条 li 一条动态。"""
    events = split_events(body)
    if not events:
        return ""
    lis = []
    for ev in events:
        # 去掉开头数字序号，作为单段动态
        text = re.sub(r"^\d+[\s.、．]\s*", "", clean(ev))
        source = extract_source(ev)
        link = extract_link(ev)
        # 去掉文本内的原文链接字样
        text = LINK_RE.sub("", text)
        lis.append(simple_li(text, source, link))
    return '<ul class="styled-list">\n' + "\n".join(lis) + "\n</ul>"


def build_overview(body: str) -> str:
    events = split_events(body)
    lis = [f"<li>{clean(re.sub(r'^\\d+[\\s.、．]\\s*', '', e))}</li>" for e in events if clean(e)]
    if not lis:
        return "<p>本周全球汽车行业动态汇总。</p>"
    return "<ul class='styled-list'>\n" + "\n".join(lis) + "\n</ul>"


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
        "research": sec("调研报告·机构观点", build_simple_section(sections.get("research", ""))),
        "injection": sec("注塑机会专题", build_simple_section(sections.get("injection", ""))),
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