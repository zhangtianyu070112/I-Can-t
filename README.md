# 智学资源体（源码包）

本目录是可复现构建的完整源码包，主程序采用 FastAPI + Vue 3。源码、依赖锁文件、测试脚本、空敏感配置模板、最小演示数据和路演版前端构建文件均已包含；依赖目录不随交付 ZIP 提交。

## 目录说明

- `backend/`：FastAPI 后端源码、单元测试与最小演示数据。
- `frontend-vue/`：Vue 3 前端源码、静态资源、端到端测试和 `package-lock.json`。
- `tests/`：后端验收与集成流程脚本。
- `scripts/`：自动化验收脚本。
- `start-roadshow.bat` / `start-roadshow.ps1`：单端口现场路演启动入口。
- `安装依赖.ps1`：安装 Python 和 Node.js 依赖。
- `start-dev.ps1` / `启动源码.bat`：启动源码开发环境。
- `stop-dev.ps1`：停止本项目使用的本地端口。

## 环境要求

- Windows 10/11
- Python 3.11 或更高版本
- Node.js 18 或更高版本（附带 npm）

## 首次安装

在本目录打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\安装依赖.ps1
```

安装脚本会执行：

```powershell
python -m pip install -r .\backend\requirements.txt
Push-Location .\frontend-vue
npm ci
Pop-Location
```

## 启动

双击 `启动源码.bat`，或在 PowerShell 中运行：

```powershell
.\start-dev.ps1
```

启动后访问：

- 前端：`http://127.0.0.1:5173`
- 后端接口文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

演示登录：

- 推荐点击“使用预置数据进入路演”，直接查看随包附带的 `demo` 学习记录与资源。
- 手机号：任意 11 位数字
- 密码：`demo123`
- 验证码：按页面显示输入（初始演示值通常为 `2VV3`）
- 普通测试登录会创建独立学习者标识，可在“用户设置”查看和修改。

## 现场路演启动

先安装 Python 依赖；若 `frontend-vue/dist/index.html` 不存在，再执行 `npm ci` 和 `npm run build`。随后双击 `start-roadshow.bat`，浏览器会自动打开单端口正式页面；脚本从 8000–8010 中选择空闲端口，不会结束其他程序。前端和 API 共用同一地址，刷新 `/profile` 等子页面也能正常打开。

未配置外部模型和语音服务时，预置画像、资源、练习、路径、评估与本地资料问答可演示；实时语音数字人和新的模型生成任务仍需相应服务配置。页面会明确提示缺少配置，不会伪装成已经完成的实时生成。

## 第三方服务配置

默认配置不包含任何真实密钥。基础页面、演示数据与本地流程可直接运行；需要调用外部大模型、图像生成或数字人服务时：

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

然后仅在本机填写相应配置。请勿把含真实密钥的 `.env` 对外提交。

## 构建与验收

```powershell
.\scripts\run-all-tests.ps1 -SkipInstall
```

也可按 [README_TESTING.md](README_TESTING.md) 分项执行。前端生产构建命令为：

```powershell
Push-Location .\frontend-vue
npm run build
Pop-Location
```

原作品包中的 EXE 是旧版构建；本次修复请使用源码目录的 `start-roadshow.bat`。如需重新制作免安装 EXE，应以修复后的源码重新打包后再验收。

## 提交安全说明

路演交付 ZIP 未包含真实 `.env`、版本库历史、依赖目录、缓存、日志、个人运行数据、学校标识或参赛人员信息。演示数据仅使用通用的 `demo` 标识。
