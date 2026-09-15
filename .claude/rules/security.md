---
paths:
  - "**/*"
---

# Universal Security Rules (2026)

## Secrets & Credentials
1. NEVER log, commit, or store secrets (.env, API keys, tokens, passwords)
2. NEVER commit .env files — always .gitignore them
3. Use environment variables or a secrets manager for all credentials
4. PostToolUse hooks SHOULD warn on edits to .env*, secrets, or migration files

## Input & Output
5. Validate all external input at system boundaries (use schema validation — e.g., Zod, JSON Schema, or language-native equivalents)
6. Use parameterized queries for database access (no string concatenation)
7. Sanitize output to prevent XSS
8. Use standardized error responses: `{ code, message, details? }` — never leak stack traces to clients

## Dependencies & Access
9. Follow OWASP Top 10 guidelines
10. Review dependencies for known vulnerabilities before adding
11. Use least-privilege principles for file/network access
12. Apply rate limiting on public-facing endpoints

## Enforcement
- Security rules can be enforced via PreToolUse hooks (see `.claude/settings.json`)
- Use path-scoped rules to add language-specific security (e.g., buffer safety for C, SQL injection for Python)
