import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { api, type CapabilitiesResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { hasYearlyAccess } from '@/lib/periodAccess'

export function YearlySyncConfig({
  caps,
  onJobStart,
}: {
  caps: CapabilitiesResponse | undefined
  onJobStart?: (jobId: string) => void
}) {
  const qc = useQueryClient()
  const prefs = useQuery({
    queryKey: QK.preferences,
    queryFn: api.preferences,
  })
  const update = useMutation({
    mutationFn: ({ enabled, years }: { enabled: boolean; years: number }) =>
      api.updateYearlySync(enabled, years),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.preferences }),
  })

  const hasAccess = hasYearlyAccess(caps)
  const enabled = prefs.data?.yearly_sync_enabled ?? false
  const years = prefs.data?.yearly_sync_years ?? 10
  const [localYears, setLocalYears] = useState(years)
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => { setLocalYears(years) }, [years])

  const handleToggle = () => {
    if (!hasAccess) return
    update.mutate({ enabled: !enabled, years: localYears })
  }

  const handleJobStart = (jobId?: string) => {
    setIsRunning(true)
    if (jobId && onJobStart) onJobStart(jobId)
  }

  return (
    <div className="px-4 pb-4 pt-3 border-t border-accent/20 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <button
            onClick={handleToggle}
            disabled={!hasAccess}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200 shrink-0 ${
              enabled ? 'bg-accent shadow-[0_0_6px_rgba(61,214,140,0.3)]' : 'bg-elevated'
            } ${!hasAccess ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <span
              className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                enabled ? 'translate-x-[18px]' : 'translate-x-0.5'
              }`}
            />
          </button>
          <span className="text-xs text-foreground font-medium">
            {enabled ? '自动同步' : '已关闭'}
          </span>
        </div>
        {!hasAccess && (
          <span className="text-[10px] text-warning/80 bg-warning/8 rounded px-1.5 py-px font-medium">
            需 stock-sdk 等源
          </span>
        )}
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[10px] text-secondary">同步年数</span>
        <div className="flex items-center gap-2">
          <div className="flex items-center">
            <button
              onClick={() => { const v = Math.max(1, localYears - 1); setLocalYears(v); update.mutate({ enabled, years: v }) }}
              disabled={!hasAccess || !enabled || localYears <= 1}
              className="h-6 w-6 flex items-center justify-center rounded-l-btn bg-elevated border border-border text-secondary hover:bg-border/50 disabled:opacity-30 transition-colors text-xs"
            >
              −
            </button>
            <div
              className={`h-6 w-10 flex items-center justify-center border-y border-border text-[11px] font-mono tabular-nums ${
                enabled ? 'text-foreground bg-base' : 'text-muted bg-elevated/50'
              }`}
            >
              {localYears}
            </div>
            <button
              onClick={() => { const v = Math.min(40, localYears + 1); setLocalYears(v); update.mutate({ enabled, years: v }) }}
              disabled={!hasAccess || !enabled || localYears >= 40}
              className="h-6 w-6 flex items-center justify-center rounded-r-btn bg-elevated border border-border text-secondary hover:bg-border/50 disabled:opacity-30 transition-colors text-xs"
            >
              +
            </button>
          </div>
          <span className="text-[10px] text-muted">年</span>
        </div>
      </div>

      <div className="pt-2 border-t border-border space-y-2.5">
        <div className="text-[10px] text-secondary">向前扩展历史数据</div>
        <YearlyExtendControls
          hasAccess={hasAccess}
          isRunning={isRunning}
          onStart={handleJobStart}
        />
      </div>

      <div className="pt-2 border-t border-border space-y-2.5">
        <div className="text-[10px] text-secondary">立即同步</div>
        <YearlySyncNow
          hasAccess={hasAccess}
          isRunning={isRunning}
          onStart={handleJobStart}
        />
      </div>

      <div className="text-[10px] text-muted">
        年 K · 独立存储于 kline_yearly · 由月线聚合（日历年）
      </div>
    </div>
  )
}

function YearlyExtendControls({
  hasAccess,
  isRunning,
  onStart,
}: {
  hasAccess: boolean
  isRunning: boolean
  onStart: (jobId?: string) => void
}) {
  const qc = useQueryClient()
  const [value, setValue] = useState(1)

  const dataStatus = useQuery({
    queryKey: QK.dataStatus,
    queryFn: api.dataStatus,
  })
  const earliestDate = dataStatus.data?.yearly?.earliest_date ?? null
  const hasData = !!earliestDate

  const extend = useMutation({
    mutationFn: () => api.extendYearlyHistory(value, 'year'),
    onSuccess: (data) => {
      onStart(data.job_id)
      qc.invalidateQueries({ queryKey: QK.pipelineJobs })
      qc.invalidateQueries({ queryKey: QK.dataStatus })
    },
  })

  const estimate = earliestDate
    ? (() => {
        const d = new Date(earliestDate)
        d.setDate(d.getDate() - value * 365)
        return d.toISOString().slice(0, 10)
      })()
    : null

  return (
    <>
      <div className="flex items-center gap-2">
        <div className="flex items-center">
          <button
            onClick={() => setValue(Math.max(1, value - 1))}
            disabled={!hasAccess || isRunning || extend.isPending}
            className="h-6 w-6 flex items-center justify-center rounded-l-btn bg-elevated border border-border text-secondary hover:bg-border/50 disabled:opacity-30 transition-colors text-xs"
          >
            −
          </button>
          <div className="h-6 w-8 flex items-center justify-center border-y border-border text-[11px] font-mono tabular-nums text-foreground bg-base">
            {value}
          </div>
          <button
            onClick={() => setValue(Math.min(10, value + 1))}
            disabled={!hasAccess || isRunning || extend.isPending || value >= 10}
            className="h-6 w-6 flex items-center justify-center rounded-r-btn bg-elevated border border-border text-secondary hover:bg-border/50 disabled:opacity-30 transition-colors text-xs"
          >
            +
          </button>
        </div>
        <span className="text-[10px] text-muted">年</span>
      </div>

      {estimate && (
        <div className="text-[10px] text-muted">
          预计扩展至 <span className="font-mono text-secondary">{estimate}</span>
          {earliestDate && (
            <span> (当前最早: <span className="font-mono text-secondary">{earliestDate}</span>)</span>
          )}
        </div>
      )}

      {!hasData && (
        <div className="text-[10px] text-muted">
          请先使用下方「同步最近年 K」获取基础数据, 再向前扩展历史。
        </div>
      )}

      <button
        onClick={() => extend.mutate()}
        disabled={!hasAccess || !hasData || isRunning || extend.isPending}
        className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-btn bg-accent/90 text-base text-xs font-medium hover:bg-accent disabled:opacity-40 disabled:pointer-events-none transition-colors duration-150"
      >
        {extend.isPending ? (
          <><Loader2 className="h-3 w-3 animate-spin" />请求中…</>
        ) : (
          <>获取数据</>
        )}
      </button>
    </>
  )
}

function YearlySyncNow({
  hasAccess,
  isRunning,
  onStart,
}: {
  hasAccess: boolean
  isRunning: boolean
  onStart: (jobId?: string) => void
}) {
  const qc = useQueryClient()
  const sync = useMutation({
    mutationFn: api.syncYearly,
    onSuccess: (data) => {
      onStart(data.job_id)
      qc.invalidateQueries({ queryKey: QK.pipelineJobs })
      qc.invalidateQueries({ queryKey: QK.dataStatus })
    },
  })

  return (
    <button
      onClick={() => sync.mutate()}
      disabled={!hasAccess || isRunning || sync.isPending}
      className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-btn bg-elevated border border-border text-secondary text-xs font-medium hover:bg-border/50 hover:text-foreground disabled:opacity-40 disabled:pointer-events-none transition-colors duration-150"
    >
      {sync.isPending ? (
        <><Loader2 className="h-3 w-3 animate-spin" />启动中…</>
      ) : (
        <>同步最近年 K</>
      )}
    </button>
  )
}
