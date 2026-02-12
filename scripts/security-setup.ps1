# Security Setup and Scanning Script for Nigerian Tax Compliance Backend
# PowerShell version for Windows
# Run with: .\security-setup.ps1

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Security Setup - Nigerian Tax Compliance Backend" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# Step 1: Install main requirements with security packages
Write-Host "`nStep 1: Installing main requirements..." -ForegroundColor Yellow
pip install -r requirements-main.txt

# Step 2: Install development/security scanning tools
Write-Host "`nStep 2: Installing security scanning tools..." -ForegroundColor Yellow
pip install -r requirements-dev.txt

# Step 3: Create security reports directory
Write-Host "`nCreating security-reports directory..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "security-reports" | Out-Null

# Step 4: Run Bandit security scan
Write-Host "`nStep 3: Running Bandit security scan..." -ForegroundColor Yellow
Write-Host "Scanning Python code for security issues..."
bandit -r app/ -f json -o security-reports/bandit-report.json
bandit -r app/ -ll  # Show medium and high severity issues

# Step 5: Run Safety dependency check
Write-Host "`nStep 4: Running Safety dependency vulnerability scan..." -ForegroundColor Yellow
Write-Host "Checking dependencies for known vulnerabilities..."
safety check --json --output security-reports/safety-report.json
safety check --bare

# Step 6: Generate security report summary
Write-Host "`n================================================" -ForegroundColor Green
Write-Host "Security scans complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Reports generated in ./security-reports/"
Write-Host "  - bandit-report.json (code security issues)"
Write-Host "  - safety-report.json (dependency vulnerabilities)"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Review the security reports"
Write-Host "2. Fix any high/medium severity issues"
Write-Host "3. Configure Sentry for error monitoring"
Write-Host "4. Set up AWS Secrets Manager for production"
Write-Host "5. Implement rate limiting with SlowAPI"
Write-Host "6. Add input sanitization with Bleach"