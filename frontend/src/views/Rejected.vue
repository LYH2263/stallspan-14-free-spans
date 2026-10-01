<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { fitHintWithShortfall, marginsOf, TIER_META, type FitHintResult, type MarginGap } from '../margins'

const run = ref<any>(null)
onMounted(async () => { run.value = await api('/allocate/latest?segment_id=1') })

const rows = computed<any[]>(() => run.value?.rejected || [])
const margins = computed<MarginGap[]>(() => marginsOf(run.value))

const hints = computed<Record<number, FitHintResult>>(() => {
  const map: Record<number, FitHintResult> = {}
  for (const r of rows.value) {
    const h = fitHintWithShortfall(r.width_m, margins.value)
    if (h) map[r.vendor_id] = h
  }
  return map
})

function fmtTime(iso?: string): string {
  return iso ? iso.replace('T', ' ').slice(0, 19) : ''
}
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">无法在连续空档内安置且不跨越挡柱的摊位 · 可摆提示取本次运行同一套柱间余量</p>
  <div class="card">
    <table>
      <thead>
        <tr><th>摊主</th><th>需求宽度</th><th>原因</th><th>可摆提示（柱间余量）</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td>
          <td>{{ r.width_m }} m</td>
          <td>{{ r.reason }}</td>
          <td>
            <template v-if="hints[r.vendor_id]">
              <span
                class="badge"
                :style="{
                  background: TIER_META[hints[r.vendor_id].gap.tier].soft,
                  color: TIER_META[hints[r.vendor_id].gap.tier].color,
                }"
              >{{ TIER_META[hints[r.vendor_id].gap.tier].label }}</span>
              最大空档 {{ hints[r.vendor_id].gap.start_m }}–{{ hints[r.vendor_id].gap.end_m }} m
              （余 {{ hints[r.vendor_id].gap.length_m }} m）
              <template v-if="hints[r.vendor_id].fit">
                — <strong>可摆入</strong>
              </template>
              <template v-else>
                — 仍差 <strong>{{ hints[r.vendor_id].shortfall_m }} m</strong>
              </template>
            </template>
            <span v-else class="muted">本街段已无剩余空档</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="muted">全部放下</p>
    <p v-if="run" class="muted ss-run-ref">
      余量来自{{ run.created_at ? '运行 #' + run.id + '（' + fmtTime(run.created_at) + '）' : '当前计算'}}，
      共 {{ margins.length }} 段；与分配带色档同源。
    </p>
  </div>
</template>

<style scoped>
.ss-run-ref { margin-bottom: 0; font-size: 0.75rem; }
</style>
