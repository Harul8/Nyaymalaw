# Launcher for the code-review-graph MCP server.
#
# Exists for two reasons, both measured on 9 September 2026:
#
# 1. Semantic search embeds the QUERY at search time, not only the nodes at
#    index time. The server process therefore needs the same OpenAI credentials
#    the `embed` run used, or `semantic_search_nodes_tool` degrades to
#    search_mode "none" -- which reads exactly like "not in the codebase"
#    (defect shape S3). The key is read from .env, which is gitignored; .mcp.json
#    is tracked and must never carry it.
#
# 2. Norton injects SSLKEYLOGFILE into the process environment as a device path
#    (\\.\nllMonFltProxy\<hex>). CPython's ssl.create_default_context() hands
#    that straight to OpenSSL as a FILE*, and the process aborts on the first
#    TLS call with "OPENSSL_Uplink(...,08): no OPENSSL_Applink". Clearing the
#    variable is the whole fix -- CPython tests it for truthiness, so empty
#    reads as unset.
#
# Nothing here may write to stdout: this is a stdio MCP server and any stray
# line corrupts the protocol stream.

$ErrorActionPreference = 'Stop'

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $repo '.env'

if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*NM_MODEL_API_KEY\s*=\s*(.+?)\s*$') {
            $env:CRG_OPENAI_API_KEY = $Matches[1].Trim('"')
        }
        elseif ($line -match '^\s*NM_EMBED_MODEL\s*=\s*(.+?)\s*$') {
            $env:CRG_OPENAI_MODEL = $Matches[1].Trim('"')
        }
    }
}

if (-not $env:CRG_OPENAI_BASE_URL) {
    $env:CRG_OPENAI_BASE_URL = 'https://api.openai.com/v1'
}
$env:CRG_ACCEPT_CLOUD_EMBEDDINGS = '1'
$env:SSLKEYLOGFILE = ''

uvx code-review-graph serve
