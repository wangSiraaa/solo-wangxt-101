<template>
  <div class="drawer-mask" @click.self="$emit('close')">
    <div class="drawer">
      <header>
        <h3>{{ slot.year }}年{{ slot.month }}月 · 第{{ slot.volume }}卷第{{ slot.number }}期</h3>
        <button class="close" @click="$emit('close')">×</button>
      </header>

      <p class="state-line">
        状态：<span class="state" :class="slot.state">{{ stateText }}</span>
        <span v-if="slot.redundant" class="state REDUNDANT">多单元覆盖（待馆员决定）</span>
      </p>

      <template v-if="units.length">
        <h4>覆盖本期的出版单元（{{ units.length }} 个）</h4>
        <div v-for="u in units" :key="u.id" class="unit">
          <p class="unit-head">
            <span class="uid">单元#{{ u.id }}</span>
            {{ u.label }}
            <span class="kind">{{ u.kind_display }}</span>
          </p>
          <p v-if="u.kind === 'COMBINED'" class="covers">
            一期合刊覆盖 {{ u.covers.map((c) => `第${c.number}期`).join('、') }}
            —— 覆盖多个单元不等于有多本可借实体。
          </p>
          <div v-if="u.numberings && u.numberings.length > 1" class="history">
            编号沿革：
            <span v-for="n in u.numberings" :key="n.id" class="ver" :class="{ current: n.is_current }">
              {{ n.number_label }}<template v-if="!n.is_current">（{{ (n.valid_to || '').slice(0, 10) }} 失效{{ n.reason ? `：${n.reason}` : '' }}）</template>
              <template v-else>（当前）</template>
            </span>
          </div>
        </div>
      </template>

      <template v-if="slot.items && slot.items.length">
        <h4>可借实体（{{ slot.items.length }} 册）</h4>
        <table>
          <thead>
            <tr><th>条码</th><th>复本</th><th>状态</th><th>实际位置</th><th>所在合订本</th><th v-if="slot.redundant"></th></tr>
          </thead>
          <tbody>
            <tr v-for="it in slot.items" :key="it.id">
              <td class="mono">{{ it.barcode }}</td>
              <td>{{ it.copy_no }}</td>
              <td>{{ it.status_display }}</td>
              <td>{{ it.effective_location ? it.effective_location.code : '—' }}</td>
              <td>
                <template v-if="it.bound_volume">
                  <span class="mono">{{ it.bound_volume.barcode }}</span>
                </template>
                <template v-else>—</template>
              </td>
              <td v-if="slot.redundant">
                <button class="withdraw" @click="withdraw(it)">注销</button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>

      <template v-if="slot.withdrawn_items && slot.withdrawn_items.length">
        <h4>已注销实体（不计入可借）</h4>
        <table class="withdrawn">
          <tbody>
            <tr v-for="it in slot.withdrawn_items" :key="it.id">
              <td class="mono">{{ it.barcode }}</td>
              <td>{{ it.status_display }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <div v-if="slot.explanation && slot.explanation.length" class="explanation">
        <h4>判定解释（可逐项核实）</h4>
        <ul>
          <li v-for="(e, i) in slot.explanation" :key="i">{{ e }}</li>
        </ul>
      </div>

      <div v-if="slot.verification" class="verification">
        <h4>核实提示</h4>
        <p>{{ slot.verification }}</p>
      </div>

      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  slot: { type: Object, required: true },
})
const emit = defineEmits(['close', 'withdrawn'])

const error = ref('')

const units = computed(() => props.slot.units || (props.slot.issue ? [props.slot.issue] : []))

const stateText = computed(
  () =>
    ({
      HELD: '在藏',
      MISSING: '缺藏',
      NOT_PUBLISHED: '缺号（未登记出版）',
    }[props.slot.state] || props.slot.state),
)

async function withdraw(item) {
  const reason = window.prompt(
    `注销 ${item.barcode} 的原因（如：补寄单期已到，不再保留合刊复本）`,
    '补寄单期已到，馆员决定注销',
  )
  if (reason === null) return
  error.value = ''
  try {
    await api.post(`/items/${item.id}/withdraw/`, { reason, actor: 'librarian' })
    emit('withdrawn')
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.drawer-mask {
  position: fixed; inset: 0; background: rgba(0, 0, 0, 0.35);
  display: flex; justify-content: flex-end; z-index: 30;
}
.drawer {
  width: 620px; max-width: 94vw; height: 100%; overflow-y: auto;
  background: #fff; padding: 18px 20px; box-shadow: -4px 0 16px rgba(0, 0, 0, 0.15);
}
header { display: flex; justify-content: space-between; align-items: center; }
h3 { margin: 0; font-size: 16px; }
h4 { margin: 16px 0 6px; font-size: 13px; color: #555; }
.close { border: none; background: none; font-size: 22px; cursor: pointer; color: #888; }
.state { padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-right: 6px; }
.state.HELD { background: #e8f5e9; color: #2e7d32; }
.state.MISSING { background: #ffebee; color: #c62828; }
.state.NOT_PUBLISHED { background: #f5f5f5; color: #616161; }
.state.REDUNDANT { background: #f8bbd0; color: #880e4f; }
.unit { border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }
.unit-head { margin: 0; font-size: 13px; }
.uid { font-family: ui-monospace, monospace; background: #eceff1; border-radius: 4px; padding: 1px 5px; font-size: 11px; margin-right: 4px; }
.kind { font-size: 11px; background: #e3f2fd; color: #1565c0; border-radius: 8px; padding: 1px 6px; margin-left: 6px; }
.covers { font-size: 12px; color: #6d4c41; background: #fbe9e7; border-radius: 6px; padding: 6px 8px; margin: 6px 0 0; }
.history { font-size: 12px; color: #004d40; margin-top: 6px; }
.ver { background: #e0f2f1; border-radius: 4px; padding: 1px 5px; margin: 0 4px 2px 0; display: inline-block; }
.ver.current { background: #b2dfdb; font-weight: 600; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { border: 1px solid #e0e0e0; padding: 5px 6px; text-align: left; }
th { background: #fafafa; }
.mono { font-family: ui-monospace, monospace; }
table.withdrawn td { color: #999; }
.withdraw { font-size: 11px; padding: 2px 8px; border: 1px solid #c62828; color: #c62828; background: #fff; border-radius: 4px; cursor: pointer; }
.explanation { background: #e3f2fd; border: 1px solid #90caf9; border-radius: 6px; padding: 4px 10px; margin-top: 12px; }
.explanation ul { margin: 4px 0 8px; padding-left: 18px; }
.explanation li { font-size: 12px; color: #0d47a1; margin-bottom: 2px; }
.verification { background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px; padding: 4px 10px; margin-top: 12px; }
.verification p { font-size: 12px; color: #6d4c41; }
.error { color: #c62828; font-size: 12px; }
</style>
