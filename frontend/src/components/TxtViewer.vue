<template>
  <div class="txt-viewer">
    <div v-if="loading" class="viewer-loading">
      <a-spin tip="加载文本内容中..." />
    </div>
    <div v-else-if="error" class="viewer-error">
      <a-result status="error" title="文本加载失败" :sub-title="error">
        <template #extra>
          <a-button type="primary" @click="loadText">重试</a-button>
        </template>
      </a-result>
    </div>
    <div v-else class="txt-content-wrapper">
      <div class="txt-toolbar">
        <a-switch
          v-model:checked="highlightEnabled"
          size="small"
          checked-children="高亮"
          un-checked-children="纯文本"
        />
        <a-select
          v-if="highlightEnabled"
          v-model:value="language"
          size="small"
          style="width: 120px; margin-left: 8px"
          :options="languageOptions"
          placeholder="语言"
        />
      </div>
      <div class="txt-content">
        <pre v-if="!highlightEnabled" class="plain-text">{{ textContent }}</pre>
        <pre v-else class="highlight-text"><code :class="highlightClass" v-html="highlightedContent"></code></pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import hljs from 'highlight.js'
import * as api from '../api/index.js'

const props = defineProps({
  /** 文本文件预览URL */
  fileUrl: { type: String, required: true },
  /** 文件ID，用于通过API获取内容 */
  fileId: { type: [String, Number], required: true },
})

/** 加载状态 */
const loading = ref(true)

/** 错误信息 */
const error = ref('')

/** 文本内容 */
const textContent = ref('')

/** 是否启用代码高亮 */
const highlightEnabled = ref(false)

/** 选择的语言 */
const language = ref('auto')

/** 语言选项 */
const languageOptions = [
  { value: 'auto', label: '自动检测' },
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'java', label: 'Java' },
  { value: 'cpp', label: 'C/C++' },
  { value: 'json', label: 'JSON' },
  { value: 'yaml', label: 'YAML' },
  { value: 'xml', label: 'XML' },
  { value: 'sql', label: 'SQL' },
  { value: 'bash', label: 'Shell/Bash' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'plaintext', label: '纯文本' },
]

/**
 * 高亮语言的CSS类名
 */
const highlightClass = computed(() => {
  if (language.value === 'auto') return 'hljs'
  return `language-${language.value} hljs`
})

/**
 * 高亮后的HTML内容
 */
const highlightedContent = computed(() => {
  if (!textContent.value) return ''
  try {
    if (language.value === 'auto') {
      return hljs.highlightAuto(textContent.value).value
    }
    return hljs.highlight(textContent.value, { language: language.value }).value
  } catch {
    // 高亮失败时返回转义后的纯文本
    return escapeHtml(textContent.value)
  }
})

/**
 * 加载文本内容
 */
async function loadText() {
  loading.value = true
  error.value = ''

  try {
    const result = await api.getTxtContent(props.fileId)
    textContent.value = typeof result === 'string' ? result : JSON.stringify(result, null, 2)
  } catch (err) {
    error.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

/**
 * HTML转义
 * @param {string} str - 原始字符串
 * @returns {string} 转义后的字符串
 */
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/** 监听fileId变化重新加载 */
watch(() => props.fileId, loadText)

onMounted(loadText)
</script>

<style scoped>
.txt-viewer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.viewer-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.viewer-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.txt-content-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.txt-toolbar {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
  flex-shrink: 0;
}

.txt-content {
  flex: 1;
  overflow: auto;
  padding: 0;
}

.plain-text,
.highlight-text {
  margin: 0;
  padding: 16px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: rgba(0, 0, 0, 0.85);
  background: #fafafa;
  min-height: 100%;
}

.highlight-text {
  background: #1e1e1e;
  color: #d4d4d4;
}

.highlight-text :deep(.hljs) {
  background: transparent;
  padding: 0;
}
</style>
