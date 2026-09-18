#!/usr/bin/env python3
"""通过 API 调用扣子 Bot 生成周报 Markdown，写入 ROOT/weekly_YYYYMMDD.md。

重建原因（2026-09-16）：
    旧版误用了 generate_weekly.py 专门为「输出 HTML」设计的 fetch_weekly_html()，
    其 prompt 主体全部是 HTML 渲染/卡片/配图要求，与「输出纯 Markdown」目标矛盾，
    导致 Bot 行为错乱、首轮返回 0 字，脚本却无失败判定仍写入空 md / 渲染空 HTML。
    本次改为独立调用 /v3/chat 的纯 Markdown prompt，并加入硬性失败守卫：
    - 首轮 0 字 → 直接判失败抛出，绝不落盘；
    - 板块/区域明显缺失且三次续写仍补不全 → 判失败抛出；
    - 只有拿到合格正文才写入 weekly_YYYYMMDD.md。

输出：ROOT/weekly_YYYYMMDD.md（Agent 原始 Markdown 文本）。
"""
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

import generate_weekly as g

COZE_API_TOKEN = g.COZE_API_TOKEN
COZE_API_BASE = g.COZE_API_BASE
HEADERS = g.HEADERS
BOT_ID = os.environ.get("COZE_BOT_ID", "7685975869638459392")
import requests as REQUESTS

SECTIONS = ["本周总览", "各地市场动态", "政策", "车企", "调研", "注塑", "下周关注"]
REGS = ["中国", "北美", "欧洲", "东南亚", "印度", "其他"]

_NOW = datetime.now()
_TODAY = _NOW.strftime('%Y年%m月%d日')
# 下周关注的时间窗（明天起 7 天内），用于约束 Bot 不得使用往年同期事件
_NEXT_START = (_NOW + timedelta(days=1)).strftime('%Y年%m月%d日')
_NEXT_END = (_NOW + timedelta(days=7)).strftime('%Y年%m月%d日')
_YEAR = _NOW.strftime('%Y')

MAIN_PROMPT = f"""请直接一次输出完整的《全球汽车行业深度周报（{_TODAY}）》Markdown 文本。

【务必严格遵守】
- 只输出 Markdown 正文本身，禁止输出 HTML 代码，禁止输出任何前后说明文字、禁止用代码块包裹。
- 内容基于你联网检索到的近 7 天真实行业数据（政策、车企动态、各地销量/渗透率、行业报告、注塑机与汽车注塑件相关机会），每条信息标注真实出处。
- 当前真实日期是 {_TODAY}（{_YEAR} 年）。全文所有日期、数据、事件必须与 {_YEAR} 年一致；严禁把往年（如 {int(_YEAR)-1} 年或更早）的同期事件、历史数据当作本周新闻或下周关注。

一、板块齐全，用 Markdown 二级标题（##）依次输出，一个都不能少：
1. 本周总览（2-3 段概述 + 3 个本周核心热点，每条给原文链接）
2. 各地市场动态（见下方"二、区域要求"）
3. 政策与法规动态（至少 2 条）
4. 主要车企动态（至少 2 条）
5. 调研报告/机构观点（至少 2 条）
6. 注塑机会专题（至少 3 个方向，每个用 **标题**：列出机会点、对应设备/材料、涉及客户）
7. 下周关注（3-5 条，纯列表项；**只能是 {_NEXT_START} 至 {_NEXT_END} 这 7 天内即将发生的真实事件**，日期一律用 {_YEAR} 年表述；若检索到的是往年同期日程，必须确认该事件在 {_YEAR} 年同一时间点确实仍会发生，否则不要列出）

二、各地市场动态区域要求（用 Markdown 三级标题 ###）：
- 依次输出固定 6 个区域：### 中国市场、### 北美市场、### 欧洲市场、### 东南亚市场、### 印度市场、### 其他市场（南美/日韩/俄罗斯等并入"其他"）。
- 中国/北美/欧洲/东南亚/印度每区**至少 3 条**新闻；"其他"可 1-3 条。6 区一个都不能少，也不得合并/改名/新增其他区域。
- 每条新闻用数字序号开头（如 `1.`），格式固定（三要点 + 来源 + 链接，必须在一起）：
    1. 事件一句话标题
       - 量化要点：关键事件与具体数据
       - 产业链影响：对汽车行业/供应链/注塑机及注塑件需求的影响
       - 趋势判断：短期趋势或后续关注点
       【原文链接】：真实可访问 URL
       来源：机构名

三、除总览外的所有板块（政策/车企/调研/注塑/各区域）每条都要带【原文链接】+ 来源。链接必须是真实可访问、与内容匹配的文章页；严禁按标题拼凑 URL。若拿不到精确文章页，给该机构权威数据页/官网栏目页作为兜底，不得整条不附链接。

四、政策/车企/调研板块每条也用数字序号+三要点格式（不一定要"量化要点/产业链影响/趋势判断"逐字，但需包含数据要点、影响、出处）。

请现在直接开始输出正文。"""

# 续写指令模板（被截断时按缺项补齐）
CONT_TMPL = """继续刚才那份周报尚未写到的部分，与被截断前文连成完整一份。当前仍缺：{hints}。用与前文完全一致的 Markdown 格式（含量化要点/产业链影响/趋势判断/【原文链接】+ 来源），只输出新增的 Markdown 正文，不要重复前文，不要任何说明文字。可直接基于已掌握信息输出。"""


# ---------- 独立 API 封装（不复用 generate_weekly 的 HTML fetch） ----------
_LAST_CONVERSATION_ID = None


def _create_chat(user_prompt: str, conversation_id=None) -> dict:
    global _LAST_CONVERSATION_ID
    body = {
        "bot_id": BOT_ID,
        "user_id": "weekly_automation",
        "stream": False,
        "additional_messages": [
            {"role": "user", "content": user_prompt, "content_type": "text"}
        ],
        "auto_save_history": True,
    }
    if conversation_id:
        body["conversation_id"] = conversation_id
    resp = REQUESTS.post(
        f"{COZE_API_BASE}/v3/chat",
        headers=HEADERS,
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    doc = resp.json()
    if doc.get("code") != 0:
        raise RuntimeError(f"创建对话失败: {doc}")
    data = doc["data"]
    _LAST_CONVERSATION_ID = data["conversation_id"]
    return data


def _wait_and_fetch(data: dict, need_raise_on_incomplete: bool = True) -> str:
    conversation_id = data["conversation_id"]
    chat_id = data["id"]
    status = "in_progress"
    deadline = time.time() + 600
    for _ in range(300):
        if time.time() > deadline:
            break
        try:
            rr = REQUESTS.get(
                f"{COZE_API_BASE}/v3/chat/retrieve",
                headers=HEADERS,
                params={"conversation_id": conversation_id, "chat_id": chat_id},
                timeout=30,
            )
            rr.raise_for_status()
            rj = rr.json()
            status = rj["data"]["status"]
        except Exception as e:
            print(f"[warn] retrieve 轮询异常: {e}", flush=True)
            time.sleep(3)
            continue
        if status in ("completed", "failed", "canceled"):
            break
        time.sleep(2)
    print(f"chat 状态: {status}", flush=True)

    msgs = REQUESTS.get(
        f"{COZE_API_BASE}/v3/chat/message/list",
        headers=HEADERS,
        params={"conversation_id": conversation_id, "chat_id": chat_id},
        timeout=30,
    ).json()
    partial = ""
    for m in msgs.get("data", []):
        if m.get("role") == "assistant" and m.get("type") == "answer":
            partial = m.get("content", "") or ""
            break
    print(f"[info] 对话返回正文 {len(partial)} 字", flush=True)
    if status != "completed":
        msg = f"对话状态 {status}（可能达到单轮 5 次工具调用上限 6150），当前返回正文 {len(partial)} 字"
        if need_raise_on_incomplete:
            raise RuntimeError(msg)
        print(f"[warn] {msg}，交由调用方判断是否续写", flush=True)
    return partial


def fetch_markdown(need_raise_on_incomplete: bool = False) -> str:
    # failed/在途中止（如单轮工具调用上限 6150）不应让流水线硬失败，
    # 返回当前 partial 正文交给 main() 的续写/重试兜底。
    data = _create_chat(MAIN_PROMPT)
    return _wait_and_fetch(data, need_raise_on_incomplete=need_raise_on_incomplete)


def fetch_markdown_continued(instruction: str) -> str:
    if not _LAST_CONVERSATION_ID:
        raise RuntimeError("无可用会话上下文，请先调用首轮")
    data = _create_chat(instruction, conversation_id=_LAST_CONVERSATION_ID)
    return _wait_and_fetch(data, need_raise_on_incomplete=True)


def parts_full(parts):
    return "\n".join(x for x in parts if x)


def _headlines(full: str) -> str:
    """提取全文的标题行（#/##/###…），用于板块完整度判断。"""
    out = []
    for line in full.splitlines():
        if re.match(r"^\s*#{1,3}\s+", line):
            out.append(re.sub(r"^\s*#{1,3}\s+", "", line).strip(" #.*-="))
    return "\n".join(out)


def still_missing(full: str) -> str:
    hints = []
    heads = _headlines(full)
    miss_regs = [r for r in REGS if f"{r}市场" not in heads]
    if miss_regs:
        hints.append("分区域市场动态尤其要补齐：" + "、".join(miss_regs))
    miss_secs = [s for s in SECTIONS if s not in heads]
    if miss_secs:
        hints.append("补齐板块：" + "、".join(miss_secs))
    return "；".join(hints)


def main():
    parts: list[str] = []

    print("MAIN_PROMPT len:", len(MAIN_PROMPT), flush=True)
    p1 = ""
    for attempt in range(1, 4):
        p1 = fetch_markdown()
        print(f"首轮(尝试{attempt}) len:", len(p1), flush=True)
        if p1.strip():
            break
        # 首轮 failed 且 0 字：重新开一场（不带 conversation_id 即新对话）再试
        print(f"首轮为空（对话可能 failed），重试新对话 (attempt={attempt})", flush=True)
    parts.append(p1)
    if not p1.strip():
        print("[warn] 重试 3 次后首轮仍为空，转续写兜底", flush=True)

    for r in range(1, 4):
        full = parts_full(parts)
        missing = still_missing(full)
        if not missing or not full.strip():
            break
        print(f"---- 续写轮 {r}: {missing} ----", flush=True)
        try:
            nxt = fetch_markdown_continued(CONT_TMPL.format(hints=missing))
        except Exception as e2:
            print("续写异常:", e2, flush=True)
            time.sleep(4)
            continue
        if not nxt.strip():
            break
        parts.append(nxt)
        print("续写部分 len:", len(nxt), flush=True)

    full = parts_full(parts)
    if not full.strip():
        raise RuntimeError(
            "周报生成失败：最终正文为 0 字（首轮与续写均未产出有效内容），"
            "不写入 weekly_*.md，流水线中止。"
        )
    still = still_missing(full)
    if still:
        raise RuntimeError(
            f"周报生成不合格：仍缺失【{still}】。"
            f"（当前正文 {len(full)} 字）为保质量不落盘，流水线中止，请检查 Bot 与网络。"
        )

    # 兜底校验：扫描"下周关注"及全文中的往年日期，发现则告警（不阻断，便于 Actions 日志排查）
    stale = sorted(set(re.findall(r"(19\d{2}|20[0-2]\d)\s*年", full)))
    stale = [y for y in stale if int(y) < _NOW.year]
    if stale:
        print(f"[warn] 正文出现往年日期 {stale}，疑似 Bot 引用了往年同期事件，请人工复核", flush=True)

    date = datetime.now().strftime("%Y%m%d")
    out = ROOT / f"weekly_{date}.md"
    out.write_text(full, encoding="utf-8")
    print("DONE parts:", len(parts), "total_len:", len(full))
    print("已保存:", out)
    return out


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[FATAL] {exc}", flush=True)
        sys.exit(1)