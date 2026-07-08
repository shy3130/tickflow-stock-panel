import { useSyncExternalStore } from 'react'

/**
 * 参数优化任务管理 (SSE 模式 + 重连)。镜像 backtestTask, 结果为排名 dict。
 */

export interface OptimizeProgress {
  type: string
  done: number
  total: number
  best_score: number | null
}

export interface OptimizeResultRow {
  params: Record<string, any>
  objective_raw: number | null
  stats?: Record<string, any>
  rank: number
  error?: string
}

export interface OptimizeResult {
  objective: string
  direction: string
  n_combinations: number
  n_completed: number
  best_params: Record<string, any> | null
  best_score: number | null
  results: OptimizeResultRow[]
  elapsed_ms: number
}

export interface OptimizerTask {
  id: number
  isPending: boolean
  result: OptimizeResult | null
  progress: OptimizeProgress | null
  error: string | null
}

export interface StartOptimizeParams {
  strategy_id: string
  param_grid: Record<string, any>
  objective: string
  direction?: string
  max_workers?: number
  symbols?: string[] | null
  start?: string | null
  end?: string | null
  matching?: string
  fees_pct?: number
  commission_pct?: number
  stamp_tax_pct?: number
  slippage_bps?: number
  max_positions?: number
  max_exposure_pct?: number
  initial_capital?: number
  position_sizing?: string
  mode?: 'position' | 'full'
  holding_days?: number
}

let current: OptimizerTask | null = null
const listeners = new Set<() => void>()
let taskSeq = 0
let eventSource: EventSource | null = null
let currentJobKey: string | null = null

const RECONNECT_KEY = 'optimizer_reconnect'
const JOB_KEY_KEY = 'optimizer_job_key'

function emit() {
  listeners.forEach(fn => fn())
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') sp.set(k, String(v))
  }
  return sp.toString()
}

function connectSSE(url: string): void {
  const id = current?.id ?? ++taskSeq

  if (eventSource) {
    eventSource.close()
    eventSource = null
  }

  const es = new EventSource(url)
  eventSource = es

  // 首事件: 后端回吐 job_key, 存下供 cancel 直接引用 (无需前端重算)
  es.addEventListener('job', (e: MessageEvent) => {
    try {
      const key = JSON.parse(e.data)?.key
      if (key) {
        currentJobKey = key
        localStorage.setItem(JOB_KEY_KEY, key)
      }
    } catch { /* ignore */ }
  })

  es.addEventListener('progress', (e: MessageEvent) => {
    if (current?.id !== id) return
    try {
      const prog = JSON.parse(e.data) as OptimizeProgress
      current = { ...current, progress: prog }
      emit()
    } catch { /* ignore */ }
  })

  es.addEventListener('done', (e: MessageEvent) => {
    if (current?.id !== id) return
    try {
      const result = JSON.parse(e.data) as OptimizeResult
      current = { ...current, isPending: false, result, error: null }
      emit()
    } catch {
      current = { ...current, isPending: false, error: '结果解析失败' }
      emit()
    }
    es.close()
    eventSource = null
    currentJobKey = null
    localStorage.removeItem(RECONNECT_KEY)
    localStorage.removeItem(JOB_KEY_KEY)
  })

  es.addEventListener('error', (e: MessageEvent) => {
    if (current?.id !== id) return
    if (e.data) {
      try {
        const msg = JSON.parse(e.data)?.message ?? '优化出错'
        current = { ...current, isPending: false, error: msg }
        emit()
      } catch {
        current = { ...current, isPending: false, error: '优化出错' }
        emit()
      }
      es.close()
      eventSource = null
      localStorage.removeItem(RECONNECT_KEY)
    }
    // 无 data: 连接异常断开, 自动重连
  })
}

export function startOptimize(params: StartOptimizeParams): void {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }

  const id = ++taskSeq
  current = { id, isPending: true, result: null, progress: null, error: null }
  emit()

  const qs = buildQuery({
    strategy_id: params.strategy_id,
    param_grid: JSON.stringify(params.param_grid),
    objective: params.objective,
    direction: params.direction,
    max_workers: params.max_workers,
    symbols: params.symbols?.join(','),
    start: params.start ?? undefined,
    end: params.end ?? undefined,
    matching: params.matching,
    fees_pct: params.fees_pct,
    commission_pct: params.commission_pct,
    stamp_tax_pct: params.stamp_tax_pct,
    slippage_bps: params.slippage_bps,
    max_positions: params.max_positions,
    max_exposure_pct: params.max_exposure_pct,
    initial_capital: params.initial_capital,
    position_sizing: params.position_sizing,
    mode: params.mode,
    holding_days: params.holding_days,
  })

  localStorage.setItem(RECONNECT_KEY, qs)
  connectSSE(`/api/backtest/optimize/stream?${qs}`)
}

export async function stopOptimize(): Promise<void> {
  const jobKey = currentJobKey ?? localStorage.getItem(JOB_KEY_KEY)
  if (jobKey) {
    await fetch('/api/backtest/optimize/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_key: jobKey }),
    }).catch(() => {})
  }
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  if (current?.isPending) {
    current = { ...current, isPending: false, error: '已取消' }
    emit()
  }
  currentJobKey = null
  localStorage.removeItem(RECONNECT_KEY)
  localStorage.removeItem(JOB_KEY_KEY)
}

export function clearOptimize(): void {
  current = null
  emit()
}

export function tryReconnectOptimize(): boolean {
  const qs = localStorage.getItem(RECONNECT_KEY)
  if (!qs) return false
  const id = ++taskSeq
  current = { id, isPending: true, result: null, progress: null, error: null }
  emit()
  connectSSE(`/api/backtest/optimize/stream?${qs}`)
  return true
}

export function useOptimizerTask(): OptimizerTask | null {
  return useSyncExternalStore(subscribe, () => current, () => null)
}
