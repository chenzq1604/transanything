const { app, BrowserWindow, dialog } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn, exec, execSync } = require('child_process')

let mainWindow = null
let backendProcess = null

const BACKEND_PORT = 18030
const FRONTEND_PORT = 13010
const REQUIRED_CODE_VERSION = '20260614-v3'

/**
 * 检测后端是否已经在运行，且代码版本匹配
 * 如果后端运行的是旧代码，返回false以强制重启
 * @param {number} port - 要检测的端口
 * @returns {Promise<boolean>} 后端是否在运行且版本匹配
 */
function isBackendRunning(port) {
  return new Promise((resolve) => {
    const http = require('http')
    const req = http.get(`http://localhost:${port}/api/health`, (res) => {
      let data = ''
      res.on('data', chunk => data += chunk)
      res.on('end', () => {
        if (res.statusCode === 200) {
          try {
            const info = JSON.parse(data)
            if (info.code_version === REQUIRED_CODE_VERSION) {
              console.log(`[TransAnything] 后端已运行且版本匹配: ${info.code_version}`)
              resolve(true)
            } else {
              console.log(`[TransAnything] 后端版本不匹配: 期望=${REQUIRED_CODE_VERSION}, 实际=${info.code_version}, 需要重启`)
              resolve(false)
            }
          } catch {
            console.log('[TransAnything] 后端版本未知，需要重启')
            resolve(false)
          }
        } else {
          resolve(false)
        }
      })
    })
    req.on('error', () => resolve(false))
    req.setTimeout(3000, () => { req.destroy(); resolve(false) })
  })
}

/**
 * 获取后端backend目录路径
 * packaged时: process.resourcesPath/backend/ (extraResources)
 * 开发时: 项目根目录/backend/
 * @returns {string} 后端目录路径
 */
function getBackendDir() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend')
  }
  return path.resolve(__dirname, '..', '..', 'backend')
}

/**
 * 查找Python可执行文件
 * 自动探测conda环境中的python，无需硬编码路径
 * @returns {{exe: string, cwd: string}} Python路径和工作目录
 */
function findPython() {
  const backendDir = getBackendDir()

  // 1. 自动探测conda环境：通过conda命令查找
  try {
    const condaInfo = execSync('conda info --json', { encoding: 'utf-8', timeout: 5000 })
    const info = JSON.parse(condaInfo)
    if (info.envs_dirs && info.envs_dirs.length > 0) {
      for (const envsDir of info.envs_dirs) {
        const condaPython = path.join(envsDir, 'transanything', 'python.exe')
        if (fs.existsSync(condaPython)) {
          console.log(`[TransAnything] 找到conda Python: ${condaPython}`)
          return { exe: condaPython, cwd: backendDir }
        }
      }
    }
    // conda info可能直接返回envs列表
    if (info.envs && info.envs.length > 0) {
      for (const envPath of info.envs) {
        const condaPython = path.join(envPath, 'python.exe')
        if (fs.existsSync(condaPython) && envPath.includes('transanything')) {
          console.log(`[TransAnything] 找到conda Python: ${condaPython}`)
          return { exe: condaPython, cwd: backendDir }
        }
      }
    }
  } catch (e) {
    // conda命令不可用，继续尝试其他方式
  }

  // 2. 常见conda安装路径
  const commonPaths = [
    'D:\\ProgramData\\anaconda3\\envs\\transanything\\python.exe',
    'C:\\ProgramData\\anaconda3\\envs\\transanything\\python.exe',
    'C:\\Users\\' + (process.env.USERNAME || '') + '\\anaconda3\\envs\\transanything\\python.exe',
    'C:\\Users\\' + (process.env.USERNAME || '') + '\\miniconda3\\envs\\transanything\\python.exe',
  ]
  for (const p of commonPaths) {
    if (fs.existsSync(p)) {
      console.log(`[TransAnything] 找到Python: ${p}`)
      return { exe: p, cwd: backendDir }
    }
  }

  // 3. 系统PATH中的python
  console.log('[TransAnything] 未找到conda环境，使用系统Python')
  return { exe: 'python', cwd: backendDir }
}

/**
 * 启动Python后端进程
 * @param {number} port - 后端端口号
 */
function startBackend(port) {
  const { exe, cwd } = findPython()

  console.log(`[TransAnything] Python: ${exe}`)
  console.log(`[TransAnything] 工作目录: ${cwd}`)
  console.log(`[TransAnything] 后端端口: ${port}`)
  console.log(`[TransAnything] 后端目录存在: ${fs.existsSync(cwd)}`)

  const env = { ...process.env, BACKEND_PORT: String(port) }
  backendProcess = spawn(exe, ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', `--port=${port}`], {
    cwd: cwd,
    env: env,
    stdio: ['pipe', 'pipe', 'pipe']
  })

  backendProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })

  backendProcess.stderr.on('data', (data) => {
    const msg = data.toString().trim()
    if (msg.includes('ERROR') || msg.includes('WARNING') || msg.includes('Started') || msg.includes('Uvicorn') || msg.includes('Application startup complete')) {
      console.log(`[Backend] ${msg}`)
    }
  })

  backendProcess.on('error', (err) => {
    console.error(`[Backend] 启动失败: ${err.message}`)
  })

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] 进程退出: code=${code}`)
  })
}

/**
 * 等待后端就绪
 * @param {number} port - 后端端口号
 * @param {number} maxRetries - 最大重试次数
 * @param {number} interval - 重试间隔(ms)
 * @returns {Promise<void>}
 */
function waitForBackend(port, maxRetries = 60, interval = 2000) {
  return new Promise((resolve, reject) => {
    const http = require('http')
    let retries = 0

    function check() {
      http.get(`http://localhost:${port}/api/health`, (res) => {
        if (res.statusCode === 200) {
          console.log('[TransAnything] 后端就绪')
          resolve()
        } else {
          retry()
        }
      }).on('error', () => {
        retry()
      })

      function retry() {
        retries++
        if (retries >= maxRetries) {
          reject(new Error('后端启动超时'))
        } else {
          setTimeout(check, interval)
        }
      }
    }

    check()
  })
}

/**
 * 创建主窗口
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    title: 'TransAnything - 文件转Markdown平台',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  mainWindow.setMenuBarVisibility(false)

  if (app.isPackaged) {
    // packaged模式: 从asar内加载dist/index.html
    const indexPath = path.join(__dirname, '..', 'dist', 'index.html')
    console.log(`[TransAnything] 加载: ${indexPath}`)
    mainWindow.loadFile(indexPath)
  } else {
    // 开发模式: 连接Vite开发服务器
    const url = `http://localhost:${FRONTEND_PORT}`
    console.log(`[TransAnything] 加载: ${url}`)
    mainWindow.loadURL(url)
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

/**
 * 杀掉占用指定端口的进程（Windows）
 * @param {number} port - 要释放的端口号
 * @returns {Promise<boolean>} 是否杀掉了进程
 */
function killExistingBackend(port) {
  return new Promise((resolve) => {
    const { exec } = require('child_process')
    exec(`netstat -ano | findstr :${port} | findstr LISTENING`, (err, stdout) => {
      if (err || !stdout.trim()) {
        resolve(false)
        return
      }
      const lines = stdout.trim().split('\n')
      const pids = new Set()
      for (const line of lines) {
        const parts = line.trim().split(/\s+/)
        const pid = parts[parts.length - 1]
        if (pid && /^\d+$/.test(pid)) {
          pids.add(pid)
        }
      }
      if (pids.size === 0) {
        resolve(false)
        return
      }
      console.log(`[TransAnything] 发现旧后端进程 PID: ${[...pids].join(', ')}, 正在终止...`)
      for (const pid of pids) {
        exec(`taskkill /PID ${pid} /T /F`, (killErr) => {
          if (killErr) {
            console.log(`[TransAnything] 终止进程 ${pid} 失败: ${killErr.message}`)
          } else {
            console.log(`[TransAnything] 已终止进程 ${pid}`)
          }
        })
      }
      // 等待进程退出
      setTimeout(() => resolve(true), 2000)
    })
  })
}

/**
 * 应用启动
 * 流程：检测已有后端 → 杀掉旧版本 → 启动后端 → 创建窗口
 */
app.whenReady().then(async () => {
  // 1. 检测已有后端是否在运行且版本匹配
  const running = await isBackendRunning(BACKEND_PORT)
  if (running) {
    console.log(`[TransAnything] 后端已在端口 ${BACKEND_PORT} 运行且版本匹配`)
    createWindow()
    return
  }

  // 2. 后端版本不匹配或未运行，杀掉旧进程
  const killed = await killExistingBackend(BACKEND_PORT)
  if (killed) {
    console.log('[TransAnything] 已终止旧后端进程，等待端口释放...')
    await new Promise(r => setTimeout(r, 2000))
  }

  // 3. 启动后端
  console.log(`[TransAnything] 启动后端，端口: ${BACKEND_PORT}`)
  startBackend(BACKEND_PORT)

  try {
    // 4. 等待后端就绪
    await waitForBackend(BACKEND_PORT, 60, 2000)
    createWindow()
  } catch (err) {
    console.error('[TransAnything] 后端未就绪')
    const result = dialog.showMessageBoxSync({
      type: 'warning',
      title: '后端服务未启动',
      message: '无法启动Python后端服务',
      detail: '请先在终端中启动后端：\n\n' +
        '  conda activate transanything\n' +
        '  cd backend目录\n' +
        `  python -m uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT}\n\n` +
        '点击"继续"将打开前端（功能受限），点击"退出"关闭应用。',
      buttons: ['继续', '退出'],
      defaultId: 1,
      noLink: true
    })

    if (result === 1) {
      app.quit()
    } else {
      createWindow()
    }
  }
})

app.on('window-all-closed', () => {
  app.quit()
})

app.on('before-quit', () => {
  if (backendProcess) {
    console.log('[TransAnything] 停止后端进程')
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/PID', String(backendProcess.pid), '/T', '/F'], { stdio: 'ignore' })
      } else {
        backendProcess.kill()
      }
    } catch (e) {
      // ignore
    }
    backendProcess = null
  }
})

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow()
  }
})
