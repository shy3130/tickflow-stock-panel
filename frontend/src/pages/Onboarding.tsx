import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Eye,
  EyeOff,
  Loader2,
  Save,
  Check,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  Copy,
  Sparkles,
  LineChart,
  ScanSearch,
  Flame,
  Zap,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useCapabilities, useSettings } from '@/lib/useSharedQueries'
import { QK } from '@/lib/queryKeys'
import { CAP_LABELS } from '@/lib/capability-labels'
import { Logo } from '@/components/Logo'

// ===== 引导页:4 步向导 =====
// 1. 欢迎  2. 输入 Key(可跳过)  3. 能力探测结果  4. 完成 → 写标记 → 进面板

const STEPS = ['欢迎', '配置 Key', '能力探测', '完成'] as const

const HIGHLIGHTS = [
  { icon: LineChart, title: '看板与自选', desc: '实时行情、MA/MACD 指标、自定义自选列表' },
  { icon: ScanSearch, title: '策略选股', desc: '内置多套选股策略,一键扫描全市场命中' },
  { icon: Flame, title: '连板梯队', desc: '涨停板梯队、概念行业热度、市场情绪一览' },
  { icon: Zap, title: '回测验证', desc: '策略历史回测、因子分析,用数据说话' },
]

export function Onboarding() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [step, setStep] = useState(0)

  // 完成向导 —— 写后端标记,使守卫放行
  const complete = useMutation({
    mutationFn: api.completeOnboarding,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.settings })
      navigate('/', { replace: true })
    },
    onError: () => {
      // 标记失败不应阻塞用户进入面板,仍放行
      navigate('/', { replace: true })
    },
  })

  const finish = () => complete.mutate()

  return (
    <div className="min-h-screen bg-base flex flex-col">
      {/* 顶栏:logo + 进度指示 */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div className="flex items-center gap-2 text-foreground">
          <Logo size={22} />
          <span className="text-sm font-medium">TickFlow Stock Panel</span>
        </div>
        <div className="flex items-center gap-1.5">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-1.5">
              <div
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  i === step ? 'w-6 bg-accent' : i < step ? 'w-1.5 bg-accent' : 'w-1.5 bg-border'
                }`}
              />
            </div>
          ))}
        </div>
        <div className="w-[88px] text-right">
          <span className="text-xs text-muted">
            {step + 1} / {STEPS.length}
          </span>
        </div>
      </header>

      {/* 步骤内容 */}
      <main className="flex-1 flex items-center justify-center px-6 py-10">
        <div className="w-full max-w-lg">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            >
              {step === 0 && <WelcomeStep onNext={() => setStep(1)} onSkip={finish} />}
              {step === 1 && (
                <KeyStep onNext={() => setStep(2)} onSkip={() => setStep(2)} onBack={() => setStep(0)} />
              )}
              {step === 2 && <ResultStep onNext={finish} onBack={() => setStep(1)} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  )
}

// ===== Step 0: 欢迎 =====

function WelcomeStep({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  return (
    <div className="text-center">
      <div className="mx-auto w-fit rounded-2xl bg-accent/10 p-4">
        <Sparkles className="h-8 w-8 text-accent" />
      </div>
      <h1 className="mt-6 text-2xl font-bold text-foreground">欢迎使用 TickFlow Stock Panel</h1>
      <p className="mt-3 text-sm text-secondary leading-relaxed max-w-md mx-auto">
        一个本地化的 A 股量化分析面板 —— 行情、选股、回测、财务一体化。
        花一分钟配置,即可开始使用。
      </p>

      <div className="mt-8 grid grid-cols-2 gap-3 text-left">
        {HIGHLIGHTS.map((h) => (
          <div key={h.title} className="rounded-card border border-border bg-surface p-4">
            <h.icon className="h-5 w-5 text-accent" />
            <div className="mt-2 text-sm font-medium text-foreground">{h.title}</div>
            <div className="mt-1 text-xs text-muted leading-relaxed">{h.desc}</div>
          </div>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-center gap-3">
        <button
          onClick={onNext}
          className="inline-flex items-center gap-2 px-5 h-10 rounded-xl bg-accent text-white text-sm font-semibold hover:bg-accent/90 transition-colors"
        >
          开始配置
          <ArrowRight className="h-4 w-4" />
        </button>
        <button
          onClick={onSkip}
          className="px-4 h-10 rounded-xl text-sm text-secondary hover:text-foreground transition-colors"
        >
          稍后再说
        </button>
      </div>
    </div>
  )
}

// ===== Step 1: 输入 TickFlow Key =====

function KeyStep({ onNext, onSkip, onBack }: { onNext: () => void; onSkip: () => void; onBack: () => void }) {
  const qc = useQueryClient()
  const settings = useSettings()

  const [keyInput, setKeyInput] = useState('')
  const [revealing, setRevealing] = useState(false)
  const [copiedCode, setCopiedCode] = useState(false)
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () => api.saveTickflowKey(keyInput.trim()),
    onSuccess: () => {
      setSaved(true)
      qc.invalidateQueries({ queryKey: QK.settings })
      qc.invalidateQueries({ queryKey: QK.capabilities })
      // 保存成功后自动进入下一步看探测结果
      setTimeout(() => onNext(), 600)
    },
  })

  const alreadyHasKey = settings.data?.has_tickflow_key

  return (
    <div>
      <h2 className="text-xl font-bold text-foreground">配置 TickFlow API Key</h2>
      <p className="mt-2 text-sm text-secondary leading-relaxed">
        Key 决定你能使用的数据范围。没有 Key 也能以 <span className="font-medium text-foreground">Free</span> 模式试用基础功能;
        配置后可解锁概念行业、财务数据等扩展能力。
      </p>

      {/* 注册引导 */}
      <div className="mt-5 rounded-card border border-border bg-surface p-4 text-xs text-secondary leading-relaxed">
        还没有 Key?前往{' '}
        <a
          href="https://tickflow.org/auth/register?ref=V3KDKGXPEA"
          target="_blank"
          rel="noreferrer"
          className="text-accent hover:underline inline-flex items-baseline gap-0.5"
        >
          tickflow.org
          <ExternalLink className="h-3 w-3 self-center" />
        </a>{' '}
        注册,或填写邀请码{' '}
        <span className="font-mono font-semibold text-accent inline-flex items-baseline gap-1">
          V3KDKGXPEA
          <button
            type="button"
            onClick={() => {
              navigator.clipboard?.writeText('V3KDKGXPEA').then(() => {
                setCopiedCode(true)
                setTimeout(() => setCopiedCode(false), 1500)
              })
            }}
            className="text-muted hover:text-accent transition-colors self-center"
            aria-label="复制邀请码"
            tabIndex={-1}
          >
            {copiedCode ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          </button>
        </span>
        ,即可免费领取扩展数据。
      </div>

      {/* Key 已配置提示 */}
      {alreadyHasKey && !save.isPending && (
        <div className="mt-4 flex items-start gap-2 rounded-btn border border-bear/30 bg-bear/10 px-3 py-2.5 text-xs text-bear">
          <CheckCircle2 className="h-3.5 w-3.5 mt-px shrink-0" />
          <span>
            已检测到配置好的 Key(<span className="font-mono">{settings.data?.tickflow_api_key_masked}</span>)。
            可直接下一步查看能力,或在下方粘贴新 Key 替换。
          </span>
        </div>
      )}

      {/* 输入 */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (keyInput.trim()) save.mutate()
        }}
        className="mt-4 space-y-2"
      >
        <div className="relative">
          <input
            type={revealing ? 'text' : 'password'}
            placeholder={alreadyHasKey ? '粘贴新 Key 替换当前' : '粘贴 TickFlow API Key'}
            value={keyInput}
            onChange={(e) => {
              setKeyInput(e.target.value)
              if (saved) setSaved(false)
            }}
            className="w-full px-3 py-2 pr-9 rounded-input bg-base border border-border text-sm font-mono focus:outline-none focus:border-accent transition-colors"
          />
          <button
            type="button"
            onClick={() => setRevealing((v) => !v)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-foreground transition-colors"
            tabIndex={-1}
            aria-label={revealing ? '隐藏' : '显示'}
          >
            {revealing ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>

        {/* 保存中提示 */}
        {save.isPending && (
          <div className="flex items-start gap-1.5 rounded-btn border border-warning/30 bg-warning/10 px-3 py-2 text-[11px] leading-snug text-warning">
            <AlertCircle className="h-3.5 w-3.5 mt-px shrink-0" />
            <span>正在验证 Key 并探测能力,验证通过前请不要离开当前页面。</span>
          </div>
        )}

        {save.isError && (
          <div className="text-xs text-danger">保存失败:{String((save.error as any).message)}</div>
        )}
      </form>

      {/* 底部操作 */}
      <div className="mt-6 flex items-center justify-between">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 px-3 h-9 rounded-btn text-sm text-secondary hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          上一步
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={onSkip}
            disabled={save.isPending}
            className="px-4 h-9 rounded-btn text-sm text-secondary hover:text-foreground transition-colors disabled:opacity-50"
          >
            {alreadyHasKey ? '下一步' : '暂不配置'}
          </button>
          <button
            onClick={() => keyInput.trim() && save.mutate()}
            disabled={save.isPending || !keyInput.trim()}
            className="inline-flex items-center gap-2 px-5 h-9 rounded-xl bg-accent text-white text-sm font-semibold hover:bg-accent/90 disabled:opacity-40 transition-all"
          >
            {save.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : saved ? (
              <Check className="h-4 w-4" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {save.isPending ? '保存中...' : saved ? '已保存' : '保存并检测'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ===== Step 2: 能力探测结果 =====

function ResultStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const settings = useSettings()
  const caps = useCapabilities()

  const hasKey = settings.data?.has_tickflow_key
  const capList = caps.data ? Object.entries(caps.data.capabilities) : []

  return (
    <div>
      <h2 className="text-xl font-bold text-foreground">能力探测结果</h2>

      {hasKey ? (
        <>
          <p className="mt-2 text-sm text-secondary leading-relaxed">
            Key 已生效,以下是你当前可用的全部能力。后续可在
            <span className="text-foreground"> 设置 → 账户 </span>
            中重新检测或更换 Key。
          </p>

          <div className="mt-5 rounded-card border border-border bg-surface p-5">
            <div className="flex items-baseline justify-between">
              <span className="text-[10px] uppercase tracking-widest text-muted">订阅档位</span>
              <span className="font-mono text-2xl font-bold tracking-tight text-foreground">
                {caps.data?.label ?? settings.data?.tier_label ?? '—'}
              </span>
            </div>

            {caps.isLoading ? (
              <div className="mt-4 flex items-center gap-2 text-xs text-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                正在探测能力…
              </div>
            ) : capList.length > 0 ? (
              <div className="mt-4 grid grid-cols-1 gap-1.5">
                {capList.slice(0, 8).map(([cap]) => {
                  const meta = CAP_LABELS[cap]
                  return (
                    <div key={cap} className="flex items-center gap-2 text-xs">
                      <CheckCircle2 className="h-3.5 w-3.5 text-bear shrink-0" />
                      <span className="text-foreground">{meta?.name ?? cap}</span>
                    </div>
                  )
                })}
                {capList.length > 8 && (
                  <div className="text-[11px] text-muted pl-5">…等共 {capList.length} 项</div>
                )}
              </div>
            ) : (
              <div className="mt-4 text-xs text-muted">暂未探测到能力</div>
            )}
          </div>
        </>
      ) : (
        <div className="mt-5 rounded-card border border-border bg-surface p-6 text-center">
          <div className="mx-auto w-fit rounded-xl bg-elevated p-3">
            <Zap className="h-6 w-6 text-warning" />
          </div>
          <div className="mt-3 text-sm font-medium text-foreground">将以 Free 模式继续</div>
          <p className="mt-2 text-xs text-muted leading-relaxed max-w-sm mx-auto">
            你可以立即试用基础行情与选股功能。需要扩展数据时,随时在
            <span className="text-foreground"> 设置 → 账户 </span>
            配置 Key。
          </p>
        </div>
      )}

      {/* 底部操作 */}
      <div className="mt-6 flex items-center justify-between">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 px-3 h-9 rounded-btn text-sm text-secondary hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          上一步
        </button>
        <button
          onClick={onNext}
          className="inline-flex items-center gap-2 px-5 h-9 rounded-xl bg-accent text-white text-sm font-semibold hover:bg-accent/90 transition-colors"
        >
          进入面板
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
