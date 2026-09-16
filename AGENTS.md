# AGENTS.md

## 项目概览

这是一个原生静态网页项目，用于托管《全球汽车行业周报》HTML 报告。项目通过 GitHub Pages 对外提供静态访问，并通过影刀 RPA 触发企业微信发送报告链接。

## 技术栈

- 模板：`native-static`（Coze CLI）
- 构建工具：无（纯静态 HTML）
- 运行时：Python `http.server`
- 托管目标：GitHub Pages

## 文件结构

```
.
├── index.html              # 周报主页面（GitHub Pages 入口）
├── styles/                 # 样式目录
├── .coze                   # Coze 运行配置
├── .gitignore              # Git 忽略规则
├── scripts/
│   ├── generate_weekly.py  # 调用扣子 Agent 生成周报 HTML
│   ├── agent_checks.py     # Agent 输出检查清单（7 板块/6 区域/三要点/来源/链接）
│   ├── render_html.py      # 将 Agent HTML 渲染为成品周报页面
│   └── send_wecom.py       # 企业微信热点推送
├── templates/weekly.html   # 成品渲染模板
├── DESIGN.md              # 设计规范（渲染与三要点卡片规则）
└── AGENTS.md              # 本文件
```

## 本地预览

```bash
coze dev
```

## GitHub Pages 部署要点

1. 仓库需为 Public（私有仓库的 GitHub Pages 有访问限制）。
2. 在仓库 Settings > Pages 中，Source 选择 Deploy from a branch，Branch 选择 `main`，目录选择 `/(root)`。
3. 部署完成后访问地址为：`https://<用户名>.github.io/<仓库名>/`。
4. 首页文件 `index.html` 必须位于仓库根目录。

## 影刀触发企微流程

1. 影刀触发方式：定时触发 / 手动触发 / HTTP 请求触发。
2. 打开企业微信 PC 客户端。
3. 搜索并定位目标群聊或联系人。
4. 输入消息文本，包含周报标题与 GitHub Pages 链接。
5. 点击发送，完成推送。

## Agent 输出检查清单（scripts/agent_checks.py）

`generate_weekly.py` 每次生成后自动对 Agent 输出的 HTML 执行 `agent_checks.validate()`，不合格自动重试（默认最多 3 次，可用环境变量 `AGENT_MAX_ATTEMPTS` 调整），且**补缺重试**：若某区域无内容（如印度/南美空缺），会把缺失区域清单传给下一次重呼，要求 Agent 专题搜索补齐该区新闻。检查维度：

1. **七大板块齐全**：本周总览 / 各地市场动态 / 政策动态 / 车企动态 / 调研报告·机构观点 / 注塑机会专题 / 下周关注。
2. **市场六大区域覆盖**：中国、北美、欧洲、东南亚、印度、其他——每个区域都须有内容，否则对应板块会空置（"无 news"）。
3. **三要点完整**：每条事件须含 关键数据/事件、影响分析、趋势判断。
4. **来源标注**：每条事件须带"来源：机构名"。
5. **原文链接**：每条事件须带可跳转的 `source-link` 链接，且不能是伪造格式。

常用入口：

```bash
# 校验已保存的 agent.html 输出报告
python3 -c "import sys;sys.path.insert(0,'scripts');from agent_checks import validate,print_report;c=validate(open('agent.html',encoding='utf-8').read());print(print_report(c))"
```

## 注意事项

- 不要修改 `.coze` 中的端口配置，运行时已通过 `${DEPLOY_RUN_PORT}` 注入。
- 页面内所有资源建议使用相对路径，确保在 GitHub Pages 子路径下也能正常加载。
- 如需更新周报内容，直接替换 `index.html` 并重新推送到 GitHub。
- 历史已确认版本以 git tag 记录（如 `weekly-v1-fixed-*`）。
