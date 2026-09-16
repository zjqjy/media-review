# media-review 安装器：装 skill 到 ~/.claude/skills/，检查 Python 依赖
# 用法：powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$skillSrc = Join-Path $PSScriptRoot "skill\media-review"
$skillDst = Join-Path $HOME ".claude\skills\media-review"

Write-Host "== media-review 安装 ==" -ForegroundColor Cyan

# 1. Python 检查
try {
    $pyVersion = python --version 2>&1
    Write-Host "[OK] Python: $pyVersion"
} catch {
    Write-Host "[FAIL] 没找到 python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

# 2. 依赖：收集窗需要 Pillow（fetch_bili.py 零依赖）
python -c "import PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[..] 安装 Pillow..."
    python -m pip install pillow
}
Write-Host "[OK] 依赖就绪"

# 3. 复制 skill（镜像：删掉旧内容再拷，改代码后重跑即可更新）
if (Test-Path $skillDst) { Remove-Item $skillDst -Recurse -Force }
New-Item -ItemType Directory -Path $skillDst -Force | Out-Null
Copy-Item "$skillSrc\*" $skillDst -Recurse -Force
Write-Host "[OK] skill 已安装到 $skillDst"

# 4. 配置指引
Write-Host ""
Write-Host "== 剩下一步 ==" -ForegroundColor Yellow
Write-Host "1. 打开 vault: 20_自媒体/复盘/_config_local.example.json"
Write-Host "2. 复制为 _config_local.json（同目录），填入 SESSDATA："
Write-Host "   B站网页 F12 → Application → Cookies → bilibili.com → SESSDATA"
Write-Host "3. 在 Claude Code 里喊 /media-review 试跑"
