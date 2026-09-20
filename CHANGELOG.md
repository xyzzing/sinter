# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Sentinel telemetry** — session-scoped temperature, power, energy monitoring
- Energy measurement tiers (wall-meter, hwmon counter, power integration, assumed)
- Optional electricity cost and CO₂e estimates via `[accounting]` config
- Thermal policy with advisory warnings and optional critical stop
- `sinter telemetry` command (one-shot probe, session summary, garbage collection)
- `sinter status` now includes live telemetry quality and readings
- `sinter doctor` includes one-shot sensor probe
- Backend version and feature detection
- Context size benchmarking (`sinter bench`)
- Backend update management (`sinter update --backend`)
- Compatibility validation in `sinter validate`
- Enhanced `sinter doctor` with feature detection

### Changed
- Improved error messages and diagnostics
- Updated hardware probing for better ROCm support

## [0.1.0] - 2025-09-20

### Added
- Process supervision with finite state machine
- Memory admission checks with safety reserves
- Hardware probing (`sinter doctor`)
- Profile validation (`sinter validate`)
- Resource planning (`sinter plan`)
- Backend lifecycle management (`sinter up`/`down`)
- Instance status reporting (`sinter status`)
- Sandboxed command execution (`sinter exec`)
- Interactive setup wizard (`sinter setup`)
- Comprehensive test suite (129 tests)