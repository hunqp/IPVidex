# Changelog

All notable changes to IPVidex are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-11-10

### Changed
- Unexpected errors now show the error message and code location directly, with full technical details and a **Copy details** button for bug reports. Credentials inside URLs are masked; the log file still records only error types and stack frames.

### Fixed
- Logging in to a device again after a cancelled or failed login failed with "An unexpected error occurred (RuntimeError)".
- Image page failed with "An unexpected error occurred (TypeError)" on cameras that report a white-balance Cb gain setting.
- Stopping a video view or closing the RTSP console printed "QObject::disconnect: wildcard call disconnects from destroyed signal" warnings.

## [1.0.0] - 2026-11-10

First public release.

### Added
- ONVIF device discovery (WS-Discovery on every IPv4 interface) and manual device entry.
- Device workspace with Overview, Live, Video, Image, PTZ, Profiles, Network, Time, Users, Certificates, Events and Maintenance pages; several devices can be open at once.
- RTSP/RTSPS playback through libVLC in an isolated worker process, with automatic reconnection and a software-decoding fallback.
- RTSPS through a local TLS relay that trusts only the camera's own certificate.
- RTSP command console for OPTIONS, DESCRIBE, SETUP, PLAY, PAUSE, GET/SET_PARAMETER and TEARDOWN.
- RTMP/RTMPS and WebRTC (WHIP/WHEP) ingest servers powered by MediaMTX 1.21.3, with live statistics and optional self-signed TLS.
- Windows installer, single executable and portable folder builds (see `GUIDELINE.md`).

### Security
- Passwords are never written to disk; credentials reach worker processes only through standard input.
- Device addresses and certificates are pinned for the whole session.
- WS-UsernameToken digests for ONVIF and HTTP/RTSP Digest authentication.
