import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Settings,
  Database,
  Loader2,
  CheckCircle2,
  ExternalLink,
  X,
} from 'lucide-react'
import {
  useCapabilities,
  useSettings,
  usePreferences,
  useQuoteStatus,
  useVersion,
} from '@/lib/useSharedQueries'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { tierRank } from '@/lib/capability-labels'
import { Logo } from '../Logo'
import { cn } from '@/lib/cn'
import {
  BRAND,
  TICKFLOW_REGISTER_URL,
  CORE_INDEXES,
  useDataSyncStatus,
  useVisibleNavItems,
  useRealtimeToggle,
} from './shared'
import {
  ThemeToggle,
  TierBadge,
  AIConfigBadge,
  MonitorBadge,
  SidebarIndexQuotes,
} from './components'

interface SidebarContentProps {
  /** 移动抽屉选中导航后关闭抽屉 */
  onNavigate?: () => void
  /** 桌面三态切换按钮（由 DesktopSidebar 注入，在 Logo 区右侧渲染） */
  toggleButton?: React.ReactNode
}

export function SidebarContent({ onNavigate, toggleButton }: SidebarContentProps) {
  // ===== 共享 hooks =====
  const { data: caps } = useCapabilities()
  const { data: settingsState } = useSettings()
  const { data: versionData } = useVersion()
  const { data: prefs } = usePreferences()
  const { data: dataSources } = useQuery({
    queryKey: QK.dataSources,
    queryFn: api.dataSources,
    staleTime: 60_000,
  })
  const { data: quoteStatus } = useQuoteStatus({ poll: true })
  const { data: analysisMenus } = useQuery({
    queryKey: QK.analysisMenus,
    queryFn: api.analysisMenus,
  })

  const { isDataSyncing, dataSyncJustDone } = useDataSyncStatus()

  const navigate = useNavigate()
  const version = versionData?.version
  const realtimeEnabled = prefs?.realtime_quotes_enabled ?? false
  const [dismissFreeHint, setDismissFreeHint] = useState(false)
  const indicesPinned = prefs?.indices_nav_pinned ?? true
  const sidebarIndexSymbols = prefs?.sidebar_index_symbols ?? CORE_INDEXES.map((p) => p.symbol)
  const sidebarIndexes = CORE_INDEXES.filter((item) => sidebarIndexSymbols.includes(item.symbol))
  const showSidebarQuotes = indicesPinned || realtimeEnabled
  const { data: sidebarIndexQuotes } = useQuery({
    queryKey: [...QK.indexQuotes, 'sidebar', sidebarIndexSymbols.join(',')] as const,
    queryFn: () => api.indexQuotes(sidebarIndexes.map((p) => p.symbol)),
    enabled: showSidebarQuotes && sidebarIndexes.length > 0,
    placeholderData: (prev) => prev,
  })

  const isRunning = quoteStatus?.running ?? false
  const isTrading = quoteStatus?.is_trading_hours ?? false
  const isPaused = quoteStatus?.paused ?? false
  const tier = tierRank(caps?.label ?? '')
  const isNoneTier = tier < 0
  const isWatchlistMode = tier === 0
  const realtimeModeLabel = isWatchlistMode ? '自选股' : '全市场'
  const realtimeProvider = prefs?.realtime_data_provider
  const realtimeProviderName =
    realtimeProvider && realtimeProvider !== 'tickflow'
      ? dataSources?.custom?.find((s) => s.name === realtimeProvider)?.display_name || realtimeProvider
      : null

  const activeProvider = prefs?.daily_data_provider || 'tickflow'
  const activeProviderName =
    activeProvider === 'tickflow'
      ? 'TickFlow'
      : dataSources?.custom?.find((s) => s.name === activeProvider)?.display_name || activeProvider
  const activeProviderDatasets =
    activeProvider === 'tickflow'
      ? ['daily', 'adj_factor', 'realtime', 'minute']
      : dataSources?.custom?.find((s) => s.name === activeProvider)?.datasets || []
  const isCustomActive = activeProvider !== 'tickflow'

  // ===== 导航项合并（内置 + 扩展分析菜单 + 自定义排序 + 隐藏）=====
  const visibleNavItems = useVisibleNavItems(analysisMenus, prefs)

  // ===== 实时行情开关逻辑（共享 hook）=====
  const { handleToggle, toggleQuote } = useRealtimeToggle(isTrading)

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* ===== Brand 区 ===== */}
      <div className="px-5 py-5 border-b border-border shrink-0">
        <div className="flex items-center gap-2.5">
          <Logo
            size={28}
            className="shrink-0 drop-shadow-[0_0_8px_rgba(139,92,246,0.5)]"
            style={{ color: BRAND }}
          />
          <div
            className="font-mono font-bold text-[13px] tracking-[0.06em] text-foreground leading-tight"
            style={{ textShadow: `0 0 10px ${BRAND}44` }}
          >
            <div>TickFlow</div>
            <div>Stock Panel</div>
          </div>
          {/* 桌面三态切换按钮 — 由 DesktopSidebar 注入，靠右放置（负 margin 抵消 px-5 右侧 padding） */}
          <div className="flex-1" />
          <div className="-mr-3">{toggleButton}</div>
        </div>

        <div className="mt-2.5 text-[10px] uppercase tracking-[0.22em] text-secondary">
          Quant · Terminal
        </div>

        <div
          className="mt-3 h-px"
          style={{ background: `linear-gradient(90deg, ${BRAND}88, transparent 80%)` }}
        />

        <TierBadge label={caps?.label ?? ''} hasKey={settingsState?.mode !== 'none'} />
        <AIConfigBadge
          configured={settingsState?.ai_configured ?? settingsState?.has_ai_key}
          model={settingsState?.ai_model}
        />
      </div>

      {/* ===== 导航 ===== */}
      <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-3 space-y-0.5">
        {visibleNavItems.map(({ to, label, icon: Icon, badge }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                isActive
                  ? 'bg-elevated text-foreground font-medium'
                  : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className="h-4 w-4 shrink-0" />
                <span className="flex-1">{label}</span>
                {badge && (
                  <span className="ml-auto inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400 shrink-0">
                    {badge}
                  </span>
                )}
                {to === '/data' && isDataSyncing && (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
                )}
                {to === '/data' && !isDataSyncing && dataSyncJustDone && (
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-bull animate-pulse" />
                )}
                {to === '/monitor' && <MonitorBadge active={isActive} />}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ===== 数据源状态条 ===== */}
      <button
        onClick={() => navigate('/settings?tab=data-sources')}
        className="mx-2 mb-1 flex items-center gap-2 rounded-btn px-2.5 py-2 text-left transition-colors hover:bg-elevated/60 shrink-0 group"
        title="数据源设置"
      >
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
            isCustomActive ? 'bg-accent/15' : 'bg-elevated'
          }`}
        >
          <Database className={`h-3 w-3 ${isCustomActive ? 'text-accent' : 'text-muted'}`} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-medium text-secondary truncate group-hover:text-foreground transition-colors">
              {activeProviderName}
            </span>
            {isCustomActive && (
              <span className="shrink-0 rounded bg-accent/15 px-1 py-px text-[8px] font-semibold uppercase tracking-wider text-accent">
                自定义
              </span>
            )}
          </div>
          <div className="mt-0.5 flex gap-0.5">
            {(['daily', 'adj_factor', 'realtime', 'minute'] as const).map((ds) => {
              const supported = ds === 'daily' || ds === 'adj_factor' || ds === 'realtime' || ds === 'minute'
              const active =
                supported &&
                (isCustomActive ? activeProviderDatasets.includes(ds) : true)
              return (
                <span
                  key={ds}
                  title={ds}
                  className={`h-1 flex-1 rounded-full transition-colors ${
                    active ? 'bg-accent/60' : 'bg-muted/20'
                  }`}
                />
              )
            })}
          </div>
        </div>
      </button>

      {/* ===== 实时行情开关区 ===== */}
      <div className="border-t border-border px-3 py-2.5 shrink-0">
        {isNoneTier && !realtimeProviderName ? (
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-secondary truncate">实时行情</span>
              <span className="text-[10px] text-accent/70 font-medium bg-accent/10 px-1.5 py-0.5 rounded">
                Free+
              </span>
            </div>
            <div className="mt-1.5 text-[10px] leading-snug text-muted">
              免费注册
              <a
                href={TICKFLOW_REGISTER_URL}
                target="_blank"
                rel="noreferrer"
                className="mx-1 inline-flex items-baseline gap-0.5 text-accent/80 hover:text-accent hover:underline"
              >
                TickFlow
                <ExternalLink className="h-2.5 w-2.5 self-center" />
              </a>
              开启个股监控
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full shrink-0 ${
                  realtimeEnabled && isRunning && isTrading
                    ? 'bg-accent animate-pulse'
                    : realtimeEnabled
                      ? 'bg-warning/60'
                      : 'bg-muted'
                }`}
              />
              <span className="text-xs text-secondary truncate">
                实时行情 · {realtimeProviderName || realtimeModeLabel}
              </span>
              <button
                onClick={() => navigate('/settings?tab=monitoring')}
                className="text-secondary hover:text-foreground transition-colors shrink-0"
                title="实时监控设置"
              >
                <Settings className="h-3 w-3" />
              </button>
            </div>
            <button
              onClick={() => handleToggle(!realtimeEnabled)}
              disabled={toggleQuote.isPending || isPaused}
              title={isPaused ? '数据同步运行中，实时行情已临时暂停' : undefined}
              className={`relative inline-flex h-4 w-7 items-center rounded-full shrink-0 transition-colors duration-200 ${
                realtimeEnabled
                  ? 'bg-accent shadow-[0_0_6px_rgba(59,130,246,0.3)]'
                  : 'bg-elevated'
              } ${toggleQuote.isPending || isPaused ? 'opacity-50' : 'cursor-pointer'}`}
            >
              <span
                className={`inline-block h-3 w-3 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  realtimeEnabled ? 'translate-x-[14px]' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>
        )}

        {realtimeEnabled && (!isNoneTier || realtimeProviderName) && (
          <div className="mt-1.5 text-[10px] leading-snug space-y-0.5">
            {isWatchlistMode && !dismissFreeHint && !realtimeProviderName && (
              <div className="flex items-start gap-1 text-amber-400/80">
                <span className="flex-1">监控自选股前 5 只，全市场监控需 Starter+</span>
                <button
                  onClick={() => setDismissFreeHint(true)}
                  className="text-amber-400/50 hover:text-amber-400 shrink-0 transition-colors"
                  title="关闭提示"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </div>
            )}
            {isPaused ? (
              <div className="text-warning/80">数据同步运行中，实时行情已临时暂停</div>
            ) : isRunning && isTrading ? (
              <div className="text-accent">行情运行中</div>
            ) : realtimeEnabled && !isTrading ? (
              <div className="text-warning/70">非交易时段，将在交易时间自动开启</div>
            ) : null}
          </div>
        )}
        {showSidebarQuotes && !isWatchlistMode && (!isNoneTier || !!realtimeProviderName) && (
          <SidebarIndexQuotes rows={sidebarIndexQuotes?.rows} items={sidebarIndexes} />
        )}
      </div>

      {/* ===== 底部：主题 + 设置 ===== */}
      <div className="border-t border-border px-2 py-3 shrink-0">
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <NavLink
            to="/settings"
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex flex-1 items-center justify-between gap-3 px-3 py-2 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                isActive
                  ? 'bg-elevated text-foreground font-medium'
                  : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
              )
            }
          >
            <span className="flex items-center gap-3">
              <Settings className="h-4 w-4 shrink-0" />
              <span>设置</span>
            </span>
            <span className="font-mono text-[10px] text-muted/50 select-none">{version ?? ''}</span>
          </NavLink>
        </div>
      </div>
    </div>
  )
}
