<template>
  <div class="md-editor">
    <!-- 模式切换工具栏 -->
    <div class="editor-toolbar">
      <a-radio-group v-model:value="mode" size="small" button-style="solid">
        <a-radio-button value="edit">
          <EditOutlined /> 编辑
        </a-radio-button>
        <a-radio-button value="preview">
          <EyeOutlined /> 预览
        </a-radio-button>
        <a-radio-button value="split">
          <ColumnWidthOutlined /> 分屏
        </a-radio-button>
      </a-radio-group>
      <div class="toolbar-info">
        <span class="char-count">{{ charCount }} 字符</span>
        <span class="line-count">{{ lineCount }} 行</span>
      </div>
    </div>

    <!-- 编辑区域 -->
    <div class="editor-body">
      <!-- 编辑模式 -->
      <div v-if="mode === 'edit'" class="editor-pane full-pane">
        <textarea
          ref="textareaRef"
          class="editor-textarea"
          :value="localContent"
          @input="onInput"
          @keydown="onKeyDown"
          placeholder="Markdown内容将在此显示..."
          spellcheck="false"
        ></textarea>
      </div>

      <!-- 预览模式 -->
      <div v-else-if="mode === 'preview'" class="preview-pane full-pane" ref="previewRef">
        <div class="markdown-body" v-html="renderedHtml"></div>
      </div>

      <!-- 分屏模式 -->
      <template v-else>
        <div class="editor-pane split-pane">
          <textarea
            ref="splitTextareaRef"
            class="editor-textarea"
            :value="localContent"
            @input="onInput"
            @keydown="onKeyDown"
            placeholder="Markdown内容将在此显示..."
            spellcheck="false"
          ></textarea>
        </div>
        <div class="split-divider"></div>
        <div class="preview-pane split-pane" ref="splitPreviewRef">
          <div class="markdown-body" v-html="renderedHtml"></div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { EditOutlined, EyeOutlined, ColumnWidthOutlined } from '@ant-design/icons-vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

const props = defineProps({
  /** Markdown内容（v-model绑定） */
  modelValue: { type: String, default: '' },
  /** 所有区域数据 */
  regions: { type: Array, default: () => [] },
  /** 高亮的region ID（-1表示无高亮） */
  highlightRegionId: { type: Number, default: -1 },
})

const emit = defineEmits(['update:modelValue', 'save'])

/** 编辑器模式 */
const mode = ref('split')
/** 本地内容副本 */
const localContent = ref(props.modelValue)
/** 编辑区textarea引用 */
const textareaRef = ref(null)
/** 分屏模式textarea引用 */
const splitTextareaRef = ref(null)
/** 预览容器引用 */
const previewRef = ref(null)
const splitPreviewRef = ref(null)

const BACKEND_PORT = 18030

/**
 * 判断是否在Electron环境中
 */
const isElectron = typeof window !== 'undefined' && window.navigator.userAgent.includes('Electron')

/**
 * 配置marked v18：使用marked.use()替代已废弃的setOptions
 * - 自定义image渲染器：Electron环境下将/api/路径补全为完整URL
 * - 自定义code渲染器：使用highlight.js实现语法高亮（替代已移除的highlight选项）
 */
marked.use({
  breaks: true,
  gfm: true,
  renderer: {
    image({ href, title, text }) {
      let url = href || ''
      if (isElectron && url.startsWith('/api/')) {
        url = 'http://localhost:' + BACKEND_PORT + url
      }
      const titleAttr = title ? ` title="${title}"` : ''
      return `<img src="${url}" alt="${text || ''}"${titleAttr}>`
    },
    code({ text, lang }) {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return `<pre><code class="hljs language-${lang}">${hljs.highlight(text, { language: lang }).value}</code></pre>`
        } catch { /* ignore */ }
      }
      try {
        return `<pre><code class="hljs">${hljs.highlightAuto(text).value}</code></pre>`
      } catch {
        return `<pre><code>${text}</code></pre>`
      }
    }
  }
})

/**
 * 渲染HTML（含region锚点），Electron环境下修复图片路径
 */
const renderedHtml = computed(() => {
  if (!localContent.value) return '<p style="color:#999">暂无内容</p>'
  try {
    let html = marked.parse(localContent.value)
    // Electron环境下，HTML中的<img src="/api/...">需要补全为完整URL
    if (isElectron) {
      html = html.replace(/(<img\s[^>]*src=["'])(\/api\/)/g, '$1http://localhost:' + BACKEND_PORT + '$2')
    }
    return html
  } catch (err) {
    console.error('Markdown渲染出错:', err)
    return '<p style="color:red">Markdown渲染出错</p>'
  }
})

/**
 * 字符数
 */
const charCount = computed(() => localContent.value?.length || 0)

/**
 * 行数
 */
const lineCount = computed(() => {
  if (!localContent.value) return 0
  return localContent.value.split('\n').length
})

/**
 * 监听外部modelValue变化
 */
watch(() => props.modelValue, (val) => {
  localContent.value = val
})

/**
 * 监听region高亮变化：在编辑器和预览中定位
 * regionId < 0 时清除高亮
 */
watch(() => props.highlightRegionId, async (regionId) => {
  if (regionId < 0) {
    // 清除之前的高亮
    const previewContainer = previewRef.value || splitPreviewRef.value
    if (previewContainer) {
      const prevHighlight = previewContainer.querySelector('.rg-highlight-block')
      if (prevHighlight) {
        prevHighlight.classList.remove('rg-highlight-block')
      }
    }
    const textarea = textareaRef.value || splitTextareaRef.value
    if (textarea) {
      textarea.classList.remove('region-flash')
    }
    return
  }

  await nextTick()

  const region = props.regions.find(r => r.id === regionId)
  if (!region) return

  // 1. 在textarea中定位并选中
  const textarea = textareaRef.value || splitTextareaRef.value
  if (textarea) {
    highlightInTextarea(textarea, region)
  }

  // 2. 在预览DOM中搜索region文本并滚动
  await nextTick()
  const previewContainer = previewRef.value || splitPreviewRef.value
  if (previewContainer) {
    scrollToRegionInPreview(previewContainer, region)
  }
})

/**
 * 在预览DOM中搜索region的contentPreview文本并滚动
 * 使用TreeWalker遍历文本节点，不修改HTML字符串
 */
function scrollToRegionInPreview(container, region) {
  // 先移除之前的高亮
  const prevHighlight = container.querySelector('.rg-highlight-block')
  if (prevHighlight) {
    prevHighlight.classList.remove('rg-highlight-block')
  }

  const preview = String(region.contentPreview || '').replace(/\s+/g, ' ').trim()
  if (!preview || preview.length < 2) {
    // fallback: 按region顺序比例滚动
    const blocks = container.querySelectorAll('.markdown-body > *')
    if (blocks.length > 0) {
      const idx = Math.min(
        Math.floor((region.order / Math.max(props.regions.length, 1)) * blocks.length),
        blocks.length - 1
      )
      const block = blocks[idx]
      block.classList.add('rg-highlight-block')
      block.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setTimeout(() => block.classList.remove('rg-highlight-block'), 2000)
    }
    return
  }

  // 用TreeWalker搜索文本节点
  const walker = document.createTreeWalker(
    container.querySelector('.markdown-body') || container,
    NodeFilter.SHOW_TEXT,
    null
  )

  const searchWords = preview.split(/\s+/).filter(w => w.length > 1).slice(0, 3)
  let bestNode = null
  let bestScore = 0

  while (walker.nextNode()) {
    const text = walker.currentNode.textContent || ''
    if (text.trim().length < 2) continue
    // 计算匹配分数：searchWords中有多少在文本中出现
    const lowerText = text.toLowerCase()
    const score = searchWords.filter(w => lowerText.includes(w.toLowerCase())).length
    if (score > bestScore) {
      bestScore = score
      bestNode = walker.currentNode
    }
  }

  if (bestNode && bestScore > 0) {
    // 找到最近的块级父元素
    let blockEl = bestNode.parentElement
    while (blockEl && blockEl !== container) {
      const display = getComputedStyle(blockEl).display
      if (display === 'block' || display === 'list-item' || display === 'table-row' || display === 'table-cell') {
        break
      }
      blockEl = blockEl.parentElement
    }
    if (blockEl && blockEl !== container) {
      blockEl.classList.add('rg-highlight-block')
      blockEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setTimeout(() => blockEl.classList.remove('rg-highlight-block'), 2000)
    }
  }
}

/**
 * 在textarea中找到region对应的文本并选中
 */
function highlightInTextarea(textarea, region) {
  const text = localContent.value
  if (!text) return

  const preview = String(region.contentPreview || '').replace(/\s+/g, ' ').trim()
  if (!preview || preview.length < 2) {
    // fallback: 按比例滚动
    const lines = text.split('\n')
    const approxLine = Math.min(
      Math.floor((region.order / Math.max(props.regions.length, 1)) * lines.length),
      lines.length - 3
    )
    textarea.scrollTop = Math.max(0, approxLine * 22)
    return
  }

  // 在markdown中搜索contentPreview
  // 先尝试精确匹配
  let idx = text.indexOf(preview)
  if (idx === -1) {
    // 尝试忽略空格的匹配
    const previewNoSpace = preview.replace(/\s+/g, '')
    const textNoSpace = text.replace(/\s+/g, '')
    idx = textNoSpace.indexOf(previewNoSpace)
    if (idx >= 0) {
      // 映射回原始位置（近似）
      idx = Math.floor(idx * text.length / Math.max(textNoSpace.length, 1))
    }
  }

  if (idx >= 0) {
    // 选中目标文本
    const endIdx = idx + preview.length
    textarea.focus()
    textarea.setSelectionRange(idx, Math.min(endIdx, text.length))

    // 计算行号并滚动
    const beforeText = text.substring(0, idx)
    const lineNum = beforeText.split('\n').length
    textarea.scrollTop = Math.max(0, (lineNum - 3) * 22)

    // 视觉闪烁（通过临时CSS类）
    textarea.classList.add('region-flash')
    setTimeout(() => textarea.classList.remove('region-flash'), 800)
  }
}

/**
 * 输入事件
 */
function onInput(e) {
  localContent.value = e.target.value
  emit('update:modelValue', localContent.value)
}

/**
 * 键盘事件
 */
function onKeyDown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    emit('save', localContent.value)
  }
  if (e.key === 'Tab') {
    e.preventDefault()
    const ta = e.target
    const start = ta.selectionStart
    const end = ta.selectionEnd
    localContent.value = ta.value.substring(0, start) + '  ' + ta.value.substring(end)
    ta.selectionStart = ta.selectionEnd = start + 2
    emit('update:modelValue', localContent.value)
  }
}
</script>

<style scoped>
.md-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1e1e1e;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: #2d2d2d;
  border-bottom: 1px solid #3e3e3e;
  flex-shrink: 0;
}

.toolbar-info {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
}

.editor-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.full-pane {
  width: 100%;
  height: 100%;
}

.split-pane {
  width: 50%;
  height: 100%;
}

.editor-pane {
  display: flex;
  overflow: hidden;
}

.editor-textarea {
  width: 100%;
  height: 100%;
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: #d4d4d4;
  background: #1e1e1e;
  border: none;
  outline: none;
  resize: none;
  tab-size: 2;
  transition: background 0.3s;
}

.editor-textarea::placeholder {
  color: rgba(255, 255, 255, 0.25);
}

/* 区域闪烁高亮 */
.editor-textarea.region-flash {
  background: #2a3f5f;
}

.split-divider {
  width: 1px;
  background: #3e3e3e;
  flex-shrink: 0;
}

.preview-pane {
  overflow: auto;
  background: #fff;
}

.markdown-body {
  padding: 20px 24px;
  font-size: 14px;
  line-height: 1.8;
  color: rgba(0, 0, 0, 0.85);
}

/* 区域高亮块（hover region时，对应块添加背景） */
.markdown-body :deep(.rg-highlight-block) {
  background: #fff8e1;
  border-left: 3px solid #ffab00;
  padding-left: 8px;
  transition: background 0.3s, border-color 0.3s;
}

.markdown-body :deep(h1) {
  font-size: 28px;
  font-weight: 600;
  margin: 24px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e8e8e8;
}

.markdown-body :deep(h2) {
  font-size: 24px;
  font-weight: 600;
  margin: 20px 0 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0f0;
}

.markdown-body :deep(h3) {
  font-size: 20px;
  font-weight: 600;
  margin: 16px 0 10px;
}

.markdown-body :deep(h4) {
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0 8px;
}

.markdown-body :deep(p) {
  margin: 8px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 16px;
  border-left: 4px solid #1890ff;
  background: #f6f8fa;
  color: rgba(0, 0, 0, 0.65);
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  font-size: 13px;
  background: #f5f5f5;
  border-radius: 3px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

.markdown-body :deep(pre) {
  margin: 12px 0;
  padding: 16px;
  background: #f6f8fa;
  border-radius: 6px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  font-size: 13px;
  line-height: 1.6;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #d9d9d9;
  padding: 8px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #fafafa;
  font-weight: 600;
}

.markdown-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
}

.markdown-body :deep(a) {
  color: #1890ff;
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid #e8e8e8;
  margin: 16px 0;
}

/* Ant Design 深色主题覆盖 */
.editor-toolbar :deep(.ant-radio-group) {
  background: transparent;
}

.editor-toolbar :deep(.ant-radio-button-wrapper) {
  background: #3e3e3e;
  border-color: #4e4e4e;
  color: rgba(255, 255, 255, 0.65);
  font-size: 12px;
}

.editor-toolbar :deep(.ant-radio-button-wrapper:first-child) {
  border-left-color: #4e4e4e;
}

.editor-toolbar :deep(.ant-radio-button-wrapper:not(:first-child)::before) {
  background-color: #4e4e4e;
}

.editor-toolbar :deep(.ant-radio-button-wrapper:hover) {
  color: #fff;
}

.editor-toolbar :deep(.ant-radio-button-wrapper-checked) {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}

.editor-toolbar :deep(.ant-radio-button-wrapper-checked:hover) {
  color: #fff;
}
</style>
