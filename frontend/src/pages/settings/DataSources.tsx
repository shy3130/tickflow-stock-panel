import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, Database, Plus, RefreshCw, Zap, FileWarning } from 'lucide-react'
import { api, type DataSourceItem } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { usePreferences } from '@/lib/useSharedQueries'
import { toast } from '@/components/Toast'
import { DataSourceEditor } from './DataSourceEditor'

const DATASET_LABEL: Record<string, string> = {
  daily: '日K',
  adj_factor: '除权',
  realtime: '实时',
  minute: '分钟',
}

export function SettingsDataSourcesPanel() {
  const qc = useQueryClient()
  const prefs = usePreferences()
  const sources = useQuery({ queryKey: QK.dataSources, queryFn: api.dataSources })
  const [selected, setSelected] = useState<string>('tickflow') // 当前在右侧编辑的源 name
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const reload = useMutation({
    mutationFn: api.reloadDataSources,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.dataSources })
      toast('配置已重新加载', 'success')
    },
  })

  const remove = useMutation({
    mutationFn: (name: string) => api.deleteDataSource(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.dataSources })
      qc.invalidateQueries({ queryKey: QK.preferences })
      setSelected('tickflow')
      setConfirmDelete(null)
      toast('数据源已删除', 'success')
    },
  })

  const switchProvider = useMutation({
    mutationFn: (name: string) => {
      if (name === 'tickflow') {
        return api.updateDataProviders({
          daily_data_provider: 'tickflow',
          adj_factor_provider: 'same_as_daily',
          realtime_data_provider: 'tickflow',
          minute_data_provider: 'tickflow',
          financial_data_provider: 'tickflow',
        })
      }
      // 按目标源声明的数据集精确切换; 未声明的数据集回落 tickflow。
      const item = allItems.find(s => s.name === name)
      const ds = new Set(item?.datasets ?? ['daily', 'realtime'])
      return api.updateDataProviders({
        daily_data_provider: ds.has('daily') ? name : 'tickflow',
        adj_factor_provider: 'same_as_daily',
        realtime_data_provider: ds.has('realtime') ? name : 'tickflow',
        minute_data_provider: ds.has('minute') ? name : 'tickflow',
        financial_data_provider: ds.has('financial') ? name : 'tickflow',
      })
    },
    onSuccess: (_data, name) => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      // 切换后让右侧详情/选中态跟随新的当前源, 避免旧源残留高亮造成误导
      setSelected(name)
      toast('数据源已切换', 'success')
    },
  })

  const editExisting = useMutation({
    mutationFn: (name: string) => api.dataSource(name),
    onSuccess: (_data, name) => setSelected(name),
  })

  const builtin: DataSourceItem[] = sources.data?.builtin ?? []
  const customList: DataSourceItem[] = sources.data?.custom ?? []
  const errors = sources.data?.errors ?? []
  const activeName = prefs.data?.daily_data_provider || 'tickflow'

  // 首次进入时让右侧详情默认对准「当前启用源」, 而非硬编码 tickflow。
  // 用户手动点选后不再自动跟随(syncedRef 只放行一次)。
  const syncedRef = useRef(false)
  useEffect(() => {
    if (syncedRef.current) return
    if (!prefs.data) return
    syncedRef.current = true
    if (activeName !== 'tickflow' && selected === 'tickflow') setSelected(activeName)
  }, [prefs.data, activeName, selected])
  const builtinNames = new Set(builtin.map(b => b.name))
  const isBuiltin = (name: string) => builtinNames.has(name)

  // 顶部数据源选择列表 (内置 + 自定义 + 新增)
  const allItems = [
    ...builtin,
    ...customList,
  ]

  const selectedCustom = customList.find(s => s.name === selected)

  return (
    <div className="space-y-5 max-w-5xl">
      {/* ===== 顶部: 当前数据源 + 数据源选择 (一个大卡片) ===== */}
      <section className="rounded-card border border-border bg-surface p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <Database className="h-4 w-4 text-secondary" />
            <h2 className="text-sm font-medium text-foreground">数据源</h2>
            <span className="text-[10px] text-muted/40 font-mono truncate max-w-[280px]" title={sources.data?.config_dir}>
              {sources.data?.config_dir}
            </span>
          </div>
          <button
            onClick={() => reload.mutate()}
            disabled={reload.isPending}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn text-xs text-muted hover:text-foreground hover:bg-elevated transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${reload.isPending ? 'animate-spin' : ''}`} />
            重新加载
          </button>
        </div>

        {/* 当前数据源状态 */}
        <div className="flex items-center gap-2 mb-4 px-3 py-2.5 rounded-lg bg-elevated/30">
          <span className="text-[10px] uppercase tracking-widest text-muted">当前</span>
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
          <span className="text-sm font-medium text-foreground">
            {allItems.find(s => s.name === activeName)?.display_name || activeName}
          </span>
        </div>

        {/* 数据源选择 - 横向卡片列表 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {allItems.map(item => {
            const isActive = activeName === item.name
            const isSelected = selected === item.name
            return (
              <div
                key={item.name}
                onClick={() => {
                  setSelected(item.name)
                  if (!isBuiltin(item.name)) {
                    editExisting.mutate(item.name)
                  }
                }}
                className={`relative cursor-pointer text-left rounded-lg border px-3.5 py-3 transition-all ${
                  isActive
                    ? 'border-accent/60 bg-accent/[0.07] ring-1 ring-accent/30'
                    : isSelected
                      ? 'border-accent/30 bg-elevated/40'
                      : 'border-border/60 bg-elevated/20 hover:bg-elevated/40'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${isActive ? 'bg-accent' : 'bg-transparent border border-muted/40'}`} />
                  <span className={`text-sm truncate flex-1 ${isActive ? 'font-medium text-foreground' : 'text-secondary'}`}>
                    {item.display_name}
                  </span>
                  {isBuiltin(item.name) && (
                    <span className="text-[9px] text-muted/50 uppercase tracking-wider shrink-0">内置</span>
                  )}
                  {item.available === false && (
                    <span className="text-[9px] text-danger/70 uppercase tracking-wider shrink-0" title={item.status}>不可用</span>
                  )}
                  {isActive ? (
                    <span className="inline-flex items-center gap-0.5 text-[9px] text-accent shrink-0">
                      <Check className="h-2.5 w-2.5" /> 使用中
                    </span>
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); switchProvider.mutate(item.name) }}
                      disabled={switchProvider.isPending}
                      className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium bg-accent/10 text-accent hover:bg-accent/20 transition-colors disabled:opacity-50"
                    >
                      使用
                    </button>
                  )}
                </div>
                {item.datasets.length > 0 && (
                  <div className="flex flex-wrap gap-1 ml-3.5">
                    {item.datasets.map(ds => (
                      <span key={ds} className="text-[9px] text-muted/60 bg-elevated/60 px-1 py-0.5 rounded">
                        {DATASET_LABEL[ds] || ds}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          {/* 新增数据源卡片 */}
          <button
            onClick={() => setSelected('__new__')}
            className={`rounded-lg border border-dashed px-3.5 py-3 transition-all flex items-center justify-center gap-1.5 text-sm ${
              selected === '__new__'
                ? 'border-accent/50 bg-accent/5 text-accent'
                : 'border-border/50 text-muted hover:text-foreground hover:border-border hover:bg-elevated/30'
            }`}
          >
            <Plus className="h-3.5 w-3.5" />
            新增数据源
          </button>
        </div>

        {/* 错误提示 */}
        {errors.length > 0 && (
          <div className="mt-3 flex items-start gap-1.5 px-3 py-2 rounded-lg bg-danger/5 border border-danger/20">
            <FileWarning className="h-3.5 w-3.5 text-danger shrink-0 mt-0.5" />
            <div className="text-[11px] text-danger/80 leading-relaxed space-y-0.5">
              {errors.map((err, idx) => (
                <div key={idx}>
                  <span className="font-mono">{err.name || err.path}</span>: {err.errors.join('; ')}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-3 flex items-center gap-3 text-[10px] text-muted/50">
          <span>单击编辑</span>
          <span className="text-muted/30">·</span>
          <span>点「使用」切换为当前数据源</span>
          <span className="text-muted/30">·</span>
          <span>未启用的数据集自动回退 TickFlow</span>
        </div>
      </section>

      {/* ===== 下方: 编辑区 ===== */}
      <AnimatePresence mode="wait">
        <motion.div
          key={selected}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15 }}
        >
          {selected === 'tickflow' ? (
            <TickFlowDetail
              active={activeName === 'tickflow'}
              onSwitch={() => switchProvider.mutate('tickflow')}
              switching={switchProvider.isPending}
            />
          ) : isBuiltin(selected) ? (
            <BuiltinDetail
              item={builtin.find(b => b.name === selected)!}
              active={activeName === selected}
              onSwitch={() => switchProvider.mutate(selected)}
              switching={switchProvider.isPending}
            />
          ) : (
            <DataSourceEditor
              key={selected}
              initial={null}
              existingName={selected === '__new__' ? undefined : selected}
              onCancel={() => setSelected('tickflow')}
              onSaved={() => {
                qc.invalidateQueries({ queryKey: QK.dataSources })
                // 强制清除该源的详情缓存, 下次编辑重新拉取最新配置
                if (selected !== '__new__') {
                  qc.removeQueries({ queryKey: ['data-source-detail', selected] })
                }
                if (selected === '__new__') setSelected(activeName === 'tickflow' ? 'tickflow' : activeName)
              }}
              activeName={activeName}
              onActivate={(name) => switchProvider.mutate(name)}
              onDelete={selected !== '__new__' && selectedCustom ? () => setConfirmDelete(selected) : undefined}
            />
          )}
        </motion.div>
      </AnimatePresence>

      {/* 删除确认弹窗 */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setConfirmDelete(null)}
          />
          <div className="relative w-[90vw] max-w-[380px] rounded-card border border-border bg-base shadow-2xl p-6">
            <h3 className="text-sm font-medium text-foreground mb-2">删除数据源</h3>
            <p className="text-xs text-secondary mb-5">
              确认删除「{customList.find(s => s.name === confirmDelete)?.display_name || confirmDelete}」? 该数据源的配置文件将被移除,此操作不可撤销。
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-3 py-1.5 rounded-btn bg-elevated text-secondary hover:bg-elevated/80 text-sm transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => remove.mutate(confirmDelete)}
                disabled={remove.isPending}
                className="px-3 py-1.5 rounded-btn bg-danger/15 text-danger hover:bg-danger/25 text-sm font-medium transition-colors disabled:opacity-50"
              >
                {remove.isPending ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function BuiltinDetail({
  item,
  active,
  onSwitch,
  switching,
}: {
  item: DataSourceItem
  active: boolean
  onSwitch: () => void
  switching: boolean
}) {
  const unavailable = item.available === false
  return (
    <section className="rounded-card border border-border bg-surface p-6">
      <div className="flex items-start gap-4 mb-5">
        <div className="h-11 w-11 rounded-xl bg-accent/10 flex items-center justify-center shrink-0">
          <Database className="h-5 w-5 text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-base font-semibold text-foreground">{item.display_name}</h2>
            <span className="text-[10px] text-muted/60 uppercase tracking-wider border border-border rounded px-1.5 py-0.5">内置</span>
            {active && (
              <span className="inline-flex items-center gap-1 text-[10px] text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                <Check className="h-2.5 w-2.5" /> 当前使用
              </span>
            )}
            {unavailable && (
              <span className="inline-flex items-center gap-1 text-[10px] text-danger bg-danger/10 px-1.5 py-0.5 rounded">
                <FileWarning className="h-2.5 w-2.5" /> 不可用
              </span>
            )}
          </div>
          {item.description && (
            <p className="text-xs text-secondary mt-1.5 leading-relaxed">{item.description}</p>
          )}
          {item.status && (
            <p className={`text-[11px] mt-1 font-mono ${unavailable ? 'text-danger/80' : 'text-muted/60'}`}>{item.status}</p>
          )}
        </div>
      </div>

      {item.datasets.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-5">
          {item.datasets.map(ds => (
            <div key={ds} className="rounded-lg border border-border/50 bg-elevated/20 px-3 py-2.5">
              <div className="text-xs font-medium text-foreground">{DATASET_LABEL[ds] || ds}</div>
            </div>
          ))}
        </div>
      )}

      {unavailable && (
        <div className="mb-4 flex items-start gap-1.5 px-3 py-2 rounded-lg bg-danger/5 border border-danger/20">
          <FileWarning className="h-3.5 w-3.5 text-danger shrink-0 mt-0.5" />
          <div className="text-[11px] text-danger/80 leading-relaxed">
            当前运行环境无法使用该数据源(通常是未安装 Node.js)。可先切换，抓取时未配置的数据集会自动回退 TickFlow。
          </div>
        </div>
      )}

      {!active && (
        <button
          onClick={onSwitch}
          disabled={switching}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-btn bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
        >
          <Zap className="h-3.5 w-3.5" />
          切换为当前数据源
        </button>
      )}
    </section>
  )
}

function TickFlowDetail({ active, onSwitch, switching }: { active: boolean; onSwitch: () => void; switching: boolean }) {
  return (
    <section className="rounded-card border border-border bg-surface p-6">
      <div className="flex items-start gap-4 mb-5">
        <div className="h-11 w-11 rounded-xl bg-accent/10 flex items-center justify-center shrink-0">
          <Database className="h-5 w-5 text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-base font-semibold text-foreground">TickFlow</h2>
            <span className="text-[10px] text-muted/60 uppercase tracking-wider border border-border rounded px-1.5 py-0.5">内置默认</span>
            {active && (
              <span className="inline-flex items-center gap-1 text-[10px] text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                <Check className="h-2.5 w-2.5" /> 当前使用
              </span>
            )}
          </div>
          <p className="text-xs text-secondary mt-1.5 leading-relaxed">
            项目默认数据源。日K、除权因子、实时行情、分钟K均由 TickFlow 提供,无需额外配置。
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-5">
        {[
          { label: '日K', desc: '历史 + 实时覆写' },
          { label: '除权因子', desc: 'Starter+ 能力' },
          { label: '实时行情', desc: '全市场快照' },
          { label: '分钟K', desc: 'Pro+ 能力' },
        ].map(f => (
          <div key={f.label} className="rounded-lg border border-border/50 bg-elevated/20 px-3 py-2.5">
            <div className="text-xs font-medium text-foreground">{f.label}</div>
            <div className="text-[10px] text-muted mt-0.5">{f.desc}</div>
          </div>
        ))}
      </div>

      {!active && (
        <button
          onClick={onSwitch}
          disabled={switching}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-btn bg-accent text-white text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
        >
          <Zap className="h-3.5 w-3.5" />
          切换为当前数据源
        </button>
      )}
    </section>
  )
}
