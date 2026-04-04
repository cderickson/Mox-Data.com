# deploy-ecs.ps1
# Deploy a new image tag to ECS web + worker services.
#
# Usage:
#   .\deploy-ecs.ps1 -Cluster "mox-data-cluster" -WebService "mox-data-web-service" -WorkerService "mox-data-worker-service-d5hj8z1o" -ImageTag "2026-03-25-01"
#
# Optional:
#   -Region "us-west-2" -AccountId "968362146563" -Repository "mox-data"

param(
  [Parameter(Mandatory=$true)] [string]$Cluster,
  [Parameter(Mandatory=$true)] [string]$WebService,
  [Parameter(Mandatory=$true)] [string]$WorkerService,
  [Parameter(Mandatory=$true)] [string]$ImageTag,
  [string]$WebBaseTaskDefinition = "",
  [string]$WorkerBaseTaskDefinition = "",
  [string]$MigrationContainerName = "web",
  [string]$MigrationCommand = "python -m flask db upgrade",
  [switch]$SkipMigration,
  [string]$Region = "us-west-2",
  [string]$AccountId = "968362146563",
  [string]$Repository = "mox-data"
)

$ErrorActionPreference = "Stop"

function Test-RequiredCommand([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $Name"
  }
}

function New-RegisterTaskDefPayload {
  param(
    [Parameter(Mandatory=$true)] $TaskDefObject
  )

  # Keep only fields accepted by register-task-definition.
  $allowedFields = @(
    "family",
    "taskRoleArn",
    "executionRoleArn",
    "networkMode",
    "containerDefinitions",
    "volumes",
    "placementConstraints",
    "requiresCompatibilities",
    "cpu",
    "memory",
    "tags",
    "pidMode",
    "ipcMode",
    "proxyConfiguration",
    "inferenceAccelerators",
    "ephemeralStorage",
    "runtimePlatform"
  )

  $payload = [ordered]@{}
  foreach ($field in $allowedFields) {
    $prop = $TaskDefObject.PSObject.Properties[$field]
    if ($null -ne $prop -and $null -ne $prop.Value) {
      $payload[$field] = $prop.Value
    }
  }

  return $payload
}

function Update-ContainerImageByName {
  param(
    [Parameter(Mandatory=$true)] $TaskDefObject,
    [Parameter(Mandatory=$true)] [string]$ContainerName,
    [Parameter(Mandatory=$true)] [string]$ImageUri
  )

  $found = $false
  foreach ($c in $TaskDefObject.containerDefinitions) {
    if ($c.name -eq $ContainerName) {
      $c.image = $ImageUri
      $found = $true
    }
  }

  if (-not $found) {
    throw "Container '$ContainerName' not found in task definition family '$($TaskDefObject.family)'."
  }
}

function Write-JsonFileNoBom {
  param(
    [Parameter(Mandatory=$true)] [string]$Path,
    [Parameter(Mandatory=$true)] [string]$Json
  )

  # AWS CLI can reject UTF-8 with BOM; write UTF-8 without BOM.
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Json, $utf8NoBom)
}

# Inline JSON loses double quotes when Windows forwards args to aws (aws.cmd / argument limits). Use file:// instead.
function Get-AwsCliFileUri {
  param([Parameter(Mandatory=$true)] [string]$Path)
  $full = [System.IO.Path]::GetFullPath($Path)
  # Windows AWS CLI (Python) mis-handles file:///C:/... (Errno 22). Use file://C:\path per AWS docs.
  if ($full -match '^[A-Za-z]:') {
    return "file://" + $full
  }
  $unix = $full -replace '\\', '/'
  return "file://$unix"
}

# describe-services often returns capacityProviderStrategy: null. @($null) in PowerShell is a 1-element array of null — do not use that for run-task.
function Get-ValidCapacityProviderStrategyEntries {
  param([Parameter(Mandatory=$true)] $WebServiceObject)
  $out = @()
  $raw = $WebServiceObject.capacityProviderStrategy
  if ($null -eq $raw) {
    return $out
  }
  foreach ($entry in @($raw)) {
    if ($null -eq $entry) {
      continue
    }
    $cp = $entry.capacityProvider
    if ([string]::IsNullOrWhiteSpace([string]$cp)) {
      continue
    }
    $out += $entry
  }
  return $out
}

function Invoke-EcsMigrationTask {
  param(
    [Parameter(Mandatory=$true)] [string]$Cluster,
    [Parameter(Mandatory=$true)] [string]$Region,
    [Parameter(Mandatory=$true)] [string]$TaskDefinitionArn,
    [Parameter(Mandatory=$true)] [string]$ContainerName,
    [Parameter(Mandatory=$true)] [string]$CommandString,
    [Parameter(Mandatory=$true)] $WebServiceObject
  )

  $commandParts = @($CommandString -split "\s+") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
  if ($commandParts.Count -eq 0) {
    throw "Migration command is empty."
  }

  # Do not pipe hashtables to ConvertTo-Json — IEnumerable is enumerated and output can be empty/wrong.
  $overridesPayload = @{
    containerOverrides = @(
      @{
        name = $ContainerName
        command = @($commandParts | ForEach-Object { [string]$_ })
      }
    )
  }
  $overridesJson = ConvertTo-Json -InputObject $overridesPayload -Compress -Depth 20
  if ([string]::IsNullOrWhiteSpace($overridesJson)) {
    throw "Internal error: failed to serialize ECS run-task overrides to JSON."
  }

  $tempDir = [System.IO.Path]::GetTempPath()
  $tempFiles = @()

  try {
    $overridesFile = Join-Path $tempDir ("mox-deploy-ecs-run-overrides-" + [Guid]::NewGuid().ToString("N") + ".json")
    $tempFiles += $overridesFile
    Write-JsonFileNoBom -Path $overridesFile -Json $overridesJson

    $runTaskArgs = @(
      "ecs", "run-task",
      "--region", $Region,
      "--cluster", $Cluster,
      "--task-definition", $TaskDefinitionArn,
      "--overrides", (Get-AwsCliFileUri $overridesFile),
      "--query", "tasks[0].taskArn",
      "--output", "text"
    )

    $awsvpc = $WebServiceObject.networkConfiguration.awsvpcConfiguration
    if ($null -ne $awsvpc) {
      $subnetIds = @($awsvpc.subnets | ForEach-Object { [string]$_ })
      $securityGroupIds = @($awsvpc.securityGroups | ForEach-Object { [string]$_ })
      $networkPayload = @{
        awsvpcConfiguration = @{
          subnets = $subnetIds
          securityGroups = $securityGroupIds
          assignPublicIp = [string]$awsvpc.assignPublicIp
        }
      }
      $networkConfigurationJson = ConvertTo-Json -InputObject $networkPayload -Compress -Depth 10
      if ([string]::IsNullOrWhiteSpace($networkConfigurationJson)) {
        throw "Internal error: failed to serialize ECS network configuration to JSON."
      }
      $networkFile = Join-Path $tempDir ("mox-deploy-ecs-run-network-" + [Guid]::NewGuid().ToString("N") + ".json")
      $tempFiles += $networkFile
      Write-JsonFileNoBom -Path $networkFile -Json $networkConfigurationJson
      $runTaskArgs += @("--network-configuration", (Get-AwsCliFileUri $networkFile))
    }

    $capacityProviderStrategy = Get-ValidCapacityProviderStrategyEntries -WebServiceObject $WebServiceObject
    if ($capacityProviderStrategy.Count -gt 0) {
      $capacityProviderJson = ConvertTo-Json -InputObject $capacityProviderStrategy -Compress -Depth 10
      if ([string]::IsNullOrWhiteSpace($capacityProviderJson)) {
        throw "Internal error: failed to serialize capacity provider strategy to JSON."
      }
      $capacityFile = Join-Path $tempDir ("mox-deploy-ecs-run-capacity-" + [Guid]::NewGuid().ToString("N") + ".json")
      $tempFiles += $capacityFile
      Write-JsonFileNoBom -Path $capacityFile -Json $capacityProviderJson
      $runTaskArgs += @("--capacity-provider-strategy", (Get-AwsCliFileUri $capacityFile))
    } elseif (-not [string]::IsNullOrWhiteSpace($WebServiceObject.launchType)) {
      $runTaskArgs += @("--launch-type", $WebServiceObject.launchType)
    }

    Write-Host "Starting migration task using task definition: $TaskDefinitionArn" -ForegroundColor Yellow
    $taskArn = & aws @runTaskArgs
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($taskArn) -or $taskArn -eq "None") {
      throw "Failed to start ECS migration task."
    }
    Write-Host "Migration task started: $taskArn"

    & aws ecs wait tasks-stopped `
      --region $Region `
      --cluster $Cluster `
      --tasks $taskArn
    if ($LASTEXITCODE -ne 0) {
      throw "Migration task did not reach STOPPED state successfully."
    }

    $taskRaw = aws ecs describe-tasks `
      --region $Region `
      --cluster $Cluster `
      --tasks $taskArn `
      --query "tasks[0]" `
      --output json
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to describe migration task: $taskArn"
    }

    $taskObj = $taskRaw | ConvertFrom-Json
    $migrationContainer = @($taskObj.containers | Where-Object { $_.name -eq $ContainerName }) | Select-Object -First 1
    if ($null -eq $migrationContainer) {
      throw "Migration container '$ContainerName' was not found in task '$taskArn'."
    }

    $exitCode = $migrationContainer.exitCode
    if ($null -eq $exitCode -or [int]$exitCode -ne 0) {
      $reason = $migrationContainer.reason
      $stoppedReason = $taskObj.stoppedReason
      throw "Migration failed (exitCode=$exitCode). Container reason='$reason'. Task stoppedReason='$stoppedReason'."
    }

    Write-Host "Migration task completed successfully." -ForegroundColor Green
  }
  finally {
    foreach ($f in $tempFiles) {
      if (Test-Path $f) {
        Remove-Item $f -Force -ErrorAction SilentlyContinue
      }
    }
  }
}

Test-RequiredCommand "aws"

$imageUri = "$AccountId.dkr.ecr.$Region.amazonaws.com/$Repository`:$ImageTag"
Write-Host "Using image: $imageUri" -ForegroundColor Cyan

# Resolve web service details and current task definition ARN.
$webServiceRaw = aws ecs describe-services `
  --region $Region `
  --cluster $Cluster `
  --services $WebService `
  --query "services[0]" `
  --output json
if ($LASTEXITCODE -ne 0) {
  throw "Failed to describe web service '$WebService'."
}

$webServiceObj = $webServiceRaw | ConvertFrom-Json
$webServiceTdArn = $webServiceObj.taskDefinition
if ([string]::IsNullOrWhiteSpace($webServiceTdArn) -or $webServiceTdArn -eq "None") {
  throw "Could not resolve task definition for web service '$WebService'."
}

$workerServiceTdArn = aws ecs describe-services `
  --region $Region `
  --cluster $Cluster `
  --services $WorkerService `
  --query "services[0].taskDefinition" `
  --output text
if ($LASTEXITCODE -ne 0) {
  throw "Failed to resolve current worker service task definition."
}

if ([string]::IsNullOrWhiteSpace($workerServiceTdArn) -or $workerServiceTdArn -eq "None") {
  throw "Could not resolve task definition for worker service '$WorkerService'."
}

$webTdArn = if ([string]::IsNullOrWhiteSpace($WebBaseTaskDefinition)) { $webServiceTdArn } else { $WebBaseTaskDefinition }
$workerTdArn = if ([string]::IsNullOrWhiteSpace($WorkerBaseTaskDefinition)) { $workerServiceTdArn } else { $WorkerBaseTaskDefinition }

Write-Host "Web service current task def:    $webServiceTdArn"
Write-Host "Worker service current task def: $workerServiceTdArn"
Write-Host "Web base task def for cloning:   $webTdArn"
Write-Host "Worker base task def for cloning:$workerTdArn"

# Temp files.
$webPayloadFile = "web-td-register.json"
$workerPayloadFile = "worker-td-register.json"

try {
  # Web: register new task def revision with updated web container image.
  $webTdRaw = aws ecs describe-task-definition `
    --region $Region `
    --task-definition $webTdArn `
    --query "taskDefinition" `
    --output json
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to describe web task definition: $webTdArn"
  }

  $webTdObj = $webTdRaw | ConvertFrom-Json
  Update-ContainerImageByName -TaskDefObject $webTdObj -ContainerName "web" -ImageUri $imageUri

  $webRegisterPayload = New-RegisterTaskDefPayload -TaskDefObject $webTdObj
  $webJson = ConvertTo-Json -InputObject $webRegisterPayload -Depth 100
  Write-JsonFileNoBom -Path $webPayloadFile -Json $webJson

  $newWebTdArn = aws ecs register-task-definition `
    --region $Region `
    --cli-input-json ("file://$webPayloadFile") `
    --query "taskDefinition.taskDefinitionArn" `
    --output text
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($newWebTdArn)) {
    throw "Failed to register new web task definition from payload file '$webPayloadFile'."
  }

  Write-Host "Registered new web task definition: $newWebTdArn" -ForegroundColor Green

  if (-not $SkipMigration) {
    Invoke-EcsMigrationTask `
      -Cluster $Cluster `
      -Region $Region `
      -TaskDefinitionArn $newWebTdArn `
      -ContainerName $MigrationContainerName `
      -CommandString $MigrationCommand `
      -WebServiceObject $webServiceObj
  } else {
    Write-Host "Skipping migration step because -SkipMigration was provided." -ForegroundColor Yellow
  }

  # Worker: register after migration so a failed migration does not leave an extra worker task def revision.
  $workerTdRaw = aws ecs describe-task-definition `
    --region $Region `
    --task-definition $workerTdArn `
    --query "taskDefinition" `
    --output json
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to describe worker task definition: $workerTdArn"
  }

  $workerTdObj = $workerTdRaw | ConvertFrom-Json
  Update-ContainerImageByName -TaskDefObject $workerTdObj -ContainerName "worker" -ImageUri $imageUri

  $workerRegisterPayload = New-RegisterTaskDefPayload -TaskDefObject $workerTdObj
  $workerJson = ConvertTo-Json -InputObject $workerRegisterPayload -Depth 100
  Write-JsonFileNoBom -Path $workerPayloadFile -Json $workerJson

  $newWorkerTdArn = aws ecs register-task-definition `
    --region $Region `
    --cli-input-json ("file://$workerPayloadFile") `
    --query "taskDefinition.taskDefinitionArn" `
    --output text
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($newWorkerTdArn)) {
    throw "Failed to register new worker task definition from payload file '$workerPayloadFile'."
  }

  Write-Host "Registered new worker task definition: $newWorkerTdArn" -ForegroundColor Green

  # Update services.
  aws ecs update-service `
    --region $Region `
    --cluster $Cluster `
    --service $WebService `
    --task-definition $newWebTdArn `
    --force-new-deployment | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to update web service '$WebService' to task definition '$newWebTdArn'."
  }

  aws ecs update-service `
    --region $Region `
    --cluster $Cluster `
    --service $WorkerService `
    --task-definition $newWorkerTdArn `
    --force-new-deployment | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to update worker service '$WorkerService' to task definition '$newWorkerTdArn'."
  }

  Write-Host "Service updates submitted. Waiting for stability..." -ForegroundColor Yellow

  aws ecs wait services-stable `
    --region $Region `
    --cluster $Cluster `
    --services $WebService $WorkerService
  if ($LASTEXITCODE -ne 0) {
    throw "Services failed to reach stable state."
  }

  Write-Host "Deployment complete. Both services are stable." -ForegroundColor Green
}
finally {
  foreach ($f in @($webPayloadFile, $workerPayloadFile)) {
    if (Test-Path $f) { Remove-Item $f -Force }
  }
}
