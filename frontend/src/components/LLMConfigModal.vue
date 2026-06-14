<template>
  <a-modal
    v-model:open="visible"
    title="LLM 大模型配置"
    :width="520"
    :footer="null"
    :destroyOnClose="true"
    @cancel="handleClose"
  >
    <a-form :model="formState" layout="vertical" class="llm-config-form">
      <a-form-item label="API Key" required>
        <a-input-password
          v-model:value="formState.api_key"
          placeholder="输入LLM API Key"
          autocomplete="off"
        />
      </a-form-item>

      <a-form-item label="Base URL" required>
        <a-input
          v-model:value="formState.base_url"
          placeholder="如 https://api.openai.com/v1"
        />
      </a-form-item>

      <a-form-item label="模型名称" required>
        <a-input
          v-model:value="formState.model"
          placeholder="如 gpt-4o、doubao-vision-pro 等"
        />
        <div class="form-hint">
          图片识别引擎需要支持多模态的模型（如 GPT-4o、Claude-3.5-Sonnet、doubao-vision-pro 等）
        </div>
      </a-form-item>

      <a-form-item>
        <a-space>
          <a-button @click="handleTestConnection" :loading="testingConnection">
            <ApiOutlined /> 测试连接
          </a-button>
          <a-button @click="handleTestVision" :loading="testingVision" :disabled="!connectionOk">
            <EyeOutlined /> 测试图片识别
          </a-button>
        </a-space>

        <!-- 测试结果 -->
        <div v-if="testResult" class="test-result" :class="testResult.success ? 'test-success' : 'test-fail'">
          <CheckCircleOutlined v-if="testResult.success" />
          <CloseCircleOutlined v-else />
          {{ testResult.message }}
        </div>
      </a-form-item>

      <a-form-item>
        <a-space>
          <a-button type="primary" @click="handleSave" :loading="saving">
            保存配置
          </a-button>
          <a-button @click="handleClose">取消</a-button>
        </a-space>
      </a-form-item>
    </a-form>

    <!-- 常用模型配置参考 -->
    <a-divider>常用模型配置参考</a-divider>
    <div class="model-presets">
      <div class="preset-item" v-for="preset in MODEL_PRESETS" :key="preset.name" @click="applyPreset(preset)">
        <div class="preset-name">{{ preset.name }}</div>
        <div class="preset-desc">{{ preset.desc }}</div>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ApiOutlined, EyeOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import * as api from '../api/index.js'

/** 弹窗可见状态 */
const visible = defineModel('open', { type: Boolean, default: false })

/** 表单状态 */
const formState = reactive({
  api_key: '',
  base_url: '',
  model: '',
})

/** 测试状态 */
const testingConnection = ref(false)
const testingVision = ref(false)
const saving = ref(false)
const connectionOk = ref(false)
const testResult = ref(null)

/** 常用模型预设 */
const MODEL_PRESETS = [
  {
    name: '火山方舟 - 豆包视觉',
    desc: 'doubao-vision-pro，支持图片识别',
    base_url: 'https://ark.cn-beijing.volces.com/api/v3',
    model: 'doubao-vision-pro-32k',
  },
  {
    name: '火山方舟 - 豆包文本',
    desc: 'doubao-pro，仅文本优化',
    base_url: 'https://ark.cn-beijing.volces.com/api/v3',
    model: 'doubao-pro-32k',
  },
  {
    name: 'OpenAI - GPT-4o',
    desc: '支持图片识别，需要海外代理',
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4o',
  },
  {
    name: 'DeepSeek - Chat',
    desc: '仅文本优化，性价比高',
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
  },
]

/** 监听弹窗打开，加载当前配置 */
watch(visible, async (val) => {
  if (val) {
    testResult.value = null
    connectionOk.value = false
    try {
      const config = await api.getLLMConfig()
      formState.api_key = config.api_key || ''
      formState.base_url = config.base_url || ''
      formState.model = config.model || ''
    } catch (e) {
      console.error('获取LLM配置失败:', e)
    }
  }
})

/** 应用预设配置 */
function applyPreset(preset) {
  formState.base_url = preset.base_url
  formState.model = preset.model
  message.info(`已选择预设: ${preset.name}，请填写API Key后保存`)
}

/** 测试连接 */
async function handleTestConnection() {
  testingConnection.value = true
  testResult.value = null
  try {
    // 先保存配置再测试
    await api.saveLLMConfig({
      api_key: formState.api_key,
      base_url: formState.base_url,
      model: formState.model,
    })
    const result = await api.testLLMConnection()
    connectionOk.value = result.success
    testResult.value = result
  } catch (e) {
    connectionOk.value = false
    testResult.value = { success: false, message: `测试失败: ${e.message}` }
  } finally {
    testingConnection.value = false
  }
}

/** 测试图片识别 */
async function handleTestVision() {
  testingVision.value = true
  testResult.value = null
  try {
    const result = await api.testLLMVision()
    testResult.value = result
  } catch (e) {
    testResult.value = { success: false, message: `测试失败: ${e.message}` }
  } finally {
    testingVision.value = false
  }
}

/** 保存配置 */
async function handleSave() {
  if (!formState.api_key || !formState.base_url || !formState.model) {
    message.warning('请填写完整的配置信息')
    return
  }
  saving.value = true
  try {
    await api.saveLLMConfig({
      api_key: formState.api_key,
      base_url: formState.base_url,
      model: formState.model,
    })
    message.success('LLM配置已保存')
    visible.value = false
  } catch (e) {
    message.error(`保存失败: ${e.message}`)
  } finally {
    saving.value = false
  }
}

/** 关闭弹窗 */
function handleClose() {
  visible.value = false
}
</script>

<style scoped>
.llm-config-form {
  margin-top: 8px;
}

.form-hint {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
  margin-top: 4px;
}

.test-result {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
}

.test-success {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.test-fail {
  background: #fff2f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.model-presets {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.preset-item {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.preset-item:hover {
  border-color: #1890ff;
  background: #e6f7ff;
}

.preset-name {
  font-weight: 500;
  font-size: 13px;
  color: #1890ff;
}

.preset-desc {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
  margin-top: 2px;
}
</style>
