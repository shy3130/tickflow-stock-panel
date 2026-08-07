import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  fmtIndexValue,
  fmtIndexPct,
  indexPctClass,
  type CoreIndex,
} from './shared'
import type { IndexQuote } from '@/lib/api'

/**
 * 图标条态指数轮播。
 * 3 秒自动切换 + hover 暂停 + 点击跳转 /indices?symbol=。
 * quotes 接收 IndexQuote[]（调用方需从 query 结果取 .rows）。
 */
export function IndexQuoteCarousel({
  quotes,
  items,
}: {
  quotes: IndexQuote[] | undefined
  items: CoreIndex[]
}) {
  const [idx, setIdx] = useState(0)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (paused || items.length <= 1) return
    const t = setInterval(() => setIdx((i) => (i + 1) % items.length), 3000)
    return () => clearInterval(t)
  }, [paused, items.length])

  // items 变化时重置 idx 防越界的
  useEffect(() => {
    if (idx >= items.length) setIdx(0)
  }, [items.length, idx])

  if (items.length === 0) return null
  // 越界保护：items 缩减时 useEffect 修复在下一次渲染，当前渲染需安全回退
  const safeIdx = idx >= items.length ? 0 : idx
  const item = items[safeIdx]
  const q = quotes?.find((x) => x.symbol === item.symbol)
  const value = q?.last_price ?? q?.close
  const pct = q?.change_pct

  return (
    <NavLink
      to={`/indices?symbol=${encodeURIComponent(item.symbol)}`}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className="block w-14 my-1 rounded bg-elevated/60 px-1.5 py-1.5 hover:bg-elevated transition-colors overflow-hidden"
      title={`${item.name} ${item.symbol}`}
    >
      <motion.div
        key={item.symbol}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        <div className="flex items-center justify-between gap-0.5">
          <span className="text-[9px] text-secondary truncate">{item.name.slice(0, 2)}</span>
          <span className={`text-[9px] font-mono shrink-0 ${indexPctClass(pct)}`}>
            {fmtIndexPct(pct)}
          </span>
        </div>
        <div className={`mt-0.5 truncate font-mono text-[9px] ${indexPctClass(pct)}`}>
          {fmtIndexValue(value)}
        </div>
      </motion.div>
    </NavLink>
  )
}
