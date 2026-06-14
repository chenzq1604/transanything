<template>
  <a-layout class="app-layout">
    <!-- 顶部导航栏 -->
    <a-layout-header class="app-header">
      <div class="header-left">
        <SwapOutlined class="header-icon" @click="showAboutModal = true" style="cursor: pointer" />
        <h1 class="header-title" @click="showAboutModal = true" style="cursor: pointer">TransAnything</h1>
        <span class="header-subtitle">文件转Markdown平台</span>
      </div>
      <div class="header-right">
        <a-button type="text" size="small" @click="showEnvCheckModal = true" style="color: rgba(255,255,255,0.85)">
          <SafetyCertificateOutlined /> 环境检测
        </a-button>
        <a-button type="text" size="small" @click="showLLMConfigModal = true" style="color: rgba(255,255,255,0.85)">
          <SettingOutlined /> 大模型配置
        </a-button>
        <FileUpload @uploaded="onFileUploaded" />
      </div>
    </a-layout-header>

    <!-- 主体内容区 -->
    <a-layout-content class="app-content">
      <div class="content-wrapper">
        <!-- 左侧文件列表（可拖拽调整宽度） -->
        <div
          class="file-sider"
          :style="{ width: siderWidth + 'px' }"
          v-show="!siderCollapsed"
        >
          <div class="sider-header">
            <span class="sider-title">文件列表</span>
            <a-button type="text" size="small" @click="siderCollapsed = true">
              <MenuFoldOutlined />
            </a-button>
          </div>
          <FileList
            ref="fileListRef"
            :activeFileId="currentFile?.id || ''"
            @view="onViewFile"
          />
        </div>

        <!-- 拖拽分隔条 -->
        <div
          v-show="!siderCollapsed"
          class="resize-handle"
          @mousedown="onResizeStart"
        >
          <div class="resize-line"></div>
        </div>

        <!-- 右侧对比视图 -->
        <div class="compare-area">
          <!-- 展开按钮 -->
          <a-button
            v-if="siderCollapsed"
            class="sider-expand-btn"
            type="text"
            size="small"
            @click="siderCollapsed = false"
          >
            <MenuUnfoldOutlined />
          </a-button>

          <!-- 空状态 -->
          <div v-if="!currentFile" class="empty-state">
            <div class="upload-drag-area">
              <a-upload-dragger
                :customRequest="handleDragUpload"
                :showUploadList="false"
                :multiple="true"
                accept=".pdf,.docx,.doc,.xls,.xlsx,.txt,.md,.csv,.pptx"
              >
                <p class="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
                <p class="ant-upload-hint">
                  支持 PDF、DOCX、XLS/XLSX、TXT、CSV、PPTX 等格式
                </p>
              </a-upload-dragger>
            </div>
          </div>

          <!-- 对比视图 -->
          <CompareView
            v-else
            ref="compareViewRef"
            :fileId="currentFile.id"
            :fileType="currentFile.file_type"
            :fileName="currentFile.filename"
            :markdownContent="currentFile.markdown_content || ''"
            :fileStatus="currentFile.status || ''"
            :engineResults="currentFile.engine_results || []"
            @save="onSaveMarkdown"
            @reconvert="onReconvert"
            @back="currentFile = null"
            @converted="onConverted"
            @openLLMConfig="showLLMConfigModal = true"
          />
        </div>
      </div>
    </a-layout-content>

    <!-- 软件说明弹窗 -->
    <a-modal v-model:open="showAboutModal" title="关于 TransAnything" :footer="null" :width="420" centered>
      <div class="about-content">
        <div class="about-logo">
          <SwapOutlined style="font-size: 48px; color: #1890ff" />
        </div>
        <h2 style="text-align: center; margin: 16px 0 4px">TransAnything</h2>
        <p style="text-align: center; color: rgba(0,0,0,0.45); margin-bottom: 20px">文件转Markdown平台</p>

        <a-descriptions :column="1" size="small" bordered>
          <a-descriptions-item label="开发者">Larf.chen</a-descriptions-item>
          <a-descriptions-item label="GitHub">
            <a href="https://github.com/chenzq1604/transanything" target="_blank">
              chenzq1604/transanything
            </a>
          </a-descriptions-item>
          <a-descriptions-item label="开源协议">AGPL-3.0 license</a-descriptions-item>
        </a-descriptions>

        <div style="margin-top: 16px; color: rgba(0,0,0,0.45); font-size: 12px; text-align: center">
          支持多种OCR和文档理解引擎，提供多引擎对比、差异分析等功能
        </div>
      </div>
    </a-modal>

    <!-- LLM配置弹窗 -->
    <LLMConfigModal v-model:open="showLLMConfigModal" />

    <!-- 环境检测弹窗 -->
    <EnvCheckModal v-model:open="showEnvCheckModal" />
  </a-layout>
</template>

<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { SwapOutlined, MenuFoldOutlined, MenuUnfoldOutlined, InboxOutlined, SettingOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import FileUpload from './components/FileUpload.vue'
import FileList from './components/FileList.vue'
import CompareView from './components/CompareView.vue'
import LLMConfigModal from './components/LLMConfigModal.vue'
import EnvCheckModal from './components/EnvCheckModal.vue'
import * as api from './api/index.js'

/** 当前查看的文件 */
const currentFile = ref(null)

/** 侧边栏折叠状态 */
const siderCollapsed = ref(false)

/** 侧边栏宽度 */
const siderWidth = ref(360)

/** 文件列表组件引用 */
const fileListRef = ref(null)

/** 对比视图组件引用 */
const compareViewRef = ref(null)

/** 软件说明弹窗 */
const showAboutModal = ref(false)

/** LLM配置弹窗 */
const showLLMConfigModal = ref(false)

/** 环境检测弹窗 */
const showEnvCheckModal = ref(false)

/**
 * 拖拽调整侧边栏宽度 - 鼠标按下
 * @param {MouseEvent} e - 鼠标事件
 */
function onResizeStart(e) {
  e.preventDefault()
  const startX = e.clientX
  const startWidth = siderWidth.value

  /**
   * 拖拽中 - 鼠标移动
   * @param {MouseEvent} moveEvent - 鼠标移动事件
   */
  function onMouseMove(moveEvent) {
    const diff = moveEvent.clientX - startX
    const newWidth = Math.min(Math.max(startWidth + diff, 200), 600)
    siderWidth.value = newWidth
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
 * 文件上传成功回调
 * 刷新文件列表
 */
function onFileUploaded() {
  fileListRef.value?.refresh()
}

/**
 * 拖拽上传处理
 * @param {Object} options - 上传选项
 */
async function handleDragUpload(options) {
  const { file, onSuccess, onError } = options
  try {
    const formData = new FormData()
    formData.append('files', file)
    await api.uploadFiles(formData)
    onSuccess && onSuccess()
    fileListRef.value?.refresh()
    message.success(`文件 ${file.name} 上传成功`)
  } catch (err) {
    onError && onError(err)
    message.error(`文件 ${file.name} 上传失败`)
  }
}

/**
 * 查看文件详情
 * @param {Object} file - 文件对象
 */
async function onViewFile(file) {
  try {
    const detail = await api.getFileDetail(file.id)
    currentFile.value = detail
  } catch (err) {
    message.error('获取文件详情失败：' + (err.message || '未知错误'))
  }
}

/**
 * 保存Markdown内容
 * @param {Object} payload - { fileId, content }
 */
async function onSaveMarkdown({ fileId, content }) {
  try {
    await api.saveMarkdown(fileId, content)
    message.success('保存成功')
  } catch (err) {
    message.error('保存失败：' + (err.message || '未知错误'))
  }
}

/**
 * 重新转换文件
 * 支持单引擎和批量多引擎转换，进度由CompareView轮询驱动
 * @param {Object} payload - { fileId, useLlmOptimize, engineType?, engineTypes? }
 *   - engineType: 单引擎模式，调用convertFile
 *   - engineTypes: 批量模式，调用batchConvert
 */
async function onReconvert({ fileId, useLlmOptimize, engineType, engineTypes }) {
  try {
    if (engineTypes && engineTypes.length > 0) {
      // 批量多引擎转换
      await api.batchConvert(fileId, engineTypes, useLlmOptimize)
    } else {
      // 单引擎转换
      await api.convertFile(fileId, useLlmOptimize, engineType)
    }
  } catch (err) {
    message.error('转换请求失败：' + (err.message || '未知错误'))
    // 转换请求失败时停止轮询
    compareViewRef.value?.stopReconverting()
  }
}

/**
 * 转换完成回调
 * 刷新文件详情以更新状态和引擎结果
 * @param {Object} payload - { fileId }
 */
async function onConverted({ fileId }) {
  try {
    const detail = await api.getFileDetail(fileId)
    currentFile.value = detail
    message.success('转换完成')
  } catch (err) {
    // 静默处理，CompareView已自行更新markdown内容
  }
}
</script>

<style scoped>
.about-content {
  padding: 8px 0;
}

.about-logo {
  text-align: center;
  margin-bottom: 8px;
}
</style>
