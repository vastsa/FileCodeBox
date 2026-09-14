## [Unreleased]

<!-- Current release: 2.6.0 x-release-please-version -->

### Added

- Added a global storage capacity limit with concurrency-safe reservations for regular, chunked, presigned, and admin file uploads.
- Added the storage reservation migration and stale upload cleanup so failed, cancelled, or expired uploads release reserved capacity.
