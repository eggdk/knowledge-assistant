# 网页问答插件前端

本目录是 `knowledge-assistant` 的前端工程，使用 React、TypeScript 和 Vite，实现可嵌入普通网页的桌面聊天插件。

当前交付为静态界面：右下角悬浮入口、欢迎面板、输入区、展开收起及键盘操作。发送按钮禁用，尚未连接问答后端，不会生成回答、引用或反馈记录。本项目当前不做移动端。

## 目录结构

```text
web/
├─ README.md
├─ index.html               # 普通网页宿主演示，通过 embed.js 加载插件
├─ widget.html              # iframe 内的 React 页面入口
├─ public/embed.js          # 独立加载脚本，生产构建时保留固定文件名
├─ src/
│  ├─ main.tsx              # 界面组件、状态、消息通信与焦点管理
│  └─ style.css             # 插件样式
├─ scripts/check-embed.mjs  # 加载脚本的轻量边界检查
├─ package.json
├─ pnpm-lock.yaml           # 依赖锁文件
├─ pnpm-workspace.yaml      # 本工程的 pnpm 配置
├─ tsconfig.json
└─ vite.config.ts           # 演示页与插件页的多页面构建配置
```

组件职责：

| 组件 | 职责 |
|---|---|
| `App` | 展开状态、宿主消息通信、Esc 关闭与焦点恢复 |
| `Launcher` | 右下角悬浮入口 |
| `ChatPanel` | 面板标题、关闭按钮和内容布局 |
| `WelcomeState` | 欢迎图标、标题与说明 |
| `Composer` | 输入区、禁用的发送按钮与预览提示 |

## 环境准备

已有开发记录使用 Node.js 24.22.1、pnpm 11.25.0，项目依赖由 `pnpm-lock.yaml` 固定。前端不需要 Python 虚拟环境。

先确认终端可以运行以下命令：

```shell
node --version
pnpm --version
```

若命令不可用，先在自己的环境中准备 Node.js 和 pnpm，再重新打开终端。本工程不依赖个人电脑的盘符、用户名或编辑器缓存路径。

## 本地开发

从 `knowledge-assistant` 仓库根目录运行：

```shell
cd apps/web
pnpm install --frozen-lockfile
pnpm dev
```

打开终端显示的地址，通常为 `http://127.0.0.1:5173/`，点击右下角按钮查看插件。按 `Ctrl+C` 停止服务。若已进入本目录，直接执行安装和启动命令即可。

Windows PowerShell 中若 `pnpm` 被解析为不可执行的脚本，可以使用 `pnpm.cmd` 替代。

## 检查、构建与预览

以下命令均在本目录执行：

| 命令 | 作用 |
|---|---|
| `pnpm typecheck` | 执行 TypeScript 类型检查，不生成构建产物 |
| `node --check public/embed.js` | 检查加载脚本语法 |
| `node scripts/check-embed.mjs` | 检查重复加载、子路径解析、消息过滤、卸载和重新挂载 |
| `pnpm build` | 生成生产静态文件到 `dist/` |
| `pnpm preview` | 预览已经生成的生产静态文件 |

生产预览需先构建，再运行预览命令；地址以终端输出为准。页面必须通过 HTTP(S) 服务访问，不能直接双击 HTML 文件代替运行。

构建可能提示演示页中的普通 `embed.js` 无法作为模块打包。该脚本有意保持独立，由 Vite 原样复制到 `dist/`，不能直接给它添加 `type="module"`，因为加载逻辑使用 `document.currentScript` 定位自身地址。

轻量检查使用模拟宿主，不替代真实浏览器、实际网站或 Agent Insight 的交互验证。`node_modules/`、`.pnpm-store/` 和 `dist/` 是本地生成目录，已通过 `.gitignore` 排除。

## 嵌入普通网页

加载关系：

```text
宿主页 → embed.js → iframe（widget.html）→ React 插件界面
```

将 `dist/` 全部文件放到可访问的静态目录，保留 `embed.js`、`widget.html` 与 `assets/` 之间的目录关系。宿主添加一条脚本标签，并把示例地址替换为实际的插件地址：

```html
<script src="https://example.com/knowledge-assistant/embed.js" defer></script>
```

宿主不需要安装 React。加载脚本会根据自身地址找到同目录的 `widget.html`，支持静态资源部署到子路径。iframe 隔离内部样式，外围容器使用 Shadow DOM；重复加载只保留一个实例。宿主需允许加载相应脚本和 iframe。

插件默认收起，展开区域约为 380 × 600 像素；较小桌面窗口会约束尺寸。支持关闭按钮、悬浮按钮收起和 Esc，关闭后焦点回到入口，刷新后重置。

宿主与插件通过 `knowledge-assistant:state` 消息同步展开状态，校验来源窗口、origin 和布尔状态。该通信只控制界面，不是问答 API。

### 单页应用卸载

宿主页离开对应布局时，可以向插件容器发送卸载事件：

```javascript
document
  .getElementById('knowledge-assistant-embed')
  ?.dispatchEvent(new Event('knowledge-assistant:dispose'));
```

该事件会移除容器和消息监听。再次挂载时需重新加载接入脚本。

## Agent Insight 接入说明

可将构建后的 `embed.js`、`widget.html` 和整个 `assets/` 放入宿主的 `public/knowledge-assistant/`，再在所需布局加载 `/knowledge-assistant/embed.js`。插件更新后需重新构建并同步这些资源；本工程未提供自动同步流程。

宿主自身的安装、数据目录配置和启动方式应遵循其项目说明。静态插件能加载不代表真实问答已接通，入口展示、页面切换、键盘交互和宿主兼容性仍需在具体宿主中验证。

## 后端对接边界

后端位于同一仓库的 `apps/api/`，与前端分别运行。当前前端没有业务接口请求，也没有后端代理配置。

已有建库、上传和文档列表接口见 [后端接口约定](../../docs/api/knowledge-base-v1.md)。接入问答前需双方确认知识库标识、会话上下文、流式事件、引用详情、反馈与错误格式；前端不能自行假定尚未提供的接口。

当前网页上传接口的 `searchable: false` 表示资料已存储，不代表可以问答。模型调用及密钥由后端负责。
