/**
 * 数据源切换共享逻辑 —— 供 设置页 / 引导页 / 看板首次拉取卡片 复用。
 *
 * 关键点: 按目标源声明的数据集精确切换, 未声明的数据集回落 tickflow。
 * 三处入口共用同一份 payload 构造 + 切换 mutation, 避免逻辑漂移。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type DataSourceItem, type Preferences } from './api'
import { QK } from './queryKeys'
import { usePreferences } from './useSharedQueries'
import { toast } from '@/components/Toast'

type ProviderUpdate = Partial<
  Pick<
    Preferences,
    | 'daily_data_provider'
    | 'adj_factor_provider'
    | 'minute_data_provider'
    | 'realtime_data_provider'
    | 'financial_data_provider'
  >
>

/** 由目标源(及其声明的数据集)构造各数据集的 provider 更新载荷。 */
export function providerUpdatePayload(name: string, item?: DataSourceItem): ProviderUpdate {
  if (name === 'tickflow') {
    return {
      daily_data_provider: 'tickflow',
      adj_factor_provider: 'same_as_daily',
      realtime_data_provider: 'tickflow',
      minute_data_provider: 'tickflow',
      financial_data_provider: 'tickflow',
    }
  }
  const ds = new Set(item?.datasets ?? ['daily', 'realtime'])
  return {
    daily_data_provider: ds.has('daily') ? name : 'tickflow',
    adj_factor_provider: 'same_as_daily',
    realtime_data_provider: ds.has('realtime') ? name : 'tickflow',
    minute_data_provider: ds.has('minute') ? name : 'tickflow',
    financial_data_provider: ds.has('financial') ? name : 'tickflow',
  }
}

/** 数据源列表 + 当前启用源。builtin(含 tickflow/stocksdk) 在前, 自定义源在后。 */
export function useDataSourceList() {
  const sources = useQuery({ queryKey: QK.dataSources, queryFn: api.dataSources })
  const prefs = usePreferences()
  const builtin: DataSourceItem[] = sources.data?.builtin ?? []
  const custom: DataSourceItem[] = sources.data?.custom ?? []
  const items = [...builtin, ...custom]
  const activeName = prefs.data?.daily_data_provider || 'tickflow'
  const builtinNames = new Set(builtin.map((b) => b.name))
  return {
    sources,
    prefs,
    builtin,
    custom,
    items,
    activeName,
    activeItem: items.find((s) => s.name === activeName),
    isBuiltin: (name: string) => builtinNames.has(name),
  }
}

export type DatasetKind = 'daily' | 'adj_factor' | 'minute' | 'realtime' | 'financial'

/**
 * 按数据集解析生效的 provider —— 各数据集可独立选源, 与后端 preferences 一致。
 * 用于「消费侧」判断某能力是否由免费源(非 tickflow)提供, 从而放开 TickFlow 档位门控。
 * 与 quote_service.realtime_mode() 的 `provider != tickflow → 免费全量` 逻辑对齐。
 */
export function useDatasetProviders() {
  const { items, prefs } = useDataSourceList()
  const p = prefs.data

  const resolve = (dataset: DatasetKind): string => {
    if (!p) return 'tickflow'
    switch (dataset) {
      case 'daily':
        return p.daily_data_provider || 'tickflow'
      case 'adj_factor': {
        const a = p.adj_factor_provider || 'same_as_daily'
        return a === 'same_as_daily' ? p.daily_data_provider || 'tickflow' : a
      }
      case 'minute':
        return p.minute_data_provider || 'tickflow'
      case 'realtime':
        return p.realtime_data_provider || 'tickflow'
      case 'financial':
        return p.financial_data_provider || 'tickflow'
    }
  }

  /** 该数据集是否由非 TickFlow 的(免费)源提供。 */
  const usesFreeProvider = (dataset: DatasetKind) => resolve(dataset) !== 'tickflow'
  /** provider name → 展示名(内置/自定义)。 */
  const displayName = (name: string) => items.find((i) => i.name === name)?.display_name || name

  return { resolve, usesFreeProvider, displayName, items }
}

/** 切换当前数据源的 mutation。onSwitched 回调用于同步选中态 / 关闭弹窗等。 */
export function useSwitchProvider(opts?: { onSwitched?: (name: string) => void; silent?: boolean }) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { name: string; item?: DataSourceItem }) =>
      api.updateDataProviders(providerUpdatePayload(vars.name, vars.item)),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      if (!opts?.silent) toast('数据源已切换', 'success')
      opts?.onSwitched?.(vars.name)
    },
  })
}
