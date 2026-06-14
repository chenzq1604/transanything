<template>
  <div class="xls-viewer">
    <div v-if="loading" class="viewer-loading">
      <a-spin tip="加载Excel数据中..." />
    </div>
    <div v-else-if="error" class="viewer-error">
      <a-result status="error" title="Excel加载失败" :sub-title="error">
        <template #extra>
          <a-button type="primary" @click="loadExcel">重试</a-button>
        </template>
      </a-result>
    </div>
    <div v-else class="xls-content">
      <!-- 工作表标签 -->
      <div v-if="sheetNames.length > 1" class="sheet-tabs">
        <a-radio-group v-model:value="activeSheet" size="small" button-style="solid">
          <a-radio-button v-for="name in sheetNames" :key="name" :value="name">
            {{ name }}
          </a-radio-button>
        </a-radio-group>
      </div>
      <!-- 数据表格 -->
      <div class="table-wrapper">
        <a-table
          :columns="currentColumns"
          :data-source="currentData"
          :pagination="{ pageSize: 50, size: 'small', showSizeChanger: true, pageSizeOptions: ['20', '50', '100'] }"
          :scroll="{ x: 'max-content', y: 'calc(100vh - 280px)' }"
          size="small"
          bordered
          class="xls-table"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import * as api from '../api/index.js'

const props = defineProps({
  /** Excel文件预览URL */
  fileUrl: { type: String, required: true },
  /** 文件ID，用于通过API获取数据 */
  fileId: { type: [String, Number], required: true },
})

/** 加载状态 */
const loading = ref(true)

/** 错误信息 */
const error = ref('')

/** 工作表名称列表 */
const sheetNames = ref([])

/** 当前选中的工作表 */
const activeSheet = ref('')

/** 各工作表数据 { sheetName: { columns, data } } */
const sheetsData = ref({})

/**
 * 当前工作表的列定义
 */
const currentColumns = computed(() => {
  if (!activeSheet.value) return []
  return sheetsData.value[activeSheet.value]?.columns || []
})

/**
 * 当前工作表的数据
 */
const currentData = computed(() => {
  if (!activeSheet.value) return []
  return sheetsData.value[activeSheet.value]?.data || []
})

/**
 * 加载Excel数据
 * 通过后端API获取结构化数据
 */
async function loadExcel() {
  loading.value = true
  error.value = ''

  try {
    const result = await api.getExcelData(props.fileId)

    // 解析后端返回的数据结构
    // 期望格式: { sheets: { sheetName: { headers: [], rows: [[]] } } }
    if (result.sheets) {
      const parsed = {}
      const names = []

      for (const [name, sheet] of Object.entries(result.sheets)) {
        names.push(name)
        const columns = (sheet.headers || []).map((h, i) => ({
          title: h || `列${i + 1}`,
          dataIndex: `col_${i}`,
          key: `col_${i}`,
          width: 120,
          ellipsis: true,
        }))

        const data = (sheet.rows || []).map((row, idx) => {
          const record = { key: idx }
          row.forEach((cell, i) => {
            record[`col_${i}`] = cell ?? ''
          })
          return record
        })

        parsed[name] = { columns, data }
      }

      sheetsData.value = parsed
      sheetNames.value = names
      activeSheet.value = names[0] || ''
    }
  } catch (err) {
    error.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

/** 监听fileId变化重新加载 */
watch(() => props.fileId, loadExcel)

onMounted(loadExcel)
</script>

<style scoped>
.xls-viewer {
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

.xls-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sheet-tabs {
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
  flex-shrink: 0;
  overflow-x: auto;
  white-space: nowrap;
}

.table-wrapper {
  flex: 1;
  overflow: auto;
  padding: 8px;
}

.xls-table :deep(.ant-table-cell) {
  font-size: 12px;
  padding: 4px 8px !important;
}
</style>
