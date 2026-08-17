# AI WorkHub 使用说明

新电脑备份与恢复请先阅读 [RESTORE.md](RESTORE.md)。AI WorkHub 使用两个互相独立的私有仓库：

- `pipiyapi/ai-workhub-framework`：可复用规则、通用脚本、空白 Obsidian Vault 蓝图与恢复文档，不包含任何用户的项目清单。
- `pipiyapi/ai-workhub-knowledge-data`：个人 Wiki、日报、Raw 来源、处理结果、内部项目登记和同步状态。

本地仍组合成一个工作目录：Codex 打开 `D:\AI-WorkHub`，Obsidian 打开 `D:\AI-WorkHub\vault`。`vault/` 本身是独立 Git 仓库，并被外层框架仓库忽略。

这是基于 Codex、Obsidian 和 Git 的本地个人工作知识库，内部项目来源同时包含 GitHub 与 Gitee。

## Obsidian 技能集成

框架将 [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) 中的 `obsidian-markdown` 作为 Markdown 编辑约定的一部分：使用 Wiki 链接关联 Vault 内知识、使用外链保留外部来源，并可使用 Obsidian callout 提示重点。具体边界以根目录 `AGENTS.md` 的“Obsidian Markdown 技能”为准。

已安装的 Bases、Canvas、Obsidian CLI 和 Defuddle 技能均为可选项；当前框架不要求安装额外插件、CLI 或服务，也不会自动向知识库添加 `.base`、`.canvas` 或网页抓取结果。

- Codex 打开知识库仓库根目录（推荐：`D:\AI-WorkHub`）
- Obsidian 只打开根目录下的 `vault`（推荐：`D:\AI-WorkHub\vault`）
- `repos/` 不加入 Obsidian Vault，避免源码污染搜索和 Graph View。

## 框架与知识分离

| 层 | 本地位置 | GitHub 仓库 | 可以单独使用 |
| --- | --- | --- | --- |
| 框架 | `D:\AI-WorkHub` | `ai-workhub-framework` | 是，可生成全新的空 Vault |
| 知识与用户项目配置 | `D:\AI-WorkHub\vault` | `ai-workhub-knowledge-data` | 是，可导入任意兼容框架 |
| 内部项目 | `D:\AI-WorkHub\repos\*` | 各项目原仓库 | 是，各自独立恢复 |

框架蓝图位于 `scripts/vault-template/`。`bootstrap.ps1` 只补齐缺失的 Obsidian 配置、目录和模板，不覆盖已经存在的知识文件。

分别备份：

```powershell
.\scripts\backup-framework.ps1
.\scripts\backup-knowledge.ps1
```

同时备份两个仓库：

```powershell
.\scripts\backup-all.ps1
```

## 用户自己的 GitHub/Gitee 项目

真实项目清单集中在知识数据仓库的 `vault\system\project-config.psd1`，因此不同的人或不同知识数据集可以拥有完全不同的 GitHub/Gitee 项目。框架仓库只在 `scripts\vault-template\system\project-config.psd1` 提供空白示例。

项目源码仍分别恢复到 `repos\<project>`，不会复制进 framework 或 knowledge-data Git 历史。`Provider = 'GitHub'` 的项目由 GitHub CLI 克隆，其他 Git 服务由普通 `git clone` 克隆。

GitHub 仓库缺失时，脚本先检查 `gh auth status`，认证成功后才使用 `gh repo clone`。需要重新登录时执行：

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

账号必须对当前知识数据配置中登记的私有仓库具有读取权限。项目特有的补充规则随知识数据保存在 `vault\AGENTS.md`。

## GitHub 分支同步

执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-now.ps1
```

同步脚本只处理项目配置中 `SyncMode = 'GitHubBranches'` 的条目，并会：

1. 对每个仓库执行 `git fetch --all --prune`。
2. 读取 `refs/remotes/origin/` 下除 `origin/HEAD` 外的所有远程分支。
3. 获取每个分支的 SHA 和最近提交时间，并识别默认分支与最近活跃分支。
4. 对已有分支只分析 `OLD_SHA..NEW_SHA`。
5. 对新分支从其与默认分支的 `merge-base` 开始分析。
6. 只有单个分支的 Codex 知识更新成功后，才更新对应 JSON 键。

分支状态保存在：

```text
vault\system\sync-state\github\<repository>.json
```

同步不会 checkout、merge、add、commit、push、reset 或 clean。单仓库/单分支失败不会阻止其他项目继续。

## 每天

### 1. 写原始日报

原始日报统一放在：

```text
vault\journal\daily\raw\YYYY-MM-DD.md
```

这里的文件是不可修改事实源。Codex 和脚本不得修改、删除、润色、重命名、移动或覆盖。

### 2. 正常开发并提交 Git

知识库同步只读取 GitHub/Gitee 项目，不替你修改或提交代码。

### 3. 同步并整理

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-now.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\daily-report.ps1
```

整理后的日报输出到：

```text
vault\journal\daily\organized\YYYY-MM-DD.md
```

GitHub/Gitee 用于补全和验证人工日报，不能替代人工日报；Feature 分支工作不会被自动写成“已完成”或“已合并”。日报完成后继续执行 DISTILL。

## 每周

周五或周末执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\weekly-report.ps1
```

周报优先读取 `daily\organized\`，结合本周 commits、远程分支变化、Project、Insights 与 Wiki。只有需要核对事实时才读取只读 raw 日报。

周报文件位于 `vault\journal\weekly\`，同时包含内部完整周报和对外三列表格。

## 视频 → 知识

视频来源沿用现有“外部事实源 → 可读输出 → 必要时蒸馏为长期知识”的体系，没有新增 Vault 顶层目录：

```text
视频链接 / 分享文本 / 本地媒体
→ vault/raw/video/                         # 不可变原始文字稿与 manifest
→ vault/outputs/video-knowledge/notes/     # 可迭代知识笔记
→ vault/outputs/video-knowledge/assets/    # 视觉模式关键画面
→ INGEST / DISTILL                         # 必要时晋升长期 Wiki
```

首次使用先安装免费的本地依赖并检查环境：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-video-knowledge.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\video-knowledge.ps1 doctor
```

安装脚本在 `scripts/.venv-video-knowledge/` 创建独立环境，安装 FunASR、Paraformer/SenseVoice 运行依赖、项目内 yt-dlp 和项目内 FFmpeg 运行包。模型权重在首次转录时从公开模型仓库下载，不需要 API Key。视觉 OCR 需要时增加 `-WithOcr`；抖音/Bilibili 的 Lux 第二下载器需要时增加 `-WithLux`；系统级媒体工具需要时增加 `-InstallMediaTools`。

日常直接在 Codex 中说“把这个视频加入知识库：<链接>”或粘贴完整分享口令。以下底层命令用于排错：

```powershell
.\scripts\video-knowledge.ps1 inspect -InputText "3.21 复制打开抖音…… https://v.douyin.com/.../"
.\scripts\video-knowledge.ps1 ingest -InputText "https://www.bilibili.com/video/BV..."
.\scripts\video-knowledge.ps1 ingest -InputText "https://..." -Mode visual -EnableOcr
.\scripts\video-knowledge.ps1 ingest -InputText "https://..." -KeepVideo
.\scripts\video-knowledge.ps1 audit
```

内容获取顺序是：平台字幕 → 平台自动字幕 → 视频内嵌字幕 → 本地 FunASR。中文知识类讲话默认 Paraformer（VAD、标点和时间戳），SenseVoice 是 CPU 回退。

抖音的下载层与转录层相互独立。默认先通过开源 `Douyin_TikTok_Download_API` 兼容解析端点把分享链接解析为 CDN 媒体地址，并校验下载文件确实含有可解码音频；再尝试本地 yt-dlp 和 Lux。解析端点可用环境变量 `VIDEO_KNOWLEDGE_DOUYIN_RESOLVER_URL` 替换为自有部署，接口只负责“链接 → 媒体地址”，不接触 ASR 或知识库。公共演示端点不保证长期可用，因此替换端点不需要改动后续流水线。

需要登录态时可临时使用 `-CookiesFromBrowser edge`。Cookie 不会写入 Vault。若必须使用导出的 Cookie 文件，只能放在 Vault 外并设置 `VIDEO_KNOWLEDGE_COOKIE_FILE`，不要把 Cookie、Token 或 API Key 放进知识库。

只给出博主名称时，Codex 会先通过公开搜索寻找候选账号和视频；同名或身份不确定时必须让你确认。批量任务默认最多 10 条，先展示候选，确认后逐条入库。确认后的批次使用 `batch-ingest` 清单逐项处理：每条完成后立即原子保存状态，意外中断时直接续跑，已完成项只做完整性复核而不会重新下载或转录。清单会记录 `attempts`、`transcript_path` 和 `note_path`，便于定位单条失败。

流水线针对受限网络做了以下稳定性处理：抖音博主批次只请求一次公开作品列表，并复用其中的 CDN 地址和元数据；CDN 候选按较小完整清晰度优先，单个无响应节点快速超时后切换候选；同批次复用已加载的 FunASR 模型；控制台统一 UTF-8，标题含 emoji 时也不会在成功落盘后因输出编码报错。抖音配置了远程解析器时，不再先执行必然超时的平台网页字幕探测，下载后仍会检查容器内嵌字幕。

每条入库会先完成文字稿、知识笔记、可选关键帧/原视频的暂存与结构校验，最后才提交不可变 raw。`audit` 可随时检查 manifest 与两个持久输出是否一一对应、video ID 是否重复、是否存在孤立笔记和未清理的临时目录。只有完整性校验通过的项目才报告成功。

## 添加技术资料

把原始资料放入 `vault\raw\` 对应目录，然后在 Codex 中说：

```text
按照 AGENTS.md 执行 INGEST。
```

raw 原件始终只读；Codex 优先更新已有知识，不为每份资料机械创建摘要。

## 收藏外部技术资料

### 技术博客与网页

```text
Obsidian Web Clipper
→ vault/raw/web/
→ 按照 AGENTS.md 执行 INGEST
→ concepts / technologies / insights
```

网页原始剪藏始终是 `ownership = external` 的只读资料。

### 第三方 GitHub 页面

```text
Obsidian Web Clipper
→ vault/raw/github/
→ 按照 AGENTS.md 执行 INGEST
```

收藏第三方 README、release 或项目页面，不代表这些能力是我的工作成果。

### 深入阅读第三方源码

当需要研究完整源码时，让 Codex 执行 `EXTERNAL_REPO_INGEST`：

```text
references/repos/<repo-name>
→ EXTERNAL_REPO_INGEST
→ vault/wiki/references/<项目名称>.md
```

目录边界：

- `repos/` = 我的工作项目。
- `references/repos/` = 别人的只读参考项目。
- `vault/wiki/projects/` = 我的项目知识。
- `vault/wiki/references/` = 外部项目知识。

外部资料可以更新 Concept、Technology、Insight 和 Reference，但不能自动进入日报、周报或“用户已完成项目成果”。

## 查询与维护

```text
按照 AGENTS.md 执行 QUERY：<你的问题>
```

定期检查：

```text
按照 AGENTS.md 执行 LINT。
```

## 安全边界

- `repos/` 是 internal 只读工作事实源；`references/repos/` 是 external 只读参考源码。
- 禁止知识库任务执行 `git add`、`git commit`、`git push`、`git reset --hard`、`git clean`。
- `vault/raw/` 与 `vault/journal/daily/raw/` 永远只读。
- 外部网页、GitHub 页面和第三方源码不能自动写成用户工作成果。
- Feature/dev 分支内容必须标注真实状态，不能自动视为已完成或已合并。
- 分支 SHA 只在该分支 Git 分析和知识更新全部成功后推进。
