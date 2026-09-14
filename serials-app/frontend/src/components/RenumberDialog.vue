<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>改号（出版社更正卷期编号）</h3>
      <p class="tip">
        只新增编号映射版本：单元身份与实体记录不变，旧编号仍可检索；已合订册内改号不影响册序。
      </p>
      <label>出版单元
        <select v-model="issueId" @change="onPick">
          <option v-for="i in issues" :key="i.id" :value="i.id">
            #{{ i.id }} {{ i.label }}
          </option>
        </select>
      </label>
      <div class="row">
        <label>新卷 <input v-model.number="volume" type="number" min="1" /></label>
        <label>新期号 <input v-model.number="number" type="number" min="1" /></label>
        <label v-if="isCombined">止期号 <input v-model.number="numberEnd" type="number" min="2" /></label>
      </div>
      <label>改号原因
        <input v-model.trim="reason" placeholder="如：出版社更正：第9期应为第10期" />
      </label>
      <p v-if="warning" class="warning">{{ warning }}</p>
      <p v-if="error" class="error">{{ error }}</p>
      <footer>
        <button @click="$emit('close')">取消</button>
        <button class="primary" :disabled="!issueId || !volume || !number" @click="submit">改号</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  titleId: { type: Number, required: true },
})
const emit = defineEmits(['close', 'done'])

const issues = ref([])
const issueId = ref(null)
const volume = ref(null)
const number = ref(null)
const numberEnd = ref(null)
const reason = ref('')
const warning = ref('')
const error = ref('')

const isCombined = computed(() => {
  const i = issues.value.find((x) => x.id === issueId.value)
  return i && i.kind === 'COMBINED'
})

onMounted(async () => {
  const all = await api.get(`/issues/?title=${props.titleId}`)
  issues.value = all.filter((i) => i.kind !== 'SUPPLEMENT')
  if (issues.value.length) {
    issueId.value = issues.value[0].id
    onPick()
  }
})

function onPick() {
  const i = issues.value.find((x) => x.id === issueId.value)
  if (i) {
    volume.value = i.volume
    number.value = i.number
    numberEnd.value = i.number_end
  }
}

async function submit() {
  error.value = ''
  warning.value = ''
  try {
    const resp = await api.post(`/issues/${issueId.value}/renumber/`, {
      volume: volume.value,
      number: number.value,
      number_end: isCombined.value ? numberEnd.value : null,
      reason: reason.value,
      actor: 'librarian',
    })
    if (resp.warning) {
      warning.value = `${resp.warning}（重名单元：${resp.collisions.map((c) => '#' + c.issue_id).join(', ')}）——已生效，3 秒后关闭`
      setTimeout(() => emit('done'), 3000)
    } else {
      emit('done')
    }
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; align-items: center; justify-content: center; z-index: 40; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 480px; max-width: 94vw; }
h3 { margin: 0 0 8px; font-size: 15px; }
.tip { font-size: 12px; color: #777; background: #f5f5f5; border-radius: 6px; padding: 6px 8px; }
label { display: block; font-size: 12px; color: #555; margin-bottom: 8px; }
.row { display: flex; gap: 10px; }
.row label { flex: 1; }
select, input { display: block; width: 100%; margin-top: 3px; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.warning { font-size: 12px; color: #e65100; background: #fff3e0; border-radius: 6px; padding: 6px 8px; }
.error { font-size: 12px; color: #c62828; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
button.primary { background: #1976d2; border-color: #1976d2; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
</style>
