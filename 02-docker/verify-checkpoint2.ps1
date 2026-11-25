# Run from PowerShell with access to the Docker Linux engine.
$ErrorActionPreference = 'Stop'
function Invoke-Docker {
    # Windows PowerShell can turn redirected native stderr into error records.
    # Docker writes normal build progress there, so use its exit code instead.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    & docker @args 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            Write-Host $_.ToString()
        } else {
            $_
        }
    }
    $dockerExitCode = $LASTEXITCODE
    if ($dockerExitCode -ne 0) { throw "Docker exited with code ${dockerExitCode}: $args" }
}

function Wait-AgentHealth {
    param([string]$Uri)
    for ($attempt = 1; $attempt -le 15; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri $Uri -TimeoutSec 3
            if ($health.status -eq 'ok') { return $health }
        } catch {
            if ($attempt -eq 15) { throw }
        }
        Start-Sleep -Seconds 1
    }
    throw "Agent health did not report ok at $Uri"
}

Push-Location (Join-Path $PSScriptRoot '..')
$run = [guid]::NewGuid().ToString('N').Substring(0, 8)
$basic = "day14-basic-$run"
$compose = @('compose', '-p', "day14-cp2-$run", '-f', '02-docker/production/docker-compose.yml')
$basicStarted = $false
$stackStarted = $false
try {
    Invoke-Docker version --format '{{.Server.Version}}'
    Invoke-Docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
    Invoke-Docker run -d --name $basic -p '127.0.0.1::8000' my-agent:develop
    $basicStarted = $true
    $binding = Invoke-Docker port $basic 8000/tcp
    "Checking basic agent at http://$binding/health"
    Wait-AgentHealth "http://$binding/health"
    $reply = Invoke-RestMethod -Method Post "http://$binding/ask?question=Docker"
    if (-not $reply.answer) { throw 'Missing basic answer' }
    $reply
    Invoke-Docker logs --tail 5 $basic
    Invoke-Docker exec $basic python --version

    $stackStarted = $true
    Invoke-Docker @compose up --build --wait --wait-timeout 180
    Invoke-Docker @compose ps
    $health = Wait-AgentHealth 'http://127.0.0.1/health'
    $reply = Invoke-RestMethod -Method Post 'http://127.0.0.1/ask' -ContentType 'application/json' -Body '{"question":"Docker"}'
    if ($health.status -ne 'ok' -or -not $reply.answer) { throw 'Nginx smoke test failed' }
    $health
    $reply
    Invoke-Docker @compose exec -T nginx nginx -t
    Invoke-Docker @compose exec -T redis redis-cli ping
    Invoke-Docker @compose exec -T agent id
    Invoke-Docker @compose logs --tail 5 agent nginx
    $agent = Invoke-Docker @compose ps -q agent
    $image = Invoke-Docker inspect --format '{{.Image}}' $agent
    $basicSize = [long](Invoke-Docker image inspect --format '{{.Size}}' my-agent:develop)
    $advancedSize = [long](Invoke-Docker image inspect --format '{{.Size}}' $image)
    "Basic: $basicSize bytes; advanced: $advancedSize bytes; reduction: $([math]::Round(100 * (1 - $advancedSize / $basicSize), 2))%"
} catch {
    if ($basicStarted) {
        try { Invoke-Docker logs --tail 30 $basic } catch { Write-Warning $_.Exception.Message }
    }
    if ($stackStarted) {
        try { Invoke-Docker @compose logs --tail 30 } catch { Write-Warning $_.Exception.Message }
    }
    throw
} finally {
    if ($basicStarted) { & docker rm -f $basic | Out-Null }
    if ($stackStarted) { & docker @compose down --volumes }
    Pop-Location
}
