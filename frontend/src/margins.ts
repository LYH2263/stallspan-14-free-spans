// 柱间余量色档：全应用唯一数据源（主图色带 / 侧栏 / 运行抽屉 / 放不下可摆提示共用）。
// 分界与后端 first_fit_engine 锁死一致：<=1.5 紧，<=3.0 中，再大松。
export const TIGHT_MAX_M = 1.5
export const MEDIUM_MAX_M = 3.0

export type Tier = 'tight' | 'medium' | 'loose'

export interface MarginGap {
  start_m: number
  end_m: number
  length_m: number
  tier: Tier
}

export const TIER_META: Record<Tier, { label: string; color: string; soft: string }> = {
  tight: { label: '紧', color: '#b23b2c', soft: 'rgba(178,59,44,0.42)' },
  medium: { label: '中', color: '#cf8a1e', soft: 'rgba(207,138,30,0.40)' },
  loose: { label: '松', color: '#3a7a4a', soft: 'rgba(58,122,74,0.40)' },
}

export function tierForLength(length_m: number): Tier {
  if (length_m <= TIGHT_MAX_M + 1e-9) return 'tight'
  if (length_m <= MEDIUM_MAX_M + 1e-9) return 'medium'
  return 'loose'
}

interface LegacySpan { start_m: number; end_m: number }
interface RunLike {
  margins?: MarginGap[] | null
  free_spans?: LegacySpan[] | null
}

/** 读取一次运行的余量：新记录用冻结 margins；旧结构（仅 free_spans）按同一分界现派生展示。 */
export function marginsOf(run: RunLike | null | undefined): MarginGap[] {
  if (!run) return []
  if (Array.isArray(run.margins)) {
    return [...run.margins]
      .map(g => ({ ...g, tier: (g.tier || tierForLength(g.length_m)) as Tier }))
      .sort((a, b) => a.start_m - b.start_m)
  }
  return (run.free_spans || [])
    .map(s => {
      const length_m = round3(s.end_m - s.start_m)
      return { start_m: round3(s.start_m), end_m: round3(s.end_m), length_m, tier: tierForLength(length_m) }
    })
    .filter(g => g.length_m > 1e-6)
    .sort((a, b) => a.start_m - b.start_m)
}

/** 放不下旁的可摆提示：返回能容纳 need 的最长余量空档（优先松、再中、再紧中的最长者）。 */
export function fitHint(need_m: number, margins: MarginGap[]): MarginGap | null {
  const fits = margins.filter(g => g.length_m + 1e-9 >= need_m)
  if (!fits.length) return null
  fits.sort((a, b) => b.length_m - a.length_m)
  return fits[0]
}

export interface FitHintResult { gap: MarginGap; fit: boolean; shortfall_m: number }

/**
 * 放不下旁的提示（first-fit 下被拒者通常所有空档都不够）：
 * 始终取最长余量空档——够则给出可摆位置，不够则给出最近空档与缺口米数。
 */
export function fitHintWithShortfall(need_m: number, margins: MarginGap[]): FitHintResult | null {
  if (!margins.length) return null
  const gap = [...margins].sort((a, b) => b.length_m - a.length_m)[0]
  return { gap, fit: gap.length_m + 1e-9 >= need_m, shortfall_m: round3(need_m - gap.length_m) }
}

function round3(x: number): number {
  return Math.round(x * 1000) / 1000
}
