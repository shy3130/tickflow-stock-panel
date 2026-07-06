/**
 * 数据源快速选择器 —— 紧凑卡片, 供引导页 / 看板首次拉取处内嵌复用。
 *
 * 设计: 每个源一张可点卡片, 点击即切换为当前数据源(非付费 key 输入)。
 * 高亮跟随「当前启用源」(activeName), 不做「选中待编辑」态, 避免误导。
 * stock-sdk 无 Node 环境时 available=false, 卡片置灰但仍可切换(抓取时按数据集回退)。
 */
import { Check, Database, Loader2, Zap } from 'lucide-react'
import { useDataSourceList, useSwitchProvider } from '@/lib/dataProviders'

const DATASET_LABEL: Record<string, string> = {
  daily: '日K',
  adj_factor: '除权',
  realtime: '实时',
  minute: '分钟',
}

export function DataSourceQuickPicker({
  onSwitched,
  compact = false,
}: {
  onSwitched?: (name: string) => void
  compact?: boolean
}) {
  const { items, activeName } = useDataSourceList()
  const switchProvider = useSwitchProvider({ onSwitched })

  if (items.length === 0) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在加载数据源…
      </div>
    )
  }

  return (
    <div className={`grid gap-2 ${compact ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1 sm:grid-cols-2'}`}>
      {items.map((item) => {
        const isActive = activeName === item.name
        const unavailable = item.available === false
        const pending = switchProvider.isPending && switchProvider.variables?.name === item.name
        return (
          <button
            key={item.name}
            type="button"
            onClick={() => {
              if (isActive) return
              switchProvider.mutate({ name: item.name, item })
            }}
            disabled={switchProvider.isPending || isActive}
            className={`group relative text-left rounded-lg border px-3 py-2.5 transition-all ${
              isActive
                ? 'border-accent/60 bg-accent/[0.07] ring-1 ring-accent/30 cursor-default'
                : 'border-border/60 bg-elevated/20 hover:border-accent/30 hover:bg-elevated/40'
            } ${unavailable ? 'opacity-70' : ''}`}
          >
            <div className="flex items-center gap-2">
              <span
                className={`h-6 w-6 rounded-md flex items-center justify-center shrink-0 ${
                  isActive ? 'bg-accent/15' : 'bg-elevated/60'
                }`}
              >
                <Database className={`h-3.5 w-3.5 ${isActive ? 'text-accent' : 'text-muted'}`} />
              </span>
              <span
                className={`text-sm truncate flex-1 min-w-0 ${
                  isActive ? 'font-medium text-foreground' : 'text-secondary'
                }`}
              >
                {item.display_name}
              </span>
              {unavailable && (
                <span className="text-[9px] text-danger/70 uppercase tracking-wider shrink-0" title={item.status}>
                  不可用
                </span>
              )}
              {isActive ? (
                <span className="inline-flex items-center gap-0.5 text-[10px] text-accent shrink-0">
                  <Check className="h-3 w-3" /> 使用中
                </span>
              ) : pending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-accent shrink-0" />
              ) : (
                <span className="inline-flex items-center gap-0.5 text-[10px] text-muted group-hover:text-accent transition-colors shrink-0">
                  <Zap className="h-3 w-3" /> 使用
                </span>
              )}
            </div>
            {!compact && item.datasets.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1 pl-8">
                {item.datasets.map((ds) => (
                  <span key={ds} className="text-[9px] text-muted/60 bg-elevated/60 px-1 py-0.5 rounded">
                    {DATASET_LABEL[ds] || ds}
                  </span>
                ))}
              </div>
            )}
            {!compact && item.description && (
              <p className="mt-1 pl-8 text-[10px] text-muted/70 leading-snug line-clamp-2">{item.description}</p>
            )}
          </button>
        )
      })}
    </div>
  )
}
