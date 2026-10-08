param(
    [double]$Horas = 6,
    [int]$Lote = 10,
    [switch]$Logar,
    [string]$Tema = ""
)

$ErrorActionPreference = "Continue"
$env:PYTHONUNBUFFERED = "1"

Write-Host "== Loop noturno: $Horas h (lote=$Lote) ==" -ForegroundColor Cyan
Write-Host "A saida dos agentes aparece AO VIVO abaixo."

Write-Host "Impedindo suspensao/hibernacao do PC..."
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Write-Host "Aquecendo o Ollama..."
ollama run qwen3.5:9b "ok" | Out-Null

if ($Tema -ne "") {
    Write-Host "Semeando o vault com o tema: $Tema"
    uv run python -m src.main run --tema $Tema
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$transcript = "data\output\console-$stamp.log"

Write-Host ""
Write-Host "Iniciando daemon ($Horas h). Ctrl+C encerra." -ForegroundColor Yellow
Write-Host ""

if ($Logar) {
    uv run python -m src.main pesquisar --horas $Horas --lote $Lote 2>&1 |
        Tee-Object -FilePath $transcript
} else {
    uv run python -m src.main pesquisar --horas $Horas --lote $Lote
}

Write-Host ""
Write-Host "Concluido." -ForegroundColor Green
Write-Host "  Loop log:  data\output\loop-*.log"
Write-Host "  Saidas:    data\output\pesquisa-*.md"
Write-Host "  Vault:     data\vault\  (abra no Obsidian)"
if ($Logar) { Write-Host "  Console:   $transcript" }
