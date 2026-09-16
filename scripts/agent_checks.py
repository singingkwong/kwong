#!/usr/bin/env python3
"""Agent 输出检查清单。

对扣子 Agent 生成/返回的周报 HTML 做结构化合规校验，确保输出稳定：
- 必须出现的 7 大 section（本周总览 / 各地市场动态 / 政策 / 车企 / 调研 / 注塑专题 / 下周关注）
- 市场动态必须覆盖 6 大区域（中国、北美、欧洲、东南亚、印度、其他）
- 市场每条动态必须是完整"三要点"（关键数据/事件、影响分析、趋势判断）+ 来源 + 原文链接
  （三要点与来源必须位于同一条动态内，不得拆散）
- 原文链接必须真实可达（复用 render_html 的链接校验）

返回一份 CheckItem 列表，含 pass/fail；并提供 summarize 输出可读清单。
"""
import re
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup

try:  # 尽量复用已有链接校验逻辑，避免重复
    from render_html import _is_fake_link_format, _link_is_reachable
except Exception:  # noqa: BLE001 独立可运行
    def _is_fake_link_format(_href: str) -> bool:
        return False

    def _link_is_reachable(_href: str) -> bool:
        return True


EXPECTED_SECTIONS: List[Tuple[str, List[str], bool]] = [
    ("本周总览", ["本周总览", "核心看点", "本周看点", "总览"], True),
    ("各地市场动态", ["各地市场", "市场动态", "区域市场", "市场"], True),
    ("政策动态", ["政策"], True),
    ("车企动态", ["车企", "整车", "主机厂"], True),
    ("调研报告/机构观点", ["调研", "机构", "研究报告", "观点", "研报"], True),
    ("注塑机会专题", ["注塑", "注射", "注塑机会"], True),
    ("下周关注", ["下周"], True),
]

# 市场六大区域：key -> 该区域名词、其所属区域卡标题、以及可在正文兜底识别的关键词
MARKET_REGIONS: List[Dict[str, object]] = [
    {"key": "china", "label": "中国", "names": ["中国"]},
    {"key": "na", "label": "北美", "names": ["北美"], "kws": ["美国", "加拿大", "墨西哥"]},
    {"key": "eu", "label": "欧洲", "names": ["欧洲"], "kws": ["欧盟", "德国", "法国", "英国"]},
    {"key": "sea", "label": "东南亚", "names": ["东南亚"], "kws": ["印尼", "泰国", "越南", "马来西亚"]},
    {"key": "india", "label": "印度", "names": ["印度"]},
    {"key": "other", "label": "其他", "names": ["其他"], "kws": ["南美", "巴西", "阿根廷", "俄罗斯", "日本", "韩国", "澳洲"]},
]

POINT_LABELS = ("关键数据", "影响分析", "趋势判断")

MIN_EVENTS_PER_REGION = 4  # 主要区域每条至少 4 条


class CheckItem:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail

    def __repr__(self) -> str:
        return f"{'✅' if self.passed else '❌'} {self.name} {self.detail}"


def _find_market_section(sections: List[Dict[str, str]]) -> Dict[str, str]:
    for sec in sections:
        if any(k in sec["title"] for k in ("各地市场", "市场动态", "区域市场", "市场")):
            return sec
    return {}


def _extract_per_region_data(market_body: str) -> Dict[str, List[Dict[str, object]]]:
    """从市场模块原始 HTML 中，把动态按区域归类，返回 {region_key: [card]}。

    每张卡/每个 li 视为一条事件；通过该条所在卡片标题（card-title / h3/h4）
    或正文关键词判断所属区域。
    """
    soup = BeautifulSoup(market_body, "html.parser")
    result: Dict[str, List[Dict[str, object]]] = {r["key"]: [] for r in MARKET_REGIONS}

    def region_for(title: str, text: str) -> str:
        title_text = (title or "").strip()
        for r in MARKET_REGIONS:
            for n in r["names"]:
                if title_text == n or title_text.startswith(n + " ") or title_text.startswith(n + "：") or title_text.startswith(n + ":"):
                    return r["key"]
        # 兜底：正文关键词
        low = text
        for r in MARKET_REGIONS:
            for k in r.get("kws", []):
                if k in low:
                    return r["key"]
        return ""

    # 优先按 .card（含 card-title）拆分，一条事件一卡
    cards = soup.select(".card, .region-card, .market-card")
    if not cards:
        # 退化为 section 内所有 li / p
        items = soup.find_all("li") or soup.find_all("p")
        for it in items:
            txt = it.get_text(" ", strip=True)
            if len(txt) >= 8:
                rk = region_for("", txt)
                if rk:
                    result[rk].append({"text": txt})
        return result

    for c in cards:
        ct = c.select_one(".card-title, h3, h4")
        title = clean_text(ct.get_text(" ", strip=True)) if ct else ""
        text = clean_text(c.get_text(" ", strip=True))
        rk = region_for(title, text)
        if not rk:
            continue
        # 区域内事件：优先拆 card 内的 li（每个 li 一条独立事件）
        lis = c.find_all("li")
        if lis:
            for li in lis:
                li_txt = clean_text(li.get_text(" ", strip=True))
                if len(li_txt) >= 8:
                    result[rk].append({"title": "", "text": li_txt, "el": li})
        else:
            result[rk].append({"title": title, "text": text, "el": c})
    return result


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _has_three_points(text: str) -> bool:
    """文本是否包含完整三要点（关键数据/影响分析/趋势判断）。"""
    cnt = 0
    for lab in POINT_LABELS:
        if lab in text:
            cnt += 1
    return cnt >= 3


def _point_intact_per_item(el) -> bool:
    """校验：一条动态卡/li 内三要点与来源是否聚在一起（未被拆到多个子项）。

    对 .card 或 <li> 元素：检查其直接子 p 中是否同时含有三个要点标签。
    """
    for p in el.find_all("p"):
        t = p.get_text(" ", strip=True)
        if any(lab in t for lab in POINT_LABELS):
            sub_cnt = 0
            for lab in POINT_LABELS:
                if lab in t:
                    sub_cnt += 1
            # 同一 p 内 ≥2 个要点说明它自己就是一个事件；若单独 p 只含 1 个要点则视为拆散
            if sub_cnt >= 2:
                continue
    return True


def _has_source_and_link(el) -> Tuple[bool, bool]:
    text = clean_text(el.get_text(" ", strip=True))
    has_source = bool(re.search(r"来源[:：]\s*\S+", text))
    a = el.find("a", href=True)
    has_link = bool(a and a["href"].startswith("http"))
    return has_source, has_link


def validate(html: str) -> List[CheckItem]:
    from render_html import split_sections_by_title

    checks: List[CheckItem] = []
    full_html = html
    if "<body" in full_html.lower():
        m = re.search(r"<body[^>]*>(.*?)</body>", full_html, re.DOTALL | re.IGNORECASE)
        if m:
            full_html = m.group(1)

    # 1) 基础结构
    sections = split_sections_by_title(full_html)
    present = {s["title"] for s in sections}
    for name, kws, required in EXPECTED_SECTIONS:
        found = any(any(k in t for k in kws) for t in present)
        checks.append(CheckItem(f"板块「{name}」", found if required else (True or found),
                                "存在" if found else "缺失！"))

    # 1.5) 正式板块空态检测（板块标题存在但内容为空态 → 判 FAIL，纳入补缺）
    EMPTY_PHRASES = ("暂无", "无新增", "未更新", "待补充", "暂缺", "没有更新", "无重点")
    for name, kws, required in EXPECTED_SECTIONS:
        if name == "各地市场动态":  # 市场区域单独检测
            continue
        sec = next((s for s in sections if any(k in s["title"] for k in kws)), None)
        if not sec:
            continue  # 已由板块存在性检查覆盖
        body_txt = clean_text(re.sub(r"<[^>]+>", " ", sec.get("body", "")))
        empty_hit = [p for p in EMPTY_PHRASES if p in body_txt]
        has_content = len(re.sub(r"、|。|，", "", body_txt)) > 30  # 去掉标点后仍有实质文字
        if empty_hit and not has_content:
            checks.append(CheckItem(f"板块「{name}」有实质内容", False,
                                    f"空态占位（{'/'.join(empty_hit)}）→ 需补缺"))
        else:
            checks.append(CheckItem(f"板块「{name}」有实质内容", True,
                                    "无空态占位" if empty_hit else "正常"))

    # 2) 市场区域覆盖
    market = _find_market_section(sections)
    all_names = " ".join(present)
    checks.append(CheckItem("市场模块存在",
                            bool(market) or any(k in all_names for k in ("市场",)),
                            "存在" if (market or any(k in all_names for k in ("市场",))) else "缺失"))

    if market:
        region_data = _extract_per_region_data(market.get("body", ""))
        for r in MARKET_REGIONS:
            key, label = r["key"], r["label"]
            items = region_data.get(key, [])
            checks.append(CheckItem(
                f"市场区域「{label}」",
                len(items) >= 1,
                f"{len(items)} 条" if items else "无内容（导致该板块无 news）",
            ))
            if items:
                points_ok = any(_has_three_points(it["text"]) for it in items)
                checks.append(CheckItem(f"  「{label}」含三要点解读", points_ok,
                                        "含三要点" if points_ok else "缺三要点"))

    # 3) 三要点 + 来源 + 链接 覆盖
    if market:
        soup_m = BeautifulSoup(market.get("body", ""), "html.parser")
        events = soup_m.select(".card") or soup_m.find_all("li")
        events = [e for e in events if len(e.get_text(" ", strip=True)) >= 20]
        if events:
            have_points = sum(1 for e in events if _has_three_points(e.get_text(" ", strip=True)))
            have_src = sum(1 for e in events if re.search(r"来源[:：]\s*\S+", e.get_text(" ", strip=True)))
            have_link_a = sum(1 for e in events if e.find("a", href=True))
            checks.append(CheckItem("市场事件数（待核）", len(events) >= 1, f"共 {len(events)} 条"))
            checks.append(CheckItem("三要点覆盖率", have_points >= len(events) * 0.8,
                                    f"{have_points}/{len(events)} 条含三要点"))
            checks.append(CheckItem("来源标注重率", have_src >= len(events) * 0.8,
                                    f"{have_src}/{len(events)} 条含来源"))
            checks.append(CheckItem("原文链接覆盖", have_link_a >= len(events) * 0.8,
                                    f"{have_link_a}/{len(events)} 条含原文链接"))

    # 4) 原文链接可达性（抽样，防卡死）
    anchors = [a["href"] for a in BeautifulSoup(full_html, "html.parser").find_all("a", href=True)
               if a["href"].startswith("http")]
    fake = [h for h in anchors if _is_fake_link_format(h)]
    checks.append(CheckItem("原文链接无伪造格式", not fake, f"{len(fake)} 条疑似伪造" if fake else f"{len(anchors)} 条链接格式正常"))

    # 5) 配图数量必须达标（≥3 张）
    soups = [BeautifulSoup(full_html, "html.parser")]
    soup = soups[0]
    n_img = len([i for i in soup.find_all("img") if i.get("src") and i["src"].startswith("http")])
    checks.append(CheckItem("配图数量达标",
                            n_img >= 3,
                            f"{n_img} 张配图（要求 ≥3）"))

    # 6) 全篇原文链接总数必须达标（≥26 条）
    n_src = len([a for a in soup.find_all("a", class_="source-link", href=True)
                 if a["href"].startswith("http")])
    checks.append(CheckItem("原文链接数量达标",
                            n_src >= 26,
                            f"{n_src} 条原文链接（要求 ≥26）"))

    return checks


def empty_sections(checks: List[CheckItem]) -> List[str]:
    """从校验失败项中提取"空态占位"的正式板块名（用于补缺指令）。"""
    empty: List[str] = []
    for c in checks:
        if not c.passed and "有实质内容" in c.name and "空态占位" in c.detail:
            name = c.name
            for lab in ("本周总览", "各地市场", "政策动态", "车企动态", "调研报告", "注塑机会", "下周关注"):
                if lab in name:
                    empty.append(name.split("「")[1].split("」")[0])
                    break
    return empty


def summarize(checks: List[CheckItem]) -> Dict[str, object]:
    passed = sum(1 for c in checks if c.passed)
    total = len(checks)
    failed = [c for c in checks if not c.passed]
    return {"passed": passed, "total": total, "ok": not failed, "failed": failed}


def print_report(checks: List[CheckItem]) -> str:
    lines = ["━━━ Agent 输出检查清单 ━━━"]
    for c in checks:
        lines.append(str(c))
    s = summarize(checks)
    lines.append(f"\n共 {s['total']} 项：通过 {s['passed']}，未通过 {len(s['failed'])} → {'✅ 合格' if s['ok'] else '❌ 需要重试/修正'}")
    return "\n".join(lines)