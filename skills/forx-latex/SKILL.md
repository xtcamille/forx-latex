---
name: forx-latex
description: 全流程 LaTeX 学术论文写作、模板初始化、语法保护改写、编译自愈与投稿体检技能。当用户需要写 LaTeX 论文、编译 PDF、润色/中译英/压页数、管理 BibTeX、制作三线表/TikZ 图或检查双盲/引用一致性时使用。
---

# Hermes LaTeX 论文工坊指南

## 核心工作原则

1. **零本地 TeX 环境兜底**：若 `latex_setup_compiler(action="status")` 显示本机未安装编译器，先提示用户并可经确认后调用 `latex_setup_compiler(action="install_tectonic")` 一键安装轻量独立的 Tectonic 引擎（无需 TeX Live / MiKTeX）。
2. **模板覆盖**：优先通过 `latex_project_manage(action="list_templates")` 展示 IEEE、计算机顶会（ACM SIGCONF / NeurIPS / CVPR / USENIX / LNCS）及 CCF 区块链专委会推荐期刊（Elsevier BCRA / ACM DLT / IET Blockchain / 中文《计算机学报》《软件学报》《密码学报》等）模板。
3. **改写必用语法保护**：修改现有 `.tex` 正文（润色、中译英、压页数、去 AI 味）时，使用 `latex_syntax_rewrite` 保护 `\cite{}`、`\ref{}`、`\label{}` 与数学公式，切勿直接破坏性重写或编造引用 Key。
4. **改后闭环验证**：写入修改后，建议调用 `latex_compile` 编译验证；若报错，可启用 `auto_heal` 生成最小修复 Diff 并重编确认；投稿前调用 `latex_preflight_check` 完成一致性、双盲匿名与超宽溢出检查。
5. **不虚构文献**：插入参考文献前优先调用 `latex_bib_manage` 通过 DOI、arXiv ID 或 Crossref 检索真实 BibTeX 条目。
6. **资料驱动与对话修改**：当用户提供实验数据（CSV/日志）或架构设计提纲时，调用 `latex_project_chat`，将 `materials/` 中的参考资料作为事实依据，按顶会规范打磨特定章节并生成精准代码补丁，支持安全快照备份与直接合入。
