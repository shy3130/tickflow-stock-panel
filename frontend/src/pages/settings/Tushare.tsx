import { useState, type ComponentType, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Check, CheckCircle2, Database, Loader2, Save, Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useSettings } from '@/lib/useSharedQueries'

const DEFAULT_TUSHARE_URL = 'https://tt.xiaodefa.cn'

export function SettingsTusharePanel() {
  const qc = useQueryClient()
  const settings = useSettings()

  const [tokenInput, setTokenInput] = useState('')
  const [urlInput, setUrlInput] = useState('')
  const [tokenSaved, setTokenSaved] = useState(false)
  const [urlSaved, setUrlSaved] = useState(false)

  const invalidateTushareConsumers = () => {
    qc.invalidateQueries({ queryKey: QK.settings })
    qc.invalidateQueries({ queryKey: QK.quoteStatus })
    qc.invalidateQueries({ queryKey: QK.dataStatus })
    qc.invalidateQueries({ queryKey: QK.extData })
    qc.invalidateQueries({ queryKey: QK.indexQuotes })
    qc.invalidateQueries({ queryKey: QK.overviewMarket() })
    qc.invalidateQueries({ queryKey: QK.watchlistQuotes })
  }

  const saveToken = useMutation({
    mutationFn: () => api.saveTushareToken(tokenInput.trim()),
    onSuccess: () => {
      setTokenInput('')
      setTokenSaved(true)
      setTimeout(() => setTokenSaved(false), 2000)
      invalidateTushareConsumers()
    },
  })

  const clearToken = useMutation({
    mutationFn: api.clearTushareToken,
    onSuccess: invalidateTushareConsumers,
  })

  const saveUrl = useMutation({
    mutationFn: () => api.saveTushareHttpUrl(urlInput.trim()),
    onSuccess: () => {
      setUrlInput('')
      setUrlSaved(true)
      setTimeout(() => setUrlSaved(false), 2000)
      invalidateTushareConsumers()
    },
  })

  const resetUrl = useMutation({
    mutationFn: api.clearTushareHttpUrl,
    onSuccess: invalidateTushareConsumers,
  })

  const hasToken = !!settings.data?.has_tushare_token
  const currentUrl = settings.data?.tushare_http_url || DEFAULT_TUSHARE_URL

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-6 max-w-5xl">
      <div className="space-y-6">
        <Card icon={Database} title="Tushare Token">
          <p className="text-sm text-secondary leading-relaxed mb-4">
            用于从 Tushare 直接导入 A 股日 K 和基础标的信息，Token 只保存在本地 secrets.json。
          </p>

          <div className="flex items-center justify-between mb-4">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-muted">状态</div>
              <div className="mt-1 flex items-center gap-2 min-w-0">
                {hasToken ? (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-bear shrink-0" />
                    <span className="text-sm font-medium shrink-0">已配置</span>
                    <span className="font-mono text-xs text-secondary truncate">
                      {settings.data?.tushare_token_masked}
                    </span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-4 w-4 text-muted shrink-0" />
                    <span className="text-sm font-medium text-muted">未配置</span>
                  </>
                )}
              </div>
            </div>
            {hasToken && (
              <button
                type="button"
                onClick={() => clearToken.mutate()}
                disabled={clearToken.isPending}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn bg-elevated text-secondary hover:text-danger text-xs transition-colors duration-150 ease-smooth disabled:opacity-50 shrink-0"
              >
                <Trash2 className="h-3 w-3" />
                清除
              </button>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (tokenInput.trim()) saveToken.mutate()
            }}
            className="space-y-2"
          >
            <input
              type="password"
              placeholder={hasToken ? '粘贴新 Tushare Token 替换当前' : '粘贴 Tushare Token'}
              value={tokenInput}
              onChange={(e) => {
                setTokenInput(e.target.value)
                if (tokenSaved) setTokenSaved(false)
              }}
              className="w-full px-3 py-2 rounded-input bg-base border border-border text-sm font-mono focus:outline-none focus:border-accent transition-colors duration-150 ease-smooth"
            />
            <button
              type="submit"
              disabled={saveToken.isPending || (!tokenInput.trim() && !tokenSaved)}
              className="w-full h-10 rounded-xl bg-accent text-white text-sm font-semibold flex items-center justify-center gap-2 hover:bg-accent/90 disabled:opacity-40 transition-all"
            >
              {saveToken.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : tokenSaved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              {saveToken.isPending ? '保存中...' : tokenSaved ? '已保存' : '保存 Tushare Token'}
            </button>
          </form>
          {saveToken.isError && (
            <div className="mt-3 text-xs text-danger">
              保存失败:{String((saveToken.error as any).message)}
            </div>
          )}
        </Card>

        <Card icon={Database} title="Tushare HTTP URL">
          <div className="flex items-center justify-between mb-3">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-muted">当前地址</div>
              <div className="mt-1 font-mono text-xs text-secondary truncate">{currentUrl}</div>
            </div>
            <button
              type="button"
              onClick={() => resetUrl.mutate()}
              disabled={resetUrl.isPending}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn bg-elevated text-secondary hover:text-danger text-xs transition-colors duration-150 ease-smooth disabled:opacity-50 shrink-0"
            >
              <Trash2 className="h-3 w-3" />
              默认
            </button>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (urlInput.trim()) saveUrl.mutate()
            }}
            className="space-y-2"
          >
            <input
              type="text"
              placeholder={currentUrl || DEFAULT_TUSHARE_URL}
              value={urlInput}
              onChange={(e) => {
                setUrlInput(e.target.value)
                if (urlSaved) setUrlSaved(false)
              }}
              className="w-full px-3 py-2 rounded-input bg-base border border-border text-sm font-mono focus:outline-none focus:border-accent transition-colors duration-150 ease-smooth"
            />
            <button
              type="submit"
              disabled={saveUrl.isPending || (!urlInput.trim() && !urlSaved)}
              className="w-full h-10 rounded-xl bg-elevated text-foreground text-sm font-semibold flex items-center justify-center gap-2 hover:bg-border/60 disabled:opacity-40 transition-all"
            >
              {saveUrl.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : urlSaved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              {saveUrl.isPending ? '保存中...' : urlSaved ? '已保存' : '保存 HTTP URL'}
            </button>
          </form>
          {saveUrl.isError && (
            <div className="mt-3 text-xs text-danger">
              保存失败:{String((saveUrl.error as any).message)}
            </div>
          )}
        </Card>
      </div>

      <Card icon={Database} title="用途">
        <div className="space-y-3 text-sm text-secondary leading-relaxed">
          <p>Tushare 是独立数据源，用来补充 TickFlow 之外的数据导入和本地行情能力。</p>
          <p>这里的配置不会影响 TickFlow API Key 和订阅档位检测。</p>
          <p>保存后，数据同步、实时行情兜底和 Tushare 导入任务会读取本地 secrets.json 中的配置。</p>
        </div>
      </Card>
    </div>
  )
}

interface CardProps {
  icon: ComponentType<{ className?: string }>
  title: string
  children: ReactNode
}

function Card({ icon: Icon, title, children }: CardProps) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center gap-2.5 mb-3">
        <Icon className="h-4 w-4 text-secondary" />
        <h2 className="text-sm font-medium text-foreground">{title}</h2>
      </div>
      {children}
    </section>
  )
}
