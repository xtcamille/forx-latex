import {
  host,
  useValue,
  Button,
  Badge,
  Codicon,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Textarea,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  PALETTE_AREA,
} from '@hermes/plugin-sdk'
import { createElement as h, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'

const PLUGIN_ID = 'forx-latex'

function cleanErrorMessage(err) {
  let msg = err?.message || String(err || '') || '操作未完成，请重试'
  msg = msg.replace(/^Error invoking remote method '[^']+':\s*/i, '')
  msg = msg.replace(/^Error:\s*/i, '')
  const httpMatch = msg.match(/^(\d{3}):\s*(.*)$/s)
  if (httpMatch) {
    const [, status, body] = httpMatch
    try {
      const parsed = JSON.parse(body)
      if (parsed.detail) {
        if (typeof parsed.detail === 'string') return parsed.detail
        if (Array.isArray(parsed.detail)) {
          return parsed.detail.map(d => `${d.loc?.filter(x => x !== 'body').join('.') || '参数'}: ${d.msg}`).join('; ')
        }
        return JSON.stringify(parsed.detail)
      }
      if (parsed.error) return parsed.error
    } catch {
      if (body.trim()) return body.trim()
    }
    if (status === '404') return '接口未找到或后端尚未加载该路由 (404)'
    if (status === '422') return '请求参数格式校验未通过 (422)'
    if (status === '500') return '后台服务处理异常，请检查大模型或编译状态 (500)'
  }
  return msg
}

const CSS = `
.hlx-root {
  container: hlx-workbench / inline-size;
  --hlx-inset: clamp(8px, 1.15cqi, 14px);
  /* The compiled desktop CSS can inline radius tokens into its utilities. */
  --hlx-control-radius: var(--radius-lg, calc(var(--radius-scalar, 1) * 0.75rem));
  --hlx-panel-radius: var(--radius-2xl, calc(var(--radius-scalar, 1) * 1.5rem));
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  min-height: 0;
  min-width: 0;
  color: var(--ui-text-primary);
  background: var(--ui-bg-chrome);
  font-family: var(--dt-font-sans, system-ui);
  font-size: 13px;
  overflow: hidden;
}

/* Toolbar */
.hlx-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  margin: var(--hlx-inset) var(--hlx-inset) 0;
  padding: 9px 12px;
  border: 1px solid var(--ui-stroke-tertiary);
  border-radius: var(--hlx-panel-radius);
  background: var(--ui-bg-elevated);
  flex: none;
  flex-wrap: wrap;
}
.hlx-tb-group, .hlx-action-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-width: 0;
  max-width: 100%;
}
.hlx-save-label {
  min-width: 4em;
  text-align: center;
}
.hlx-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 14px;
  color: var(--ui-text-primary);
  letter-spacing: -0.2px;
  user-select: none;
  white-space: nowrap;
}
.hlx-brand-icon {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: var(--hlx-control-radius);
  background: var(--ui-control-active-background);
  color: color-mix(in oklab, var(--ui-accent) 60%, var(--ui-text-primary));
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: bold;
}

.hlx-select {
  min-width: 0;
  max-width: 100%;
  height: 32px;
  padding: 0 10px;
  border-radius: var(--hlx-control-radius, 12px);
  border: 1px solid var(--ui-stroke-tertiary);
  background: var(--ui-control-hover-background);
  color: var(--ui-text-primary);
  font-size: 12.5px;
  text-overflow: ellipsis;
}
.hlx-project-select {
  width: clamp(9rem, 24cqi, 15rem);
}
.hlx-reference-select {
  width: 9rem;
  height: 28px;
  font-size: 11.5px;
}
.hlx-banner, .hlx-error-bar, .hlx-status {
  flex: none;
  margin: 8px var(--hlx-inset) 0;
  border-radius: var(--hlx-control-radius);
  padding: 7px 12px;
  font-size: 12px;
}
.hlx-banner, .hlx-error-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.hlx-banner {
  flex-wrap: wrap;
  background: color-mix(in oklab, var(--ui-yellow) 12%, var(--ui-bg-elevated));
}

.hlx-error-bar {
  max-height: 20%;
  overflow: auto;
  background: color-mix(in oklab, var(--ui-red) 10%, var(--ui-bg-elevated));
  color: color-mix(in oklab, var(--ui-red) 68%, var(--ui-text-primary));
}
.hlx-error-bar > span, .hlx-card, .hlx-chat-header, .hlx-mat-label {
  min-width: 0;
  overflow-wrap: anywhere;
}
.hlx-status {
  align-self: flex-start;
  background: var(--ui-bg-elevated);
  color: var(--ui-text-secondary);
}
.hlx-empty {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 12px;
  text-align: center;
  display: grid;
  align-content: safe center;
  justify-items: center;
  gap: 12px;
}
/* 3-Pane Layout */
.hlx-main {
  display: grid;
  grid-template-columns: var(--hlx-columns);
  grid-template-rows: minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  overflow: hidden;
  gap: var(--hlx-inset);
  padding: var(--hlx-inset);
}
.hlx-main > * {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border-radius: var(--hlx-panel-radius);
  border: 1px solid var(--ui-stroke-tertiary);
  background: var(--ui-bg-elevated);
}
.hlx-center {
  background: var(--ui-bg-editor);
}

/* Segmented Tabs */
.hlx-tabs {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 9px 4px;
}
.hlx-workspace-controls {
  align-self: flex-start;
  margin: var(--hlx-inset) var(--hlx-inset) 0;
  padding: 4px;
  border-radius: var(--radius-xl, 16px);
  border: 1px solid var(--ui-stroke-tertiary);
  background: var(--ui-bg-elevated);
}
.hlx-pane-switch {
  display: none;
}
@container hlx-workbench (width >= 52rem) {
  .hlx-main > [data-collapsed] { display: none; }
}
@container hlx-workbench (width < 52rem) {
  .hlx-pane-controls { display: none; }
  .hlx-pane-switch { display: flex; }
  .hlx-main {
    grid-template-columns: minmax(0, 1fr);
  }
  .hlx-main > :not([data-compact-active]) {
    display: none;
  }
}
.hlx-tab {
  border: none;
  background: transparent;
  color: var(--ui-text-secondary);
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 550;
  cursor: pointer;
  white-space: nowrap;
}
.hlx-left .hlx-tab {
  padding-inline: 6px;
}
.hlx-pane-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.hlx-tab:hover {
  background: var(--ui-control-hover-background);
  color: var(--ui-text-primary);
}
.hlx-tab:is([aria-pressed="true"], [aria-expanded="true"]) {
  background: var(--ui-control-active-background);
  color: var(--ui-text-primary);
}
.hlx-select:focus-visible, .hlx-tab:focus-visible, .hlx-item:focus-visible,
.hlx-prompt-chip:focus-visible, .hlx-tmpl-card:focus-visible, .hlx-upload:focus-within {
  outline: 2px solid var(--ui-accent);
  outline-offset: -2px;
}

/* Scroll area */
.hlx-scroll {
  flex: 1;
  overflow: auto;
  padding: 10px;
  min-height: 0;
}
.hlx-scroll, .hlx-textarea, .hlx-chat-messages, .hlx-tmpl-grid {
  scrollbar-width: thin;
  scrollbar-color: var(--ui-stroke-primary) transparent;
}

/* List Items */
.hlx-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 7px 10px;
  border-radius: var(--hlx-control-radius);
  cursor: pointer;
  font-size: 12.5px;
  color: var(--ui-text-primary);
  text-align: start;
  margin-bottom: 2px;
}
.hlx-item:hover {
  background: var(--ui-row-hover-background);
}
.hlx-item-active {
  background: var(--ui-row-active-background);
}
.hlx-file-label {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.hlx-file-label .codicon {
  flex: none;
  color: var(--ui-text-tertiary);
}

/* Cards */
.hlx-card {
  padding: 12px 14px;
  border-radius: var(--radius-xl, 16px);
  border: 1px solid var(--ui-stroke-tertiary);
  background: var(--ui-bg-editor);
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Editor */
.hlx-editor-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 12px;
  border-bottom: 1px solid var(--ui-stroke-tertiary);
  background: var(--ui-bg-elevated);
  flex-wrap: wrap;
}
.hlx-editor-name {
  flex: 1 0 10rem;
  flex-wrap: nowrap;
}
.hlx-editor-name > :last-child {
  white-space: nowrap;
}
.hlx-truncate, .hlx-badge.hlx-truncate {
  display: block;
  min-width: 0;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hlx-editor-wrap {
  --hlx-line-height: 20px;
  --hlx-editor-padding: 12px;
  flex: 1;
  display: flex;
  min-height: 0;
  background: var(--ui-bg-editor, var(--ui-bg-primary));
}
.hlx-gutter, .hlx-textarea {
  font: 12.5px/var(--hlx-line-height) var(--dt-font-mono, monospace);
}
.hlx-gutter {
  flex: 0 0 3rem;
  text-align: right;
  color: var(--ui-text-tertiary);
  user-select: none;
  border-right: 1px solid var(--ui-stroke-quaternary);
  overflow: hidden;
  background: var(--ui-bg-elevated);
}
.hlx-gutter pre {
  margin: 0;
  padding: var(--hlx-editor-padding) 8px;
  font: inherit;
}
.hlx-textarea {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  resize: none;
  padding: var(--hlx-editor-padding) 12px;
  color: var(--ui-text-primary);
  background: transparent;
  tab-size: 2;
  white-space: pre;
  overflow: auto;
}

/* Selection action floating bar */
.hlx-selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin: 7px 8px 0;
  padding: 6px 10px;
  border-radius: var(--hlx-control-radius);
  background: var(--ui-control-hover-background);
  font-size: 12px;
}

/* PDF Preview Frame */
.hlx-pdf-frame {
  flex: 1;
  min-height: 0;
  margin: 4px 8px 8px;
  border: none;
  border-radius: var(--hlx-control-radius);
  background: var(--ui-bg-chrome);
}

/* Chat & Copilot */
.hlx-chat-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: var(--ui-bg-elevated);
}
.hlx-chat-header {
  padding: 7px 12px;
  border-bottom: 1px solid var(--ui-stroke-tertiary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11.5px;
  flex-shrink: 0;
}
.hlx-chat-context {
  flex: 1 0 12rem;
}
.hlx-chat-filename {
  flex: 1 1 7rem;
  max-width: min(16rem, 100%);
}
.hlx-chat-messages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.hlx-chat-welcome {
  flex-shrink: 0;
}
.hlx-chat-welcome p {
  margin: 0 0 10px;
  color: var(--ui-text-secondary);
  line-height: 1.6;
}
.hlx-chat-row {
  display: flex;
  flex-direction: column;
  max-width: 92%;
  flex-shrink: 0;
}
.hlx-chat-row-user {
  align-self: flex-end;
}
.hlx-chat-row-assistant {
  align-self: flex-start;
}
.hlx-chat-bubble {
  padding: 12px 16px;
  font-size: 12.5px;
  line-height: 1.6;
  word-break: break-word;
  color: var(--ui-text-primary);
}
.hlx-chat-bubble-user {
  border-radius: var(--radius-xl, 16px) var(--radius-xl, 16px) var(--radius-sm, 6px) var(--radius-xl, 16px);
  background: var(--ui-control-active-background);
}
.hlx-chat-bubble-assistant {
  border-radius: var(--radius-xl, 16px) var(--radius-xl, 16px) var(--radius-xl, 16px) var(--radius-sm, 6px);
  background: var(--ui-bg-editor);
  border: 1px solid var(--ui-stroke-tertiary);
}
.hlx-prompt-chip {
  font-size: 11.5px;
  padding: 5px 12px;
  border-radius: 9999px;
  border: 1px solid var(--ui-stroke-tertiary);
  background: var(--ui-bg-quaternary);
  color: var(--ui-text-secondary);
  cursor: pointer;
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
  text-align: start;
}
.hlx-prompt-chip:hover {
  background: var(--ui-control-active-background);
  color: var(--ui-text-primary);
}
.hlx-patch-box {
  margin-top: 10px;
  border-radius: var(--hlx-control-radius);
  background: var(--ui-bg-quaternary);
  padding: 10px 12px;
  font-size: 11.5px;
}
.hlx-diff {
  font-family: var(--dt-font-mono, monospace);
  font-size: 11.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  padding: 10px 12px;
  border-radius: var(--hlx-control-radius, 12px);
  background: var(--ui-bg-editor);
  border: 1px solid var(--ui-stroke-tertiary);
  max-height: 240px;
  overflow: auto;
  overflow-wrap: anywhere;
}
.hlx-chat-input-bar {
  margin: 0 11px 11px;
  padding: 9px 10px;
  border-radius: var(--radius-xl, 16px);
  border: 1px solid var(--ui-stroke-secondary);
  background: var(--ui-bg-editor);
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}
.hlx-chat-input-bar:focus-within {
  border-color: var(--ui-accent);
}
.hlx-chat-materials-select {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11.5px;
  max-height: 6rem;
  overflow: auto;
}
.hlx-mat-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 9999px;
  background: var(--ui-bg-quaternary);
  border: 1px solid var(--ui-stroke-tertiary);
  cursor: pointer;
  user-select: none;
  max-width: 100%;
}
.hlx-chat-textarea {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--ui-text-primary);
  padding: 3px 4px;
  font-size: 12.5px;
  line-height: 1.5;
  resize: none;
  outline: none;
}
.hlx-chat-textarea::placeholder {
  color: var(--ui-text-tertiary);
}

/* Modals */
.hlx-dialog {
  max-width: min(46rem, calc(100vw - 24px));
}

.hlx-tmpl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(12rem, 100%), 1fr));
  gap: 10px;
  max-height: min(42dvh, 24rem);
  overflow: auto;
  padding: 2px;
}
.hlx-file-form {
  display: grid;
  gap: 12px;
}
.hlx-file-form-error {
  color: var(--ui-red);
  margin: 0;
  overflow-wrap: anywhere;
}
.hlx-tmpl-card {
  padding: 12px 14px;
  border-radius: var(--radius-xl, 16px);
  border: 1px solid var(--ui-stroke-tertiary);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--ui-bg-editor);
  color: inherit;
  text-align: start;
}
.hlx-tmpl-card:hover {
  background: var(--ui-control-hover-background);
}
.hlx-tmpl-card-active {
  border-color: var(--ui-stroke-primary);
  background: var(--ui-control-active-background);
}

/* Badges & Pills */
.hlx-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 500;
  background: var(--ui-bg-quaternary);
  color: var(--ui-text-secondary);
}
.hlx-badge-success {
  background: color-mix(in oklab, var(--ui-green) 12%, transparent);
  color: color-mix(in oklab, var(--ui-green) 68%, var(--ui-text-primary));
}
.hlx-badge-accent {
  background: var(--ui-control-active-background);
  color: color-mix(in oklab, var(--ui-accent) 60%, var(--ui-text-primary));
}

@media (prefers-reduced-motion: no-preference) {
  .hlx-tab, .hlx-item, .hlx-select, .hlx-tmpl-card, .hlx-prompt-chip, .hlx-chat-input-bar {
    transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease;
  }
}
@media (prefers-reduced-motion: reduce) {
  .hlx-dialog { animation: none; }
}
`

function b64ToBlobUrl(b64, mime = 'application/pdf') {
  const bin = atob(b64)
  const arr = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i += 1) arr[i] = bin.charCodeAt(i)
  return URL.createObjectURL(new Blob([arr], { type: mime }))
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '')
    reader.onerror = () => reject(new Error('无法读取本地文件'))
    reader.readAsDataURL(file)
  })
}

const SNIPPETS = [
  { label: '公式', code: '\n\\begin{equation}\n  \\label{eq:new}\n  y = f(x)\n\\end{equation}\n' },
  { label: '三线表', code: '\n\\begin{table}[htbp]\n  \\centering\n  \\caption{Evaluation Results}\n  \\label{tab:new}\n  \\begin{tabular}{lcc}\n    \\toprule\n    Method & Acc (\\%) & Latency (ms) \\\\\n    \\midrule\n    Baseline & 92.4 & 3.85 \\\\\n    Ours & \\textbf{98.2} & \\textbf{1.12} \\\\\n    \\bottomrule\n  \\end{tabular}\n\\end{table}\n' },
  { label: '插图', code: '\n\\begin{figure}[htbp]\n  \\centering\n  \\includegraphics[width=0.9\\linewidth]{figures/arch.pdf}\n  \\caption{System Architecture.}\n  \\label{fig:arch}\n\\end{figure}\n' },
]

const WORKSPACE_PANES = [
  { id: 'files', label: '工程', track: 'clamp(10rem, 20cqi, 14rem)' },
  { id: 'editor', label: '源码', track: 'minmax(0, 1.15fr)' },
  { id: 'output', label: '预览与工具', track: 'minmax(0, 1fr)' },
]

function WorkspacePaneControls({ paneId, isExpanded, onToggle, compact = false }) {
  return h('div', {
    className: `hlx-tabs hlx-workspace-controls ${compact ? 'hlx-pane-switch' : 'hlx-pane-controls'}`,
    role: 'group',
    'aria-label': compact ? '工作区视图' : '工作区面板',
  }, WORKSPACE_PANES.map(pane => {
    const expanded = isExpanded(pane.id)
    return h('button', {
      key: pane.id,
      type: 'button',
      className: 'hlx-tab hlx-pane-toggle',
      'aria-controls': `${paneId}-${pane.id}`,
      'aria-expanded': expanded,
      onClick: () => onToggle(pane.id),
    }, h(Codicon, { name: expanded ? 'eye' : 'eye-closed', size: 13 }), pane.label)
  }))
}

function WorkbenchTabs({ label, items, value, onChange }) {
  return h('div', {
    className: 'hlx-tabs',
    role: 'group',
    'aria-label': label,
  }, items.map(item => h('button', {
    key: item.id,
    type: 'button',
    className: 'hlx-tab',
    'aria-pressed': value === item.id,
    onClick: () => onChange(item.id),
  }, item.label)))
}

function WorkbenchDialog({ open, onOpenChange, title, description, children }) {
  return h(Dialog, { open, onOpenChange },
    h(DialogContent, { className: 'hlx-dialog', showCloseButton: false },
      h(DialogHeader, null, h(DialogTitle, null, title), h(DialogDescription, null, description)),
      children
    )
  )
}

function LatexWorkbench({ ctx }) {
  const gateway = useValue(host.state.gateway)
  const [statusInfo, setStatusInfo] = useState(null)
  const [templates, setTemplates] = useState([])
  const [projects, setProjects] = useState([])
  const [activeProj, setActiveProj] = useState(null)
  const [files, setFiles] = useState([])
  const [structure, setStructure] = useState(null)
  const [activeFile, setActiveFile] = useState('')
  const [code, setCode] = useState('')
  const [dirty, setDirty] = useState(false)
  const [cursorLine, setCursorLine] = useState(1)
  const [editorNavigation, setEditorNavigation] = useState(null)
  const [compactPane, setCompactPane] = useState('editor')
  const [expandedPanes, setExpandedPanes] = useState(() => WORKSPACE_PANES.map(pane => pane.id))
  const paneId = useId()
  const [leftTab, setLeftTab] = useState('files')
  const [rightTab, setRightTab] = useState('chat')
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [materials, setMaterials] = useState([])
  const [selectedMaterials, setSelectedMaterials] = useState([])
  const [selectionText, setSelectionText] = useState('')
  const [materialModal, setMaterialModal] = useState(false)
  const [materialName, setMaterialName] = useState('experiments/benchmark.csv')
  const [materialText, setMaterialText] = useState('')
  const chatMessagesRef = useRef(null)
  const [taskStatus, setTaskStatus] = useState('')
  const [openingFile, setOpeningFile] = useState(false)
  const busy = Boolean(taskStatus || openingFile)
  const [error, setError] = useState('')
  const [compileRes, setCompileRes] = useState(null)
  const [pdfUrl, setPdfUrl] = useState('')
  const [pdfPage, setPdfPage] = useState(1)
  const [syncPoints, setSyncPoints] = useState([])
  const [bibData, setBibData] = useState({ entries: [], issues: [] })
  const [bibQuery, setBibQuery] = useState('')
  const [bibKind, setBibKind] = useState('doi')
  const [bibSearchResults, setBibSearchResults] = useState([])
  const [checkReport, setCheckReport] = useState(null)
  const [snapshots, setSnapshots] = useState([])
  const [diffText, setDiffText] = useState('')

  // Modals
  const [newFilePath, setNewFilePath] = useState(null)
  const [newFileError, setNewFileError] = useState('')
  const newFileInputId = useId()
  const [newModal, setNewModal] = useState(false)
  const [newTitle, setNewTitle] = useState('Scalable Byzantine Consensus for Decentralized Ledgers')
  const [newAuthor, setNewAuthor] = useState('Anonymous Author(s)')
  const [newTemplateId, setNewTemplateId] = useState('ieee-conf')

  // Unified AI Toolbox Modal
  const [toolboxModal, setToolboxModal] = useState(false)
  const [toolboxTab, setToolboxTab] = useState('rewrite')
  const [aiMode, setAiMode] = useState('polish')
  const [aiInput, setAiInput] = useState('')
  const [aiResult, setAiResult] = useState(null)
  const [genKind, setGenKind] = useState('table')
  const [genInput, setGenInput] = useState('Method,TPS,Latency\nPBFT,1420,3.85\nOurs,4860,1.12')
  const [genOutput, setGenOutput] = useState('')

  const editorRef = useRef(null)
  const gutterRef = useRef(null)
  const pdfUrlRef = useRef('')
  const fileRequestRef = useRef(null)

  const cancelFileRead = () => {
    fileRequestRef.current = null
    setOpeningFile(false)
  }

  const setPdfBlob = url => {
    if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current)
    pdfUrlRef.current = url
    setPdfUrl(url)
  }

  useEffect(() => () => {
    fileRequestRef.current = null
    if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current)
  }, [])

  useEffect(() => {
    const messages = chatMessagesRef.current
    if (messages?.clientHeight) messages.scrollTop = messages.scrollHeight
  }, [chatMessages, chatBusy, rightTab, compactPane])

  const runTask = async (label, fn, reportError = setError) => {
    setTaskStatus(label)
    setError('')
    try {
      return await fn()
    } catch (err) {
      reportError(cleanErrorMessage(err))
      return null
    } finally {
      setTaskStatus('')
    }
  }

  const refreshBoot = async () => {
    const [st, tmpl, projs] = await Promise.all([
      ctx.rest('/status'),
      ctx.rest('/templates'),
      ctx.rest('/projects'),
    ])
    setStatusInfo(st)
    setTemplates(tmpl.templates || [])
    setProjects(projs.projects || [])
    const savedId = ctx.storage.get('activeProjectId', null)
    const target = (projs.projects || []).find(p => p.id === savedId) || (projs.projects || [])[0]
    if (target) await openProject(target.id)
  }

  useEffect(() => {
    if (gateway === 'open') void runTask('连接 LaTeX 后端…', refreshBoot)
  }, [gateway])

  const openProject = async projectId => {
    cancelFileRead()
    const res = await ctx.rest(`/projects/${projectId}`)
    if (projectId !== activeProj?.id) {
      setCompileRes(null)
      setCheckReport(null)
      setDiffText('')
      setBibSearchResults([])
      setSelectedMaterials([])
    }
    setActiveProj(res.project)
    setFiles(res.files || [])
    setStructure(res.structure || null)
    ctx.storage.set('activeProjectId', projectId)
    const firstFile = res.project.main_file || res.files?.[0]?.path || ''
    if (firstFile) await openFile(projectId, firstFile)
    else showFile('', '')
    setCompactPane('editor')
    await Promise.all([
      refreshPdf(projectId),
      refreshBib(projectId),
      refreshSnapshots(projectId),
      refreshChatMessages(projectId),
      refreshMaterials(projectId),
    ])
  }

  const refreshChatMessages = async projectId => {
    try {
      const res = await ctx.rest(`/projects/${projectId}/chat/history`)
      setChatMessages(res.messages || [])
    } catch {
      setChatMessages([])
    }
  }

  const refreshMaterials = async projectId => {
    try {
      const res = await ctx.rest(`/projects/${projectId}/materials`)
      setMaterials(res.materials || [])
    } catch {
      setMaterials([])
    }
  }

  const handleSendChat = async promptOverride => {
    const textToSend = (promptOverride || chatInput || '').trim()
    if (!textToSend || !activeProj || chatBusy) return
    setChatBusy(true)
    setError('')
    try {
      const res = await ctx.rest(`/projects/${activeProj.id}/chat`, {
        method: 'POST',
        timeoutMs: 120000,
        body: {
          prompt: textToSend,
          active_file: activeFile || activeProj.main_file,
          cursor_line: cursorLine,
          selection_text: selectionText,
          referenced_materials: selectedMaterials,
          auto_apply: false,
        },
      })
      await refreshChatMessages(activeProj.id)
      setChatInput('')
      if (res.applied) {
        await openProject(activeProj.id)
      }
    } catch (err) {
      setError(cleanErrorMessage(err))
    } finally {
      setChatBusy(false)
    }
  }

  const handleApplyChatPatch = async messageId => {
    if (!activeProj) return
    await runTask('采纳修改并写入工程…', async () => {
      await ctx.rest(`/projects/${activeProj.id}/chat/apply`, {
        method: 'POST',
        body: { message_id: messageId },
      })
      await openProject(activeProj.id)
      await refreshChatMessages(activeProj.id)
      await handleCompile()
    })
  }

  const handleClearChatHistory = async () => {
    if (!activeProj) return
    await runTask('清空对话历史…', async () => {
      await ctx.rest(`/projects/${activeProj.id}/chat/history`, { method: 'DELETE' })
      setChatMessages([])
    })
  }

  const handleSaveMaterial = async () => {
    if (!activeProj || !materialName.trim()) return
    await runTask('保存参考资料…', async () => {
      await ctx.rest(`/projects/${activeProj.id}/materials`, {
        method: 'POST',
        body: { path: materialName.trim(), text_content: materialText },
      })
      await refreshMaterials(activeProj.id)
      setMaterialModal(false)
      setMaterialText('')
    })
  }

  const revealPane = id => {
    setExpandedPanes(panes => panes.includes(id) ? panes : [...panes, id])
    setCompactPane(id)
  }

  const showFile = (relPath, content, jumpLine = null) => {
    setActiveFile(relPath)
    setCode(content)
    setDirty(false)
    setSelectionText('')
    setEditorNavigation({ jumpLine })
  }

  const readFile = async (projectId, relPath) => {
    const res = await ctx.rest(`/projects/${projectId}/file?path=${encodeURIComponent(relPath)}`)
    return res.content || ''
  }

  const openFile = async (projectId, relPath) => {
    cancelFileRead()
    showFile(relPath, await readFile(projectId, relPath))
  }

  const handleOpenFile = async (relPath, jumpLine) => {
    if (!activeProj || taskStatus) return
    revealPane('editor')
    if (relPath === activeFile) {
      cancelFileRead()
      if (jumpLine) setEditorNavigation({ jumpLine })
      return
    }

    const request = {}
    fileRequestRef.current = request
    setOpeningFile(true)
    try {
      const content = await readFile(activeProj.id, relPath)
      if (fileRequestRef.current === request) showFile(relPath, content, jumpLine)
    } catch (err) {
      if (fileRequestRef.current === request) host.notify({ kind: 'error', message: cleanErrorMessage(err) })
    } finally {
      if (fileRequestRef.current === request) cancelFileRead()
    }
  }

  const syncGutter = editor => {
    if (gutterRef.current) gutterRef.current.style.transform = `translateY(${-editor.scrollTop}px)`
  }

  useLayoutEffect(() => {
    const editor = editorRef.current
    if (!editorNavigation || !editor) return
    const lines = editor.value.split('\n')
    const line = Math.min(editorNavigation.jumpLine || 1, lines.length)
    const offset = lines.slice(0, line - 1).reduce((sum, text) => sum + text.length + 1, 0)
    if (editorNavigation.jumpLine) editor.focus({ preventScroll: true })
    editor.setSelectionRange(offset, offset)
    setSelectionText('')
    editor.scrollTop = Math.max(0, (line - 4) * parseFloat(getComputedStyle(editor).lineHeight))
    editor.scrollLeft = 0
    setCursorLine(line)
    syncGutter(editor)
  }, [editorNavigation])

  const handleCreateFile = event => {
    event.preventDefault()
    const path = newFilePath?.trim().replaceAll('\\', '/').split('/').filter(part => part && part !== '.').join('/')
    if (!activeProj || !path || busy) return
    if (files.some(file => file.path.toLowerCase() === path.toLowerCase())) {
      setNewFileError('此路径已有文件，请使用其他文件名。')
      return
    }
    setNewFileError('')
    void runTask('正在创建文件…', async () => {
      const content = '% New section\n'
      const res = await ctx.rest(`/projects/${activeProj.id}/file`, {
        method: 'PUT', body: { path, content, expected_revision: activeProj.revision },
      })
      setActiveProj(res.project)
      setFiles(res.files || [])
      setStructure(res.structure || null)
      setNewFilePath(null)
      if (!dirty) {
        showFile(path, content)
        revealPane('editor')
      }
    }, setNewFileError)
  }

  const saveCurrentFile = async (snapshotLabel = null) => {
    if (!activeProj || !activeFile) return
    const res = await ctx.rest(`/projects/${activeProj.id}/file`, {
      method: 'PUT',
      body: { path: activeFile, content: code, snapshot_label: snapshotLabel },
    })
    setActiveProj(res.project)
    setFiles(res.files || [])
    setStructure(res.structure || null)
    setDirty(false)
  }

  const refreshPdf = async projectId => {
    const res = await ctx.rest(`/projects/${projectId}/pdf`)
    const hasPdf = res.available && res.data
    setPdfBlob(hasPdf ? b64ToBlobUrl(res.data) : '')
    setPdfPage(1)
    setSyncPoints([])
    if (hasPdf && res.synctex_available) {
      const sp = await ctx.rest(`/projects/${projectId}/synctex/page?page=1`)
      setSyncPoints(sp.points || [])
    }
  }

  const refreshBib = async projectId => {
    const res = await ctx.rest(`/projects/${projectId}/bib`)
    setBibData(res)
  }

  const refreshSnapshots = async projectId => {
    const res = await ctx.rest(`/projects/${projectId}/snapshots`)
    setSnapshots(res.snapshots || [])
  }

  const showOutput = tab => {
    setRightTab(tab)
    revealPane('output')
  }

  const handleCompile = async () => {
    if (!activeProj) return
    await runTask('正在编译 LaTeX 工程…', async () => {
      if (dirty) await saveCurrentFile()
      const res = await ctx.rest(`/projects/${activeProj.id}/compile`, {
        method: 'POST',
        body: { engine: activeProj.engine || 'auto' },
        timeoutMs: 180000,
      })
      setCompileRes(res)
      if (res.ok) await refreshPdf(activeProj.id)
      showOutput(res.ok ? 'pdf' : 'diag')
    })
  }

  const handleInstallTectonic = () => runTask('正在下载安装 Tectonic 编译引擎…', async () => {
    await ctx.rest('/compiler/install-tectonic', { method: 'POST', timeoutMs: 120000 })
    const st = await ctx.rest('/status')
    setStatusInfo(st)
  })

  const handleCreateProject = () => runTask('初始化模板工程…', async () => {
    const res = await ctx.rest('/projects', {
      method: 'POST',
      body: { name: newTitle, title: newTitle, author: newAuthor, template_id: newTemplateId },
    })
    setNewModal(false)
    const projs = await ctx.rest('/projects')
    setProjects(projs.projects || [])
    await openProject(res.project.id)
  })

  const handleForwardSync = () => runTask('查找 PDF 位置…', async () => {
    if (!activeProj || !activeFile) return
    const res = await ctx.rest(`/projects/${activeProj.id}/synctex/forward?file=${encodeURIComponent(activeFile)}&line=${cursorLine}`)
    const pt = res.points?.[0]
    if (pt) {
      const sp = await ctx.rest(`/projects/${activeProj.id}/synctex/page?page=${pt.page}`)
      setPdfPage(pt.page)
      setSyncPoints(sp.points || [])
      showOutput('pdf')
    } else {
      throw new Error('当前源码行没有对应的 PDF 定位点。')
    }
  })

  const insertAtCursor = snippet => {
    revealPane('editor')
    const ta = editorRef.current
    if (!ta) {
      setCode(prev => prev + snippet)
      setDirty(true)
      return
    }
    const start = ta.selectionStart ?? code.length
    const end = ta.selectionEnd ?? code.length
    const next = code.slice(0, start) + snippet + code.slice(end)
    setCode(next)
    setDirty(true)
    setTimeout(() => {
      ta.focus()
      ta.setSelectionRange(start + snippet.length, start + snippet.length)
    }, 10)
  }

  const openToolbox = (tab = 'rewrite', prefill = '') => {
    setToolboxTab(tab)
    if (prefill) {
      setAiInput(prefill)
    } else {
      const ta = editorRef.current
      const selected = ta && ta.selectionEnd > ta.selectionStart ? code.slice(ta.selectionStart, ta.selectionEnd) : code
      setAiInput(selected)
    }
    setAiResult(null)
    setToolboxModal(true)
  }

  const runAiRewrite = () => runTask('AI 语法保护改写中…', async () => {
    const res = await ctx.rest(`/projects/${activeProj.id}/ai/rewrite`, {
      method: 'POST',
      body: { text: aiInput, mode: aiMode, filename: activeFile || 'section.tex' },
      timeoutMs: 90000,
    })
    setAiResult(res)
  })

  const applyAiRewrite = () => {
    if (!aiResult?.rewritten_text) return
    if (aiInput === code) {
      setCode(aiResult.rewritten_text)
    } else {
      setCode(prev => prev.replace(aiInput, aiResult.rewritten_text))
    }
    setDirty(true)
    revealPane('editor')
    setToolboxModal(false)
  }

  const runAiHeal = () => runTask('AI 诊断编译错误…', async () => {
    const res = await ctx.rest(`/projects/${activeProj.id}/ai/heal`, {
      method: 'POST',
      body: { apply_patches: true, engine: activeProj.engine || 'auto' },
      timeoutMs: 120000,
    })
    setCompileRes(res.compile)
    if (res.heal?.applied) {
      await openFile(activeProj.id, activeFile)
      await handleCompile()
    }
  })

  const runCheck = () => runTask('执行投稿合规与一致性体检…', async () => {
    if (dirty) await saveCurrentFile()
    const rep = await ctx.rest(`/projects/${activeProj.id}/check`, { method: 'POST', body: {} })
    setCheckReport(rep)
    showOutput('check')
  })

  const handleExportZip = () => runTask('打包干净投稿源码…', async () => {
    const res = await ctx.rest(`/projects/${activeProj.id}/export-zip`, { method: 'POST', body: {} })
    const url = b64ToBlobUrl(res.data, 'application/zip')
    const a = document.createElement('a')
    a.href = url
    a.download = res.filename || 'submission.zip'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 3000)
  })

  const handleBibFetch = () => runTask('检索/导入文献…', async () => {
    const res = await ctx.rest(`/projects/${activeProj.id}/bib/fetch`, {
      method: 'POST',
      body: { kind: bibKind, query: bibQuery, append: bibKind !== 'search' },
    })
    if (bibKind === 'search') {
      setBibSearchResults(res.results || [])
    } else {
      setBibQuery('')
      await refreshBib(activeProj.id)
    }
  })

  const handleGenerateSnippet = () => runTask('生成 LaTeX 代码…', async () => {
    const res = await ctx.rest(`/projects/${activeProj.id}/ai/generate`, {
      method: 'POST',
      body: { kind: genKind, input: genInput },
      timeoutMs: 90000,
    })
    setGenOutput(res.code || '')
  })

  const lineNumbers = useMemo(() => {
    const count = Math.max(1, code.split('\n').length)
    return Array.from({ length: count }, (_, i) => i + 1).join('\n')
  }, [code])

  const compilerReady = statusInfo?.compiler?.ready
  const diagCount = (compileRes?.errors?.length || 0) + (compileRes?.warnings?.length || 0) + (compileRes?.overfulls?.length || 0)
  const visiblePanes = WORKSPACE_PANES.filter(pane => expandedPanes.includes(pane.id))
  const columns = visiblePanes.length > 1 ? visiblePanes.map(pane => pane.track).join(' ') : 'minmax(0, 1fr)'
  const paneProps = id => ({
    id: `${paneId}-${id}`,
    'data-collapsed': expandedPanes.includes(id) ? undefined : true,
    'data-compact-active': compactPane === id || undefined,
  })

  return h('section', { className: 'hlx-root', 'aria-label': 'LaTeX 论文工坊' },
    h('style', null, CSS),

    // Reorganized Toolbar with 3 clear zones
    h('header', { className: 'hlx-toolbar' },
      // Zone 1: Project Management
      h('div', { className: 'hlx-tb-group' },
        h('div', { className: 'hlx-brand' },
          h('div', { className: 'hlx-brand-icon' }, 'TeX'),
          h('span', null, 'LaTeX 工坊')
        ),
        h('select', {
          className: 'hlx-select hlx-project-select',
          'aria-label': '论文工程',
          title: activeProj?.name,
          disabled: !!busy || !projects.length,
          value: activeProj?.id || '',
          onChange: e => e.target.value && void runTask('切换项目…', () => openProject(e.target.value)),
        },
          h('option', { value: '' }, projects.length ? '切换论文工程…' : '暂无工程，请新建'),
          ...projects.map(p => h('option', { key: p.id, value: p.id }, `${p.name} [${p.template_id}]`))
        ),
        h(Button, { size: 'sm', variant: 'secondary', disabled: !templates.length || !!busy, onClick: () => setNewModal(true) }, '＋ 新建论文')
      ),

      // Zone 2: Build & Status
      activeProj && h('div', { className: 'hlx-tb-group' },
        h(Button, {
          size: 'sm',
          variant: 'default',
          disabled: !!busy,
          onClick: () => void handleCompile(),
        }, '编译预览'),

        h(Button, {
          size: 'sm',
          variant: 'secondary',
          disabled: !dirty || !!busy,
          onClick: () => void runTask('保存中…', () => saveCurrentFile()),
        }, h('span', { className: 'hlx-save-label' }, dirty ? '保存更改' : '已保存')),

        compileRes?.page_count > 0 && h(Badge, { variant: 'secondary' },
          `${compileRes.page_count}${activeProj.page_limit ? '/' + activeProj.page_limit : ''} 页 · ${compileRes.engine_used}`
        )
      ),

      // Zone 3: AI Copilot & Quality Tools
      activeProj && h('div', { className: 'hlx-tb-group' },
        h(Button, {
          size: 'sm',
          variant: 'ghost',
          onClick: () => showOutput('chat'),
        }, 'AI 伴写'),

        h(Button, {
          size: 'sm',
          variant: 'ghost',
          onClick: () => openToolbox('rewrite'),
        }, 'AI 工具箱'),

        h(Button, {
          size: 'sm',
          variant: 'ghost',
          disabled: !!busy,
          onClick: () => void runCheck(),
        }, '投稿体检'),

        h(Button, {
          size: 'sm',
          variant: 'ghost',
          disabled: !!busy,
          onClick: () => void handleExportZip(),
        }, '导出源码包')
      )
    ),

    taskStatus && h('div', { className: 'hlx-status', role: 'status' }, taskStatus),

    // Compiler status banner when no local TeX distro
    statusInfo && !compilerReady && h('div', { className: 'hlx-banner' },
      h('span', null, '未检测到 LaTeX 编译器。安装 Tectonic 后即可预览 PDF。'),
      h(Button, { size: 'sm', disabled: !!busy, onClick: () => void handleInstallTectonic() }, '安装 Tectonic')
    ),

    // Error banner with clean friendly message
    error && h('div', { className: 'hlx-error-bar', role: 'alert' },
      h('span', null, error),
      h('div', { className: 'hlx-action-row' },
        !statusInfo && h(Button, { size: 'xs', variant: 'secondary', disabled: !!busy, onClick: () => void runTask('重新连接后端…', refreshBoot) }, '重试连接'),
        h(Button, { size: 'icon-xs', variant: 'ghost', 'aria-label': '关闭提示', onClick: () => setError('') }, '✕')
      )
    ),

    activeProj && h(WorkspacePaneControls, {
      paneId,
      isExpanded: pane => expandedPanes.includes(pane),
      onToggle: pane => setExpandedPanes(current => current.includes(pane)
        ? current.filter(id => id !== pane)
        : [...current, pane]),
    }),
    activeProj && h(WorkspacePaneControls, {
      paneId, compact: true,
      isExpanded: pane => compactPane === pane,
      onToggle: pane => setCompactPane(current => current === pane ? null : pane),
    }),

    // Main 3-pane workbench
    !activeProj ? h('div', { className: 'hlx-empty' },
      statusInfo ? h('h2', { style: { margin: 0, fontSize: 18, fontWeight: 650 } }, projects.length ? '选择论文工程' : '从模板开始写论文') : null,
      statusInfo && !projects.length && h('p', { style: { color: 'var(--ui-text-secondary)', margin: 0 } }, '选择 IEEE、ACM、NeurIPS 等学术模板开始编辑。'),
      statusInfo && !projects.length && h(Button, { disabled: !templates.length || !!busy, onClick: () => setNewModal(true) }, '从模板新建论文'),
      !statusInfo && !busy && !error && h('span', { role: 'status' }, '正在等待 LaTeX 后端连接…')
    ) : h('div', { className: 'hlx-main', style: { '--hlx-columns': columns } },
      // Left Sidebar: Files / Outline / BibTeX / Materials
      h('aside', { ...paneProps('files'), className: 'hlx-left', 'aria-label': '工程' },
        h(WorkbenchTabs, { label: '工程资源', value: leftTab, onChange: setLeftTab, items: [
          { id: 'files', label: '文件' },
          { id: 'outline', label: '大纲' },
          { id: 'bib', label: `文献 (${bibData.entries?.length || 0})` },
          { id: 'materials', label: `资料 (${materials.length})` },
        ] }),

        // Files tab
        leftTab === 'files' && h('div', { className: 'hlx-scroll' },
          h('div', { className: 'hlx-action-row', style: { marginBottom: 10 } },
            h(Button, {
              size: 'xs', variant: 'secondary', disabled: !!busy, onClick: () => {
                setNewFileError('')
                setNewFilePath('')
              },
            }, '＋ 新建文件'),
            h(Button, { size: 'xs', variant: 'secondary', asChild: true }, h('label', { className: 'hlx-upload' },
              '上传插图',
              h('input', {
                type: 'file', className: 'sr-only', accept: '.png,.jpg,.jpeg,.pdf,.eps',
                onChange: e => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  e.target.value = ''
                  void runTask('上传图片…', async () => {
                    const b64 = await readFileAsBase64(f)
                    const res = await ctx.rest(`/projects/${activeProj.id}/upload-asset`, {
                      method: 'POST', body: { path: `figures/${f.name}`, data_base64: b64 },
                    })
                    setFiles(res.files || [])
                  })
                },
              })
            ))
          ),
          ...files.map(f =>
            h(f.is_binary ? 'div' : 'button', {
              type: f.is_binary ? undefined : 'button',
              disabled: f.is_binary ? undefined : Boolean(taskStatus),
              key: f.path,
              title: f.path,
              'aria-current': activeFile === f.path ? 'true' : undefined,
              className: `hlx-item ${activeFile === f.path ? 'hlx-item-active' : ''}`,
              onClick: f.is_binary ? undefined : () => void handleOpenFile(f.path),
            },
              h('span', { className: 'hlx-file-label' },
                h(Codicon, { size: 13, name: f.kind === 'bib' ? 'book' : f.kind === 'image' ? 'file-media' : 'file-code' }),
                h('span', { className: 'hlx-truncate' }, f.path)
              ),
              f.path === activeProj.main_file && h('span', { className: 'hlx-badge hlx-badge-accent' }, '主文件')
            )
          )
        ),

        // Outline tab
        leftTab === 'outline' && h('div', { className: 'hlx-scroll' },
          !(structure?.outline?.length) ? h('div', { style: { padding: 12, color: 'var(--ui-text-secondary)', fontSize: 12 } }, '未检测到大纲结构，请检查 \\section 指令。') : (structure?.outline || []).map(node =>
            h('button', {
              type: 'button',
              disabled: Boolean(taskStatus),
              key: node.id,
              className: 'hlx-item',
              title: node.title,
              style: { paddingLeft: 8 + node.level * 10 },
              onClick: () => void handleOpenFile(node.file, node.line),
            },
              h('span', { className: 'hlx-truncate' }, node.title),
              h('span', { style: { fontSize: 10.5, color: 'var(--ui-text-tertiary)' } }, `L${node.line}`)
            )
          )
        ),

        // Bib tab
        leftTab === 'bib' && h('div', { className: 'hlx-scroll' },
          h('div', { style: { display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 } },
            h('select', { className: 'hlx-select', value: bibKind, onChange: e => setBibKind(e.target.value) },
              h('option', { value: 'doi' }, '按 DOI 自动导入'),
              h('option', { value: 'arxiv' }, '按 arXiv ID 导入'),
              h('option', { value: 'search' }, '关键词检索 Crossref')
            ),
            h('div', { style: { display: 'flex', gap: 6 } },
              h(Input, {
                value: bibQuery,
                onChange: e => setBibQuery(e.target.value),
                placeholder: bibKind === 'search' ? '关键词 (如 consensus)...' : '10.1109/... 或 2401.00001',
                style: { flex: 1, minWidth: 0 },
              }),
              h(Button, { size: 'sm', variant: 'default', onClick: () => void handleBibFetch() }, '导入')
            ),
            h(Button, {
              size: 'xs', variant: 'secondary', onClick: () => void runTask('BibTeX 去重格式化…', async () => {
                await ctx.rest(`/projects/${activeProj.id}/bib/dedup`, { method: 'POST' })
                await refreshBib(activeProj.id)
              })
            }, '去重并格式化 refs.bib')
          ),
          ...bibSearchResults.map((r, i) =>
            h('div', { key: i, className: 'hlx-card' },
              h('div', { style: { fontWeight: 600, fontSize: 12 } }, r.title),
              h('div', { style: { fontSize: 11, color: 'var(--ui-text-secondary)' } }, `${(r.authors || []).slice(0, 2).join(', ')} (${r.year})`),
              r.doi && h(Button, {
                size: 'xs', variant: 'secondary', onClick: () => void runTask('导入 DOI…', async () => {
                  await ctx.rest(`/projects/${activeProj.id}/bib/fetch`, { method: 'POST', body: { kind: 'doi', query: r.doi, append: true } })
                  await refreshBib(activeProj.id)
                })
              }, '＋ 加入 refs.bib')
            )
          ),
          ...(bibData.entries || []).map(e =>
            h('div', { key: e.key, className: 'hlx-card' },
              h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
                h('code', { style: { fontSize: 11.5, fontWeight: 700 } }, e.key),
                h(Button, { size: 'xs', variant: 'secondary', onClick: () => insertAtCursor(`~\\cite{${e.key}}`) }, '引用')
              ),
              h('div', { style: { fontSize: 11.5, color: 'var(--ui-text-secondary)', lineHeight: 1.4 } }, e.fields?.title || '')
            )
          )
        ),

        // Materials tab
        leftTab === 'materials' && h('div', { className: 'hlx-scroll' },
          h('div', { className: 'hlx-action-row', style: { justifyContent: 'space-between', marginBottom: 10 } },
            h('span', { style: { fontWeight: 600, fontSize: 12 } }, '研究资料'),
            h(Button, { size: 'xs', variant: 'default', onClick: () => setMaterialModal(true) }, '＋ 添加资料')
          ),
          h('div', { style: { fontSize: 11.5, color: 'var(--ui-text-secondary)', marginBottom: 8, lineHeight: 1.5 } },
            '勾选要在伴写中引用的资料。'
          ),
          !materials.length ? h('div', { style: { fontSize: 12, color: 'var(--ui-text-secondary)', padding: 12, textAlign: 'center' } },
            '暂无参考资料。点击上方【＋ 添加资料】导入 CSV 数据或架构提纲。'
          ) : materials.map(m => {
            const isChecked = selectedMaterials.includes(m.path)
            return h('div', {
              key: m.path,
              className: `hlx-item ${isChecked ? 'hlx-item-active' : ''}`,
              onClick: () => {
                setSelectedMaterials(prev => isChecked ? prev.filter(p => p !== m.path) : [...prev, m.path])
              },
            },
              h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' } },
                h('span', { className: 'hlx-truncate', title: m.path },
                  `${isChecked ? '☑ ' : '☐ '}📊 ${m.path.replace(/^materials\//, '')}`
                ),
                h('span', { style: { fontSize: 10.5, color: 'var(--ui-text-tertiary)' } }, `${Math.round(m.size / 1024 * 10) / 10}KB`)
              )
            )
          })
        )
      ),

      // Center Pane: Editor
      h('section', { ...paneProps('editor'), className: 'hlx-center', 'aria-label': '源码编辑', 'aria-busy': openingFile || undefined },
        h('div', { className: 'hlx-editor-bar' },
          h('div', { className: 'hlx-action-row hlx-editor-name' },
            h('span', { className: 'hlx-badge hlx-truncate', title: activeFile }, activeFile || '未打开文件'),
            h('span', { style: { fontSize: 11, color: 'var(--ui-text-tertiary)' } }, openingFile ? '打开中…' : `行 ${cursorLine}`)
          ),
          h('div', { className: 'hlx-action-row' },
            h(Button, { size: 'xs', variant: 'secondary', disabled: !pdfUrl || !!busy, onClick: () => void handleForwardSync() }, '定位到 PDF'),
            ...SNIPPETS.map(s => h(Button, { key: s.label, size: 'xs', variant: 'secondary', disabled: !activeFile, onClick: () => insertAtCursor(s.code) }, `+ ${s.label}`)),
            structure?.labels?.length > 0 && h('select', {
              className: 'hlx-select hlx-reference-select',
              'aria-label': '插入交叉引用',
              value: '',
              onChange: e => { if (e.target.value) insertAtCursor(`\\ref{${e.target.value}}`) },
            },
              h('option', { value: '' }, '引用 \\ref{…}'),
              ...structure.labels.map(l => h('option', { key: `${l.file}:${l.line}:${l.key}`, value: l.key }, l.key))
            )
          )
        ),

        // Context selection bar (shows up when text is highlighted)
        selectionText && h('div', { className: 'hlx-selection-bar' },
          h('span', { style: { color: 'var(--ui-text-primary)', fontWeight: 600 } },
            `已圈选 ${selectionText.split('\n').length} 行（${selectionText.length} 字符）`
          ),
          h('div', { className: 'hlx-action-row' },
            h(Button, {
              size: 'xs', variant: 'secondary', onClick: () => {
                showOutput('chat')
                setChatInput(`请针对我圈选的这部分内容进行深入润色与修改，要求：\n`)
              }
            }, '发送至 AI 伴写'),
            h(Button, {
              size: 'xs', variant: 'default', onClick: () => openToolbox('rewrite', selectionText)
            }, '语法保护改写'),
            h('button', {
              style: { border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--ui-text-tertiary)', fontSize: 12 },
              onClick: () => setSelectionText('')
            }, '✕ 取消')
          )
        ),

        h('div', { className: 'hlx-editor-wrap' },
          h('div', { className: 'hlx-gutter', 'aria-hidden': true }, h('pre', { ref: gutterRef }, lineNumbers)),
          h('textarea', {
            ref: editorRef,
            className: 'hlx-textarea',
            'aria-label': 'LaTeX 源码',
            value: code,
            disabled: !activeFile,
            wrap: 'off',
            spellCheck: false,
            onScroll: e => syncGutter(e.currentTarget),
            onSelect: e => {
              const s = e.target.selectionStart
              const end = e.target.selectionEnd
              setSelectionText(s !== end ? e.target.value.substring(s, end) : '')
            },
            onClick: e => setCursorLine(e.target.value.slice(0, e.target.selectionStart).split('\n').length),
            onKeyUp: e => setCursorLine(e.target.value.slice(0, e.target.selectionStart).split('\n').length),
            onKeyDown: e => {
              if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                e.preventDefault()
                if (dirty && !busy) void runTask('保存文件…', () => saveCurrentFile())
              }
            },
            onChange: e => { setCode(e.target.value); setDirty(true) },
          })
        )
      ),

      // Right Pane: Dual-mode Preview / AI Copilot Hub
      h('section', { ...paneProps('output'), className: 'hlx-right', 'aria-label': '预览与工具' },
        h(WorkbenchTabs, { label: '工具视图', value: rightTab, onChange: setRightTab, items: [
          { id: 'chat', label: `AI 伴写 (${chatMessages.length})` },
          { id: 'pdf', label: 'PDF 预览' },
          { id: 'diag', label: `编译诊断 (${diagCount})` },
          { id: 'check', label: '投稿体检' },
          { id: 'snaps', label: `快照 (${snapshots.length})` },
        ] }),

        // AI Chat tab
        rightTab === 'chat' && h('div', { className: 'hlx-chat-container' },
          h('div', { className: 'hlx-chat-header' },
            h('div', { className: 'hlx-action-row hlx-chat-context' },
              h('span', { style: { fontWeight: 600, color: 'var(--ui-text-secondary)' } }, '当前文件'),
              h('span', { className: 'hlx-badge hlx-truncate hlx-chat-filename', title: activeFile }, activeFile || '未打开文件'),
              selectionText ? h('span', { className: 'hlx-badge hlx-badge-accent' }, `圈选 ${selectionText.split('\n').length} 行`) : null,
              selectedMaterials.length > 0 ? h('span', { className: 'hlx-badge hlx-badge-success' }, `引用 ${selectedMaterials.length} 篇资料`) : null,
            ),
            h(Button, { size: 'xs', variant: 'ghost', onClick: () => void handleClearChatHistory() }, '清空记录')
          ),

          h('div', { ref: chatMessagesRef, className: 'hlx-chat-messages' },
            chatMessages.length === 0 && h('div', { className: 'hlx-chat-welcome' },
              h('p', null, '描述要修改的内容，或选一个常用任务。写入源码前可先审阅差异。'),
              h('div', { className: 'hlx-action-row' },
                [
                  ['补充实验评估', '结合研究材料补充实验评估章节与对比分析'],
                  ['润色选段', '对当前圈选内容进行深度学术润色并消除 AI 腔'],
                  ['梳理论文贡献', '为引言部分梳理 3 点突出的研究贡献 (Contributions)'],
                  ['精简篇幅', '精简本节表述，消除多余冗余词句，控制篇幅']
                ].map(([label, prompt]) =>
                  h('button', {
                    key: label,
                    className: 'hlx-prompt-chip',
                    onClick: () => { setChatInput(prompt) }
                  }, label)
                )
              )
            ),

            ...chatMessages.map(msg =>
              h('div', { key: msg.id, className: `hlx-chat-row ${msg.role === 'user' ? 'hlx-chat-row-user' : 'hlx-chat-row-assistant'}` },
                h('div', { className: `hlx-chat-bubble ${msg.role === 'user' ? 'hlx-chat-bubble-user' : 'hlx-chat-bubble-assistant'}` },
                  h('div', { style: { whiteSpace: 'pre-wrap', lineHeight: 1.55 } }, msg.text),
                  (msg.attachments?.materials?.length > 0 || msg.attachments?.active_file) && h('div', { style: { display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' } },
                    msg.attachments?.active_file && h('span', { className: 'hlx-badge', style: { fontSize: 10 } }, `📄 ${msg.attachments.active_file}`),
                    ...(msg.attachments?.materials || []).map(m => h('span', { key: m, className: 'hlx-badge', style: { fontSize: 10 } }, `📎 ${m.replace(/^materials\//, '')}`))
                  ),
                  msg.patches?.length > 0 && h('div', { className: 'hlx-patch-box' },
                    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 } },
                      h('strong', { style: { fontSize: 12, color: 'var(--ui-text-primary)' } }, `📝 建议修改清单 (${msg.patches.length} 处变更)`),
                      msg.applied
                        ? h('span', { className: 'hlx-badge hlx-badge-success' }, '已采纳写入工程')
                        : h(Button, { size: 'xs', variant: 'default', onClick: () => void handleApplyChatPatch(msg.id) }, '采纳并写入工程')
                    ),
                    msg.diff && h('pre', { className: 'hlx-diff', style: { maxHeight: 180, margin: '6px 0 0 0' } }, msg.diff)
                  )
                )
              )
            ),
            chatBusy && h('div', { className: 'hlx-card', role: 'status' }, '正在生成修改建议…')
          ),

          // Chat Input bar
          h('div', { className: 'hlx-chat-input-bar' },
            materials.length > 0 && h('div', { className: 'hlx-chat-materials-select' },
              h('span', { style: { fontSize: 11, fontWeight: 600, color: 'var(--ui-text-secondary)' } }, '引用资料'),
              ...materials.map(m => {
                const p = m.path || m.rel_path || ''
                return h('label', { key: p, className: 'hlx-mat-label' },
                  h('input', {
                    type: 'checkbox',
                    checked: selectedMaterials.includes(p),
                    onChange: e => {
                      if (e.target.checked) setSelectedMaterials([...selectedMaterials, p])
                      else setSelectedMaterials(selectedMaterials.filter(x => x !== p))
                    }
                  }),
                  h('span', { style: { fontSize: 11 } }, p.replace(/^materials\//, ''))
                )
              })
            ),
            h('div', { style: { display: 'flex', gap: 8, alignItems: 'flex-end' } },
              h('textarea', {
                className: 'hlx-chat-textarea',
                'aria-label': '论文伴写要求',
                placeholder: '输入修改要求，Ctrl + Enter 发送',
                rows: 2,
                value: chatInput,
                onChange: e => setChatInput(e.target.value),
                onKeyDown: e => {
                  if (!e.nativeEvent.isComposing && (e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault()
                    void handleSendChat()
                  }
                }
              }),
              h(Button, {
                size: 'sm',
                variant: 'default',
                disabled: chatBusy || !chatInput.trim(),
                onClick: () => void handleSendChat()
              }, chatBusy ? '生成中…' : '发送要求')
            )
          )
        ),

        // PDF Preview tab
        rightTab === 'pdf' && h('div', { style: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 } },
          pdfUrl ? h('div', { style: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 } },
            h('iframe', { key: `${pdfUrl}#page=${pdfPage}`, src: `${pdfUrl}#page=${pdfPage}`, className: 'hlx-pdf-frame', title: 'LaTeX PDF Preview' }),
            syncPoints.length > 0 && h('div', { style: { maxHeight: 110, overflowY: 'auto', padding: '8px 12px', borderTop: '1px solid var(--ui-stroke-tertiary)', fontSize: 11.5 } },
              h('div', { style: { fontWeight: 600, marginBottom: 4 } }, `第 ${pdfPage} 页 SyncTeX 反向定位锚点（点击跳转回源码）:`),
              h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 4 } },
                ...syncPoints.slice(0, 24).map((sp, i) =>
                  h('button', {
                    key: i,
                    style: { fontSize: 11, padding: '3px 8px', borderRadius: 6, border: '1px solid var(--ui-stroke-secondary)', background: 'var(--ui-bg-elevated)', cursor: 'pointer', color: 'var(--ui-text-primary)' },
                    onClick: () => void handleOpenFile(sp.file, sp.line),
                  }, `${sp.file}:${sp.line}`)
                )
              )
            )
          ) : h('div', { style: { padding: 32, textAlign: 'center', color: 'var(--ui-text-secondary)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 } },
            h(Codicon, { name: 'file-pdf', size: 26 }),
            h('div', { style: { fontSize: 14, fontWeight: 600 } }, '尚未生成 PDF 预览'),
            h(Button, { size: 'sm', disabled: !!busy, onClick: () => void handleCompile() }, '编译 PDF')
          )
        ),

        // Diagnostics tab
        rightTab === 'diag' && h('div', { className: 'hlx-scroll' },
          compileRes?.errors?.length > 0 && h('div', { style: { marginBottom: 12 } },
            h(Button, { size: 'sm', disabled: !!busy, onClick: () => void runAiHeal() }, 'AI 修复编译错误')
          ),
          !compileRes && h('p', null, '编译后可在这里查看错误和警告。'),
          compileRes?.ok && diagCount === 0 && h('p', null, '编译成功。'),
          compileRes && !compileRes.ok && h('p', null, compileRes.hint || '编译失败，请查看下方诊断。'),
          ...(compileRes?.errors || []).map((d, i) =>
            h('div', { key: `e-${i}`, className: 'hlx-card', onClick: () => d.line && void handleOpenFile(d.file, d.line) },
              h('strong', { style: { color: 'var(--ui-red)' } }, `ERROR · ${d.file}${d.line ? ':' + d.line : ''}`),
              h('div', null, d.message),
              d.snippet && h('code', { style: { fontSize: 11, background: 'var(--ui-diff-remove-background)', padding: '2px 4px', borderRadius: 'var(--radius-sm, 6px)' } }, d.snippet)
            )
          ),
          ...(compileRes?.overfulls || []).map((d, i) =>
            h('div', { key: `o-${i}`, className: 'hlx-card' },
              h('strong', { style: { color: 'var(--ui-yellow)' } }, `OVERFULL · ${d.file}${d.line ? ':' + d.line : ''}`),
              h('div', null, d.message)
            )
          ),
          ...(compileRes?.warnings || []).map((d, i) =>
            h('div', { key: `w-${i}`, className: 'hlx-card' },
              h('strong', null, `WARNING · ${d.file}${d.line ? ':' + d.line : ''}`),
              h('div', null, d.message)
            )
          )
        ),

        // Preflight Check tab
        rightTab === 'check' && h('div', { className: 'hlx-scroll' },
          !checkReport ? h('div', { style: { padding: 24, textAlign: 'center', color: 'var(--ui-text-secondary)' } },
            h('div', { style: { fontSize: 28, marginBottom: 8 } }, '🛡'),
            h('div', null, '点击顶部【🛡 投稿体检】运行引用一致性、双盲匿名与篇幅统计检查。')
          ) : h('div', null,
            h('div', { className: 'hlx-card', style: { background: 'var(--ui-bg-elevated)' } },
              h('div', { style: { fontWeight: 600, fontSize: 13 } }, '📊 篇幅与合规概览'),
              h('div', { style: { fontSize: 12 } }, `词数统计：英文 ${checkReport.word_count?.en_words || 0} 词 / 中文 ${checkReport.word_count?.cjk_chars || 0} 字`),
              h('div', { style: { fontSize: 12, display: 'flex', gap: 6, marginTop: 4 } },
                h('span', { className: 'hlx-badge', style: { color: 'var(--ui-red)' } }, `错误 ${checkReport.summary?.errors || 0}`),
                h('span', { className: 'hlx-badge', style: { color: 'var(--ui-yellow)' } }, `警告 ${checkReport.summary?.warnings || 0}`),
                h('span', { className: 'hlx-badge' }, `提示 ${checkReport.summary?.infos || 0}`)
              )
            ),
            ...(checkReport.issues || []).map((it, i) =>
              h('div', { key: i, className: 'hlx-card', onClick: () => it.line && void handleOpenFile(it.file, it.line) },
                h('strong', { style: { color: it.severity === 'error' ? 'var(--ui-red)' : it.severity === 'warning' ? 'var(--ui-yellow)' : 'var(--ui-text-primary)' } },
                  `[${it.category}] ${it.title}`
                ),
                h('div', { style: { fontSize: 12 } }, it.detail),
                it.suggestion && h('div', { style: { fontSize: 11.5, color: 'var(--ui-text-secondary)' } }, `建议：${it.suggestion}`)
              )
            )
          )
        ),

        // Snapshots tab
        rightTab === 'snaps' && h('div', { className: 'hlx-scroll' },
          h(Button, {
            size: 'sm', variant: 'secondary', style: { marginBottom: 10, width: '100%', borderRadius: 8 }, onClick: () => void runTask('创建快照…', async () => {
              await ctx.rest(`/projects/${activeProj.id}/snapshots`, { method: 'POST', body: { label: '手动快照' } })
              await refreshSnapshots(activeProj.id)
            })
          }, '＋ 创建当前快照'),
          ...snapshots.map(s =>
            h('div', { key: s.id, className: 'hlx-card' },
              h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
                h('strong', null, `r${s.revision} · ${s.label}`),
                h('div', { style: { display: 'flex', gap: 6 } },
                  h(Button, {
                    size: 'xs', variant: 'secondary', onClick: () => void runTask('对比差异…', async () => {
                      const d = await ctx.rest(`/projects/${activeProj.id}/snapshots/diff?from_id=${encodeURIComponent(s.id)}`)
                      setDiffText((d.changes || []).map(c => c.diff).join('\n') || '与当前工作区完全一致')
                    })
                  }, 'Diff'),
                  h(Button, {
                    size: 'xs', variant: 'secondary', onClick: () => void runTask('恢复快照…', async () => {
                      await ctx.rest(`/projects/${activeProj.id}/snapshots/${s.id}/restore`, { method: 'POST' })
                      await openProject(activeProj.id)
                    })
                  }, '恢复')
                )
              ),
              h('div', { style: { fontSize: 11, color: 'var(--ui-text-tertiary)' } }, s.created_at)
            )
          ),
          diffText && h('pre', { className: 'hlx-diff' }, diffText)
        )
      )
    ),

    h(Dialog, { open: newFilePath !== null, onOpenChange: open => { if (!open && !busy) setNewFilePath(null) } },
      h(DialogContent, null,
        h(DialogHeader, null,
          h(DialogTitle, null, '新建文件'),
          h(DialogDescription, null, '路径相对于当前论文工程。')
        ),
        h('form', { className: 'hlx-file-form', onSubmit: handleCreateFile },
          h('label', { htmlFor: newFileInputId }, '文件路径'),
          h(Input, {
            id: newFileInputId,
            'aria-invalid': !!newFileError || undefined,
            'aria-describedby': newFileError ? `${newFileInputId}-error` : undefined,
            value: newFilePath || '',
            onChange: e => { setNewFilePath(e.target.value); setNewFileError('') },
            placeholder: 'sections/06_appendix.tex',
            disabled: !!busy,
          }),
          newFileError && h('p', { id: `${newFileInputId}-error`, className: 'hlx-file-form-error', role: 'alert' }, newFileError),
          h(DialogFooter, null,
            h(Button, { type: 'button', variant: 'secondary', disabled: !!busy, onClick: () => setNewFilePath(null) }, '取消'),
            h(Button, { type: 'submit', disabled: !newFilePath?.trim() || !!busy, loading: taskStatus === '正在创建文件…' }, '创建文件')
          )
        )
      )
    ),

    h(WorkbenchDialog, {
      open: newModal, onOpenChange: setNewModal,
      title: '从学术模板新建论文工程', description: '填写标题和作者，然后选择论文模板。',
    },
      h(Input, { 'aria-label': '论文标题', value: newTitle, onChange: e => setNewTitle(e.target.value), placeholder: '论文标题' }),
      h(Input, { 'aria-label': '作者', value: newAuthor, onChange: e => setNewAuthor(e.target.value), placeholder: '作者（双盲评审可保留匿名）' }),
      h('div', { className: 'hlx-tmpl-grid' },
        templates.map(t =>
          h('button', {
            type: 'button',
            key: t.id,
            className: `hlx-tmpl-card ${newTemplateId === t.id ? 'hlx-tmpl-card-active' : ''}`,
            'aria-pressed': newTemplateId === t.id,
            onClick: () => setNewTemplateId(t.id),
          },
            h('strong', { style: { fontSize: 12.5 } }, t.name),
            h('span', { style: { fontSize: 11, color: 'var(--ui-text-secondary)', lineHeight: 1.4 } }, t.description)
          )
        )
      ),
      h(DialogFooter, null,
        h(Button, { size: 'sm', variant: 'secondary', onClick: () => setNewModal(false) }, '取消'),
        h(Button, { size: 'sm', disabled: !newTitle.trim() || !!busy, onClick: () => void handleCreateProject() }, '创建工程')
      )
    ),

    h(WorkbenchDialog, {
      open: toolboxModal, onOpenChange: setToolboxModal,
      title: 'AI 论文创作工具箱', description: '改写时保留 LaTeX 引用、交叉引用和公式。',
    },
      h(WorkbenchTabs, { label: 'AI 工具箱', value: toolboxTab, onChange: setToolboxTab, items: [
        { id: 'rewrite', label: '学术改写与压页' },
        { id: 'generate', label: '三线表 / 公式 / TikZ' },
      ] }),

      toolboxTab === 'rewrite' && h('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
        h('label', { className: 'hlx-action-row' },
          h('span', { style: { fontSize: 12, fontWeight: 600 } }, '改写模式'),
          h('select', { className: 'hlx-select', value: aiMode, onChange: e => setAiMode(e.target.value) },
            h('option', { value: 'polish' }, '学术润色'),
            h('option', { value: 'zh2en' }, '中译英'),
            h('option', { value: 'en2zh' }, '英译中'),
            h('option', { value: 'compress' }, '精简篇幅'),
            h('option', { value: 'deai' }, '去除 AI 腔调'),
            h('option', { value: 'expand' }, '扩展论述')
          )
        ),
        h(Textarea, {
          rows: 6,
          value: aiInput,
          onChange: e => setAiInput(e.target.value),
          placeholder: '输入要改写的 LaTeX 正文…',
        }),
        aiResult && h('div', null,
          h('div', { style: { fontSize: 12, marginBottom: 6, color: aiResult.integrity_ok ? 'var(--ui-green)' : 'var(--ui-red)', fontWeight: 600 } },
            aiResult.integrity_ok
              ? `已保留 ${aiResult.preserved_tokens} 个 LaTeX 指令和公式标记`
              : `完整性检查提示 ${(aiResult.integrity_errors || []).join('，')}`
          ),
          h('pre', { className: 'hlx-diff' }, aiResult.diff || aiResult.rewritten_text)
        ),
        h(DialogFooter, null,
          h(Button, { size: 'sm', variant: 'secondary', onClick: () => setToolboxModal(false) }, '关闭'),
          h(Button, { size: 'sm', disabled: !!busy, onClick: () => void runAiRewrite() }, '生成改写 Diff'),
          aiResult && h(Button, { size: 'sm', onClick: applyAiRewrite }, '采纳到编辑器')
        )
      ),

      toolboxTab === 'generate' && h('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
        h('label', { className: 'hlx-action-row' },
          h('span', { style: { fontSize: 12, fontWeight: 600 } }, '生成类型'),
          h('select', { className: 'hlx-select', value: genKind, onChange: e => setGenKind(e.target.value) },
            h('option', { value: 'table' }, 'CSV / Markdown → booktabs 三线表'),
            h('option', { value: 'formula' }, '自然语言 → LaTeX 数学公式'),
            h('option', { value: 'tikz' }, '文本描述 → TikZ 架构图或流程图'),
            h('option', { value: 'algorithm' }, '伪代码 → algorithm2e 算法块')
          )
        ),
        h(Textarea, {
          rows: 5,
          value: genInput,
          onChange: e => setGenInput(e.target.value),
          placeholder: '输入 CSV 数据、公式描述或算法逻辑…',
        }),
        genOutput && h('pre', { className: 'hlx-diff' }, genOutput),
        h(DialogFooter, null,
          h(Button, { size: 'sm', variant: 'secondary', onClick: () => setToolboxModal(false) }, '关闭'),
          h(Button, { size: 'sm', disabled: !!busy, onClick: () => void handleGenerateSnippet() }, '生成代码'),
          genOutput && h(Button, { size: 'sm', onClick: () => { insertAtCursor('\n' + genOutput + '\n'); setToolboxModal(false) } }, '插入当前光标')
        )
      )
    ),

    h(WorkbenchDialog, {
      open: materialModal, onOpenChange: setMaterialModal,
      title: '添加研究资料', description: '将资料保存到工程的 materials/ 目录，供伴写时引用。',
    },
      h(Input, {
        'aria-label': '资料路径',
        value: materialName,
        onChange: e => setMaterialName(e.target.value),
        placeholder: '例如 experiments/benchmark.csv',
      }),
      h(Textarea, {
        'aria-label': '资料正文',
        rows: 8,
        value: materialText,
        onChange: e => setMaterialText(e.target.value),
        placeholder: '粘贴实验数据、提纲或审稿意见…',
      }),
      h(DialogFooter, null,
        h(Button, { size: 'sm', variant: 'secondary', onClick: () => setMaterialModal(false) }, '取消'),
        h(Button, {
          size: 'sm',
          disabled: !materialName.trim() || !materialText.trim(),
          onClick: () => void handleSaveMaterial()
        }, '保存资料')
      )
    )
  )
}

export default {
  id: PLUGIN_ID,
  name: 'LaTeX 论文工坊',
  defaultEnabled: true,
  register(ctx) {
    ctx.registerMany([
      { id: 'route', area: ROUTES_AREA, data: { path: '/latex' }, render: () => h(LatexWorkbench, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/latex', label: 'LaTeX 工坊', codicon: 'file-code' } },
      { id: 'open', area: PALETTE_AREA, data: { id: 'forx-latex.open', label: '打开 LaTeX 论文工坊', keywords: ['latex', 'paper', 'tex', '论文'], run: () => host.navigate('/latex') } },
    ])
  },
}
