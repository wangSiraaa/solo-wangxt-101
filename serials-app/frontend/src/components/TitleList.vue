<template>
  <aside class="title-list">
    <h2>刊名</h2>
    <div
      v-for="t in titles"
      :key="t.id"
      class="title-card"
      :class="{ active: t.id === selectedId }"
      @click="$emit('select', t.id)"
    >
      <div class="name-row">
        <span class="name">{{ t.name }}</span>
        <span class="badge" :class="t.status === 'CEASED' ? 'ceased' : 'active'">
          {{ t.status_display }}<template v-if="t.status === 'CEASED'">
            {{ t.ceased_year }}-{{ String(t.ceased_month).padStart(2, '0') }}
          </template>
        </span>
      </div>
      <div class="meta">
        {{ t.frequency_display }} · ISSN {{ t.issn || '—' }} · 自第{{ t.volume_start_number }}卷起
      </div>
      <div v-if="t.predecessor_name" class="lineage">沿革：前身为《{{ t.predecessor_name }}》</div>
    </div>
  </aside>
</template>

<script setup>
defineProps({
  titles: { type: Array, default: () => [] },
  selectedId: { type: Number, default: null },
})
defineEmits(['select'])
</script>

<style scoped>
.title-list { width: 260px; flex-shrink: 0; overflow-y: auto; }
h2 { font-size: 14px; color: #666; margin: 0 0 8px; }
.title-card {
  border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px 12px;
  margin-bottom: 8px; cursor: pointer; background: #fff;
}
.title-card:hover { border-color: #90caf9; }
.title-card.active { border-color: #1976d2; box-shadow: 0 0 0 1px #1976d2 inset; }
.name-row { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.name { font-weight: 600; }
.badge { font-size: 11px; padding: 1px 6px; border-radius: 10px; white-space: nowrap; }
.badge.active { background: #e8f5e9; color: #2e7d32; }
.badge.ceased { background: #efebe9; color: #6d4c41; }
.meta { font-size: 12px; color: #777; margin-top: 4px; }
.lineage { font-size: 12px; color: #8d6e63; margin-top: 2px; }
</style>
