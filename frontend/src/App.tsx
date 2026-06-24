import type { Dispatch, SetStateAction } from 'react'
import { useEffect, useState } from 'react'
import type { ConfigTab, Page, StatusFilter } from './types'
import { Sidebar } from './components/Sidebar'
import { Header } from './components/Header'
import { DocumentsPage } from './pages/DocumentsPage'
import { AttentionPage } from './pages/AttentionPage'
import { ConfigPage } from './pages/ConfigPage'
import { TemplatesPage } from './pages/TemplatesPage'
import { AutomationsPage } from './pages/AutomationsPage'
import { DryRunPage } from './pages/DryRunPage'

type Theme = 'light' | 'dark'

const PAGE_META: Record<Page, [title: string, desc: string]> = {
  documentos: ['Documentos', 'Arquivos encontrados e tratados pelo watcher'],
  atencao: [
    'Precisam de atenção',
    'Documentos que pararam por falha, quarentena ou baixa confiança',
  ],
  templates: ['Templates', 'Modelos de extração de dados por tipo de documento'],
  automacoes: ['Automações', 'Ações executadas após o tratamento dos documentos'],
  dryrun: ['Pré-visualização das automações', 'Confira origem → destino antes de aplicar'],
  config: ['Configurações', 'Pastas monitoradas, regras, leitura e integrações'],
}

function initialTheme(): Theme {
  const saved = localStorage.getItem('docwatch-theme')
  return saved === 'dark' ? 'dark' : 'light'
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [page, setPage] = useState<Page>('documentos')
  const [configTab, setConfigTab] = useState<ConfigTab>('pastas')
  const [status, setStatus] = useState<StatusFilter>('todos')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [watcher, setWatcher] = useState(true)
  const [ruleState, setRuleState] = useState<Record<number, boolean>>({ 1: true, 2: false, 3: true, 4: true })
  const [deskew, setDeskew] = useState(true)
  const [denoise, setDenoise] = useState(true)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('docwatch-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme((t) => (t === 'light' ? 'dark' : 'light'))
  const toggleSel = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const toggleAll = (ids: number[]) =>
    setSelected((s) => (s.length === ids.length ? [] : ids.slice()))
  const clearSel = () => setSelected([])
  const toggleIn = (
    set: Dispatch<SetStateAction<Record<number, boolean>>>,
    id: number,
  ) => set((s) => ({ ...s, [id]: !s[id] }))

  const [title, desc] = PAGE_META[page]

  return (
    <div className="app" data-theme={theme}>
      <Sidebar page={page} onNavigate={setPage} />
      <main className="main">
        <Header
          title={title}
          desc={desc}
          search={search}
          onSearch={setSearch}
          isDark={theme === 'dark'}
          onToggleTheme={toggleTheme}
        />
        <div className="scroll">
          {page === 'documentos' && (
            <DocumentsPage
              search={search}
              status={status}
              onStatus={setStatus}
              selected={selected}
              onToggleSel={toggleSel}
              onToggleAll={toggleAll}
              onClearSel={clearSel}
            />
          )}
          {page === 'atencao' && <AttentionPage />}
          {page === 'config' && (
            <ConfigPage
              tab={configTab}
              onTab={setConfigTab}
              watcher={watcher}
              onToggleWatcher={() => setWatcher((w) => !w)}
              ruleState={ruleState}
              onToggleRule={(id) => toggleIn(setRuleState, id)}
              deskew={deskew}
              onToggleDeskew={() => setDeskew((d) => !d)}
              denoise={denoise}
              onToggleDenoise={() => setDenoise((d) => !d)}
            />
          )}
          {page === 'templates' && <TemplatesPage />}
          {page === 'automacoes' && <AutomationsPage />}
          {page === 'dryrun' && <DryRunPage />}
        </div>
      </main>
    </div>
  )
}
