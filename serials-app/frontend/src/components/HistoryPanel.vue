<template>
  <section class="history panel">
    <h3>操作历史（入藏 / 移库 / 合订 / 拆订）</h3>
    <table v-if="logs.length">
      <thead>
        <tr><th>时间</th><th>操作</th><th>对象</th><th>位置变化</th><th>操作人</th><th>明细</th></tr>
      </thead>
      <tbody>
        <tr v-for="l in logs" :key="l.id">
          <td class="mono">{{ fmt(l.created_at) }}</td>
          <td><span class="op" :class="l.type">{{ l.type_display }}</span></td>
          <td class="mono">{{ l.bound_volume_barcode || l.item_barcode || l.issue_label || '—' }}</td>
          <td>
            <template v-if="l.from_location_name || l.to_location_name">
              {{ l.from_location_name || '—' }} → {{ l.to_location_name || '—' }}
            </template>
            <template v-else>—</template>
          </td>
          <td>{{ l.actor }}</td>
          <td class="detail">{{ detail(l) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">暂无操作记录。</p>
  </section>
</template>

<script setup>
defineProps({
  logs: { type: Array, default: () => [] },
})

function fmt(iso) {
  return (iso || '').replace('T', ' ').slice(0, 19)
}

function detail(l) {
  const p = l.payload || {}
  if (l.type === 'BIND' && p.items) return `合订 ${p.items.length} 册：${p.items.map((i) => i.barcode).join(', ')}`
  if (l.type === 'UNBIND' && p.restored)
    return `逐册恢复：${p.restored.map((r) => `${r.barcode}→${r.restored_location}`).join(', ')}`
  if (l.type === 'CHECK_IN') return `复本号 ${p.copy_no}`
  if (l.type === 'ISSUE_REGISTER') return p.label || ''
  if (l.type === 'RENUMBER' && p.old && p.new)
    return `第${p.old.volume}卷第${p.old.number}期 → 第${p.new.volume}卷第${p.new.number}期（${p.reason || ''}）${
      p.collisions && p.collisions.length ? ' ⚠️重名' : ''
    }`
  if (l.type === 'TITLE_RESUME' && p.previous_ceased)
    return `停刊（至${p.previous_ceased.year}年${p.previous_ceased.month}月）更正为延迟出版`
  if (l.type === 'SPLIT_VOLUME' && p.moved)
    return `拆出 ${p.moved.length} 册 → ${p.new_barcode}：${p.moved.join(', ')}`
  if (l.type === 'WITHDRAW_ITEM') return `${p.barcode || ''} ${p.reason || ''}`
  return ''
}
</script>

<style scoped>
.panel { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px 14px; }
h3 { margin: 0 0 8px; font-size: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border: 1px solid #e0e0e0; padding: 5px 6px; text-align: left; }
th { background: #fafafa; }
.mono { font-family: ui-monospace, monospace; font-size: 11px; }
.op { padding: 1px 6px; border-radius: 8px; font-size: 11px; white-space: nowrap; background: #eceff1; color: #37474f; }
.op.CHECK_IN { background: #e8f5e9; color: #2e7d32; }
.op.BIND { background: #e3f2fd; color: #1565c0; }
.op.UNBIND { background: #fce4ec; color: #ad1457; }
.op.MOVE_ITEM, .op.MOVE_VOLUME { background: #fff3e0; color: #e65100; }
.detail { color: #555; max-width: 320px; }
.empty { color: #888; font-size: 13px; }
</style>
