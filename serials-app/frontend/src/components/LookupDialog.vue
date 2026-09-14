<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>编号检索（含历史版本）</h3>
      <p class="tip">
        旧编号仍可检索；重名时列出全部匹配单元，各自指向自己的实体——历史目录链接不会指向错误实体。
      </p>
      <div class="row">
        <label>卷 <input v-model.number="volume" type="number" min="1" /></label>
        <label>期号 <input v-model.number="number" type="number" min="1" /></label>
        <label>时间点（可选） <input v-model="at" type="datetime-local" /></label>
      </div>
      <button class="primary search" :disabled="!volume || !number" @click="search">检索</button>

      <div v-if="searched" class="results">
        <p v-if="!matches.length" class="empty">无匹配的编号版本。</p>
        <div v-for="(m, i) in matches" :key="i" class="match">
          <p class="mhead">
            <span class="uid">单元#{{ m.issue.id }}</span>
            {{ m.issue.label }}
            <span class="ver" :class="{ current: m.assignment.is_current }">
              {{ m.assignment.is_current ? '当前编号' : '历史编号' }}
            </span>
          </p>
          <p class="mline">
            编号 {{ m.assignment.number_label }} · 有效期
            {{ fmt(m.assignment.valid_from) }} ~ {{ m.assignment.valid_to ? fmt(m.assignment.valid_to) : '至今' }}
            <template v-if="m.assignment.reason"> · {{ m.assignment.reason }}</template>
          </p>
          <p class="mline">
            实体：
            <template v-if="m.items.length">
              <span v-for="it in m.items" :key="it.id" class="barcode">{{ it.barcode }}（{{ it.status_display }}）</span>
            </template>
            <template v-else>无</template>
          </p>
        </div>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <footer><button @click="$emit('close')">关闭</button></footer>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  titleId: { type: Number, required: true },
})
defineEmits(['close'])

const volume = ref(null)
const number = ref(null)
const at = ref('')
const matches = ref([])
const searched = ref(false)
const error = ref('')

function fmt(iso) {
  return (iso || '').replace('T', ' ').slice(0, 16)
}

async function search() {
  error.value = ''
  try {
    let url = `/lookup/numbering/?title=${props.titleId}&volume=${volume.value}&number=${number.value}`
    if (at.value) url += `&at=${encodeURIComponent(new Date(at.value).toISOString())}`
    const data = await api.get(url)
    matches.value = data.matches
    searched.value = true
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; align-items: center; justify-content: center; z-index: 40; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 560px; max-width: 94vw; max-height: 86vh; overflow-y: auto; }
h3 { margin: 0 0 8px; font-size: 15px; }
.tip { font-size: 12px; color: #777; background: #f5f5f5; border-radius: 6px; padding: 6px 8px; }
.row { display: flex; gap: 10px; }
.row label { flex: 1; font-size: 12px; color: #555; }
input { display: block; width: 100%; margin-top: 3px; padding: 6px 8px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.search { margin: 4px 0 10px; }
.results { border-top: 1px solid #eee; padding-top: 8px; }
.match { border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }
.mhead { margin: 0 0 4px; font-size: 13px; }
.uid { font-family: ui-monospace, monospace; background: #eceff1; border-radius: 4px; padding: 1px 5px; font-size: 11px; margin-right: 4px; }
.ver { font-size: 11px; border-radius: 8px; padding: 1px 6px; margin-left: 6px; background: #f5f5f5; color: #616161; }
.ver.current { background: #b2dfdb; color: #004d40; }
.mline { margin: 2px 0; font-size: 12px; color: #555; }
.barcode { font-family: ui-monospace, monospace; background: #eceff1; border-radius: 4px; padding: 1px 5px; margin-right: 4px; font-size: 11px; }
.empty { color: #999; font-size: 13px; }
.error { font-size: 12px; color: #c62828; }
footer { display: flex; justify-content: flex-end; margin-top: 8px; }
button { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
button.primary { background: #1976d2; border-color: #1976d2; color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }
</style>
