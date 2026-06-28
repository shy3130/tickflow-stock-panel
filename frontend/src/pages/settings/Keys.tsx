import { useState, type ComponentType, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Key,
  Loader2,
  RefreshCw,
  Save,
  Trash2,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useCapabilities, useSettings } from '@/lib/useSharedQueries'
import { QK } from '@/lib/queryKeys'
import { CAP_LABELS, tierTextStyle } from '@/lib/capability-labels'

export function SettingsKeysPanel() {
  const qc = useQueryClient()
  const settings = useSettings()
  const caps = useCapabilities()
  const [keyInput, setKeyInput] = useState('')
  const [revealing, setRevealing] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [saved, setSaved] = useState(false)
  const [copiedCode, setCopiedCode] = useState(false)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: QK.settings })
    qc.invalidateQueries({ queryKey: QK.capabilities })
  }

  const save = useMutation({
    mutationFn: () => api.saveTickflowKey(keyInput.trim()),
    onSuccess: (data) => {
      setKeyInput('')
      invalidate()
      if (data.ok) {
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
      }
    },
  })

  const clear = useMutation({
    mutationFn: api.clearTickflowKey,
    onSuccess: invalidate,
  })

  const redetect = useMutation({
    mutationFn: api.redetectCapabilities,
    onSuccess: invalidate,
  })

  const mode = settings.data?.mode
  const masked = settings.data?.tickflow_api_key_masked
  const capCount = caps.data ? Object.keys(caps.data.capabilities).length : 0

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.3fr] gap-6 max-w-5xl">
        <div className="space-y-6">
          <Card icon={Key} title="TickFlow API Key">
            <p className="text-sm text-secondary leading-relaxed mb-4">
              在{' '}
              <a
                href="https://tickflow.org/auth/register?ref=V3KDKGXPEA"
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline inline-flex items-baseline gap-0.5"
              >
                tickflow.org
                <ExternalLink className="h-3 w-3 self-center" />
              </a>{' '}
              注册获取 API Key。Key 只保存在本地。
            </p>
            <p className="text-xs text-secondary leading-relaxed mb-4">
              邀请码{' '}
              <span className="font-mono font-semibold text-accent inline-flex items-baseline gap-1">
                V3KDKGXPEA
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText('V3KDKGXPEA').then(() => {
                      setCopiedCode(true)
                      setTimeout(() => setCopiedCode(false), 1500)
                    })
                  }}
                  className="text-muted hover:text-accent transition-colors"
                  aria-label="复制邀请码"
                  tabIndex={-1}
                >
                  {copiedCode ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                </button>
              </span>
            </p>

            <div className="flex items-center justify-between mb-4">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-widest text-muted">状态</div>
                <div className="mt-1 flex items-center gap-2 min-w-0">
                  {mode === 'api_key' || mode === 'free' ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-bear shrink-0" />
                      <span className="text-sm font-medium shrink-0">
                        {mode === 'free' ? '免费 Key' : '已配置'}
                      </span>
                      <span className="font-mono text-xs text-secondary truncate">{masked}</span>
                    </>
                  ) : (
                    <>
                      <AlertCircle className="h-4 w-4 text-muted shrink-0" />
                      <span className="text-sm font-medium text-muted">未配置</span>
                    </>
                  )}
                </div>
              </div>
              {(mode === 'api_key' || mode === 'free') && (
                <button
                  onClick={() => setConfirmClear(true)}
                  disabled={clear.isPending}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn bg-elevated text-secondary hover:text-danger text-xs disabled:opacity-50 shrink-0"
                >
                  <Trash2 className="h-3 w-3" />
                  清除
                </button>
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (keyInput.trim()) save.mutate()
              }}
              className="space-y-2"
            >
              <div className="relative">
                <input
                  type={revealing ? 'text' : 'password'}
                  placeholder={mode === 'none' ? '粘贴 TickFlow API Key' : '粘贴新 Key 替换当前'}
                  value={keyInput}
                  onChange={(e) => {
                    setKeyInput(e.target.value)
                    if (saved) setSaved(false)
                  }}
                  className="w-full px-3 py-2 pr-9 rounded-input bg-base border border-border text-sm font-mono focus:outline-none focus:border-accent transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setRevealing((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-foreground transition-colors"
                  tabIndex={-1}
                  aria-label={revealing ? '隐藏' : '显示'}
                >
                  {revealing ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <button
                type="submit"
                disabled={save.isPending || (!keyInput.trim() && !saved)}
                className="w-full h-10 rounded-xl bg-accent text-white text-sm font-semibold flex items-center justify-center gap-2 hover:bg-accent/90 disabled:opacity-40 transition-all"
              >
                {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                {save.isPending ? '保存中...' : saved ? '已保存' : '保存并检测'}
              </button>
            </form>

            {save.isError && (
              <div className="mt-3 text-xs text-danger">
                保存失败: {String((save.error as any).message)}
              </div>
            )}
            {save.data && !save.data.ok && (
              <div className="mt-3 text-xs text-danger flex items-center gap-1.5">
                <AlertCircle className="h-3 w-3 shrink-0" />
                {save.data.reason === 'invalid' ? 'Key 无效或已过期，请检查后重试。' : save.data.error ?? '保存失败'}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card
            icon={Activity}
            title="订阅档位"
            right={
              <button
                onClick={() => redetect.mutate()}
                disabled={redetect.isPending}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn bg-elevated hover:bg-elevated/80 text-xs text-secondary disabled:opacity-50"
              >
                <RefreshCw className={`h-3 w-3 ${redetect.isPending ? 'animate-spin' : ''}`} />
                重新检测
              </button>
            }
          >
            {caps.data ? (
              <>
                <div className="font-mono text-3xl font-bold tracking-tight" style={tierTextStyle(caps.data.label)}>
                  {caps.data.label}
                </div>
                <div className="mt-1 text-xs text-muted">根据 API Key 自动检测能力。</div>
                {settings.data?.missing_caps && settings.data.missing_caps.length > 0 && (
                  <div className="mt-3 rounded-btn border border-warning/40 bg-warning/5 px-3 py-2 text-xs">
                    <div className="font-medium text-warning mb-1">
                      未检测到 {settings.data.missing_caps.length} 项预期能力
                    </div>
                    <div className="text-secondary space-y-0.5">
                      {settings.data.missing_caps.map((c) => (
                        <div key={c} className="font-mono">{CAP_LABELS[c]?.name ?? c}</div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-sm text-muted">加载中...</div>
            )}
          </Card>

          <Card icon={CheckCircle2} title="可用功能" badge={`${capCount} 项`}>
            {caps.data ? (
              <div className="-mx-5 -mb-5 border-t border-border">
                {Object.entries(caps.data.capabilities).map(([cap, lim]) => {
                  const meta = CAP_LABELS[cap]
                  return (
                    <div
                      key={cap}
                      className="px-5 py-3 border-b border-border last:border-b-0 flex items-baseline justify-between gap-4"
                    >
                      <div className="min-w-0">
                        <div className="text-sm text-foreground truncate">{meta?.name ?? cap}</div>
                        {meta?.hint && <div className="mt-0.5 text-[11px] text-muted truncate">{meta.hint}</div>}
                      </div>
                      <div className="text-right shrink-0 text-xs">
                        <div className="font-mono text-foreground">
                          {lim.rpm ? `${lim.rpm}/min` : lim.subscribe ? `${lim.subscribe} 订阅` : '-'}
                        </div>
                        {lim.batch && <div className="font-mono text-muted">{lim.batch} 只/次</div>}
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="text-sm text-muted">加载中...</div>
            )}
          </Card>
        </div>
      </div>

      {confirmClear && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setConfirmClear(false)} />
          <div className="relative w-[90vw] max-w-[380px] rounded-card border border-border bg-base shadow-2xl p-6">
            <h3 className="text-sm font-medium text-foreground mb-2">清除 API Key</h3>
            <p className="text-xs text-secondary mb-5">清除后将回到未配置状态。</p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmClear(false)}
                className="px-3 py-1.5 rounded-btn bg-elevated text-secondary hover:bg-elevated/80 text-sm transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => {
                  setConfirmClear(false)
                  clear.mutate()
                }}
                disabled={clear.isPending}
                className="px-3 py-1.5 rounded-btn bg-danger/15 text-danger hover:bg-danger/25 text-sm font-medium transition-colors disabled:opacity-50"
              >
                {clear.isPending ? '清除中...' : '确认清除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

interface CardProps {
  icon: ComponentType<{ className?: string }>
  title: string
  badge?: string
  right?: ReactNode
  children: ReactNode
}

function Card({ icon: Icon, title, badge, right, children }: CardProps) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <Icon className="h-4 w-4 text-secondary" />
          <h2 className="text-sm font-medium text-foreground">{title}</h2>
          {badge && (
            <span className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-elevated text-muted">
              {badge}
            </span>
          )}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}
