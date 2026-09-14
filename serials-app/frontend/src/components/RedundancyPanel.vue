<template>
  <section v-if="redundancies && redundancies.length" class="redundancy panel">
    <h3>
      多单元覆盖（补寄待决）
      <span class="count">{{ redundancies.length }} 个 slot 由多个出版单元覆盖</span>
    </h3>
    <p class="hint">
      补寄单期与原合刊并存。系统不会自动删除合刊——请馆员逐 slot 决定保留或注销多余实体。
    </p>
    <table>
      <thead>
        <tr><th>发行年月</th><th>卷期</th><th>覆盖单元</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="r in redundancies" :key="`${r.year}-${r.month}`">
          <td>{{ r.year }}-{{ String(r.month).padStart(2, '0') }}</td>
          <td>第{{ r.volume }}卷 第{{ r.number }}期</td>
          <td>
            <span v-for="(l, i) in r.labels" :key="i" class="unit-chip">
              #{{ r.issue_ids[i] }} {{ l }}
            </span>
          </td>
          <td><button @click="$emit('select', { year: r.year, month: r.month })">处理</button></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
defineProps({
  redundancies: { type: Array, default: () => [] },
  slots: { type: Array, default: () => [] },
})
defineEmits(['select'])
</script>

<style scoped>
.panel { background: #fff; border: 1px solid #f48fb1; border-radius: 8px; padding: 12px 14px; }
h3 { margin: 0 0 4px; font-size: 14px; color: #880e4f; }
.count { font-size: 12px; color: #888; font-weight: normal; margin-left: 8px; }
.hint { font-size: 12px; color: #777; margin: 0 0 8px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border: 1px solid #e0e0e0; padding: 5px 6px; text-align: left; }
th { background: #fafafa; }
.unit-chip { display: inline-block; background: #fce4ec; border-radius: 8px; padding: 1px 6px; margin: 1px 4px 1px 0; font-size: 11px; }
button { padding: 3px 10px; border: 1px solid #ad1457; color: #ad1457; background: #fff; border-radius: 4px; cursor: pointer; font-size: 12px; }
</style>
