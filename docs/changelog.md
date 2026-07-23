# Changelog

## [2.5.3](https://github.com/vastsa/FileCodeBox/compare/v2.5.2...v2.5.3) (2026-07-23)


### Bug Fixes

* add magic-byte checks, login rate limits, and non-root Docker ([eda0a31](https://github.com/vastsa/FileCodeBox/commit/eda0a3127ab562b6a2cf828c0df4a93933c44526))
* magic-byte file checks, admin login rate limit, non-root Docker ([0ee2f04](https://github.com/vastsa/FileCodeBox/commit/0ee2f046dd057fecceaee1059d72d67de3038f19))

## [2.5.2](https://github.com/vastsa/FileCodeBox/compare/v2.5.1...v2.5.2) (2026-07-23)


### Bug Fixes

* harden share expiry, download token, quota SQL, and CORS ([ae77026](https://github.com/vastsa/FileCodeBox/commit/ae7702603a99dc77b9b48e78746058b2a74b0bf5))
* harden share expiry, download token, quota SQL, and CORS ([a41693f](https://github.com/vastsa/FileCodeBox/commit/a41693f90ded0234e0883c399254319bef04924a))

## [2.5.1](https://github.com/vastsa/FileCodeBox/compare/v2.5.0...v2.5.1) (2026-07-21)


### Bug Fixes

* patch CVE dependencies and path traversal risks ([00f3abd](https://github.com/vastsa/FileCodeBox/commit/00f3abd3b20fe2344e4dbf8d53714773e23a1050))

## [2.5.0](https://github.com/vastsa/FileCodeBox/compare/v2.4.0...v2.5.0) (2026-07-11)


### Features

* add global storage capacity limit ([818dd47](https://github.com/vastsa/FileCodeBox/commit/818dd47b2a4136d4b0d68b2484ac2d01a7ae6a3c))
* automate version releases ([ee8f908](https://github.com/vastsa/FileCodeBox/commit/ee8f9082ab59418a4a7721a05fc358215230981f))
* configure admin session lifetime ([#484](https://github.com/vastsa/FileCodeBox/issues/484)) ([93ff291](https://github.com/vastsa/FileCodeBox/commit/93ff291366aaac9d04c5259d3ecf01b20aed3fd0))


### Bug Fixes

* build frontend on native Docker platform ([2c51384](https://github.com/vastsa/FileCodeBox/commit/2c51384c80a9ff3f4eb98eb876759b8949dfae89))
* harden automated release workflow ([46883c9](https://github.com/vastsa/FileCodeBox/commit/46883c90ff52894631fe53bbd9b9c4100a7b27f1))
* harden share retrieval and admin visibility ([#482](https://github.com/vastsa/FileCodeBox/issues/482), [#480](https://github.com/vastsa/FileCodeBox/issues/480)) ([8d7d856](https://github.com/vastsa/FileCodeBox/commit/8d7d856c62d73badd0797eb4daec8d2ff10a403a))
* resolve docs dependency audit warnings ([36300ef](https://github.com/vastsa/FileCodeBox/commit/36300ef54ee09081a6cf6a5fe4e69cee7aad0162))

## [Unreleased]

### Added

- 增加全局存储容量上限配置，并对普通上传、分片上传、预签名直传和后台文件分享统一执行并发安全的容量预留。
- 增加存储预留迁移及过期上传清理，失败、取消或过期的上传会释放预留容量。
