# Release Signing Secrets

The `release-installers.yml` workflow can run from `workflow_dispatch` without signing secrets for dry release validation. Tagged releases (`refs/tags/v*.*.*`) require the platform signing secrets below and fail early when they are missing.

## Windows

Required secrets:

* `WINDOWS_SIGNING_CERTIFICATE_BASE64`: Base64-encoded `.pfx` certificate.
* `WINDOWS_SIGNING_PASSWORD`: Password for the `.pfx` certificate.

The workflow signs both one-file executables with `signtool`, uses a SHA-256 digest, timestamps with DigiCert, and verifies the resulting Authenticode signatures before uploading artifacts.

## macOS

Required secrets:

* `MACOS_DEVELOPER_ID_APPLICATION`: Developer ID Application identity name inside the imported certificate.
* `MACOS_SIGNING_CERTIFICATE_BASE64`: Base64-encoded Developer ID Application `.p12` certificate.
* `MACOS_SIGNING_PASSWORD`: Password for the `.p12` certificate.
* `MACOS_NOTARY_APPLE_ID`: Apple ID used for notarization.
* `MACOS_NOTARY_PASSWORD`: App-specific password or keychain profile password for notarization.
* `MACOS_NOTARY_TEAM_ID`: Apple Developer Team ID.

The workflow imports the signing certificate into a temporary keychain, signs the CLI and desktop executables with the hardened runtime and `.github/signing/macos-entitlements.plist`, verifies code signatures, creates the DMG, submits it to `notarytool`, staples the notarization ticket, and runs `spctl` assessment before upload.
