<template>
  <div class="file-list-wrapper">
    <!-- 搜索栏 -->
    <div class="file-list-search">
      <a-input-search
        v-model:value="searchText"
        placeholder="搜索文件名"
        size="small"
        allow-clear
      />
    </div>

    <!-- 文件表格 -->
    <a-table
      :columns="columns"
      :data-source="filteredFiles"
      :loading="loading && files.length > 0"
      :pagination="false"
      :scroll="{ y: tableScrollY }"
      row-key="id"
      size="small"
      class="file-table"
      :row-class-name="(record) => record.id === props.activeFileId ? 'active-row' : ''"
    >
      <!-- 文件名列 -->
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'filename'">
          <div class="filename-cell" @click="handleView(record)">
            <FileTextOutlined class="file-icon" />
            <div class="filename-info">
              <span class="filename-text" :title="record.filename">
                {{ record.filename }}
              </span>
              <span class="filename-meta">
                {{ record.file_type?.toUpperCase()?.replace('.', '') }} · {{ formatSize(record.file_size) }}
              </span>
            </div>
            <EyeOutlined v-if="record.id === props.activeFileId" class="active-indicator" />
          </div>
        </template>

        <!-- 状态列 -->
        <template v-else-if="column.key === 'status'">
          <a-tag :color="getStatusColor(record.status)" size="small">
            {{ getStatusText(record.status) }}
          </a-tag>
        </template>

        <!-- 操作列 -->
        <template v-else-if="column.key === 'action'">
          <a-space size="small">
            <a-tooltip title="删除">
              <a-popconfirm
                title="确定删除此文件？"
                @confirm="handleDelete(record)"
                ok-text="确定"
                cancel-text="取消"
              >
                <a-button type="link" size="small" danger>
                  <DeleteOutlined />
                </a-button>
              </a-popconfirm>
            </a-tooltip>
          </a-space>
        </template>
      </template>
    </a-table>

    <!-- 转换日志区域 -->
    <div v-if="logs.length > 0" class="log-panel" :style="{ height: logHeight + 'px' }">
      <!-- 拖拽调整高度的把手 -->
      <div class="log-resize-handle" @mousedown="onLogResizeStart"></div>
      <div class="log-header">
        <span class="log-title">转换日志</span>
        <a-button type="text" size="small" @click="clearLogs">
          <ClearOutlined />
        </a-button>
      </div>
      <div ref="logContainerRef" class="log-content">
        <div
          v-for="(log, index) in logs"
          :key="index"
          :class="['log-line', `log-${log.type}`]"
        >
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import {
  FileTextOutlined,
  DeleteOutlined,
  ClearOutlined,
} from '@ant-design/icons-vue'
import * as api from '../api/index.js'

const emit = defineEmits(['view'])

/** 当前打开的文件ID */
const props = defineProps({
  activeFileId: { type: String, default: '' },
})

/** 文件列表数据 */
const files = ref([])

/** 加载状态 */
const loading = ref(false)

/** 搜索关键词 */
const searchText = ref('')

/** 转换日志 */
const logs = ref([])

/** 日志容器引用 */
const logContainerRef = ref(null)

/** 日志面板高度 */
const logHeight = ref(180)

/** 表格滚动高度（根据日志面板高度动态计算） */
const tableScrollY = computed(() => {
  if (logs.value.length > 0) {
    return `calc(100vh - ${200 + logHeight.value}px)`
  }
  return 'calc(100vh - 200px)'
})

/** 表格列定义 */
const columns = [
  { title: '文件名', dataIndex: 'filename', key: 'filename', ellipsis: true },
  { title: '状态', dataIndex: 'status', key: 'status', width: 80, align: 'center' },
  { title: '操作', key: 'action', width: 60, align: 'center' },
]

/**
 * 根据搜索关键词过滤文件
 */
const filteredFiles = computed(() => {
  if (!searchText.value) return files.value
  const keyword = searchText.value.toLowerCase()
  return files.value.filter((f) =>
    f.filename?.toLowerCase().includes(keyword)
  )
})

/**
 * 添加日志
 * @param {string} msg - 日志消息
 * @param {string} type - 日志类型 info/warn/error
 */
function addLog(msg, type = 'info') {
  const now = new Date()
  const time = now.toLocaleTimeString('zh-CN', { hour12: false })
  logs.value.push({ time, message: msg, type })
  // 最多保留200条
  if (logs.value.length > 200) {
    logs.value = logs.value.slice(-200)
  }
  // 自动滚动到底部
  nextTick(() => {
    if (logContainerRef.value) {
      logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
    }
  })
}

/**
 * 清空日志
 */
function clearLogs() {
  logs.value = []
}

/**
 * 日志面板拖拽调整高度开始
 * @param {MouseEvent} e - 鼠标事件
 */
function onLogResizeStart(e) {
  e.preventDefault()
  const startY = e.clientY
  const startHeight = logHeight.value

  const onMouseMove = (moveEvent) => {
    // 向上拖增大，向下拖缩小
    const delta = startY - moveEvent.clientY
    const newHeight = Math.min(500, Math.max(80, startHeight + delta))
    logHeight.value = newHeight
  }

  const onMouseUp = () => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

/**
 * 刷新文件列表
 */
async function refresh() {
  loading.value = true
  try {
    files.value = await api.getFileList()
  } catch (err) {
    message.error('获取文件列表失败')
  } finally {
    loading.value = false
  }
}

/**
 * 查看文件
 * @param {Object} record - 文件记录
 */
function handleView(record) {
  emit('view', record)
}

/**
 * 删除文件
 * @param {Object} record - 文件记录
 */
async function handleDelete(record) {
  try {
    await api.deleteFile(record.id)
    message.success('删除成功')
    await refresh()
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的字符串
 */
function formatSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

/**
 * 获取状态标签颜色
 * @param {string} status - 文件状态
 * @returns {string} 颜色值
 */
function getStatusColor(status) {
  const map = { uploaded: 'default', converting: 'processing', completed: 'success', failed: 'error' }
  return map[status] || 'default'
}

/**
 * 获取状态显示文本
 * @param {string} status - 文件状态
 * @returns {string} 中文文本
 */
function getStatusText(status) {
  const map = { uploaded: '已上传', converting: '转换中', completed: '已完成', failed: '转换失败' }
  return map[status] || status
}

/** 暴露refresh和addLog方法给父组件 */
defineExpose({ refresh, addLog })

onMounted(() => {
  refresh()
})
</script>

<style scoped>
.file-list-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.file-list-search {
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
}

.file-table {
  flex: 1;
  min-height: 0;
}

/* 表格滚动条与内容间距 */
.file-table :deep(.ant-table-body) {
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.15) transparent;
}

.file-table :deep(.ant-table-body::-webkit-scrollbar) {
  width: 6px;
}

.file-table :deep(.ant-table-body::-webkit-scrollbar-thumb) {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}

.file-table :deep(.ant-table-row:last-child td) {
  padding-bottom: 16px;
}

.filename-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #1890ff;
}

.filename-cell:hover .filename-text {
  text-decoration: underline;
}

.file-icon {
  font-size: 16px;
  color: rgba(0, 0, 0, 0.45);
  flex-shrink: 0;
}

.filename-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.filename-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 1.4;
}

.filename-meta {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
  line-height: 1.3;
}

/* 当前打开的文件行高亮 */
:deep(.active-row) {
  background-color: #e6f7ff !important;
}

:deep(.active-row:hover > td) {
  background-color: #bae7ff !important;
}

.active-indicator {
  color: #1890ff;
  font-size: 14px;
  flex-shrink: 0;
  margin-left: auto;
}

/* 日志面板 */
.log-panel {
  border-top: 1px solid #d9d9d9;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: relative;
}

.log-resize-handle {
  position: absolute;
  top: -3px;
  left: 0;
  right: 0;
  height: 6px;
  cursor: ns-resize;
  z-index: 10;
}

.log-resize-handle:hover {
  background: #1890ff;
  opacity: 0.3;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
}

.log-title {
  font-size: 12px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.65);
}

.log-content {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.6;
  background: #1e1e1e;
  color: #d4d4d4;
}

.log-line {
  display: flex;
  gap: 8px;
  padding: 1px 4px;
  border-radius: 2px;
}

.log-line:hover {
  background: rgba(255, 255, 255, 0.05);
}

.log-time {
  color: #6a9955;
  flex-shrink: 0;
}

.log-info .log-msg {
  color: #d4d4d4;
}

.log-warn .log-msg {
  color: #dcdcaa;
}

.log-error .log-msg {
  color: #f44747;
}
</style>
