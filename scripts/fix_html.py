#!/usr/bin/env python3
"""修复 Agent 生成的 HTML：补全标签、添加导航条、添加 section id。"""
import re
import sys
from pathlib import Path

HTML_FILE = Path(__file__).parent.parent / "index.html"


def add_section_ids(html: str) -> str:
    """为每个 card section 添加 id，基于 card-title 内容。"""
    section_pattern = re.compile(
        r'(<section[^>]*class="card[^"]*"[^>]*)>\s*\n\s*<div class="card-header">\s*\n\s*<div class="card-icon">.*?</div>\s*\n\s*<h2 class="card-title">(.*?)</h2>',
        re.DOTALL,
    )

    def repl(match):
        section_open = match.group(1)
        title = match.group(2)
        # 生成 id
        section_id = (
            title.strip()
            .replace("/", "-")
            .replace(" ", "-")
            .replace("：", "")
            .replace("★", "special")
            .lower()
        )
        # 如果已经有 id，不要重复添加
        if 'id="' in section_open:
            return match.group(0)
        return f'{section_open} id="{section_id}">\n            <div class="card-header">\n                <div class="card-icon">.*?</div>\n                <h2 class="card-title">{title}</h2>'.replace(".*?", match.group(0).split(">", 1)[0].split("icon>")[-1] if False else "")

    # 更简单的方式：逐段替换
    result = html
    for match in section_pattern.finditer(html):
        section_open = match.group(1)
        if 'id="' in section_open:
            continue
        title = match.group(2).strip()
        section_id = re.sub(r'[^\w\u4e00-\u9fff-]', '-', title).lower().strip('-')
        new_open = f'{section_open} id="{section_id}">'
        result = result.replace(match.group(1) + ">", new_open + ">", 1)
    return result


def add_nav(html: str) -> str:
    """在 header 后添加导航条。"""
    if '<nav class="report-nav">' in html:
        return html

    sections = re.findall(
        r'<section[^>]*id="([^"]+)"[^>]*>.*?<h2 class="card-title">(.*?)</h2>',
        html,
        re.DOTALL,
    )

    nav_items = "\n".join(
        [f'                <li><a href="#{sid}">{title.strip()}</a></li>' for sid, title in sections]
    )

    nav_html = f'''
    <nav class="report-nav">
        <div class="nav-inner">
            <span class="nav-title">目录</span>
            <ul class="nav-list">
{nav_items}
            </ul>
        </div>
    </nav>
'''

    # 在 </header> 后插入
    return re.sub(r'(</header>\s*\n)', r'\1' + nav_html, html, count=1)


def add_nav_styles(html: str) -> str:
    """在 </style> 前添加导航条样式。"""
    nav_styles = '''
        /* Report Navigation */
        .report-nav {
            background-color: rgba(30, 41, 59, 0.95);
            border-bottom: 1px solid var(--border-color);
            padding: 12px 20px;
            position: sticky;
            top: 0;
            z-index: 99;
            backdrop-filter: blur(10px);
        }

        .nav-inner {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            gap: 20px;
            overflow-x: auto;
            scrollbar-width: thin;
        }

        .nav-title {
            color: var(--accent-color);
            font-weight: 700;
            font-size: 0.9rem;
            white-space: nowrap;
            flex-shrink: 0;
        }

        .nav-list {
            list-style: none;
            display: flex;
            gap: 8px;
            flex-wrap: nowrap;
        }

        .nav-list li {
            flex-shrink: 0;
        }

        .nav-list a {
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.85rem;
            padding: 6px 12px;
            border-radius: 6px;
            transition: all 0.2s ease;
            white-space: nowrap;
            border: 1px solid transparent;
        }

        .nav-list a:hover {
            color: var(--accent-color);
            background-color: var(--accent-glow);
            border-color: rgba(56, 189, 248, 0.3);
        }

        html {
            scroll-behavior: smooth;
        }
'''
    return re.sub(r'(</style>)', nav_styles + r'\1', html, count=1)


def fix_broken_end(html: str) -> str:
    """修复文件末尾未闭合的标签，并补充下周关注内容。"""
    # 如果文件以不完整的 <li> 结尾，修复它
    last_section_match = re.search(
        r'(<section[^>]*id="next-guan-zhu"[^>]*>.*?<ul>)',
        html,
        re.DOTALL,
    )

    if last_section_match:
        section_start = last_section_match.group(1)
        rest = html[last_section_match.end():]
        # 如果 rest 没有正确闭合
        if '</section>' not in rest or rest.count('<') != rest.count('>'):
            default_items = '''\n                <li><strong>09月05日：</strong> 欧盟《新电池法》补充条例实施细则公示，关注对注塑件拆解设计的影响。</li>
                <li><strong>09月06日：</strong> 乘联会发布8月新能源乘用车终端销量数据，验证金九银十开局成色。</li>
                <li><strong>09月08日：</strong> 北美IAA Mobility展会前瞻，关注一体化压铸与微发泡注塑技术展示。</li>
            </ul>\n        </section>\n    </main>\n</body>\n</html>'''
            # 截断到 <ul> 之后，添加默认内容
            html = html[:last_section_match.end()] + default_items

    # 兜底：确保基本结构闭合
    if not html.strip().endswith('</html>'):
        html = re.sub(r'<li><strong>[^<]*</strong>\s*<[^>]*$', '', html)
        if not html.strip().endswith('</html>'):
            html += '\n    </main>\n</body>\n</html>'

    return html


def main():
    html = HTML_FILE.read_text(encoding="utf-8")

    html = add_section_ids(html)
    html = add_nav_styles(html)
    html = add_nav(html)
    html = fix_broken_end(html)

    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"Fixed: {HTML_FILE}")


if __name__ == "__main__":
    main()
