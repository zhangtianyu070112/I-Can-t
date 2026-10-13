# 测试与验收说明

以下命令均从源码包根目录执行。

## 一键测试

首次运行先执行 `.\安装依赖.ps1`，然后：

```powershell
.\scripts\run-all-tests.ps1 -SkipInstall
```

脚本使用独立临时数据目录启动前后端并执行：

1. 后端单元及回归测试；
2. 前端类型检查与生产构建；
3. Playwright 当前路演链路测试（登录、主页面、本地答疑、响应式布局和按钮操作）。

脚本不会结束运行前已占用 8000 或 5173 端口的程序，端口被占用时会提示先关闭该程序。

如本机没有可用的 Edge/Playwright 浏览器，可先跳过 E2E：

```powershell
.\scripts\run-all-tests.ps1 -SkipInstall -SkipE2E
```

## 分项执行

后端服务启动后，可按需执行历史验收脚本。这两份脚本仍包含旧版“无密钥也生成新资源/实时答疑”的预期，当前无模型配置时不会全部通过：

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python .\tests\backend_acceptance.py http://127.0.0.1:8000
python .\tests\integration_flow.py http://127.0.0.1:8000
```

后端单元测试：

```powershell
Push-Location .\backend
$env:PYTHONPATH = (Get-Location).Path
python -m unittest discover -s tests -p "test*.py" -v
Pop-Location
```

前端检查与构建：

```powershell
Push-Location .\frontend-vue
npm run check
npm run lint
npm run build
Pop-Location
```

前端 E2E：

```powershell
Push-Location .\frontend-vue
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:5173"
npm run test:roadshow -- --project=msedge --workers=1
Pop-Location
```

`npm run test:e2e` 会运行目录内所有历史布局和模型服务实验脚本；其中部分断言针对旧界面，不能作为当前路演版的默认验收门槛。

## 验收重点

- 登录页能够进入系统；
- 所有主导航页面可访问且无白屏；
- 用户画像、资源工坊、练习诊断、知识中枢、路径推送、智能辅导和评估进化页面可正常加载；
- 无外部密钥时，预置资源与本地资料检索可用，新模型生成和实时音视频明确提示需要配置；
- 前端生产构建和后端自动化测试通过。
