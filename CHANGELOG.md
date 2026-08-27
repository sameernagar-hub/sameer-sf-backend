# Changelog

All notable changes to this project are documented here.

The format follows Keep a Changelog 1.1.0 and the project uses SemVer.

## [0.2.0] - 2026-08-26

### Added

- `Address` rows with a foreign key to `Contact`, a Home/Work/Other type, submitted ordering, and an `is_primary` flag.
- A partial unique index guaranteeing at most one primary address per contact.

### Changed

- `PUT` replaces the whole address collection; `PATCH` leaves it untouched unless `addresses` is present in the body.

### Removed

- **Breaking:** the flat `address`, `city`, `state`, `postal_code`, and `country` contact fields. Read and write `addresses` instead.

## [0.1.0] - 2026-08-26

### Added

- Contact photos as validated base64 data URLs, capped at 512 KB.
- Initial contacts API.
