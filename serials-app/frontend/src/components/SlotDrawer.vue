<template>
  <div class="drawer-mask" @click.self="$emit('close')">
    <div class="drawer">
      <header>
        <h3>{{ slot.year }}年{{ slot.month }}月 · 第{{ slot.volume }}卷第{{ slot.number }}期</h3>
        <button class="close" @click="$emit('close')">×</button>
      </header>

      <p class="state-line">
        状态：<span class="state" :class="slot.state">{{ stateText }}</span>
      </p>

      <template v-if="slot.issue">
        <h4>出版登记</h4>
        <p class="issue-label">
          {{ slot.issue.label }}
          <span class="kind">{{ slot.issue.kind_display }}</span>
        </p>
        <p v-if="slot.issue.kind === 'COMBINED'" class="covers">
          覆盖期号：{{ slot.issue.covers.map((c) => `第${c.number}期`).join('、') }}
          —— 一期合刊覆盖两个期号，被覆盖期号不算缺号。
        </p>
      </template>

      <template v-if="slot.items && slot.items.length">
        <h4>馆藏实体（{{ slot.items.length }} 册）</h4>
        <table>
          <thead>
            <tr><th>条码</th><th>复本</th><th>状态</th><th>登记位置</th><th>实际位置</th><th>所在合订本</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in slot.items" :key="it.id">
              <td class="mono">{{ it.barcode }}</td>
              <td>{{ it.copy_no }}</td>
              <td>{{ it.status_display }}</td>
              <td>{{ it.location.code }}</td>
              <td>{{ it.effective_location ? it.effective_location.code : '—' }}</td>
              <td>
                <template v-if="it.bound_volume">
                  <span class="mono">{{ it.bound_volume.barcode }}</span>
                  （{{ it.bound_volume.location.code }}）
                </template>
                <template v-else>—</template>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <div v-if="slot.verification" class="verification">
        <h4>核实提示</h4>
        <p>{{ slot.verification }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  slot: { type: Object, required: true },
})
defineEmits(['close'])

const stateText = computed(
  () =>
    ({
      HELD: '在藏',
      MISSING: '缺藏',
      NOT_PUBLISHED: '缺号（未登记出版）',
    }[props.slot.state] || props.slot.state),
)
</script>

<style scoped>
.drawer-mask {
  position: fixed; inset: 0; background: rgba(0, 0, 0, 0.35);
  display: flex; justify-content: flex-end; z-index: 30;
}
.drawer {
  width: 560px; max-width: 92vw; height: 100%; overflow-y: auto;
  background: #fff; padding: 18px 20px; box-shadow: -4px 0 16px rgba(0, 0, 0, 0.15);
}
header { display: flex; justify-content: space-between; align-items: center; }
h3 { margin: 0; font-size: 16px; }
h4 { margin: 16px 0 6px; font-size: 13px; color: #555; }
.close { border: none; background: none; font-size: 22px; cursor: pointer; color: #888; }
.state { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.state.HELD { background: #e8f5e9; color: #2e7d32; }
.state.MISSING { background: #ffebee; color: #c62828; }
.state.NOT_PUBLISHED { background: #f5f5f5; color: #616161; }
.kind { font-size: 11px; background: #e3f2fd; color: #1565c0; border-radius: 8px; padding: 1px 6px; margin-left: 6px; }
.covers { font-size: 12px; color: #6d4c41; background: #fbe9e7; border-radius: 6px; padding: 6px 8px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border: 1px solid #e0e0e0; padding: 5px 6px; text-align: left; }
th { background: #fafafa; }
.mono { font-family: ui-monospace, monospace; }
.verification { background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px; padding: 4px 10px; margin-top: 12px; }
.verification p { font-size: 12px; color: #6d4c41; }
</style>
