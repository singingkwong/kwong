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
├── index.html          # 周报主页面（GitHub Pages 入口）
├── styles/             # 样式目录
├── .coze               # Coze 运行配置
├── .gitignore          # Git 忽略规则
└── AGENTS.md           # 本文件
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

## 注意事项

- 不要修改 `.coze` 中的端口配置，运行时已通过 `${DEPLOY_RUN_PORT}` 注入。
- 页面内所有资源建议使用相对路径，确保在 GitHub Pages 子路径下也能正常加载。
- 如需更新周报内容，直接替换 `index.html` 并重新推送到 GitHub。
