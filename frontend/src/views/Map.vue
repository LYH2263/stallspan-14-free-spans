<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { marginsOf, TIER_META, type MarginGap, type Tier } from '../margins'

interface RunSummary { id: number; created_at: string | null }

const live = ref<any>(null)        // 最新一次确认（POST /run 返回）
const viewRun = ref<any>(null)     // 抽屉中打开的历史冻结运行；null 表示看 live
const vendors = ref<any[]>([])
const runs = ref<RunSummary[]>([])
const drawerOpen = ref(false)
const loading = ref(false)

const view = computed(() => viewRun.value ?? live.value)
// 历史记录若缺 segment/pillars（更早的旧结构），标尺借当前街段，色档仍用冻结坐标。
const seg = computed(() => view.value?.segment ?? live.value?.segment ?? { name: '', width_m: 0 })
const viewPillars = computed(() => view.value?.pillars ?? live.value?.pillars ?? [])
const width = computed(() => seg.value?.width_m ?? 0)
const margins = computed<MarginGap[]>(() => marginsOf(view.value))

const PX_PER_M = 30
const trackWidth = computed(() => Math.max(width.value * PX_PER_M, 1))

const colors = ['#e8a87c', '#85dcb8', '#e27d60', '#c38d9e', '#41b3a3', '#f4a261', '#e76f51']

interface Cell {
  kind: 'stall' | 'pillar' | 'margin'
  start: number
  w: number
  label: string
  color?: string
  tier?: Tier
  key: string
}

// 主图上每一个可见块都按真实米位绝对定位——色档与未涂色空隙天然对齐。
const cells = computed<Cell[]>(() => {
  if (!view.value) return []
  const out: Cell[] = []
  for (const [i, p] of (view.value.placements || []).entries()) {
    out.push({
      kind: 'stall', key: `s-${p.vendor_id}`,
      start: p.start_m, w: p.width_m, label: p.vendor_name,
      color: colors[i % colors.length],
    })
  }
  for (const p of viewPillars.value) {
    out.push({
      kind: 'pillar', key: `p-${p.position_m}`,
      start: p.position_m - p.thickness_m / 2, w: p.thickness_m,
      label: p.label || '挡柱',
    })
  }
  for (const [i, g] of margins.value.entries()) {
    out.push({
      kind: 'margin', key: `m-${i}`,
      start: g.start_m, w: g.length_m,
      label: `${TIER_META[g.tier].label} ${g.length_m}m`,
      tier: g.tier,
    })
  }
  return out.sort((a, b) => a.start - b.start)
})

const tierCounts = computed(() => {
  const c: Record<Tier, number> = { tight: 0, medium: 0, loose: 0 }
  for (const g of margins.value) c[g.tier]++
  return c
})

async function run() {
  loading.value = true
  try {
    live.value = await api('/allocate/run?segment_id=1', { method: 'POST' })
    viewRun.value = null
    await refreshRunList()
  } finally {
    loading.value = false
  }
}

async function refreshRunList() {
  runs.value = await api('/allocate/runs?segment_id=1')
}

async function openRun(id: number) {
  viewRun.value = await api(`/allocate/runs/${id}`)
}

function fmtTime(iso: string | null): string {
  if (!iso) return ''
  return iso.replace('T', ' ').slice(0, 19)
}

onMounted(async () => {
  vendors.value = await api('/vendors')
  live.value = await api('/allocate/latest?segment_id=1')
  await refreshRunList()
})
</script>

<template>
  <div class="ss-map">
    <div class="ss-map-head">
      <div>
        <h1>街段分配带</h1>
        <p class="sub">沿街一维开间 · 挡柱为竖直阻断 · 色档为柱间余量（紧/中/松）· 底部为摊主排队</p>
      </div>
      <div class="ss-map-actions">
        <button class="btn btn-ghost" @click="drawerOpen = true">运行抽屉 ({{ runs.length }})</button>
        <button class="btn" :disabled="loading" @click="run">{{ loading ? '确认中…' : '重新分配' }}</button>
      </div>
    </div>

    <div v-if="viewRun" class="ss-hist-banner">
      正在查看历史运行 <strong>#{{ viewRun.id }}</strong>
      <span v-if="viewRun.created_at">· {{ fmtTime(viewRun.created_at) }}</span>
      <em>色档为该次确认瞬间冻结，改街宽/挪柱不会改写</em>
      <button class="btn btn-mini" @click="viewRun = null">回到最新</button>
    </div>

    <div class="ss-map-body" v-if="view">
      <div class="ss-band-area">
        <div class="ss-band-ruler">
          <span>0 m</span>
          <span>{{ seg.name }} · {{ seg.width_m }} m</span>
          <span>{{ seg.width_m }} m</span>
        </div>
        <div class="ss-street-band ss-map-band">
          <div class="ss-map-track" :style="{ width: trackWidth + 'px' }">
            <div
              v-for="c in cells" :key="c.key"
              class="ss-map-cell"
              :class="{ 'ss-pillar': c.kind === 'pillar', 'ss-margin': c.kind === 'margin' }"
              :style="{
                left: (c.start / width) * 100 + '%',
                width: (c.w / width) * 100 + '%',
                background: c.kind === 'stall' ? c.color
                  : c.kind === 'margin' ? TIER_META[c.tier!].soft : undefined,
                borderColor: c.kind === 'margin' ? TIER_META[c.tier!].color : undefined,
              }"
            >
              <span
                v-if="c.kind === 'pillar' || c.w * PX_PER_M >= 26"
                class="ss-map-label"
              >{{ c.label }}</span>
            </div>
          </div>
        </div>

        <div class="ss-vendor-queue">
          <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
            <strong>{{ v.name }}</strong>
            <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
          </div>
        </div>

        <div class="card">
          <table>
            <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
            <tbody>
              <tr v-for="p in view.placements" :key="p.vendor_id">
                <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <aside class="ss-margin-rail">
        <div class="card ss-margin-card">
          <h2>柱间余量</h2>
          <ul class="ss-tier-legend">
            <li v-for="t in (['tight','medium','loose'] as Tier[])" :key="t">
              <i :style="{ background: TIER_META[t].color }"></i>
              {{ TIER_META[t].label }}档 · {{ tierCounts[t] }} 段
            </li>
          </ul>
          <p v-if="!margins.length" class="muted">无剩余空档，色档为空</p>
          <div
            v-for="(g, i) in margins" :key="i"
            class="ss-margin-row"
            :style="{ borderLeftColor: TIER_META[g.tier].color }"
          >
            <div class="ss-margin-row-head">
              <span class="badge" :style="{ background: TIER_META[g.tier].soft, color: TIER_META[g.tier].color }">
                {{ TIER_META[g.tier].label }}
              </span>
              <strong>{{ g.length_m }} m</strong>
            </div>
            <div class="muted">{{ g.start_m }} m → {{ g.end_m }} m</div>
          </div>
        </div>
      </aside>
    </div>

    <transition name="ss-drawer">
      <div v-if="drawerOpen" class="ss-drawer-mask" @click.self="drawerOpen = false">
        <aside class="ss-drawer">
          <header>
            <h2>运行抽屉</h2>
            <button class="btn btn-mini" @click="drawerOpen = false">收起</button>
          </header>
          <p class="sub">确认瞬间固化余量色档；历史记录只读，不随街宽/挡柱改动重算。</p>
          <ul class="ss-run-list">
            <li
              v-for="r in runs" :key="r.id"
              :class="{ active: viewRun && viewRun.id === r.id }"
              @click="openRun(r.id)"
            >
              <strong>运行 #{{ r.id }}</strong>
              <span class="muted">{{ fmtTime(r.created_at) }}</span>
            </li>
          </ul>
          <p v-if="!runs.length" class="muted">尚无运行记录</p>
        </aside>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.ss-map { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.ss-map-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.ss-map-actions { display: flex; gap: 0.5rem; flex: 0 0 auto; padding-top: 0.1rem; }
.btn-ghost { background: var(--ss-paper); color: var(--ss-curb); }
.btn-mini { padding: 0.15rem 0.55rem; font-size: 0.75rem; box-shadow: none; }
.ss-hist-banner {
  display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
  background: rgba(196, 92, 38, 0.14); border: 1px solid var(--ss-accent);
  border-radius: 4px; padding: 0.4rem 0.7rem; margin-bottom: 0.6rem; font-size: 0.82rem;
}
.ss-hist-banner em { color: var(--ss-muted); font-style: normal; font-size: 0.75rem; }

.ss-map-body { flex: 1; display: flex; gap: 0.85rem; min-height: 0; }
.ss-band-area { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow-y: auto; }
.ss-margin-rail { flex: 0 0 230px; overflow-y: auto; }
.ss-margin-card h2 { margin: 0 0 0.5rem; font-size: 0.95rem; }
.ss-tier-legend {
  list-style: none; margin: 0 0 0.6rem; padding: 0 0 0.6rem;
  display: flex; gap: 0.75rem; border-bottom: 1px dashed rgba(92, 74, 50, 0.35);
  font-size: 0.78rem; color: var(--ss-muted);
}
.ss-tier-legend i { display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px; margin-right: 0.25rem; }
.ss-margin-row {
  border-left: 4px solid; background: rgba(255, 255, 255, 0.35);
  border-radius: 0 3px 3px 0; padding: 0.4rem 0.55rem; margin-bottom: 0.45rem;
  font-size: 0.82rem;
}
.ss-margin-row-head { display: flex; align-items: center; justify-content: space-between; }
.ss-margin-row-head .badge { border-radius: 3px; }

.ss-map-band { overflow-x: auto; }
.ss-map-track { position: relative; height: 100%; }
.ss-map-cell {
  position: absolute; top: 0; bottom: 0;
  display: flex; align-items: center; justify-content: center;
  border-right: 1px solid rgba(255, 255, 255, 0.12);
  overflow: hidden; padding: 0;
}
.ss-map-cell.ss-pillar {
  background: repeating-linear-gradient(180deg, var(--ss-pillar) 0 8px, #2a2824 8px 16px);
  box-shadow: inset 0 0 0 2px #1a1814;
}
.ss-map-cell.ss-pillar .ss-map-label { color: #c8c0b4; writing-mode: vertical-rl; letter-spacing: 0.15em; font-size: 0.7rem; }
.ss-map-cell.ss-margin {
  border: 1px dashed; border-top: none; border-bottom: none;
  background-image: repeating-linear-gradient(45deg, rgba(255,255,255,0.25) 0 6px, transparent 6px 12px);
  font-size: 0.72rem; font-weight: 800;
}
.ss-map-cell.ss-margin .ss-map-label { color: var(--ss-paper); text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85); font-weight: 800; }
.ss-map-label { padding: 0 0.3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 700; font-size: 0.78rem; }

.ss-drawer-mask { position: fixed; inset: 0; background: rgba(26, 20, 14, 0.4); z-index: 40; display: flex; justify-content: flex-end; }
.ss-drawer {
  width: 320px; max-width: 85vw; height: 100%;
  background: var(--ss-paper); border-left: 3px solid var(--ss-accent);
  padding: 0.9rem 1rem; overflow-y: auto;
}
.ss-drawer header { display: flex; align-items: center; justify-content: space-between; }
.ss-drawer h2 { margin: 0; font-size: 1rem; }
.ss-run-list { list-style: none; margin: 0.6rem 0 0; padding: 0; }
.ss-run-list li {
  display: flex; flex-direction: column; gap: 0.15rem;
  padding: 0.55rem 0.7rem; border: 2px solid var(--ss-curb); border-radius: 4px;
  margin-bottom: 0.45rem; cursor: pointer; background: rgba(255,255,255,0.4);
}
.ss-run-list li:hover { border-color: var(--ss-accent); }
.ss-run-list li.active { border-color: var(--ss-accent); background: rgba(196, 92, 38, 0.12); }
.ss-drawer-enter-active, .ss-drawer-leave-active { transition: opacity 0.15s; }
.ss-drawer-enter-from, .ss-drawer-leave-to { opacity: 0; }

@media (max-width: 820px) {
  .ss-map-body { flex-direction: column; }
  .ss-margin-rail { flex: 0 0 auto; }
}
</style>
