#!/usr/bin/env python3
"""
修复 Agent 生成的汽车行业周报 HTML：
- 套用统一样式（styles/main.css）
- 清理未闭合标签
- 添加/更新顶部导航栏
- 添加编制团队信息
- 添加数据来源说明
- 给 section 设置语义化 id 用于锚点导航
"""

import os
import re
import sys
from html.parser import HTMLParser
from bs4 import BeautifulSoup


def is_self_closing(tag_name: str) -> bool:
    """判断标签是否为自闭合标签。"""
    return tag_name.lower() in {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"
    }


def fix_unclosed_tags(html: str) -> str:
    """通过栈匹配修复未闭合标签，保留合法结构。"""
    class TagStackParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.output = []
            self.skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if self.skip_depth:
                self.skip_depth += 1
                return
            if tag.lower() == "html":
                self.skip_depth = 1
                return
            attr_str = ""
            if attrs:
                attr_str = " " + " ".join(
                    f'{k}="{v}"' if v is not None else k for k, v in attrs
                )
            self.output.append(f"<{tag}{attr_str}>")
            if not is_self_closing(tag):
                self.stack.append(tag.lower())

        def handle_endtag(self, tag):
            tag_lower = tag.lower()
            if self.skip_depth:
                self.skip_depth -= 1
                return
            if tag_lower == "html" and self.skip_depth == 1:
                self.skip_depth = 0
                return
            if tag_lower in self.stack:
                while self.stack and self.stack[-1] != tag_lower:
                    closing = self.stack.pop()
                    self.output.append(f"</{closing}>")
                if self.stack:
                    self.stack.pop()
                self.output.append(f"</{tag}>")

        def handle_data(self, data):
            if not self.skip_depth:
                self.output.append(data)

        def handle_entityref(self, name):
            if not self.skip_depth:
                self.output.append(f"&{name};")

        def handle_charref(self, name):
            if not self.skip_depth:
                self.output.append(f"&#{name};")

        def close(self):
            while self.stack:
                closing = self.stack.pop()
                self.output.append(f"</{closing}>")
            super().close()

    # 临时去掉 <html> 和 </html>，让 HTMLParser 不会自动补全
    html = re.sub(r"<!DOCTYPE\s+html[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<html[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"</html>", "", html, flags=re.IGNORECASE)

    parser = TagStackParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as e:
        print(f"[fix_html] 修复标签时出错: {e}")
        return html

    inner = "".join(parser.output)
    return f"<!DOCTYPE html>\n<html lang=\"zh-CN\">{inner}</html>"


# 章节标题 -> 语义化 id
SECTION_ID_MAP = {
    "本周总览": "overview",
    "各地市场动态": "markets",
    "全球市场动态": "markets",
    "政策动态": "policy",
    "政策法规": "policy",
    "车企动态": "oem",
    "车企与供应链": "oem",
    "调研报告": "reports",
    "机构观点": "reports",
    "调研报告/机构观点": "reports",
    "注塑机会": "injection",
    "注塑机会专题": "injection",
    "下周关注": "outlook",
    "数据来源": "sources",
}


def get_section_id(title: str) -> str:
    title_clean = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", title)
    for key, sid in SECTION_ID_MAP.items():
        if key in title or title in key:
            return sid
    # fallback：拼音化
    fallback = re.sub(r"[^a-zA-Z0-9]", "-", title_clean).lower().strip("-") or "section"
    return fallback[:30]


def clean_section_title(title: str) -> str:
    """去掉英文副标题等多余内容，保留中文标题。"""
    # 去除英文说明，如 "本周总览 Weekly Overview"
    title = re.sub(r"\s*[A-Za-z][A-Za-z\s/-]*$", "", title).strip()
    # 去除括号里的英文
    title = re.sub(r"\s*[（(][A-Za-z\s/-]+[）)]", "", title).strip()
    return title


def extract_header_info(soup: BeautifulSoup):
    title = "全球汽车行业深度周报"
    date = ""
    team = "编制团队：YZM海外汽车行业拓展项目组"

    header = soup.body.find("div", class_="header") or soup.body.find("header")
    if header:
        h1 = header.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        date_div = header.find("div", class_="date")
        if date_div:
            date = date_div.get_text(strip=True)
        team_div = header.find("div", class_="team")
        if team_div:
            team = team_div.get_text(strip=True)

    # 如果 body 开头是 h1 但没 header div
    if not date:
        h1 = soup.body.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    # 从 title 标签提取日期兜底
    if not date and soup.title:
        m = re.search(r"(\d{4}年\d{2}月\d{2}日)", soup.title.get_text())
        if m:
            date = m.group(1)

    return title, date, team


def extract_sections(soup: BeautifulSoup):
    """返回 [(id, title, content_html)]，content 不包含标题元素。"""
    sections = []
    seen_ids = set()

    # 先把嵌套在其它 section 里的「数据来源」提升到 body 顶层
    for nested in list(soup.body.find_all("section")):
        parent = nested.find_parent("section")
        if parent is None:
            continue
        title_elem = nested.find("div", class_="section-title") or nested.find(["h2", "h3"])
        if title_elem and "数据" in title_elem.get_text():
            nested.extract()
            soup.body.append(nested)

    for section in list(soup.body.find_all("section")):
        # 跳过嵌套在 section 里的 section
        parent = section.find_parent("section")
        if parent is not None:
            continue

        title_elem = section.find("div", class_="section-title") or section.find(["h2", "h3"])
        if not title_elem:
            continue

        raw_title = title_elem.get_text(strip=True)
        title = clean_section_title(raw_title)
        sid = get_section_id(title)

        # 避免 id 重复
        base_sid = sid
        counter = 2
        while sid in seen_ids:
            sid = f"{base_sid}-{counter}"
            counter += 1
        seen_ids.add(sid)

        # 把标题元素替换为统一的 <h2><span>title</span></h2>
        new_h2 = soup.new_tag("h2")
        new_span = soup.new_tag("span")
        new_span.string = title
        new_h2.append(new_span)
        title_elem.replace_with(new_h2)

        # 获取 section 内容字符串（去掉 section 标签本身）
        content_html = "".join(str(child) for child in section.contents).strip()

        sections.append({
            "id": sid,
            "title": title,
            "content_html": content_html,
        })

    return sections


def ensure_sources_section(sections: list) -> list:
    """确保只有一个规范的数据来源 section。"""
    # 删除已有的数据来源 section，统一重新生成
    sections = [s for s in sections if s["title"] != "数据来源"]

    sources_html = """
        <h2><span>数据来源</span></h2>
        <div class="card">
            <p class="sources-intro">本报告数据与资讯来源于以下公开渠道及行业数据库：</p>
            <div class="grid-3">
                <div class="source-col">
                    <h4>行业数据库</h4>
                    <ul>
                        <li>MarkLines 付费数据库</li>
                        <li>乘联会 (CPCA)</li>
                        <li>中汽协 (CAAM)</li>
                        <li>ACEA（欧洲）</li>
                    </ul>
                </div>
                <div class="source-col">
                    <h4>区域市场</h4>
                    <ul>
                        <li>GAIKINDO（印尼）</li>
                        <li>TAI / FTI（泰国）</li>
                        <li>ANFAVEA / Fenabrave（巴西）</li>
                        <li>SIAM（印度）、AEB（俄罗斯）</li>
                    </ul>
                </div>
                <div class="source-col">
                    <h4>媒体与研报</h4>
                    <ul>
                        <li>盖世汽车、36氪、界面新闻</li>
                        <li>AlixPartners、麦肯锡</li>
                        <li>Maybank、爱建证券</li>
                    </ul>
                </div>
            </div>
        </div>
    """
    sections.append({
        "id": "sources",
        "title": "数据来源",
        "content_html": sources_html,
    })
    return sections


def build_nav(sections: list) -> str:
    items = []
    for s in sections:
        items.append(f'<li><a href="#{s["id"]}">{s["title"]}</a></li>')
    return (
        '<nav class="top-nav">\n'
        '    <div class="nav-brand">📊 全球汽车行业周报</div>\n'
        '    <ul class="nav-menu">\n        '
        + "\n        ".join(items)
        + '\n    </ul>\n'
        '</nav>\n'
    )


def build_html(title: str, date: str, team: str, nav_html: str, sections: list) -> str:
    sections_html = "\n".join(
        f'<section id="{s["id"]}">\n{s["content_html"]}\n</section>'
        for s in sections
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {date}</title>
    <link rel="stylesheet" href="./styles/main.css">
</head>
<body>
{nav_html}
    <div class="container">
        <header class="hero">
            <div class="hero-badge">WEEKLY INSIGHT</div>
            <h1>{title}</h1>
            <div class="hero-meta">
                <span class="hero-date">{date}</span>
                <span class="hero-divider"></span>
                <span class="hero-team">{team}</span>
            </div>
        </header>
        <main>
{sections_html}
        </main>
    </div>
</body>
</html>
"""


def fix_html(html: str) -> str:
    # 先简单修复未闭合标签
    html = fix_unclosed_tags(html)

    soup = BeautifulSoup(html, "html.parser")
    if not soup.body:
        return html

    title, date, team = extract_header_info(soup)
    sections = extract_sections(soup)
    sections = ensure_sources_section(sections)
    nav_html = build_nav(sections)
    result = build_html(title, date, team, nav_html, sections)

    # 最终再修复一次，防止模板拼接引入的问题
    result = fix_unclosed_tags(result)
    return result


def main():
    file_path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        print(f"[fix_html] 文件不存在: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()

    fixed = fix_html(html)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(fixed)

    # 简单验证
    soup = BeautifulSoup(fixed, "html.parser")
    sections = soup.find_all("section")
    nav = soup.find("nav")
    print(f"[fix_html] 已修复 {file_path}")
    print(f"[fix_html] 导航栏: {'已添加' if nav else '未添加'}")
    print(f"[fix_html] Section 数量: {len(sections)}")
    for s in sections:
        title = s.find(["h2", "h3"])
        print(f"  - {s.get('id', 'no-id')}: {title.get_text(strip=True) if title else '无标题'}")


if __name__ == "__main__":
    main()
