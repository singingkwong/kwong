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
    tag = m.group(0)
    # section 结束位置
    if i + 1 < len(section_matches):
        section_end = section_matches[i + 1].start()
    else:
        section_end = len(html)
    
    section_html = html[end:section_end]
    h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', section_html, re.DOTALL)
    if h2_match:
        title = re.sub(r'<[^>]+>', '', h2_match.group(1)).strip()
        # 优先使用 section 已有的 id
        existing_id_match = re.search(r'\sid=["\']([^"\']+)["\']', tag)
        if existing_id_match:
            section_id = existing_id_match.group(1)
        else:
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
        nav_items.append((section_id, title, start, end, tag))

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
        # 替换已有的 <ul>...</ul> 内容
        # 找到 nav 里的 <ul>...</ul>
        ul_match = re.search(r'(<nav[^>]*>.*?<ul[^>]*>)(.*?)(</ul>.*?</nav>)', html, re.DOTALL)
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

# 步骤 6：添加编制团队信息
if "YZM海外汽车行业拓展项目组" not in html:
    # 在 report-meta 里追加编制团队
    if '<div class="report-meta">' in html:
        html = re.sub(
            r'(<div class="report-meta">\s*)(.*?)(\s*</div>)',
            lambda m: f'{m.group(1)}{m.group(2).strip()}<br>\\n                编制团队：YZM海外汽车行业拓展项目组{m.group(3)}',
            html,
            count=1,
            flags=re.DOTALL,
        )
    else:
        # 如果没有 report-meta，在 h1 后面追加
        html = re.sub(
            r'(</h1>\s*</div>\s*<div>)',
            r'\1<div style="margin-top: 8px; font-size: 0.9rem; opacity: 0.8;">编制团队：YZM海外汽车行业拓展项目组</div><div>',
            html,
            count=1,
            flags=re.DOTALL,
        )

# 步骤 7：提取专家建议并格式化为独立 section
expert_section = ""
# 匹配 "专家建议：" 或 "专家建议：" 开头的段落
expert_match = re.search(
    r'<p[^>]*>\s*<strong>\s*专家建议[：:]\s*</strong>\s*(.*?)</p>',
    html,
    re.DOTALL | re.IGNORECASE,
)
if expert_match and "section-expert" not in html:
    expert_content = expert_match.group(1).strip()
    # 清理内容中的额外标签
    expert_content = re.sub(r'<[^>]+>', '', expert_content)
    expert_content = expert_content.strip()
    if expert_content:
        expert_section = f"""
        <!-- 专家建议 -->
        <section class="injection-section" id="section-expert">
            <h2>专家建议</h2>
            <div class="card" style="border-left: 4px solid var(--accent-color);">
                <p><strong>专家建议：</strong> {expert_content}</p>
            </div>
        </section>"""
        # 从原位置移除这段专家建议（避免重复）
        html = html[:expert_match.start()] + html[expert_match.end():]

# 步骤 7：修复文件末尾未闭合的问题
html = html.rstrip()

# 找到最后一个未闭合的 <li>（内容被截断）
last_li_match = re.search(r'<li[^>]*>.*?<p>[^<]*\s*$', html, re.DOTALL)
if last_li_match:
    # 截断到最后一个完整的 <li> 之前
    html = html[:last_li_match.start()]
    html = html.rstrip()

# 如果下周关注 section 没有正确闭合，补全
if "<section" in html and "下周关注" in html:
    # 找到下周关注 section 的位置
    next_week_match = re.search(r'<section[^>]*id="section-7"[^>]*>.*?</section>', html, re.DOTALL)
    if not next_week_match:
        # section 未闭合，补全
        html = html.rstrip()
        if not html.endswith("</section>"):
            # 补全 ul、section
            html += """
                </ul>
            </div>
        </section>"""

# 步骤 8：添加数据来源说明
sources_section = """
        <!-- 数据来源 -->
        <section id="sources">
            <h2>数据来源</h2>
            <div class="card">
                <p style="margin-bottom: 15px;">本报告数据与资讯来源于以下公开渠道及行业数据库，所有引用均标注来源及日期：</p>
                <div class="grid-3">
                    <div>
                        <h4>行业数据库</h4>
                        <ul style="list-style: disc; padding-left: 20px; color: var(--text-secondary);">
                            <li>MarkLines 付费数据库</li>
                            <li>乘联会 (CPCA)</li>
                            <li>中汽协 (CAAM)</li>
                            <li>ACEA（欧洲）</li>
                        </ul>
                    </div>
                    <div>
                        <h4>区域市场</h4>
                        <ul style="list-style: disc; padding-left: 20px; color: var(--text-secondary);">
                            <li>GAIKINDO（印尼）</li>
                            <li>TAI / FTI（泰国）</li>
                            <li>ANFAVEA / Fenabrave（巴西）</li>
                            <li>SIAM（印度）、AEB（俄罗斯）</li>
                        </ul>
                    </div>
                    <div>
                        <h4>媒体与研报</h4>
                        <ul style="list-style: disc; padding-left: 20px; color: var(--text-secondary);">
                            <li>盖世汽车、36氪、界面新闻</li>
                            <li>AlixPartners、麦肯锡</li>
                            <li>Maybank、爱建证券</li>
                        </ul>
                    </div>
                </div>
            </div>
        </section>"""

if 'id="sources"' not in html and "数据来源" not in html:
    if "</main>" in html:
        html = html.replace("</main>", sources_section + "\n    </main>", 1)
    else:
        html = html.rstrip() + sources_section + "\n    </main>"

# 确保基本结构完整
if "</main>" not in html:
    # 如果存在专家建议 section，把它放到 main 里面
    if expert_section:
        html = html.rstrip()
        html += expert_section
    html += "\n    </main>"
else:
    # 如果已经有 </main>，但专家建议还没插入，插入到 </main> 之前
    if expert_section and "section-expert" not in html:
        html = html.replace("</main>", expert_section + "\n    </main>", 1)

if "</body>" not in html:
    html += "\n</body>"
if "</html>" not in html:
    html += "\n</html>\n"

HTML_PATH.write_text(html, encoding="utf-8")
print(f"Fixed {HTML_PATH}")
print(f"Added {len(nav_items)} nav items")
for section_id, title, _, _, _ in nav_items:
    print(f"  - {section_id}: {title}")
if expert_section:
    print("Added section-expert: 专家建议")
