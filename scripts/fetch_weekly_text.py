#!/usr/bin/env python3
"""通过 API 调用扣子 Bot 生成周报 Markdown，写入 ROOT/weekly_YYYYMMDD.md。

流程：单次主调用要求 Bot 直接输出完整 Markdown；若被单轮 5 次工具上限(6150)截断且板块不齐，
做少量续写兜底补齐。最终把完整 md 落盘，供 run_pipeline 提交 git / 渲染 HTML。
输出：ROOT/weekly_YYYYMMDD.md（Agent 原始 Markdown 文本）。
"""
import os, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_weekly as g

g.BOT_ID = os.environ.get("COZE_BOT_ID", "7685975869638459392")
ROOT = g.ROOT

SECTIONS = ["本周总览", "各地市场动态", "政策动态", "车企动态", "调研报告", "注塑机会", "下周关注"]
REGS = ["中国", "北美", "欧洲", "东南亚", "印度", "其他"]

MAIN_PROMPT = f"""请直接一次输出完整的《全球汽车行业深度周报（{datetime.now().strftime('%Y年%m月%d日')}）》 Markdown 文本（不是 HTML），不要中途停顿，尽量一次给全。

要求（务必严格覆盖，一次输出到位）：
1. 板块齐全：一、本周总览；二、分区域市场动态；三、政策与法规；四、主要车企动态；五、注塑机会专题；六、下周关注。
2. 分区域市场动态用子标题列出：中国市场/北美市场/欧洲市场/东南亚市场/印度市场/其他市场，每区至少 3 条真实新闻（核对日期与真实数据，给出真实出处链接）。
3. 每条新闻格式固定：
   - 量化要点：关键事件与数据
   - 产业链影响：影响分析
   - 趋势判断：后市判断
   【原文链接】：真实可访问 URL
   来源：机构名
4. 政策/车企/注塑/下周等板块每条也标注来源与原文链接。

请直接输出 Markdown 正文本身，不要输出任何前后说明文字。"""

CONT_TMPL = """继续输出刚才那份周报尚未写到的部分，与被截断前文连成完整一份。当前仍缺：{hints}。用与前文一致格式（每条含 量化要点/产业链影响/趋势判断/【原文链接】+来源）只输出新增 Markdown，不要重复前文，不要说明文字。可直接基于已掌握信息输出。"""


def parts_full(parts):
    return "\n".join(x for x in parts if x)


def still_missing(full):
    hints = []
    miss_regs = [r for r in REGS if f"{r}市场" not in full]
    if miss_regs:
        hints.append("分区域市场动态尤其要补齐：" + "、".join(miss_regs))
    miss_secs = [s for s in SECTIONS if s not in full]
    if miss_secs:
        hints.append("补齐板块：" + "、".join(miss_secs))
    return "；".join(hints)


def main():
    parts = []
    try:
        p1 = g.fetch_weekly_html(extra_instruction="直接输出完整 Markdown 周报，7板块6区域一次给全")
        parts.append(p1)
        print("首轮 len:", len(p1), flush=True)
    except Exception as e:
        print("首轮异常:", e, flush=True)

    # 有限续写兜底：补齐到板块齐全即可，最多 8 轮
    for r in range(1, 9):
        full = parts_full(parts)
        missing = still_missing(full)
        if not missing or not full.strip():
            break
        print(f"---- 续写轮 {r}: {missing} ----", flush=True)
        try:
            nxt = g.fetch_weekly_continued(CONT_TMPL.format(hints=missing))
        except Exception as e2:
            print("续写异常:", e2, flush=True)
            time.sleep(4)
            continue
        if not nxt.strip():
            break
        parts.append(nxt)
        print("续写部分 len:", len(nxt), flush=True)

    full = parts_full(parts)
    date = datetime.now().strftime("%Y%m%d")
    out = ROOT / f"weekly_{date}.md"
    out.write_text(full, encoding="utf-8")
    print("DONE parts:", len(parts), "total_len:", len(full))
    print("已保存:", out)
    return out


if __name__ == "__main__":
    main()