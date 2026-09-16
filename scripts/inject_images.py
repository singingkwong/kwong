#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为渲染后的 index.html 注入板块配图（本周总览 / 各地市场动态 / 注塑机会专题）。

定位：render_html.py 在解析/渲染时会丢弃 Agent HTML 里的 <img>（它只抽取文本卡），
因此配图放在渲染后处理阶段注入，确保最终 index.html 真正含图。
部署到 GitHub Pages 后在子路径下依然可用（使用相对路径 images/xxx.jpeg）。

用法：
    python3 scripts/inject_images.py [index.html]
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def figure_html(cls: str, src: str, alt: str) -> str:
    return (f'<figure class="weekly-figure {cls}">'
            f'<img src="{src}" alt="{alt}" class="weekly-img" '
            f'width="1280" height="720" loading="lazy">'
            f'</figure>')


# 插入点：section id → (在 section 内第几个子节点后插入, 图片)
# 插入到各 section 内容(header)之后的第一个空白节点前，用简单字符串定位。
PLAN = [
    # (section 开标签正则, 在该 section 内、header 结束后的插入锚点替换)
    {
        "tag": r'<section class="key-points" id="overview">',
        "anchor": r'(<div class="kp-grid">)',
        "img": figure_html("weekly-figure-hero", "images/cover-global-weekly.jpeg", "本周全球汽车行业动态总览配图"),
        "after_header": True,
    },
    {
        "tag": r'<section class="section" id="markets">',
        "anchor": r'(<div class="subsection region-cn" id="china">)',
        "img": figure_html("weekly-figure-markets", "images/export-port.jpeg", "各地市场动态：新能源汽车出口与海运场景配图"),
        "after_header": False,
    },
    {
        "tag": r'<section class="injection-section" id="injection">',
        "anchor": r'(<section class="injection-section" id="injection">)',
        "img": figure_html("weekly-figure-injection", "images/injection-factory.jpeg", "注塑机会专题：汽车注塑零部件生产配图"),
        "after_header": True,
    },
]


def inject(html: str) -> tuple[str, int]:
    count = 0
    for plan in PLAN:
        tag_m = re.search(plan["tag"], html)
        if not tag_m:
            continue
        seg_start = tag_m.end()
        # 在 anchor 首次出现处插入（取 section 内的 anchor）
        anchor_re = re.compile(plan["anchor"])
        m = anchor_re.search(html, seg_start)
        if not m:
            # injection 无 header，anchor 就是开标签之后的 placeholder；回退插到 section 开头
            html = html[:seg_start] + "\n" + plan["img"] + html[seg_start:]
            count += 1
            continue
        # 插入到 anchor 之前（即图片作为 section 首个子元素）
        html = html[:m.start()] + "\n      " + plan["img"] + "\n" + html[m.start():]
        count += 1
    return html, count


def main() -> None:
    idx = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "index.html"
    html = idx.read_text(encoding="utf-8")
    new_html, count = inject(html)
    if count:
        idx.write_text(new_html, encoding="utf-8")
        print(f"已注入 {count} 张配图到 {idx}")
    else:
        print("未注入任何配图（可能已注入或未匹配到锚点）")


if __name__ == "__main__":
    main()