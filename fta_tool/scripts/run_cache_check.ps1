<#
.SYNOPSIS
    PR-C の W-02（普段のブラウザでの実際の Ctrl+F5・F5）の確認を実行する
    （Windows PowerShell 5.1 用）。

.DESCRIPTION
    tests/e2e/cache_manual_check.py を、自動確認専用の venv の python で実行します。
    利用者が行うのは、表示される案内に従ったブラウザの操作（画面のリンクの
    クリック、3画面での Ctrl+F5 を1回ずつ、編集画面での F5 を1回）だけです。

    次は自動です：静的ファイルの一時コピーと試験 DB・分析データの準備（記録
    フォルダの中）、旧方式の配信での起動、目印の版の変更（w0→w1→w2）、
    サーバーの停止と同じポートでの起動、要求・応答の記録とページが使った値の
    収集、判定、result.md・result.json の作成、一時コピーと試験 DB の削除。

    普段のコード・利用者の DB・ブラウザのデータは変更・消去しません。
    詳しい手順は docs/manual-check-pr-c.md。

.PARAMETER Venv
    自動確認専用の venv（run_browser_e2e.ps1 -Mode Setup で作ったもの）。

.PARAMETER OutRoot
    記録フォルダを作る場所（コードのフォルダの外）。実行のたびに新しい
    フォルダを作ります。

.PARAMETER ExpectedSha
    確認する SHA（7 桁以上）。コードの HEAD と一致しなければ止まります。

.PARAMETER Browser
    chrome（既定）または msedge。記録に書くためだけに使います（操作するのは
    利用者が開いた普段のブラウザ）。

.PARAMETER Port
    確認のサーバーのポート（既定 8001）。普段のサーバーとは別のポートにします。

.PARAMETER Source
    テストするコードの fta_tool フォルダ。既定は、このスクリプトがある fta_tool。

.EXAMPLE
    & "$src\scripts\run_cache_check.ps1" -Venv $venv -OutRoot $out -ExpectedSha $sha

.NOTES
    - 終了コード：0 判定 OK、1 判定 NG、2 未完了（時間切れ・中断・ポート使用中など）、
      9 実行前の確認で中止（確認は始めていない）。
    - このファイルは UTF-8 BOM 付き・CRLF で保存します
      （tests/test_run_cache_check_script.py が検査します）。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Venv,
    [Parameter(Mandatory = $true)][string]$OutRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedSha,
    [ValidateSet("chrome", "msedge")][string]$Browser = "chrome",
    [ValidateRange(1024, 65535)][int]$Port = 8001,
    [string]$Source = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$AbortCode = 9
$OnWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
$BrowserNames = @{ "chrome" = "Google Chrome"; "msedge" = "Microsoft Edge" }

function Stop-Check([string]$Message) {
    Write-Host "中止：$Message" -ForegroundColor Red
    exit $AbortCode
}

function Resolve-UserPath([string]$Path) {
    return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
}

function Test-Inside([string]$Path, [string]$Folder) {
    $separators = [char[]]@('\', '/')
    $p = $Path.TrimEnd($separators) + [System.IO.Path]::DirectorySeparatorChar
    $f = $Folder.TrimEnd($separators) + [System.IO.Path]::DirectorySeparatorChar
    return $p.StartsWith($f, [System.StringComparison]::OrdinalIgnoreCase)
}

function Invoke-Git([string[]]$Arguments) {
    # Windows PowerShell 5.1 turns a native command's stderr into errors that
    # "Stop" would throw, so they are collected here.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & git @Arguments 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    $lines = @($output | ForEach-Object { "$_" })
    return New-Object PSObject -Property @{ Code = $code; Text = ($lines -join "`n").Trim() }
}

if ($Source) { $sourcePath = Resolve-UserPath $Source } else { $sourcePath = Split-Path -Parent $PSScriptRoot }
$tool = Join-Path (Join-Path (Join-Path $sourcePath "tests") "e2e") "cache_manual_check.py"
if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
    Stop-Check "このコードには W-02 の確認（tests/e2e/cache_manual_check.py）がありません：$sourcePath"
}
$repo = Split-Path -Parent $sourcePath
$venvPath = Resolve-UserPath $Venv
if ($OnWindows) { $python = Join-Path (Join-Path $venvPath "Scripts") "python.exe" } else { $python = Join-Path (Join-Path $venvPath "bin") "python" }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Stop-Check "自動確認専用の venv がありません：$python。先に run_browser_e2e.ps1 -Mode Setup を実行してください"
}
$outRootPath = Resolve-UserPath $OutRoot
if (Test-Inside $outRootPath $repo) { Stop-Check "記録はコードのフォルダの外に作ってください：$outRootPath" }

$sha = Invoke-Git @("-C", $repo, "rev-parse", "HEAD")
if ($sha.Code -ne 0 -or $sha.Text -notmatch '^[0-9a-f]{40}$') { Stop-Check "コードの SHA を取得できません（$repo）：$($sha.Text)" }
$head = $sha.Text
$dirty = Invoke-Git @("-C", $repo, "status", "--porcelain", "--untracked-files=no")
if ($dirty.Code -ne 0) { Stop-Check "コードの状態を確認できません：$($dirty.Text)" }
if ($dirty.Text) { Stop-Check "コードに未コミットの変更があります（$repo）。確認する SHA のままの worktree で実行してください" }
$expected = $ExpectedSha.Trim().ToLowerInvariant()
if ($expected.Length -lt 7 -or -not $head.StartsWith($expected)) { Stop-Check "コードの HEAD（$head）が -ExpectedSha（$ExpectedSha）と一致しません" }

$runName = "{0}-{1}-{2}-w02" -f $head.Substring(0, 7), (Get-Date -Format "yyyyMMdd-HHmmss"), $Browser
$runDir = Join-Path $outRootPath $runName
if (Test-Path -LiteralPath $runDir) { Stop-Check "記録フォルダが既にあります：$runDir" }

$previousOutputEncoding = $null
try { $previousOutputEncoding = [Console]::OutputEncoding; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$saved = @{}
foreach ($name in @("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONUNBUFFERED")) {
    $saved[$name] = [System.Environment]::GetEnvironmentVariable($name, "Process")
}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
$code = 2
Push-Location -LiteralPath $sourcePath
try {
    Write-Host "対象 SHA：$head"
    Write-Host "記録フォルダ：$runDir"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $python -m tests.e2e.cache_manual_check --out $runDir --port $Port --browser $BrowserNames[$Browser]
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
} finally {
    Pop-Location
    foreach ($name in $saved.Keys) { [System.Environment]::SetEnvironmentVariable($name, $saved[$name], "Process") }
    if ($null -ne $previousOutputEncoding) { try { [Console]::OutputEncoding = $previousOutputEncoding } catch { } }
}
Write-Host ""
Write-Host "結果：$(Join-Path $runDir 'result.md')（終了コード $code）"
exit $code
