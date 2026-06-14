<template>
  <div class="compare-view">
    <!-- 顶部工具栏 -->
    <div class="compare-toolbar">
      <div class="toolbar-left">
        <a-button type="text" size="small" @click="emit('back')">
          <ArrowLeftOutlined /> 返回列表
        </a-button>
        <a-divider type="vertical" />
        <a-tooltip :title="fileName" placement="bottom">
          <span class="toolbar-filename">{{ fileName }}</span>
        </a-tooltip>
        <a-tag :color="getTypeColor(normalizedType)" size="small">{{ normalizedType?.toUpperCase() }}</a-tag>
      </div>
      <div class="toolbar-right">
        <!-- 识别操作组 -->
        <a-select v-model:value="engineType" size="small" style="width: 200px">
          <a-select-option v-for="et in ALL_ENGINE_TYPES" :key="et" :value="et" :disabled="!engineAvailability[et]?.available">
            <a-tooltip v-if="!engineAvailability[et]?.available" :title="engineAvailability[et]?.reason || '不可用'" placement="right">
              <span style="color: rgba(0,0,0,0.25)">{{ ENGINE_NAMES[et] }} (不可用)</span>
            </a-tooltip>
            <span v-else>{{ ENGINE_NAMES[et] }}</span>
          </a-select-option>
        </a-select>
        <a-popover trigger="hover" placement="bottom">
          <template #content>
            <div class="llm-switch-tooltip">
              <div><b>LLM后处理优化</b></div>
              <div style="margin-top:4px">开启后，其他引擎识别完成的结果会再经过LLM优化格式和排版。</div>
              <div style="margin-top:6px">
                <span v-if="llmStatus.connection_ok" style="color:#52c41a">● 连接正常</span>
                <span v-else style="color:#ff4d4f">● 连接失败</span>
                <span v-if="llmStatus.supports_vision === true" style="margin-left:12px;color:#52c41a">● 图片识别可用</span>
                <span v-else-if="llmStatus.supports_vision === false" style="margin-left:12px;color:#faad14">● 图片识别不可用</span>
              </div>
              <div style="margin-top:4px;color:rgba(0,0,0,0.45);font-size:12px">
                当前模型: {{ llmStatus.model || '未配置' }}
              </div>
              <div style="margin-top:6px">
                <a style="font-size:12px" @click="$emit('openLLMConfig')">配置大模型...</a>
              </div>
            </div>
          </template>
          <a-switch v-model:checked="useLlmOptimize" size="small">
            <template #checkedChildren>LLM</template>
            <template #unCheckedChildren>LLM</template>
          </a-switch>
        </a-popover>
        <a-button type="primary" size="small" :loading="reconverting" @click="handleBatchReconvert">
          <ThunderboltOutlined /> 识别全部
        </a-button>
        <a-button size="small" :loading="reconverting" @click="handleReconvert">
          <ThunderboltOutlined /> 识别
        </a-button>
        <a-divider type="vertical" />
        <!-- 对比操作组 -->
        <a-button size="small" @click="showAddEngineModal">
          <PlusOutlined /> 添加引擎
        </a-button>
        <a-button size="small" @click="showMetricsModal">
          <BarChartOutlined /> 指标
        </a-button>
        <a-button size="small" :disabled="completedEngineCount < 2" @click="showDiffModal">
          <DiffOutlined /> 差异
        </a-button>
        <!-- 隐藏列恢复下拉 -->
        <a-dropdown v-if="hiddenColumnsInfo.length > 0" :trigger="['click']">
          <a-button size="small">
            <EyeInvisibleOutlined /> 显示列
          </a-button>
          <template #overlay>
            <a-menu>
              <a-menu-item v-for="col in hiddenColumnsInfo" :key="col.engineType" @click="showHiddenColumn(col.engineType)">
                <EyeOutlined /> {{ col.engineName }}
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
        <a-button v-if="leftPaneHidden" size="small" @click="toggleLeftPane">
          <EyeOutlined /> 原始文件
        </a-button>
      </div>
    </div>

    <!-- 转换进度条 -->
    <div v-if="progress.visible" class="progress-bar">
      <div class="progress-content">
        <div class="progress-detail">
          <a-progress :percent="progress.percentage" :status="progress.status === 'failed' ? 'exception' : progress.status === 'completed' ? 'success' : 'active'" size="small" />
          <div class="progress-message">
            <LoadingOutlined v-if="progress.status === 'converting'" spin />
            <CheckCircleOutlined v-else-if="progress.status === 'completed'" style="color: #52c41a" />
            <CloseCircleOutlined v-else-if="progress.status === 'failed'" style="color: #ff4d4f" />
            <span class="progress-text">{{ progress.message || '准备中...' }}</span>
          </div>
        </div>
        <!-- 多引擎独立进度 -->
        <div v-if="Object.keys(engineProgresses).length > 0" class="engine-progress-list">
          <div v-for="(prog, etype) in engineProgresses" :key="etype" class="engine-progress-item">
            <span class="engine-progress-name">{{ ENGINE_NAMES[etype] || etype }}</span>
            <a-progress
              :percent="prog.percentage"
              :status="prog.status === 'failed' ? 'exception' : prog.status === 'completed' ? 'success' : 'active'"
              size="small"
              style="flex: 1"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 分栏主体：整体水平滚动 -->
    <div class="compare-body" ref="splitContainer">
      <div class="compare-body-inner" :style="{ width: bodyInnerWidth + 'px' }">
        <!-- 左侧：原始文件预览（固定像素宽度） -->
        <template v-if="!leftPaneHidden">
          <div
            class="compare-pane left-pane"
            :style="{ width: leftPaneWidth + 'px' }"
          >
            <div class="pane-header">
              <FileOutlined /> 原始文件
              <a-tooltip title="隐藏原始文件" placement="bottom">
                <EyeInvisibleOutlined class="pane-hide-btn" @click="toggleLeftPane" />
              </a-tooltip>
            </div>
            <div class="pane-content">
              <PdfViewer
                v-if="normalizedType === 'pdf'"
                :fileUrl="previewUrl"
                :regions="activeRegions"
                @hover-region="onHoverRegion"
              />
              <DocxViewer v-else-if="normalizedType === 'docx' || normalizedType === 'doc'" :fileUrl="previewUrl" />
              <XlsViewer v-else-if="normalizedType === 'xls' || normalizedType === 'xlsx'" :fileUrl="previewUrl" :fileId="fileId" />
              <TxtViewer v-else :fileUrl="previewUrl" :fileId="fileId" />
            </div>
          </div>

          <!-- PDF分隔条 -->
          <div
            class="split-bar"
            @mousedown="onSplitMouseDown('pdf', $event)"
          >
            <div class="split-handle"></div>
          </div>
        </template>

        <!-- 右侧引擎列 -->
        <div class="engine-columns">
          <template v-for="(col, index) in visibleEngineColumns" :key="col.engineType">
            <!-- 引擎列 -->
            <div
              class="engine-column"
              :data-engine-type="col.engineType"
              :class="{ 'drag-over': dragState.targetEngineType === col.engineType, 'drag-source': dragState.sourceEngineType === col.engineType }"
              :style="{ width: col.width + 'px' }"
              @dragover="onEngineDragOver(col.engineType, $event)"
              @dragleave="onEngineDragLeave(col.engineType, $event)"
              @drop="onEngineDrop(col.engineType, $event)"
            >
              <!-- 引擎头部：拖拽手柄、名称、指标、隐藏/关闭按钮 -->
              <div
                class="engine-header"
                draggable="true"
                @dragstart="onEngineDragStart(col.engineType, $event)"
                @dragend="onEngineDragEnd"
              >
                <a-tooltip title="拖拽排序" placement="bottom">
                  <HolderOutlined class="engine-drag-handle" />
                </a-tooltip>
                <span class="engine-name">{{ col.engineName }}</span>
                <span v-if="col.status === 'completed' && col.duration > 0" class="engine-stats">
                  {{ col.duration.toFixed(1) }}s · {{ col.charCount }}字 · {{ col.lineCount }}行
                </span>
                <a-progress
                  v-if="col.status === 'converting'"
                  :percent="col.percentage || 0"
                  size="small"
                  style="flex: 1; margin: 0 8px;"
                />
                <span v-if="col.status === 'failed'" class="engine-error">
                  <CloseCircleOutlined style="color: #ff4d4f" /> 失败
                </span>
                <span v-if="col.status === 'pending'" class="engine-pending">
                  等待中
                </span>
                <a-tooltip title="隐藏此列" placement="bottom">
                  <EyeInvisibleOutlined class="engine-hide-btn" @click="toggleEngineColumn(col.engineType)" />
                </a-tooltip>
                <CloseOutlined
                  v-if="engineColumns.length > 1"
                  class="engine-close"
                  @click="removeEngine(col.engineType)"
                />
              </div>
              <!-- 引擎内容：MdEditor -->
              <div class="engine-content">
                <MdEditor
                  v-model="col.markdown"
                  :regions="col.regions"
                  :highlight-region-id="hoveredRegion.sourceEngine === col.engineType ? hoveredRegion.originalId : -1"
                  @save="(content) => handleEngineSave(col.engineType, content)"
                />
              </div>
              <!-- 引擎底部操作栏 -->
              <div class="engine-footer">
                <a-button size="small" @click="handleEngineSave(col.engineType, col.markdown)">
                  <SaveOutlined /> 保存
                </a-button>
                <a-button size="small" @click="handleEngineExport(col)">
                  <DownloadOutlined /> 导出
                </a-button>
                <a-button size="small" @click="handleEngineCopy(col.markdown)">
                  <CopyOutlined /> 复制
                </a-button>
              </div>
            </div>

            <!-- 列间分隔条 -->
            <div
              class="column-split-bar"
              @mousedown="onColumnSplitMouseDown(col.engineType, visibleEngineColumns[index + 1]?.engineType, $event)"
            >
              <div class="column-split-handle"></div>
            </div>
          </template>

          <!-- 添加引擎按钮 -->
          <div v-if="engineColumns.length < 6" class="add-engine-column" @click="showAddEngineModal">
            <PlusOutlined style="font-size: 24px; color: #999" />
            <span style="margin-top: 8px; color: #999">添加引擎</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加引擎弹窗 -->
    <a-modal
      v-model:open="addEngineModalVisible"
      title="添加引擎"
      @ok="handleAddEngine"
      ok-text="确定"
      cancel-text="取消"
    >
      <p style="margin-bottom: 12px; color: rgba(0,0,0,0.65);">选择要添加的引擎（可多选）：</p>
      <a-checkbox-group v-model:value="selectedEngines" style="width: 100%;">
        <div v-for="eng in availableEnginesToAdd" :key="eng.value" class="engine-checkbox-item">
          <a-tooltip v-if="!engineAvailability[eng.value]?.available" :title="engineAvailability[eng.value]?.reason || '不可用'" placement="right">
            <a-checkbox :value="eng.value" :disabled="true">
              <span class="engine-checkbox-name" style="color: rgba(0,0,0,0.25)">{{ eng.label }} (不可用)</span>
              <span class="engine-checkbox-desc">{{ eng.description }}</span>
            </a-checkbox>
          </a-tooltip>
          <a-checkbox v-else :value="eng.value">
            <span class="engine-checkbox-name">{{ eng.label }}</span>
            <span class="engine-checkbox-desc">{{ eng.description }}</span>
          </a-checkbox>
        </div>
      </a-checkbox-group>
      <div v-if="availableEnginesToAdd.length === 0" style="color: #999; text-align: center; padding: 16px;">
        所有引擎已添加
      </div>
    </a-modal>

    <!-- 指标对比弹窗 -->
    <a-modal
      v-model:open="metricsModalVisible"
      title="识别指标对比"
      :footer="null"
      width="800px"
    >
      <div v-if="completedEngineCount === 0" style="text-align: center; padding: 24px; color: #999;">
        暂无已完成的引擎结果
      </div>
      <a-table
        v-else
        :columns="metricsColumns"
        :data-source="metricsData"
        :pagination="false"
        size="small"
        bordered
        :row-class-name="(record) => record.isBest ? 'metrics-best-row' : ''"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'engineName'">
            <span style="font-weight: 600;">{{ record.engineName }}</span>
          </template>
          <template v-if="column.key === 'duration'">
            <span :style="{ color: record.isFastest ? '#52c41a' : '', fontWeight: record.isFastest ? '600' : '' }">
              {{ record.duration.toFixed(1) }}s
            </span>
          </template>
          <template v-if="column.key === 'charCount'">
            <span :style="{ color: record.isMostChars ? '#52c41a' : '', fontWeight: record.isMostChars ? '600' : '' }">
              {{ record.charCount.toLocaleString() }}
            </span>
          </template>
          <template v-if="column.key === 'lineCount'">
            <span :style="{ color: record.isMostLines ? '#52c41a' : '', fontWeight: record.isMostLines ? '600' : '' }">
              {{ record.lineCount.toLocaleString() }}
            </span>
          </template>
          <template v-if="column.key === 'speed'">
            {{ record.speed.toFixed(0) }} 字/秒
          </template>
        </template>
      </a-table>
    </a-modal>

    <!-- Diff对比弹窗 -->
    <a-modal
      v-model:open="diffModalVisible"
      title="差异对比"
      :footer="null"
      width="90%"
      style="top: 20px;"
      :bodyStyle="{ padding: '0', maxHeight: '80vh', overflow: 'auto' }"
    >
      <div class="diff-controls">
        <span class="diff-label">基准引擎：</span>
        <a-select v-model:value="diffBaseEngine" size="small" style="width: 180px;">
          <a-select-option v-for="col in completedEngineColumns" :key="col.engineType" :value="col.engineType">
            {{ col.engineName }}
          </a-select-option>
        </a-select>
        <span class="diff-label" style="margin-left: 16px;">对比引擎：</span>
        <a-select v-model:value="diffCompareEngine" size="small" style="width: 180px;">
          <a-select-option v-for="col in completedEngineColumns" :key="col.engineType" :value="col.engineType">
            {{ col.engineName }}
          </a-select-option>
        </a-select>
        <a-button size="small" type="link" @click="swapDiffEngines">
          <SwapOutlined /> 交换
        </a-button>
      </div>
      <div class="diff-stats" v-if="diffResult">
        <a-tag color="green">新增 {{ diffResult.addedLines }} 行</a-tag>
        <a-tag color="red">删除 {{ diffResult.removedLines }} 行</a-tag>
        <a-tag color="blue">修改 {{ diffResult.modifiedLines }} 行</a-tag>
        <a-tag>相同 {{ diffResult.unchangedLines }} 行</a-tag>
        <span class="diff-similarity">相似度: {{ diffResult.similarity }}%</span>
      </div>
      <div class="diff-content" v-if="diffResult">
        <div class="diff-pane diff-pane-left">
          <div class="diff-pane-header">{{ getEngineName(diffBaseEngine) }}</div>
          <div class="diff-lines">
            <div
              v-for="(line, idx) in diffResult.leftLines"
              :key="'l' + idx"
              :class="['diff-line', line.type === 'removed' ? 'diff-line-removed' : line.type === 'modified-old' ? 'diff-line-modified-old' : '']"
            >
              <span class="diff-line-num">{{ line.num }}</span>
              <span class="diff-line-prefix">{{ line.prefix }}</span>
              <span class="diff-line-text">{{ line.text }}</span>
            </div>
          </div>
        </div>
        <div class="diff-pane diff-pane-right">
          <div class="diff-pane-header">{{ getEngineName(diffCompareEngine) }}</div>
          <div class="diff-lines">
            <div
              v-for="(line, idx) in diffResult.rightLines"
              :key="'r' + idx"
              :class="['diff-line', line.type === 'added' ? 'diff-line-added' : line.type === 'modified-new' ? 'diff-line-modified-new' : '']"
            >
              <span class="diff-line-num">{{ line.num }}</span>
              <span class="diff-line-prefix">{{ line.prefix }}</span>
              <span class="diff-line-text">{{ line.text }}</span>
            </div>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  ThunderboltOutlined,
  SaveOutlined,
  DownloadOutlined,
  CopyOutlined,
  FileOutlined,
  EditOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  CloseOutlined,
  BarChartOutlined,
  DiffOutlined,
  SwapOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  HolderOutlined,
} from '@ant-design/icons-vue'
import PdfViewer from './PdfViewer.vue'
import DocxViewer from './DocxViewer.vue'
import XlsViewer from './XlsViewer.vue'
import TxtViewer from './TxtViewer.vue'
import MdEditor from './MdEditor.vue'
import * as api from '../api/index.js'

/** 引擎名称映射 */
const ENGINE_NAMES = {
  markitdown: 'MarkItDown',
  paddleocr: 'PaddleOCR v6',
  ppstructure: 'PP-StructureV3',
  ppchatocr: 'PP-ChatOCRv4',
  mineru: 'MinerU',
  llm: 'LLM图片识别',
}

/** 引擎描述映射 */
const ENGINE_DESCRIPTIONS = {
  markitdown: '微软开源库，支持广泛格式',
  paddleocr: '本地GPU OCR，适合扫描件和图片型PDF',
  ppstructure: '版面分析+表格识别+公式识别+印章识别',
  ppchatocr: 'OCR+版面分析+可选LLM关键信息提取',
  mineru: '端到端文档理解：版面分析+OCR+公式+表格+图片',
  llm: '渲染图片后用多模态LLM识别，最准确但最慢',
}

/** 所有可选引擎列表 */
const ALL_ENGINE_TYPES = ['markitdown', 'paddleocr', 'ppstructure', 'ppchatocr', 'mineru', 'llm']

const props = defineProps({
  fileId: { type: [String, Number], required: true },
  fileType: { type: String, default: '' },
  fileName: { type: String, default: '' },
  markdownContent: { type: String, default: '' },
  fileStatus: { type: String, default: '' },
  /** 从App.vue传入的引擎结果列表 */
  engineResults: { type: Array, default: () => [] },
})

const emit = defineEmits(['save', 'reconvert', 'back', 'converted', 'openLLMConfig'])

/** 引擎列数据：每个元素代表一个引擎面板 */
const engineColumns = ref([])

/** 切换文件时重置引擎列 */
watch(() => props.fileId, (newFileId, oldFileId) => {
  if (newFileId !== oldFileId) {
    engineColumns.value = []
    hoveredRegion.value = { regionId: -1, sourceEngine: '', originalId: -1 }
    hiddenEngineTypes.value = new Set()
    leftPaneHidden.value = false
    leftPaneWidth.value = 600
  }
})

/** LLM优化开关 */
const useLlmOptimize = ref(false)

/** LLM状态信息（用于tooltip显示） */
const llmStatus = ref({
  connection_ok: false,
  supports_vision: null,
  model: '',
  base_url: '',
})

/** 引擎可用状态 { type: { available, reason } } */
const engineAvailability = ref({})

/** 加载LLM状态 */
async function loadLLMStatus() {
  try {
    const status = await api.getLLMStatus()
    llmStatus.value = status
  } catch (e) {
    llmStatus.value = { connection_ok: false, supports_vision: null, model: '', base_url: '' }
  }
}

/** 加载引擎可用状态 */
async function loadEngineAvailability() {
  try {
    const res = await api.checkEngines()
    const map = {}
    for (const engine of (res.engines || [])) {
      map[engine.type] = { available: engine.available, reason: engine.reason }
    }
    engineAvailability.value = map
  } catch (e) {
    engineAvailability.value = {}
  }
}

// 组件挂载时加载LLM状态和引擎可用状态
loadLLMStatus()
loadEngineAvailability()

/** 手动识别引擎类型 */
const engineType = ref('markitdown')

/** 重新转换中 */
const reconverting = ref(false)

/** 左侧PDF面板宽度（像素） */
const leftPaneWidth = ref(500)

/** 左侧PDF面板是否隐藏 */
const leftPaneHidden = ref(false)

/** 隐藏的引擎类型集合 */
const hiddenEngineTypes = ref(new Set())

/** 拖拽状态 */
const dragState = ref({
  sourceEngineType: '',
  targetEngineType: '',
  isDragging: false,
})

/** 分隔容器引用 */
const splitContainer = ref(null)

/** 轮询定时器引用 */
let pollTimer = null

/** 转换进度 */
const progress = ref({
  visible: false,
  status: 'idle',
  currentEngine: '',
  currentStep: '',
  message: '',
  enginesTried: [],
  currentStepNum: 0,
  totalSteps: 4,
  percentage: 0,
})

/** 多引擎独立进度映射 */
const engineProgresses = ref({})

/** 添加引擎弹窗可见性 */
const addEngineModalVisible = ref(false)

/** 弹窗中选中的引擎列表 */
const selectedEngines = ref([])

/** 指标对比弹窗可见性 */
const metricsModalVisible = ref(false)

/** Diff对比弹窗可见性 */
const diffModalVisible = ref(false)

/** Diff基准引擎 */
const diffBaseEngine = ref('')

/** Diff对比引擎 */
const diffCompareEngine = ref('')

/** Diff对比结果 */
const diffResult = ref(null)

/** 列间分隔条宽度 */
const COLUMN_SPLIT_WIDTH = 6

/** 最小列宽 */
const MIN_COLUMN_WIDTH = 400

/** 添加引擎按钮宽度 */
const ADD_ENGINE_WIDTH = 80

/**
 * 从Markdown末尾解析REGIONS JSON块
 * @param {string} md - Markdown内容
 * @returns {Array} 区域数组
 */
const RE_REGIONS = /<!--\s*REGIONS:\s*([\s\S]*?)\s*-->/s
function parseRegions(md) {
  if (!md) return []
  const match = md.match(RE_REGIONS)
  if (!match) return []
  try {
    const parsed = JSON.parse(match[1])
    if (!Array.isArray(parsed)) return []
    return parsed
  } catch {
    return []
  }
}

/**
 * 从Markdown中去除regions注释
 * @param {string} md - Markdown内容
 * @returns {string} 去除regions后的Markdown
 */
function stripRegions(md) {
  if (!md) return ''
  return md.replace(RE_REGIONS, '').trimEnd()
}

/**
 * 将regions数据附加到markdown内容（用于保存时保留联动数据）
 * @param {string} md - Markdown内容
 * @param {Array} regionsData - 区域数据
 * @returns {string} 附加regions后的Markdown
 */
function attachRegions(md, regionsData) {
  if (!regionsData || !regionsData.length) return md
  const clean = stripRegions(md)
  const json = JSON.stringify(regionsData)
  return clean + `\n\n<!-- REGIONS:${json} -->`
}

/**
 * 规范化文件类型（去掉点号前缀）
 */
const normalizedType = computed(() => (props.fileType || '').replace(/^\./, ''))

/**
 * 原始文件预览URL
 */
const previewUrl = computed(() => api.getFilePreviewUrl(props.fileId))

/**
 * 当前活跃的regions（合并所有可见引擎的regions，用于PDF联动）
 * 每个region附带sourceEngine标识，hover时只高亮对应引擎的MdEditor
 */
const activeRegions = computed(() => {
  const visibleCols = engineColumns.value.filter(col => !hiddenEngineTypes.value.has(col.engineType))
  const allRegions = []
  let idOffset = 0
  for (const col of visibleCols) {
    if (col.regions && col.regions.length > 0) {
      for (const r of col.regions) {
        allRegions.push({
          ...r,
          id: idOffset + r.id,
          originalId: r.id,
          sourceEngine: col.engineType,
        })
      }
      idOffset += col.regions.length
    }
  }
  return allRegions
})

/**
 * 可见的引擎列（排除隐藏的引擎）
 */
const visibleEngineColumns = computed(() => {
  return engineColumns.value.filter(col => !hiddenEngineTypes.value.has(col.engineType))
})

/**
 * 隐藏列的信息（用于下拉菜单恢复显示）
 */
const hiddenColumnsInfo = computed(() => {
  return engineColumns.value
    .filter(col => hiddenEngineTypes.value.has(col.engineType))
    .map(col => ({ engineType: col.engineType, engineName: col.engineName }))
})

/**
 * 引擎列总宽度（含分隔条和添加按钮，仅计算可见列）
 */
const engineColumnsTotalWidth = computed(() => {
  let total = 0
  visibleEngineColumns.value.forEach((col) => {
    total += col.width
    // 每列后面都有分隔条
    total += COLUMN_SPLIT_WIDTH
  })
  if (engineColumns.value.length < 6) {
    total += ADD_ENGINE_WIDTH
  }
  return total
})

/**
 * 主体内部总宽度 = PDF面板（若可见）+ 分隔条 + 引擎列总宽度
 * 当总宽度不超过容器时，使用100%让内容撑满
 */
const bodyInnerWidth = computed(() => {
  const leftWidth = leftPaneHidden.value ? 0 : leftPaneWidth.value + 6
  const totalContentWidth = leftWidth + engineColumnsTotalWidth.value
  // 如果容器宽度足够，使用100%撑满；否则用固定宽度允许滚动
  const containerWidth = splitContainer.value?.clientWidth || 0
  if (containerWidth > 0 && totalContentWidth <= containerWidth) {
    return containerWidth
  }
  return totalContentWidth
})

/**
 * 可添加的引擎列表（排除已添加的）
 */
const availableEnginesToAdd = computed(() => {
  const existingTypes = new Set(engineColumns.value.map(c => c.engineType))
  return ALL_ENGINE_TYPES
    .filter(et => !existingTypes.has(et))
    .map(et => ({
      value: et,
      label: ENGINE_NAMES[et],
      description: ENGINE_DESCRIPTIONS[et] || '',
    }))
})

/**
 * 已完成的引擎列（用于指标对比和Diff）
 */
const completedEngineColumns = computed(() => {
  return engineColumns.value.filter(c => c.status === 'completed' && c.markdown)
})

/**
 * 已完成引擎数量
 */
const completedEngineCount = computed(() => completedEngineColumns.value.length)

/**
 * 指标对比表格列定义
 */
const metricsColumns = [
  { title: '引擎', dataIndex: 'engineName', key: 'engineName', width: 140 },
  { title: '耗时', dataIndex: 'duration', key: 'duration', width: 100, sorter: (a, b) => a.duration - b.duration },
  { title: '字符数', dataIndex: 'charCount', key: 'charCount', width: 100, sorter: (a, b) => a.charCount - b.charCount },
  { title: '行数', dataIndex: 'lineCount', key: 'lineCount', width: 80, sorter: (a, b) => a.lineCount - b.lineCount },
  { title: '速度', dataIndex: 'speed', key: 'speed', width: 110, sorter: (a, b) => a.speed - b.speed },
  { title: '状态', dataIndex: 'status', key: 'status', width: 80 },
]

/**
 * 指标对比表格数据
 */
const metricsData = computed(() => {
  const completed = completedEngineColumns.value
  if (completed.length === 0) return []

  const fastestDuration = Math.min(...completed.map(c => c.duration))
  const mostChars = Math.max(...completed.map(c => c.charCount))
  const mostLines = Math.max(...completed.map(c => c.lineCount))

  return completed.map((col, index) => ({
    key: col.engineType,
    engineName: col.engineName,
    duration: col.duration || 0,
    charCount: col.charCount || 0,
    lineCount: col.lineCount || 0,
    speed: (col.duration > 0 && col.charCount > 0) ? (col.charCount / col.duration) : 0,
    status: col.status === 'completed' ? '完成' : col.status,
    isFastest: col.duration === fastestDuration,
    isMostChars: col.charCount === mostChars,
    isMostLines: col.lineCount === mostLines,
    isBest: col.duration === fastestDuration,
  }))
})

/**
 * 显示指标对比弹窗
 */
function showMetricsModal() {
  metricsModalVisible.value = true
}

/**
 * 显示Diff对比弹窗
 */
function showDiffModal() {
  const completed = completedEngineColumns.value
  if (completed.length < 2) {
    message.warning('至少需要2个已完成的引擎结果才能对比')
    return
  }
  // 默认选择前两个引擎
  if (!diffBaseEngine.value || !completed.find(c => c.engineType === diffBaseEngine.value)) {
    diffBaseEngine.value = completed[0].engineType
  }
  if (!diffCompareEngine.value || !completed.find(c => c.engineType === diffCompareEngine.value) || diffCompareEngine.value === diffBaseEngine.value) {
    diffCompareEngine.value = completed.find(c => c.engineType !== diffBaseEngine.value)?.engineType || completed[1]?.engineType
  }
  computeDiff()
  diffModalVisible.value = true
}

/**
 * 交换Diff基准和对比引擎
 */
function swapDiffEngines() {
  const temp = diffBaseEngine.value
  diffBaseEngine.value = diffCompareEngine.value
  diffCompareEngine.value = temp
  computeDiff()
}

/**
 * 获取引擎名称
 * @param {string} engineType - 引擎类型标识
 * @returns {string} 引擎显示名称
 */
function getEngineName(engineType) {
  return ENGINE_NAMES[engineType] || engineType
}

/**
 * 计算两个引擎结果的Diff
 * 使用LCS（最长公共子序列）算法进行逐行对比
 */
function computeDiff() {
  const baseCol = engineColumns.value.find(c => c.engineType === diffBaseEngine.value)
  const compareCol = engineColumns.value.find(c => c.engineType === diffCompareEngine.value)
  if (!baseCol || !compareCol) {
    diffResult.value = null
    return
  }

  const baseLines = (baseCol.markdown || '').split('\n')
  const compareLines = (compareCol.markdown || '').split('\n')

  // 使用LCS算法计算差异
  const lcs = computeLCS(baseLines, compareLines)

  // 根据LCS结果生成差异行
  const leftLines = []
  const rightLines = []
  let addedLines = 0, removedLines = 0, modifiedLines = 0, unchangedLines = 0

  let i = 0, j = 0
  for (const op of lcs) {
    if (op.type === 'equal') {
      leftLines.push({ num: i + 1, prefix: ' ', text: baseLines[i], type: 'unchanged' })
      rightLines.push({ num: j + 1, prefix: ' ', text: compareLines[j], type: 'unchanged' })
      unchangedLines++
      i++; j++
    } else if (op.type === 'removed') {
      leftLines.push({ num: i + 1, prefix: '-', text: baseLines[i], type: 'removed' })
      i++
      removedLines++
    } else if (op.type === 'added') {
      rightLines.push({ num: j + 1, prefix: '+', text: compareLines[j], type: 'added' })
      j++
      addedLines++
    } else if (op.type === 'modified') {
      leftLines.push({ num: i + 1, prefix: '~', text: baseLines[i], type: 'modified-old' })
      rightLines.push({ num: j + 1, prefix: '~', text: compareLines[j], type: 'modified-new' })
      modifiedLines++
      i++; j++
    }
  }

  // 计算相似度
  const totalLines = Math.max(baseLines.length, compareLines.length)
  const similarity = totalLines > 0 ? ((unchangedLines / totalLines) * 100).toFixed(1) : '100.0'

  diffResult.value = {
    leftLines,
    rightLines,
    addedLines,
    removedLines,
    modifiedLines,
    unchangedLines,
    similarity,
  }
}

/**
 * 计算两个文本数组的LCS差异
 * 使用优化的动态规划算法，对长文本做行级对比
 * @param {string[]} a - 基准文本行数组
 * @param {string[]} b - 对比文本行数组
 * @returns {Array} 操作序列
 */
function computeLCS(a, b) {
  const m = a.length
  const n = b.length

  // 对超长文本做截断优化，避免O(mn)过大
  const MAX_LINES = 3000
  const aSlice = a.slice(0, MAX_LINES)
  const bSlice = b.slice(0, MAX_LINES)
  const am = aSlice.length
  const bn = bSlice.length

  // 构建DP表
  const dp = Array.from({ length: am + 1 }, () => new Uint16Array(bn + 1))
  for (let i = 1; i <= am; i++) {
    for (let j = 1; j <= bn; j++) {
      if (aSlice[i - 1] === bSlice[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1])
      }
    }
  }

  // 回溯生成操作序列
  const ops = []
  let i = am, j = bn
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && aSlice[i - 1] === bSlice[j - 1]) {
      ops.push({ type: 'equal' })
      i--; j--
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ type: 'added' })
      j--
    } else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
      ops.push({ type: 'removed' })
      i--
    }
  }
  ops.reverse()

  // 将连续的removed+added合并为modified
  const merged = []
  let k = 0
  while (k < ops.length) {
    if (ops[k].type === 'removed' && k + 1 < ops.length && ops[k + 1].type === 'added') {
      merged.push({ type: 'modified' })
      k += 2
    } else {
      merged.push(ops[k])
      k++
    }
  }

  // 如果原始文本被截断，追加剩余行
  if (a.length > MAX_LINES) {
    for (let ri = MAX_LINES; ri < a.length; ri++) {
      merged.push({ type: 'removed' })
    }
  }
  if (b.length > MAX_LINES) {
    for (let ri = MAX_LINES; ri < b.length; ri++) {
      merged.push({ type: 'added' })
    }
  }

  return merged
}

/** 监听Diff引擎选择变化，重新计算 */
watch([diffBaseEngine, diffCompareEngine], () => {
  if (diffModalVisible.value && diffBaseEngine.value && diffCompareEngine.value) {
    computeDiff()
  }
})

/**
 * 根据可用宽度计算每列的初始宽度
 * @param {number} columnCount - 列数
 * @returns {number} 每列宽度
 */
function calculateColumnWidth(columnCount) {
  // 默认每列600px，最小400px
  const defaultWidth = 600
  return Math.max(defaultWidth, MIN_COLUMN_WIDTH)
}

/**
 * 计算自适应列宽：当列数较少时让列撑满容器
 * @returns {{ leftWidth: number, engineWidths: number[] }}
 */
function calculateAutoFitWidths() {
  if (!splitContainer.value) {
    return { leftWidth: leftPaneWidth.value, engineWidths: visibleEngineColumns.value.map(() => 600) }
  }

  const containerWidth = splitContainer.value.clientWidth
  const visibleCount = visibleEngineColumns.value.length
  if (visibleCount === 0) {
    return { leftWidth: leftPaneWidth.value, engineWidths: [] }
  }

  // 计算固定占用：分隔条 + 添加引擎按钮
  const splitCount = (leftPaneHidden.value ? 0 : 1) + visibleCount // 每列后面都有分隔条
  const addBtnWidth = (engineColumns.value.length < 6) ? ADD_ENGINE_WIDTH : 0
  const fixedWidth = splitCount * COLUMN_SPLIT_WIDTH + addBtnWidth

  // 可用宽度 = 容器宽度 - 固定占用
  const availableWidth = containerWidth - fixedWidth

  // 计算各列按固定宽度的总需求
  const leftW = leftPaneHidden.value ? 0 : leftPaneWidth.value
  const engineFixedTotal = visibleCount * 600
  const totalFixed = leftW + engineFixedTotal

  if (totalFixed <= availableWidth) {
    // 固定宽度能放下，按比例分配多余空间
    const extra = availableWidth - totalFixed
    const leftExtra = leftPaneHidden.value ? 0 : Math.round(extra * (leftW / totalFixed))
    const engineExtra = extra - leftExtra
    const perEngine = Math.floor(engineExtra / visibleCount)
    const remainder = engineExtra - perEngine * visibleCount

    const engineWidths = visibleEngineColumns.value.map((_, i) => 600 + perEngine + (i < remainder ? 1 : 0))
    return { leftWidth: leftW + leftExtra, engineWidths }
  } else {
    // 放不下，用固定宽度（允许水平滚动）
    return {
      leftWidth: leftW,
      engineWidths: visibleEngineColumns.value.map(() => 600)
    }
  }
}

/**
 * 应用自适应列宽到各列
 */
function applyAutoFitWidths() {
  const { leftWidth, engineWidths } = calculateAutoFitWidths()
  if (!leftPaneHidden.value) {
    leftPaneWidth.value = leftWidth
  }
  visibleEngineColumns.value.forEach((col, i) => {
    if (engineWidths[i] !== undefined) {
      col.width = engineWidths[i]
    }
  })
}

/**
 * 初始化引擎列数据
 * 根据已有的引擎结果构建初始列，如果没有结果则默认添加markitdown
 * @param {Array} engineResults - 后端返回的引擎结果列表
 */
function initEngineColumns(engineResults) {
  const colWidth = calculateColumnWidth(engineResults?.length || 1)

  if (engineResults && engineResults.length > 0) {
    engineColumns.value = engineResults.map(er => ({
      engineType: er.engine_type,
      engineName: er.engine_name || ENGINE_NAMES[er.engine_type] || er.engine_type,
      markdown: stripRegions(er.markdown_content || ''),
      regions: parseRegions(er.markdown_content || ''),
      status: er.status || 'completed',
      duration: er.duration || 0,
      charCount: er.char_count || 0,
      lineCount: er.line_count || 0,
      percentage: 0,
      width: colWidth,
      errorMessage: er.error_message || '',
    }))
  } else if (props.markdownContent) {
    // 有外部传入的markdown内容（兼容旧接口），用下拉框当前选中的引擎显示
    const defaultEngine = engineType.value || 'markitdown'
    engineColumns.value = [{
      engineType: defaultEngine,
      engineName: ENGINE_NAMES[defaultEngine] || defaultEngine,
      markdown: stripRegions(props.markdownContent),
      regions: parseRegions(props.markdownContent),
      status: 'completed',
      duration: 0,
      charCount: 0,
      lineCount: 0,
      percentage: 0,
      width: colWidth,
      errorMessage: '',
    }]
  } else {
    // 没有引擎结果也没有markdown内容，空列等待用户添加引擎
    engineColumns.value = []
  }

  // 初始化后自适应列宽
  nextTick(() => applyAutoFitWidths())
}

/**
 * 监听外部markdown内容变化（兼容旧接口）
 */
watch(
  () => props.markdownContent,
  (val) => {
    // 仅在单列模式且为默认引擎时更新
    if (engineColumns.value.length === 1 && engineColumns.value[0].engineType === engineType.value) {
      engineColumns.value[0].markdown = stripRegions(val)
      engineColumns.value[0].regions = parseRegions(val)
      if (val) {
        engineColumns.value[0].status = 'completed'
      }
    }
  },
  { immediate: true }
)

/**
 * 监听外部engineResults变化
 */
watch(
  () => props.engineResults,
  (val) => {
    if (val && val.length > 0) {
      // 更新已有列的数据或新增列
      val.forEach(er => {
        const existingCol = engineColumns.value.find(c => c.engineType === er.engine_type)
        if (existingCol) {
          // 更新已有列
          if (er.markdown_content) {
            existingCol.markdown = stripRegions(er.markdown_content)
            existingCol.regions = parseRegions(er.markdown_content)
          }
          existingCol.status = er.status || existingCol.status
          existingCol.duration = er.duration || existingCol.duration
          existingCol.charCount = er.char_count || existingCol.charCount
          existingCol.lineCount = er.line_count || existingCol.lineCount
          existingCol.errorMessage = er.error_message || existingCol.errorMessage
        }
      })
    }
  },
  { deep: true }
)

/**
 * 显示添加引擎弹窗
 */
function showAddEngineModal() {
  selectedEngines.value = []
  addEngineModalVisible.value = true
}

/**
 * 处理添加引擎确认
 * 对选中的引擎：如果后端已有结果则直接显示，否则触发识别
 */
async function handleAddEngine() {
  if (selectedEngines.value.length === 0) {
    message.warning('请至少选择一个引擎')
    return
  }

  addEngineModalVisible.value = false

  // 获取后端已有的引擎结果
  let existingResults = {}
  try {
    const res = await api.getEngineResults(props.fileId)
    if (res && res.engine_results) {
      res.engine_results.forEach(er => {
        existingResults[er.engine_type] = er
      })
    }
  } catch {
    // 获取失败不影响后续操作
  }

  // 计算新列数量
  const newColumnCount = engineColumns.value.length + selectedEngines.value.length

  // 需要识别的引擎列表
  const enginesToConvert = []

  // 添加新列
  selectedEngines.value.forEach(et => {
    const existing = existingResults[et]
    engineColumns.value.push({
      engineType: et,
      engineName: ENGINE_NAMES[et] || et,
      markdown: existing ? stripRegions(existing.markdown_content || '') : '',
      regions: existing ? parseRegions(existing.markdown_content || '') : [],
      status: existing ? (existing.status || 'completed') : 'pending',
      duration: existing ? (existing.duration || 0) : 0,
      charCount: existing ? (existing.char_count || 0) : 0,
      lineCount: existing ? (existing.line_count || 0) : 0,
      percentage: 0,
      width: 600,
      errorMessage: existing ? (existing.error_message || '') : '',
    })

    // 如果没有已有结果或状态不是completed，需要触发识别
    if (!existing || (existing.status !== 'completed' && existing.status !== 'converting')) {
      enginesToConvert.push(et)
    }
  })

  // 如果有需要识别的引擎，触发批量识别
  if (enginesToConvert.length > 0) {
    reconverting.value = true
    connectProgress(props.fileId)
    emit('reconvert', {
      fileId: props.fileId,
      useLlmOptimize: useLlmOptimize.value,
      engineTypes: enginesToConvert,
    })
  }

  // 添加引擎后自适应列宽
  nextTick(() => applyAutoFitWidths())
}

/**
 * 切换左侧PDF面板的显示/隐藏
 */
function toggleLeftPane() {
  leftPaneHidden.value = !leftPaneHidden.value
  nextTick(() => applyAutoFitWidths())
}

/**
 * 切换引擎列的显示/隐藏
 * @param {string} engineType - 引擎类型标识
 */
function toggleEngineColumn(engineType) {
  if (hiddenEngineTypes.value.has(engineType)) {
    hiddenEngineTypes.value.delete(engineType)
  } else {
    // 至少保留一个可见列
    if (visibleEngineColumns.value.length <= 1) {
      message.warning('至少保留一个可见的引擎列')
      return
    }
    hiddenEngineTypes.value.add(engineType)
  }
  nextTick(() => applyAutoFitWidths())
}

/**
 * 恢复显示被隐藏的引擎列
 * @param {string} engineType - 引擎类型标识
 */
function showHiddenColumn(engineType) {
  hiddenEngineTypes.value.delete(engineType)
  nextTick(() => applyAutoFitWidths())
}

/**
 * 移除引擎列
 * @param {string} engineType - 引擎类型标识
 */
function removeEngine(engineType) {
  const index = engineColumns.value.findIndex(c => c.engineType === engineType)
  if (index === -1) return
  hiddenEngineTypes.value.delete(engineType)
  engineColumns.value.splice(index, 1)
  // 重新自适应列宽
  nextTick(() => applyAutoFitWidths())
}

/**
 * 批量识别全部已添加引擎
 */
function handleBatchReconvert() {
  // 检查LLM相关提示
  const engineTypes = engineColumns.value.map(c => c.engineType)
  if (engineTypes.includes('llm') && !llmStatus.value.connection_ok) {
    message.warning('LLM连接不可用，图片识别引擎可能失败，请先配置大模型')
  }
  if (useLlmOptimize.value && !llmStatus.value.connection_ok) {
    message.warning('LLM连接不可用，优化功能可能失败，请先配置大模型')
  }
  reconverting.value = true
  // 重置所有列状态
  engineColumns.value.forEach(col => {
    col.status = 'pending'
    col.percentage = 0
  })
  connectProgress(props.fileId)
  emit('reconvert', {
    fileId: props.fileId,
    useLlmOptimize: useLlmOptimize.value,
    engineTypes: engineTypes,
  })
}

/**
 * 单引擎识别（手动识别下拉框选择的引擎）
 */
function handleReconvert() {
  const selectedType = engineType.value
  // 检查LLM相关提示
  if (selectedType === 'llm' && !llmStatus.value.connection_ok) {
    message.warning('LLM连接不可用，图片识别引擎可能失败，请先配置大模型')
  }
  if (selectedType === 'llm' && llmStatus.value.supports_vision === false) {
    message.warning('当前模型不支持图片识别，请配置支持多模态的模型（如 GPT-4o、doubao-vision-pro）')
  }
  if (useLlmOptimize.value && !llmStatus.value.connection_ok) {
    message.warning('LLM连接不可用，优化功能可能失败，请先配置大模型')
  }
  reconverting.value = true
  // 检查该引擎是否已在列中
  const existingCol = engineColumns.value.find(c => c.engineType === selectedType)
  if (existingCol) {
    // 已存在，重置状态并重新识别
    existingCol.status = 'pending'
    existingCol.percentage = 0
  } else {
    // 不存在，添加新列
    engineColumns.value.push({
      engineType: selectedType,
      engineName: ENGINE_NAMES[selectedType] || selectedType,
      markdown: '',
      regions: [],
      status: 'pending',
      duration: 0,
      charCount: 0,
      lineCount: 0,
      percentage: 0,
      width: 600,
      errorMessage: '',
    })
    nextTick(() => applyAutoFitWidths())
  }
  connectProgress(props.fileId)
  emit('reconvert', {
    fileId: props.fileId,
    useLlmOptimize: useLlmOptimize.value,
    engineType: selectedType,
  })
}

/**
 * 开始轮询转换进度
 * @param {string} fileId - 文件ID
 */
function connectProgress(fileId) {
  disconnectProgress()
  progress.value = {
    visible: true,
    status: 'converting',
    currentEngine: '',
    currentStep: '',
    message: '正在启动转换...',
    enginesTried: [],
    currentStepNum: 0,
    totalSteps: 4,
    percentage: 0,
  }
  engineProgresses.value = {}

  /** 立即查询一次 */
  pollProgress(fileId)

  /** 每1秒轮询一次 */
  pollTimer = setInterval(() => pollProgress(fileId), 1000)
}

/**
 * 轮询一次进度，解析多引擎独立进度
 * @param {string} fileId - 文件ID
 */
async function pollProgress(fileId) {
  try {
    const data = await api.getConvertProgress(fileId)
    if (!data || data.status === 'idle') return

    const enginesTried = [...progress.value.enginesTried]
    if (data.current_engine && !enginesTried.includes(data.current_engine)) {
      enginesTried.push(data.current_engine)
    }

    progress.value = {
      visible: true,
      status: data.status,
      currentEngine: data.current_engine,
      currentStep: data.current_step,
      message: data.message || `${ENGINE_NAMES[data.current_engine] || data.current_engine} - ${data.current_step}`,
      enginesTried: data.engines_tried || enginesTried,
      currentStepNum: data.current_step_num || 0,
      totalSteps: data.total_steps || 4,
      percentage: data.percentage || 0,
    }

    // 更新多引擎独立进度
    if (data.engines && typeof data.engines === 'object') {
      engineProgresses.value = data.engines
      // 同步更新对应引擎列的状态和进度
      for (const [etype, eprog] of Object.entries(data.engines)) {
        const col = engineColumns.value.find(c => c.engineType === etype)
        if (col) {
          col.status = eprog.status || col.status
          col.percentage = eprog.percentage || 0
        }
      }
    }

    // 转换完成或失败时停止轮询
    if (data.status === 'completed') {
      await refreshEngineResults(fileId)
      reconverting.value = false
      emit('converted', { fileId })
      setTimeout(() => {
        progress.value.visible = false
      }, 3000)
      disconnectProgress()
    } else if (data.status === 'failed') {
      reconverting.value = false
      setTimeout(() => {
        progress.value.visible = false
      }, 5000)
      disconnectProgress()
    }
  } catch {
    // 轮询失败不中断，继续下次
  }
}

/**
 * 转换完成后刷新所有引擎结果
 * @param {string} fileId - 文件ID
 */
async function refreshEngineResults(fileId) {
  try {
    const res = await api.getEngineResults(fileId)
    if (res && res.engine_results) {
      res.engine_results.forEach(er => {
        const col = engineColumns.value.find(c => c.engineType === er.engine_type)
        if (col) {
          if (er.markdown_content) {
            col.markdown = stripRegions(er.markdown_content)
            col.regions = parseRegions(er.markdown_content)
          }
          col.status = er.status || col.status
          col.duration = er.duration || col.duration
          col.charCount = er.char_count || col.charCount
          col.lineCount = er.line_count || col.lineCount
          col.errorMessage = er.error_message || col.errorMessage
        }
      })
    }
  } catch {
    // 刷新失败不影响主流程
  }
}

/**
 * 停止轮询
 */
function disconnectProgress() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/**
 * 停止轮询并重置reconverting状态
 */
function stopReconverting() {
  reconverting.value = false
  disconnectProgress()
}

/**
 * 保存指定引擎的Markdown
 * @param {string} engineType - 引擎类型
 * @param {string} content - Markdown内容
 */
async function handleEngineSave(engineType, content) {
  const col = engineColumns.value.find(c => c.engineType === engineType)
  if (!col) return
  const contentWithRegions = attachRegions(content, col.regions)
  try {
    await api.saveEngineMarkdown(props.fileId, engineType, contentWithRegions)
    message.success(`${col.engineName} 保存成功`)
  } catch (err) {
    message.error(`${col.engineName} 保存失败：${err.message || '未知错误'}`)
  }
}

/**
 * 导出指定引擎的Markdown文件
 * @param {Object} col - 引擎列数据
 */
function handleEngineExport(col) {
  const blob = new Blob([col.markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${(props.fileName?.replace(/\.[^.]+$/, '') || 'document')}_${col.engineType}.md`
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * 复制指定引擎的Markdown内容到剪贴板
 * @param {string} content - Markdown内容
 */
async function handleEngineCopy(content) {
  try {
    await navigator.clipboard.writeText(content)
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败')
  }
}

/**
 * PDF分隔条拖拽 - 鼠标按下
 * @param {string} type - 分隔条类型（'pdf'）
 * @param {MouseEvent} e - 鼠标事件
 */
function onSplitMouseDown(type, e) {
  e.preventDefault()

  const startX = e.clientX
  const startWidth = leftPaneWidth.value

  /**
   * 拖拽中 - 鼠标移动
   * @param {MouseEvent} moveEvent - 鼠标移动事件
   */
  function onMouseMove(moveEvent) {
    const dx = moveEvent.clientX - startX
    leftPaneWidth.value = Math.min(1200, Math.max(200, startWidth + dx))
  }

  /**
   * 拖拽结束 - 鼠标松开
   */
  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

/**
 * 列间分隔条拖拽 - 鼠标按下
 * @param {string} leftEngineType - 左侧列的引擎类型
 * @param {string} rightEngineType - 右侧列的引擎类型
 * @param {MouseEvent} e - 鼠标事件
 */
function onColumnSplitMouseDown(leftEngineType, rightEngineType, e) {
  e.preventDefault()
  const leftCol = engineColumns.value.find(c => c.engineType === leftEngineType)
  if (!leftCol) return

  const startX = e.clientX
  const startLeftWidth = leftCol.width
  const rightCol = rightEngineType ? engineColumns.value.find(c => c.engineType === rightEngineType) : null
  const startRightWidth = rightCol ? rightCol.width : 0

  /**
   * 拖拽中 - 鼠标移动
   * @param {MouseEvent} moveEvent - 鼠标移动事件
   */
  function onMouseMove(moveEvent) {
    const dx = moveEvent.clientX - startX
    let newLeftWidth = startLeftWidth + dx

    // 限制最小宽度
    if (newLeftWidth < MIN_COLUMN_WIDTH) {
      newLeftWidth = MIN_COLUMN_WIDTH
    }

    if (rightCol) {
      // 两列之间拖动：左侧变宽，右侧变窄
      let newRightWidth = startRightWidth - dx
      if (newRightWidth < MIN_COLUMN_WIDTH) {
        newRightWidth = MIN_COLUMN_WIDTH
        newLeftWidth = startLeftWidth + startRightWidth - MIN_COLUMN_WIDTH
      }
      rightCol.width = newRightWidth
    }
    // 最后一列后面拖动：只调整左侧列宽

    leftCol.width = newLeftWidth
  }

  /**
   * 拖拽结束 - 鼠标松开
   */
  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

/**
 * 引擎列拖拽开始
 * @param {string} engineType - 被拖拽的引擎类型
 * @param {DragEvent} event - 拖拽事件
 */
function onEngineDragStart(engineType, event) {
  dragState.value.sourceEngineType = engineType
  dragState.value.isDragging = true
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', engineType)
  // 让源列半透明
  const el = document.querySelector(`[data-engine-type="${engineType}"]`)
  if (el) el.style.opacity = '0.4'
}

/**
 * 引擎列拖拽经过目标列
 * @param {string} engineType - 目标引擎类型
 * @param {DragEvent} event - 拖拽事件
 */
function onEngineDragOver(engineType, event) {
  if (!dragState.value.isDragging || dragState.value.sourceEngineType === engineType) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dragState.value.targetEngineType = engineType
}

/**
 * 引擎列拖拽离开目标列
 * @param {string} engineType - 目标引擎类型
 * @param {DragEvent} event - 拖拽事件
 */
function onEngineDragLeave(engineType, event) {
  // 只在真正离开列时清除
  const rect = event.currentTarget.getBoundingClientRect()
  const x = event.clientX
  const y = event.clientY
  if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
    if (dragState.value.targetEngineType === engineType) {
      dragState.value.targetEngineType = ''
    }
  }
}

/**
 * 引擎列拖拽放下
 * @param {string} targetEngineType - 目标引擎类型
 * @param {DragEvent} event - 拖拽事件
 */
async function onEngineDrop(targetEngineType, event) {
  event.preventDefault()
  const sourceEngineType = dragState.value.sourceEngineType
  if (!sourceEngineType || sourceEngineType === targetEngineType) {
    resetDragState()
    return
  }

  // FLIP: First - 记录所有可见列当前位置
  const firstRects = {}
  visibleEngineColumns.value.forEach(col => {
    const el = document.querySelector(`[data-engine-type="${col.engineType}"]`)
    if (el) firstRects[col.engineType] = el.getBoundingClientRect()
  })

  // 重排序 engineColumns 数组
  const sourceIndex = engineColumns.value.findIndex(c => c.engineType === sourceEngineType)
  const targetIndex = engineColumns.value.findIndex(c => c.engineType === targetEngineType)
  if (sourceIndex === -1 || targetIndex === -1) {
    resetDragState()
    return
  }
  const [moved] = engineColumns.value.splice(sourceIndex, 1)
  engineColumns.value.splice(targetIndex, 0, moved)

  // FLIP: Last + Invert + Play
  await nextTick()
  visibleEngineColumns.value.forEach(col => {
    const el = document.querySelector(`[data-engine-type="${col.engineType}"]`)
    if (el && firstRects[col.engineType]) {
      const lastRect = el.getBoundingClientRect()
      const deltaX = firstRects[col.engineType].left - lastRect.left
      if (deltaX !== 0) {
        el.style.transform = `translateX(${deltaX}px)`
        el.style.transition = 'none'
        requestAnimationFrame(() => {
          el.style.transition = 'transform 0.3s ease'
          el.style.transform = ''
          // 动画结束后清理
          el.addEventListener('transitionend', () => {
            el.style.transition = ''
            el.style.transform = ''
          }, { once: true })
        })
      }
    }
  })

  resetDragState()
}

/**
 * 引擎列拖拽结束
 */
function onEngineDragEnd() {
  resetDragState()
}

/**
 * 重置拖拽状态
 */
function resetDragState() {
  // 恢复源列透明度
  if (dragState.value.sourceEngineType) {
    const el = document.querySelector(`[data-engine-type="${dragState.value.sourceEngineType}"]`)
    if (el) el.style.opacity = ''
  }
  dragState.value = {
    sourceEngineType: '',
    targetEngineType: '',
    isDragging: false,
  }
}

/** 当前悬停的区域信息 { regionId, sourceEngine, originalId } */
const hoveredRegion = ref({ regionId: -1, sourceEngine: '', originalId: -1 })

/**
 * 左侧区域悬停事件处理
 * @param {number} regionId - 区域ID（合并后的全局ID，-1表示离开）
 */
function onHoverRegion(regionId) {
  if (regionId < 0) {
    hoveredRegion.value = { regionId: -1, sourceEngine: '', originalId: -1 }
    return
  }
  // 从activeRegions中找到对应的region，获取sourceEngine和originalId
  const region = activeRegions.value.find(r => r.id === regionId)
  if (region) {
    hoveredRegion.value = {
      regionId,
      sourceEngine: region.sourceEngine,
      originalId: region.originalId,
    }
  } else {
    hoveredRegion.value = { regionId, sourceEngine: '', originalId: -1 }
  }
}

/**
 * 获取文件类型标签颜色
 * @param {string} type - 文件类型
 * @returns {string} 颜色值
 */
function getTypeColor(type) {
  const map = { pdf: 'red', docx: 'blue', doc: 'blue', xls: 'green', xlsx: 'green', txt: 'orange', csv: 'cyan' }
  return map[type] || 'default'
}

/** 窗口resize时重新自适应列宽 */
function onWindowResize() {
  applyAutoFitWidths()
}

/** 组件挂载时初始化引擎列 */
onMounted(async () => {
  // 监听窗口resize
  window.addEventListener('resize', onWindowResize)

  // 等待容器渲染完成
  await nextTick()

  // 如果有传入的engineResults，使用它们初始化
  if (props.engineResults && props.engineResults.length > 0) {
    initEngineColumns(props.engineResults)
  } else {
    // 尝试从后端获取引擎结果
    try {
      const res = await api.getEngineResults(props.fileId)
      if (res && res.engine_results && res.engine_results.length > 0) {
        initEngineColumns(res.engine_results)
      } else {
        // 没有引擎结果，用默认markdown初始化单列
        initEngineColumns([])
      }
    } catch {
      initEngineColumns([])
    }
  }

  // 如果文件正在转换中，自动启动轮询
  if (props.fileStatus === 'converting') {
    connectProgress(props.fileId)
  }
})

/** 组件卸载时停止轮询和resize监听 */
onUnmounted(() => {
  disconnectProgress()
  window.removeEventListener('resize', onWindowResize)
})

/** 暴露方法给父组件 */
defineExpose({ stopReconverting })
</script>

<style scoped>
.compare-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f0f2f5;
}

/* 工具栏 */
.compare-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.toolbar-filename {
  font-size: 14px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.85);
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  overflow-x: auto;
  flex-shrink: 0;
}

/* 进度条 */
.progress-bar {
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.progress-content {
  max-width: 900px;
  margin: 0 auto;
}

.progress-detail {
  display: flex;
  align-items: center;
  gap: 16px;
}

.progress-detail :deep(.ant-progress) {
  flex: 1;
  margin-bottom: 0;
}

.progress-message {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.progress-text {
  color: rgba(0, 0, 0, 0.65);
}

/* 多引擎独立进度 */
.engine-progress-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.engine-progress-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.engine-progress-name {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.65);
  min-width: 100px;
}

/* 分栏主体：整体水平滚动 */
.compare-body {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0;
}

.compare-body-inner {
  display: flex;
  height: 100%;
  min-width: 100%;
}

/* 面板 */
.compare-pane {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.pane-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(0, 0, 0, 0.65);
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.pane-content {
  flex: 1;
  overflow: hidden;
}

/* PDF分隔条 */
.split-bar {
  width: 6px;
  cursor: col-resize;
  background: #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.2s;
}

.split-bar:hover {
  background: #1890ff;
}

.split-handle {
  width: 2px;
  height: 32px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 1px;
}

.split-bar:hover .split-handle {
  background: #fff;
}

/* 引擎列容器 */
.engine-columns {
  display: flex;
  height: 100%;
  flex: 1;
}

/* 引擎列 */
.engine-column {
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
  flex-shrink: 0;
}

.engine-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.engine-name {
  font-weight: 600;
  color: rgba(0, 0, 0, 0.85);
  white-space: nowrap;
}

.engine-stats {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.45);
  white-space: nowrap;
}

.engine-error {
  font-size: 11px;
  color: #ff4d4f;
  white-space: nowrap;
}

.engine-pending {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.35);
  white-space: nowrap;
}

.engine-close {
  margin-left: auto;
  cursor: pointer;
  color: rgba(0, 0, 0, 0.25);
  font-size: 12px;
  padding: 2px 4px;
  transition: color 0.2s;
}

.engine-close:hover {
  color: #ff4d4f;
}

/* 左侧面板隐藏按钮 */
.pane-hide-btn {
  margin-left: auto;
  cursor: pointer;
  color: rgba(0, 0, 0, 0.45);
  font-size: 14px;
  padding: 2px 6px;
  transition: color 0.2s;
}
.pane-hide-btn:hover {
  color: #1890ff;
}

/* 引擎列隐藏按钮 */
.engine-hide-btn {
  cursor: pointer;
  color: rgba(0, 0, 0, 0.45);
  font-size: 14px;
  padding: 2px 6px;
  transition: color 0.2s;
}
.engine-hide-btn:hover {
  color: #1890ff;
}

/* 拖拽手柄 */
.engine-drag-handle {
  cursor: grab;
  color: rgba(0, 0, 0, 0.45);
  font-size: 14px;
  padding: 2px 4px;
  transition: color 0.2s;
}
.engine-drag-handle:hover {
  color: #1890ff;
}
.engine-drag-handle:active {
  cursor: grabbing;
}

/* 拖拽状态 */
.engine-column.drag-source {
  opacity: 0.4;
}

.engine-column.drag-over {
  box-shadow: -3px 0 0 0 #1890ff;
}

/* 引擎header拖拽时样式 */
.engine-header[draggable="true"] {
  cursor: default;
  user-select: none;
}

.engine-content {
  flex: 1;
  overflow: hidden;
}

.engine-footer {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #fafafa;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.engine-footer :deep(.ant-btn) {
  font-size: 12px;
}

/* 列间分隔条 */
.column-split-bar {
  width: 6px;
  cursor: col-resize;
  background: #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.2s;
}

.column-split-bar:hover {
  background: #1890ff;
}

.column-split-handle {
  width: 2px;
  height: 32px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 1px;
}

.column-split-bar:hover .column-split-handle {
  background: #fff;
}

/* 添加引擎按钮 */
.add-engine-column {
  width: 80px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: #fafafa;
  border: 2px dashed #d9d9d9;
  border-radius: 4px;
  margin: 8px 4px;
  transition: border-color 0.2s, background 0.2s;
}

.add-engine-column:hover {
  border-color: #1890ff;
  background: #f0f5ff;
}

/* 添加引擎弹窗中的引擎选项 */
.engine-checkbox-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.engine-checkbox-item:last-child {
  border-bottom: none;
}

.engine-checkbox-name {
  font-weight: 500;
  margin-right: 8px;
}

.engine-checkbox-desc {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

/* 指标对比最佳行高亮 */
:deep(.metrics-best-row) {
  background: #f6ffed;
}

/* Diff对比 */
.diff-controls {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
}

.diff-label {
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
  white-space: nowrap;
}

.diff-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}

.diff-similarity {
  margin-left: auto;
  font-size: 13px;
  font-weight: 600;
  color: #1890ff;
}

.diff-content {
  display: flex;
  height: calc(80vh - 120px);
  overflow: hidden;
}

.diff-pane {
  flex: 1;
  overflow-y: auto;
  border-right: 1px solid #f0f0f0;
}

.diff-pane:last-child {
  border-right: none;
}

.diff-pane-header {
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.85);
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
  position: sticky;
  top: 0;
  z-index: 1;
}

.diff-lines {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.diff-line {
  display: flex;
  padding: 0 8px;
  min-height: 20px;
}

.diff-line:hover {
  background: rgba(0, 0, 0, 0.02);
}

.diff-line-num {
  width: 48px;
  text-align: right;
  color: rgba(0, 0, 0, 0.3);
  flex-shrink: 0;
  user-select: none;
  padding-right: 8px;
}

.diff-line-prefix {
  width: 16px;
  flex-shrink: 0;
  font-weight: 600;
  user-select: none;
}

.diff-line-text {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
}

.diff-line-removed {
  background: #fff1f0;
}

.diff-line-removed .diff-line-prefix {
  color: #ff4d4f;
}

.diff-line-added {
  background: #f6ffed;
}

.diff-line-added .diff-line-prefix {
  color: #52c41a;
}

.diff-line-modified-old {
  background: #fff7e6;
}

.diff-line-modified-old .diff-line-prefix {
  color: #fa8c16;
}

.diff-line-modified-new {
  background: #e6f7ff;
}

.diff-line-modified-new .diff-line-prefix {
  color: #1890ff;
}

.llm-switch-tooltip {
  max-width: 280px;
  font-size: 13px;
  line-height: 1.6;
}
</style>
