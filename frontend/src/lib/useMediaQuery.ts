import { useEffect, useState } from 'react'

/**
 * 响应式媒体查询 hook。
 * SSR 安全：typeof window === 'undefined' 时返回 false。
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    mql.addEventListener('change', handler)
    setMatches(mql.matches) // 同步初始值（避免 SSR 不一致）
    return () => mql.removeEventListener('change', handler)
  }, [query])

  return matches
}

/** 桌面端断点：≥768px */
export const useIsDesktop = () => useMediaQuery('(min-width: 768px)')
