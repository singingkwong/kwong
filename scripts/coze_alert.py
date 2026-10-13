#!/usr/bin/env python3
"""向 Coze Bot 发送告警消息（用于 token 过期 / 鉴权失败等场景）。

优先使用独立的告警 Bot（COZE_ALERT_BOT_ID / COZE_ALERT_API_TOKEN），
未配置时回退到主 Bot（COZE_BOT_ID / COZE_WORKLOAD_API_TOKEN）。
告警发送失败不会阻塞主流程（整体退出码由 run_pipeline 决定）。

用法：
  python3 scripts/coze_alert.py "告警内容"     # 显式指定告警内容
  # 或读环境变量 COZE_ALERT_MESSAGE；两者都缺省时使用默认文案
"""
import os
import sys
import time

import requests

API_BASE = os.environ.get("COZE_API_BASE_URL", "https://api.coze.cn")
BOT_ID = os.environ.get("COZE_ALERT_BOT_ID") or os.environ.get("COZE_BOT_ID")
TOKEN = os.environ.get("COZE_ALERT_API_TOKEN") or os.environ.get("COZE_WORKLOAD_API_TOKEN")

DEFAULT_MESSAGE = (
    "【汽车周报自动告警】\n"
    "Coze 鉴权失败（token 过期/无效/无权限），本次周报已中止，未推送。\n"
    "请到 GitHub 仓库 Settings → Secrets and variables → Actions 更新 "
    "COZE_WORKLOAD_API_TOKEN（若告警 Bot 独立，也请检查 COZE_ALERT_API_TOKEN），"
    "修复后手动触发 workflow：Actions → 生成汽车行业周报并推送 → Run workflow。"
)

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _create_chat(message: str) -> dict:
    body = {
        "bot_id": BOT_ID,
        "user_id": "weekly_alert",
        "stream": False,
        "additional_messages": [
            {"role": "user", "content": message, "content_type": "text"}
        ],
        "auto_save_history": True,
    }
    resp = requests.post(f"{API_BASE}/v3/chat", headers=HEADERS, json=body, timeout=60)
    resp.raise_for_status()
    doc = resp.json()
    if doc.get("code") != 0:
        raise RuntimeError(f"创建告警对话失败: {doc}")
    return doc["data"]


def _wait(data: dict) -> tuple[str, str]:
    conversation_id = data["conversation_id"]
    chat_id = data["id"]
    status = "in_progress"
    for _ in range(120):
        rr = requests.get(
            f"{API_BASE}/v3/chat/retrieve",
            headers=HEADERS,
            params={"conversation_id": conversation_id, "chat_id": chat_id},
            timeout=30,
        )
        rr.raise_for_status()
        status = rr.json()["data"]["status"]
        if status in ("completed", "failed", "canceled"):
            break
        time.sleep(2)
    msgs = requests.get(
        f"{API_BASE}/v3/chat/message/list",
        headers=HEADERS,
        params={"conversation_id": conversation_id, "chat_id": chat_id},
        timeout=30,
    ).json()
    reply = ""
    for m in msgs.get("data", []):
        if m.get("role") == "assistant" and m.get("type") == "answer":
            reply = m.get("content", "") or ""
            break
    return status, reply


def main() -> int:
    if not BOT_ID or not TOKEN:
        print(
            "[alert] 未配置告警 Bot（COZE_ALERT_BOT_ID / COZE_ALERT_API_TOKEN），跳过 Coze 告警发送",
            flush=True,
        )
        return 0
    message = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("COZE_ALERT_MESSAGE", DEFAULT_MESSAGE)
    )
    print(f"[alert] 发送 Coze 告警 → bot_id={BOT_ID}", flush=True)
    try:
        data = _create_chat(message)
        status, reply = _wait(data)
        print(f"[alert] 告警对话状态: {status}", flush=True)
        if reply.strip():
            print(f"[alert] 告警 Bot 回复(前120字): {reply[:120]}", flush=True)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[alert][warn] Coze 告警发送失败: {e}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())