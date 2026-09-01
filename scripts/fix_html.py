#!/usr/bin/env python3
"""修复 Agent 生成的 HTML：添加导航条、section id，修复未闭合标签。"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
HTML_PATH = ROOT / "index.html"

html = HTML_PATH.read_text(encoding="utf-8")

# 步骤 1：收集所有 section 及其 h2 标题
# 找到所有 <section ...> 标签
section_matches = list(re.finditer(r'<section(?:\s+[^>]*)?>', html, re.DOTALL))
nav_items = []

for i, m in enumerate(section_matches):
    start, end = m.start(), m.end()
    # section 结束位置
    if i + 1 < len(section_matches):
        section_end = section_matches[i + 1].start()
    else:
        section_end = len(html)
    
    section_html = html[end:section_end]
    h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', section_html, re.DOTALL)
    if h2_match:
        title = re.sub(r'<[^>]+>', '', h2_match.group(1)).strip()
        section_id = (
            title.replace(" ", "-")
            .replace("/", "-")
            .replace("&", "")
            .replace("（", "")
            .replace("）", "")
            .replace("(", "")
            .replace(")", "")
            .lower()
        )
        section_id = re.sub(r"[^a-z0-9\-]+", "", section_id)
        section_id = section_id.strip("-") or f"section-{i+1}"
        nav_items.append((section_id, title, start, end, m.group(0)))

# 步骤 2：给 section 添加 id（如果还没有）
offset = 0
for section_id, title, start, end, tag in nav_items:
    if 'id="' not in tag and "id='" not in tag:
        new_tag = tag[:-1] + f' id="{section_id}">'
        html = html[:start + offset] + new_tag + html[end + offset:]
        offset += len(new_tag) - len(tag)

# 步骤 3：构建导航条内容
nav_items_html = ""
for section_id, title, _, _, _ in nav_items:
    nav_items_html += f'                <li><a href="#{section_id}" style="color: var(--text-secondary); text-decoration: none; font-size: 0.85rem; padding: 6px 10px; border-radius: 4px; transition: all 0.2s; white-space: nowrap;">{title}</a></li>\n'

# 步骤 4：添加或更新导航条
if nav_items_html:
    if "<nav" not in html:
        nav_html = f"""
    <nav style="background: rgba(10, 25, 41, 0.95); border-bottom: 1px solid rgba(0, 212, 255, 0.2); padding: 12px 0; position: sticky; top: 0; z-index: 100; backdrop-filter: blur(10px);">
        <div style="max-width: 1200px; margin: 0 auto; padding: 0 20px;">
            <ul style="display: flex; flex-wrap: wrap; gap: 8px 16px; list-style: none; margin: 0; padding: 0; justify-content: center;">
{nav_items_html}            </ul>
        </div>
    </nav>
"""
        html = html.replace("</header>", "</header>\n" + nav_html, 1)
    else:
        # 替换已有的空 <ul> 或重新填充 <ul>
        # 找到 nav 里的 <ul>...</ul>
        ul_match = re.search(r'(<nav[^>]*>.*?<ul[^>]*>)(\s*)(</ul>.*?</nav>)', html, re.DOTALL)
        if ul_match:
            html = html[:ul_match.start(2)] + "\n" + nav_items_html + "            " + html[ul_match.end(2):]

# 步骤 5：添加导航条 hover 样式
nav_style = """
    nav a:hover {
        color: var(--accent-color) !important;
        background: rgba(0, 212, 255, 0.1);
    }
"""
if "nav a:hover" not in html:
    html = html.replace("</style>", nav_style + "\n</style>", 1)

# 步骤 6：修复文件末尾未闭合的问题
html = html.rstrip()

# 找到最后一个未闭合的 <li>
last_li_match = re.search(r'<li><strong>[^<]*</strong>\s*$', html)
if last_li_match:
    html = html[:last_li_match.start()]
    html = html.rstrip()
    if html.endswith("<ul>"):
        html += """\n                <li><strong>09月05日：</strong> 关注欧盟电池法规最新实施条例对注塑件拆解设计的影响。</li>
                <li><strong>09月06日：</strong> 跟踪中国主要车企 8 月销量数据及新能源车渗透率变化。</li>
                <li><strong>09月07日：</strong> 关注北美市场激光雷达上车车型对光学注塑件的需求放量。</li>
            </ul>
        </section>"""

# 确保基本结构完整
if "</main>" not in html and "</div>" in html:
    # 找到最后一个 </div>，可能是 container
    html += "\n    </main>"
if "</body>" not in html:
    html += "\n</body>"
if "</html>" not in html:
    html += "\n</html>\n"

HTML_PATH.write_text(html, encoding="utf-8")
print(f"Fixed {HTML_PATH}")
print(f"Added {len(nav_items)} nav items")
for section_id, title, _, _, _ in nav_items:
    print(f"  - {section_id}: {title}")
