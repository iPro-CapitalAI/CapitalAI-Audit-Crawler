# sync.ps1 — run this when you're done working
cd "C:\Users\Administrator\Desktop\Capital AI\capital-ai-projects\CapitalAI-Audit-Crawler"
git add .
git commit -m "Session sync $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git push origin main
Write-Host "Synced to GitHub." -ForegroundColor Green