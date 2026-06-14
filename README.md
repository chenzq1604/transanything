# TransAnything

多引擎文件转 Markdown 平台，支持 PDF / Word / Excel / 图片等多种格式，提供 6 种识别引擎并行对比，内置 LLM 智能优化，可编辑导出。

## 功能特性

- **多引擎并行对比** — 同一文件同时使用 2~6 个引擎识别，结果并排展示，支持差异对比（Diff）
- **PDF 区域联动** — 鼠标悬停 PDF 原文区域，右侧 Markdown 自动高亮定位对应内容
- **LLM 智能优化** — 支持接入 OpenAI 兼容 API，对识别结果进行智能纠错和格式优化
- **LLM 图片识别** — 独立引擎，使用多模态大模型直接识别 PDF 页面图片
- **Markdown 编辑** — 内置编辑器，支持源码/预览/分屏三种模式，可实时编辑并保存
- **环境检测** — 自动检测 GPU、Python 依赖包安装状态，不可用的引擎自动禁用
- **Electron 桌面端** — 打包为 Windows NSIS 安装包，支持自定义安装目录、桌面快捷方式

## 支持的文件格式

| 格式 | 扩展名 | 可用引擎 |
|------|--------|---------|
| PDF | `.pdf` | MarkItDown, PaddleOCR, PP-StructureV3, PP-ChatOCRv4, MinerU, LLM图片识别 |
| Word | `.docx` `.doc` | MarkItDown |
| Excel | `.xlsx` `.xls` | MarkItDown |
| 文本 | `.txt` `.md` `.csv` | 纯文本读取 |
| 其他 | `.pptx` `.html` 等 | MarkItDown |

## 识别引擎

| 引擎 | 说明 | GPU 要求 | 支持区域联动 |
|------|------|---------|------------|
| **MarkItDown** | 微软开源文件转换库，轻量快速 | 无 | 否 |
| **PaddleOCR V6** | 百度飞桨 OCR，文字识别精度高 | 需要 NVIDIA GPU | 否 |
| **PP-StructureV3** | 百度飞桨版面分析，支持表格/图片/标题识别 | 需要 NVIDIA GPU | 是 |
| **PP-ChatOCRv4** | 百度飞桨智能 OCR，结合大模型理解 | 需要 NVIDIA GPU | 是 |
| **MinerU** | 开源文档解析，版面分析能力强 | 需要 NVIDIA GPU | 是 |
| **LLM 图片识别** | 使用多模态大模型识别 PDF 页面 | 无（需配置 API） | 否 |

> PaddleOCR / PP-Structure / PP-ChatOCR / MinerU 需要 NVIDIA GPU + CUDA 环境，无 GPU 的机器自动禁用。

## 技术架构

```
TransAnything
├── frontend/                    # 前端 (Vue 3 + Ant Design Vue)
│   ├── src/
│   │   ├── api/                 # API 请求层
│   │   ├── components/
│   │   │   ├── App.vue          # 主应用（文件列表、上传、引擎选择）
│   │   │   ├── CompareView.vue  # 多引擎对比视图（核心组件）
│   │   │   ├── PdfViewer.vue    # PDF 预览 + 区域联动
│   │   │   ├── MdEditor.vue     # Markdown 编辑器（源码/预览/分屏）
│   │   │   ├── LLMConfigModal.vue   # LLM 配置弹窗
│   │   │   └── EnvCheckModal.vue    # 环境检测弹窗
│   │   └── main.js
│   ├── electron/
│   │   └── main.js              # Electron 主进程（后端启停、窗口管理）
│   ├── vite.config.js           # Vite 配置（端口 13010，代理到 18030）
│   └── package.json
├── backend/                     # 后端 (Python FastAPI)
│   ├── app/
│   │   ├── main.py              # FastAPI 入口（端口 18030）
│   │   ├── config.py            # 配置管理（pydantic-settings）
│   │   ├── api/
│   │   │   ├── upload.py        # 文件上传
│   │   │   ├── convert.py       # 转换 API（单引擎/批量/多引擎）
│   │   │   ├── files.py         # 文件管理（列表/删除/结果查询）
│   │   │   ├── llm_config.py    # LLM 配置 API（读取/保存/测试）
│   │   │   └── engine_check.py  # 环境检测 API
│   │   ├── engines/
│   │   │   ├── base.py          # 引擎基类
│   │   │   ├── factory.py       # 引擎工厂（根据类型创建实例）
│   │   │   ├── markitdown_engine.py
│   │   │   ├── paddleocr_engine.py
│   │   │   ├── ppstructure_engine.py
│   │   │   ├── ppchatocr_engine.py
│   │   │   ├── mineru_engine.py
│   │   │   ├── pdf_engine.py    # PyMuPDF 引擎
│   │   │   ├── docx_engine.py
│   │   │   ├── xls_engine.py
│   │   │   └── txt_engine.py
│   │   ├── llm/
│   │   │   ├── client.py        # LLM 客户端（OpenAI 兼容）
│   │   │   └── prompts.py       # 提示词模板
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic 数据模型
│   │   └── services/
│   │       ├── convert_service.py  # 转换服务（多引擎并行调度）
│   │       └── progress.py         # 进度管理（SSE 推送）
│   ├── requirements.txt
│   └── environment.yaml         # Conda 环境导出
├── start_dev.py                 # 一键启动脚本（开发模式）
└── .gitignore
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Conda（推荐）
- NVIDIA GPU + CUDA（可选，用于 PaddleOCR/PP-Structure/PP-ChatOCR/MinerU）

### 1. 创建 Conda 环境

```bash
conda env create -f environment.yaml
conda activate transanything
```

或手动安装：

```bash
conda create -n transanything python=3.12
conda activate transanything
pip install -r backend/requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
```

### 3. 启动开发服务器

**方式一：一键启动**

```bash
conda activate transanything
python start_dev.py
```

**方式二：分别启动**

```bash
# 终端1：启动后端（端口 18030）
conda activate transanything
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 18030

# 终端2：启动前端（端口 13010）
cd frontend
npm run dev
```

访问 http://localhost:13010

### 4. Electron 开发模式

```bash
cd frontend
npm run electron:dev
```

## 打包发布

```bash
cd frontend
npm run build
python D:\source\trace\shellscript\transanything\2026-06-14\manual_build.py
```

生成的安装包位于 `D:\transanything-build\TransAnything-Setup-1.0.0.exe`。

> 目标机器需要预装 `transanything` conda 环境。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传文件 |
| GET | `/api/files` | 获取文件列表 |
| POST | `/api/convert/{file_id}` | 触发单引擎转换 |
| POST | `/api/convert/{file_id}/batch` | 触发多引擎批量转换 |
| GET | `/api/convert/{file_id}/progress` | SSE 转换进度推送 |
| GET | `/api/convert/{file_id}/results` | 获取所有引擎结果 |
| PUT | `/api/convert/{file_id}/save` | 保存编辑后的 Markdown |
| DELETE | `/api/files/{file_id}` | 删除文件及结果 |
| GET | `/api/llm-config` | 获取 LLM 配置 |
| PUT | `/api/llm-config` | 保存 LLM 配置 |
| POST | `/api/llm-config/test` | 测试 LLM 连接 |
| POST | `/api/llm-config/test-vision` | 测试 LLM 图片识别 |
| GET | `/api/engine-check` | 环境检测（GPU/依赖） |
| GET | `/api/health` | 健康检查 |

## LLM 配置

支持任何 OpenAI 兼容 API，通过前端界面配置（不硬编码密钥）：

1. 点击右上角 LLM 配置按钮
2. 填写 API Key、Base URL、模型名称
3. 点击"测试连接"验证可用性
4. 配置持久化到 `llm_config.json`，重启自动加载

## 核心交互

### 多引擎对比

- 下拉选择默认引擎，点击"识别"触发单引擎转换
- 点击"添加引擎"可增加 2~6 个引擎列并排对比
- 点击"识别全部"对当前所有引擎列并行转换
- 支持列隐藏/恢复、拖拽排序、拖拽调整列宽

### PDF 区域联动

- PP-StructureV3、PP-ChatOCRv4、MinerU 引擎支持区域联动
- 鼠标悬停 PDF 原文区域，右侧 Markdown 自动高亮并滚动到对应内容
- 区域信息通过 `<!-- REGIONS:... -->` 注释嵌入 Markdown

### Diff 差异对比

- 点击"差异对比"按钮，选择两个引擎进行逐行 Diff
- 基于 LCS（最长公共子序列）算法，新增/删除/修改行不同颜色标注

## 许可证

AGPL-3.0
