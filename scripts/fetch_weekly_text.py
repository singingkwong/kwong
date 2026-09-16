#!/usr/bin/env python3
"""通过 API 真正触发新 Bot，多轮续写拿完整 Markdown 文本输出（突破单轮 5 次工具上限 6150）。

输出：ROOT/weekly_YYYYMMDD.md（Agent 原始 Markdown 文本，含图片 URL 引用）。
"""
import os, re, sys, time, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_weekly as g

g.BOT_ID = os.environ.get("COZE_BOT_ID", "7685975869638459392")

ROOT = g.ROOT

SECTIONS = ["本周总览", "各地市场动态", "政策动态", "车企动态", "调研报告", "注塑机会", "下周关注"]
REGS = ["中国", "北美", "欧洲", "东南亚", "印度", "其他"]

MAIN_PROMPT = f"""请撰写今天（{datetime.now().strftime('%Y年%m月%d日')}）《全球汽车行业深度周报》，直接输出 Markdown 文本（不是 HTML）。

要求：
1. 板块齐全：一、本周总览；二、分区域市场动态（中国/北美/欧洲/东南亚/印度/其他）；三、政策与法规；四、主要车企动态；五、注塑机会；六、下周关注。
2. 分区域市场动态用子标题标出每个区域（中国市场/北美市场/欧洲市场/东南亚市场/印度市场），每区至少给 3-4 条真实新闻。
3. 每条新闻包含：关键事件与数据、产业链影响、趋势判断、【原文链接】真实可访问的 URL；并在文末标注 来源：机构名。
4. 若相关，可在相应位置用 Markdown 图片语法 ![](图片URL) 引用真实存在的配图（全篇 ≥3 张）。
5. 只输出 Markdown 文本本身，不要输出前后说明文字。
"""

CONT_TMPL = """请继续撰写刚才那份《全球汽车行业深度周报》尚未完成的部分，与被截断的前文连成完整一份。当前仍缺：{hints}。请针对缺失部分继续输出 Markdown 文本，格式与前文一致（每条含 关键事件与数据/产业链影响/趋势判断/【原文链接】+来源）。可以直接基于你已掌握的信息补充，不必重新联网全文检索。只输出新增部分的 Markdown，不要重复前文，不要输出说明文字。"""


def parts_full(parts):
    return "\n".join(x for x in parts if x)


def still_missing(full):
    hints = []
    miss_regs = [r for r in REGS if f"{r}市场" not in full]
    if miss_regs:
        hints.append("分区域市场动态中尤其要补齐：" + "、".join(miss_regs))
    miss_secs = [s for s in SECTIONS if s not in full]
    if miss_secs:
        hints.append("补齐板块：" + "、".join(miss_secs))
    return "；".join(hints)


def main():
    parts = []
    try:
        p1 = g.fetch_weekly_html(extra_instruction="")
        parts.append(p1)
        print("首轮 len:", len(p1), flush=True)
    except Exception as e:
        print("首轮异常(将续写):", e, flush=True)

    for r in range(1, 12):
        full = parts_full(parts)
        missing = still_missing(full)
        if not missing:
            print(f"板块与区域齐全(len={len(full)})，结束续写", flush=True)
            break
        print(f"---- 续写轮 {r}: {missing} ----", flush=True)
        try:
            nxt = g.fetch_weekly_continued(CONT_TMPL.format(hints=missing))
        except Exception as e2:
            print("续写异常:", e2, flush=True)
            time.sleep(4)
            continue
        if not nxt.strip():
            print("本轮返回空，退出", flush=True)
            break
        parts.append(nxt)
        open(f"/tmp/fetch_text_round{r}.md", "w", encoding="utf-8").write(nxt)
        print("续写部分 len:", len(nxt), flush=True)

    full = parts_full(parts)
    date = datetime.now().strftime("%Y%m%d")
    out = ROOT / f"weekly_{date}.md"
    out.write_text(full, encoding="utf-8")
    print("DONE parts:", len(parts), "total_len:", len(full))
    print("已保存:", out)


if __name__ == "__main__":
    main()