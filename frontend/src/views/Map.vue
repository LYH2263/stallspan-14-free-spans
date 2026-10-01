<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const vendors = ref<any[]>([])
const drawerOpen = ref(false)
async function run() { data.value = await api('/allocate/run?segment_id=1', { method: 'POST' }) }
onMounted(async () => {
  vendors.value = await api('/vendors')
  await run()
})
const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
const TIER_CLS: Record<string, string> = { '紧': 'tight', '中': 'medium', '松': 'loose' }
const TIER_BADGE: Record<string, string> = { '紧': 'bad', '中': 'warn', '松': 'ok' }
const tierCls = (t: string) => TIER_CLS[t] || 'medium'
const tierBadge = (t: string) => TIER_BADGE[t] || 'warn'
const widthM = computed(() => data.value?.segment?.width_m || 1)
const pct = (m: number) => (m / widthM.value) * 100
// 同一套余量：主图色带、侧栏、运行抽屉都读这一个数组
const bands = computed<any[]>(() => data.value?.margin_bands || [])
const runTime = computed(() => (data.value?.created_at || '').replace('T', ' ').slice(0, 19))
const cells = computed(() => {
  if (!data.value) return []
  const out: any[] = []
  for (const p of data.value.pillars || []) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m/2, w: p.thickness_m, label: p.label || '挡柱' })
  }
  for (const [i, p] of (data.value.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m, label: p.vendor_name, color: colors[i % colors.length] })
  }
  return out
})
</script>
<template>
  <div class="ss-street-wrap">
    <div class="ss-map-head">
      <div>
        <h1>街段分配带</h1>
        <p class="sub">沿街一维开间 · 挡柱为竖直阻断 · 底部色带为柱间余量色档</p>
      </div>
      <div class="ss-map-actions">
        <button class="btn" @click="run">重新分配</button>
        <button class="btn btn-ghost" @click="drawerOpen = true">运行抽屉</button>
      </div>
    </div>
    <div class="ss-map-layout">
      <div class="ss-map-main">
        <div class="ss-band-ruler" v-if="data">
          <span>0 m</span>
          <span>{{ data.segment.name }} · {{ data.segment.width_m }} m</span>
          <span>{{ data.segment.width_m }} m</span>
        </div>
        <div class="ss-street-scroll" v-if="data">
          <div class="ss-street-scale">
            <div class="ss-street-band">
              <div class="ss-street-inner ss-abs">
                <div
                  v-for="(c,i) in cells" :key="i"
                  class="ss-band-cell"
                  :class="{ 'ss-pillar': c.type === 'pillar' }"
                  :style="{ left: pct(c.start) + '%', width: pct(c.w) + '%', background: c.type === 'pillar' ? undefined : c.color }"
                >{{ c.label }}</div>
              </div>
            </div>
            <div class="ss-margin-strip">
              <div
                v-for="(b,i) in bands" :key="i"
                class="ss-margin-cell"
                :class="'tier-' + tierCls(b.tier)"
                :style="{ left: pct(b.start_m) + '%', width: pct(b.length_m) + '%' }"
              >{{ b.length_m }}m·{{ b.tier }}</div>
              <div v-if="!bands.length" class="ss-margin-empty">无剩余空档 · 色档为空</div>
            </div>
          </div>
        </div>
        <div class="ss-margin-legend" v-if="data">
          <span><i class="dot tier-tight"></i>紧 &lt; 3m</span>
          <span><i class="dot tier-medium"></i>中 3–6m</span>
          <span><i class="dot tier-loose"></i>松 ≥ 6m</span>
          <span class="muted">色带与上图未涂色空隙逐段对齐</span>
        </div>
        <div class="ss-vendor-queue">
          <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
            <strong>{{ v.name }}</strong>
            <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
          </div>
        </div>
        <div class="card" v-if="data">
          <table>
            <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
            <tbody>
              <tr v-for="p in data.placements" :key="p.vendor_id">
                <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <aside class="ss-margin-side card" v-if="data">
        <h2>余量色档</h2>
        <p class="muted">柱间剩余空档 · 与主图色带同一套</p>
        <div v-for="(b,i) in bands" :key="i" class="ss-margin-row">
          <span class="badge" :class="'badge-' + tierBadge(b.tier)">{{ b.tier }}</span>
          <span class="ss-margin-range">{{ b.start_m }}–{{ b.end_m }} m</span>
          <span class="muted">余 {{ b.length_m }} m</span>
        </div>
        <p v-if="!bands.length" class="muted">无剩余空档，色档为空</p>
      </aside>
    </div>

    <div class="ss-drawer-mask" v-if="drawerOpen" @click="drawerOpen = false"></div>
    <aside class="ss-drawer" :class="{ open: drawerOpen }" v-if="data">
      <div class="ss-drawer-head">
        <h2>运行抽屉</h2>
        <button class="btn btn-ghost" @click="drawerOpen = false">收起</button>
      </div>
      <p class="muted">运行 #{{ data.id }} · {{ runTime }}</p>
      <div class="ss-drawer-stats">
        <div><span class="stat">{{ (data.placements || []).length }}</span>放置</div>
        <div><span class="stat">{{ (data.rejected || []).length }}</span>放不下</div>
        <div><span class="stat">{{ bands.length }}</span>余量段</div>
      </div>
      <h3>余量色档（与主图同一套）</h3>
      <div v-for="(b,i) in bands" :key="i" class="ss-margin-row">
        <span class="badge" :class="'badge-' + tierBadge(b.tier)">{{ b.tier }}</span>
        <span class="ss-margin-range">{{ b.start_m }}–{{ b.end_m }} m</span>
        <span class="muted">余 {{ b.length_m }} m</span>
      </div>
      <p v-if="!bands.length" class="muted">无剩余空档，色档为空</p>
      <h3>放不下</h3>
      <div v-for="r in data.rejected" :key="r.vendor_id" class="ss-margin-row">
        <strong>{{ r.vendor_name }}</strong>
        <span class="muted">需 {{ r.width_m }} m</span>
      </div>
      <p v-if="!(data.rejected || []).length" class="muted">全部放下</p>
    </aside>
  </div>
</template>
