# set_clip_image.ps1 — 把图片文件写进 OS 剪贴板（公众号编辑器吃截图粘贴）
# 用法: powershell -STA -NoProfile -ExecutionPolicy Bypass -File set_clip_image.ps1 -Path "C:/x.jpg"
param([string]$Path = "")
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile($Path)
[System.Windows.Forms.Clipboard]::SetImage($img)
$img.Dispose()
Write-Output "clip=1"
