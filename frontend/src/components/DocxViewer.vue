<template>
  <div class="docx-viewer">
    <div v-if="loading" class="viewer-loading">
      <a-spin tip="加载DOCX中..." />
    </div>
    <div v-else-if="error" class="viewer-error">
      <a-result status="error" title="DOCX加载失败" :sub-title="error">
        <template #extra>
          <a-button type="primary" @click="loadDocx">重试</a-button>
        </template>
      </a-result>
    </div>
    <div v-else class="docx-content" v-html="htmlContent"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'

const props = defineProps({
  /** DOCX文件预览URL */
  fileUrl: { type: String, required: true },
})

/** 加载状态 */
const loading = ref(true)

/** 错误信息 */
const error = ref('')

/** 转换后的HTML内容 */
const htmlContent = ref('')

/**
 * 加载并渲染DOCX文件
 * 使用mammoth.js将docx转为HTML
 */
async function loadDocx() {
  loading.value = true
  error.value = ''

  try {
    // 动态导入mammoth，减小首屏加载体积
    const mammoth = await import('mammoth')
    const response = await fetch(props.fileUrl)

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const arrayBuffer = await response.arrayBuffer()
    const result = await mammoth.convertToHtml({ arrayBuffer })
    htmlContent.value = result.value

    // 如果有警告信息，在控制台输出
    if (result.messages?.length) {
      console.warn('DOCX转换警告:', result.messages)
    }
  } catch (err) {
    error.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

/** 监听URL变化重新加载 */
watch(() => props.fileUrl, loadDocx)

onMounted(loadDocx)
</script>

<style scoped>
.docx-viewer {
  width: 100%;
  height: 100%;
  overflow: auto;
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

.docx-content {
  padding: 24px;
  font-size: 14px;
  line-height: 1.8;
  color: rgba(0, 0, 0, 0.85);
}

/* DOCX内容样式 */
.docx-content :deep(h1) { font-size: 24px; margin: 20px 0 12px; }
.docx-content :deep(h2) { font-size: 20px; margin: 16px 0 10px; }
.docx-content :deep(h3) { font-size: 16px; margin: 12px 0 8px; }
.docx-content :deep(p) { margin: 8px 0; }
.docx-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}
.docx-content :deep(td),
.docx-content :deep(th) {
  border: 1px solid #d9d9d9;
  padding: 8px 12px;
}
.docx-content :deep(img) {
  max-width: 100%;
  height: auto;
}
</style>
