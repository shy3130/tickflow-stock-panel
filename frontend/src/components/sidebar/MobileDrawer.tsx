import { useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Menu, X } from 'lucide-react'
import { SidebarContent } from './SidebarContent'

export function MobileDrawer() {
  const [open, setOpen] = useState(false)

  // ESC 关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  // 抽屉打开时锁定 body 滚动，防止背景穿透
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  return (
    <>
      {/* FAB 汉堡按钮 — 左上角悬浮 */}
      <button
        onClick={() => setOpen(true)}
        className="fixed left-2 top-2 z-40 flex h-8 w-8 items-center justify-center rounded-full bg-surface/70 backdrop-blur-sm border border-border shadow-lg text-accent hover:bg-surface cursor-pointer transition-all"
        aria-label="打开菜单"
      >
        <Menu className="h-4 w-4 stroke-[2.5]" />
      </button>

      <AnimatePresence>
        {open && (
          <>
            {/* 遮罩 */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-40 bg-black/50"
            />
            {/* 抽屉 */}
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="fixed left-0 top-0 z-50 h-full w-[80vw] max-w-[320px] border-r border-border bg-surface flex flex-col"
            >
              {/* 关闭按钮 */}
              <button
                onClick={() => setOpen(false)}
                className="absolute right-2 top-2 z-10 flex h-8 w-8 items-center justify-center rounded-full text-foreground/60 hover:bg-elevated hover:text-foreground cursor-pointer"
                aria-label="关闭菜单"
              >
                <X className="h-4 w-4" />
              </button>
              <SidebarContent onNavigate={() => setOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
