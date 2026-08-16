# AI WorkHub 双仓库恢复指南

AI WorkHub 将可复用框架与个人知识分开保存：

- 框架仓库：`pipiyapi/ai-workhub-framework`
- 知识仓库：`pipiyapi/ai-workhub-knowledge-data`

本地组合后，Codex 仍打开框架根目录，Obsidian 仍打开根目录下的 `vault`。

```text
D:\AI-WorkHub\                 # framework Git repository
├─ AGENTS.md
├─ scripts\
├─ RESTORE.md
├─ vault\                       # knowledge-data Git repository
├─ repos\                       # independently restored internal projects
└─ references\repos\            # independently restored external references
```

## 一、安装基础软件

在新 Windows 电脑上安装：

1. Git for Windows
2. GitHub CLI
3. Codex
4. Obsidian

```powershell
git --version
gh --version
codex --version
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

## 二、模式 A：只复用框架，创建一个空知识库

适合把这套工作方法用于新主题、新公司或另一套完全独立的知识库。

### 1. 下载框架

```powershell
git clone https://github.com/pipiyapi/ai-workhub-framework.git D:\AI-WorkHub
Set-Location D:\AI-WorkHub
```

### 2. 创建空 Vault

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 -EmptyKnowledge -SkipProjectClone
```

脚本会创建独立的 `vault` Git 仓库，并从 `scripts/vault-template/` 安装 Obsidian 配置、知识模板和目录骨架。它不会导入任何旧知识。

### 3. 打开应用

- Codex：打开 `D:\AI-WorkHub`
- Obsidian：打开 `D:\AI-WorkHub\vault`

如果新知识库也要云端备份，为它创建另一个私有仓库并把 `vault` 的 `origin` 指向该仓库。

## 三、模式 B：恢复框架并导入原有知识

这是电脑损坏或换电脑后的完整恢复方式。

### 1. 下载框架

```powershell
git clone https://github.com/pipiyapi/ai-workhub-framework.git D:\AI-WorkHub
Set-Location D:\AI-WorkHub
```

### 2. 只读预检

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 -CheckOnly -SkipProjectClone
```

### 3. 导入知识并补齐框架配置

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 -SkipProjectClone
```

脚本会把 `pipiyapi/ai-workhub-knowledge-data` 克隆到 `vault`，再以“不覆盖已有文件”的方式安装 Obsidian 配置和模板。

### 4. 恢复内部项目

确认知识恢复正常后执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

四个 GitHub 项目从各自私有仓库恢复，AI-School 从 Gitee 恢复。它们不会进入框架仓库或知识仓库。

### 5. 验证

```powershell
git -C D:\AI-WorkHub status
git -C D:\AI-WorkHub\vault status
Get-ChildItem D:\AI-WorkHub\vault\wiki
Get-ChildItem D:\AI-WorkHub\repos
```

然后在 Obsidian 打开 `vault/wiki/index.md`，在 Codex 中说：

```text
请读取 AGENTS.md 和 vault/wiki/index.md，只读检查框架与知识仓库是否恢复完整。
```

## 四、模式 C：为现有框架导入另一套知识

目标 `vault` 必须不存在或为空，不能覆盖现有知识：

```powershell
gh repo clone OWNER/ANOTHER-KNOWLEDGE-REPO D:\AI-WorkHub\vault
powershell -ExecutionPolicy Bypass -File .\scripts\install-vault-template.ps1
```

这样可以在相同框架下切换不同知识集。建议不同知识集使用不同的工作目录，避免误把两套知识混合。

## 五、日常备份

只备份框架：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-framework.ps1
```

只备份知识：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-knowledge.ps1
```

同时备份：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-all.ps1
```

三者均支持 `-DryRun`。框架和知识分别生成提交并分别推送，任何一方失败都不会篡改另一方的 Git 历史。

## 六、边界和未备份内容

- 知识仓库不跟踪 `.obsidian/`；它由框架蓝图恢复。
- `vault/raw/`、`vault/wiki/`、`vault/journal/`、`vault/outputs/` 和同步状态属于知识仓库。
- `vault/outputs/video-knowledge/media/` 默认不进 GitHub，保留的视频应使用独立的大文件或加密云备份。
- `repos/` 与 `references/repos/` 不进入框架或知识仓库。
- 虚拟环境、下载工具、缓存、Cookie、Token、密钥和 `.env` 不进入任何仓库。
- Codex 聊天记录不是灾难恢复来源，重要结论必须沉淀到知识仓库。
