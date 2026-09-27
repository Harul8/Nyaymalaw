param([Parameter(Mandatory=$true)][string]$Repository)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath $Repository).Path.TrimEnd('\','/')
$manifestPath = Join-Path $taskRoot 'assurance/common/journey_layout.json'
$taskManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$taskPrefix = $taskRoot + [IO.Path]::DirectorySeparatorChar
$targets = @{}
# Validate EVERY resolved target and byte identity before moving ANY file.
foreach ($entry in $taskManifest.moves) {
    $source = [IO.Path]::GetFullPath((Join-Path $taskRoot $entry.old_path))
    $target = [IO.Path]::GetFullPath((Join-Path $taskRoot $entry.path))
    if (-not $source.StartsWith($taskPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        -not $target.StartsWith($taskPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Move escapes the intended repository: $source -> $target"
    }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or
        (Test-Path -LiteralPath $target) -or $targets.ContainsKey($target)) {
        throw "Missing source, occupied target or duplicate destination: $target"
    }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        $entry.sha256_before) {
        throw "Concurrent edit after inventory: $source"
    }
    $targets[$target] = $true
}
foreach ($entry in $taskManifest.moves) {
    $source = [IO.Path]::GetFullPath((Join-Path $taskRoot $entry.old_path))
    $target = [IO.Path]::GetFullPath((Join-Path $taskRoot $entry.path))
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
    Move-Item -LiteralPath $source -Destination $target
}
Write-Output ("Moved {0} individually verified files" -f $taskManifest.moves.Count)
