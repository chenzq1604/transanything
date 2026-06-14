<template>
  <div class="pdf-viewer" ref="viewerRef">
    <div v-if="loading" class="viewer-loading">
      <a-spin tip="加载PDF中..." />
    </div>
    <div v-if="error" class="viewer-error">
      <a-result status="error" title="PDF加载失败" :sub-title="error">
        <template #extra>
          <a-button type="primary" @click="retry">重试</a-button>
        </template>
      </a-result>
    </div>
    <div v-show="!loading && !error" class="pdf-canvas-container" ref="containerRef">
      <div
        v-for="(page, pi) in pageCanvases"
        :key="pi"
        class="pdf-page-wrapper"
        :style="{ position: 'relative' }"
      >
        <canvas :ref="el => setCanvasRef(pi, el)" class="pdf-page-canvas" />
        <!-- Region遮罩层 -->
        <div
          v-if="pageRegions(pi).length"
          class="region-overlay"
          :style="{
            width: pageSizes[pi]?.cssW + 'px',
            height: pageSizes[pi]?.cssH + 'px',
          }"
        >
          <div
            v-for="r in pageRegions(pi)"
            :key="r.id"
            class="region-hitbox"
            :class="{ 'region-hovered': activeRegion === r.id }"
            :style="regionStyle(r, pi)"
            :title="r.type + (r.contentPreview ? ': ' + r.contentPreview : '')"
            @mouseenter="onRegionEnter(r.id)"
            @mouseleave="onRegionLeave"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// 设置PDF.js worker - 使用本地打包的worker文件，版本与pdfjs-dist一致
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

const props = defineProps({
  fileUrl: { type: String, required: true },
  regions: { type: Array, default: () => [] },
})

const emit = defineEmits(['hover-region'])

/** 加载状态 */
const loading = ref(true)
const error = ref('')

/** 页面画布引用 */
const pageCanvases = ref([])
const pageSizes = ref([])
const canvasRefs = {}
const containerRef = ref(null)
const viewerRef = ref(null)

/** 活跃区域 */
const activeRegion = ref(-1)

/** PDF文档对象 */
let pdfDoc = null
let renderTasks = []

/** 引擎渲染缩放因子 (200/72) */
const ENGINE_ZOOM = 200 / 72

/**
 * 设置canvas引用
 */
function setCanvasRef(pi, el) {
  if (el) canvasRefs[pi] = el
}

/**
 * 获取某页的区域
 */
function pageRegions(pi) {
  return props.regions.filter(r => r.page === pi)
}

/**
 * 计算区域的CSS样式
 * bbox来自引擎渲染图片坐标(ENGINE_ZOOM)，需要映射到canvas的CSS显示坐标
 * 缩放比 = canvas的CSS显示宽度 / 引擎图片宽度
 * 引擎图片宽度 = PDF原始宽度(72dpi) * ENGINE_ZOOM
 */
function regionStyle(region, pi) {
  const size = pageSizes.value[pi]
  if (!size || !size.cssW) return { display: 'none' }
  // cssW是canvas实际CSS显示宽度，engineW是引擎渲染的图片像素宽度
  // 缩放比 = CSS显示宽度 / 引擎图片宽度
  const s = size.cssW / size.engineW
  const b = region.bbox
  return {
    left: (b[0] * s) + 'px',
    top: (b[1] * s) + 'px',
    width: ((b[2] - b[0]) * s) + 'px',
    height: ((b[3] - b[1]) * s) + 'px',
  }
}

/**
 * 区域进入事件
 */
function onRegionEnter(regionId) {
  activeRegion.value = regionId
  emit('hover-region', regionId)
}

/**
 * 区域离开事件
 */
function onRegionLeave() {
  activeRegion.value = -1
  emit('hover-region', -1)
}

/**
 * 加载并渲染PDF
 */
async function loadPdf(url) {
  loading.value = true
  error.value = ''
  activeRegion.value = -1

  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const arrayBuffer = await response.arrayBuffer()

    pdfDoc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise
    const numPages = pdfDoc.numPages

    pageCanvases.value = Array.from({ length: numPages }, (_, i) => i)
    pageSizes.value = Array.from({ length: numPages }, () => ({ cssW: 0, cssH: 0, engineW: 0 }))

    // 先关闭loading让容器可见，才能获取正确的clientWidth
    loading.value = false
    await nextTick()
    await renderAllPages(numPages)
  } catch (err) {
    error.value = err.message || 'PDF加载失败'
    loading.value = false
  }
}

/**
 * 渲染所有页面
 * 关键：让canvas的像素尺寸 = CSS显示尺寸（1:1），避免CSS缩放导致region偏移
 */
async function renderAllPages(numPages) {
  // 获取容器宽度，确保容器可见后再取值
  let containerWidth = containerRef.value?.clientWidth || 0
  // 如果容器宽度为0（还没渲染），使用viewerRef的宽度或默认值
  if (containerWidth <= 0) {
    containerWidth = viewerRef.value?.clientWidth || 612
  }
  // 留一点padding空间
  const displayWidth = containerWidth - 16

  for (let pi = 0; pi < numPages; pi++) {
    const page = await pdfDoc.getPage(pi + 1)
    const viewport = page.getViewport({ scale: 1 })

    // 计算让canvas刚好fit容器宽度的scale
    const scale = displayWidth / viewport.width
    const scaledViewport = page.getViewport({ scale })

    // canvas像素尺寸 = CSS显示尺寸（1:1映射，不做CSS缩放）
    const cssW = Math.round(scaledViewport.width)
    const cssH = Math.round(scaledViewport.height)

    // 引擎渲染图片的像素宽度（用于bbox坐标映射）
    const engineW = viewport.width * ENGINE_ZOOM

    pageSizes.value[pi] = { cssW, cssH, engineW }

    const canvas = canvasRefs[pi]
    if (!canvas) continue
    // canvas属性尺寸 = CSS显示尺寸，确保1:1无缩放
    canvas.width = cssW
    canvas.height = cssH
    canvas.style.width = cssW + 'px'
    canvas.style.height = cssH + 'px'

    const ctx = canvas.getContext('2d')
    const task = page.render({ canvasContext: ctx, viewport: scaledViewport })
    renderTasks.push(task)
    await task.promise
  }
}

/**
 * 重试加载
 */
function retry() {
  loadPdf(props.fileUrl)
}

/**
 * 清理渲染任务
 */
function clearRender() {
  renderTasks.forEach(t => {
    try { t.cancel() } catch { /* ignore */ }
  })
  renderTasks = []
}

/** 监听URL变化 */
watch(() => props.fileUrl, (url) => {
  if (url) {
    clearRender()
    loadPdf(url)
  }
}, { immediate: true })

/** 窗口resize时重新渲染 */
let resizeTimer = null
function onResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (pdfDoc) {
      clearRender()
      renderAllPages(pdfDoc.numPages)
    }
  }, 300)
}

onMounted(() => {
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  clearRender()
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})
</script>

<style scoped>
.pdf-viewer {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
}

.pdf-canvas-container {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

.pdf-page-wrapper {
  margin-bottom: 14px;
  position: relative;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}

.pdf-page-canvas {
  display: block;
  /* 不使用max-width缩放，canvas像素尺寸=CSS尺寸，1:1映射 */
}

.region-overlay {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
}

.region-hitbox {
  position: absolute;
  cursor: pointer;
  pointer-events: auto;
  transition: background 0.15s;
  border-radius: 2px;
}

.region-hitbox:hover,
.region-hovered {
  background: rgba(24, 144, 255, 0.25);
  outline: 2px solid rgba(24, 144, 255, 0.7);
  outline-offset: 0;
  z-index: 2;
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
</style>
