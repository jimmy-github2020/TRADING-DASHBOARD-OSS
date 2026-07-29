# Security Policy

## Supported Versions

Security fixes are applied to the latest release and the default branch.

## Reporting

Do not open a public issue for a suspected vulnerability or exposed credential.
Use GitHub's private vulnerability reporting feature for this repository.

Include:

- affected version or commit;
- reproduction steps;
- impact and required preconditions;
- suggested mitigation, if known.

Do not access data that is not yours, disrupt services, or retain credentials.
The maintainer will acknowledge a complete report as soon as practical and will
coordinate remediation and disclosure.

## Security Boundaries

- Live trading is outside the supported scope.
- External providers and notifications are disabled or dry-run-first.
- Users are responsible for their provider accounts, API keys, and data rights.
- Never attach production databases, logs, `.env` files, or market-data dumps to
  an issue.
