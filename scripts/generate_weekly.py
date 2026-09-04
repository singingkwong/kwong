#!/usr/bin/env python3
"""
调用扣子 Agent 生成汽车行业周报 Markdown。
渲染 HTML 请使用 scripts/render_weekly.py。
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


def fetch_weekly_markdown() -> str:
    """调用扣子 Bot 生成周报 Markdown。"""
    today = datetime.now().strftime("%Y年%m月%d日")
    prompt = (
        f"请生成一份{today}的全球汽车行业深度周报，输出为 Markdown 格式，不要输出 HTML。"
        "基于你搜索到的近7天最新行业数据、政策动态、车企动向和注塑机相关机会，"
        "严格按照以下固定模板组织内容，每个章节标题必须保留：\n\n"
        "```\n"
        "# 全球汽车行业深度周报\n"
        "**报告日期**：YYYY年MM月DD日\n"
        "**编制团队**：YZM海外汽车行业拓展项目组\n\n"
        "## 一、本周总览\n"
        "- 5条核心看点，每条用一句话总结，标注来源和日期。\n"
        "- 必须在开头列出 3 个本周热点，格式如下：\n"
        "  - **热点1**：标题（15-20字，抓人眼球）｜ 描述（30-40字）\n"
        "  - **热点2**：...\n"
        "  - **热点3**：...\n\n"
        "## 二、各地市场动态\n"
        "必须覆盖以下全部区域，每个区域单独一个三级标题，包含关键数据、趋势和注塑机会关联：\n"
        "- 2.1 中国市场\n"
        "- 2.2 东南亚市场\n"
        "- 2.3 南亚/印度市场\n"
        "- 2.4 南美市场\n"
        "- 2.5 北美市场\n"
        "- 2.6 欧洲市场\n"
        "- 2.7 俄罗斯/中东/非洲市场\n"
        "- 2.8 日韩/澳洲市场\n\n"
        "## 三、政策动态\n"
        "- 每条政策用三级标题，格式：3.x 地区/机构：政策名称\n"
        "- 内容说明政策要点及对注塑行业的影响。\n"
        "- 每条末尾标注来源和日期，格式：来源 (YYYY-MM-DD)\n\n"
        "## 四、车企动态\n"
        "- 每条车企动态用三级标题，格式：4.x 车企：事件标题\n"
        "- 用 bullet list 列出关键信息。\n"
        "- 每条末尾标注来源和日期。\n\n"
        "## 五、调研报告/机构观点\n"
        "- 每条报告用三级标题，格式：5.x 机构：报告标题\n"
        "- 内容总结核心观点。\n"
        "- 每条末尾标注来源和日期。\n\n"
        "## 六、注塑机会专题\n"
        "- 每条机会用三级标题，格式：6.x 【注塑机会】事件标题\n"
        "- 说明驱动因素、机会点、推荐设备/材料。\n\n"
        "## 七、下周关注\n"
        "- 用 bullet list 列出 6-8 条下周值得跟踪的事件或数据。\n\n"
        "## 八、数据来源\n"
        "- 列出本报告使用的主要数据来源机构名称，用逗号分隔。\n"
        "```\n\n"
        "格式要求：\n"
        "1. 只输出 Markdown，不要输出 HTML、不要输出代码块标记、不要输出任何说明文字；\n"
        "2. 数据必须标注来源和日期，格式：来源 (YYYY-MM-DD)；\n"
        "3. 每个区域/政策/车企/报告/机会必须独立成段，内容充实，不要一句话带过；\n"
        "4. 章节标题必须严格使用上面的编号和名称（一、二、三...），方便后续解析。"
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


def clean_markdown(content: str) -> str:
    """清理 Agent 返回的内容，只保留 Markdown 部分。"""
    content = content.strip()
    if content.startswith("```markdown"):
        content = content[len("```markdown"):]
        if content.endswith("```"):
            content = content[:-3]
    elif content.startswith("```"):
        content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
    return content.strip()


def save_markdown(content: str) -> Path:
    """保存 Markdown 文件。"""
    md_path = ROOT / "weekly.md"
    md_path.write_text(content, encoding="utf-8")
    print(f"Markdown 已保存: {md_path}")
    return md_path


def extract_title(content: str) -> str:
    """从 Markdown 中提取标题。"""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "全球汽车行业周报"


def main():
    print("开始调用 Agent 生成周报 Markdown...")
    content = fetch_weekly_markdown()
    content = clean_markdown(content)
    md_path = save_markdown(content)

    title = extract_title(content)
    print(f"title={title}")
    print(f"md_path={md_path}")


if __name__ == "__main__":
    main()
