import { useState, useCallback, useEffect, useRef } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import {
  Activity,
  Shield,
  Wifi,
  BarChart3,
  Flame,
  Zap,
  Bell,
} from 'lucide-react'
import {
  usePreferences,
  useQuoteStatus,
  useQuoteInterval,
  useCapabilities,
} from '@/lib/useSharedQueries'
import { useUpdateQuoteInterval, useToggleRealtimeQuotes } from '@/lib/useSharedMutations'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { tierRank } from '@/lib/capability-labels'
import { toast } from '@/components/Toast'
import { DepthConfigContent } from '@/components/data/DepthConfigCard'

// 页面 → 显示名
const PAGE_LABELS: Record<string, string> = {
  'overview-market': '看板',
  watchlist: '自选页',
  'limit-ladder': '连板梯队',
}

const SIDEBAR_INDEX_OPTIONS = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
]

// ===== 导出为 Panel 组件 (由 Settings.tsx 嵌入) =====

export function SettingsMonitoringPanel({ highlight }: { highlight?: string } = {}) {
  const qc = useQueryClient()
  const { data: prefs } = usePreferences()
  const { data: caps } = useCapabilities()
  const { data: quoteStatus } = useQuoteStatus()
  const { data: intervalData } = useQuoteInterval()
  const updateInterval = useUpdateQuoteInterval()
  const toggleQuote = useToggleRealtimeQuotes()
  // TickFlow none/free 通常没有实时行情；保存了 Tushare Token 或配置了本地分钟库时后端会放开。
  const realtimeAllowed = prefs?.realtime_allowed ?? tierRank(caps?.label ?? '') >= 1
  const realtimeEnabled = prefs?.realtime_quotes_enabled ?? false
  const refreshPages = prefs?.sse_refresh_pages ?? {}
  const limitLadderMonitor = prefs?.limit_ladder_monitor_enabled ?? false
  const systemNotify = prefs?.system_notify_enabled ?? false
  const hasDepth = !!caps?.capabilities?.['depth5.batch']
  const sidebarIndexSymbols = prefs?.sidebar_index_symbols ?? SIDEBAR_INDEX_OPTIONS.map(i => i.symbol)
  const indicesPinned = prefs?.indices_nav_pinned ?? true
  const isRunning = quoteStatus?.running ?? false
  const isTrading = quoteStatus?.is_trading_hours ?? false
  const interval = intervalData?.interval ?? 10
  const minInterval = intervalData?.min_interval ?? 5
  const maxInterval = intervalData?.max_interval ?? 60

  const save = useCallback(async (cfg: Record<string, unknown>) => {
    try {
      await api.updateRealtimeMonitorConfig(cfg)
      qc.invalidateQueries({ queryKey: QK.preferences })
    } catch (e) {
      // 忽略 — Toast 已在 request 层处理
    }
  }, [qc])

  const handleToggleQuote = useCallback(async (enabled: boolean) => {
    await toggleQuote.mutateAsync(enabled)
    qc.invalidateQueries({ queryKey: QK.preferences })
    qc.invalidateQueries({ queryKey: QK.quoteStatus })
  }, [toggleQuote, qc])

  const toggleSidebarIndex = useCallback((symbol: string, visible: boolean) => {
    const selected = new Set(sidebarIndexSymbols)
    if (visible) selected.add(symbol)
    else selected.delete(symbol)
    const next = SIDEBAR_INDEX_OPTIONS
      .map(item => item.symbol)
      .filter(s => selected.has(s))
    save({ sidebar_index_symbols: next })
  }, [save, sidebarIndexSymbols])

  const toggleIndicesPin = useCallback((pinned: boolean) => {
    api.updateIndicesNavPinned(pinned).then(() => qc.invalidateQueries({ queryKey: QK.preferences }))
  }, [qc])

  const toggleLimitLadderMonitor = useCallback(async (enabled: boolean) => {
    await api.updateLimitLadderMonitor(enabled)
    qc.invalidateQueries({ queryKey: QK.preferences })
  }, [qc])

  const toggleSystemNotify = useCallback(async (enabled: boolean) => {
    await api.updateSystemNotify(enabled)
    qc.invalidateQueries({ queryKey: QK.preferences })
  }, [qc])

  const runFix = useMutation({
    mutationFn: () => api.runLimitLadderFix(),
    onSuccess: (data) => {
      toast(data.msg, data.ok ? 'success' : 'error')
      // 修正后连板梯队数据变了, 刷新相关缓存
      qc.invalidateQueries({ queryKey: ['limit-ladder'] })
    },
    onError: () => toast('修正请求失败', 'error'),
  })

  // highlight=depth-fix 时闪烁高亮连板梯队修正卡片
  const [flash, setFlash] = useState(false)
  const flashedRef = useRef(false)
  useEffect(() => {
    if (highlight === 'depth-fix' && !flashedRef.current) {
      flashedRef.current = true
      // 延迟一帧确保 DOM 已渲染, 再触发闪烁
      requestAnimationFrame(() => {
        setFlash(true)
        const t = setTimeout(() => setFlash(false), 2000)
        return () => clearTimeout(t)
      })
    }
  }, [highlight])

  // 无 TickFlow 实时权限且没有可用的 Tushare/本地分钟行情 — 显示配置提示
  if (!realtimeAllowed) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl
                        bg-gradient-to-br from-purple-500/20 to-blue-500/20 mb-5">
          <Activity className="h-7 w-7 text-purple-400" />
        </div>
        <h2 className="text-lg font-medium text-foreground mb-2">实时监控</h2>
        <p className="text-sm text-secondary max-w-md mb-6">
          实时行情轮询、策略监控等功能需要 Starter 及以上档位。
          升级后可配置轮询间隔、选择监控策略池。
        </p>
        <a
          href="/settings?tab=account"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-btn
                     bg-accent text-white text-sm font-medium
                     hover:bg-accent/90 transition-colors"
        >
          配置 API Key 升级
        </a>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-6 max-w-5xl">
      {/* ========== 左列 ========== */}
      <div className="space-y-6">
        {/* 行情状态 — 开关 + 间隔 */}
        <Card icon={Activity} title="行情轮询">
          <ToggleRow
            label="实时行情"
            desc={isRunning && isTrading ? '运行中' : isRunning ? '运行中 (非交易时段)' : '已关闭'}
            checked={realtimeEnabled}
            onChange={handleToggleQuote}
          />

          <div className="mt-3 pt-3 border-t border-border">
            <div className="flex items-center justify-between gap-4 py-1">
              <div className="min-w-0">
                <div className="text-sm text-foreground">轮询间隔</div>
                <div className="text-[11px] text-muted">每轮拉取全市场行情的时间间隔</div>
              </div>
              <span className="text-[11px] font-mono text-foreground shrink-0 tabular-nums">
                {interval < 1 ? interval.toFixed(1) : interval.toFixed(0)}s
              </span>
            </div>
            <div className="flex items-center gap-3 mt-2">
              <input
                type="range"
                min={minInterval}
                max={maxInterval}
                step={minInterval < 1 ? 0.1 : minInterval < 3 ? 0.5 : 1}
                value={interval}
                onChange={(e) => updateInterval.mutate(parseFloat(e.target.value))}
                className="flex-1 h-1 accent-accent cursor-pointer"
              />
              <span className="text-[10px] text-muted shrink-0">
                {minInterval}s — {maxInterval}s
              </span>
            </div>
          </div>
        </Card>

        {/* 页面刷新 */}
        <Card icon={Wifi} title="页面实时刷新">
          <p className="text-xs text-secondary mb-4">
            选择哪些页面跟随 SSE 实时刷新数据。关闭的页面不会被推送，
            但行情轮询和策略监控不受影响。
          </p>
          <div className="space-y-2">
            {Object.entries(PAGE_LABELS).map(([key, label]) => (
              <ToggleRow
                key={key}
                label={label}
                desc={`SSE 推送时刷新 ${label} 数据`}
                checked={refreshPages[key] !== false}
                onChange={(v) => save({ sse_refresh_pages: { ...refreshPages, [key]: v } })}
              />
            ))}
          </div>
        </Card>

        <Card icon={BarChart3} title="左侧菜单指数">
          <p className="text-xs text-secondary mb-4">
            选择实时行情开启时，左侧菜单底部显示哪些指数点位和涨跌幅。
          </p>
          <div className="space-y-2">
            {SIDEBAR_INDEX_OPTIONS.map(item => (
              <ToggleRow
                key={item.symbol}
                label={item.name}
                desc={item.symbol}
                checked={sidebarIndexSymbols.includes(item.symbol)}
                onChange={(v) => toggleSidebarIndex(item.symbol, v)}
              />
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-border">
            <ToggleRow
              label="固定显示"
              desc={indicesPinned ? '指数卡片常驻显示（即使实时行情关闭）' : '跟随实时行情开关（仅实时开时显示）'}
              checked={indicesPinned}
              onChange={toggleIndicesPin}
            />
          </div>
        </Card>
      </div>

      {/* ========== 右列 ========== */}
      <div className="space-y-6">
        {/* 策略监控已迁移至监控中心 */}
        <Card icon={Shield} title="策略监控">
          <p className="text-xs text-secondary mb-3">
            策略监控、个股信号监控、价格监控已统一到「监控中心」页面,支持灵活配置触发条件、冷却期和作用范围。
          </p>
          <a
            href="#/monitor"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn bg-accent/15 text-accent text-xs font-medium hover:bg-accent/25 transition-colors"
          >
            前往监控中心配置 →
          </a>
          <div className="mt-3 pt-3 border-t border-border">
            <ToggleRow
              icon={Bell}
              label="系统通知"
              desc="监控告警同时推送到操作系统通知中心（窗口最小化或后台也能收到）"
              checked={systemNotify}
              onChange={toggleSystemNotify}
            />
          </div>
        </Card>

        {/* 连板梯队降级修正 */}
        <div
          id="depth-fix"
          className={`rounded-card transition-all duration-500 ${flash ? 'ring-2 ring-accent/60 ring-offset-2 ring-offset-base scale-[1.01]' : 'ring-0 ring-transparent'}`}
        >
        <Card
          icon={Flame}
          title="连板梯队降级修正"
          badge={!hasDepth ? '需 Pro+' : undefined}
          right={hasDepth ? (
            <button
              onClick={() => runFix.mutate()}
              disabled={runFix.isPending}
              className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px]
                         bg-accent/15 text-accent hover:bg-accent/25 transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Zap className="h-3 w-3" />
              {runFix.isPending ? '修正中…' : '立即修正'}
            </button>
          ) : undefined}
        >
          {hasDepth ? (
            <>
              <p className="text-xs text-secondary mb-4">
                通过五档盘口实时修正真假涨停/跌停。真封板显示封单量,假涨停(收盘价=涨停价但卖一有量)归入炸板。
                盘中按设定间隔轮询,收盘后自动定版。
              </p>
              <ToggleRow
                label="启用真假板修正"
                desc="开启后盘中自动拉取五档盘口修正真假板"
                checked={limitLadderMonitor}
                onChange={toggleLimitLadderMonitor}
              />
              <div className="mt-4 pt-3 border-t border-border">
                <div className="text-[10px] uppercase tracking-widest text-muted mb-3">
                  五档盘口配置
                </div>
                <DepthConfigContent disabled={!limitLadderMonitor} />
              </div>
            </>
          ) : (
            <DepthConfigContent disabled />
          )}
        </Card>
        </div>
      </div>
    </div>
  )
}


// ===== ToggleRow =====

function ToggleRow({
  label,
  desc,
  checked,
  onChange,
  icon: Icon,
}: {
  label: string
  desc: string
  checked: boolean
  onChange: (v: boolean) => void
  icon?: React.ComponentType<{ className?: string }>
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="min-w-0 flex items-start gap-2">
        {Icon && <Icon className="h-3.5 w-3.5 text-secondary shrink-0 mt-0.5" />}
        <div className="min-w-0">
          <div className="text-sm text-foreground">{label}</div>
          <div className="text-[11px] text-muted truncate">{desc}</div>
        </div>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full shrink-0 transition-colors duration-200 ${
          checked ? 'bg-accent' : 'bg-elevated'
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
            checked ? 'translate-x-[18px]' : 'translate-x-[3px]'
          }`}
        />
      </button>
    </div>
  )
}


// ===== 通用卡片 =====

interface CardProps {
  icon: React.ComponentType<{ className?: string }>
  title: string
  badge?: string
  right?: React.ReactNode
  children: React.ReactNode
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
