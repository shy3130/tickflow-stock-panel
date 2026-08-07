import { useRef, useState, useCallback, useEffect } from 'react'
import { useSidebarState, type SidebarState } from '@/lib/useSidebarState'
import { SidebarContent } from './SidebarContent'
import { IconRailContent } from './IconRailContent'
import { PanelLeftClose, PanelLeft, ChevronsLeft } from 'lucide-react'

const WIDTH_CLASS: Record<SidebarState, string> = {
  expanded: 'w-56', // 14rem
  collapsed: 'w-14', // 3.5rem
  hidden: 'w-0',
}

const ICON: Record<SidebarState, typeof PanelLeft> = {
  expanded: PanelLeftClose, // 展开态显示"收起"图标
  collapsed: ChevronsLeft, // 图标条态显示"进一步隐藏"图标
  hidden: PanelLeft, // 隐藏态显示"展开"图标
}

const TITLE: Record<SidebarState, string> = {
  expanded: '折叠为图标条',
  collapsed: '完全隐藏',
  hidden: '展开侧边栏',
}

const HOVER_DELAY = 1000 // hover 1s 后展开
const ANIM_DURATION = 300 // 缓慢展开动画 ms
const CONTENT_DELAY = 150 // 内容延迟挂载 ms（等宽度动画过半再渲染内容）

export function DesktopSidebar() {
  const [state, cycle, set] = useSidebarState()
  const ToggleIcon = ICON[state]

  // 内容延迟挂载：state 变化后延迟 CONTENT_DELAY ms 才挂载内容
  // 避免 hover 展开时内容闪一下重新布局渲染
  const [contentVisible, setContentVisible] = useState<SidebarState | null>(state)
  const contentTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isFirstRender = useRef(true) // P2 修复：首次渲染跳过卸载+延迟逻辑

  const prevStateRef = useRef<SidebarState>(state)

  useEffect(() => {
    // P2 修复：首次渲染不执行卸载+延迟，避免内容闪烁
    if (isFirstRender.current) {
      isFirstRender.current = false
      prevStateRef.current = state
      return
    }
    if (contentTimer.current) clearTimeout(contentTimer.current)
    // 任何 state 变化都先卸载内容，避免宽度过渡期间内容布局变形
    setContentVisible(null)
    if (state !== 'hidden') {
      // 判断是收起（宽度变小）还是展开（宽度变大）
      // 对应 WIDTH_CLASS: w-56=224px, w-14=56px, w-0=0px
      const widthMap: Record<SidebarState, number> = { expanded: 224, collapsed: 56, hidden: 0 }
      const prevWidth = widthMap[prevStateRef.current]
      const nextWidth = widthMap[state]
      const isCollapsing = nextWidth < prevWidth
      // 收起方向等宽度动画完成(ANIM_DURATION)，展开方向过半即可(CONTENT_DELAY)
      const delay = isCollapsing ? ANIM_DURATION : CONTENT_DELAY
      contentTimer.current = setTimeout(() => {
        setContentVisible(state)
      }, delay)
    }
    prevStateRef.current = state
    return () => {
      if (contentTimer.current) clearTimeout(contentTimer.current)
    }
  }, [state])

  // P3 修复：组件卸载时清理 hoverTimer，防止内存泄漏
  useEffect(() => {
    return () => {
      if (hoverTimer.current) clearTimeout(hoverTimer.current)
    }
  }, [])

  // hover 展开模式：overlay 不挤压 main；点击固定展开：push 挤压 main
  // pinned=true: 点击固定展开，不自动隐藏，push 布局
  // pinned=false: hover 展开，移出自动隐藏，overlay 布局
  const [pinned, setPinned] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // hover 进入悬浮按钮：1s 后展开（仅 hidden 态，非 pinned）
  const handleHoverEnter = useCallback(() => {
    if (state !== 'hidden' || pinned) return
    hoverTimer.current = setTimeout(() => {
      set('expanded')
    }, HOVER_DELAY)
  }, [state, pinned, set])

  // hover 离开悬浮按钮：取消待展开的 timer
  const handleHoverLeave = useCallback(() => {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current)
      hoverTimer.current = null
    }
  }, [])

  // 鼠标离开整个 aside（hover 展开非 pinned 时自动隐藏回 hidden）
  const handleAsideLeave = useCallback(() => {
    if (state === 'expanded' && !pinned) {
      set('hidden')
    }
  }, [state, pinned, set])

  // 点击切换按钮
  // hidden 态点击: 固定展开 (pinned=true, push 布局)
  // expanded 态点击 (pinned): 取消固定 + 收起到 collapsed
  // 其他态点击: 正常 cycle
  const handleClick = useCallback(() => {
    handleHoverLeave()
    if (state === 'hidden') {
      set('expanded')
      setPinned(true)
    } else if (state === 'expanded' && pinned) {
      setPinned(false)
      set('collapsed')
    } else {
      cycle()
    }
  }, [state, pinned, cycle, set, handleHoverLeave])

  // 切换按钮样式
  // expanded 态: 固定 w-8，放品牌名旁边
  // collapsed 态: w-14，在图标条内对齐
  // hidden 态: fixed 悬浮按钮，hover 1s 展开或点击固定展开
  const toggleBtn = (
    <button
      onClick={handleClick}
      onMouseEnter={state === 'hidden' ? handleHoverEnter : undefined}
      onMouseLeave={state === 'hidden' ? handleHoverLeave : undefined}
      className={
        state === 'hidden'
          ? 'fixed left-0 top-1/2 -translate-y-1/2 z-50 flex h-12 w-7 items-center justify-center rounded-r-lg bg-surface/70 backdrop-blur-sm border border-l-0 border-border shadow-lg text-accent hover:bg-surface hover:w-8 transition-all cursor-pointer'
          : state === 'collapsed'
            ? 'flex h-8 w-14 items-center justify-center rounded-btn text-foreground/80 hover:bg-elevated hover:text-foreground cursor-pointer'
            : 'flex h-8 w-8 items-center justify-center rounded-btn text-foreground/80 hover:bg-elevated hover:text-foreground cursor-pointer'
      }
      title={TITLE[state]}
    >
      <ToggleIcon className="h-4 w-4 stroke-[2.5]" />
    </button>
  )

  // overlay 模式：hover 展开（非 pinned）+ hidden 态，aside 浮在 main 上方不挤压 main
  //   — expanded !pinned 和 hidden 都是 absolute，两者切换时无 position 跳变，main 宽度始终不变
  // push 模式：pinned expanded 或 collapsed，aside 正常 flex 布局挤压 main
  const isOverlay = (state === 'expanded' && !pinned) || state === 'hidden'

  return (
    <aside
      onMouseLeave={handleAsideLeave}
      style={{
        transitionDuration: `${ANIM_DURATION}ms`,
      }}
      className={`${WIDTH_CLASS[state]} bg-surface flex flex-col h-full min-h-0 overflow-hidden transition-[width] ease-smooth ${
        isOverlay ? 'absolute z-40 shadow-2xl' : 'relative shrink-0'
      }`}
    >
      {/* 内容延迟挂载：等宽度动画过半(150ms)再渲染内容，避免布局闪烁
          contentVisible 跟踪当前应该显示哪个内容组件 */}
      {contentVisible === 'expanded' && (
        <div className="flex-1 min-h-0 flex flex-col">
          <SidebarContent toggleButton={toggleBtn} />
        </div>
      )}
      {contentVisible === 'collapsed' && (
        <div className="flex-1 min-h-0 flex flex-col">
          <IconRailContent toggleButton={toggleBtn} />
        </div>
      )}
      {state === 'hidden' && toggleBtn}
    </aside>
  )
}
