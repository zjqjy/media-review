# media-review 自媒体 skill 集安装器：装 media 门面技能到 ~/.claude/skills/，检查 Python 依赖
# 用法：powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$skills = @("media")

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

# media-cut/cut 子技能依赖
python -c "import pyJianYingDraft" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[..] 安装 pyJianYingDraft（剪映草稿直出）..."
    python -m pip install pyJianYingDraft
}
python -c "import funasr" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[..] 安装 funasr（转录；torch 级依赖，需几分钟）..."
    python -m pip install funasr
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] funasr 安装失败（国内网络建议：开 VPN 装包，装完关掉下模型）" -ForegroundColor Yellow
    }
}
# torchaudio 是 funasr 的 fbank 后端：必须与已装 torch 同版本，--no-deps 防止 pip 动 torch
$torchVer = python -c "import torch; print(torch.__version__.split('+')[0])" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] 未检测到 torch——funasr 转录不可用；python -m pip install torch 后重跑" -ForegroundColor Yellow
} else {
    python -c "import torchaudio" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[..] 安装 torchaudio $torchVer（匹配 torch，--no-deps）..."
        python -m pip install "torchaudio==$torchVer" --no-deps
    }
}
Write-Host "[OK] 依赖就绪（funasr 首次转录还会从 ModelScope 下约 1.2G 模型，直连国内网即可）"

# 3. 复制 skill（镜像：删掉旧内容再拷，改代码后重跑即可更新）
foreach ($skill in $skills) {
    $skillSrc = Join-Path $PSScriptRoot "skill\$skill"
    $skillDst = Join-Path $HOME ".claude\skills\$skill"
    if (Test-Path $skillDst) { Remove-Item $skillDst -Recurse -Force }
    New-Item -ItemType Directory -Path $skillDst -Force | Out-Null
    Copy-Item "$skillSrc\*" $skillDst -Recurse -Force
    Write-Host "[OK] $skill 已安装到 $skillDst"
}

# 旧版拆装的独立 skill 目录清理（media-review / media-cut 已并为 media 的子技能，留着会重复触发）
foreach ($legacy in @("media-review", "media-cut")) {
    $legacyDst = Join-Path $HOME ".claude\skills\$legacy"
    if (Test-Path $legacyDst) {
        Remove-Item $legacyDst -Recurse -Force
        Write-Host "[OK] 已清理旧 skill 目录 $legacyDst"
    }
}

# 4. 配置骨架自动生成（零人工起步：用户之后只需跑一次 login 扫码）
$cfgFile = Join-Path $PSScriptRoot "_config_local.json"
$cfgExample = Join-Path $PSScriptRoot "config.example.json"
if (-not (Test-Path $cfgFile) -and (Test-Path $cfgExample)) {
    Copy-Item $cfgExample $cfgFile
    Write-Host "[OK] 已生成配置 _config_local.json（SESSDATA 待填）" 
}

# 5. 配置指引
Write-Host ""
Write-Host "== 剩下一步（只需一次扫码） ==" -ForegroundColor Yellow
Write-Host "配置 _config_local.json 已在仓根生成；直接跑扫码登录，SESSDATA 自动写入："
Write-Host "  python skill/media/review/scripts/fetch_bili.py login --config _config_local.json"
Write-Host "（F12 手动复制 SESSDATA 为备用方案；paths 各键不填即用默认目录结构）"
Write-Host "然后在 Claude Code 里喊 /media 试跑"
