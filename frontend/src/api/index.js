import axios from 'axios'

/**
 * API基础配置
 * 开发环境：通过Vite代理转发到后端（端口18030）
 * Electron生产环境：后端固定端口18030
 */
const isElectron = typeof window !== 'undefined' && window.navigator.userAgent.includes('Electron')

const BACKEND_PORT = 18030
const API_BASE = isElectron ? `http://localhost:${BACKEND_PORT}/api` : '/api'

const request = axios.create({
  baseURL: API_BASE,
  timeout: 300000,
})

/**
 * 请求拦截器
 * 可在此添加认证Token等
 */
request.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error)
)

/**
 * 响应拦截器
 * 统一处理错误响应
 */
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.detail || error.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

/**
 * 上传文件
 * @param {FormData} formData - 包含文件的FormData对象
 * @returns {Promise<Array>} 上传结果列表
 */
export function uploadFiles(formData) {
  return request.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/**
 * 获取文件列表
 * @returns {Promise<Array>} 文件列表
 */
export async function getFileList() {
  const res = await request.get('/files')
  // 后端返回 {files: [...], total: N}，提取files数组
  return res.files || res
}

/**
 * 触发文件转换
 * @param {string|number} fileId - 文件ID
 * @param {boolean} useLlmOptimize - 是否使用LLM优化
 * @param {string} engineType - 引擎类型：pymupdf/markitdown/paddleocr/llm
 * @returns {Promise<Object>} 转换结果
 */
export function convertFile(fileId, useLlmOptimize = true, engineType = 'auto') {
  return request.post(`/convert/${fileId}`, null, {
    params: { use_llm_optimize: useLlmOptimize, engine_type: engineType },
  })
}

/**
 * 获取可用引擎列表
 * @param {string} fileType - 文件类型
 * @returns {Promise<Object>} 引擎列表
 */
export function getEngines(fileType = '.pdf') {
  return request.get('/engines', { params: { file_type: fileType } })
}

/**
 * 获取文件详情（含Markdown内容）
 * 后端返回 {file_info: {...}, markdown_content: "...", engine_results: [...]}
 * 合并为扁平结构方便前端使用
 * @param {string|number} fileId - 文件ID
 * @returns {Promise<Object>} 文件详情
 */
export async function getFileDetail(fileId) {
  const res = await request.get(`/files/${fileId}`)
  if (res.file_info) {
    return {
      ...res.file_info,
      markdown_content: res.markdown_content || '',
      engine_results: res.engine_results || [],
    }
  }
  return res
}

/**
 * 保存编辑后的Markdown
 * @param {string|number} fileId - 文件ID
 * @param {string} content - Markdown内容
 * @returns {Promise<Object>} 保存结果
 */
export function saveMarkdown(fileId, content) {
  return request.put(`/convert/${fileId}/save`, { content })
}

/**
 * 下载Markdown文件
 * @param {string|number} fileId - 文件ID
 * @returns {string} 下载URL
 */
export function downloadMarkdown(fileId) {
  return `${API_BASE}/files/${fileId}/download`
}

/**
 * 删除文件
 * @param {string|number} fileId - 文件ID
 * @returns {Promise<Object>} 删除结果
 */
export function deleteFile(fileId) {
  return request.delete(`/files/${fileId}`)
}

/**
 * 获取原始文件预览URL
 * @param {string|number} fileId - 文件ID
 * @returns {string} 预览URL
 */
export function getFilePreviewUrl(fileId) {
  return `${API_BASE}/files/${fileId}/preview`
}

/**
 * 获取Excel文件数据（用于前端表格渲染）
 * @param {string|number} fileId - 文件ID
 * @returns {Promise<Object>} Excel数据
 */
export function getExcelData(fileId) {
  return request.get(`/files/${fileId}/excel-data`)
}

/**
 * 获取文本文件内容
 * @param {string|number} fileId - 文件ID
 * @returns {Promise<string>} 文本内容
 */
export function getTxtContent(fileId) {
  return request.get(`/files/${fileId}/text-content`)
}

/**
 * 获取转换进度（轮询方式）
 * @param {string|number} fileId - 文件ID
 * @returns {Promise<Object>} 进度信息
 */
export function getConvertProgress(fileId) {
  return request.get(`/convert/${fileId}/progress`)
}

/**
 * 批量转换（多引擎并行）
 * @param {string|number} fileId - 文件ID
 * @param {string[]} engineTypes - 引擎类型列表，如 ['markitdown', 'paddleocr']
 * @param {boolean} useLlmOptimize - 是否使用LLM优化，默认false
 * @returns {Promise<Object>} 批量转换结果，含file_id、engine_results、status
 */
export function batchConvert(fileId, engineTypes, useLlmOptimize = false) {
  return request.post(`/convert/${fileId}/batch`, {
    engine_types: engineTypes,
    use_llm_optimize: useLlmOptimize,
  })
}

/**
 * 获取文件所有引擎结果
 * @param {string|number} fileId - 文件ID
 * @returns {Promise<Object>} 引擎结果列表，含file_id和engine_results数组
 */
export function getEngineResults(fileId) {
  return request.get(`/files/${fileId}/engines`)
}

/**
 * 保存指定引擎的Markdown内容
 * @param {string|number} fileId - 文件ID
 * @param {string} engineType - 引擎类型标识
 * @param {string} content - Markdown内容
 * @returns {Promise<Object>} 保存结果
 */
export function saveEngineMarkdown(fileId, engineType, content) {
  return request.put(`/files/${fileId}/engines/${engineType}/save`, { content })
}

/**
 * 获取LLM配置
 * @returns {Promise<Object>} LLM配置信息
 */
export function getLLMConfig() {
  return request.get('/llm/config')
}

/**
 * 保存LLM配置
 * @param {Object} config - LLM配置 {api_key, base_url, model}
 * @returns {Promise<Object>} 保存后的配置
 */
export function saveLLMConfig(config) {
  return request.post('/llm/config', config)
}

/**
 * 测试LLM连接
 * @returns {Promise<Object>} 测试结果 {success, message}
 */
export function testLLMConnection() {
  return request.post('/llm/test-connection')
}

/**
 * 测试LLM图片识别能力
 * @returns {Promise<Object>} 测试结果 {success, message, supports_vision}
 */
export function testLLMVision() {
  return request.post('/llm/test-vision')
}

/**
 * 获取LLM状态（轻量级，用于tooltip）
 * @returns {Promise<Object>} 状态信息 {connection_ok, supports_vision, model, base_url}
 */
export function getLLMStatus() {
  return request.get('/llm/status')
}

/**
 * 检测所有引擎环境依赖
 * @returns {Promise<Object>} {engines: [{type, name, description, available, reason, requires_gpu, dependencies}]}
 */
export function checkEngines() {
  return request.get('/engines/check')
}
