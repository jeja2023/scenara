param(
    [Parameter(Mandatory = $true)] [string] $PostgresContainer,
    [Parameter(Mandatory = $true)] [string] $DockerNetwork,
    [Parameter(Mandatory = $true)] [string] $S3AccessKey,
    [Parameter(Mandatory = $true)] [string] $S3SecretKey
)

$ErrorActionPreference = "Stop"
$drillId = [guid]::NewGuid().ToString("N")
$drillRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("scenara-backup-drill-" + $drillId)
$minioRoot = Join-Path $drillRoot "minio"
$dumpPath = Join-Path $drillRoot "postgres.dump"
$dumpInContainer = "/tmp/scenara-backup-drill.dump"
$restoreInContainer = "/tmp/scenara-backup-drill-restore.dump"
$marker = "scenara-backup-ok-" + $drillId
$objectValue = "scenara-object-ok-" + $drillId
$mcImage = "minio/mc:RELEASE.2025-07-21T05-28-08Z"

function Assert-ExitCode([string] $Action) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE"
    }
}

New-Item -ItemType Directory -Path $minioRoot -Force | Out-Null
$resolvedRoot = (Resolve-Path -LiteralPath $drillRoot).Path
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if (-not $resolvedRoot.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "backup drill directory is outside the system temporary directory"
}

try {
    docker exec $PostgresContainer psql -U scenara -d scenara -v ON_ERROR_STOP=1 -c `
        "DROP TABLE IF EXISTS qualification_backup_marker; CREATE TABLE qualification_backup_marker(value text PRIMARY KEY); INSERT INTO qualification_backup_marker VALUES ('$marker');" | Out-Null
    Assert-ExitCode "PostgreSQL seed"
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        -e "MARKER=$objectValue" --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && printf "%s" "$MARKER" | mc pipe local/scenara/qualification/marker.txt' | Out-Null
    Assert-ExitCode "MinIO seed"

    docker exec $PostgresContainer pg_dump -U scenara -d scenara --format=custom --file=$dumpInContainer
    Assert-ExitCode "PostgreSQL backup"
    docker cp "$($PostgresContainer):$dumpInContainer" $dumpPath | Out-Null
    Assert-ExitCode "PostgreSQL backup copy"
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        -v "$($minioRoot):/backup" --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc mirror --overwrite local/scenara /backup' | Out-Null
    Assert-ExitCode "MinIO backup"

    docker exec $PostgresContainer psql -U scenara -d scenara -v ON_ERROR_STOP=1 -c `
        "DROP TABLE qualification_backup_marker;" | Out-Null
    Assert-ExitCode "PostgreSQL mutation"
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc rm local/scenara/qualification/marker.txt' | Out-Null
    Assert-ExitCode "MinIO mutation"

    docker cp $dumpPath "$($PostgresContainer):$restoreInContainer" | Out-Null
    Assert-ExitCode "PostgreSQL restore copy"
    docker exec $PostgresContainer pg_restore -U scenara -d scenara --clean --if-exists --no-owner `
        --no-privileges --exit-on-error $restoreInContainer
    Assert-ExitCode "PostgreSQL restore"
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        -v "$($minioRoot):/backup:ro" --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc mirror --overwrite --remove /backup local/scenara' | Out-Null
    Assert-ExitCode "MinIO restore"

    $databaseValue = (docker exec $PostgresContainer psql -U scenara -d scenara -tAc `
        "SELECT value FROM qualification_backup_marker").Trim()
    Assert-ExitCode "PostgreSQL verification"
    $objectRestored = (docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" `
        -e "SECRET_KEY=$S3SecretKey" --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc cat local/scenara/qualification/marker.txt').Trim()
    Assert-ExitCode "MinIO verification"
    if ($databaseValue -ne $marker -or $objectRestored -ne $objectValue) {
        throw "restored marker values do not match the backup"
    }
    $dumpHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $dumpPath).Hash.ToLowerInvariant()
    Write-Output "backup_restore=passed"
    Write-Output "postgres_marker=$databaseValue"
    Write-Output "minio_marker=$objectRestored"
    Write-Output "postgres_dump_sha256=$dumpHash"
}
finally {
    docker exec $PostgresContainer rm -f $dumpInContainer $restoreInContainer 2>$null | Out-Null
    docker exec $PostgresContainer psql -U scenara -d scenara -c `
        "DROP TABLE IF EXISTS qualification_backup_marker;" 2>$null | Out-Null
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc rm --force local/scenara/qualification/marker.txt' 2>$null | Out-Null
    if (Test-Path -LiteralPath $resolvedRoot) {
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    }
}
