# win_window.ps1 — ego 窗口还原/最小化双模式（发布流程自动调用，用户零操作）
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File win_window.ps1 restore    # 还原+置前（跑流程前）
#   powershell -NoProfile -ExecutionPolicy Bypass -File win_window.ps1 minimize   # 收回最小化（流程结束后）
param([string]$Action = "restore")
$def = 'using System; using System.Runtime.InteropServices; public class EgoWinNative { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n); [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }'
Add-Type -TypeDefinition $def
$n = if ($Action -eq "minimize") { 6 } else { 9 }   # SW_MINIMIZE=6 / SW_RESTORE=9
$hit = 0
Get-Process ego -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
  [EgoWinNative]::ShowWindow($_.MainWindowHandle, $n) | Out-Null
  if ($Action -eq "restore") { [EgoWinNative]::SetForegroundWindow($_.MainWindowHandle) | Out-Null }
  $hit++
}
Start-Sleep -Milliseconds 800
Write-Output "${Action}=$hit"
