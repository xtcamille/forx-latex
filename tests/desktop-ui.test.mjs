// With the desktop renderer built, run from the repo root with:
// node --test hermes-latex/tests/desktop-ui.test.mjs
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { once } from 'node:events'
import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { after, before, test } from 'node:test'
import { build } from 'esbuild'
import { chromium } from 'playwright'

const repoRoot = resolve(import.meta.dirname, '../..')
const desktop = join(repoRoot, 'apps', 'desktop')
const browserOrigin = 'http://latex-ui.test'
const apiRoot = '/api/plugins/hermes-latex'
const sessionToken = randomUUID()
const tempRoot = realpathSync(tmpdir())
const longFile = 'sections/supplementary-experiments-and-reproducibility-details-for-the-appendix.tex'
const shortFile = 'sections/notes.tex'
let testHome, backend, browser, bundle, desktopCss, projectId
let requestId = 0
const pending = new Map()

before(async () => {
  testHome = mkdtempSync(join(tempRoot, 'latex-ui-'))
  cpSync(resolve(import.meta.dirname, '..'), join(testHome, 'plugins', 'hermes-latex'), {
    recursive: true,
    filter: path => !['tests', '__pycache__'].includes(path.split(/[\\/]/).at(-1)),
  })
  writeFileSync(join(testHome, 'config.yaml'), 'plugins:\n  enabled: [hermes-latex]\n')

  const credential = /(?:_KEY|_TOKEN|_SECRET|_PASSWORD|_CREDENTIALS)$/i
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !credential.test(key)))
  const python = env.HERMES_PYTHON || join(repoRoot, '.venv', ...(process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']))
  const serve = [
    'import json, sys',
    'from fastapi.testclient import TestClient',
    'wire = sys.stdout',
    'from hermes_cli.web_server import app',
    'client = TestClient(app, base_url="http://127.0.0.1")',
    'print("LaTeX test API ready", file=wire, flush=True)',
    'for line in sys.stdin:',
    '    req = json.loads(line)',
    '    resp = client.request(req["method"], req["path"], content=req.get("body"), headers=req["headers"])',
    '    print(json.dumps({"id": req["id"], "status": resp.status_code, "body": resp.text}), file=wire, flush=True)',
  ].join('\n')
  backend = spawn(python, ['-u', '-c', serve], {
    cwd: repoRoot,
    env: { ...env, PYTHONUTF8: '1', FORX_HOME: testHome, HERMES_HOME: testHome, HERMES_DESKTOP: '1', HERMES_DASHBOARD_SESSION_TOKEN: sessionToken },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })
  await new Promise((accept, reject) => {
    let diagnostics = ''
    const timer = setTimeout(() => reject(new Error(`Hermes serve timed out: ${diagnostics}`)), 25_000)
    backend.stderr.on('data', data => { diagnostics = (diagnostics + data).slice(-2000) })
    backend.once('error', reject)
    backend.once('exit', code => {
      const error = new Error(`Hermes test API exited (${code}): ${diagnostics}`)
      reject(error)
      for (const request of pending.values()) request.reject(error)
      pending.clear()
    })
    createInterface({ input: backend.stdout }).on('line', line => {
      if (line === 'LaTeX test API ready') {
        clearTimeout(timer)
        accept()
        return
      }
      try {
        const { id, status, body } = JSON.parse(line)
        const request = pending.get(id)
        if (request) request.resolve(new Response(body, { status }))
        pending.delete(id)
      } catch {
        diagnostics = `${diagnostics}\n${line}`.slice(-2000)
      }
    })
    backend.once('close', () => clearTimeout(timer))
    timer.unref()
  })

  const assets = join(desktop, 'dist', 'assets')
  const cssFile = readdirSync(assets).find(name => /^index-.+\.css$/.test(name))
  desktopCss = readFileSync(join(assets, cssFile), 'utf8')
  const compiled = await build({
    stdin: {
      resolveDir: repoRoot,
      contents: `import { createRoot } from 'react-dom/client';
        import plugin from './hermes-latex/desktop/plugin.js';
        plugin.register({
          registerMany(items) {
            const route = items.find(item => item.area === 'routes' && item.data.path === '/latex');
            createRoot(document.getElementById('fixture')).render(route.render());
          },
          storage: { get: () => null, set: () => {} },
          async rest(path, options = {}) {
            const response = await fetch('${apiRoot}' + path, {
              method: options.method,
              headers: { 'Content-Type': 'application/json' },
              body: options.body && JSON.stringify(options.body),
            });
            if (!response.ok) throw new Error(response.status + ': ' + await response.text());
            return response.json();
          },
        });`,
    },
    bundle: true,
    write: false,
    format: 'esm',
    define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env': '{"DEV":false}' },
    alias: { '@': join(desktop, 'src'), '@hermes/plugin-sdk': join(import.meta.dirname, 'desktop-test-sdk.mjs') },
  })
  bundle = compiled.outputFiles[0].text
  browser = await chromium.launch(existsSync(chromium.executablePath()) ? {} : { channel: 'chrome' })

  const project = await api('/projects', 'POST', { name: 'Long project title '.repeat(8), template_id: 'ieee-conf' })
  projectId = project.project.id
  const main = Array.from({ length: 180 }, (_, i) => {
    if (i === 2) return `% ${'long-source-line '.repeat(70)}`
    if (i === 99) return '\\section{Section one hundred}'
    return `% line ${i + 1}`
  }).join('\n')
  await api(`/projects/${projectId}/file`, 'PUT', { path: 'main.tex', content: main })
  await api(`/projects/${projectId}/file`, 'PUT', { path: longFile, content: '% Supplementary experiments' })
  await api(`/projects/${projectId}/file`, 'PUT', { path: shortFile, content: '% Notes' })
})

after(async () => {
  await browser?.close()
  if (backend && backend.exitCode === null && backend.signalCode === null) {
    const exited = once(backend, 'exit')
    backend.kill()
    await exited
  }
  if (testHome && dirname(realpathSync(testHome)) === tempRoot) rmSync(testHome, { recursive: true, force: true })
})

function callBackend(path, method, body) {
  const id = ++requestId
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    backend.stdin.write(JSON.stringify({
      id, path, method, body,
      headers: { 'X-Hermes-Session-Token': sessionToken, 'Content-Type': 'application/json' },
    }) + '\n', error => {
      if (!error) return
      pending.delete(id)
      reject(error)
    })
  })
}

async function api(path, method = 'GET', data) {
  const response = await callBackend(apiRoot + path, method, data && JSON.stringify(data))
  assert(response.ok, `${method} ${path} returned ${response.status}: ${response.ok ? '' : await response.text()}`)
  return response.json()
}

async function openWorkbench(t, width) {
  const page = await browser.newPage({ viewport: { width, height: 750 } })
  t.after(() => page.close())
  await page.route(`${browserOrigin}/**`, async route => {
    const url = new URL(route.request().url())
    if (url.pathname.startsWith(apiRoot + '/')) {
      const response = await callBackend(url.pathname + url.search, route.request().method(), route.request().postData() ?? undefined)
      return route.fulfill({ status: response.status, contentType: 'application/json', body: await response.text() })
    }
    if (url.pathname === '/bundle.js') return route.fulfill({ contentType: 'text/javascript', body: bundle })
    if (url.pathname === '/desktop.css') return route.fulfill({ contentType: 'text/css', body: desktopCss })
    return route.fulfill({ contentType: 'text/html', body: `<!doctype html><meta charset="utf-8">
      <link rel="stylesheet" href="/desktop.css"><div id="fixture" style="height:100vh;margin-left:220px"></div>
      <script type="module" src="/bundle.js"></script>` })
  })
  await page.goto(browserOrigin)
  await page.getByRole('textbox', { name: 'LaTeX 源码' }).waitFor()
  return page
}

test('toolbar actions and all panes stay accessible as the workbench narrows', async t => {
  const page = await openWorkbench(t, 1470)
  const root = page.getByRole('region', { name: 'LaTeX 论文工坊' })
  const toolbar = root.locator('.hlx-toolbar')
  const switcher = root.getByRole('group', { name: '工作区视图' })
  const fits = element => element.evaluate(el => el.scrollWidth <= el.clientWidth + 1)
  assert(await fits(toolbar))
  assert(!(await switcher.isVisible()))
  assert(await root.getByRole('button', { name: 'PDF 预览' }).isVisible())

  await page.setViewportSize({ width: 825, height: 680 })
  assert(await fits(toolbar))
  assert(await switcher.isVisible())
  await switcher.getByRole('button', { name: '预览与工具' }).click()
  await root.getByRole('button', { name: '编译诊断 (0)' }).click()
  await root.getByText('编译后可在这里查看错误和警告。').waitFor()
  await toolbar.getByRole('button', { name: '投稿体检' }).click()
  await root.getByText('篇幅与合规概览', { exact: false }).waitFor()
  await switcher.getByRole('button', { name: '工程', exact: true }).click()
  await root.getByRole('button', { name: '大纲' }).click()
  await root.getByRole('button', { name: /Section one hundred/ }).click()
  const editor = root.getByRole('textbox', { name: 'LaTeX 源码' })
  assert(await editor.isVisible())
  assert.equal(await editor.evaluate(el => el.value.slice(0, el.selectionStart).split('\n').length), 100)
  assert(await editor.evaluate(el => el.scrollWidth > el.clientWidth && getComputedStyle(el).whiteSpace === 'pre'))
  assert.equal(await root.locator('.hlx-gutter').evaluate(el => getComputedStyle(el).lineHeight),
    await editor.evaluate(el => getComputedStyle(el).lineHeight))
})

test('the create-file dialog rejects an existing path and the editor persists a new file', async t => {
  const page = await openWorkbench(t, 825)
  const root = page.getByRole('region', { name: 'LaTeX 论文工坊' })
  const file = '/projects/' + projectId + '/file'
  const original = await api(file + '?path=main.tex')
  await root.getByRole('button', { name: '工程', exact: true }).click()
  await root.getByRole('button', { name: '＋ 新建文件' }).click()
  const dialog = page.getByRole('dialog', { name: '新建文件' })
  const path = dialog.getByRole('textbox', { name: '文件路径' })
  await path.fill('./main.tex')
  await path.press('Enter')
  await dialog.getByRole('alert').getByText('此路径已有文件，请使用其他文件名。').waitFor()
  assert.deepEqual(await api(file + '?path=main.tex'), original)

  await path.fill('sections/desktop-test.tex')
  await path.press('Enter')
  await dialog.waitFor({ state: 'hidden' })
  const editor = root.getByRole('textbox', { name: 'LaTeX 源码' })
  assert(await editor.isVisible())
  const draft = '% 保存从桌面创建的文件\n'
  await editor.fill(draft)
  await editor.press('ControlOrMeta+s')
  await root.getByRole('button', { name: '已保存' }).waitFor()
  assert.equal((await api(file + '?path=sections%2Fdesktop-test.tex')).content, draft)
})

async function holdFileRead(page, path) {
  const started = Promise.withResolvers()
  const release = Promise.withResolvers()
  const matches = url => url.pathname === `${apiRoot}/projects/${projectId}/file` && url.searchParams.get('path') === path
  await page.route(matches, async route => {
    started.resolve()
    await release.promise
    await route.fallback()
  })
  return { started: started.promise, release: release.resolve, matches }
}

function afterPaint(page) {
  return page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
}

test('switching files keeps the workspace, source, and chat at the same positions', async t => {
  const page = await openWorkbench(t, 1200)
  await page.getByRole('button', { name: '编译预览', disabled: false }).waitFor()
  const positions = () => page.evaluate(() => ['.hlx-main', '.hlx-textarea', '.hlx-chat-messages'].map(
    selector => document.querySelector(selector).getBoundingClientRect().top
  ))
  const idle = await positions()
  const read = await holdFileRead(page, longFile)
  let loading
  try {
    await page.getByRole('button', { name: longFile, exact: false }).click()
    await read.started
    await afterPaint(page)
    loading = await positions()
  } finally {
    read.release()
  }
  await page.waitForFunction(() => document.querySelector('.hlx-textarea').value === '% Supplementary experiments')
  const loaded = await positions()
  assert.deepEqual({ loading, loaded }, { loading: idle, loaded: idle })
})

test('a slower file response cannot replace the most recently selected file', async t => {
  const page = await openWorkbench(t, 1200)
  await page.getByRole('button', { name: '编译预览', disabled: false }).waitFor()
  const read = await holdFileRead(page, longFile)
  try {
    await page.getByRole('button', { name: longFile, exact: false }).click()
    await read.started
    await page.getByRole('button', { name: shortFile, exact: false }).click()
    await page.waitForFunction(() => document.querySelector('.hlx-textarea').value === '% Notes')
    const response = page.waitForResponse(response => read.matches(new URL(response.url())))
    read.release()
    await (await response).finished()
    await afterPaint(page)
    assert.equal(await page.getByRole('textbox', { name: 'LaTeX 源码' }).inputValue(), '% Notes')
  } finally {
    read.release()
  }
})

test('each desktop pane can collapse, give up its width, and reopen in place', async t => {
  const page = await openWorkbench(t, 1470)
  await page.getByRole('button', { name: '编译预览', disabled: false }).waitFor()
  const controls = page.getByRole('group', { name: '工作区面板' })
  assert(await controls.isVisible(), 'wide workbench needs controls to reopen its panels')
  const filesToggle = controls.getByRole('button', { name: '工程', exact: true })
  const sourceToggle = controls.getByRole('button', { name: '源码', exact: true })
  const outputToggle = controls.getByRole('button', { name: '预览与工具', exact: true })
  const editor = page.getByRole('textbox', { name: 'LaTeX 源码' })
  const files = page.getByRole('complementary', { name: '工程' })
  const output = page.getByRole('region', { name: '预览与工具' })
  const editorWidth = async () => (await editor.boundingBox()).width
  const original = await editorWidth()
  const draft = (await editor.inputValue()) + '\n% 未保存的源码'
  await editor.fill(draft)
  await editor.evaluate(el => { el.scrollTop = 400; el.setSelectionRange(30, 30) })

  await filesToggle.click()
  await files.waitFor({ state: 'hidden' })
  assert.equal(await filesToggle.getAttribute('aria-expanded'), 'false')
  const twoPanes = await editorWidth()
  assert(twoPanes > original)
  await outputToggle.click()
  await output.waitFor({ state: 'hidden' })
  assert(await editorWidth() > twoPanes)

  await sourceToggle.click()
  await editor.waitFor({ state: 'hidden' })
  assert(await controls.isVisible())
  await sourceToggle.click()
  await editor.waitFor()
  assert.equal(await editor.inputValue(), draft)
  assert.deepEqual(await editor.evaluate(el => [el.scrollTop, el.selectionStart]), [400, 30])
  await filesToggle.click()
  await files.waitFor()
  await outputToggle.click()
  await output.waitFor()
  assert.equal(await editorWidth(), original)
})

test('compact panes can fold and wide panel choices survive a resize', async t => {
  const page = await openWorkbench(t, 1470)
  const wide = page.getByRole('group', { name: '工作区面板' })
  assert(await wide.isVisible(), 'wide workbench needs panel controls')
  const compact = page.getByRole('group', { name: '工作区视图' })
  const files = page.getByRole('complementary', { name: '工程' })
  const editor = page.getByRole('textbox', { name: 'LaTeX 源码' })
  const output = page.getByRole('region', { name: '预览与工具' })
  await wide.getByRole('button', { name: '工程' }).click()
  await wide.getByRole('button', { name: '预览与工具' }).click()

  await page.setViewportSize({ width: 825, height: 680 })
  await compact.getByRole('button', { name: '源码' }).click()
  await editor.waitFor({ state: 'hidden' })
  await compact.getByRole('button', { name: '工程' }).click()
  await files.waitFor()

  await page.setViewportSize({ width: 1470, height: 750 })
  await editor.waitFor()
  assert(!(await files.isVisible()))
  assert(!(await output.isVisible()))
  await page.locator('.hlx-toolbar').getByRole('button', { name: '投稿体检' }).click()
  await output.getByText('篇幅与合规概览', { exact: false }).waitFor()
  assert.equal(await wide.getByRole('button', { name: '预览与工具' }).getAttribute('aria-expanded'), 'true')
})
