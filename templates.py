"""Built-in academic LaTeX templates (IEEE, CS Top Venues, CCF Blockchain Journals, Thesis) + ZIP import."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

from .models import TemplateMeta

_SHARED_BIB = """@article{nakamoto2008bitcoin,
  author  = {Nakamoto, Satoshi},
  title   = {Bitcoin: A Peer-to-Peer Electronic Cash System},
  journal = {Decentralized Business Review},
  year    = {2008},
  pages   = {21260}
}

@inproceedings{castro1999pbft,
  author    = {Castro, Miguel and Liskov, Barbara},
  title     = {Practical Byzantine Fault Tolerance},
  booktitle = {Proceedings of the Third Symposium on Operating Systems Design and Implementation (OSDI)},
  year      = {1999},
  pages     = {173--186}
}

@article{wood2014ethereum,
  author  = {Wood, Gavin},
  title   = {Ethereum: A Secure Decentralised Generalised Transaction Ledger},
  journal = {Ethereum Project Yellow Paper},
  year    = {2014},
  volume  = {151},
  pages   = {1--32}
}
"""


def _shared_sections(*, lang: str = "en") -> dict[str, str]:
    if lang == "zh":
        return {
            "sections/01_intro.tex": r"""\section{引言}
\label{sec:intro}

近年来，随着分布式系统与可信计算基础设施的快速发展，如何在去中心化环境下同时实现高吞吐、强一致性与可验证安全性，成为学术界与工业界共同关注的核心问题~\cite{nakamoto2008bitcoin,castro1999pbft}。

本文针对上述挑战提出了一种可扩展的系统框架。主要贡献总结如下：
\begin{itemize}
  \item \textbf{形式化建模}：给出面向关键安全属性的形式化定义与威胁模型（见第~\ref{sec:method} 节）。
  \item \textbf{高效协议设计}：设计低通信复杂度的协同机制，降低节点验证开销。
  \item \textbf{充分实验验证}：在多节点测试环境下完成基准对比（见表~\ref{tab:results}）。
\end{itemize}
""",
            "sections/02_related.tex": r"""\section{相关工作}
\label{sec:related}

现有研究主要分为面向共识协议优化与面向执行层扩展两类路线~\cite{castro1999pbft,wood2014ethereum}。与现有方案相比，本文在保持安全假设不变的前提下，进一步提升了系统的端到端吞吐率与确定性延迟表现。
""",
            "sections/03_method.tex": r"""\section{系统设计与方法}
\label{sec:method}

令 $\mathcal{N} = \{1, \dots, n\}$ 表示参与节点集合，其中至多存在 $f < n/3$ 个拜占庭节点。节点在轮次 $r$ 内通过状态转移函数 $\Pi(s_r, \sigma_r) \rightarrow s_{r+1}$ 完成区块确认与状态提交：
\begin{equation}
\label{eq:throughput}
T_{\mathrm{eff}} = \frac{B_{\mathrm{tx}}}{\Delta_{\mathrm{prop}} + \Delta_{\mathrm{verify}}}
\end{equation}
由式~\eqref{eq:throughput} 可见，缩短验证延迟 $\Delta_{\mathrm{verify}}$ 与消息传播开销 $\Delta_{\mathrm{prop}}$ 是提升吞吐的关键路径。
""",
            "sections/04_experiments.tex": r"""\section{实验评估}
\label{sec:experiments}

表~\ref{tab:results} 展示了本文方法与基线方案在不同节点规模下的吞吐量与确认延迟对比结果。

\begin{table}[htbp]
  \centering
  \caption{不同节点规模下的系统性能对比}
  \label{tab:results}
  \begin{tabular}{lccc}
    \toprule
    方案名称 & 吞吐量 (TPS) $\uparrow$ & 确认延迟 (s) $\downarrow$ & 通信开销 (KB/tx) $\downarrow$ \\
    \midrule
    Baseline-PBFT~\cite{castro1999pbft} & 1,420 & 3.85 & 18.4 \\
    Baseline-EVM~\cite{wood2014ethereum} & 2,180 & 2.94 & 12.1 \\
    \textbf{本文方法 (Ours)} & \textbf{4,860} & \textbf{1.12} & \textbf{5.3} \\
    \bottomrule
  \end{tabular}
\end{table}
""",
            "sections/05_conclusion.tex": r"""\section{总结与展望}
\label{sec:conclusion}

本文提出并验证了面向高可信分布式环境的协同处理架构。实验结果表明，本文方案在吞吐量与延迟方面均优于对比基线。未来工作将进一步探索跨链互操作与零知识证明加速方向。
""",
        }

    return {
        "sections/01_intro.tex": r"""\section{Introduction}
\label{sec:intro}

Decentralized protocols and high-assurance distributed systems have attracted substantial research attention in recent years~\cite{nakamoto2008bitcoin,wood2014ethereum}. However, achieving high throughput while preserving Byzantine fault tolerance and deterministic finality remains challenging~\cite{castro1999pbft}.

In this paper, we address these limitations with a modular protocol design. Our main contributions are summarized as follows:
\begin{itemize}
  \item \textbf{Formal Framework:} We formulate the system and threat model under standard partial-synchrony assumptions (Section~\ref{sec:method}).
  \item \textbf{Protocol Optimization:} We reduce message complexity and verification overhead without weakening safety guarantees.
  \item \textbf{Empirical Evaluation:} Extensive benchmarks demonstrate consistent gains in throughput and tail latency (Table~\ref{tab:results}).
\end{itemize}
""",
        "sections/02_related.tex": r"""\section{Related Work}
\label{sec:related}

Prior efforts focus either on Byzantine consensus scalability~\cite{castro1999pbft} or programmable state-machine execution~\cite{wood2014ethereum}. Unlike existing approaches, our architecture decouples ordering from batched state verification to eliminate redundant cross-node communication.
""",
        "sections/03_method.tex": r"""\section{Methodology}
\label{sec:method}

Let $\mathcal{N} = \{1, \dots, n\}$ denote the validator set with at most $f < n/3$ Byzantine nodes. In round $r$, honest replicas advance state via $\Pi(s_r, \sigma_r) \rightarrow s_{r+1}$, yielding effective throughput:
\begin{equation}
\label{eq:throughput}
T_{\mathrm{eff}} = \frac{B_{\mathrm{tx}}}{\Delta_{\mathrm{prop}} + \Delta_{\mathrm{verify}}}.
\end{equation}
As indicated in Eq.~\eqref{eq:throughput}, minimizing both propagation latency $\Delta_{\mathrm{prop}}$ and per-batch verification cost $\Delta_{\mathrm{verify}}$ governs end-to-end scalability.
""",
        "sections/04_experiments.tex": r"""\section{Evaluation}
\label{sec:experiments}

Table~\ref{tab:results} compares our proposed protocol against representative baselines across throughput, confirmation latency, and per-transaction communication cost.

\begin{table}[t]
  \centering
  \caption{Performance comparison against baseline protocols ($n=32$ validators).}
  \label{tab:results}
  \begin{tabular}{lccc}
    \toprule
    Method & Throughput (TPS) $\uparrow$ & Latency (s) $\downarrow$ & Comm. (KB/tx) $\downarrow$ \\
    \midrule
    PBFT~\cite{castro1999pbft} & 1,420 & 3.85 & 18.4 \\
    Standard Ledger~\cite{wood2014ethereum} & 2,180 & 2.94 & 12.1 \\
    \textbf{Ours} & \textbf{4,860} & \textbf{1.12} & \textbf{5.3} \\
    \bottomrule
  \end{tabular}
\end{table}
""",
        "sections/05_conclusion.tex": r"""\section{Conclusion}
\label{sec:conclusion}

We presented a scalable, Byzantine-resilient protocol architecture and evaluated it across realistic network settings. Future work will extend our design to cross-domain interoperability and hardware-accelerated proof verification.
""",
    }


TEMPLATES: dict[str, TemplateMeta] = {
    "ieee-trans": TemplateMeta(
        id="ieee-trans",
        name="IEEE Transactions 期刊 (IEEE TIFS / TDSC / TPDS / TNSE)",
        category="ieee",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["IEEE", "CCF-A", "TIFS", "TDSC", "TPDS", "TNSE", "TSC"],
        page_limit=14,
        double_blind=False,
        description="IEEEtran 双栏期刊模板，适用于 IEEE TIFS、TDSC、TPDS、TNSE 等顶刊与 CCF 区块链相关英文期刊。",
    ),
    "ieee-conf": TemplateMeta(
        id="ieee-conf",
        name="IEEE 会议双栏模板 (IEEE S&P / ICDE / INFOCOM / ICBC)",
        category="ieee",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["IEEE", "S&P", "ICDE", "ICDCS", "INFOCOM", "ICBC"],
        page_limit=12,
        double_blind=True,
        description="IEEEtran conference 模式，含双盲匿名开关与标准会议排版规范。",
    ),
    "acm-sigconf": TemplateMeta(
        id="acm-sigconf",
        name="ACM SIGCONF 会议模板 (CCS / SIGMOD / KDD / WWW)",
        category="cs_top",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["ACM", "CCF-A", "CCS", "SIGMOD", "KDD", "WWW"],
        page_limit=12,
        double_blind=True,
        description="acmart sigconf 双栏模板，含 CCS Concepts 与匿名审稿选项。",
    ),
    "acm-journal": TemplateMeta(
        id="acm-journal",
        name="ACM 期刊模板 (ACM DLT / CSUR / TOIS)",
        category="ccf_blockchain",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["ACM", "CCF-C", "ACM DLT", "CSUR", "Blockchain"],
        page_limit=24,
        double_blind=False,
        description="acmart acmsmall 期刊模板，适配 ACM Distributed Ledger Technologies (DLT) 等 ACM 系列期刊。",
    ),
    "neurips": TemplateMeta(
        id="neurips",
        name="NeurIPS / ICLR 机器学习顶会模板 (自包含样式)",
        category="cs_top",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["NeurIPS", "ICLR", "CCF-A", "AI"],
        page_limit=9,
        double_blind=True,
        description="单栏顶会模板，内置自包含 neurips_compat.sty 兼容样式及 Paper Checklist。",
    ),
    "cvpr": TemplateMeta(
        id="cvpr",
        name="CVPR / ICCV / AAAI 顶会模板 (自包含样式)",
        category="cs_top",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["CVPR", "ICCV", "AAAI", "CCF-A"],
        page_limit=8,
        double_blind=True,
        description="双栏计算机视觉/AI 顶会模板，内置自包含审稿行号与匿名模式。",
    ),
    "usenix": TemplateMeta(
        id="usenix",
        name="USENIX Security / OSDI / NSDI 系统安全顶会",
        category="cs_top",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["USENIX", "OSDI", "NSDI", "Security", "CCF-A"],
        page_limit=13,
        double_blind=True,
        description="USENIX 双栏会议排版，含伦理考量与 Artifact Evaluation 章节。",
    ),
    "springer-lncs": TemplateMeta(
        id="springer-lncs",
        name="Springer LNCS (CRYPTO / EUROCRYPT / ESORICS / FC)",
        category="cs_top",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["LNCS", "CRYPTO", "ESORICS", "FC", "Springer"],
        page_limit=16,
        double_blind=True,
        description="Springer LNCS 单栏密码学与信息安全会议模板（含自包含兼容宏包确保零缺失编译）。",
    ),
    "elsevier-bcra": TemplateMeta(
        id="elsevier-bcra",
        name="Elsevier 区块链期刊 (BCRA CCF-B / HCC)",
        category="ccf_blockchain",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["Elsevier", "BCRA", "CCF-B", "HCC", "CCF-TCBC"],
        page_limit=20,
        double_blind=False,
        description="elsarticle 双栏/审稿模板，适配 Blockchain: Research and Applications (BCRA) 与 High-Confidence Computing (HCC)。",
    ),
    "iet-blockchain": TemplateMeta(
        id="iet-blockchain",
        name="IET Blockchain / 工程区块链英文期刊",
        category="ccf_blockchain",
        language="en",
        recommended_engine="tectonic",
        venue_tags=["IET Blockchain", "CCF-TCBC", "SCI", "EI"],
        page_limit=16,
        double_blind=False,
        description="适配 IET Blockchain 等 CCF 区块链专委会推荐英文期刊，含 Data Availability 与 Funding 声明段。",
    ),
    "cn-blockchain-journal": TemplateMeta(
        id="cn-blockchain-journal",
        name="中文计算机核心期刊 (计算机学报/软件学报/密码学报/信息安全学报)",
        category="ccf_blockchain",
        language="bilingual",
        recommended_engine="tectonic",
        venue_tags=["计算机学报", "软件学报", "计算机研究与发展", "密码学报", "信息安全学报", "CCF-TCBC"],
        page_limit=16,
        double_blind=False,
        description="基于 ctexart 的中文双栏期刊模板，含中英文双语摘要、关键词、中图分类号、基金资助及作者简介。",
    ),
    "cn-thesis": TemplateMeta(
        id="cn-thesis",
        name="中文研究生学位论文模板 (硕士/博士)",
        category="thesis",
        language="bilingual",
        recommended_engine="tectonic",
        venue_tags=["中文学位论文", "ctexbook", "硕博论文"],
        page_limit=None,
        double_blind=False,
        description="基于 ctexbook 的中文学位论文结构模板，含中英文摘要、目录、分章正文、致谢与成果清单。",
    ),
}


def list_templates() -> list[TemplateMeta]:
    return list(TEMPLATES.values())


def get_template_files(
    template_id: str,
    *,
    title: str = "Scalable Byzantine Consensus for Decentralized Applications",
    author: str = "Anonymous Author(s)",
) -> tuple[TemplateMeta, dict[str, str]]:
    if template_id not in TEMPLATES:
        raise KeyError(f"未知模板: {template_id}。可选: {', '.join(TEMPLATES)}")
    meta = TEMPLATES[template_id]
    files: dict[str, str] = {"refs.bib": _SHARED_BIB}
    zh_title = title if any("\u4e00" <= c <= "\u9fff" for c in title) else "面向去中心化应用的可扩展拜占庭共识机制研究"

    if template_id == "ieee-trans":
        files.update(_shared_sections(lang="en"))
        files["main.tex"] = r"""\documentclass[journal]{IEEEtran}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{cite}

\begin{document}
\title{__TITLE__}
\author{__AUTHOR__%
\thanks{Manuscript received November 2026.}}

\maketitle

\begin{abstract}
This paper investigates scalable consensus and verifiable execution in decentralized networks. We formalize the system model, propose an optimized pipelined protocol, and demonstrate significant throughput and latency improvements over existing baselines.
\end{abstract}

\begin{IEEEkeywords}
Blockchain, Byzantine fault tolerance, distributed consensus, scalability.
\end{IEEEkeywords}

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{IEEEtran}
\bibliography{refs}
\end{document}
"""
    elif template_id == "ieee-conf":
        files.update(_shared_sections(lang="en"))
        files["main.tex"] = r"""\documentclass[conference]{IEEEtran}
\IEEEoverridecommandlockouts
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{cite}

\begin{document}
\title{__TITLE__}
\author{\IEEEauthorblockN{__AUTHOR__}
\IEEEauthorblockA{Double-Blind Submission}}

\maketitle

\begin{abstract}
We present a scalable and verifiable protocol for decentralized state replication under partial synchrony. Evaluation results demonstrate 2.2$\times$--3.4$\times$ higher throughput with lower communication overhead.
\end{abstract}

\begin{IEEEkeywords}
Distributed systems, consensus, blockchain, fault tolerance.
\end{IEEEkeywords}

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{IEEEtran}
\bibliography{refs}
\end{document}
"""
    elif template_id in {"acm-sigconf", "acm-journal"}:
        files.update(_shared_sections(lang="en"))
        doc_opts = "sigconf,anonymous,review" if template_id == "acm-sigconf" else "acmsmall"
        files["main.tex"] = r"""\documentclass[__DOC_OPTS__]{acmart}
\usepackage{booktabs}

\begin{document}
\title{__TITLE__}

\author{__AUTHOR__}
\affiliation{%
  \institution{Anonymous Institution}
  \country{Country}
}

\begin{abstract}
This work introduces a modular state-machine replication protocol designed for high-throughput decentralized ledger applications.
\end{abstract}

\begin{CCSXML}
<ccs2012>
   <concept>
       <concept_id>10010520.10010575.10010577</concept_id>
       <concept_desc>Computer systems organization~Dependable and fault-tolerant systems and networks</concept_desc>
       <concept_significance>500</concept_significance>
   </concept>
</ccs2012>
\end{CCSXML}
\ccsdesc[500]{Computer systems organization~Dependable and fault-tolerant systems and networks}
\keywords{Distributed Ledger, Consensus, Fault Tolerance}

\maketitle

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{ACM-Reference-Format}
\bibliography{refs}
\end{document}
""".replace("__DOC_OPTS__", doc_opts)
    elif template_id == "neurips":
        files.update(_shared_sections(lang="en"))
        files["neurips_compat.sty"] = r"""% Self-contained NeurIPS-compatible style wrapper for zero-dependency builds
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{neurips_compat}[2026/01/01 NeurIPS-compatible layout]
\RequirePackage[margin=1in]{geometry}
\RequirePackage{times}
\RequirePackage{xcolor}
\RequirePackage{fancyhdr}
\newif\if@neuripsfinal\@neuripsfinalfalse
\DeclareOption{final}{\@neuripsfinaltrue}
\ProcessOptions\relax
\pagestyle{fancy}
\fancyhf{}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0pt}
\newcommand{\nipsline}{\par\noindent\rule{\linewidth}{2pt}\par}
\renewcommand{\maketitle}{%
  \begin{center}
    \nipsline
    \vspace{0.5em}
    {\Large\bfseries \@title \par}
    \vspace{0.5em}
    \nipsline
    \vspace{0.75em}
    {\normalsize \if@neuripsfinal \@author \else Anonymous Author(s)\\Affiliation\\Address\\\texttt{email} \fi \par}
    \vspace{1em}
  \end{center}
}
"""
        files["main.tex"] = r"""\documentclass{article}
\usepackage{neurips_compat}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage[numbers]{natbib}

\title{__TITLE__}
\author{__AUTHOR__}

\begin{document}
\maketitle

\begin{abstract}
We study scalable Byzantine-resilient coordination and present an analytical and empirical evaluation across multi-node clusters.
\end{abstract}

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{plainnat}
\bibliography{refs}
\end{document}
"""
    elif template_id == "cvpr":
        files.update(_shared_sections(lang="en"))
        files["cvpr_compat.sty"] = r"""\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{cvpr_compat}[2026/01/01 CVPR-compatible two-column layout]
\RequirePackage[margin=0.68in,columnsep=0.3125in]{geometry}
\RequirePackage{times}
\RequirePackage{lineno}
\newif\if@cvprfinal\@cvprfinalfalse
\DeclareOption{final}{\@cvprfinaltrue}
\ProcessOptions\relax
\if@cvprfinal\else\linenumbers\fi
"""
        files["main.tex"] = r"""\documentclass[10pt,twocolumn,letterpaper]{article}
\usepackage{cvpr_compat}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}

\title{__TITLE__}
\author{Anonymous CVPR Submission\\Paper ID ****}

\begin{document}
\maketitle

\begin{abstract}
We propose a high-throughput verification and representation pipeline evaluated on standard multi-node benchmarks.
\end{abstract}

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{plain}
\bibliography{refs}
\end{document}
"""
    elif template_id == "usenix":
        files.update(_shared_sections(lang="en"))
        files["usenix_compat.sty"] = r"""\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{usenix_compat}[2026/01/01 USENIX-compatible two-column style]
\RequirePackage[margin=0.75in,columnsep=0.33in]{geometry}
\RequirePackage{times}
"""
        files["main.tex"] = r"""\documentclass[letterpaper,twocolumn,10pt]{article}
\usepackage{usenix_compat}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}

\title{\Large\bf __TITLE__}
\author{__AUTHOR__}
\date{}

\begin{document}
\maketitle

\begin{abstract}
We design and implement a fault-tolerant distributed execution engine that scales linearly with validator count while maintaining strict safety guarantees.
\end{abstract}

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\section*{Artifact Availability}
Source code and benchmark scripts will be released upon publication.

\bibliographystyle{plain}
\bibliography{refs}
\end{document}
"""
    elif template_id == "springer-lncs":
        files.update(_shared_sections(lang="en"))
        files["main.tex"] = r"""\documentclass[runningheads]{article}
\usepackage[margin=1.4in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}

\title{__TITLE__}
\author{__AUTHOR__}
\date{}

\begin{document}
\maketitle

\begin{abstract}
We propose a verifiable cryptographic coordination protocol and establish formal security bounds under standard assumptions.
\par\medskip\noindent\textbf{Keywords:} Blockchain \and Consensus \and Cryptography.
\end{abstract}

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{plain}
\bibliography{refs}
\end{document}
"""
    elif template_id == "elsevier-bcra":
        files.update(_shared_sections(lang="en"))
        files["main.tex"] = r"""\documentclass[preprint,12pt,5p,times,twocolumn]{elsarticle}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}

\journal{Blockchain: Research and Applications}

\begin{document}
\begin{frontmatter}
\title{__TITLE__}

\author[inst1]{__AUTHOR__}
\affiliation[inst1]{organization={School of Computer Science}, city={Beijing}, country={China}}

\begin{abstract}
This paper investigates high-throughput Byzantine fault-tolerant consensus and verifiable state execution for next-generation blockchain systems.
\end{abstract}

\begin{keyword}
Blockchain \sep Distributed consensus \sep Byzantine fault tolerance \sep Scalability
\end{keyword}
\end{frontmatter}

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{elsarticle-num}
\bibliography{refs}
\end{document}
"""
    elif template_id == "iet-blockchain":
        files.update(_shared_sections(lang="en"))
        files["main.tex"] = r"""\documentclass[twocolumn,10pt]{article}
\usepackage[margin=0.7in,columnsep=0.28in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}

\title{__TITLE__}
\author{__AUTHOR__}
\date{}

\begin{document}
\maketitle

\begin{abstract}
We propose a low-overhead validation protocol tailored for permissioned and public blockchain networks, achieving substantial gains in throughput and finality latency.
\end{abstract}

\noindent\textbf{Keywords:} Blockchain, consensus, smart contracts, performance evaluation.

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\section*{Data Availability Statement}
Data sharing is not applicable to this article as no external datasets were generated.

\section*{Conflict of Interest}
The authors declare no conflict of interest.

\bibliographystyle{plain}
\bibliography{refs}
\end{document}
"""
    elif template_id == "cn-blockchain-journal":
        files.update(_shared_sections(lang="zh"))
        files["main.tex"] = r"""\documentclass[UTF8,twocolumn,10pt]{ctexart}
\usepackage[margin=1.8cm,columnsep=0.6cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage[numbers,sort&compress]{natbib}

\title{\Large\bfseries __ZH_TITLE__}
\author{__AUTHOR__}
\date{}

\begin{document}
\twocolumn[
  \begin{@twocolumnfalse}
    \maketitle
    \begin{abstract}
    \noindent\textbf{摘\quad 要}：针对去中心化分布式账本在高并发场景下面临的共识通信瓶颈与验证延迟问题，本文提出了一种可扩展的拜占庭容错协同处理框架。通过将交易排序与批量状态验证解耦，有效降低了单节点通信复杂度。实验结果表明，本文方案在吞吐量与确认延迟等关键指标上均显著优于现有基线方案。

    \noindent\textbf{关键词}：区块链；拜占庭容错；共识机制；可扩展性
    \vspace{0.5em}

    \noindent\textbf{Abstract}: This paper presents a scalable Byzantine fault-tolerant coordination framework for decentralized ledgers. By decoupling transaction ordering from batched state verification, our protocol reduces per-node communication overhead and outperforms representative baselines in throughput and latency.

    \noindent\textbf{Key words}: blockchain; Byzantine fault tolerance; consensus mechanism; scalability
    \vspace{1em}
    \end{abstract}
  \end{@twocolumnfalse}
]

\input{sections/01_intro}
\input{sections/02_related}
\input{sections/03_method}
\input{sections/04_experiments}
\input{sections/05_conclusion}

\bibliographystyle{unsrtnat}
\bibliography{refs}
\end{document}
"""
    else:  # cn-thesis
        files.update(_shared_sections(lang="zh"))
        files["main.tex"] = r"""\documentclass[UTF8,a4paper,12pt]{ctexbook}
\usepackage[margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage[numbers,sort&compress]{natbib}

\title{__ZH_TITLE__}
\author{__AUTHOR__}
\date{\today}

\begin{document}
\frontmatter
\maketitle

\chapter*{摘\quad 要}
\addcontentsline{toc}{chapter}{摘\quad 要}
针对分布式共识与区块链系统面临的可扩展性瓶颈，本文开展了系统性研究并设计了高效验证协议。

\tableofcontents

\mainmatter
\chapter{绪论}
\input{sections/01_intro}
\input{sections/02_related}

\chapter{系统设计与形式化分析}
\input{sections/03_method}

\chapter{实验评估与性能对比}
\input{sections/04_experiments}

\chapter{总结与展望}
\input{sections/05_conclusion}

\backmatter
\bibliographystyle{unsrtnat}
\bibliography{refs}

\chapter*{致\quad 谢}
\addcontentsline{toc}{chapter}{致\quad 谢}
感谢导师与课题组成员的悉心指导与支持。
\end{document}
"""

    files["main.tex"] = (
        files["main.tex"]
        .replace("__TITLE__", title)
        .replace("__ZH_TITLE__", zh_title)
        .replace("__AUTHOR__", author)
    )
    return meta, files


def extract_zip_template(zip_bytes: bytes, *, max_files: int = 200, max_total_bytes: int = 20 * 1024 * 1024) -> dict[str, str]:
    """Safely extract text files from an uploaded template ZIP (blocks ZipSlip & bombs)."""
    files: dict[str, str] = {}
    total_size = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_files:
            raise ValueError(f"压缩包文件过多 ({len(infos)} > {max_files})")
        # Detect common single top-level directory prefix
        names = [i.filename.replace("\\", "/").lstrip("/") for i in infos]
        prefixes = {n.split("/", 1)[0] for n in names if "/" in n}
        strip_prefix = next(iter(prefixes)) + "/" if len(prefixes) == 1 and all("/" in n for n in names) else ""

        for info in infos:
            raw_name = info.filename.replace("\\", "/").lstrip("/")
            if strip_prefix and raw_name.startswith(strip_prefix):
                raw_name = raw_name[len(strip_prefix):]
            if not raw_name or ".." in Path(raw_name).parts or raw_name.startswith("__MACOSX"):
                continue
            total_size += info.file_size
            if total_size > max_total_bytes:
                raise ValueError("模板压缩包解压后超过 20MB 上限")
            raw = zf.read(info)
            if b"\x00" in raw[:1024]:
                continue
            files[raw_name] = raw.decode("utf-8", errors="replace")
    if not files:
        raise ValueError("压缩包中未找到有效的文本或 LaTeX 文件")
    return files
