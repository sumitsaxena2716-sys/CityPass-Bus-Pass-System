$ErrorActionPreference = "Stop"

Write-Host "`n========== 1. PYTHON ENVIRONMENT ==========" -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) { throw "Python environment check failed." }

Write-Host "`n========== 2. FULL TEST SUITE + COVERAGE ==========" -ForegroundColor Cyan
python -m pytest -q --cov=app --cov-report=term-missing
if ($LASTEXITCODE -ne 0) { throw "Tests failed. Review failures before proceeding." }

Write-Host "`n========== 3. DEPENDENCY SECURITY AUDIT ==========" -ForegroundColor Cyan
python -m pip_audit -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency audit failed or reported vulnerabilities." }

Write-Host "`n========== 4. GIT WHITESPACE CHECKS ==========" -ForegroundColor Cyan
git diff --check
if ($LASTEXITCODE -ne 0) { throw "Unstaged diff check failed." }

git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Staged diff check failed." }

Write-Host "`n========== 5. GIT STATUS ==========" -ForegroundColor Cyan
git status
if ($LASTEXITCODE -ne 0) { throw "Git status failed." }

Write-Host "`n========== ALL CHECKS COMPLETED SUCCESSFULLY ==========" -ForegroundColor Green
