#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为渲染后的 index.html 注入板块配图（本周总览 / 各地市场动态 / 注塑机会专题）。

定位：render_html.py 在解析/渲染时会丢弃 Agent HTML 里的 <img>（它只抽取文本卡），
因此配图放在渲染后处理阶段注入，确保最终 index.html 真正含图。

配图来源（优先）：
    从 Agent 输出的 markdown（weekly_*.md）中提取真实远程图片 URL
    （形如 `![alt](https://...)`），按出现顺序分配到三个板块。
  不再使用本地超大 jpeg（1MB/张）以免页面过大、拖慢 GitHub Pages。

用法：
    python3 scripts/inject_images.py [index.html] [--md weekly_20260918.md]
    - 未给 --md 时自动取项目根最新 weekly_*.md
"""
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 远程图片提取正则：匹配 `![alt](https://...)`
IMG_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")

# 回退本地小图（webp，体积 ~40KB，供 Agent 远程图不可达时兜底，避免破图/空图）
_FALLBACKS = [
    "images/cover-global-weekly.webp",
    "images/export-port.webp",
    "images/injection-factory.webp",
]


def _reachable(url: str, timeout: float = 8.0) -> bool:
    """轻量校验远程图片是否可达（HEAD 优先，失败降级 GET 前部字节）。"""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0",
                                                                     "Range": "bytes=0-128"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return 200 <= r.status < 400
        except Exception:
            return False


def collect_md_images(md_path: Path | None) -> list[tuple[str, str]]:
    """从 md 提取 (alt, url) 列表；探测每个 url，不可达的替换为本地小图。"""
    if not md_path or not md_path.exists():
        return []
    text = md_path.read_text(encoding="utf-8")
    hits: list[tuple[str, str]] = []
    fallback_i = 0
    for m in IMG_RE.finditer(text):
        alt = m.group(1).strip() or "行业配图"
        url = m.group(2).strip().rstrip(".)】")
        if not url:
            continue
        if _reachable(url):
            hits.append((alt, url))
        else:
            fb = _FALLBACKS[fallback_i % len(_FALLBACKS)]
            print(f"[warn] 远程图不可达，回退本地小图: {url} → {fb}")
            hits.append((alt, fb))
            fallback_i += 1
        time.sleep(0.2)
    return hits


def figure_html(cls: str, src: str, alt: str) -> str:
    return (f'<figure class="weekly-figure {cls}">'
            f'<img src="{src}" alt="{alt}" class="weekly-img" '
            f'width="1280" height="720" loading="lazy">'
            f'</figure>')


# 插入点：section id → (在该 section 内定位的锚点, 图片类名)
PLAN = [
    {
        "tag": r'<section class="key-points" id="overview">',
        "anchor": r'(<div class="kp-grid">)',
        "cls": "weekly-figure-hero",
        "fallback_alt": "本周全球汽车行业动态总览配图",
    },
    {
        "tag": r'<section class="section" id="markets">',
        "anchor": r'(<div class="subsection region-cn" id="china">)',
        "cls": "weekly-figure-markets",
        "fallback_alt": "各地市场动态：汽车市场场景配图",
    },
    {
        "tag": r'<section class="injection-section" id="injection">',
        "anchor": r'(<section class="injection-section" id="injection">)',
        "cls": "weekly-figure-injection",
        "fallback_alt": "注塑机会专题：汽车注塑零部件配图",
    },
]


def inject(html: str, images: list[tuple[str, str]]) -> tuple[str, int]:
    count = 0
    for idx, plan in enumerate(PLAN):
        tag_m = re.search(plan["tag"], html)
        if not tag_m:
            continue
        # 优先用 md 提供的图片（按板块顺序）；不足则回退到本地小图兜底逻辑外之一
        src = ""
        alt = plan["fallback_alt"]
        if idx < len(images):
            alt, src = images[idx]
        if not src:
            continue  # 无可用图片，该板块不强插
        seg_start = tag_m.end()
        anchor_re = re.compile(plan["anchor"])
        m = anchor_re.search(html, seg_start)
        img_html = "\n      " + figure_html(plan["cls"], src, alt) + "\n"
        if not m:
            # injection 无 header，anchor 就是开标签之后的 placeholder；回退插到 section 开头
            html = html[:seg_start] + img_html + html[seg_start:]
            count += 1
            continue
        html = html[:m.start()] + img_html + html[m.start():]
        count += 1
    return html, count


def _latest_md() -> Path | None:
    today = ROOT / f"weekly_{datetime.now().strftime('%Y%m%d')}.md"
    if today.exists():
        return today
    mds = sorted(ROOT.glob("weekly_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mds[0] if mds else None


def main() -> None:
    args = sys.argv[1:]
    idx_path = ROOT / "index.html"
    md_path: Path | None = None
    rest: list[str] = []
    for a in args:
        if a == "--md":
            continue
        if a.startswith("--md="):
            md_path = Path(a[len("--md="):])
        elif not a.startswith("--"):
            rest.append(a)
    if rest:
        idx_path = Path(rest[0])
    if md_path is None:
        md_path = _latest_md()
    images = collect_md_images(md_path)
    if not images:
        print(f"[warn] 未在 md 中发现远程配图（{md_path}），本轮跳过注入（不改动 index.html）")
        return

    html = idx_path.read_text(encoding="utf-8")
    new_html, count = inject(html, images)
    if count:
        idx_path.write_text(new_html, encoding="utf-8")
        print(f"已注入 {count} 张配图（来自 md 远程图片）到 {idx_path}")
    else:
        print("未匹配到板块锚点，未注入")


if __name__ == "__main__":
    main()