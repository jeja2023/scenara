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
$tenantId = "drill" + $drillId.Substring(0, 24)
$projectId = "qualification"
$assetId = "ast_" + $drillId
$runId = "run_" + $drillId
$pipelineId = "qualification.restore." + $drillId
$modelId = "qualification.restore." + $drillId
$identityId = "pid_" + $drillId
$mediaObjectKey = "qualification/media/$drillId.bin"
$resultObjectKey = "qualification/results/$drillId.json"
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
    $seededAt = Get-Date
    $seedSql = @"
DROP TABLE IF EXISTS qualification_backup_marker;
CREATE TABLE qualification_backup_marker(value text PRIMARY KEY);
INSERT INTO qualification_backup_marker VALUES ('$marker');
INSERT INTO scenara_organizations
    (tenant_id, display_name, created_at, updated_at, document)
VALUES
    ('$tenantId', 'Backup drill', now(), now(), jsonb_build_object('marker', '$marker'));
INSERT INTO scenara_projects
    (tenant_id, project_id, display_name, created_at, updated_at, document)
VALUES
    ('$tenantId', '$projectId', 'Qualification', now(), now(), jsonb_build_object('marker', '$marker'));
INSERT INTO scenara_media_assets
    (tenant_id, project_id, asset_id, created_at, document)
VALUES
    ('$tenantId', '$projectId', '$assetId', now(), jsonb_build_object('marker', '$marker', 'object_key', '$mediaObjectKey'));
INSERT INTO scenara_pipeline_versions
    (pipeline_id, version, domain, status, definition, definition_sha256)
VALUES
    ('$pipelineId', '1.0.0', 'ocr', 'draft', jsonb_build_object('marker', '$marker'), repeat('a', 64));
INSERT INTO scenara_model_packages
    (model_id, version, capability, adapter, sha256, license_id, source_uri, vram_mb, production_ready, manifest)
VALUES
    ('$modelId', '1.0.0', 'backup-drill', 'test', repeat('b', 64), 'Proprietary', 'internal://backup-drill', 0, false, jsonb_build_object('marker', '$marker'));
INSERT INTO scenara_runs
    (tenant_id, project_id, run_id, domain, status, revision, priority, created_at, updated_at, document)
VALUES
    ('$tenantId', '$projectId', '$runId', 'ocr', 'completed', 1, 0, now(), now(), jsonb_build_object('marker', '$marker'));
INSERT INTO scenara_run_results
    (tenant_id, project_id, run_id, domain, schema_version, object_key, sha256, unit_count, created_at, summary)
VALUES
    ('$tenantId', '$projectId', '$runId', 'ocr', '1.0', '$resultObjectKey', repeat('c', 64), 1, now(), jsonb_build_object('marker', '$marker'));
INSERT INTO scenara_audit_events
    (tenant_id, project_id, principal_id, action, resource_type, resource_id, outcome, evidence)
VALUES
    ('$tenantId', '$projectId', 'backup-drill', 'backup.verify', 'backup', '$drillId', 'success', jsonb_build_object('marker', '$marker'));
INSERT INTO scenara_portrait_identities
    (tenant_id, project_id, identity_id, display_name, created_at, updated_at, document)
VALUES
    ('$tenantId', '$projectId', '$identityId', 'Backup drill identity', now(), now(), jsonb_build_object('marker', '$marker'));
"@
    docker exec $PostgresContainer psql -U scenara -d scenara -v ON_ERROR_STOP=1 -c $seedSql | Out-Null
    Assert-ExitCode "PostgreSQL seed"
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        -e "MARKER=$objectValue" -e "MEDIA_KEY=$mediaObjectKey" -e "RESULT_KEY=$resultObjectKey" `
        --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && printf "%s" "$MARKER" | mc pipe local/scenara/qualification/marker.txt && printf "media-%s" "$MARKER" | mc pipe "local/scenara/$MEDIA_KEY" && printf "{\"marker\":\"%s\"}" "$MARKER" | mc pipe "local/scenara/$RESULT_KEY"' | Out-Null
    Assert-ExitCode "MinIO seed"

    docker exec $PostgresContainer pg_dump -U scenara -d scenara --format=custom --file=$dumpInContainer
    Assert-ExitCode "PostgreSQL backup"
    docker cp "$($PostgresContainer):$dumpInContainer" $dumpPath | Out-Null
    Assert-ExitCode "PostgreSQL backup copy"
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        -v "$($minioRoot):/backup" --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc mirror --overwrite local/scenara /backup' | Out-Null
    Assert-ExitCode "MinIO backup"
    $backupCompletedAt = Get-Date

    $cleanupSql = @"
DELETE FROM scenara_portrait_identities WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND identity_id = '$identityId';
DELETE FROM scenara_audit_events WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND resource_id = '$drillId';
DELETE FROM scenara_run_results WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND run_id = '$runId';
DELETE FROM scenara_runs WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND run_id = '$runId';
DELETE FROM scenara_media_assets WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND asset_id = '$assetId';
DELETE FROM scenara_model_packages WHERE model_id = '$modelId' AND version = '1.0.0';
DELETE FROM scenara_pipeline_versions WHERE pipeline_id = '$pipelineId' AND version = '1.0.0';
DELETE FROM scenara_projects WHERE tenant_id = '$tenantId' AND project_id = '$projectId';
DELETE FROM scenara_organizations WHERE tenant_id = '$tenantId';
DROP TABLE IF EXISTS qualification_backup_marker;
"@
    docker exec $PostgresContainer psql -U scenara -d scenara -v ON_ERROR_STOP=1 -c $cleanupSql | Out-Null
    Assert-ExitCode "PostgreSQL mutation"
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        -e "MEDIA_KEY=$mediaObjectKey" -e "RESULT_KEY=$resultObjectKey" --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc rm local/scenara/qualification/marker.txt "local/scenara/$MEDIA_KEY" "local/scenara/$RESULT_KEY"' | Out-Null
    Assert-ExitCode "MinIO mutation"
    $recoveryStartedAt = Get-Date

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
    $entityCounts = (docker exec $PostgresContainer psql -U scenara -d scenara -tAc `
        "SELECT concat_ws('|', (SELECT count(*) FROM scenara_organizations WHERE tenant_id = '$tenantId'), (SELECT count(*) FROM scenara_projects WHERE tenant_id = '$tenantId' AND project_id = '$projectId'), (SELECT count(*) FROM scenara_media_assets WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND asset_id = '$assetId'), (SELECT count(*) FROM scenara_runs WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND run_id = '$runId'), (SELECT count(*) FROM scenara_run_results WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND run_id = '$runId'), (SELECT count(*) FROM scenara_pipeline_versions WHERE pipeline_id = '$pipelineId' AND version = '1.0.0'), (SELECT count(*) FROM scenara_model_packages WHERE model_id = '$modelId' AND version = '1.0.0'), (SELECT count(*) FROM scenara_audit_events WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND resource_id = '$drillId'), (SELECT count(*) FROM scenara_portrait_identities WHERE tenant_id = '$tenantId' AND project_id = '$projectId' AND identity_id = '$identityId'))").Trim()
    Assert-ExitCode "Business entity verification"
    $objectRestored = (docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" `
        -e "SECRET_KEY=$S3SecretKey" -e "MEDIA_KEY=$mediaObjectKey" -e "RESULT_KEY=$resultObjectKey" `
        --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc cat local/scenara/qualification/marker.txt && mc stat "local/scenara/$MEDIA_KEY" >/dev/null && mc stat "local/scenara/$RESULT_KEY" >/dev/null').Trim()
    Assert-ExitCode "MinIO verification"
    if ($databaseValue -ne $marker -or $objectRestored -ne $objectValue -or $entityCounts -ne "1|1|1|1|1|1|1|1|1") {
        throw "restored marker values do not match the backup"
    }
    $recoveryCompletedAt = Get-Date
    $dumpHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $dumpPath).Hash.ToLowerInvariant()
    $rpoSeconds = [math]::Round(($backupCompletedAt - $seededAt).TotalSeconds, 3)
    $rtoSeconds = [math]::Round(($recoveryCompletedAt - $recoveryStartedAt).TotalSeconds, 3)
    Write-Output "backup_restore=passed"
    Write-Output "postgres_marker=$databaseValue"
    Write-Output "minio_marker=$objectRestored"
    Write-Output "entities_verified=tenants,projects,media,runs,results,pipelines,models,audit,biometrics"
    Write-Output "entity_counts=$entityCounts"
    Write-Output "rpo_seconds=$rpoSeconds"
    Write-Output "rto_seconds=$rtoSeconds"
    Write-Output "postgres_dump_sha256=$dumpHash"
}
finally {
    docker exec $PostgresContainer rm -f $dumpInContainer $restoreInContainer 2>$null | Out-Null
    if ($cleanupSql) {
        docker exec $PostgresContainer psql -U scenara -d scenara -c $cleanupSql 2>$null | Out-Null
    }
    docker run --rm --network $DockerNetwork -e "ACCESS_KEY=$S3AccessKey" -e "SECRET_KEY=$S3SecretKey" `
        -e "MEDIA_KEY=$mediaObjectKey" -e "RESULT_KEY=$resultObjectKey" --entrypoint /bin/sh $mcImage -c `
        'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc rm --force local/scenara/qualification/marker.txt "local/scenara/$MEDIA_KEY" "local/scenara/$RESULT_KEY"' 2>$null | Out-Null
    if (Test-Path -LiteralPath $resolvedRoot) {
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    }
}
