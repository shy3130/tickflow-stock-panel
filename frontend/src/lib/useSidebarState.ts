import { useCallback, useEffect, useState } from 'react'

export type SidebarState = 'expanded' | 'collapsed' | 'hidden'

const STORAGE_KEY = 'sidebar_collapse_state'
const ORDER: SidebarState[] = ['expanded', 'collapsed', 'hidden']

function readStored(): SidebarState {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v && ORDER.includes(v as SidebarState)) return v as SidebarState
  } catch {
    // localStorage 不可用（隐私模式等）— 回退默认值
  }
  return 'expanded'
}

/**
 * 桌面端侧边栏三态管理。
 * 状态持久化到 localStorage，刷新页面后恢复。
 * 仅桌面端使用，移动端走抽屉模式不读取此状态。
 */
export function useSidebarState() {
  const [state, setState] = useState<SidebarState>(readStored)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, state)
    } catch {
      // 忽略写入失败
    }
  }, [state])

  const cycle = useCallback(() => {
    setState((prev) => ORDER[(ORDER.indexOf(prev) + 1) % ORDER.length])
  }, [])

  return [state, cycle] as const
}
