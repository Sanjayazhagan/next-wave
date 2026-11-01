# GradientZero browser-product: diversified real-browser API smoke/integration tests.
# Requires: PowerShell 5.1+; local integrated Docker services; configured .env.
# Does not submit external forms, solve authentication challenges, or call an LLM.
param(
    [string]$BaseUrl = 'http://localhost:8100',
    [switch]$SkipCrossSite
)
$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
$api = "$BaseUrl/integration/v2/browser"
$results = New-Object System.Collections.Generic.List[object]
$script:sid = $null
$script:obs = $null
$script:created = $null
$script:firstFill = $null
$script:artifact = $null
$script:headers = @{}
$subject = 'gz-test-synthetic-user'
$consent = 'manual-synthetic-test-with-no-real-personal-data'
$evidence = Join-Path (Get-Location).Path 'browser-test-results'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Run-Test([string]$Name, [scriptblock]$Block) {
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        & $Block
        $timer.Stop()
        $script:results.Add([pscustomobject]@{ test=$Name; status='PASS'; seconds=[math]::Round($timer.Elapsed.TotalSeconds,2); detail='' })
        Write-Host ("PASS  {0} ({1}s)" -f $Name, [math]::Round($timer.Elapsed.TotalSeconds,1)) -ForegroundColor Green
    }
    catch {
        $timer.Stop()
        $message = $_.Exception.Message
        $script:results.Add([pscustomobject]@{ test=$Name; status='FAIL'; seconds=[math]::Round($timer.Elapsed.TotalSeconds,2); detail=$message })
        Write-Host ("FAIL  {0}: {1}" -f $Name, $message) -ForegroundColor Red
    }
}
function Invoke-Gz([string]$Method, [string]$Path, [object]$Data=$null) {
    $args = @{
        Uri = "$api$Path"
        Method = $Method
        Headers = $script:headers
        TimeoutSec = 70
        ErrorAction = 'Stop'
    }
    if ($null -ne $Data) {
        $args['ContentType'] = 'application/json'
        $args['Body'] = ConvertTo-Json -InputObject $Data -Depth 35 -Compress
    }
    return Invoke-RestMethod @args
}
function Expect-HttpStatus([string]$Method,[string]$Path,[object]$Data,[int]$Expected) {
    try {
        $null = Invoke-Gz $Method $Path $Data
        throw "Expected HTTP $Expected, but request was accepted"
    }
    catch {
        $response = $_.Exception.Response
        if ($null -eq $response) { throw }
        $actual = [int]$response.StatusCode
        if ($actual -ne $Expected) { throw "Expected HTTP $Expected, received HTTP $actual" }
    }
}
function Get-Control([string]$Name, [string]$Tag='', [string]$Type='') {
    $candidates = @($script:obs.elements | Where-Object {
        $_.name -eq $Name -and
        ([string]::IsNullOrEmpty($Tag) -or $_.tag -eq $Tag) -and
        ([string]::IsNullOrEmpty($Type) -or $_.type -eq $Type)
    })
    if ($candidates.Count -lt 1) { throw "Could not find observed control name=$Name tag=$Tag type=$Type" }
    return $candidates[0]
}
function Invoke-Action([hashtable]$Action) {
    Assert-True ($null -ne $script:obs) 'No current observation'
    $Action['action_id'] = [guid]::NewGuid().ToString()
    $Action['observation_id'] = $script:obs.observation_id
    $response = Invoke-Gz 'POST' "/contexts/$script:sid/actions" $Action
    $script:obs = $response.observation
    return [pscustomobject]@{ response=$response; request=$Action }
}
function Save-Page([string]$Filename) {
    if ([string]::IsNullOrWhiteSpace($script:obs.screenshot_base64)) { throw 'No screenshot returned by worker' }
    $path = Join-Path $evidence $Filename
    [IO.File]::WriteAllBytes($path,[Convert]::FromBase64String($script:obs.screenshot_base64))
    Assert-True ((Get-Item $path).Length -gt 1000) 'Screenshot is unexpectedly tiny'
}

Write-Host "\nGradientZero REAL BROWSER API TEST SUITE" -ForegroundColor Cyan
Write-Host "Endpoint: $api"
Write-Host 'All values and documents are synthetic. No external form submission will occur.'
if (-not (Test-Path '.env')) { throw 'No .env found. Run the script from your browser-product directory.' }
$keyLine = Get-Content '.env' | Where-Object { $_ -match '^\s*INTERNAL_KEY\s*=' } | Select-Object -First 1
if (-not $keyLine) { throw 'INTERNAL_KEY missing from .env' }
$key = ($keyLine -split '=',2)[1].Trim().Trim('"').Trim("'")
Assert-True ($key.Length -ge 32) 'INTERNAL_KEY appears missing or too short'
$script:headers = @{ 'X-Internal-Key' = $key }
Remove-Variable key -ErrorAction SilentlyContinue

Run-Test '01 API readiness' {
    $ready = Invoke-RestMethod -Uri "$BaseUrl/ready" -TimeoutSec 15
    Assert-True ($ready.ok -eq $true) 'API did not report ok=true'
}
Run-Test '02 Authenticated capabilities contract' {
    $cap = Invoke-Gz 'GET' '/capabilities'
    Assert-True ($null -ne $cap) 'Capabilities response is empty'
}
Run-Test '03 Wrong API key is denied (401)' {
    try {
        $null = Invoke-RestMethod -Uri "$api/capabilities" -Headers @{'X-Internal-Key'='not-the-real-key'} -TimeoutSec 15
        throw 'Invalid key unexpectedly accepted'
    }
    catch {
        if ($null -eq $_.Exception.Response) { throw }
        Assert-True ([int]$_.Exception.Response.StatusCode -eq 401) 'Invalid key did not return 401'
    }
}
Run-Test '04 SSRF: private localhost URL blocked (403)' {
    $req = @{ request_id=[guid]::NewGuid().ToString(); subject=$subject; consent_ref=$consent; url='https://127.0.0.1/' }
    Expect-HttpStatus 'POST' '/contexts' $req 403
}
Run-Test '05 Open official Selenium practice website' {
    $req = @{ request_id=[guid]::NewGuid().ToString(); subject=$subject; consent_ref=$consent; url='https://www.selenium.dev/selenium/web/web-form.html' }
    $script:created = Invoke-Gz 'POST' '/contexts' $req
    $script:sid = $script:created.id
    $script:obs = $script:created.observation
    Assert-True (-not [string]::IsNullOrWhiteSpace($script:sid)) 'Missing context ID'
    Assert-True ($script:obs.url -like 'https://www.selenium.dev/*') 'Wrong destination'
    Assert-True (@($script:obs.elements).Count -ge 10) 'Too few form elements detected'
    Assert-True ($script:obs.truncated -eq $false) 'Selenium observation was unexpectedly truncated'
    Save-Page '01-initial-page.jpg'
}
if (-not $script:sid) {
    Write-Warning 'Site could not be opened. Skipping dependent form tests.'
}
else {
    try {
        Run-Test '06 Model-input schema is ready for LangGraph (no LLM call)' {
            $model = Invoke-Gz 'POST' "/contexts/$script:sid/model-input" @{goal='Inspect this practice form without submitting'}
            Assert-True ($model.trusted_goal -like '*practice form*') 'No trusted goal'
            Assert-True ($null -ne $model.decision_schema) 'No model decision schema'
            Assert-True ($model.observation.content_trust -eq 'untrusted_website_data') 'Site content trust boundary missing'
            Assert-True ($null -eq $model.observation.screenshot_base64) 'Screenshot unexpectedly included in standard model envelope'
            $script:obs = $model.observation
        }
        Run-Test '07 Fill text input and verify readback' {
            $el = Get-Control 'my-text' 'input' 'text'
            $script:firstFill = Invoke-Action @{kind='fill';target_ref=$el.ref;value='GradientZero API Test';verified=$true;source_ref='synthetic-suite'}
            Assert-True ($script:firstFill.response.effect.matched -eq $true) 'Text input readback was not matched'
            $el = Get-Control 'my-text' 'input' 'text'
            Assert-True ($el.value -eq 'GradientZero API Test') 'Observed value was not updated'
        }
        Run-Test '08 Same action ID is replay-safe (no second fill)' {
            Assert-True ($null -ne $script:firstFill) 'The earlier fill failed; cannot test replay'
            $replayed = Invoke-Gz 'POST' "/contexts/$script:sid/actions" $script:firstFill.request
            Assert-True ($replayed.replayed -eq $true) 'Action replay was not marked'
        }
        Run-Test '09 Reject stale observation ID (409)' {
            Assert-True ($null -ne $script:firstFill) 'Earlier fill failed; cannot test stale observation'
            $el = Get-Control 'my-textarea' 'textarea'
            $req = @{action_id=[guid]::NewGuid().ToString();observation_id=$script:firstFill.request.observation_id;kind='fill';target_ref=$el.ref;value='should not be typed';verified=$true;source_ref='synthetic-suite'}
            Expect-HttpStatus 'POST' "/contexts/$script:sid/actions" $req 409
        }
        Run-Test '10 Fill textarea with second synthetic value' {
            $el = Get-Control 'my-textarea' 'textarea'
            $act = Invoke-Action @{kind='fill';target_ref=$el.ref;value='GradientZero note - synthetic only';verified=$true;source_ref='synthetic-suite'}
            Assert-True ($act.response.effect.matched -eq $true) 'Textarea readback failed'
        }
        Run-Test '11 Select a non-disabled dropdown option' {
            $el = Get-Control 'my-select' 'select'
            $choice = @($el.options | Where-Object { -not $_.disabled -and -not [string]::IsNullOrEmpty($_.value) } | Select-Object -First 1)
            Assert-True ($choice.Count -gt 0) 'Dropdown has no selectable option'
            $act = Invoke-Action @{kind='select';target_ref=$el.ref;value=[string]$choice[0].value;verified=$true;source_ref='synthetic-suite'}
            Assert-True ($act.response.effect.matched -eq $true) 'Dropdown readback failed'
        }
        Run-Test '12 Check an unchecked checkbox' {
            $el = @($script:obs.elements | Where-Object { $_.type -eq 'checkbox' -and $_.risk -eq 'ordinary' -and $_.checked -eq $false } | Select-Object -First 1)
            Assert-True ($el.Count -gt 0) 'No unchecked ordinary checkbox observed'
            $act = Invoke-Action @{kind='check';target_ref=$el[0].ref;checked=$true;verified=$true;source_ref='synthetic-suite'}
            Assert-True ($act.response.effect.matched -eq $true) 'Checkbox readback failed'
        }
	Run-Test '12A Fill date picker' {
            $el = Get-Control 'my-date' 'input' 'text'

            $act = Invoke-Action @{
                kind = 'fill'
                target_ref = $el.ref
                value = '10/31/2026'
                verified = $true
                source_ref = 'synthetic-suite'
            }
        
            Assert-True ($act.response.effect.matched -eq $true) 'Date field readback failed'
        }
        Run-Test '13 File input visible in the observation' {
            $files = @($script:obs.elements | Where-Object { $_.tag -eq 'input' -and $_.type -eq 'file' })
            Assert-True ($files.Count -gt 0) 'No file input found on Selenium page'
        }
        Run-Test '14 Upload synthetic PDF through owner-scoped artifact API' {
            $el = @($script:obs.elements | Where-Object { $_.tag -eq 'input' -and $_.type -eq 'file' -and $_.risk -eq 'ordinary' } | Select-Object -First 1)
            Assert-True ($el.Count -gt 0) 'No ordinary file input available'
            $pdfBase64 = (& docker compose -f compose.yaml -f compose.integrated.yaml exec -T api python -c 'import base64; from server.app import fixture_pdf; print(base64.b64encode(fixture_pdf()).decode())' | Out-String).Trim()
            Assert-True ($LASTEXITCODE -eq 0 -and $pdfBase64.Length -gt 50) 'Could not generate synthetic PDF from API image'
            $doc = @{subject=$subject;source_ref='synthetic-suite-pdf';file_name='synthetic-suite.pdf';mime_type='application/pdf';file_base64=$pdfBase64}
            $script:artifact = Invoke-Gz 'POST' "/contexts/$script:sid/artifacts" $doc
            Assert-True (-not [string]::IsNullOrEmpty($script:artifact.artifact_id)) 'No artifact ID'
            $act = Invoke-Action @{kind='upload';target_ref=$el[0].ref;artifact_id=$script:artifact.artifact_id;verified=$true;source_ref='synthetic-suite-pdf'}
            Assert-True ($act.response.effect.matched -eq $true) 'File attachment readback failed'
            $updated = @($script:obs.elements | Where-Object { $_.ref -eq $el[0].ref })
            Assert-True ($updated.Count -gt 0 -and $updated[0].file_count -ge 1) 'File was not observed as attached'
            Save-Page '02-after-multi-field-and-upload.jpg'
        }
        Run-Test '15 Password / human-auth field cannot be filled by generic agent (403)' {
            $el = @($script:obs.elements | Where-Object { $_.type -eq 'password' } | Select-Object -First 1)
            Assert-True ($el.Count -gt 0) 'Password input missing'
            $req = @{action_id=[guid]::NewGuid().ToString();observation_id=$script:obs.observation_id;kind='fill';target_ref=$el[0].ref;value='fake-password';verified=$true;source_ref='synthetic-suite'}
            Expect-HttpStatus 'POST' "/contexts/$script:sid/actions" $req 403
        }
        Run-Test '16 Generic final Submit click is denied (403)' {
            $el = @($script:obs.elements | Where-Object { $_.risk -eq 'irreversible' -and ($_.type -eq 'submit' -or $_.label -match 'submit') } | Select-Object -First 1)
            Assert-True ($el.Count -gt 0) 'No protected final Submit control was observed'
            $req = @{action_id=[guid]::NewGuid().ToString();observation_id=$script:obs.observation_id;kind='click';target_ref=$el[0].ref}
            Expect-HttpStatus 'POST' "/contexts/$script:sid/actions" $req 403
        }
        Run-Test '17 Read-only screenshot endpoint and audit events' {
            $view = Invoke-Gz 'GET' "/contexts/$script:sid/view"
            Assert-True ($view.screenshot_base64.Length -gt 1000) 'Viewer screenshot missing'
            $events = Invoke-Gz 'GET' "/contexts/$script:sid/events"
            Assert-True (@($events.events).Count -ge 2) 'Too few audit events'
            # The viewer does not invalidate action references.
            $probe = Invoke-Gz 'GET' "/contexts/$script:sid/observe"
            $script:obs = $probe
        }
        if (-not $SkipCrossSite) {
            Run-Test '18 Navigate to a second external HTTPS site without changing .env' {
                $act = Invoke-Action @{kind='navigate';url='https://example.org/';timeout_ms=15000}
                Assert-True ($script:obs.url -like 'https://example.org*') 'Cross-site navigation did not finish'
                Assert-True ($script:obs.title.Length -gt 0) 'Second website title missing'
                Save-Page '03-cross-site-navigation.jpg'
            }
        }
    }
    finally {
        Run-Test '19 Close browser context and release resources' {
            $closed = Invoke-Gz 'DELETE' "/contexts/$script:sid"
            Assert-True ($closed.state -eq 'closed') 'Context close was not acknowledged'
        }
    }
}

$reportPath = Join-Path $evidence 'results.json'
# Convert the generic List to an ordinary array before PowerShell pipeline filtering.
# Windows PowerShell 5.1 can throw "Argument types do not match" when wrapping
# System.Collections.Generic.List[object] directly with @(...).
$resultRows = $results.ToArray()
$passed = ($resultRows | Where-Object { $_.status -eq 'PASS' } | Measure-Object).Count
$failed = ($resultRows | Where-Object { $_.status -eq 'FAIL' } | Measure-Object).Count
$summary = [pscustomobject]@{
    at = [DateTime]::UtcNow.ToString('o')
    api = $api
    pass = [int]$passed
    fail = [int]$failed
    tests = $resultRows
    disclaimer = 'No LangGraph/LLM inference or real application final submission performed.'
}
$summary | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $reportPath
Write-Host "\nRESULT: $($summary.pass) passed, $($summary.fail) failed" -ForegroundColor Cyan
Write-Host "Screenshots and report: $evidence"
Write-Host 'Tests cover tool execution, not autonomous LLM reasoning or authorized government submission.'
if ($summary.fail -gt 0) { exit 1 }
