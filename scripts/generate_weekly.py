#!/usr/bin/env python3
"""
调用扣子 Agent 生成汽车行业周报 Markdown。
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
        f"请生成一份{today}的全球汽车行业深度周报。"
        "基于你搜索到的近7天最新行业数据、政策动态、车企动向和注塑机相关机会，"
        "按照固定模板输出：本周总览、各地市场动态、政策动态、车企动态、调研报告/机构观点、"
        "注塑机会专题、下周关注。输出为 Markdown 格式。"
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
            "auto_save_history": False,
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

    # 轮询等待完成
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
        print(f"chat status: {status}")
        if status in ("completed", "failed", "canceled"):
            break
    else:
        raise RuntimeError("等待对话完成超时")

    if status != "completed":
        raise RuntimeError(f"对话未成功完成: {status}")

    # 获取消息列表
    msg_resp = requests.get(
        f"{COZE_API_BASE}/v3/chat/message/list",
        headers=HEADERS,
        params={"conversation_id": conversation_id, "chat_id": chat_id},
        timeout=30,
    )
    msg_resp.raise_for_status()
    msg_result = msg_resp.json()

    # 提取 assistant 的 answer 文本
    for msg in msg_result.get("data", []):
        if msg.get("role") == "assistant" and msg.get("type") == "answer":
            return msg.get("content", "")

    raise RuntimeError("未找到有效的回答内容")


def save_markdown(content: str) -> Path:
    """保存 Markdown 文件。"""
    date_str = datetime.now().strftime("%Y%m%d")
    md_path = ROOT / f"weekly_{date_str}.md"
    md_path.write_text(content, encoding="utf-8")
    print(f"Markdown 已保存: {md_path}")
    return md_path


def extract_title(content: str) -> str:
    """从 Markdown 中提取标题。"""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else "全球汽车行业周报"


def main():
    print("开始调用 Agent 生成周报...")
    content = fetch_weekly_markdown()
    md_path = save_markdown(content)

    # 同时输出摘要信息供后续步骤使用
    title = extract_title(content)
    print(f"title={title}")
    print(f"md_path={md_path}")


if __name__ == "__main__":
    main()
