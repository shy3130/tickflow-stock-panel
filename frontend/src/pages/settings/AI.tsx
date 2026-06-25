import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Loader2, Check, Wifi, WifiOff, Eye, EyeOff, Shield, Shuffle } from 'lucide-react'
import { useSettings } from '@/lib/useSharedQueries'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const PRESETS: { label: string; url: string; model: string; website: string; websiteLabel: string; description: string; partner?: boolean; promo?: string }[] = [
  { label: '炸鸡中转站', url: 'https://code.alysc.top/v1', model: 'gpt-5.5', website: 'https://code.alysc.top/sign-up?aff=1afk', websiteLabel: 'code.alysc.top', description: 'OpenAI 兼容中转服务，适合直接使用国际模型。', partner: true, promo: '通过链接邀请注册赠送免费额度 · 国际模型最低0.01倍率' },
  { label: 'DeepSeek', url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', website: 'https://www.deepseek.com/', websiteLabel: 'deepseek.com', description: 'DeepSeek 官方 OpenAI 兼容接口。' },
  { label: '通义千问', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', website: 'https://tongyi.aliyun.com/', websiteLabel: 'tongyi.aliyun.com', description: '阿里云 DashScope 兼容模式接口。' },
]

export function SettingsAIPanel() {
  const qc = useQueryClient()
  const settings = useSettings()
  const s = settings.data

  const [provider, setProvider] = useState('openai_compat')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [tokenBudget, setTokenBudget] = useState(5_000_000)
  // 自定义 User-Agent 开关:关闭 → 后端用内置默认浏览器 UA(开箱绕过 CDN 拦截);
  // 开启 → 用下方文本框的 UA,留空时随机生成。
  const [customUa, setCustomUa] = useState(false)
  const [userAgent, setUserAgent] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)

  // 测试
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)

  // 随机生成一个近期桌面端 Chrome UA(Win/Mac/Linux 随机)
  const genRandomUa = () => {
    const major = 128 + Math.floor(Math.random() * 8) // 128~135
    const platforms = [
      `Windows NT 10.0; Win64; x64`,
      `Macintosh; Intel Mac OS X 10_15_7`,
      `X11; Linux x86_64`,
    ]
    const pf = platforms[Math.floor(Math.random() * platforms.length)]
    setUserAgent(`Mozilla/5.0 (${pf}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${major}.0.0.0 Safari/537.36`)
  }

  useEffect(() => {
    if (!s) return
    setProvider(s.ai_provider ?? 'openai_compat')
    setBaseUrl(s.ai_base_url ?? '')
    setModel(s.ai_model ?? '')
    setTokenBudget(s.ai_daily_token_budget ?? 500_000)
    // 有已保存的自定义 UA → 开关默认开启;否则关闭(用后端内置默认)
    const ua = s.ai_user_agent ?? ''
    setCustomUa(!!ua)
    setUserAgent(ua)
  }, [s])

  const save = useMutation({
    mutationFn: () => api.saveAiSettings({
      provider, base_url: baseUrl, api_key: apiKey || undefined, model, daily_token_budget: tokenBudget,
      // 关闭开关 → 提交空串,后端回退内置默认 UA
      user_agent: customUa ? userAgent : '',
    }),
    onSuccess: () => {
      setSaved(true); setApiKey(''); qc.invalidateQueries({ queryKey: QK.settings })
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const handleTest = async () => {
    setTesting(true); setTestResult(null)
    try {
      // 先保存当前配置（不保存 Key 仅用于测试时临时存）
      if (apiKey) await api.saveAiSettings({ provider, base_url: baseUrl, api_key: apiKey, model, daily_token_budget: tokenBudget, user_agent: customUa ? userAgent : '' })
      const r = await api.strategyAiTest()
      setTestResult({ ok: r.ok, msg: r.ok ? `连通成功 · 模型: ${r.model}${r.usage ? ` · 消耗 ${r.usage.prompt + r.usage.completion} tokens` : ''}` : (r.error ?? '未知错误') })
    } catch (e: any) {
      setTestResult({ ok: false, msg: String(e?.message ?? '测试失败') })
    } finally { setTesting(false) }
  }

  const handlePreset = (p: typeof PRESETS[number]) => {
    setBaseUrl(p.url); setModel(p.model)
  }

  const configured = s?.has_ai_key
  const selectedPreset = PRESETS.find(p => p.url === baseUrl)

  return (
    <div className="max-w-2xl space-y-5">
      {/* ===== 状态横幅 ===== */}
      <div className={`rounded-2xl border px-5 py-4 flex items-center gap-4 ${configured ? 'border-emerald-400/20 bg-emerald-400/[0.04]' : 'border-amber-400/20 bg-amber-400/[0.04]'}`}>
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${configured ? 'bg-emerald-400/10 text-emerald-400' : 'bg-amber-400/10 text-amber-400'}`}>
          {configured ? <Wifi className="h-5 w-5" /> : <WifiOff className="h-5 w-5" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-foreground">{configured ? 'AI 已连接' : 'AI 未配置'}</div>
          <div className="text-xs text-muted mt-0.5">
            {configured ? `${s?.ai_model} · ${s?.ai_api_key_masked}` : '配置 API Key 后即可使用 AI 策略定制'}
          </div>
        </div>
        {configured && (
          <button onClick={handleTest} disabled={testing}
            className="h-8 px-3 rounded-lg border border-border/50 text-xs text-secondary hover:text-foreground hover:border-accent/30 transition-all flex items-center gap-1.5 shrink-0">
            {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
            {testing ? '测试中' : '测试'}
          </button>
        )}
      </div>

      {/* 测试结果 */}
      {testResult && (
        <div className={`rounded-xl border px-4 py-3 text-xs flex items-center gap-2.5 ${testResult.ok ? 'border-emerald-400/20 bg-emerald-400/[0.04] text-emerald-400' : 'border-danger/20 bg-danger/[0.04] text-danger'}`}>
          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${testResult.ok ? 'bg-emerald-400' : 'bg-danger'}`} />
          {testResult.msg}
        </div>
      )}

      {/* ===== 快速预设 ===== */}
      <div className="space-y-2">
        <div className="text-[10px] text-muted/50 uppercase tracking-wider">快速配置</div>
        <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
          {PRESETS.map(p => (
            <button key={p.label} onClick={() => handlePreset(p)}
              className={`rounded-lg border px-3 py-2 text-left transition-all ${baseUrl === p.url ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-secondary hover:border-accent/30'}`}>
              <div className="flex items-center gap-1.5 text-xs font-medium">
                <span>{p.label}</span>
                {p.partner && <span className="rounded-full border border-orange-400/30 bg-orange-400/10 px-1.5 py-px text-[9px] text-orange-400">优惠</span>}
              </div>
            </button>
          ))}
        </div>
        {selectedPreset && (
          <div className="rounded-lg border border-border/30 bg-surface/30 px-3 py-2 text-[10px] leading-relaxed">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-secondary">{selectedPreset.description}</span>
              {selectedPreset.promo && <span className="text-amber-400">{selectedPreset.promo}</span>}
            </div>
            <a href={selectedPreset.website} target="_blank" rel="noreferrer"
              className="mt-1 inline-flex text-muted hover:text-accent transition-colors">
              官网：{selectedPreset.websiteLabel}
            </a>
          </div>
        )}
      </div>

      {/* ===== 自定义配置卡片 ===== */}
      <div className="rounded-2xl border border-border/30 bg-surface/30 overflow-hidden">
        <div className="px-5 py-3 border-b border-border/20">
          <span className="text-xs font-medium text-foreground/70">自定义配置</span>
        </div>
        <div className="px-5 py-4 space-y-4">
          {/* API 地址 + 模型 同行 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[10px] text-muted/50 uppercase tracking-wider">API 地址</label>
              <input type="text" value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
                placeholder="https://code.alysc.top"
                className="w-full h-8 px-2.5 rounded-lg bg-base border-0 ring-1 ring-border/30 text-xs font-mono text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30 transition-shadow" />
            </div>
            <div className="space-y-1.5">
              <label className="text-[10px] text-muted/50 uppercase tracking-wider">模型</label>
              <input type="text" value={model} onChange={e => setModel(e.target.value)}
                placeholder="gpt-5.5"
                className="w-full h-8 px-2.5 rounded-lg bg-base border-0 ring-1 ring-border/30 text-xs text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30 transition-shadow" />
            </div>
          </div>

          {/* API Key */}
          <div className="space-y-1.5">
            <label className="text-[10px] text-muted/50 uppercase tracking-wider">API Key</label>
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey} onChange={e => setApiKey(e.target.value)}
                  placeholder={configured ? `${s?.ai_api_key_masked} · 留空不修改` : 'sk-...'}
                  className="w-full h-8 px-2.5 pr-8 rounded-lg bg-base border-0 ring-1 ring-border/30 text-xs font-mono text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30 transition-shadow" />
                <button onClick={() => setShowKey(v => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted/40 hover:text-muted">
                  {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
              <button onClick={handleTest} disabled={testing || !apiKey}
                className="h-8 px-3 rounded-lg border border-border/50 text-xs text-secondary hover:text-accent hover:border-accent/30 disabled:opacity-40 transition-all flex items-center gap-1.5 shrink-0">
                {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
                测试
              </button>
            </div>
          </div>

          {/* Token 预算 */}
          <div className="space-y-1.5">
            <label className="text-[10px] text-muted/50 uppercase tracking-wider">每日 Token 预算</label>
            <div className="flex items-center gap-3">
              <input type="number" value={tokenBudget} onChange={e => setTokenBudget(Math.max(10000, Number(e.target.value) || 0))}
                min={10000} step={100000}
                className="w-44 h-8 px-2.5 rounded-lg bg-base border-0 ring-1 ring-border/30 text-xs font-mono text-foreground focus:outline-none focus:ring-2 focus:ring-accent/30 transition-shadow" />
              <span className="text-[10px] text-muted">超出后仅发出提醒，不阻止 AI 调用</span>
            </div>
          </div>

          {/* 请求头 User-Agent */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[10px] text-muted/50 uppercase tracking-wider">自定义请求头 User-Agent</label>
              <button
                type="button"
                onClick={() => setCustomUa(v => !v)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full shrink-0 transition-colors duration-200 ${customUa ? 'bg-accent' : 'bg-elevated'}`}
                aria-pressed={customUa}
              >
                <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${customUa ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
              </button>
            </div>
            <div className="text-[10px] text-muted/70 leading-relaxed">
              {customUa
                ? '当前使用下方自定义 UA 调用 AI API。'
                : '默认已使用内置浏览器标识，可绕过 Cloudflare 等 CDN/WAF 拦截。仅在默认标识被拦截时才需开启自定义。'}
            </div>
            {customUa && (
              <div className="flex gap-2">
                <input type="text" value={userAgent} onChange={e => setUserAgent(e.target.value)}
                  placeholder="留空点击「随机生成」或直接粘贴浏览器 UA"
                  className="flex-1 h-8 px-2.5 rounded-lg bg-base border-0 ring-1 ring-border/30 text-xs font-mono text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30 transition-shadow" />
                <button type="button" onClick={() => { if (!userAgent) genRandomUa() }}
                  title={userAgent ? '已存在内容，清空后可重新生成' : '随机生成浏览器 UA'}
                  className="h-8 px-2.5 rounded-lg border border-border/50 text-xs text-secondary hover:text-accent hover:border-accent/30 transition-all flex items-center gap-1.5 shrink-0 disabled:opacity-40"
                  disabled={!!userAgent}>
                  <Shuffle className="h-3 w-3" /> 随机
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ===== 安全提示 ===== */}
      <div className="rounded-2xl border border-amber-400/20 bg-amber-400/[0.04] px-5 py-3.5 flex items-start gap-3">
        <Shield className="h-4 w-4 text-amber-400/70 mt-0.5 shrink-0" />
        <div className="text-[10px] text-amber-400/70 leading-relaxed">
          API Key 仅保存在本机项目文件，不上传至任何服务器。请妥善保管，勿泄露给他人。
        </div>
      </div>

      {/* ===== 保存 ===== */}
      <button onClick={() => save.mutate()} disabled={save.isPending || !baseUrl || !model}
        className="w-full h-10 rounded-xl bg-accent text-white text-sm font-semibold flex items-center justify-center gap-2 hover:bg-accent/90 disabled:opacity-40 transition-all">
        {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
        {save.isPending ? '保存中...' : saved ? '已保存' : '保存配置'}
      </button>
    </div>
  )
}
