<template>
  <section class="timeline">
    <div class="legend">
      <span><i class="sw held"></i>在藏</span>
      <span><i class="sw missing"></i>缺藏</span>
      <span><i class="sw notpub"></i>缺号（未登记出版）</span>
      <span><i class="tag-demo">合</i>合期</span>
      <span><i class="tag-demo bound">订</i>已装订</span>
      <span><i class="tag-demo supp">增</i>增刊</span>
    </div>

    <div v-for="y in years" :key="y" class="year-row">
      <div class="year-label">{{ y }}</div>
      <div
        v-for="m in 12"
        :key="m"
        class="month-cell"
        :class="cellClass(y, m)"
        @click="onClick(y, m)"
      >
        <span class="month">{{ m }}月</span>
        <template v-if="slotAt(y, m)">
          <span class="vol">v{{ slotAt(y, m).volume }}·{{ slotAt(y, m).number }}</span>
          <span class="tags">
            <span v-if="slotAt(y, m).issue && slotAt(y, m).issue.kind === 'COMBINED'" class="tag">合</span>
            <span v-if="hasBound(slotAt(y, m))" class="tag bound">订</span>
          </span>
        </template>
        <span v-if="suppAt(y, m)" class="tag supp" :title="suppAt(y, m).label">增</span>
      </div>
    </div>

    <div v-if="data.supplements && data.supplements.length" class="supp-list">
      <strong>增刊：</strong>
      <span v-for="s in data.supplements" :key="s.id" class="supp-chip">
        {{ s.label }}（{{ s.items.length }} 册）
      </span>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, required: true },
})
const emit = defineEmits(['select'])

const slotMap = computed(() => {
  const map = {}
  for (const s of props.data.slots || []) map[`${s.year}-${s.month}`] = s
  return map
})

const suppMap = computed(() => {
  const map = {}
  for (const s of props.data.supplements || []) map[`${s.pub_year}-${s.pub_month}`] = s
  return map
})

const years = computed(() => {
  const set = new Set()
  for (const s of props.data.slots || []) set.add(s.year)
  for (const s of props.data.supplements || []) set.add(s.pub_year)
  return [...set].sort()
})

function slotAt(y, m) {
  return slotMap.value[`${y}-${m}`]
}

function suppAt(y, m) {
  return suppMap.value[`${y}-${m}`]
}

function hasBound(slot) {
  return (slot.items || []).some((it) => it.bound_volume)
}

function cellClass(y, m) {
  const s = slotAt(y, m)
  if (!s) return 'empty'
  return {
    HELD: 'held',
    MISSING: 'missing',
    NOT_PUBLISHED: 'notpub',
  }[s.state] || 'empty'
}

function onClick(y, m) {
  const s = slotAt(y, m)
  if (s) emit('select', s)
}
</script>

<style scoped>
.timeline { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; }
.legend { display: flex; gap: 14px; font-size: 12px; color: #555; margin-bottom: 10px; align-items: center; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 4px; vertical-align: -2px; }
.sw.held { background: #c8e6c9; border: 1px solid #66bb6a; }
.sw.missing { background: #ffcdd2; border: 1px solid #e57373; }
.sw.notpub { background: #f5f5f5; border: 1px dashed #9e9e9e; }
.tag-demo { display: inline-block; font-size: 10px; font-style: normal; padding: 0 4px; border-radius: 3px; background: #bbdefb; color: #0d47a1; margin-right: 4px; }
.tag-demo.bound { background: #d1c4e9; color: #4527a0; }
.tag-demo.supp { background: #ffe0b2; color: #e65100; }
.year-row { display: flex; align-items: stretch; gap: 4px; margin-bottom: 4px; }
.year-label { width: 44px; font-weight: 600; color: #444; display: flex; align-items: center; }
.month-cell {
  position: relative; flex: 1; min-width: 56px; height: 52px; border-radius: 6px;
  border: 1px solid transparent; padding: 3px 5px; font-size: 11px; cursor: pointer;
  display: flex; flex-direction: column; justify-content: space-between;
}
.month-cell.empty { background: transparent; border-color: transparent; cursor: default; }
.month-cell.held { background: #e8f5e9; border-color: #a5d6a7; }
.month-cell.missing { background: #ffebee; border-color: #ef9a9a; }
.month-cell.notpub { background: #fafafa; border: 1px dashed #bdbdbd; cursor: pointer; }
.month-cell.held:hover, .month-cell.missing:hover, .month-cell.notpub:hover { outline: 2px solid #1976d2; }
.month { color: #888; }
.vol { font-weight: 600; color: #333; }
.tags { position: absolute; top: 3px; right: 4px; display: flex; gap: 2px; }
.tag { font-size: 10px; padding: 0 4px; border-radius: 3px; background: #bbdefb; color: #0d47a1; }
.tag.bound { background: #d1c4e9; color: #4527a0; }
.tag.supp { position: absolute; bottom: 3px; right: 4px; background: #ffe0b2; color: #e65100; }
.supp-list { margin-top: 10px; font-size: 12px; color: #555; }
.supp-chip { display: inline-block; background: #fff3e0; border: 1px solid #ffcc80; border-radius: 10px; padding: 1px 8px; margin: 2px 4px 2px 0; }
</style>
