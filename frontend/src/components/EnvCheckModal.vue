<template>
  <a-modal
    v-model:open="visible"
    title="环境检测"
    :footer="null"
    :width="560"
    centered
    @cancel="visible = false"
  >
    <div class="env-check-content">
      <!-- 检测中 -->
      <div v-if="loading" class="env-check-loading">
        <a-spin size="large" />
        <p style="margin-top: 12px; color: rgba(0,0,0,0.45)">正在检测环境依赖...</p>
      </div>

      <!-- 检测结果 -->
      <div v-else-if="engines.length > 0">
        <!-- 统计摘要 -->
        <div class="env-check-summary">
          <a-tag color="success">{{ availableCount }} 个可用</a-tag>
          <a-tag color="error">{{ unavailableCount }} 个不可用</a-tag>
        </div>

        <!-- 引擎列表 -->
        <div class="env-check-list">
          <div
            v-for="engine in engines"
            :key="engine.type"
            class="env-check-item"
            :class="{ 'env-check-item-ok': engine.available, 'env-check-item-fail': !engine.available }"
          >
            <div class="env-check-item-header">
              <span class="env-check-status-icon">
                <CheckCircleFilled v-if="engine.available" style="color: #52c41a; font-size: 18px" />
                <CloseCircleFilled v-else style="color: #ff4d4f; font-size: 18px" />
              </span>
              <span class="env-check-name">{{ engine.name }}</span>
              <a-tag v-if="engine.requires_gpu" color="orange" style="margin-left: 8px; font-size: 11px">需GPU</a-tag>
              <a-tag v-else color="blue" style="margin-left: 8px; font-size: 11px">CPU</a-tag>
            </div>
            <div class="env-check-desc">{{ engine.description }}</div>
            <div v-if="!engine.available" class="env-check-reason">
              <WarningOutlined style="color: #faad14; margin-right: 4px" />
              {{ engine.reason }}
            </div>
            <div class="env-check-deps">
              <span class="env-check-deps-label">依赖:</span>
              <a-tag v-for="dep in engine.dependencies" :key="dep" :color="getDepColor(engine, dep)" style="font-size: 11px; margin: 2px">
                {{ dep }}
              </a-tag>
            </div>
          </div>
        </div>

        <!-- 重新检测按钮 -->
        <div style="text-align: center; margin-top: 16px">
          <a-button type="primary" ghost @click="runCheck" :loading="loading">
            重新检测
          </a-button>
        </div>
      </div>

      <!-- 检测失败 -->
      <div v-else-if="error" class="env-check-error">
        <CloseCircleFilled style="font-size: 32px; color: #ff4d4f" />
        <p style="margin-top: 8px">{{ error }}</p>
        <a-button type="primary" @click="runCheck">重试</a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { CheckCircleFilled, CloseCircleFilled, WarningOutlined } from '@ant-design/icons-vue'
import * as api from '../api/index.js'

const visible = defineModel('open', { type: Boolean, default: false })

/** 检测结果 */
const engines = ref([])

/** 加载状态 */
const loading = ref(false)

/** 错误信息 */
const error = ref('')

/** 可用引擎数量 */
const availableCount = computed(() => engines.value.filter(e => e.available).length)

/** 不可用引擎数量 */
const unavailableCount = computed(() => engines.value.filter(e => !e.available).length)

/**
 * 运行环境检测
 */
async function runCheck() {
  loading.value = true
  error.value = ''
  engines.value = []

  try {
    const res = await api.checkEngines()
    engines.value = res.engines || []
  } catch (err) {
    error.value = '检测失败: ' + (err.message || '未知错误')
  } finally {
    loading.value = false
  }
}

/**
 * 获取依赖标签颜色
 * @param {Object} engine - 引擎对象
 * @param {string} dep - 依赖名称
 * @returns {string} 标签颜色
 */
function getDepColor(engine, dep) {
  if (engine.available) return 'green'
  // 不可用时，根据依赖类型判断
  if (dep.includes('GPU') || dep.includes('CUDA')) return 'red'
  if (dep.includes('API Key') || dep.includes('vision') || dep.includes('Tesseract')) return 'orange'
  return 'default'
}

/** 弹窗打开时自动检测 */
watch(visible, (val) => {
  if (val && engines.value.length === 0) {
    runCheck()
  }
})
</script>

<style scoped>
.env-check-content {
  padding: 4px 0;
}

.env-check-loading {
  text-align: center;
  padding: 40px 0;
}

.env-check-summary {
  margin-bottom: 16px;
  display: flex;
  gap: 8px;
}

.env-check-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.env-check-item {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  transition: all 0.2s;
}

.env-check-item-ok {
  background: #f6ffed;
  border-color: #b7eb8f;
}

.env-check-item-fail {
  background: #fff2f0;
  border-color: #ffccc7;
}

.env-check-item-header {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}

.env-check-status-icon {
  margin-right: 8px;
  display: flex;
  align-items: center;
}

.env-check-name {
  font-weight: 600;
  font-size: 14px;
}

.env-check-desc {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
  margin-left: 26px;
  margin-bottom: 4px;
}

.env-check-reason {
  color: #cf1322;
  font-size: 12px;
  margin-left: 26px;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
}

.env-check-deps {
  margin-left: 26px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.env-check-deps-label {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.45);
  margin-right: 4px;
}

.env-check-error {
  text-align: center;
  padding: 40px 0;
}
</style>
