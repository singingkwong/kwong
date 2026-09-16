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


def fetch_weekly_html(attempt: int = 1) -> str:
    """调用扣子 Bot 直接生成周报 HTML。attempt 为第几次尝试（用于提示重试）。"""
    today = datetime.now().strftime("%Y年%m月%d日")
    prompt = (
        f"请生成一份{today}的全球汽车行业深度周报，并直接输出完整的 HTML 文件内容。"
        "基于你搜索到的近7天最新行业数据、政策动态、车企动向和注塑机相关机会，"
        "严格按照固定模板组织内容：本周总览、各地市场动态、政策动态、车企动态、调研报告/机构观点、"
        "注塑机会专题、下周关注。"
        "样式必须固定为以下深色行业报告风格，每次输出保持基本一致：\n"
        "1. 输出完整独立 HTML，包含 <html><head><body>；\n"
        "2. 深色主题：body 背景 #0f1115，卡片背景 #1a1d24，主文字 #e0e0e0，次要文字 #a0a0a0，强调色 #00d2ff；\n"
        "3. 各地市场动态：**只保留固定 6 个区域，顺序必须严格为：中国、北美、欧洲、东南亚、印度、其他**。先把本周收集到的所有汽车行业相关新闻/事件/数据/政策，全部归入这 6 个区域之一；分类规则：【中国=中国内地；北美=美国+加拿大+墨西哥；欧洲=欧盟+英国+德法等欧洲国家；东南亚=东盟国家（印尼/泰国/马来西亚/越南等）；印度=印度；其他=除上述明确区域外的所有其他地区（如南美/巴西/阿根廷、俄罗斯、澳洲、日韩、中东等）都归入“其他”】，南美/日韩等**全部并入“其他”区域，不得单独成区、不得就近并入中国或北美或欧洲**。每个区域必须独立输出并且**每个区域至少 4 条**（news 总条数不设上限，各区域条数可不同，但每个展示的区域都不得少于 4 条，且 6 个区域一个都不能少：“其他”区域若真实事件不足，可说明本周无重大新增、仍应输出该区域占位卡）。输出规范：【一个区域只输出一张卡片（card-title 只写区域名，且只能是“中国”“北美”“欧洲”“东南亚”“印度”“其他”之一），卡内用至少 4 个 <li> 列表项列出该区域至少 4 条独立的一周市场事件/数据/政策，每条必须是一个完整的 <li>，且内部用“关键数据/事件：…影响分析：…趋势判断：…”三要点逐条解读（关键数据/事件给出具体数据/数字/时间/政策名；影响分析说明对汽车行业供应链/注塑机及材料/零部件的影响；趋势判断给出短期趋势或后续关注点），每条都带一个 <a class='source-link'> 原文链接并以“来源：机构名”结尾（三要点与来源写在同一个 <li> 内，严禁把一条事件的三个要拆成三个 <li>）】。严禁把一条事件的三要点拆成多个条目，严禁跳过或新增任何区域（最终只能有这 6 张区域卡，每张卡内至少 4 条且无上限），若某区域一周真实事件不足 4 条，可结合近两周数据或合理趋势预判补足到至少 4 条，但不得编造不存在的事件；“其他”区域可略少于 4 条。\n"
        "4. 使用以下固定 class 名（不要自行发明新 class）：\n"
        "   - 卡片容器：card-grid\n"
        "   - 卡片：card，卡片标题：card-title，卡片内容：card-content\n"
        "   - 表格容器：table-container\n"
        "   - 列表：styled-list\n"
        "   - 标签：tag、tag-trend（利好）、tag-risk（风险）、tag-policy（政策）；\n"
        "5. section id 必须固定为：section-1（本周总览）、section-2（各地市场动态）、section-3（政策动态）、"
        "section-4（车企动态）、section-5（调研报告/机构观点）、section-6（注塑机会专题）、section-7（下周关注）；\n"
        "   section-7 下周关注必须输出，包含 3-5 条下周值得重点关注的事件或数据发布，每条用列表项呈现；\n"
        "6. 在页面顶部报告日期下方显示：编制团队：YZM海外汽车行业拓展项目组；\n"
        "7. 在‘本周总览’区域顶部，必须显式输出 3 个‘本周热点’卡片，供企业微信图文消息使用：\n"
        "   - 容器：<div class='hotspot-grid'>，每个热点：<div class='hotspot-card'>；\n"
        "   - 热点标题：<div class='hotspot-title'>，15-20 字，必须抓人眼球、有新闻感；\n"
        "   - 热点描述：<div class='hotspot-desc'>，30-40 字，一句话说明影响或数据；\n"
        "   - 热点标签：<span class='hotspot-tag'>，如‘政策’‘数据’‘车企’‘注塑机会’；\n"
        "   - 这 3 个热点必须从本周事件中挑选最有热度、最引人瞩目的（如重大突破、销量新高、政策变化、头部车企动作、注塑机会），不要放平淡的常规数据；\n"
        "   - 如果热点有对应的外部原文链接，必须在热点卡片内用固定格式输出：<a href='原文URL' class='hotspot-source' target='_blank'>原文</a>；\n"
        "7.5 【重要】所有新闻/动态类内容都必须附真实可用的直达原文链接：\n"
        "   - 适用范围：本周总览各热点、各地市场动态、政策动态、车企动态、调研报告/机构观点、注塑机会专题，凡涉及具体事件/数据/新闻的条目，每条都必须给出可跳转的原文链接；\n"
        "   - 输出格式：在该条目内部用 <a href='原文URL' class='source-link' target='_blank'>原文</a> 固定格式输出；\n"
        "   - 【链接必须是真实的】只允许输出你联网实际访问过、确认能正常打开且内容与标题匹配的网址（如信息来源站点点开后的真实文章页）。\n"
        "   - 【严禁编造】绝对禁止按标题和域名猜测、拼凑、套模板生成 URL（如随意拼出 detail-xxx.shtml 这类规律地址），一经发现视为错误；\n"
        "   - 每条都必须给出可跳转的真实原文链接，不得删除或留空：若无法拿到某条精确的文章页 URL，必须给出该信息来源的可靠入口页（如该媒体的官网统计页/栏目页、该机构权威数据页），并用 <a href='URL' class='source-link' target='_blank'>原文</a> 格式输出，绝不允许因为拿不到精确页就整条不附链接；\n"
        "7.6 【重要】除'本周总览'外的其余模块（各地市场动态、政策动态、车企动态、调研报告/机构观点、注塑机会专题），每条新闻/动态的卡片正文必须写成'三要点'结构，让读者不点开原文也能拿到核心价值：\n"
        "   - 每条正文严格按以下三段顺序输出，用换行分隔，每段以固定标签开头；\n"
        "   - '关键数据/事件：' 后跟该动态最核心的数据或事件（数字用具体值，如销量/增幅/金额/时间等）；\n"
        "   - '影响分析：' 后跟该事件对汽车行业、供应链、注塑机及材料需求的具体影响，做到有指向、可执行；\n"
        "   - '趋势判断：' 后跟基于此事件的短期趋势判断或后续关注点；\n"
        "   - 每段 1-2 句话，三要点整体务必充实、专业，避免空话套话；\n"
        "   - 每条正文末尾须标注真实的数据来源，格式：'来源：媒体/机构名'（如 来源：MarkLines、来源：中汽协），来源必须与真实出处一致，不得编造机构名；\n"
        "   - 示例格式（三段各占一行）：\n"
        "     关键数据/事件：8月中国新能源销量165.3万辆，同比+18.9%，渗透率42.1%。\n"
        "     影响分析：渗透率突破四成将带动内饰轻量化与微发泡注塑需求，本土塑机订单同比增长35%。\n"
        "     趋势判断：预计Q4采购窗口收窄，大型两板机与多组分机将是增量主线。\n"
        "8. 在 <head> 中使用嵌入式 CSS，不要引用外部 CSS 文件；\n"
        "9. 确保所有 HTML 标签正确闭合，不要出现属性错位或未闭合标签；\n"
        "10. 不要在 HTML 外面添加任何说明文字，只输出 HTML 代码本身。\n"
        "11. 【输出前必做硬性自检，必须逐条满足，缺失任何一条都属于失败输出】：\n"
        "    (a) '<div class=\"card-title\">中国</div>'、'<div class=\"card-title\">北美</div>'、'<div class=\"card-title\">欧洲</div>'、'<div class=\"card-title\">东南亚</div>'、'<div class=\"card-title\">印度</div>'、'<div class=\"card-title\">其他</div>' 六张区域卡必须**全部**出现在'各地市场动态'模块中，一张都不能省、不能合并、不能改名；\n"
        "    (b) 中国／北美／欧洲／东南亚／印度 这 5 张卡，**每张卡内的 card-content 都必须包含至少 4 个 <li> 列表项**（每个 <li> 是一条独立市场动态，各含'关键数据/事件：…／影响分析：…／趋势判断：…'三要点 + '来源：机构名' + 一个 <a class='source-link'> 原文链接，且三者与来源必须在同一个 <li> 内）；'其他'区域卡可包含 1-4 条或说明本周无重大新增；\n"
        "    (c) 全篇至少要有 4+4+4+4+4=20 条带 source-link 链接的独立动态分散在上述 5 张区域卡内（允许更多，但不能少于 20）；\n"
        "    (d) 输出完成后逐条核对 (a)(b)(c)，若任一不满足，必须即时补充对应区域卡或列表项，直到 6 张卡、每卡 ≥4 条、共 ≥20 条全部达标再结束生成。每一条事件的三要点（关键数据/事件、影响分析、趋势判断）与来源必须放在同一个 <li> 列表项内，严禁拆成多个 <li>。"
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


MAX_ATTEMPTS = int(os.environ.get("AGENT_MAX_ATTEMPTS", "3"))

def main():
    print("开始调用 Agent 生成周报 HTML...")
    from agent_checks import print_report, validate
    import agent_checks

    content = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            print(f"\n▶ 第 {attempt} 次尝试生成（上一版未通过检查）...")
        raw = fetch_weekly_html(attempt=attempt)
        content = clean_html(raw)
        html_path = save_html(content)

        # —— Agent 输出检查清单 ——
        try:
            checks = validate(content)
            report = print_report(checks)
            print("\n" + report)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 校验执行出错（不影响保存）：{exc}")
            break

        summary = agent_checks.summarize(checks)
        if summary["ok"]:
            print("\n✅ Agent 输出通过全部检查，予以采纳。")
            break
        if attempt < MAX_ATTEMPTS:
            print(f"\n❌ 检查未通过（{len(summary['failed'])} 项）：将重试...")
        else:
            print(f"\n❌ 已达最大重试次数（{MAX_ATTEMPTS}），保留当前输出。")

    title_match = re.search(r"<title>(.*?)</title>", content, re.DOTALL)
    title = title_match.group(1).strip() if title_match else "全球汽车行业周报"
    print(f"title={title}")
    print(f"html_path={html_path}")


if __name__ == "__main__":
    main()
