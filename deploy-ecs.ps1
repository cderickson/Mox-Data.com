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

Test-RequiredCommand "aws"

$imageUri = "$AccountId.dkr.ecr.$Region.amazonaws.com/$Repository`:$ImageTag"
Write-Host "Using image: $imageUri" -ForegroundColor Cyan

# Resolve current task definition ARNs from services.
$webServiceTdArn = aws ecs describe-services `
  --region $Region `
  --cluster $Cluster `
  --services $WebService `
  --query "services[0].taskDefinition" `
  --output text
if ($LASTEXITCODE -ne 0) {
  throw "Failed to resolve current web service task definition."
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

if ([string]::IsNullOrWhiteSpace($webServiceTdArn) -or $webServiceTdArn -eq "None") {
  throw "Could not resolve task definition for web service '$WebService'."
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
  $webJson = $webRegisterPayload | ConvertTo-Json -Depth 100
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

  # Worker: register new task def revision with updated worker container image.
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
  $workerJson = $workerRegisterPayload | ConvertTo-Json -Depth 100
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
