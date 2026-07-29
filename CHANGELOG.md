# Changelog

All notable changes to this project will be documented here.

The format follows Keep a Changelog, and releases use Semantic Versioning.

## [Unreleased]

## [0.1.0] - 2026-07-30

### Added

- Open-source governance, security, contribution, and provider-policy documents.
- Opt-in gates for UDN RSS and NewsAPI integrations.
- Unit tests proving disabled news providers do not make network requests.
- Canonical instrument catalog, provider-symbol mappings, separate watchlists,
  and catalog-first tracking tiers.
- Additive migrations and a recovery-first T8 rollout runbook.

### Changed

- Updated project documentation to describe the current instrument catalog,
  watchlist, tracking-tier, analysis, and AI-brief capabilities.
- Replaced real publisher names in synthetic demo headlines.
- Removed hard-coded Docker Compose resource names so public clones are isolated
  by their Compose project name.
