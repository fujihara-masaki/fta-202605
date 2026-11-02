<#
.SYNOPSIS
    PR-7 の実機の確認（ブラウザの拡大・Windows の表示倍率・日本語入力）を
    補助する（Windows PowerShell 5.1 用）。

.DESCRIPTION
    tests/e2e/display_check.py を、自動確認専用の venv の python で実行します。
    利用者が行うのは、表示される案内に従った操作だけです：テスト用の
    ブラウザのウィンドウで Ctrl と + を押して拡大を変えること、-Ime を付けた
    ときは IME で日本語を入力して Enter を押すこと。

    次は自動です：テスト用サーバー（スタブ。実LLMは呼ばない）と試験 DB・
    データの準備（記録フォルダの中）、インストール済みの Chrome・Edge の
    起動（一時プロフィール。最大化し、表示領域は指定しない）、OS・ブラウザの
    版・画面・表示領域（clientWidth×clientHeight）・devicePixelRatio・描画に
    使われたフォントの記録、拡大の変化の検出、拡大ごとの E-V01〜E-V03 と
    同じ確認（実際のウィンドウの DOM で判定）と画面の保存、日本語入力の
    判定（変換の確定の Enter で送信されないこと）、result.md・result.json の
    作成、試験 DB の削除。

    Windows の表示倍率・ブラウザのポリシー・普段のプロフィール・利用者の DB・
    .env は変更しません。表示倍率を変えて確認するときは、Windows の設定で
    変えてから、もう一度実行します。詳しい手順は docs/manual-check-pr7.md。

.PARAMETER Venv
    自動確認専用の venv（run_browser_e2e.ps1 -Mode Setup で作ったもの）。

.PARAMETER OutRoot
    記録フォルダを作る場所（コードのフォルダの外）。実行のたびに新しい
    フォルダを作ります。

.PARAMETER ExpectedSha
    確認する SHA（7 桁以上）。コードの HEAD と一致しなければ止まります。

.PARAMETER Browser
    chrome（既定）または msedge。インストール済みのものを起動します。

.PARAMETER OsScale
    Windows の設定（ディスプレイ → 拡大/縮小）に表示されている値（例 125）。
    記録に書くためだけに使います（ツールは devicePixelRatio からも推定します）。

.PARAMETER Zooms
    確認するブラウザの拡大（既定 "100,125,150"）。

.PARAMETER Ime
    日本語入力（Microsoft IME）の確認も行う（5 か所）。

.PARAMETER Source
    テストするコードの fta_tool フォルダ。既定は、このスクリプトがある fta_tool。

.EXAMPLE
    & "$src\scripts\run_display_check.ps1" -Venv $venv -OutRoot $out -ExpectedSha $sha -Browser msedge -OsScale 100 -Ime

.NOTES
    - 終了コード：0 判定 OK、1 判定 NG、2 未完了（拡大を時間内に確認できない・
      ブラウザを起動できない・中断など）、9 実行前の確認で中止（確認は始めていない）。
    - このファイルは UTF-8 BOM 付き・CRLF で保存します
      （tests/test_run_display_check_script.py が検査します）。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Venv,
    [Parameter(Mandatory = $true)][string]$OutRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedSha,
    [ValidateSet("chrome", "msedge")][string]$Browser = "chrome",
    [ValidateRange(0, 500)][int]$OsScale = 0,
    [ValidatePattern('^\d{2,3}(,\d{2,3})*$')][string]$Zooms = "100,125,150",
    [switch]$Ime,
    [string]$Source = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$AbortCode = 9
$OnWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT

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
$tool = Join-Path (Join-Path (Join-Path $sourcePath "tests") "e2e") "display_check.py"
if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
    Stop-Check "このコードには PR-7 の確認（tests/e2e/display_check.py）がありません：$sourcePath"
}
$repo = Split-Path -Parent $sourcePath
$venvPath = Resolve-UserPath $Venv
if ($OnWindows) { $python = Join-Path (Join-Path $venvPath "Scripts") "python.exe" } else { $python = Join-Path (Join-Path $venvPath "bin") "python" }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Stop-Check "自動確認専用の venv がありません：$python。先に run_browser_e2e.ps1 -Mode Setup を実行してください"
}
$outRootPath = Resolve-UserPath $OutRoot
if (Test-Inside $outRootPath $repo) { Stop-Check "記録はコードのフォルダの外に作ってください：$outRootPath" }
$envFile = Join-Path $sourcePath ".env"
if (Test-Path -LiteralPath $envFile) { Stop-Check "コード側に .env があります：$envFile。.env のない worktree で実行してください" }

$sha = Invoke-Git @("-C", $repo, "rev-parse", "HEAD")
if ($sha.Code -ne 0 -or $sha.Text -notmatch '^[0-9a-f]{40}$') { Stop-Check "コードの SHA を取得できません（$repo）：$($sha.Text)" }
$head = $sha.Text
$dirty = Invoke-Git @("-C", $repo, "status", "--porcelain", "--untracked-files=no")
if ($dirty.Code -ne 0) { Stop-Check "コードの状態を確認できません：$($dirty.Text)" }
if ($dirty.Text) { Stop-Check "コードに未コミットの変更があります（$repo）。確認する SHA のままの worktree で実行してください" }
$expected = $ExpectedSha.Trim().ToLowerInvariant()
if ($expected.Length -lt 7 -or -not $head.StartsWith($expected)) { Stop-Check "コードの HEAD（$head）が -ExpectedSha（$ExpectedSha）と一致しません" }

$scaleText = $(if ($OsScale -gt 0) { "os$OsScale" } else { "os-unknown" })
$runName = "{0}-{1}-{2}-{3}-display" -f $head.Substring(0, 7), (Get-Date -Format "yyyyMMdd-HHmmss"), $Browser, $scaleText
$runDir = Join-Path $outRootPath $runName
if (Test-Path -LiteralPath $runDir) { Stop-Check "記録フォルダが既にあります：$runDir" }

$toolArgs = @("-m", "tests.e2e.display_check", "--out", $runDir, "--channel", $Browser, "--zooms", $Zooms)
if ($OsScale -gt 0) { $toolArgs += @("--os-scale", "$OsScale") }
if ($Ime) { $toolArgs += "--ime" }

$previousOutputEncoding = $null
try { $previousOutputEncoding = [Console]::OutputEncoding; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$saved = @{}
foreach ($name in @("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE")) {
    $saved[$name] = [System.Environment]::GetEnvironmentVariable($name, "Process")
}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$code = 2
Push-Location -LiteralPath $sourcePath
try {
    Write-Host "対象 SHA：$head"
    Write-Host "記録フォルダ：$runDir"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $failure = ""
    try {
        & $python @toolArgs
        $code = $LASTEXITCODE
    } catch {
        $failure = "$_"
        $code = 2
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($null -eq $code) { $code = 2 }
    # The tool writes result.md itself, also when it cannot go on. If it did
    # not (it could not start), say so in the record folder.
    $result = Join-Path $runDir "result.md"
    if (-not (Test-Path -LiteralPath $result)) {
        if (-not (Test-Path -LiteralPath $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
        $text = "# PR-7 表示倍率・ブラウザの拡大・日本語入力の確認（display_check）`n`n- 判定：**未完了**（終了コード $code）`n- 未完了の理由：確認の道具が結果を書きませんでした。$failure`n- 対象 SHA：``$head```n"
        [System.IO.File]::WriteAllText($result, $text, (New-Object System.Text.UTF8Encoding($false)))
        if ($code -eq 0) { $code = 2 }
    }
} finally {
    Pop-Location
    foreach ($name in $saved.Keys) { [System.Environment]::SetEnvironmentVariable($name, $saved[$name], "Process") }
    if ($null -ne $previousOutputEncoding) { try { [Console]::OutputEncoding = $previousOutputEncoding } catch { } }
}
Write-Host ""
Write-Host "結果：$(Join-Path $runDir 'result.md')（終了コード $code）"
exit $code
