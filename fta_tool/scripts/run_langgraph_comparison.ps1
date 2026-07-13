#Requires -Version 5.1
<#
.SYNOPSIS
    LangGraph / Quality Gate 比較試験の実行スクリプト（Windows PowerShell 用）。

.DESCRIPTION
    FTA支援ツールを設定ごとにローカル起動し、同一シナリオ・同一頂上事象で
    要因生成を複数回実行して、ログ・API レスポンス・エクスポート
    （JSON / CSV / Markdown）を試験ID配下へ保存します。

    比較する4設定（実効3モード。off-on は「Quality Gate フラグが
    LangGraph OFF 時に影響しない」ことを確認する対照条件）:

      off-off : LangGraph OFF / Quality Gate OFF （legacy）
      off-on  : LangGraph OFF / Quality Gate ON  （実効は legacy と同じ）
      on-off  : LangGraph ON  / Quality Gate OFF
      on-on   : LangGraph ON  / Quality Gate ON

    生成アルゴリズム・品質判定・プロンプト・DB スキーマには一切手を
    加えません。設定の切り替えは fta_tool/.env の LangGraph 関連 2 キーの
    差し替えのみで行い、元の .env は開始時にバックアップし終了時に復元します
    （.env は python-dotenv が override=True で読むため、環境変数ではなく
    .env の書き換えが必要です）。

    実行ごとに専用の作業ディレクトリで uvicorn を起動するため、
    SQLite DB（fta_tool.db）は毎回まっさらな状態から始まります
    （前の実行の要因が DB 重複除外に影響しません）。

    各実行の結果はその場でディスクへ書き出し、runs_index.csv へ逐次追記する
    ため、途中で停止しても完了済みの実行結果は失われません。

.PARAMETER TrialId
    試験ID。出力ディレクトリ名になります（既定: trial_yyyyMMdd_HHmmss）。

.PARAMETER Configs
    実行する設定。off-off / off-on / on-off / on-on（または 1..4）。
    既定は 4 設定すべて。

.PARAMETER Iterations
    設定ごとの評価対象（計測）実行回数。既定 3。

.PARAMETER WarmupRuns
    設定ごとのウォームアップ実行回数（集計から除外される）。既定 1。

.PARAMETER OrderMode
    計測実行の並べ方。interleave（既定。設定を交互に回して実行順の偏りを
    減らす）/ sequential（設定ごとにまとめて実行）/ random（シャッフル）。

.PARAMETER ScenarioId
    config/sample_scenarios.yaml のシナリオID。既定 internet_web_access_failure。
    -TopEvent を指定した場合はシナリオを使わずその頂上事象だけで実行します。

.PARAMETER MaxLevel
    生成する階層の深さ（1〜3）。既定 2。各階層生成後、生成された要因を
    すべて Yes 評価にして次階層の親にします。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\run_langgraph_comparison.ps1 `
        -TrialId trial_20260712_a -Iterations 3 -WarmupRuns 1

.NOTES
    - 実 Ollama（.env の AI_PROVIDER=ollama）が起動済みであることが前提です。
    - スクリプトは fta_tool ディレクトリ配下のどこから実行しても動作します。
    - パスに空白が含まれていても動作します。
    - このファイルは必ず UTF-8 BOM 付きで保存してください。BOM が無いと
      Windows PowerShell 5.1 が日本語コメントを ANSI として誤解釈し、
      ParserError になります（tests/test_run_langgraph_comparison_script.py が
      BOM と構文を検査します）。
#>
[CmdletBinding()]
param(
    [string]$TrialId = ("trial_" + (Get-Date -Format "yyyyMMdd_HHmmss")),
    [string[]]$Configs = @("off-off", "off-on", "on-off", "on-on"),
    [ValidateRange(1, 100)][int]$Iterations = 3,
    [ValidateRange(0, 10)][int]$WarmupRuns = 1,
    [ValidateSet("interleave", "sequential", "random")][string]$OrderMode = "interleave",
    [string]$ScenarioId = "internet_web_access_failure",
    [string]$TopEvent = "",
    [ValidateRange(1, 3)][int]$MaxLevel = 2,
    [ValidateRange(1024, 65535)][int]$Port = 8130,
    [string]$PythonExe = "python",
    [string]$OutputRoot = "",
    [string]$RunDate = (Get-Date -Format "yyyy-MM-dd HH:mm:ss"),
    [int]$StartupTimeoutSec = 90,
    [int]$GenerateTimeoutSec = 1800,
    [int]$RandomSeed = 0,
    [switch]$SkipAnalyze
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

# 日本語を含む Python 出力・HTTP 応答を正しく扱うための設定
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# --- パス解決（空白入りパス対応のため常に変数経由・引用符付きで扱う） ------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$FtaToolDir = Split-Path -Parent $ScriptDir
$AnalyzerPy = Join-Path $ScriptDir "analyze_langgraph_comparison.py"
$EnvPath    = Join-Path $FtaToolDir ".env"
$EnvBackup  = Join-Path $FtaToolDir ".env.comparison_backup"

if (-not $OutputRoot) {
    $OutputRoot = Join-Path (Split-Path -Parent $FtaToolDir) "comparison_results"
}
$TrialDir = Join-Path $OutputRoot $TrialId
$RunsDir  = Join-Path $TrialDir "runs"
$SnapDir  = Join-Path $TrialDir "config_snapshots"
$IndexCsv = Join-Path $TrialDir "runs_index.csv"
$BaseUrl  = "http://127.0.0.1:$Port"

# --- 設定定義 ----------------------------------------------------------------
$ConfigDefs = @{
    "off-off" = @{ Langgraph = "false"; QualityGate = "false"; Label = "1: LangGraph OFF / Quality Gate OFF (legacy)" }
    "off-on"  = @{ Langgraph = "false"; QualityGate = "true";  Label = "2: LangGraph OFF / Quality Gate ON (対照条件・実効はlegacy)" }
    "on-off"  = @{ Langgraph = "true";  QualityGate = "false"; Label = "3: LangGraph ON / Quality Gate OFF" }
    "on-on"   = @{ Langgraph = "true";  QualityGate = "true";  Label = "4: LangGraph ON / Quality Gate ON" }
}
$ConfigAliases = @{ "1" = "off-off"; "2" = "off-on"; "3" = "on-off"; "4" = "on-on" }

$ResolvedConfigs = @()
foreach ($c in $Configs) {
    $name = $c.ToLower().Trim()
    if ($ConfigAliases.ContainsKey($name)) { $name = $ConfigAliases[$name] }
    if (-not $ConfigDefs.ContainsKey($name)) {
        throw "不明な設定です: $c （off-off / off-on / on-off / on-on または 1..4 を指定）"
    }
    if ($ResolvedConfigs -notcontains $name) { $ResolvedConfigs += $name }
}

# --- 共通ヘルパ ---------------------------------------------------------------

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8File([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Append-Utf8File([string]$Path, [string]$Text) {
    [System.IO.File]::AppendAllText($Path, $Text, $Utf8NoBom)
}

function ConvertTo-CsvField([object]$Value) {
    $s = if ($null -eq $Value) { "" } else { [string]$Value }
    if ($s -match '[",\r\n]') { '"' + ($s -replace '"', '""') + '"' } else { $s }
}

function Add-RunIndexRow([hashtable]$Row) {
    $columns = @(
        "trial_id", "run_id", "config", "langgraph", "quality_gate", "phase",
        "iteration", "order_index", "scenario_id", "max_level",
        "start_time", "end_time", "total_http_elapsed_ms", "status", "error"
    )
    if (-not (Test-Path -LiteralPath $IndexCsv)) {
        Write-Utf8File $IndexCsv (($columns -join ",") + "`r`n")
    }
    $cells = foreach ($col in $columns) { ConvertTo-CsvField $Row[$col] }
    Append-Utf8File $IndexCsv (($cells -join ",") + "`r`n")
}

# HTTP: 応答本文を必ず UTF-8 として読む（PowerShell 5.1 の charset 既定対策）
function Invoke-HttpJson {
    param(
        [string]$Method = "GET",
        [Parameter(Mandatory)][string]$Uri,
        [object]$JsonBody = $null,
        [int]$TimeoutSec = 300
    )
    $requestParams = @{
        Method          = $Method
        Uri             = $Uri
        UseBasicParsing = $true
        TimeoutSec      = $TimeoutSec
    }
    if ($null -ne $JsonBody) {
        $json = $JsonBody | ConvertTo-Json -Depth 10 -Compress
        $requestParams["Body"] = $Utf8NoBom.GetBytes($json)
        $requestParams["ContentType"] = "application/json; charset=utf-8"
    }
    $resp = Invoke-WebRequest @requestParams
    $stream = $resp.RawContentStream
    $stream.Position = 0
    $text = $Utf8NoBom.GetString($stream.ToArray())
    return @{ Text = $text; Json = ($text | ConvertFrom-Json) }
}

function Invoke-FormPost([string]$Uri, [hashtable]$Fields, [int]$TimeoutSec = 60) {
    # 日本語を含むフォーム値を UTF-8 で URL エンコードして送る
    $pairs = foreach ($key in $Fields.Keys) {
        [System.Uri]::EscapeDataString([string]$key) + "=" +
        [System.Uri]::EscapeDataString([string]$Fields[$key])
    }
    $body = $Utf8NoBom.GetBytes(($pairs -join "&"))
    try {
        # 303 リダイレクトを追わず Location から作成先を得る
        $resp = Invoke-WebRequest -Method Post -Uri $Uri -Body $body `
            -ContentType "application/x-www-form-urlencoded; charset=utf-8" `
            -UseBasicParsing -MaximumRedirection 0 -TimeoutSec $TimeoutSec `
            -ErrorAction Stop
        return $resp.Headers["Location"]
    } catch {
        $exception = $_.Exception
        $hasResponse = $null -ne $exception.PSObject.Properties["Response"]
        if ($hasResponse -and $null -ne $exception.Response) {
            $response = $exception.Response
            try { return [string]$response.Headers["Location"] } catch { }
            try { return [string]$response.Headers.Location } catch { }
        }
        throw
    }
}

function Get-SanitizedEnvText([string[]]$Lines) {
    $masked = foreach ($line in $Lines) {
        if ($line -match '^\s*([A-Za-z0-9_]+)\s*=' ) {
            $key = $Matches[1]
            if ($key -match '(?i)(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)') {
                "$key=***MASKED***"
            } else { $line }
        } else { $line }
    }
    return ($masked -join "`r`n")
}

function Get-EnvLines {
    if (Test-Path -LiteralPath $EnvPath) {
        return @([System.IO.File]::ReadAllLines($EnvPath))
    }
    return @()
}

# 元の .env から LangGraph 関連 2 キーを除去し、設定値を追記した内容を返す
function Build-ConfigEnvText([string[]]$BaseLines, [string]$ConfigName) {
    $def = $ConfigDefs[$ConfigName]
    $kept = $BaseLines | Where-Object {
        $_ -notmatch '^\s*ENABLE_LANGGRAPH_GENERATION_WORKFLOW\s*=' -and
        $_ -notmatch '^\s*ENABLE_LANGGRAPH_QUALITY_GATE\s*='
    }
    $extra = @(
        "",
        "# --- run_langgraph_comparison.ps1 による一時設定（試験終了時に復元されます） ---",
        "ENABLE_LANGGRAPH_GENERATION_WORKFLOW=$($def.Langgraph)",
        "ENABLE_LANGGRAPH_QUALITY_GATE=$($def.QualityGate)"
    )
    return ((@($kept) + $extra) -join "`r`n") + "`r`n"
}

function Start-FtaServer([string]$WorkDir, [string]$OutLog, [string]$ErrLog) {
    $uvicornArgs = @(
        "-m", "uvicorn", "app.main:app",
        "--app-dir", ('"{0}"' -f $FtaToolDir),
        "--host", "127.0.0.1", "--port", "$Port", "--log-level", "info"
    )
    $proc = Start-Process -FilePath $PythonExe -ArgumentList $uvicornArgs `
        -WorkingDirectory $WorkDir -PassThru -NoNewWindow `
        -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            throw "サーバープロセスが起動直後に終了しました。ログ: $ErrLog"
        }
        try {
            $null = Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -TimeoutSec 3
            return $proc
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    try { Stop-Process -Id $proc.Id -Force } catch { }
    throw "サーバーが $StartupTimeoutSec 秒以内に起動しませんでした。ログ: $ErrLog"
}

function Stop-FtaServer($Proc) {
    if ($null -eq $Proc) { return }
    try {
        if (-not $Proc.HasExited) {
            Stop-Process -Id $Proc.Id -Force
            $null = $Proc.WaitForExit(15000)
        }
    } catch { }
    Start-Sleep -Milliseconds 500   # ログのフラッシュ待ち
}

# --- シナリオ読み込み -----------------------------------------------------------
function Get-Scenario {
    if ($TopEvent) {
        return @{
            id = "custom"; title = "カスタム頂上事象"; top_event = $TopEvent
            system_context = ""; incident_context = ""; demo_points = ""
        }
    }
    $raw = & $PythonExe $AnalyzerPy --dump-scenario $ScenarioId
    if ($LASTEXITCODE -ne 0) {
        throw "シナリオ '$ScenarioId' を取得できません（python $AnalyzerPy --list-scenarios で一覧を確認できます）"
    }
    $obj = ($raw -join "") | ConvertFrom-Json
    return @{
        id = $obj.id; title = $obj.title; top_event = $obj.top_event
        system_context   = [string]$obj.system_context
        incident_context = [string]$obj.incident_context
        demo_points      = [string]$obj.demo_points
    }
}

# --- 1 実行分 --------------------------------------------------------------------
function Invoke-OneRun {
    param(
        [string]$RunId, [string]$ConfigName, [string]$Phase, [int]$Iteration,
        [int]$OrderIndex, [hashtable]$Scenario, [string[]]$BaseEnvLines
    )
    $runDir  = Join-Path $RunsDir $RunId
    $workDir = Join-Path $runDir "work"
    New-Item -ItemType Directory -Force -Path $workDir | Out-Null
    $outLog = Join-Path $runDir "server.out.log"
    $errLog = Join-Path $runDir "server.err.log"

    $def = $ConfigDefs[$ConfigName]
    $startTime = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
    $status = "ok"
    $errorMessage = ""
    $levelResults = @()
    $totalHttpMs = 0
    $proc = $null

    try {
        # この設定用の .env を書き込んでからサーバーを起動する
        Write-Utf8File $EnvPath (Build-ConfigEnvText $BaseEnvLines $ConfigName)
        $proc = Start-FtaServer -WorkDir $workDir -OutLog $outLog -ErrLog $errLog

        # 分析作成（同一シナリオ・同一頂上事象）
        $location = Invoke-FormPost "$BaseUrl/analyses" @{
            title            = "$TrialId $RunId"
            top_event        = $Scenario.top_event
            system_context   = $Scenario.system_context
            incident_context = $Scenario.incident_context
            demo_points      = $Scenario.demo_points
        }
        $analysisId = 1   # 実行ごとに新規 DB のため通常 1
        if ($location -and $location -match "/analyses/(\d+)") {
            $analysisId = [int]$Matches[1]
        }

        foreach ($level in 1..$MaxLevel) {
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $gen = Invoke-HttpJson -Method POST `
                -Uri "$BaseUrl/analyses/$analysisId/generate/level/$level" `
                -JsonBody @{} -TimeoutSec $GenerateTimeoutSec
            $sw.Stop()
            $totalHttpMs += [int]$sw.ElapsedMilliseconds
            Write-Utf8File (Join-Path $runDir "gen_level$level.json") $gen.Text
            $levelResults += @{
                level           = $level
                http_elapsed_ms = [int]$sw.ElapsedMilliseconds
                api_elapsed_ms  = $gen.Json.elapsed_ms
                created         = $gen.Json.created
                success         = $gen.Json.success
            }
            if ($level -lt $MaxLevel) {
                # 生成された要因を Yes 評価して次階層の親にする
                $export = Invoke-HttpJson -Uri "$BaseUrl/analyses/$analysisId/export/json"
                $nodes = @($export.Json.nodes | Where-Object { $_.level -eq $level })
                foreach ($node in $nodes) {
                    $null = Invoke-HttpJson -Method POST `
                        -Uri "$BaseUrl/nodes/$($node.id)/update" `
                        -JsonBody @{ user_judgement = "yes" } -TimeoutSec 60
                }
                if ($nodes.Count -eq 0) {
                    throw "レベル $level の要因が 0 件のため次階層を生成できません"
                }
            }
        }

        # エクスポート保存（JSON / CSV / Markdown）
        Invoke-WebRequest -Uri "$BaseUrl/analyses/$analysisId/export/json" `
            -OutFile (Join-Path $runDir "export.json") -UseBasicParsing -TimeoutSec 120
        Invoke-WebRequest -Uri "$BaseUrl/analyses/$analysisId/export/csv" `
            -OutFile (Join-Path $runDir "export.csv") -UseBasicParsing -TimeoutSec 120
        Invoke-WebRequest -Uri "$BaseUrl/analyses/$analysisId/export/markdown" `
            -OutFile (Join-Path $runDir "export.md") -UseBasicParsing -TimeoutSec 120
    } catch {
        $status = "error"
        $errorMessage = [string]$_.Exception.Message
        Write-Warning "実行 $RunId が失敗しました: $errorMessage"
    } finally {
        Stop-FtaServer $proc
    }

    $endTime = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"

    # 実行メタデータ（解析スクリプトが読む）— 完了直後に必ず書く
    $meta = @{
        trial_id     = $TrialId
        run_id       = $RunId
        config       = $ConfigName
        config_label = $def.Label
        langgraph    = $def.Langgraph
        quality_gate = $def.QualityGate
        phase        = $Phase
        iteration    = $Iteration
        order_index  = $OrderIndex
        scenario_id  = $Scenario.id
        top_event    = $Scenario.top_event
        max_level    = $MaxLevel
        start_time   = $startTime
        end_time     = $endTime
        total_http_elapsed_ms = $totalHttpMs
        levels       = $levelResults
        status       = $status
        error        = $errorMessage
    }
    Write-Utf8File (Join-Path $runDir "run_meta.json") `
        ($meta | ConvertTo-Json -Depth 10)

    Add-RunIndexRow @{
        trial_id = $TrialId; run_id = $RunId; config = $ConfigName
        langgraph = $def.Langgraph; quality_gate = $def.QualityGate
        phase = $Phase; iteration = $Iteration; order_index = $OrderIndex
        scenario_id = $Scenario.id; max_level = $MaxLevel
        start_time = $startTime; end_time = $endTime
        total_http_elapsed_ms = $totalHttpMs; status = $status; error = $errorMessage
    }
    return ($status -eq "ok")
}

# --- 設定スナップショット（秘密情報はマスク） -------------------------------------
function Save-ConfigSnapshot([string]$ConfigName, [string[]]$BaseEnvLines) {
    New-Item -ItemType Directory -Force -Path $SnapDir | Out-Null
    $def = $ConfigDefs[$ConfigName]
    $envText = Build-ConfigEnvText $BaseEnvLines $ConfigName
    Write-Utf8File (Join-Path $SnapDir "$ConfigName.env.txt") `
        (Get-SanitizedEnvText ($envText -split "`r?`n"))

    $gitCommit = ""
    try {
        $gitCommit = (& git -C $FtaToolDir rev-parse HEAD 2>$null | Select-Object -First 1)
    } catch { }
    $snapshot = @{
        trial_id     = $TrialId
        run_date     = $RunDate
        config       = $ConfigName
        config_label = $def.Label
        langgraph    = $def.Langgraph
        quality_gate = $def.QualityGate
        port         = $Port
        max_level    = $MaxLevel
        iterations   = $Iterations
        warmup_runs  = $WarmupRuns
        order_mode   = $OrderMode
        git_commit   = [string]$gitCommit
        os_version   = [string][System.Environment]::OSVersion.VersionString
        processor_count = [System.Environment]::ProcessorCount
    }
    Write-Utf8File (Join-Path $SnapDir "$ConfigName.snapshot.json") `
        ($snapshot | ConvertTo-Json -Depth 5)
}

# ==============================================================================
# メイン処理
# ==============================================================================

New-Item -ItemType Directory -Force -Path $RunsDir | Out-Null

Write-Host "=== LangGraph / Quality Gate 比較試験 ==="
Write-Host "  試験ID       : $TrialId"
Write-Host "  実施日時     : $RunDate"
Write-Host "  設定         : $($ResolvedConfigs -join ', ')"
Write-Host "  反復回数     : $Iterations （ウォームアップ $WarmupRuns / 設定）"
Write-Host "  実行順序     : $OrderMode"
Write-Host "  対象シナリオ : $(if ($TopEvent) { 'カスタム: ' + $TopEvent } else { $ScenarioId })"
Write-Host "  階層         : 1..$MaxLevel"
Write-Host "  出力先       : $TrialDir"
Write-Host ""

# 前回異常終了時の .env バックアップが残っていれば復元してから始める
if (Test-Path -LiteralPath $EnvBackup) {
    Write-Warning "前回の .env バックアップが残っていたため復元します: $EnvBackup"
    Copy-Item -LiteralPath $EnvBackup -Destination $EnvPath -Force
    Remove-Item -LiteralPath $EnvBackup -Force
}

$scenario = Get-Scenario
$baseEnvLines = Get-EnvLines
$hadEnvFile = Test-Path -LiteralPath $EnvPath
if ($hadEnvFile) {
    Copy-Item -LiteralPath $EnvPath -Destination $EnvBackup -Force
}

# 実行計画の作成（ウォームアップ → 計測。interleave が既定）
$plan = New-Object System.Collections.ArrayList
foreach ($cfg in $ResolvedConfigs) {
    for ($w = 1; $w -le $WarmupRuns; $w++) {
        $null = $plan.Add(@{ Config = $cfg; Phase = "warmup"; Iteration = $w })
    }
}
$measured = New-Object System.Collections.ArrayList
switch ($OrderMode) {
    "interleave" {
        foreach ($i in 1..$Iterations) {
            foreach ($cfg in $ResolvedConfigs) {
                $null = $measured.Add(@{ Config = $cfg; Phase = "measured"; Iteration = $i })
            }
        }
    }
    "sequential" {
        foreach ($cfg in $ResolvedConfigs) {
            foreach ($i in 1..$Iterations) {
                $null = $measured.Add(@{ Config = $cfg; Phase = "measured"; Iteration = $i })
            }
        }
    }
    "random" {
        foreach ($cfg in $ResolvedConfigs) {
            foreach ($i in 1..$Iterations) {
                $null = $measured.Add(@{ Config = $cfg; Phase = "measured"; Iteration = $i })
            }
        }
        if ($RandomSeed -ne 0) { Get-Random -SetSeed $RandomSeed | Out-Null }
        $shuffled = $measured | Get-Random -Count $measured.Count
        $measured = New-Object System.Collections.ArrayList
        foreach ($item in $shuffled) { $null = $measured.Add($item) }
    }
}
foreach ($item in $measured) { $null = $plan.Add($item) }

$okCount = 0
$failCount = 0
try {
    foreach ($cfg in $ResolvedConfigs) { Save-ConfigSnapshot $cfg $baseEnvLines }

    $orderIndex = 0
    foreach ($item in $plan) {
        $orderIndex++
        $runId = "{0:d3}_{1}_{2}_{3:d2}" -f $orderIndex, $item.Config, $item.Phase, $item.Iteration
        Write-Host ("[{0}/{1}] {2} ({3})" -f $orderIndex, $plan.Count, $runId, `
            $ConfigDefs[$item.Config].Label)
        $ok = Invoke-OneRun -RunId $runId -ConfigName $item.Config `
            -Phase $item.Phase -Iteration $item.Iteration -OrderIndex $orderIndex `
            -Scenario $scenario -BaseEnvLines $baseEnvLines
        if ($ok) { $okCount++ } else { $failCount++ }
    }
} finally {
    # .env の復元（途中停止・例外時も必ず実行される）
    if ($hadEnvFile -and (Test-Path -LiteralPath $EnvBackup)) {
        Copy-Item -LiteralPath $EnvBackup -Destination $EnvPath -Force
        Remove-Item -LiteralPath $EnvBackup -Force
        Write-Host ".env を復元しました。"
    } elseif (-not $hadEnvFile -and (Test-Path -LiteralPath $EnvPath)) {
        Remove-Item -LiteralPath $EnvPath -Force
        Write-Host "一時作成した .env を削除しました。"
    }
}

Write-Host ""
Write-Host "実行完了: 成功 $okCount / 失敗 $failCount （結果: $TrialDir）"

if (-not $SkipAnalyze) {
    Write-Host "解析スクリプトを実行します..."
    & $PythonExe $AnalyzerPy $TrialDir
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "解析スクリプトがエラーを返しました（結果ファイルは保存済みです）。"
    }
}
