@echo off
cd /d "C:\Users\Administrator\Desktop\Capital AI\capital-ai-projects\CapitalAI-Audit-Crawler"
git add .
git commit -m "Session sync %date% %time%"
git push origin main
echo.
echo Synced to GitHub.
pause