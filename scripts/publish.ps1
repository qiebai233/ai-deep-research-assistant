#Requires -Version 5.1
<#
.SYNOPSIS
    One-command publisher: turn this working copy into a public GitHub repository
    and cut the first release tag.

.DESCRIPTION
    Steps (in order):
      1. Verify git is available and the working tree is clean.
      2. Replace the 'qiebai233' placeholder with -Owner
         (README, docs, .github, pyproject.toml, and the docs URL / User-Agent in src/).
      3. git init (if needed), git add -A, git commit.
      4. gh repo create <owner>/deepresearch --public --source . --push
         (falls back to printed manual commands when gh is missing).
      5. git tag <tag>, push the branch and the tag.
      6. Print the Actions and Release URLs.

    The script never creates the GitHub Release itself: pushing the tag triggers
    .github/workflows/release.yml, which builds the sdist/wheel and publishes the
    release with generated notes.

.PARAMETER Owner
    GitHub user or organisation name (required).

.PARAMETER Tag
    Release tag to create. Default: v0.1.0

.PARAMETER DryRun
    Print what would change/run without writing files or executing git/gh writes.

.PARAMETER SkipReplace
    Do not replace the placeholder (useful when it was already replaced).

.PARAMETER SkipCreate
    Do not run `gh repo create` (repository already exists on GitHub).

.EXAMPLE
    .\scripts\publish.ps1 -Owner qiebai233 -DryRun

.EXAMPLE
    .\scripts\publish.ps1 -Owner qiebai233

.NOTES
    If PowerShell blocks the script:
        powershell -ExecutionPolicy Bypass -File .\scripts\publish.ps1 -Owner <name>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')]
    [string]$Owner,

    [ValidatePattern('^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$Tag = 'v0.1.0',

    [switch]$DryRun,
    [switch]$SkipReplace,
    [switch]$SkipCreate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoName = 'deepresearch'
$Placeholder = 'qiebai233'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# Files/directories scanned for the placeholder (relative to the repo root).
$ReplaceTargets = @(
    'README.md',
    'README_EN.md',
    'CHANGELOG.md',
    'CONTRIBUTING.md',
    'SECURITY.md',
    'CODE_OF_CONDUCT.md',
    'pyproject.toml',
    'docs',
    '.github',
    'examples',
    'src/deepresearch/cli.py',
    'src/deepresearch/http.py'
)

# Publishing docs intentionally keep the placeholder in their examples.
$ReplaceExcluded = @('docs/publishing.md')

$ReplaceExtensions = @('.md', '.markdown', '.yml', '.yaml', '.toml', '.py', '.json', '.txt', '.sh')

function Write-Head([string]$Message) {
    Write-Host ''
    Write-Host "== $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "   [ok] $Message" -ForegroundColor Green
}

function Write-Note([string]$Message) {
    Write-Host "   $Message" -ForegroundColor DarkGray
}

function Write-WarnLine([string]$Message) {
    Write-Host "   [warn] $Message" -ForegroundColor Yellow
}

function Write-Fail([string]$Message) {
    Write-Host "   [fail] $Message" -ForegroundColor Red
}

# Run an external command, capturing output and exit code without letting a
# non-zero exit code abort the script (we decide what is fatal).
function Invoke-Capture {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$Arguments = @()
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $Command @Arguments 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{ Lines = $lines; Code = $code; Text = ($lines -join "`n") }
}

function Invoke-GitChecked {
    param([string[]]$Arguments = @())
    if ($DryRun) {
        Write-Note ('dry-run: git ' + ($Arguments -join ' '))
        return
    }
    $result = Invoke-Capture -Command 'git' -Arguments $Arguments
    if ($result.Code -ne 0) {
        throw ("git {0} failed (exit {1})`n{2}" -f ($Arguments -join ' '), $result.Code, $result.Text)
    }
}

function Invoke-GhChecked {
    param([string[]]$Arguments = @())
    if ($DryRun) {
        Write-Note ('dry-run: gh ' + ($Arguments -join ' '))
        return
    }
    $result = Invoke-Capture -Command 'gh' -Arguments $Arguments
    if ($result.Code -ne 0) {
        throw ("gh {0} failed (exit {1})`n{2}" -f ($Arguments -join ' '), $result.Code, $result.Text)
    }
}

function Get-RelativePath([string]$FullName) {
    $prefix = $RepoRoot.TrimEnd('\') + '\'
    if ($FullName.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        return $FullName.Substring($prefix.Length).Replace('\', '/')
    }
    return $FullName.Replace('\', '/')
}

function Get-PlaceholderFiles {
    $found = New-Object System.Collections.Generic.List[string]
    $seen = New-Object System.Collections.Generic.HashSet[string] ([StringComparer]::OrdinalIgnoreCase)
    foreach ($target in $ReplaceTargets) {
        $path = Join-Path $RepoRoot $target
        if (-not (Test-Path -LiteralPath $path)) {
            Write-WarnLine "replace target not found (skipped): $target"
            continue
        }
        $item = Get-Item -LiteralPath $path
        if ($item.PSIsContainer) {
            $files = Get-ChildItem -LiteralPath $item.FullName -Recurse -File -ErrorAction SilentlyContinue
        }
        else {
            $files = @($item)
        }
        foreach ($file in $files) {
            $relative = Get-RelativePath $file.FullName
            if ($ReplaceExcluded -contains $relative) { continue }
            if ($ReplaceExtensions -notcontains $file.Extension.ToLowerInvariant()) { continue }
            if ($relative -match '(^|/)(\.git|reports|\.deepresearch|\.venv|venv|__pycache__|node_modules|dist|build|\.test-tmp)/') { continue }
            if (-not $seen.Add($relative)) { continue }
            $text = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
            if ($text.Contains($Placeholder)) { $found.Add($file.FullName) }
        }
    }
    return $found
}

function Set-Placeholder {
    param([string]$OwnerName)
    $files = Get-PlaceholderFiles
    if ($files.Count -eq 0) {
        Write-Note 'placeholder not found (already replaced?) — nothing to do'
        return 0
    }
    if ($DryRun) {
        Write-Note ("dry-run: would replace '$Placeholder' -> '$OwnerName' in {0} file(s):" -f $files.Count)
        foreach ($file in $files) { Write-Note ("  - " + (Get-RelativePath $file)) }
        return $files.Count
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    foreach ($file in $files) {
        $text = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8)
        $updated = $text.Replace($Placeholder, $OwnerName)
        if ($updated -ne $text) {
            [System.IO.File]::WriteAllText($file, $updated, $utf8NoBom)
        }
    }
    Write-Ok ("replaced '$Placeholder' -> '$OwnerName' in {0} file(s)" -f $files.Count)
    return $files.Count
}

function Show-ManualCommands([string]$OwnerName, [string]$ReleaseTag, [string]$Branch) {
    Write-Head 'manual steps (no gh or no origin remote)'
    Write-Host @"
   cd "$RepoRoot"
   git remote add origin https://github.com/$OwnerName/$RepoName.git
   git push -u origin $Branch
   git tag -a $ReleaseTag -m "DeepResearch $ReleaseTag"
   git push origin $ReleaseTag

   Then open: https://github.com/$OwnerName/$RepoName/actions
   The Release workflow creates the GitHub Release from tag $ReleaseTag.
"@
}

# ---------------------------------------------------------------------------
# 1. Environment checks
# ---------------------------------------------------------------------------
Write-Head "DeepResearch publisher (owner: $Owner, tag: $Tag)"

if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'pyproject.toml'))) {
    Write-Fail "pyproject.toml not found in $RepoRoot — run this script from the repository."
    exit 1
}
Write-Ok "repository root: $RepoRoot"

$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCommand) {
    Write-Fail 'git is not installed or not on PATH.'
    Show-ManualCommands $Owner $Tag 'main'
    Write-Note 'No changes were made. Install Git and re-run this script.'
    exit 0
}
Write-Ok "git: $((Invoke-Capture -Command 'git' -Arguments @('--version')).Text)"

$isRepo = $false
$revParse = Invoke-Capture -Command 'git' -Arguments @('rev-parse', '--is-inside-work-tree')
if ($revParse.Code -eq 0 -and $revParse.Text.Trim() -eq 'true') { $isRepo = $true }

$branch = 'main'
if ($isRepo) {
    Write-Ok 'git repository detected'
    $dirty = Invoke-Capture -Command 'git' -Arguments @('status', '--porcelain')
    if ($dirty.Code -ne 0) {
        Write-Fail "git status failed: $($dirty.Text)"
        exit 1
    }
    if ($dirty.Text.Trim().Length -gt 0) {
        Write-Fail 'working tree is not clean. Commit or stash your changes first:'
        Write-Host $dirty.Text
        Write-Note 'Nothing was changed.'
        exit 1
    }
    $current = Invoke-Capture -Command 'git' -Arguments @('branch', '--show-current')
    if ($current.Code -eq 0 -and $current.Text.Trim().Length -gt 0) { $branch = $current.Text.Trim() }
    Write-Ok "working tree clean (branch: $branch)"
}
else {
    Write-WarnLine 'no git repository here yet — will run: git init -b main'
    $branch = 'main'
}

# ---------------------------------------------------------------------------
# 2. Placeholder replacement
# ---------------------------------------------------------------------------
Write-Head 'replace placeholder'
$replaced = 0
if ($SkipReplace) {
    Write-Note 'skipped (-SkipReplace)'
}
else {
    $replaced = Set-Placeholder $Owner
}

if ($DryRun) {
    Write-Head 'dry-run plan (nothing written)'
    $plan = @(
        'git init -b main   # only if not a repository yet'
        'git add -A'
        ('git commit -m "release: {0}"' -f $Tag)
        ('gh repo create {0}/{1} --public --source . --push' -f $Owner, $RepoName)
        ('git tag -a {0} -m "DeepResearch {0}"' -f $Tag)
        ('git push -u origin {0}' -f $branch)
        ('git push origin {0}' -f $Tag)
    )
    foreach ($line in $plan) { Write-Note $line }
    Write-Head 'dry-run finished'
    Write-Note 'No files were modified and no commands were executed.'
    exit 0
}

if ($replaced -eq 0 -and -not $SkipReplace) {
    Write-Note 'placeholder already replaced — continuing'
}

# ---------------------------------------------------------------------------
# 3. git init + commit
# ---------------------------------------------------------------------------
Write-Head 'commit'
if (-not $isRepo) {
    Invoke-GitChecked @('init', '-b', 'main')
    Write-Ok 'initialised repository (main)'
}
Invoke-GitChecked @('add', '-A')
$status = Invoke-Capture -Command 'git' -Arguments @('status', '--porcelain')
if ($status.Text.Trim().Length -gt 0) {
    Invoke-GitChecked @('commit', '-m', "release: $Tag")
    Write-Ok "committed: release: $Tag"
}
else {
    Write-Note 'nothing to commit — skipping'
}

# ---------------------------------------------------------------------------
# 4. create remote repository (if needed)
# ---------------------------------------------------------------------------
Write-Head 'GitHub repository'
$hasOrigin = $false
$remotes = Invoke-Capture -Command 'git' -Arguments @('remote')
if ($remotes.Code -eq 0 -and $remotes.Text -match '(?m)^origin$') { $hasOrigin = $true }

$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
$remoteReady = $hasOrigin

if ($hasOrigin) {
    Write-Ok 'remote "origin" already configured — skipping gh repo create'
}
elseif ($SkipCreate) {
    Write-Note 'skipped (-SkipCreate) but no origin remote exists'
}
elseif (-not $ghCommand) {
    Write-WarnLine 'GitHub CLI (gh) not found'
}
else {
    Push-Location $RepoRoot
    try {
        Invoke-GhChecked @('repo', 'create', "$Owner/$RepoName", '--public', '--source', '.', '--push')
        $remoteReady = $true
        Write-Ok "created and pushed https://github.com/$Owner/$RepoName"
    }
    catch {
        Write-WarnLine "gh repo create failed: $($_.Exception.Message)"
        Write-Note 'falling back to manual commands below'
    }
    finally {
        Pop-Location
    }
}

if (-not $remoteReady) {
    Show-ManualCommands $Owner $Tag $branch
    Write-Head 'done (manual steps required)'
    Write-Note 'Placeholder replacement and the local commit are complete; push manually as shown above.'
    exit 0
}

# ---------------------------------------------------------------------------
# 5. push branch + tag
# ---------------------------------------------------------------------------
Write-Head 'push and tag'
Invoke-GitChecked @('push', '-u', 'origin', $branch)
Write-Ok "pushed branch $branch"

$existingTags = Invoke-Capture -Command 'git' -Arguments @('tag', '-l', $Tag)
if ($existingTags.Text.Trim() -eq $Tag) {
    Write-WarnLine "tag $Tag already exists locally — reusing it"
}
else {
    Invoke-GitChecked @('tag', '-a', $Tag, '-m', "DeepResearch $Tag")
    Write-Ok "created tag $Tag"
}
Invoke-GitChecked @('push', 'origin', $Tag)
Write-Ok "pushed tag $Tag"

# ---------------------------------------------------------------------------
# 6. next steps
# ---------------------------------------------------------------------------
Write-Head 'done'
Write-Host ''
Write-Host '   Repository : ' -NoNewline
Write-Host "https://github.com/$Owner/$RepoName" -ForegroundColor Cyan
Write-Host '   Actions    : ' -NoNewline
Write-Host "https://github.com/$Owner/$RepoName/actions" -ForegroundColor Cyan
Write-Host '   Release    : ' -NoNewline
Write-Host "https://github.com/$Owner/$RepoName/releases/tag/$Tag" -ForegroundColor Cyan
Write-Host ''
Write-Note "The Release workflow builds the sdist/wheel for tag $Tag and creates the GitHub Release."
Write-Note 'If the Actions tab shows nothing, enable workflows under Settings -> Actions -> General.'
exit 0
