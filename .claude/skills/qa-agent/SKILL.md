---
name: qa-agent
description: This skill should be used when the user asks to "run QA", "quality check", "review code quality", "check the app", or wants a quality assurance review of the application.
version: 1.0.0
allowed-tools: Read, Bash, Grep, Glob
user-invocable: true
---

# QA Agent — LinDriveSpace

Perform quality assurance checks on LinDriveSpace at `/home/user/projects/lindrivespace`.

## Responsibilities

### 1. Code Quality Review

Read all source files and check for:
- Unused imports or dead code
- Hardcoded values that should be in config/env
- Missing error handling on I/O and external calls
- Consistent code style and naming conventions
- Proper input validation and output escaping
- Security issues (injection, XSS, exposed secrets)

### 2. Data Integrity

Load and validate all data/config files:
- Parse without errors
- Required fields present and correctly typed
- No duplicates where uniqueness is expected
- Cross-references between files are consistent
- No orphaned or stale data

### 3. Route / Endpoint Verification

Use the app's test client or HTTP requests to verify:
- All defined routes return expected status codes
- API endpoints return valid response formats
- Error endpoints return appropriate error codes
- Authentication/authorization is enforced where expected

### 4. Dependency Check

- Verify all imports resolve (no missing packages)
- Check for known security vulnerabilities in dependencies
- Verify lock files are in sync with dependency manifests

## Output

Present findings as a checklist:
- PASS or FAIL for each check
- Details on any failures with file paths and line numbers
- Summary with total pass/fail count
