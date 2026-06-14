/**
 * Electron预加载脚本
 * 通过contextBridge安全地将后端端口注入到前端页面
 */
const { contextBridge } = require('electron')

// main.js在创建窗口时通过process.argv或环境变量传递端口
// 使用--backend-port参数传递
const args = process.argv
let backendPort = 8000
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--backend-port' && args[i + 1]) {
    backendPort = parseInt(args[i + 1], 10)
    break
  }
}

contextBridge.exposeInMainWorld('__BACKEND_PORT__', backendPort)
console.log(`[Preload] 注入后端端口: ${backendPort}`)
