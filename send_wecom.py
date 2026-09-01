#!/usr/bin/env python3
"""
企业微信机器人推送：全球汽车行业周报图文卡片
"""
import requests
import sys

# ========== 请修改以下配置 ==========
WEBHOOK_KEY = "你的企业微信机器人KEY"
GITHUB_USER = "你的GitHub用户名"
GITHUB_REPO = "你的GitHub仓库名"
# ===================================

BASE_URL = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}"
COVER_URL = f"{BASE_URL}/cover.png"

payload = {
    "msgtype": "news",
    "news": {
        "articles": [
            {
                "title": "全球汽车行业周报 | 2026年8月31日",
                "description": "本周全球汽车市场五大区域深度解读：中国NEV渗透率突破64%，东南亚BEV销量暴涨，欧洲中国品牌市占率创新高。点击查看完整报告与下周重点关注。",
                "url": BASE_URL,
                "picurl": COVER_URL
            },
            {
                "title": "热点1：中国NEV渗透率64.3%",
                "description": "8月乘用车零售62.8万辆同比-22%，但NEV渗透率升至64.3%。成都车展自主品牌展位首超60%，外资品牌以价格反攻。",
                "url": f"{BASE_URL}/#china",
                "picurl": COVER_URL
            },
            {
                "title": "热点2：东南亚BEV暴增72%-257%",
                "description": "东盟H1 BEV渗透率从12%升至21%，中国车企占80-90%市场份额。泰国7月BEV销量暴增122%，本地化组装加速。",
                "url": f"{BASE_URL}/#sea",
                "picurl": COVER_URL
            },
            {
                "title": "热点3：欧洲中国品牌市占率11.2%创新高",
                "description": "中国品牌7月欧洲市场份额创纪录11.2%，目标2030年30%。欧盟BEV关税9月25日最终投票，小米汽车确认2027年入欧。",
                "url": f"{BASE_URL}/#eu",
                "picurl": COVER_URL
            }
        ]
    }
}


def send():
    if WEBHOOK_KEY == "你的企业微信机器人KEY":
        print("错误：请先在脚本中填写 WEBHOOK_KEY")
        sys.exit(1)

    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"
    resp = requests.post(url, json=payload, timeout=10)
    data = resp.json()

    if data.get("errcode") == 0:
        print("推送成功")
    else:
        print(f"推送失败：{data}")
        sys.exit(1)


if __name__ == "__main__":
    send()
