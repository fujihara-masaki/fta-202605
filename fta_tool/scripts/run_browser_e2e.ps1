#Requires -Version 5.1
<#
.SYNOPSIS
    実ブラウザテスト（E2E）を、インストール済みの Google Chrome（または
    Microsoft Edge）で実行する（Windows PowerShell 5.1 用）。

.DESCRIPTION
    初回準備・準備確認・全件の自動確認を、-Mode で選んで実行します。

      Setup      初回だけ。自動確認専用の venv を -Venv に作り、
                 requirements-dev.txt の固定版を入れる。通常の .venv には
                 何も入れない。ブラウザの導入（playwright install）はしない。
      Preflight  準備確認。編集画面を開く少数の既存テストだけを実行する
                 （pytest --e2e-preflight）。全必須 E2E の合格ではない。
      Full       全必須 E2E（pytest -m e2e --e2e-required）。
      Diagnose   最初の読み込みの診断（tests/e2e/diagnose_navigation.py）。
                 新しい一時サーバーの同じ URL を、Python（httpx）からの GET、
                 ブラウザ（最小の構成とテストの構成）、Playwright を使わない
                 起動で開き、どこまで進むか・サーバーに届いたかを記録する。
                 合否は判定しない（テストの構成を外した実行は受入ではない）。

    Preflight・Full・Diagnose は、実行のたびに -OutRoot の下へ新しい記録
    フォルダを作り、既存の記録には書きません。テスト用サーバーと DB は
    記録フォルダの中の一時領域（pytest-tmp、Diagnose では diagnose\server）に
    作ります。普段の DB、手動確認の DB、ポート 8000〜8002 は使いません。
    実LLMは呼びません（テスト用サーバーのスタブ。AI: e2e-stub）。

    ブラウザは --browser-channel で指定したインストール済みのもの（通常の
    プロフィールは使わない一時プロフィール）を、画面を表示して（--headed）
    起動します。見つからない・起動できないときは失敗として止まり、
    Playwright 同梱の Chromium には切り替えません。

.PARAMETER Mode
    Setup / Preflight / Full / Diagnose。

.PARAMETER Venv
    自動確認専用の venv のフォルダ。コードのフォルダの外で、通常の .venv とは
    別の場所。

.PARAMETER BasePython
    Setup で venv を作る元の python.exe（通常の .venv の python.exe でよい。
    その .venv は変更しない）。

.PARAMETER Source
    テストするコードの fta_tool フォルダ。既定は、このスクリプトがある
    fta_tool。

.PARAMETER OutRoot
    記録フォルダを作る場所（Preflight・Full・Diagnose で必須。コードのフォルダの外）。

.PARAMETER Channel
    chrome（既定）または msedge。

.PARAMETER ExpectedSha
    確認する SHA（7 桁以上）。コードの HEAD と一致しなければ止まる。

.PARAMETER Environment
    実行環境の区分：User（利用者環境）または Dev（開発環境）。省略すると、
    Windows では User、それ以外では Dev。記録（e2e-report.md の「実行環境の
    区分」と run-info.md）には、この区分と実際の OS を書きます。

.PARAMETER SlowMo
    失敗の調査用。操作ごとに待つミリ秒（既定 0。正式な確認では使わない。
    Diagnose では使えない）。

.PARAMETER DryRun
    確認だけを行い、実行するコマンドを表示して終わる（venv・記録フォルダを
    作らない）。

.EXAMPLE
    & "$src\scripts\run_browser_e2e.ps1" -Mode Preflight -Venv $venv -OutRoot $out -ExpectedSha $sha

.EXAMPLE
    & "$src\scripts\run_browser_e2e.ps1" -Mode Diagnose -Venv $venv -OutRoot $out -ExpectedSha $sha

.NOTES
    - 終了コード：0 成功（準備確認の成功・全必須 E2E の合格）、1〜5 pytest の
      結果（1 は失敗・不合格）、9 実行前の確認で中止（テストは実行していない）。
      Diagnose は 0 診断を実行した（結果は diagnose-report.md。合否ではない）、
      1 診断を続けられなかった・中断された、2 引数の誤り、9 実行前の確認で中止。
    - 実行ポリシー、ブラウザのポリシー、プロキシ・TLS の設定は変更しません。
      止められた場合は、そのまま報告してください。
    - 終わったときに、この実行で起動して残っているプロセス（pytest の子孫で、
      作成時刻も一致するもの）だけを止めます。名前やポート番号では止めません。
      プロセスの確認は Windows だけで行い、記録には「確認して0件」「あり
      （止めたもの）」「未確認」「取得失敗」を区別して書きます（Windows 以外
      では「未確認」）。
    - このファイルは UTF-8 BOM 付き・CRLF で保存します
      （tests/test_run_browser_e2e_script.py が検査します）。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet("Setup", "Preflight", "Full", "Diagnose")][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Venv,
    [string]$BasePython = "",
    [string]$Source = "",
    [string]$OutRoot = "",
    [ValidateSet("chrome", "msedge")][string]$Channel = "chrome",
    [string]$ExpectedSha = "",
    [string]$Environment = "",
    [ValidateRange(0, 5000)][int]$SlowMo = 0,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$AbortCode = 9
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$OnWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
$ChannelNames = @{ "chrome" = "Google Chrome"; "msedge" = "Microsoft Edge" }
$EnvironmentNames = @{ "User" = "利用者環境"; "Dev" = "開発環境" }
$MaxRunDirLength = 150  # a failed test's evidence lies up to ~100 characters deeper (MAX_PATH 260)
# What the check of leftover processes saw (Windows only): snapshots taken
# while pytest ran, and the first error of a snapshot.
$ProcessCheck = @{ Watched = 0; Failed = "" }

# --- helpers --------------------------------------------------------------------

function Stop-Run([string]$Message) {
    throw (New-Object System.InvalidOperationException($Message))
}

function Resolve-UserPath([string]$Path) {
    # Relative to the current PowerShell location (not the process' directory).
    return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
}

function Join-Parts([string]$Base, [string[]]$Parts) {
    $path = $Base
    foreach ($part in $Parts) { $path = Join-Path $path $part }
    return $path
}

function Test-Inside([string]$Path, [string]$Folder) {
    $separators = [char[]]@('\', '/')
    $p = $Path.TrimEnd($separators) + [System.IO.Path]::DirectorySeparatorChar
    $f = $Folder.TrimEnd($separators) + [System.IO.Path]::DirectorySeparatorChar
    return $p.StartsWith($f, [System.StringComparison]::OrdinalIgnoreCase)
}

function Write-Utf8File([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function ConvertTo-Argument([string]$Value) {
    # One argument of a Windows command line (the rules of CommandLineToArgvW).
    if ($Value -eq "") { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Invoke-Native([string]$File, [string[]]$Arguments) {
    # Output of a native command as text. Windows PowerShell 5.1 turns its
    # stderr into errors that "Stop" would throw, so they are collected here.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $File @Arguments 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    $lines = @($output | ForEach-Object { "$_" })
    return New-Object PSObject -Property @{ Code = $code; Text = ($lines -join "`n").Trim() }
}

function Find-Browser([string]$Name) {
    # The places Playwright looks at for --browser-channel chrome / msedge.
    $suffix = if ($Name -eq "chrome") { "Google\Chrome\Application\chrome.exe" } else { "Microsoft\Edge\Application\msedge.exe" }
    $prefixes = @($env:LOCALAPPDATA, $env:ProgramFiles, ${env:ProgramFiles(x86)})
    if ($env:HOMEDRIVE) { $prefixes += @(($env:HOMEDRIVE + "\Program Files"), ($env:HOMEDRIVE + "\Program Files (x86)")) }
    foreach ($prefix in $prefixes) {
        if (-not $prefix) { continue }
        $candidate = Join-Path $prefix $suffix
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Get-ProcessSnapshot {
    # Win32_Process (Windows only). A failure is remembered, never taken for "none".
    if (-not $OnWindows) { return @() }
    try {
        return @(Get-CimInstance -ClassName Win32_Process -Property ProcessId, ParentProcessId, Name, CreationDate -ErrorAction Stop)
    } catch {
        if (-not $ProcessCheck.Failed) { $ProcessCheck.Failed = $_.Exception.Message }
        return @()
    }
}

function Test-SameTime([datetime]$A, [datetime]$B) {
    return [math]::Abs(($A - $B).TotalSeconds) -lt 1
}

function Watch-Descendants([System.Diagnostics.Process]$Root, [hashtable]$Seen) {
    # Remember every process started below pytest while its parent still runs
    # (verified by the creation time, so a reused process id is never taken).
    $snapshot = @(Get-ProcessSnapshot)  # a function's empty array comes back as $null
    if ($snapshot.Count -eq 0) { return }
    $byId = @{}
    foreach ($proc in $snapshot) { $byId[[int]$proc.ProcessId] = $proc }
    $known = @{}
    $rootProc = $byId[$Root.Id]
    if ($null -ne $rootProc -and (Test-SameTime $rootProc.CreationDate $Root.StartTime)) {
        $known[$Root.Id] = $rootProc.CreationDate
        $ProcessCheck.Watched++
    }
    foreach ($id in @($Seen.Keys)) {
        $proc = $byId[[int]$id]
        if ($null -ne $proc -and (Test-SameTime $proc.CreationDate $Seen[$id].Created)) { $known[[int]$id] = $proc.CreationDate }
    }
    $found = $true
    while ($found) {
        $found = $false
        foreach ($proc in $snapshot) {
            $id = [int]$proc.ProcessId
            $parent = [int]$proc.ParentProcessId
            if ($known.ContainsKey($id) -or -not $known.ContainsKey($parent)) { continue }
            if ($proc.CreationDate -lt $known[$parent]) { continue }
            $known[$id] = $proc.CreationDate
            $Seen[$id] = @{ Name = $proc.Name; Created = $proc.CreationDate }
            $found = $true
        }
    }
}

function Stop-Leftovers([hashtable]$Seen) {
    # Stop what this run started and is still running (same id and creation time).
    $stopped = @()
    if (-not $OnWindows -or $ProcessCheck.Watched -eq 0) { return $stopped }
    $snapshot = @(Get-ProcessSnapshot)
    if ($snapshot.Count -eq 0) { return $stopped }  # the error is in $ProcessCheck.Failed
    foreach ($proc in $snapshot) {
        $id = [int]$proc.ProcessId
        if (-not $Seen.ContainsKey($id)) { continue }
        if (-not (Test-SameTime $proc.CreationDate $Seen[$id].Created)) { continue }
        try {
            Stop-Process -Id $id -Force -ErrorAction Stop
            $stopped += ("{0}（{1}）" -f $proc.Name, $id)
        } catch {
            $stopped += ("{0}（{1}、止められませんでした：{2}）" -f $proc.Name, $id, $_.Exception.Message)
        }
    }
    return $stopped
}

function Get-LeftoverText([string[]]$Stopped, [int]$SeenCount) {
    # Checked and none / some (stopped) / not checked / could not be checked.
    if (-not $OnWindows) { return "未確認（Windows 以外では、このスクリプトはプロセスを確認しません）" }
    $found = if ($Stopped.Count -gt 0) { "。止めたもの：" + ($Stopped -join "、") } else { "" }
    if ($ProcessCheck.Failed) { return "取得失敗（プロセスの一覧を取得できませんでした：{0}）{1}" -f $ProcessCheck.Failed, $found }
    if ($ProcessCheck.Watched -eq 0) { return "未確認（実行中のプロセスを確認する前に終わりました）" }
    if ($Stopped.Count -gt 0) { return "あり：{0} 件{1}" -f $Stopped.Count, $found }
    return "確認して0件（実行中に記録した {0} 個のプロセスは、終了後に残っていませんでした。記録は開始の約2秒後と、その後約10秒ごと）" -f $SeenCount
}

function Get-OsText {
    if ($OnWindows) {
        try {
            $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
            return "{0} {1}" -f $os.Caption, $os.Version
        } catch {
            return [System.Environment]::OSVersion.VersionString
        }
    }
    return ([System.Runtime.InteropServices.RuntimeInformation]::OSDescription).Trim()
}

function Read-SharedText([string]$Path) {
    # The log while pytest still writes it.
    try {
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            $reader = New-Object System.IO.StreamReader($stream, $Utf8NoBom)
            return $reader.ReadToEnd()
        } finally {
            $stream.Dispose()
        }
    } catch {
        return ""
    }
}

function Get-ReportValues([string]$Report, [string]$Label) {
    # Every row of the report with this label (the diagnosis has several).
    $values = @()
    if (-not (Test-Path -LiteralPath $Report)) { return $values }
    foreach ($line in [System.IO.File]::ReadAllLines($Report, $Utf8NoBom)) {
        if ($line.StartsWith("| $Label |")) {
            $values += $line.Substring($Label.Length + 4).TrimEnd(" ", "|").Trim()
        }
    }
    return $values
}

function Get-ReportValue([string]$Report, [string]$Label) {
    $values = @(Get-ReportValues $Report $Label)
    if ($values.Count -gt 0) { return $values[0] }
    return $null
}

function Format-Duration([timespan]$Span) {
    return ("{0}分{1:00}秒" -f [int][math]::Floor($Span.TotalMinutes), $Span.Seconds)
}

# --- the paths every mode needs ---------------------------------------------------

function Get-Settings {
    $sourcePath = if ($Source) { Resolve-UserPath $Source } else { Split-Path -Parent $PSScriptRoot }
    if (-not (Test-Path -LiteralPath (Join-Parts $sourcePath @("tests", "e2e", "conftest.py")))) {
        Stop-Run "テストのコードが見つかりません：$sourcePath（fta_tool フォルダを -Source に指定してください）"
    }
    $venvPath = Resolve-UserPath $Venv
    $venvPython = if ($OnWindows) { Join-Parts $venvPath @("Scripts", "python.exe") } else { Join-Parts $venvPath @("bin", "python") }
    return @{
        Source = $sourcePath
        Repo = Split-Path -Parent $sourcePath
        Venv = $venvPath
        Python = $venvPython
    }
}

function Get-PackageVersions([string]$Python) {
    $code = "import importlib.metadata as m, platform; print('Python ' + platform.python_version() + ' / ' + ' / '.join(n + ' ' + m.version(n) for n in ('playwright', 'pytest-playwright', 'pytest')))"
    return Invoke-Native $Python @("-c", $code)
}

# --- Setup ----------------------------------------------------------------------------

function Invoke-Setup([hashtable]$S) {
    if (-not $BasePython) { Stop-Run "初回準備には -BasePython（venv を作る元の python.exe）を指定してください" }
    $base = Resolve-UserPath $BasePython
    if (-not (Test-Path -LiteralPath $base -PathType Leaf)) { Stop-Run "python が見つかりません：$base" }
    if (Test-Inside $S.Venv $S.Repo) { Stop-Run "venv はコードのフォルダ（$($S.Repo)）の外に作ってください：$($S.Venv)" }
    if (Test-Inside $base $S.Venv) { Stop-Run "-Venv が -BasePython の venv と同じ場所です。自動確認専用の別のフォルダを指定してください（通常の .venv は変更しません）" }
    $marker = Join-Path $S.Venv "fta-e2e-venv.txt"
    $requirements = Join-Path $S.Source "requirements-dev.txt"

    Write-Host "== 初回準備（自動確認専用の venv） =="
    Write-Host ("  元の python      : {0}（{1}）" -f $base, (Invoke-Native $base @("--version")).Text)
    Write-Host ("  venv             : {0}" -f $S.Venv)
    Write-Host ("  入れるもの       : {0}（固定版。playwright install は実行しません）" -f $requirements)
    if (Test-Path -LiteralPath $S.Venv) {
        if (-not ((Test-Path -LiteralPath $marker) -and (Test-Path -LiteralPath $S.Python))) {
            Stop-Run "既にあるフォルダです（このスクリプトで作った venv ではありません）：$($S.Venv)。新しいフォルダを指定してください"
        }
        Write-Host "  作成済みの venv に、同じ固定版が入っているかを確かめます"
    } elseif (-not $DryRun) {
        & $base -m venv $S.Venv
        if ($LASTEXITCODE -ne 0) { Stop-Run "venv を作れませんでした（終了コード $LASTEXITCODE）" }
        Write-Utf8File $marker ("FTA 支援ツールの実ブラウザテスト専用の venv（scripts/run_browser_e2e.ps1 で作成）`r`n作成: {0}`r`n元の python: {1}`r`n" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"), $base)
    }
    if ($DryRun) {
        Write-Host "（-DryRun のため、venv の作成と導入はしていません）"
        return 0
    }
    & $S.Python -m pip install --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) { Stop-Run "requirements-dev.txt を入れられませんでした（終了コード $LASTEXITCODE）。プロキシなどの設定は変更せずに報告してください" }
    $versions = Get-PackageVersions $S.Python
    if ($versions.Code -ne 0) { Stop-Run "入れた版を確認できませんでした：$($versions.Text)" }
    Write-Host ("  入った版         : {0}" -f $versions.Text)
    if ($OnWindows) {
        foreach ($name in @("chrome", "msedge")) {
            $exe = Find-Browser $name
            $text = if ($exe) { "{0}（{1}）" -f $exe, (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion } else { "見つかりません" }
            Write-Host ("  {0,-16} : {1}" -f $ChannelNames[$name], $text)
        }
    }
    Write-Host "初回準備が終わりました。次は準備確認（-Mode Preflight）です。" -ForegroundColor Green
    return 0
}

# --- Preflight / Full / Diagnose ---------------------------------------------------------

function Invoke-Run([hashtable]$S) {
    if ($Environment -and @("User", "Dev") -notcontains $Environment) {
        Stop-Run "-Environment には User（利用者環境）か Dev（開発環境）を指定してください：$Environment"
    }
    if (-not (Test-Path -LiteralPath $S.Python -PathType Leaf)) {
        Stop-Run "自動確認専用の venv がありません：$($S.Python)。先に -Mode Setup を実行してください"
    }
    $diagnose = $Mode -eq "Diagnose"
    if ($diagnose -and $SlowMo -gt 0) { Stop-Run "-SlowMo は Diagnose では使えません（診断は時間の上限を自分で決めています）" }
    if (-not $OutRoot) { Stop-Run "-OutRoot（記録フォルダを作る場所）を指定してください" }
    $outRootPath = Resolve-UserPath $OutRoot
    if (Test-Inside $outRootPath $S.Repo) { Stop-Run "記録はコードのフォルダの外に作ってください：$outRootPath" }

    # The code under test: its commit, no changes, no code-side .env.
    $sha = Invoke-Native "git" @("-C", $S.Repo, "rev-parse", "HEAD")
    if ($sha.Code -ne 0 -or $sha.Text -notmatch '^[0-9a-f]{40}$') { Stop-Run "コードの SHA を取得できません（$($S.Repo)）：$($sha.Text)" }
    $head = $sha.Text
    $dirty = Invoke-Native "git" @("-C", $S.Repo, "status", "--porcelain", "--untracked-files=no")
    if ($dirty.Code -ne 0) { Stop-Run "コードの状態を確認できません：$($dirty.Text)" }
    if ($dirty.Text) { Stop-Run "コードに未コミットの変更があります（$($S.Repo)）。確認する SHA のままの worktree で実行してください" }
    if ($ExpectedSha) {
        $expected = $ExpectedSha.Trim().ToLowerInvariant()
        if ($expected.Length -lt 7 -or -not $head.StartsWith($expected)) { Stop-Run "コードの HEAD（$head）が -ExpectedSha（$ExpectedSha）と一致しません" }
    }
    $diagnoseScript = Join-Parts $S.Source @("tests", "e2e", "diagnose_navigation.py")
    if ($diagnose -and -not (Test-Path -LiteralPath $diagnoseScript -PathType Leaf)) {
        Stop-Run "このコード（$head）には診断（tests/e2e/diagnose_navigation.py）がありません。診断を含む SHA の worktree で実行してください"
    }
    $envFile = Join-Path $S.Source ".env"
    if (Test-Path -LiteralPath $envFile) {
        Stop-Run "コード側に .env があります：$envFile。.env のない worktree で実行してください（.env はシェルの設定より優先されます）"
    }

    # The browser of the channel (Windows: the places Playwright looks at).
    $browserText = "（Windows 以外のため確認しません。Playwright が探します）"
    if ($OnWindows) {
        $exe = Find-Browser $Channel
        if (-not $exe) {
            Stop-Run ("{0} が見つからないため、実 {0} では確認できません（Playwright 同梱の Chromium には切り替えません）。インストールされている場所を報告してください" -f $ChannelNames[$Channel])
        }
        $browserText = "{0}（ファイルの版 {1}）" -f $exe, (Get-Item -LiteralPath $exe).VersionInfo.ProductVersion
    }
    $versions = Get-PackageVersions $S.Python
    if ($versions.Code -ne 0) { Stop-Run "自動確認専用の venv に playwright・pytest-playwright がありません。-Mode Setup を実行してください：$($versions.Text)" }

    $runName = "{0}-{1}-{2}-{3}" -f $head.Substring(0, 7), (Get-Date -Format "yyyyMMdd-HHmmss"), $Channel, $Mode.ToLowerInvariant()
    $runDir = Join-Path $outRootPath $runName
    if ($runDir.Length -gt $MaxRunDirLength) {
        Stop-Run "記録フォルダのパスが長すぎます（$($runDir.Length) 文字。$MaxRunDirLength 文字まで）：$runDir。-OutRoot を短い場所にしてください"
    }
    if (Test-Path -LiteralPath $runDir) { Stop-Run "記録フォルダが既にあります：$runDir" }
    if ($diagnose) {
        $diagnoseDir = Join-Path $runDir "diagnose"
        $paths = @{
            Report = Join-Path $diagnoseDir "diagnose-report.md"
            Info = Join-Path $runDir "run-info.md"
            Output = Join-Path $runDir "diagnose-output.log"
            Errors = Join-Path $runDir "diagnose-stderr.log"
            Diagnose = $diagnoseDir
        }
        $kind = "最初の読み込みの診断（tests/e2e/diagnose_navigation.py。合否は判定しません）"
    } else {
        $paths = @{
            Report = Join-Path $runDir "e2e-report.md"
            Info = Join-Path $runDir "run-info.md"
            Output = Join-Path $runDir "pytest-output.log"
            Errors = Join-Path $runDir "pytest-stderr.log"
            Temp = Join-Path $runDir "pytest-tmp"
            Evidence = Join-Path $runDir "failures"
        }
        $kind = if ($Mode -eq "Full") { "全必須 E2E（--e2e-required）" } else { "準備確認（--e2e-preflight。全必須 E2E の合格ではありません）" }
    }
    # Where it runs: the user's environment or the development one, with the actual OS.
    $envKind = if ($Environment) { $Environment } elseif ($OnWindows) { "User" } else { "Dev" }
    $envHow = if ($Environment) { "-Environment $Environment" } else { "-Environment 未指定のため OS から判断" }
    $osText = Get-OsText
    $label = "{0}（{1}、{2}、headed）" -f $EnvironmentNames[$envKind], $osText, $ChannelNames[$Channel]
    if ($diagnose) {
        # The diagnosis starts its own server and browser (headed); it never runs the tests.
        $runArgs = @($diagnoseScript, "--out", $paths.Diagnose, "--channel", $Channel, "--env-label", $label)
    } else {
        $runArgs = @("-m", "pytest", (Join-Path $S.Source "tests"), "-m", "e2e")
        $runArgs += $(if ($Mode -eq "Full") { "--e2e-required" } else { "--e2e-preflight" })
        $runArgs += @("--browser", "chromium", "--browser-channel", $Channel, "--headed",
            "--e2e-env", $label, "--e2e-report", $paths.Report,
            "--basetemp", $paths.Temp, "--output", $paths.Evidence,
            "--screenshot", "only-on-failure", "--tracing", "retain-on-failure",
            "-p", "no:cacheprovider", "-v", "-rfE")
        if ($SlowMo -gt 0) { $runArgs += @("--slowmo", "$SlowMo") }
    }
    $commandLine = ($runArgs | ForEach-Object { ConvertTo-Argument $_ }) -join " "

    Write-Host ("== {0}：{1} ==" -f $(if ($diagnose) { "実ブラウザの最初の読み込み" } else { "実ブラウザテスト（E2E）" }), $kind)
    Write-Host ("  実行環境の区分   : {0}（{1}）" -f $label, $envHow)
    Write-Host ("  コード（Source） : {0}" -f $S.Source)
    Write-Host ("  対象 SHA         : {0}（未コミットの変更なし{1}）" -f $head, $(if ($ExpectedSha) { "、-ExpectedSha と一致" } else { "、-ExpectedSha 未指定" }))
    Write-Host ("  コード側の .env  : なし（{0}）" -f $envFile)
    Write-Host ("  Python（専用）   : {0}（{1}）" -f $S.Python, $versions.Text)
    Write-Host ("  ブラウザ         : channel {0} → {1}" -f $Channel, $browserText)
    Write-Host ("  記録フォルダ     : {0}" -f $runDir)
    if ($DryRun) {
        Write-Host "  実行するコマンド : $($S.Python) $commandLine"
        Write-Host "（-DryRun のため実行していません。記録フォルダも作っていません）"
        return 0
    }

    New-Item -ItemType Directory -Path $runDir | Out-Null
    $started = Get-Date
    $info = [ordered]@{
        "種類" = $kind
        "実行環境の区分" = "$label（$envHow）"
        "開始" = $started.ToString("yyyy-MM-dd HH:mm:ss zzz")
        "対象 SHA" = "$head（未コミットの変更なし）"
        "期待した SHA" = $(if ($ExpectedSha) { $ExpectedSha } else { "未指定" })
        "コード（Source）" = $S.Source
        "コード側の .env" = "なし（$envFile）"
        "Python（自動確認専用の venv）" = "$($S.Python)（$($versions.Text)）"
        "ブラウザの channel" = $Channel
        "ブラウザの実行ファイル" = $browserText
        "表示" = $(if ($diagnose) { "headed（診断が起動）" } elseif ($SlowMo -gt 0) { "headed、slowmo $SlowMo ms（調査用）" } else { "headed、slowmo なし" })
        "OS" = $osText
        "PowerShell" = $PSVersionTable.PSVersion.ToString()
        "実行コマンド" = "$($S.Python) $commandLine"
        "状態" = "実行中"
    }
    Save-RunInfo $paths.Info $info

    $savedEnv = @{}
    foreach ($name in @("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE", "FTA_E2E_REQUIRED", "FTA_E2E_ENV")) {
        $savedEnv[$name] = [System.Environment]::GetEnvironmentVariable($name, "Process")
    }
    $env:PYTHONIOENCODING = "utf-8"        # the logs are UTF-8
    $env:PYTHONUTF8 = "1"
    $env:PYTHONUNBUFFERED = "1"            # the log grows as the tests run
    $env:PYTHONDONTWRITEBYTECODE = "1"     # nothing written into the code's folder
    [System.Environment]::SetEnvironmentVariable("FTA_E2E_REQUIRED", $null, "Process")
    [System.Environment]::SetEnvironmentVariable("FTA_E2E_ENV", $null, "Process")

    $process = $null
    $exitCode = $null
    $state = "中断されました"
    $seen = @{}
    $leftovers = @()
    try {
        $process = Start-Process -FilePath $S.Python -ArgumentList $commandLine -WorkingDirectory $runDir `
            -NoNewWindow -PassThru -RedirectStandardOutput $paths.Output -RedirectStandardError $paths.Errors
        $null = $process.Handle  # Windows PowerShell 5.1: keeps ExitCode readable after the end
        $ticks = 0
        while (-not $process.WaitForExit(2000)) {
            $ticks++
            if ($OnWindows -and ($ticks -eq 1 -or $ticks % 5 -eq 0)) { Watch-Descendants $process $seen }
            if ($ticks % 15 -eq 0) {
                $text = Read-SharedText $paths.Output
                if ($diagnose) {
                    $steps = @($text -split "`n" | Where-Object { $_.StartsWith("[診断]") })
                    $step = if ($steps.Count -gt 0) { $steps[$steps.Count - 1].Trim() } else { "開始の準備中" }
                    Write-Host ("  実行中… 経過 {0}、{1}" -f (Format-Duration ((Get-Date) - $started)), $step)
                } else {
                    $done = ([regex]::Matches($text, ' (PASSED|FAILED|ERROR|SKIPPED)\s+\[')).Count
                    $bad = ([regex]::Matches($text, ' (FAILED|ERROR)\s+\[')).Count
                    Write-Host ("  実行中… 経過 {0}、結果 {1} 件（失敗・エラー {2}）" -f (Format-Duration ((Get-Date) - $started)), $done, $bad)
                }
            }
        }
        $process.WaitForExit()
        $exitCode = $process.ExitCode
        $state = "終了"
    } finally {
        if ($null -ne $process -and -not $process.HasExited) {
            # Interrupted (Ctrl+C): pytest closes its browser and server itself; wait for it.
            if (-not $process.WaitForExit(60000)) {
                try { Stop-Process -Id $process.Id -Force -ErrorAction Stop } catch { }
            }
        }
        if ($null -ne $process) { $leftovers = @(Stop-Leftovers $seen) }
        foreach ($name in $savedEnv.Keys) { [System.Environment]::SetEnvironmentVariable($name, $savedEnv[$name], "Process") }
        $finished = Get-Date
        $verdict = Get-ReportValue $paths.Report "判定"
        $reportName = Split-Path -Leaf $paths.Report
        $info["終了"] = $finished.ToString("yyyy-MM-dd HH:mm:ss zzz")
        $info["所要時間"] = Format-Duration ($finished - $started)
        $info["状態"] = $state
        if ($diagnose) {
            $info["終了コード（診断）"] = $(if ($null -ne $exitCode) { "$exitCode（0 は診断を実行できたこと。合否ではありません）" } else { "-" })
            $info["判定（diagnose-report.md）"] = $(if ($verdict) { $verdict } else { "（diagnose-report.md がありません）" })
            $hints = @(Get-ReportValues $paths.Report "見立て（記録からの分類。原因の確定ではありません）")
            $info["見立て（diagnose-report.md）"] = $(if ($hints.Count -gt 0) { $hints -join " ／ " } else { "-" })
        } else {
            $info["終了コード（pytest）"] = $(if ($null -ne $exitCode) { "$exitCode" } else { "-" })
            $info["判定（e2e-report.md）"] = $(if ($verdict) { $verdict } else { "（e2e-report.md がありません）" })
            $info["結果（テスト単位）"] = $(Get-ReportValue $paths.Report "結果（テスト単位）")
            $knownText = Get-ReportValue $paths.Report "既知の例外（favicon の 404）"
            $info["既知の例外（favicon の 404）"] = $(if ($knownText -and $knownText -match '^(\d+) 件') { "{0} 件（e2e-report.md の「既知の例外として除いたコンソールのエラー」）" -f $Matches[1] } else { $knownText })
        }
        $info["起動したブラウザ"] = $(Get-ReportValue $paths.Report "起動したブラウザ")
        $info["残っていたプロセス"] = Get-LeftoverText $leftovers $seen.Count
        Save-RunInfo $paths.Info $info
    }

    if ($diagnose) { return (Show-DiagnoseResult $paths $info $runDir $exitCode $reportName) }

    $verdict = $info["判定（e2e-report.md）"]
    $browser = $info["起動したブラウザ"]
    $ok = ($exitCode -eq 0) -and ($verdict -like "合格*" -or $verdict -like "成功*")
    Write-Host ""
    Write-Host "== 結果 =="
    if ($browser -and $browser.StartsWith("未起動")) {
        Write-Host ("  実 {0} では未確認です（ブラウザを起動できませんでした）：{1}" -f $ChannelNames[$Channel], $browser) -ForegroundColor Red
    }
    Write-Host ("  判定             : {0}" -f $verdict) -ForegroundColor $(if ($ok) { "Green" } else { "Red" })
    Write-Host ("  終了コード       : {0}" -f $exitCode)
    Write-Host ("  結果（テスト単位）: {0}" -f $info["結果（テスト単位）"])
    Write-Host ("  既知の例外       : {0}" -f $info["既知の例外（favicon の 404）"])
    Write-Host ("  起動したブラウザ : {0}" -f $browser)
    Write-Host ("  所要時間         : {0}" -f $info["所要時間"])
    Write-Host ("  記録フォルダ     : {0}" -f $runDir)
    Write-Host  "    e2e-report.md       受入の記録（実行条件・受入項目ごと・テストごとの結果）"
    Write-Host  "    run-info.md         この実行の条件と終了コード"
    Write-Host  "    pytest-output.log   pytest の出力（pytest-stderr.log もあわせて）"
    Write-Host  "    pytest-tmp          テスト用サーバーの一時 DB とログ（e2e-server0\server.log）"
    if (Test-Path -LiteralPath $paths.Evidence) {
        Write-Host  "    failures            失敗したテストの trace（trace.zip）と画面（png。撮れたときだけ。実際にあるファイルと"
        Write-Host  "                        撮れなかった理由は e2e-report.md の「失敗したテストの証跡（実際にあるファイル）」）"
    }
    Write-Host ("  残っていたプロセス: {0}" -f $info["残っていたプロセス"])
    if ($null -eq $exitCode) { return 2 }
    return [int]$exitCode
}

function Show-DiagnoseResult([hashtable]$Paths, $Info, [string]$RunDir, $ExitCode, [string]$ReportName) {
    Write-Host ""
    Write-Host "== 診断の結果（合否は判定しません） =="
    Write-Host ("  終了コード       : {0}" -f $(if ($null -ne $ExitCode) { "$ExitCode（0 は診断を実行できたこと。合否ではありません）" } else { "-（中断されました）" }))
    $fatal = Get-ReportValue $Paths.Report "診断を続けられなかった理由"
    if ($fatal) { Write-Host ("  続けられなかった理由: {0}" -f $fatal) -ForegroundColor Red }
    if (-not (Test-Path -LiteralPath $Paths.Report)) {
        Write-Host ("  {0} がありません。diagnose-output.log と diagnose-stderr.log を確認してください" -f $ReportName) -ForegroundColor Red
    }
    foreach ($label in @("要約（Python）", "要約（ブラウザ・最初の読み込み）", "要約（サーバーへの到達・最初の読み込み）", "要約（Playwright を使わない起動）")) {
        $value = Get-ReportValue $Paths.Report $label
        if ($value) { Write-Host ("  {0}: {1}" -f $label, $value) }
    }
    foreach ($value in @(Get-ReportValues $Paths.Report "見立て（記録からの分類。原因の確定ではありません）")) {
        Write-Host ("  見立て（原因の確定ではありません）: {0}" -f $value)
    }
    Write-Host ("  起動したブラウザ : {0}" -f $Info["起動したブラウザ"])
    Write-Host ("  所要時間         : {0}" -f $Info["所要時間"])
    Write-Host ("  記録フォルダ     : {0}" -f $RunDir)
    Write-Host  "    diagnose\diagnose-report.md    診断の記録（これを送ってください）"
    Write-Host  "    diagnose\diagnose.json         同じ内容（機械で読む形）"
    Write-Host  "    diagnose\server-access.jsonl   テスト用サーバーの受信・応答の記録（ヘッダー・本文なし）"
    Write-Host  "    diagnose\screen-*.png、trace-tests.zip   読み込みの終わりの画面と trace"
    Write-Host  "    diagnose\netlog-raw            ブラウザの通信の記録の原本（ほかのサイトの URL やプロキシの設定を含むため、依頼があるときだけ送る）"
    Write-Host  "    run-info.md、diagnose-output.log、diagnose-stderr.log   この実行の条件と出力"
    Write-Host ("  残っていたプロセス: {0}" -f $Info["残っていたプロセス"])
    if ($null -eq $ExitCode) { return 1 }
    return [int]$ExitCode
}

function Save-RunInfo([string]$Path, $Info) {
    $lines = @("# 実ブラウザテスト（E2E）の実行記録（scripts/run_browser_e2e.ps1）", "", "| 項目 | 値 |", "|---|---|")
    foreach ($key in $Info.Keys) {
        $value = if ($null -eq $Info[$key]) { "-" } else { ([string]$Info[$key]) -replace '\|', '／' }
        $lines += "| $key | $value |"
    }
    Write-Utf8File $Path (($lines -join "`r`n") + "`r`n")
}

# --- main ------------------------------------------------------------------------------

$previousOutputEncoding = $null
try { $previousOutputEncoding = [Console]::OutputEncoding; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try {
    $settings = Get-Settings
    if ($Mode -eq "Setup") { $code = Invoke-Setup $settings } else { $code = Invoke-Run $settings }
} catch {
    Write-Host ("中止しました：{0}" -f $_.Exception.Message) -ForegroundColor Red
    if (-not ($_.Exception -is [System.InvalidOperationException])) {
        Write-Host ("  （想定外のエラー：{0}{1}）" -f $_.Exception.GetType().FullName, $_.InvocationInfo.PositionMessage)
    }
    $code = $AbortCode
} finally {
    if ($null -ne $previousOutputEncoding) { try { [Console]::OutputEncoding = $previousOutputEncoding } catch { } }
}
exit $code
