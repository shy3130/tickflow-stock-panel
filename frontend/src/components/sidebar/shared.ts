import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  Star,
  ScanSearch,
  History,
  FileText,
  Tags,
  TrendingUp,
  Flame,
  BarChart3,
  Gauge,
  Layers3,
  Landmark,
  RadioTower,
  BookOpenCheck,
  Database,
} from 'lucide-react'
import { api, type IndexQuote } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useToggleRealtimeQuotes } from '@/lib/useSharedMutations'

// 品牌色 — 只用于 logo / brand 区域
export const BRAND = '#8B5CF6'
export const TICKFLOW_REGISTER_URL = 'https://tickflow.org/auth/register?ref=V3KDKGXPEA'

export const CORE_INDEXES = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
] as const

export type CoreIndex = (typeof CORE_INDEXES)[number]

// 内置导航项（扩展分析菜单在 SidebarContent 内动态合并）
export const NAV_ITEMS = [
  { to: '/', label: '看板', icon: LayoutDashboard },
  { to: '/watchlist', label: '自选', icon: Star },
  { to: '/screener', label: '策略', icon: ScanSearch },
  { to: '/backtest', label: '回测', icon: History },
  { to: '/stock-analysis', label: '个股分析', icon: TrendingUp },
  { to: '/limit-ladder', label: '连板梯队', icon: Flame },
  { to: '/concept-analysis', label: '概念分析', icon: Layers3 },
  { to: '/industry-analysis', label: '行业分析', icon: Landmark },
  { to: '/financials', label: '财务分析', icon: FileText },
  { to: '/monitor', label: '监控中心', icon: RadioTower },
  { to: '/regime', label: '市场环境', icon: Gauge, badge: 'beta' },
  { to: '/review', label: '复盘', icon: BookOpenCheck },
  { to: '/indices', label: '指数', icon: BarChart3 },
  { to: '/data', label: '数据', icon: Database },
] as const

export type NavItem = { to: string; label: string; icon: typeof Gauge; badge?: string }

// ===== 指数格式化工具 =====
export function fmtIndexValue(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(2)
}

export function fmtIndexPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}

export function indexPctClass(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return 'text-muted'
  const n = Number(v)
  if (n === 0) return 'text-foreground'
  return n > 0 ? 'text-bull' : 'text-bear'
}

// ===== 数据同步状态 hook (从 Layout.tsx 抽出) =====
// 返回 { isDataSyncing, dataSyncJustDone }
// isDataSyncing: 有活跃 pipeline job
// dataSyncJustDone: isDataSyncing 从 true→false 时置 true, 3 秒后自动复位
export function useDataSyncStatus() {
  const { data: pipelineJobs } = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(1),
    refetchInterval: (query) => (query.state.data?.active_id ? 2000 : 15000),
    refetchIntervalInBackground: true,
  })

  const isDataSyncing = !!pipelineJobs?.active_id
  const [dataSyncJustDone, setDataSyncJustDone] = useState(false)
  const prevSyncingRef = useRef(false)

  useEffect(() => {
    if (prevSyncingRef.current && !isDataSyncing) {
      setDataSyncJustDone(true)
      const t = setTimeout(() => setDataSyncJustDone(false), 3000)
      prevSyncingRef.current = isDataSyncing
      return () => clearTimeout(t)
    }
    prevSyncingRef.current = isDataSyncing
  }, [isDataSyncing])

  return { isDataSyncing, dataSyncJustDone }
}

// ===== 导航项合并/排序/隐藏 hook (SidebarContent + IconRailContent 共享) =====
type AnalysisMenusData = { items?: Array<{ id: string; label: string; visible: boolean; icon?: string }> } | undefined
type PrefsData = {
  nav_order?: string[]
  nav_hidden?: string[]
} | undefined

/**
 * 合并内置导航 + 扩展分析菜单，按用户自定义排序，过滤隐藏项。
 */
export function useVisibleNavItems(analysisMenus: AnalysisMenusData, prefs: PrefsData): NavItem[] {
  const analysisNav: NavItem[] = (analysisMenus?.items ?? [])
    .filter((m) => m.visible)
    .map((m) => ({ to: `/analysis/${m.id}`, label: m.label, icon: m.icon === 'tags' ? Tags : BarChart3 }))

  const allNav: NavItem[] = [...NAV_ITEMS, ...analysisNav]
  const savedOrder = prefs?.nav_order ?? []

  const navItems =
    savedOrder.length > 0
      ? (() => {
          const byTo = new Map(allNav.map((n) => [n.to, n]))
          const ordered = savedOrder
            .map((id) => byTo.get(id) ?? byTo.get(`/analysis/${id}`))
            .filter(Boolean)
          const seen = new Set(ordered.map((n) => n!.to))
          return [...(ordered as typeof allNav), ...allNav.filter((n) => !seen.has(n.to))]
        })()
      : allNav

  const hiddenIds = new Set(prefs?.nav_hidden ?? [])
  return navItems.filter(
    (n) => !hiddenIds.has(n.to) && !hiddenIds.has(n.to.replace(/^\/analysis\//, '')),
  )
}

// ===== 实时行情开关 toggle hook (SidebarContent + IconRailContent 共享) =====

/**
 * 实时行情开关逻辑：直接调 API，后端校验档位。
 * 与设置页 Monitoring.tsx 的 handleToggleQuote 保持一致，
 * 不在前端拦截 None 档（后端会返回 realtime_allowed: false，UI 自动更新为关闭态）。
 */
export function useRealtimeToggle(isTrading: boolean) {
  const toggleQuote = useToggleRealtimeQuotes()

  const handleToggle = useCallback(
    async (enabled: boolean) => {
      await toggleQuote.mutateAsync(enabled)
      if (enabled && isTrading) {
        api.intradayRefresh().catch(() => {})
      }
    },
    [toggleQuote, isTrading],
  )

  return { handleToggle, toggleQuote }
}
