$baseUrl = "https://antigravity-production-c355.up.railway.app"

# Send B2 webhook
Write-Host "=== SENDING B2 WEBHOOK ===" -ForegroundColor Cyan
$b2 = @{ pass = "ANTIGRAVITY_KEY"; engine = "B2"; symbol = "ETHUSDT"; side = "BUY" } | ConvertTo-Json
try {
    $r = Invoke-WebRequest -Uri "$baseUrl/webhook" -Method POST -Body $b2 -ContentType "application/json" -TimeoutSec 15 -UseBasicParsing
    Write-Host "Response: $($r.Content)"
}
catch {
    Write-Host "HTTP Error: $($_.Exception.Message)" -ForegroundColor Red
}

# Wait for background task
Start-Sleep -Seconds 5

# Check health with last_error
Write-Host ""
Write-Host "=== HEALTH + LAST_ERROR ===" -ForegroundColor Cyan
try {
    $h = Invoke-WebRequest -Uri "$baseUrl/" -TimeoutSec 10 -UseBasicParsing
    Write-Host "Body: $($h.Content)"
}
catch {
    Write-Host "Health Error: $($_.Exception.Message)" -ForegroundColor Red
}
