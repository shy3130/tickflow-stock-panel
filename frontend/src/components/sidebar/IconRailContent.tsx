import { useState, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Settings,
  Loader2,
  CheckCircle2,
  RadioTower,
} from 'lucide-react'
import {
  useCapabilities,
  usePreferences,
  useQuoteStatus,
} from '@/lib/useSharedQueries'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { tierRank } from '@/lib/capability-labels'
import { Logo } from '../Logo'
import { cn } from '@/lib/cn'
import {
  BRAND,
  CORE_INDEXES,
  useDataSyncStatus,
  useVisibleNavItems,
  useRealtimeToggle,
} from './shared'
import { ThemeToggle, MonitorBadge } from './components'
import { IndexQuoteCarousel } from './IndexQuoteCarousel'

interface IconRailContentProps {
  /** 桌面三态切换按钮 */
  toggleButton?: React.ReactNode
}

export function IconRailContent({ toggleButton }: IconRailContentProps) {
  // ===== Fixed 定位 tooltip（绕开 aside overflow-hidden 限制）=====
  const [tooltip, setTooltip] = useState<{ text: React.ReactNode; x: number; y: number } | null>(null)
  const showTooltip = useCallback((text: React.ReactNode, e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setTooltip({ text, x: rect.right + 6, y: rect.top + rect.height / 2 })
  }, [])
  const hideTooltip = useCallback(() => setTooltip(null), [])

  // ===== 按需 query（图标条态精简，只取需要的）=====
  const { data: caps } = useCapabilities()
  const { data: prefs } = usePreferences()
  const { data: quoteStatus } = useQuoteStatus({ poll: true })
  const { data: dataSources } = useQuery({
    queryKey: QK.dataSources,
    queryFn: api.dataSources,
    staleTime: 60_000,
  })
  const { data: analysisMenus } = useQuery({
    queryKey: QK.analysisMenus,
    queryFn: api.analysisMenus,
  })

  const { isDataSyncing, dataSyncJustDone } = useDataSyncStatus()

  const realtimeEnabled = prefs?.realtime_quotes_enabled ?? false
  const isRunning = quoteStatus?.running ?? false
  const isTrading = quoteStatus?.is_trading_hours ?? false
  const isPaused = quoteStatus?.paused ?? false
  const tier = tierRank(caps?.label ?? '')
  const isNoneTier = tier < 0
  const isWatchlistMode = tier === 0
  const realtimeProvider = prefs?.realtime_data_provider
  const realtimeProviderName =
    realtimeProvider && realtimeProvider !== 'tickflow'
      ? dataSources?.custom?.find((s) => s.name === realtimeProvider)?.display_name || realtimeProvider
      : null

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

  // 档位色点颜色（Logo 角标用）
  const tierBase = (caps?.label ?? '').split(' ')[0].split('+')[0].toLowerCase()
  const tierDotColor: Record<string, string> = {
    none: 'bg-zinc-600',
    free: 'bg-zinc-500',
    starter: 'bg-blue-500',
    pro: 'bg-purple-500',
    expert: 'bg-gradient-to-br from-blue-500 via-purple-500 to-amber-500',
  }
  const dotClass = tierDotColor[tierBase] || tierDotColor.none

  // ===== 共享 hook：实时行情开关逻辑 + 导航项合并 =====
  const { handleToggle, toggleQuote } = useRealtimeToggle(isTrading)
  const visibleNavItems = useVisibleNavItems(analysisMenus, prefs)

  // 实时行情按钮状态文字
  const realtimeStatusText = isPaused
    ? '数据同步运行中，已暂停'
    : isRunning && isTrading
      ? '行情运行中'
      : realtimeEnabled && !isTrading
        ? '非交易时段'
        : '已关闭'
  const realtimeModeLabel = isWatchlistMode ? '自选股' : realtimeProviderName || '全市场'

  return (
    <div className="flex flex-col h-full min-h-0 w-14">
      {/* Logo 缩略 + 档位色点角标 */}
      <div className="relative py-3 shrink-0 w-14 h-10 flex justify-center items-center">
        <Logo size={24} style={{ color: BRAND }} />
        <span
          className={`absolute bottom-2 right-3 h-2 w-2 rounded-full ${dotClass}`}
          title={caps?.label || 'None'}
        />
      </div>

      {/* 切换按钮 */}
      {toggleButton && <div className="shrink-0 w-14 flex justify-center">{toggleButton}</div>}

      {/* Nav 仅 icon */}
      <nav className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden w-14 py-2 space-y-1">
        {visibleNavItems.map(({ to, label, icon: Icon, badge }) => (
          <NavLink
            key={to}
            to={to}
            onMouseEnter={(e) => showTooltip(<>{label}{badge && <span className="ml-1 text-amber-400">[{badge}]</span>}</>, e)}
            onMouseLeave={hideTooltip}
            className={({ isActive }) =>
              cn(
                'group relative flex items-center justify-center h-9 w-14 rounded-btn transition-colors duration-150 ease-smooth',
                isActive
                  ? 'bg-accent/15 text-accent'
                  : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={cn('h-4 w-4 shrink-0', isActive && 'text-accent')}
                />
                {/* 数据同步状态角标 */}
                {to === '/data' && isDataSyncing && (
                  <Loader2 className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 animate-spin text-accent" />
                )}
                {to === '/data' && !isDataSyncing && dataSyncJustDone && (
                  <CheckCircle2 className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 text-bull" />
                )}
                {/* 监控徽标小红点 */}
                {to === '/monitor' && <MonitorBadge active={isActive} variant="dot" />}
                {/* beta 标记小点 */}
                {badge && (
                  <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-amber-400" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* 实时行情 RadioTower 图标按钮 */}
      {!isNoneTier || realtimeProviderName ? (
        <button
          onClick={() => handleToggle(!realtimeEnabled)}
          disabled={toggleQuote.isPending || isPaused}
          onMouseEnter={(e) => showTooltip(`实时行情 · ${realtimeModeLabel} · ${realtimeStatusText}`, e)}
          onMouseLeave={hideTooltip}
          className="group relative mt-4 mb-1 flex h-9 w-14 items-center justify-center rounded-btn transition-colors duration-150 ease-smooth hover:bg-elevated disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
        >
          <RadioTower
            className={cn(
              'h-4 w-4 shrink-0',
              realtimeEnabled && isRunning && isTrading
                ? 'text-accent'
                : realtimeEnabled
                  ? 'text-warning'
                  : 'text-muted',
            )}
          />
        </button>
      ) : null}

      {/* 指数轮播 */}
      {showSidebarQuotes && !isWatchlistMode && (!isNoneTier || !!realtimeProviderName) && (
        <IndexQuoteCarousel quotes={sidebarIndexQuotes?.rows} items={sidebarIndexes} />
      )}

      {/* 底部：主题 + 设置 */}
      <div className="border-t border-border py-2 shrink-0 flex flex-col gap-1 w-14">
        <div className="w-14 flex justify-center">
          <ThemeToggle />
        </div>
        <NavLink
          to="/settings"
          onMouseEnter={(e) => showTooltip('设置', e)}
          onMouseLeave={hideTooltip}
          className={({ isActive }) =>
            cn(
              'group relative flex h-9 w-14 items-center justify-center rounded-btn transition-colors duration-150 ease-smooth',
              isActive
                ? 'bg-accent/15 text-accent'
                : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
            )
          }
        >
          <Settings className="h-4 w-4 shrink-0" />
        </NavLink>
      </div>

      {/* Fixed 定位 tooltip — 绕开 aside overflow-hidden */}
      {tooltip && (
        <div
          className="fixed z-[9999] pointer-events-none whitespace-nowrap rounded bg-elevated px-2 py-1 text-xs text-foreground shadow-lg"
          style={{ left: tooltip.x, top: tooltip.y, transform: 'translateY(-50%)' }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  )
}
