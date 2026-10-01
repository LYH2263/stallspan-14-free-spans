<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const bands = ref<any[]>([])
onMounted(async () => {
  const data = await api('/allocate/latest?segment_id=1')
  rows.value = data.rejected || []
  bands.value = data.margin_bands || []
})
// 可摆提示：与主图色带、运行抽屉同一套余量色档
function hint(r: any): string {
  const fit = bands.value.filter(b => b.length_m + 1e-9 >= r.width_m)
  if (fit.length) {
    const b = fit[0]
    return `可摆 ${fit.length} 段：如 ${b.start_m}–${b.end_m}m（余 ${b.length_m}m · ${b.tier}）`
  }
  if (!bands.value.length) return '无余量空档可摆'
  const max = bands.value.reduce((a, b) => (b.length_m > a.length_m ? b : a))
  return `无可摆空档 · 最大余量 ${max.length_m}m（${max.tier}）`
}
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">无法在连续空档内安置且不跨越挡柱的摊位 · 可摆提示取自本次运行余量色档</p>
  <div class="card">
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th><th>可摆提示</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td><td>{{ hint(r) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="muted">全部放下</p>
  </div>
</template>
