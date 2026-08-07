import { Suspense, useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { Loader2, WifiOff } from 'lucide-react'
import { useQuoteStream, useQuoteStreamStatus } from '@/lib/useQuoteStream'
import { usePreferences } from '@/lib/useSharedQueries'
import { useIsDesktop } from '@/lib/useMediaQuery'
import { ToastContainer } from '@/components/Toast'
import { AlertToastContainer } from '@/components/AlertToast'
import { AiAnalysisHost } from '@/components/financials/AiAnalysisHost'
import { AiReportBubble } from '@/components/financials/AiReportBubble'
import { StockAnalysisHost } from '@/components/stock-analysis/StockAnalysisHost'
import { StockAnalysisBubble } from '@/components/stock-analysis/StockAnalysisBubble'
import { DesktopSidebar } from './sidebar/DesktopSidebar'
import { MobileDrawer } from './sidebar/MobileDrawer'
import { setCurrentTotal as setAlertTotal } from '@/lib/monitorBadge'
import { api } from '@/lib/api'

export function Layout() {
  const isDesktop = useIsDesktop()

  // SSE 全局订阅 — 保留在 Layout（需要 prefs 的 realtime_quotes_enabled + sse_refresh_pages）
  const { data: prefs } = usePreferences()
  useQuoteStream(prefs?.realtime_quotes_enabled ?? false, prefs?.sse_refresh_pages)

  // SSE 断线状态 — 保留在 Layout（断线提示是全局浮层，跟侧边栏无关）
  const streamStatus = useQuoteStreamStatus()

  // 监控徽标全局轮询 — 保留在 Layout（setAlertTotal 是全局副作用）
  const alertsTotalQuery = useQuery({
    queryKey: ['alerts-total'],
    queryFn: () => api.alertsList({ days: 7, limit: 1 }),
    refetchInterval: 15000,
    refetchIntervalInBackground: true,
    select: (data) => data.total,
  })
  useEffect(() => {
    if (alertsTotalQuery.data != null) setAlertTotal(alertsTotalQuery.data)
  }, [alertsTotalQuery.data])

  return (
    <div className="h-screen flex bg-base text-foreground overflow-hidden relative">
      {isDesktop ? <DesktopSidebar /> : <MobileDrawer />}
      <motion.main
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="h-full flex-1 overflow-auto scrollbar-gutter-stable"
      >
        {/* SSE 断线提示 */}
        {streamStatus === 'reconnecting' && (
          <div
            role="status"
            aria-live="polite"
            className="fixed bottom-4 left-1/2 z-[9998] flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 text-[11px] font-medium text-warning shadow-lg backdrop-blur-md"
          >
            <WifiOff className="h-3 w-3 shrink-0 animate-pulse" />
            与服务连接已断开 · 正在重连
          </div>
        )}
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-24">
              <Loader2 className="h-5 w-5 animate-spin text-muted" />
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </motion.main>
      <ToastContainer />
      <AlertToastContainer />
      <AiAnalysisHost />
      <AiReportBubble />
      <StockAnalysisHost />
      <StockAnalysisBubble />
    </div>
  )
}
