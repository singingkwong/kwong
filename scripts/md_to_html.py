#!/usr/bin/env python3
"""
将 Agent 生成的 Markdown 周报转换为精美的 HTML 页面。
"""
import re
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent

HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg-primary:#0f172a;
  --bg-secondary:#1e293b;
  --bg-card:#1a2236;
  --accent-blue:#3b82f6;
  --accent-orange:#f97316;
  --text-primary:#f1f5f9;
  --text-secondary:#94a3b8;
  --text-muted:#64748b;
  --border-color:#334155;
  --radius:8px;
  --shadow:0 4px 24px rgba(0,0,0,.3);
}}
html{{scroll-behavior:smooth;scroll-padding-top:80px}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:var(--bg-primary);
  color:var(--text-primary);
  line-height:1.75;
  font-size:16px;
  -webkit-font-smoothing:antialiased;
}}
.top-nav{{
  position:sticky;top:0;z-index:1000;
  background:rgba(15,23,42,.92);
  backdrop-filter:blur(12px);
  border-bottom:1px solid var(--border-color);
  padding:0 24px;
}}
.nav-inner{{
  max-width:1280px;margin:0 auto;
  display:flex;align-items:center;gap:8px;
  height:56px;
  overflow-x:auto;
  scrollbar-width:none;
}}
.nav-inner::-webkit-scrollbar{{display:none}}
.nav-brand{{
  font-weight:700;font-size:14px;
  color:var(--accent-blue);
  white-space:nowrap;margin-right:16px;
  flex-shrink:0;
}}
.hero{{
  background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%);
  border-bottom:1px solid var(--border-color);
  padding:48px 24px 40px;
  text-align:center;
}}
.hero-inner{{max-width:900px;margin:0 auto}}
.hero-badge{{
  display:inline-block;
  font-size:12px;font-weight:600;
  color:var(--accent-blue);
  background:rgba(59,130,246,.12);
  border:1px solid rgba(59,130,246,.3);
  padding:4px 14px;border-radius:20px;
  margin-bottom:16px;letter-spacing:.5px;
}}
.hero h1{{
  font-size:clamp(24px,4vw,36px);
  font-weight:800;line-height:1.3;
  margin-bottom:12px;letter-spacing:-.5px;
}}
.hero-meta{{
  font-size:14px;color:var(--text-muted);
  display:flex;flex-wrap:wrap;justify-content:center;gap:16px;
}}
.hero-cover{{
  max-width:720px;width:100%;
  margin:24px auto 0;
  border-radius:var(--radius);
  border:1px solid var(--border-color);
  box-shadow:var(--shadow);
}}
.container{{max-width:1280px;margin:0 auto;padding:32px 24px}}
.markdown-body h2{{
  font-size:22px;font-weight:800;
  color:var(--text-primary);
  margin:40px 0 20px;
  padding-bottom:10px;
  border-bottom:2px solid var(--border-color);
}}
.markdown-body h3{{
  font-size:17px;font-weight:700;
  color:var(--text-primary);
  margin:28px 0 14px;
  padding-left:12px;
  border-left:3px solid var(--accent-blue);
}}
.markdown-body h4{{
  font-size:15px;font-weight:700;
  color:var(--text-primary);
  margin:20px 0 10px;
}}
.markdown-body p{{
  font-size:15px;color:var(--text-secondary);
  margin-bottom:14px;
}}
.markdown-body ul,.markdown-body ol{{
  margin:12px 0 16px 20px;
  color:var(--text-secondary);
}}
.markdown-body li{{
  font-size:15px;
  margin-bottom:8px;
  line-height:1.8;
}}
.markdown-body strong{{color:var(--text-primary)}}
.markdown-body a{{color:var(--accent-blue);text-decoration:none}}
.markdown-body a:hover{{text-decoration:underline}}
.markdown-body img{{
  max-width:100%;border-radius:var(--radius);
  border:1px solid var(--border-color);
  margin:16px 0;
}}
.markdown-body blockquote{{
  background:var(--bg-card);
  border-left:3px solid var(--accent-orange);
  padding:16px 20px;
  margin:16px 0;
  border-radius:0 var(--radius) var(--radius) 0;
  color:var(--text-secondary);
}}
.markdown-body hr{{
  border:none;border-top:1px solid var(--border-color);
  margin:32px 0;
}}
.markdown-body table{{
  width:100%;border-collapse:collapse;
  margin:16px 0;font-size:14px;
}}
.markdown-body th,.markdown-body td{{
  border:1px solid var(--border-color);
  padding:10px 12px;
  text-align:left;
}}
.markdown-body th{{
  background:var(--bg-secondary);
  color:var(--text-primary);
  font-weight:600;
}}
.markdown-body td{{color:var(--text-secondary)}}
.footer{{
  border-top:1px solid var(--border-color);
  padding:32px 24px;
  text-align:center;
  color:var(--text-muted);
  font-size:14px;
}}
.back-top{{
  position:fixed;bottom:24px;right:24px;
  width:44px;height:44px;border-radius:50%;
  background:var(--bg-secondary);
  border:1px solid var(--border-color);
  color:var(--text-primary);font-size:18px;
  cursor:pointer;opacity:0;visibility:hidden;
  transition:all .2s ease;z-index:999;
}}
.back-top.visible{{opacity:1;visibility:visible}}
</style>
</head>
<body>
<nav class="top-nav">
  <div class="nav-inner">
    <span class="nav-brand">全球汽车行业周报</span>
  </div>
</nav>

<header class="hero">
  <div class="hero-inner">
    <span class="hero-badge">WEEKLY REPORT</span>
    <h1>{title}</h1>
    <div class="hero-meta">
      <span>📅 {date}</span>
      <span>🚗 全球汽车市场动态</span>
    </div>
    <img src="cover.png" alt="封面图" class="hero-cover">
  </div>
</header>

<main class="container">
  <div class="markdown-body">
{content}
  </div>
</main>

<footer class="footer">
  <p>© {year} 全球汽车行业周报 | 本报告仅供内部参考</p>
</footer>

<button type="button" class="back-top" id="backTop" aria-label="返回顶部">↑</button>
<script>
const backTop=document.getElementById('backTop');
window.addEventListener('scroll',function(){{
  if(window.scrollY>400) backTop.classList.add('visible');
  else backTop.classList.remove('visible');
}});
backTop.addEventListener('click',function(){{
  window.scrollTo({{top:0,behavior:'smooth'}});
}});
</script>
</body>
</html>
"""


def extract_title(md_content: str) -> str:
    match = re.search(r"^#\s+(.+)$", md_content, re.MULTILINE)
    return match.group(1).strip() if match else "全球汽车行业周报"


def extract_description(md_content: str) -> str:
    """提取第一段非空文本作为 description。"""
    lines = [line.strip() for line in md_content.splitlines() if line.strip()]
    for line in lines:
        if not line.startswith("#") and not line.startswith("!"):
            return line[:120]
    return "全球汽车行业深度周报"


def convert(md_path: Path, output_path: Path = None) -> Path:
    md_content = md_path.read_text(encoding="utf-8")

    # Markdown 转 HTML
    html_content = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "toc", "nl2br"],
    )

    title = extract_title(md_content)
    description = extract_description(md_content)
    date_str = datetime.now().strftime("%Y年%m月%d日")
    year = datetime.now().year

    html = HTML_TEMPLATE.format(
        title=title,
        description=description,
        date=date_str,
        year=year,
        content=html_content,
    )

    if output_path is None:
        output_path = ROOT / "index.html"

    output_path.write_text(html, encoding="utf-8")
    print(f"HTML 已保存: {output_path}")
    return output_path


def main():
    import sys

    if len(sys.argv) > 1:
        md_path = Path(sys.argv[1])
    else:
        # 默认取最新的 weekly_YYYYMMDD.md
        md_files = sorted(ROOT.glob("weekly_*.md"))
        if not md_files:
            raise FileNotFoundError("未找到 weekly_*.md 文件")
        md_path = md_files[-1]

    print(f"转换文件: {md_path}")
    convert(md_path)


if __name__ == "__main__":
    main()
