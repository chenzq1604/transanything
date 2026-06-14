<template>
  <a-button type="primary" @click="triggerUpload" :loading="uploading">
    <UploadOutlined />
    <span style="margin-left: 6px">上传文件</span>
  </a-button>
  <input
    ref="fileInputRef"
    type="file"
    :accept="acceptTypes"
    multiple
    style="display: none"
    @change="handleFileChange"
  />
</template>

<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import * as api from '../api/index.js'

const emit = defineEmits(['uploaded'])

/** 上传中状态 */
const uploading = ref(false)

/** 文件输入框引用 */
const fileInputRef = ref(null)

/** 支持的文件类型 */
const acceptTypes = '.pdf,.docx,.doc,.xls,.xlsx,.txt,.md,.csv,.pptx'

/**
 * 触发文件选择
 */
function triggerUpload() {
  fileInputRef.value?.click()
}

/**
 * 文件选择变更处理
 * @param {Event} event - 文件选择事件
 */
async function handleFileChange(event) {
  const files = event.target.files
  if (!files || files.length === 0) return

  uploading.value = true
  try {
    const formData = new FormData()
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i])
    }
    await api.uploadFiles(formData)
    message.success(`成功上传 ${files.length} 个文件`)
    emit('uploaded')
  } catch (err) {
    message.error('文件上传失败：' + (err.message || '未知错误'))
  } finally {
    uploading.value = false
    // 清空input值，允许重复选择同一文件
    if (fileInputRef.value) {
      fileInputRef.value.value = ''
    }
  }
}
</script>
