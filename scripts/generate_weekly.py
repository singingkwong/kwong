#!/usr/bin/env python3
"""
调用扣子 Agent 直接生成汽车行业周报 HTML。
渲染为精美页面请使用 scripts/render_html.py。
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

COZE_API_TOKEN = os.environ["COZE_WORKLOAD_API_TOKEN"]
COZE_API_BASE = os.environ.get("COZE_API_BASE_URL", "https://api.coze.cn")
BOT_ID = os.environ.get("COZE_BOT_ID", "7663310609923981358")

HEADERS = {
    "Authorization": f"Bearer {COZE_API_TOKEN}",
    "Content-Type": "application/json",
}

ROOT = Path(__file__).resolve().parent.parent


def fetch_weekly_html() -> str:
    """调用扣子 Bot 直接生成周报 HTML。"""
    today = datetime.now().strftime("%Y年%m月%d日")
    prompt = (
        f"请生成一份{today}的全球汽车行业深度周报，并直接输出完整的 HTML 文件内容。"
        "基于你搜索到的近7天最新行业数据、政策动态、车企动向和注塑机相关机会，"
        "严格按照固定模板组织内容：本周总览、各地市场动态、政策动态、车企动态、调研报告/机构观点、"
        "注塑机会专题、下周关注。"
        "样式必须固定为以下深色行业报告风格，每次输出保持基本一致：\n"
        "1. 输出完整独立 HTML，包含 <html><head><body>；\n"
        "2. 深色主题：body 背景 #0f1115，卡片背景 #1a1d24，主文字 #e0e0e0，次要文字 #a0a0a0，强调色 #00d2ff；\n"
        "3. 各地市场动态必须覆盖以下全部区域，不得以表格形式遗漏：北美、欧洲、中国、东南亚、南美（巴西/墨西哥）、印度、俄罗斯、澳洲、日韩。每个区域用一段文字或一张卡片独立呈现，包含关键数据、趋势和注塑机会关联；\n"
        "4. 使用以下固定 class 名（不要自行发明新 class）：\n"
        "   - 卡片容器：card-grid\n"
        "   - 卡片：card，卡片标题：card-title，卡片内容：card-content\n"
        "   - 表格容器：table-container\n"
        "   - 列表：styled-list\n"
        "   - 标签：tag、tag-trend（利好）、tag-risk（风险）、tag-policy（政策）；\n"
        "5. section id 必须固定为：section-1（本周总览）、section-2（各地市场动态）、section-3（政策动态）、"
        "section-4（车企动态）、section-5（调研报告/机构观点）、section-6（注塑机会专题）、section-7（下周关注）；\n"
        "6. 在页面顶部报告日期下方显示：编制团队：YZM海外汽车行业拓展项目组；\n"
        "7. 在‘本周总览’区域顶部，必须显式输出 3 个‘本周热点’卡片，供企业微信图文消息使用：\n"
        "   - 容器：<div class='hotspot-grid'>，每个热点：<div class='hotspot-card'>；\n"
        "   - 热点标题：<div class='hotspot-title'>，15-20 字，必须抓人眼球、有新闻感；\n"
        "   - 热点描述：<div class='hotspot-desc'>，30-40 字，一句话说明影响或数据；\n"
        "   - 热点标签：<span class='hotspot-tag'>，如‘政策’‘数据’‘车企’‘注塑机会’；\n"
        "   - 这 3 个热点必须从本周事件中挑选最有热度、最引人瞩目的（如重大突破、销量新高、政策变化、头部车企动作、注塑机会），不要放平淡的常规数据；\n"
        "   - 如果热点有对应的外部原文链接，必须在热点卡片内用固定格式输出：<a href='原文URL' class='hotspot-source' target='_blank'>原文</a>；\n"
        "8. 在 <head> 中使用嵌入式 CSS，不要引用外部 CSS 文件；\n"
        "9. 确保所有 HTML 标签正确闭合，不要出现属性错位或未闭合标签；\n"
        "10. 不要在 HTML 外面添加任何说明文字，只输出 HTML 代码本身。"
    )

    resp = requests.post(
        f"{COZE_API_BASE}/v3/chat",
        headers=HEADERS,
        json={
            "bot_id": BOT_ID,
            "user_id": "weekly_automation",
            "stream": False,
            "additional_messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "content_type": "text",
                }
            ],
            "auto_save_history": True,
        },
        timeout=60,
    )
    resp.raise_for_status()
    chat_result = resp.json()
    print("chat created:", json.dumps(chat_result, ensure_ascii=False, indent=2))

    if chat_result.get("code") != 0:
        raise RuntimeError(f"创建对话失败: {chat_result}")

    conversation_id = chat_result["data"]["conversation_id"]
    chat_id = chat_result["data"]["id"]

    for _ in range(120):
        time.sleep(2)
        retrieve_resp = requests.get(
            f"{COZE_API_BASE}/v3/chat/retrieve",
            headers=HEADERS,
            params={"conversation_id": conversation_id, "chat_id": chat_id},
            timeout=30,
        )
        retrieve_resp.raise_for_status()
        retrieve_result = retrieve_resp.json()
        status = retrieve_result["data"]["status"]
        last_error = retrieve_result["data"].get("last_error", {})
        print(f"chat status: {status}, last_error: {last_error}")
        if status in ("completed", "failed", "canceled"):
            break
    else:
        raise RuntimeError("等待对话完成超时")

    if status != "completed":
        raise RuntimeError(f"对话未成功完成: {status}, last_error: {last_error}")

    msg_resp = requests.get(
        f"{COZE_API_BASE}/v3/chat/message/list",
        headers=HEADERS,
        params={"conversation_id": conversation_id, "chat_id": chat_id},
        timeout=30,
    )
    msg_resp.raise_for_status()
    msg_result = msg_resp.json()

    for msg in msg_result.get("data", []):
        if msg.get("role") == "assistant" and msg.get("type") == "answer":
            return msg.get("content", "")

    raise RuntimeError("未找到有效的回答内容")


def clean_html(content: str) -> str:
    """清理 Agent 返回的内容，只保留 HTML 部分。"""
    content = content.strip()
    if content.startswith("```html"):
        content = content[len("```html"):]
        if content.endswith("```"):
            content = content[:-3]
    elif content.startswith("```"):
        content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
    return content.strip()


def save_html(content: str) -> Path:
    """保存 Agent 原始 HTML 文件。"""
    html_path = ROOT / "agent.html"
    html_path.write_text(content, encoding="utf-8")
    print(f"Agent HTML 已保存: {html_path}")
    return html_path


def main():
    print("开始调用 Agent 生成周报 HTML...")
    content = fetch_weekly_html()
    content = clean_html(content)
    html_path = save_html(content)

    title_match = re.search(r"<title>(.*?)</title>", content, re.DOTALL)
    title = title_match.group(1).strip() if title_match else "全球汽车行业周报"
    print(f"title={title}")
    print(f"html_path={html_path}")


if __name__ == "__main__":
    main()
