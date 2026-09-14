<template>
  <section class="gaps panel">
    <h3>
      缺藏 / 缺号清单
      <span class="count">{{ gaps.length }} 项待核实，{{ verified.size }} 项已核实</span>
    </h3>
    <p class="hint">缺号不等于缺藏：「缺藏」是已出版但无实体；「缺号」是无出版登记，需先与出版方核实。</p>
    <table v-if="gaps.length">
      <thead>
        <tr><th></th><th>发行年月</th><th>卷期</th><th>判定</th><th>逐项核实提示</th></tr>
      </thead>
      <tbody>
        <tr v-for="g in gaps" :key="`${g.year}-${g.month}`" :class="{ done: verified.has(key(g)) }">
          <td><input type="checkbox" :checked="verified.has(key(g))" @change="toggle(g)" /></td>
          <td>{{ g.year }}-{{ String(g.month).padStart(2, '0') }}</td>
          <td>第{{ g.volume }}卷 第{{ g.number }}期</td>
          <td><span class="state" :class="g.state">{{ g.state_display }}</span></td>
          <td class="verif">{{ g.verification }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">无缺藏、无缺号。</p>
  </section>
</template>

<script setup>
import { reactive } from 'vue'

const props = defineProps({
  gaps: { type: Array, default: () => [] },
})

const verified = reactive(new Set())

function key(g) {
  return `${g.year}-${g.month}`
}

function toggle(g) {
  const k = key(g)
  if (verified.has(k)) verified.delete(k)
  else verified.add(k)
}
</script>

<style scoped>
.panel { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px 14px; }
h3 { margin: 0 0 4px; font-size: 14px; }
.count { font-size: 12px; color: #888; font-weight: normal; margin-left: 8px; }
.hint { font-size: 12px; color: #777; margin: 0 0 8px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border: 1px solid #e0e0e0; padding: 5px 6px; text-align: left; vertical-align: top; }
th { background: #fafafa; }
tr.done td { opacity: 0.45; text-decoration: line-through; }
tr.done td:first-child { text-decoration: none; opacity: 1; }
.state { padding: 1px 6px; border-radius: 8px; font-size: 11px; white-space: nowrap; }
.state.MISSING { background: #ffebee; color: #c62828; }
.state.NOT_PUBLISHED { background: #f5f5f5; color: #616161; }
.verif { color: #6d4c41; }
.empty { color: #2e7d32; font-size: 13px; }
</style>
