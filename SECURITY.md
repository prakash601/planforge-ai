# Security Policy

## Supported Versions

Security updates are provided for the latest `main` branch only.
No released versions exist yet; once versioned, the latest minor will be supported.

## Reporting a Vulnerability

Please do NOT open a public GitHub issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting:

1. Go to the repository on GitHub
2. Security tab -> Report a vulnerability
3. Include: affected files/commit, reproduction steps, impact, and suggested severity.

We aim to acknowledge within 48 hours and provide a remediation plan within 7 days.

## Scope

- Source code and workflows in this repository
- Dependencies declared in manifests / lockfiles
- Build and release automation under `.github/workflows/`

Out of scope: the `docs/` folder (currently local-only and gitignored) and
user-supplied sample captures under `data/` (added later).

## Hardening enabled on this repository

- Secret scanning + push protection
- Dependabot alerts + security updates
- Code scanning (CodeQL default setup)
- Private vulnerability reporting
- Branch protection on `main` (PR review, no force-push, no deletion)
- Pinned GitHub Actions SHAs where practical, least-privilege `permissions:` blocks
