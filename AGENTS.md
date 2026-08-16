# AI WorkHub 操作规范

本文件是 AI WorkHub 知识库根目录的长期运行规则。Codex 在本目录处理知识库任务时必须遵守；推荐路径是 `D:\AI-WorkHub`，但脚本不得依赖固定盘符。

## 边界与安全

- 根目录是独立的框架仓库，只保存 `.gitignore`、`AGENTS.md`、`README.md`、`RESTORE.md`、`scripts/` 与 `scripts/vault-template/`；`vault/` 是独立的知识数据仓库并由根 `.gitignore` 排除。框架仓库和知识仓库不得互相暂存、提交或嵌入对方的 Git 历史。
- 仅当用户明确要求备份，或用户主动执行相应脚本时，允许在根框架仓库执行 `scripts/backup-framework.ps1`，在 `vault/` 知识仓库执行 `scripts/backup-knowledge.ps1`。该例外永远不扩展到 `repos/`、`references/repos/` 或其他独立项目仓库。

- `repos/` = **INTERNAL WORK PROJECTS**。其中四个 GitHub 项目和 AI-School Gitee 项目均为 `ownership = internal`，是用户自己的工作项目和工作事实来源。除非用户明确要求修改项目，否则禁止写入、删除、格式化项目文件，禁止 `git add`、`git commit`、`git push`、`git reset --hard`、`git clean`、创建 PR 或修改仓库配置。
- `references/repos/` = **EXTERNAL REFERENCE REPOSITORIES**。其中仓库均为 `ownership = external`，是第三方参考源码，绝对不能与 `repos/` 混淆，也不能自动成为用户工作事实。
- 知识库同步只允许获取和读取 Git 数据：`gh auth status`、`gh repo clone`、`git fetch --all --prune`、`git log`、`git diff`、`git show`、`git status`、`git rev-parse`、`git branch --show-current`、`git remote -v`、读取远程 refs、默认分支、提交时间，以及为新分支计算 `git merge-base`。不得 checkout、merge 或改动工作树。
- `references/repos/` 中的第三方仓库默认只读。知识库任务仅允许 `git clone`、`git fetch`、`git log`、`git diff`、`git show`、`git status` 和阅读源码；禁止自动 add、commit、push、创建 PR、修改或删除源码，除非用户明确要求修改某个第三方项目。
- 知识内容只写入 `vault/`；可复用架构只写入 `scripts/`、`scripts/vault-template/`、根目录 `.gitignore`、`AGENTS.md`、`README.md` 和 `RESTORE.md`。`vault/raw/`（包括 `web/`、`github/`、`video/`）与 `vault/journal/daily/raw/` 均为不可修改事实源，禁止修改、删除、润色、重命名、移动或覆盖。视频流水线只允许在完整校验成功后，以事务方式向 `vault/raw/video/` 新建一个来源目录；一旦落盘即视为不可变事实源。
- 不引入向量数据库、RAG 服务、Webhook、Docker、搜索服务、复杂数据库或后端服务。第一版只使用 Markdown、Git、PowerShell、Codex 和 Obsidian。
- 不编造事实。必须区分事实、判断、推断与不确定内容；分支上的工作状态尤其不得夸大。

## Internal Git 项目

| 项目 | 仓库 | Project 页面 | 分支状态文件 |
| --- | --- | --- | --- |
| WPS 合同审查 COM 插件 | `pipiyapi/wps-contract-review-com-addin` | `[[WPS合同审查COM插件]]` | `wps-contract-review-com-addin.json` |
| Word 文档纠错 COM 插件 | `pipiyapi/document-proofreading-com-plugin` | `[[Word文档纠错COM插件]]` | `document-proofreading-com-plugin.json` |
| 敏感词库 | `pipiyapi/sensitive-word-library` | `[[敏感词库]]` | `sensitive-word-library.json` |
| Excel 数据脱敏工具 | `pipiyapi/excel-data-masking-tool` | `[[Excel数据脱敏工具]]` | `excel-data-masking-tool.json` |

以上四个 GitHub 项目继续由 `scripts/sync-github.ps1` 和 `vault/system/sync-state/github/` 维护，现有同步逻辑不得因 AI-School 接入而改写。

| 项目 | 仓库 | Project 页面 | 同步方式 |
| --- | --- | --- | --- |
| AI-School | `https://gitee.com/pipiyapi/AI-School` | `[[AI-School]]` | 当前手工执行 `git fetch --all --prune` 并读取全部 `origin/*` 分支 |

AI-School 是用户自己的内部工作项目，不是 External Reference。它保存于 `repos/AI-School/`；Gitee 是公开稳定分发源，GitHub 私有仓库是开发镜像。当前不要把 AI-School 加入仅按 GitHub CLI 处理缺失仓库的 `project-config.psd1`，除非同步脚本先显式支持 Gitee Clone。

状态目录为 `vault/system/sync-state/github/`。每个 JSON 是“远程分支名 → 最后成功处理 SHA”的对象，例如：

```json
{
  "origin/main": "...",
  "origin/dev": "...",
  "origin/feature/example": "..."
}
```

## Internal 与 External 来源边界

### Internal Source

- `repos/`：用户自己的四个 GitHub 工作项目及 AI-School Gitee 项目，`ownership = internal`。
- `vault/wiki/projects/`：只保存用户内部项目的长期 Project 页面。
- Internal 项目的 commit、diff 和 Project 页面可以在与日期、分支状态相符时作为工作事实证据。

### External Source

- `vault/raw/web/`：外部网页剪藏，`source_type = web`、`ownership = external`。
- `vault/raw/github/`：第三方 GitHub 页面剪藏，`source_type = github`、`ownership = external`。
- `references/repos/`：需要深入研究的第三方源码仓库，`ownership = external`。
- `vault/wiki/references/`：具有长期价值的第三方项目 Reference 页面，必须明确标记 `ownership: external`。

External Source 的知识流是“External Source → INGEST → concepts / technologies / insights / references”，不是“External Source → 用户工作成果”。第三方项目禁止在 `vault/wiki/projects/` 建页；其功能、代码、commit、release、README 能力和项目成果均不得写成用户本人完成。

建议原始资料使用以下 metadata：

```yaml
# Web Clipper 网页
type: external-web
ownership: external
source: https://example.com
status: raw
clipped: YYYY-MM-DD
```

```yaml
# 第三方 GitHub 页面
type: external-github
ownership: external
source: https://github.com/owner/repo
status: raw
clipped: YYYY-MM-DD
```

## 知识维护总则

按“新信息 → 查找已有知识 → 更新已有知识 → 建立关系 → 必要时新建页面”工作，禁止把知识库做成文件摘要库。

- 一个核心概念尽量只有一个长期页面。先搜索文件名、标题、别名和正文，再决定是否新建。
- 项目特有事实进入 `vault/wiki/projects/`；可跨项目复用的内容进入 concepts、technologies 或 insights。
- 普通 commit、typo、格式、注释、小重命名和无行为影响的重构不进入 Wiki。
- 内部链接统一使用 `[[页面名称]]`；相关页面应相互链接。
- 冲突知识不直接覆盖旧结论，保留来源、日期、适用条件、不同观点和当前判断。
- 更新重要页面后维护 `vault/wiki/index.md`，但不机械罗列所有文件。
- 重要操作简洁记录到 `vault/system/log.md`，不记录 token 级或文件级噪声。

## Project 页面规则

每个项目只维护一个主要长期页面。页面必须记录 Repository、默认分支、最近活跃分支、最近同步时间、已完成内容、正在开发内容、最近重要变化、技术架构、技术决策、问题与解决、相关知识和 Insights。

状态必须基于分支和证据区分：已合并、已完成开发但未合并、开发中、测试中、已验证、未确认。Feature/dev 分支代码不能自动视为项目已完成；只有进入默认分支或存在其他明确合并证据时才能写“已合并”。

## Insight 页面规则

Insight 只用于经过验证且有长期价值的踩坑、模型规律、性能结论、架构经验、选型理由、失败方案和跨项目方法论。普通步骤、日常活动、小修复和未验证猜测不建立 Insight。已有相似 Insight 时优先合并，并保留结论、背景、适用条件、原因分析、实际验证、注意事项、相关项目、相关知识和来源。

## 操作定义

### INGEST

1. 只读扫描 `vault/raw/web/`、`vault/raw/github/`、`vault/raw/papers/` 和 `vault/raw/notes/`，判断来源是否已处理；不得修改 raw 原件。
2. 完整理解来源并判断类别。`web/` 与 `github/` 永远保持 `ownership = external`，不得自动改为 internal。
3. 先搜索 `vault/wiki/` 是否已有相关 Concept、Technology、Insight 或 Reference，优先增量更新已有页面；确有独立长期主题时才新建。
4. 不简单生成“某文章摘要”，不因为每个网页或 GitHub 页面机械创建一篇 Wiki。
5. 保留 source URL、来源、采集日期、适用条件和不确定性，建立必要的双向链接。
6. 外部资料只允许更新 `concepts/`、`technologies/`、`insights/`、`references/`；不得写入用户 Project 成果。
7. 更新重要索引入口，并在 `vault/system/log.md` 简记结果。

### VIDEO_INGEST

当用户说“把这个视频加入知识库”“提取这个抖音/Bilibili”“当成播客处理”或表达同等意图时执行：

1. 从 URL、分享文本或本地文件识别输入；分享文本自动提取 URL。默认 `mode = talk`、`keep_video = false`，只有用户明确要求时才保留视频。
2. 先运行 `scripts/video-knowledge.ps1 inspect` 做平台识别和重复检查，再运行 `ingest`。唯一性依次使用 `platform + video_id`、canonical URL / URL hash、本地文件 SHA256。已存在时返回加入日期和 Obsidian 链接。
3. 内容获取按“平台人工/作者字幕 → 平台自动字幕 → 容器内嵌字幕 → 本地 FunASR”降级。中文讲话默认 `funasr-paraformer`，可回退 SenseVoice。不得把付费 API 或 API Key 设为必需依赖。
4. Talk / Podcast 为默认模式。用户明确说明 PPT、代码、图表、白板或软件演示时使用 `mode = visual`，通过 FFmpeg 场景变化检测和感知哈希去重提取关键画面，可选 RapidOCR；禁止机械地每 N 秒截图。
5. 原始文字稿写入 `vault/raw/video/<platform>/<stable-id>/`，标记 `type: external-video-transcript`、`ownership: external`、`status: raw`，保留时间戳、原始顺序、来源和处理方式。知识笔记写入 `vault/outputs/video-knowledge/notes/`，关键画面写入同一 outputs 体系；只有经 INGEST/DISTILL 判断后才晋升 Wiki。
6. 原视频只在临时目录处理。仅在 transcript 和所需关键画面校验成功后清理；`keep_video = true` 时保存到 `vault/outputs/video-knowledge/media/`。失败时不得写入半成品 raw。
7. 若输入只是博主名称或主题，Codex 使用公开搜索查找账号/视频。存在同名、身份不可靠或批量任务时，必须先展示候选账号与视频并等待确认，确认前不得下载。
8. 批量任务默认上限 10 条。先确认账号，再列候选，再由用户确认；每条独立处理。超过 10 条需要再次明确确认，单条失败不影响其他条目。
9. 当前 Bilibili 与抖音先尝试 yt-dlp，再回退 Lux；不得假设抖音长期稳定。登录、风控、地区或 Cookie 失败时明确报告，不绕过平台安全机制。
10. Cookie 优先用 `--cookies-from-browser <browser>` 临时读取。Cookie 文件只允许通过 `VIDEO_KNOWLEDGE_COOKIE_FILE` 引用 Vault 外路径；禁止将 Cookie、Token 或浏览器配置写入 Vault、日志、manifest、Markdown 或回复。
11. 本地脚本只生成忠实 transcript 与结构化草稿。Codex 直接读取 transcript 后补全摘要、核心观点和详细内容，不为总结强制引入付费 AI API。

### EXTERNAL_REPO_INGEST

当用户要求“深入研究这个 GitHub 项目”或“把这个外部项目加入参考库”时执行：

1. 先确认目标不是已登记的 internal 项目；如属于 internal，不得放入 `references/repos/`，应按对应 Git 服务执行内部项目增量分析。
2. Clone 到 `references/repos/<repo-name>`；已有仓库只 fetch 和读取，不覆盖或修改源码。
3. 阅读 README、项目结构、核心源码、配置、文档和 tests，理解实现而非只摘抄项目介绍。
4. 在 `vault/wiki/references/<项目名称>.md` 建立或更新唯一长期 Reference 页面，明确 `ownership: external`。
5. Reference 页面记录：来源、项目定位、核心能力、技术架构、值得参考的实现、局限、与本人项目的关系、可复用知识、相关 Concepts、Technologies 和 Insights。
6. 提取真正可复用的知识，优先更新已有 concepts、technologies 和 insights。
7. 与内部 Project 的关系只能描述为“参考实现”“类似方案”“技术来源”“可借鉴方案”或“对比对象”。不得描述成用户项目组成部分，除非有明确事实证明。
8. 第三方源码始终只读；不得自动 add、commit、push、创建 PR、修改或删除源码。

### QUERY

先读 `vault/wiki/index.md`，再搜索相关 Wiki、Project 和 Insight；信息不足时再查 raw 与 repos。回答时区分事实、判断、推断和不确定内容，并给出来源。

### LINT

检查重复/同义页面、断链、孤立页面、过时或冲突知识、无来源结论、索引遗漏、应合并内容、误入 Wiki 的流水账及长期未更新的 Project 页面。安全且证据明确的问题可修复；存在歧义的只报告。不得修改 raw 或 repos。

### GITHUB_INGEST

1. 从 `scripts/project-config.psd1` 读取项目配置。仓库不存在时先执行 `gh auth status`；认证成功才可用 `gh repo clone`。认证或权限失败时停止 Clone，不反复重试。
2. 执行 `git fetch --all --prune`，识别默认分支和 `refs/remotes/origin/` 下除 `origin/HEAD` 外的全部远程分支，获取分支名、HEAD SHA 和最近提交时间。
3. 首次理解 README、目录结构、核心配置、关键代码、依赖、测试和主要文档，建立唯一 Project 页面。
4. 对默认分支做首次项目基线分析。对其他首次发现的分支，用默认分支与新分支的 `merge-base` 作为 BASE_SHA，只分析 `BASE_SHA..NEW_SHA`，禁止重读整个分支历史。
5. 逐分支提取长期知识并准确标注状态。只有该分支的知识更新成功后，才将该分支 SHA 写入 JSON；失败分支不得推进，也不得影响其他分支。

### GITHUB_UPDATE

1. 每仓库执行 `git fetch --all --prune`，不得写死 `origin/main`，不得 checkout 或 pull 工作分支。
2. 枚举 `refs/remotes/origin/`，排除 `origin/HEAD`，并逐分支与 JSON 中的 OLD_SHA 比较。
3. 已存在且变化的分支只分析 `git log OLD_SHA..NEW_SHA` 与 `git diff OLD_SHA..NEW_SHA`。必要时读取变更涉及的源码、README、配置、文档和测试；禁止完整重读仓库。
4. 新分支先确定默认分支，再计算 `git merge-base <default-branch> <new-branch>`，只分析 `BASE_SHA..NEW_SHA`。如果无法得到 merge-base，标记失败并保留未处理状态，不退化为全历史分析。
5. 判断功能、修复、架构/API/运行方式/依赖、设计决策、长期问题与跨项目复用价值；忽略无实际影响的低价值变化。
6. 增量更新 Project、Wiki、Insights、Index 与 Log，明确分支名及“已合并/未合并/开发中/测试中/已验证/未确认”。不为普通 commit 单建页面。
7. 同步脚本调用时 Codex 不写 JSON。脚本仅在 Codex 对该分支成功退出后原子更新对应键；任何失败保留旧 SHA。单分支或单仓库失败不能阻止其他分支和仓库。

### DAILY_REPORT

1. 原始日报只读位置：`vault/journal/daily/raw/YYYY-MM-DD.md`。绝对禁止修改、删除、润色、重命名、移动或覆盖。
2. 整理后的日报写入 `vault/journal/daily/organized/YYYY-MM-DD.md`，结构为：今日完成、项目进展、问题与解决、知识洞察、明日计划、关联项目、关联知识。
3. 综合当天原始日报、全部 internal 仓库相关远程分支 commits/diff、Project 页面、当天 Insights/Wiki 更新及 system log。当前包括四个 GitHub 仓库和 AI-School Gitee 仓库。
4. GitHub/Gitee 只用于补全和验证人工日报，不能替代人工日报。描述做了什么、解决什么、推进到哪里，不复制 commit message、不夸大。
5. 分支工作必须标注真实状态；Feature 分支内容不得自动写为已完成。没有依据的计划或成果不得编造。
6. External Source 不能仅因被收藏、Clone、分析或形成 Reference 页面就成为工作事实。只有当天 raw 明确记录“调研、阅读、对比、参考、方案分析”等行为时，才可写用户完成了相应调研；仍不得把第三方项目自身能力写成用户开发成果。

### DISTILL

从整理后日报的问题与解决、知识洞察、GitHub 重要变更、项目决策和解决过程判断长期价值。优先更新已有 concepts、technologies、insights，必要时才新建；禁止整篇复制日报。完成后维护 index 和 log。

### WEEKLY_REPORT

1. 按本地当前自然周读取 `vault/journal/daily/organized/`，并结合本周全部 internal 仓库 commits、远程分支变化、Project、Insights、Wiki 与 system log。raw 日报只在需要验证事实时读取，且始终只读。
2. 写入 `vault/journal/weekly/YYYY-Www.md`，生成内部完整周报和对外三列表格。
3. 按成果、项目推进、问题、交付、技术方案、测试/量化结果和知识沉淀归并，不按星期机械拼接。
4. 对外版使用 `| 日期 | 内容 | 是否完成 |`；只有明确事实依据时写“已完成”。未合并分支上的内容应准确写开发中、测试中或待合并。
5. `vault/raw/web/`、`vault/raw/github/`、`references/repos/` 和 `vault/wiki/references/` 不能自动成为周工作成果。只有本周 raw 日报明确记录外部调研工作时，才可归纳为“调研、分析、参考或完成方案对比”，不得把第三方项目能力归为用户交付。

## 同步成功判定

每个分支独立判定。Project/Wiki/Insights/Index/Log 的必要更新全部落盘且 Codex 命令成功退出，才算该分支同步成功。同步脚本负责最后原子更新 JSON 中该分支的 SHA；Git、Codex 或知识写入失败时不得推进该键。
