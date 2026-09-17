# media-review 自媒体 skill 集安装器：装全部 skill 到 ~/.claude/skills/，检查 Python 依赖
# 用法：powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$skills = @("media-review", "media-cut")

Write-Host "== media-review skill 集安装 ==" -ForegroundColor Cyan

# 1. Python 检查
try {
    $pyVersion = python --version 2>&1
    Write-Host "[OK] Python: $pyVersion"
} catch {
    Write-Host "[FAIL] 没找到 python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

# 2. 依赖：收集窗需要 Pillow，扫码登录需要 qrcode（fetch 取数本身零依赖）
python -c "import PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[..] 安装 Pillow..."
    python -m pip install pillow
}
python -c "import qrcode" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[..] 安装 qrcode..."
    python -m pip install qrcode
}
# media-cut 的 silence_trim 需要 ffmpeg：PATH 或 imageio_ffmpeg 自带二进制（脚本自动发现两者）
ffmpeg -version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    python -c "import imageio_ffmpeg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[..] 未找到 ffmpeg，安装 imageio-ffmpeg（随包二进制）..."
        python -m pip install imageio-ffmpeg
    }
}
Write-Host "[OK] 依赖就绪"

# 3. 复制 skill（镜像：删掉旧内容再拷，改代码后重跑即可更新）
foreach ($skill in $skills) {
    $skillSrc = Join-Path $PSScriptRoot "skill\$skill"
    $skillDst = Join-Path $HOME ".claude\skills\$skill"
    if (Test-Path $skillDst) { Remove-Item $skillDst -Recurse -Force }
    New-Item -ItemType Directory -Path $skillDst -Force | Out-Null
    Copy-Item "$skillSrc\*" $skillDst -Recurse -Force
    Write-Host "[OK] $skill 已安装到 $skillDst"
}

# 4. 配置指引
Write-Host ""
Write-Host "== 剩下一步 ==" -ForegroundColor Yellow
Write-Host "1. 打开 vault: 20_自媒体/复盘/_config_local.example.json"
Write-Host "2. 复制为 _config_local.json（同目录），填入 SESSDATA："
Write-Host "   B站网页 F12 → Application → Cookies → bilibili.com → SESSDATA"
Write-Host "3. 在 Claude Code 里喊 /media-review 试跑"
