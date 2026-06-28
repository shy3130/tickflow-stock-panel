import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Watchlist } from './pages/Watchlist'
import { Screener } from './pages/Screener'
import { Backtest } from './pages/Backtest'
import { Financials } from './pages/Financials'
import { Onboarding } from './pages/Onboarding'
import { Data } from './pages/Data'
import { Monitor } from './pages/Monitor'
import { Trading } from './pages/Trading'
import { Dashboard } from './pages/Dashboard'
import { AnalysisDetail } from './pages/AnalysisDetail'
import { ConceptAnalysis } from './pages/ConceptAnalysis'
import { IndustryAnalysis } from './pages/IndustryAnalysis'
import { StockAnalysis } from './pages/StockAnalysis'
import { LimitUpLadder } from './pages/LimitUpLadder'
import { Branding } from './pages/Branding'
import { Settings } from './pages/Settings'
import { Indices } from './pages/Indices'
import { Dev } from './pages/Dev'
import { useSettings } from './lib/useSharedQueries'
import { Logo } from './components/Logo'

// 首次使用守卫 —— 未完成向导则重定向到 /onboarding
// 只挂在根路由上;/onboarding 本身不被守卫,避免循环重定向。
// settings 由 Layout 预取,守卫判定不产生额外请求。
function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const settings = useSettings()

  // 加载中 或 正在后台重新请求 → 显示占位,避免用旧缓存误判
  // (根治 invalidate 触发重取未返回时, 守卫用旧 onboarding_completed=false 误重定向的竞态)
  if (settings.isLoading || settings.isFetching) {
    return (
      <div className="min-h-screen bg-base grid place-items-center">
        <div className="flex flex-col items-center gap-3 text-muted">
          <Logo size={28} className="text-foreground" />
          <div className="text-xs">加载中…</div>
        </div>
      </div>
    )
  }

  // 查询出错或字段缺失时不拦截 —— 宁可放行,也不把用户卡在空白页
  if (settings.data && settings.data.onboarding_completed === false) {
    return <Navigate to="/onboarding" replace />
  }

  return <>{children}</>
}

export const router = createBrowserRouter([
  { path: '/onboarding', element: <Onboarding /> },
  {
    path: '/',
    element: (
      <OnboardingGuard>
        <Layout />
      </OnboardingGuard>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'overview', element: <Navigate to="/" replace /> },
      { path: 'analysis', element: <Navigate to="/settings?tab=ext-pages" replace /> },
      { path: 'analysis/:menuId', element: <AnalysisDetail /> },
      { path: 'concept-analysis', element: <ConceptAnalysis /> },
      { path: 'industry-analysis', element: <IndustryAnalysis /> },
      { path: 'stock-analysis', element: <StockAnalysis /> },
      { path: 'watchlist', element: <Watchlist /> },
      { path: 'screener', element: <Screener /> },
      { path: 'backtest', element: <Backtest /> },
      { path: 'financials', element: <Financials /> },
      { path: 'data', element: <Data /> },
      { path: 'monitor', element: <Monitor /> },
      { path: 'trading', element: <Trading /> },
      { path: 'limit-ladder', element: <LimitUpLadder /> },
      { path: 'indices', element: <Indices /> },
      { path: 'branding', element: <Branding /> },
      { path: 'settings', element: <Settings /> },
      // 隐藏路由：开发者工具（不暴露在菜单，仅供调试）
      { path: 'dev', element: <Dev /> },
      // 旧路由兼容重定向
      { path: 'settings/keys', element: <Navigate to="/settings?tab=account" replace /> },
      { path: 'settings/tushare', element: <Navigate to="/settings?tab=tushare" replace /> },
      { path: 'settings/ai', element: <Navigate to="/settings?tab=ai" replace /> },
      { path: 'settings/queries', element: <Navigate to="/settings?tab=queries" replace /> },
    ],
  },
])
