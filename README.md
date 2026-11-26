# hermes-latex — 单人全栈 AI LaTeX 论文创作插件

独立外部插件，融合云端平台开箱编译/模板能力、本地 IDE 语义工程能力与 AI 原生科研写作闭环（不含多人实时协同）。

## 核心能力

- **零本地 TeX 环境支持**：内置独立编译器探测与 **Tectonic 一键安装**（`hermes latex setup` 或桌面工作台一键按钮），无需预先安装完整 TeX Live / MiKTeX。
- **12 套首批内置学术模板**：
  - **IEEE 系列**：`ieee-trans`（IEEE TIFS/TDSC/TPDS/TNSE）、`ieee-conf`（IEEE S&P/ICDE/ICBC）
  - **计算机顶会顶刊**：`acm-sigconf`（CCS/SIGMOD/KDD）、`acm-journal`（ACM DLT/CSUR）、`neurips`（自包含样式）、`cvpr`（自包含样式）、`usenix`（Security/OSDI）、`springer-lncs`
  - **CCF 区块链专委会推荐期刊**：`elsevier-bcra`（BCRA CCF-B / HCC）、`iet-blockchain`、`cn-blockchain-journal`（《计算机学报》《软件学报》《密码学报》《信息安全学报》双栏中文核心期刊）
  - **学位论文**：`cn-thesis`
- **SyncTeX 双向定位 & 结构化诊断**：纯 Python `.synctex.gz` 解析实现源码行 ↔ PDF 页码双向跳转，结构化提取 Error / Warning / Overfull hbox。
- **LaTeX 语法保护 AI 引擎**：自动占位锁定 `\cite{}`、`\ref{}`、`\label{}`、`$...$` 等指令后再做润色/中译英/压页数/去 AI 味，支持 Diff 审阅、编译错误 AI 自愈及 CSV 一键转 `booktabs` 三线表。
- **BibTeX 管家 & 投稿体检**：DOI / arXiv 拉取、Crossref 检索、去重格式化、Zotero `.bib` 同步；交叉引用一致性、未引用图表、缩略语展开、双盲匿名泄漏与超页数检查，并可一键导出干净投稿/arXiv ZIP。

## 安装

### 方式一：从社区插件目录一键安装（推荐）

目录条目合并后，所有 ForX / Hermes 用户可直接安装：

```powershell
forx plugins install hermes-latex
# 或通用 Hermes：
hermes plugins install hermes-latex
```

### 方式二：手动安装

将本仓库克隆到用户插件目录并启用（Windows ForX 默认目录为 `%LOCALAPPDATA%\forx\plugins\`，通用 Hermes 为 `~/.hermes/plugins/`）：

```powershell
git clone https://github.com/CamilleZxt/hermes-latex "$env:LOCALAPPDATA\forx\plugins\hermes-latex"
hermes plugins enable hermes-latex
```

如果本机尚未安装任何 TeX 发行版，执行以下命令一键安装轻量编译器 Tectonic：

```powershell
hermes latex setup
```

## 提供 Tools

| Tool | 用途 |
| --- | --- |
| `latex_project_manage` | 创建项目 / 应用模板（IEEE、ACM、NeurIPS、CVPR、USENIX、LNCS、CCF 区块链期刊、学位论文） |
| `latex_compile` | 零 TeX 环境编译，结构化诊断，`auto_heal` 自愈 |
| `latex_syntax_rewrite` | 锁定 `\cite`/`\ref`/`\label`/公式后安全润色、中译英、压页数、去 AI 味 |
| `latex_bib_manage` | DOI / arXiv / Crossref 拉取真实 BibTeX，去重格式化，Zotero 同步 |
| `latex_preflight_check` | 交叉引用一致性、未引用图表、双盲匿名泄漏、超页数检查，导出投稿 ZIP |
| `latex_generate_snippet` | 三线表、TikZ 图等常用片段生成 |
| `latex_setup_compiler` | 检测 / 安装 Tectonic 编译器 |
| `latex_project_chat` | 以 `materials/` 资料为事实依据打磨章节，生成可审阅补丁 |

## 许可证

MIT
