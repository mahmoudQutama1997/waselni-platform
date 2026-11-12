# Security Policy

## Supported deployment

This repository is an MVP source package. Do not deploy it with development credentials or demo accounts. Review `PRODUCTION_READINESS_REPORT.md` and complete the listed production work before handling real customer data.

## Secrets

Never commit `.env` files, passwords, API tokens, JWTs, database dumps, private media, or provider credentials. Use your hosting provider's secret manager or GitHub Actions secrets. Only example environment templates may be committed.

## Initial administrator

Create the first administrator through a controlled server-side operation. Do not place administrator credentials in source code, documentation, commits, or issue reports.

## Reporting

For a suspected vulnerability, do not publish customer data or exploit details in a public issue. Contact the repository owner privately.
