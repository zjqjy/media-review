# win_window.ps1 v2 (title-scoped): only touches ego windows whose title matches
# -TitlePattern (default: gongzhonghao/MP weixin). No process killing -- safe with
# parallel AI sessions. Actions: restore / minimize / close (WM_CLOSE).
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File win_window.ps1 restore
#   powershell -NoProfile -ExecutionPolicy Bypass -File win_window.ps1 minimize
#   powershell -NoProfile -ExecutionPolicy Bypass -File win_window.ps1 close
param(
  [string]$Action = "restore",
  [string]$TitlePattern = "blog-gzh"
)
$def = 'using System; using System.Runtime.InteropServices; public class EgoWinNative { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n); [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l); }'
Add-Type -TypeDefinition $def
$hits = @(Get-Process ego -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 -and ($_.MainWindowTitle -match $TitlePattern ) })
foreach ($p in $hits) {
  switch ($Action) {
    "restore"  { [EgoWinNative]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; [EgoWinNative]::SetForegroundWindow($p.MainWindowHandle) | Out-Null }
    "minimize" { [EgoWinNative]::ShowWindow($p.MainWindowHandle, 6) | Out-Null }
    "close"    { [EgoWinNative]::PostMessage($p.MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null }
  }
}
Start-Sleep -Milliseconds 800
Write-Output ("{0}={1}" -f $Action, $hits.Count)
