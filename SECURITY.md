# Security Policy

## Supported Versions

Security fixes are prioritized for the latest tagged release and the current `main` branch.

| Version | Supported |
| :--- | :--- |
| `0.2.x` | Yes |
| `< 0.2.0` | No |

## Reporting a Vulnerability

Please report suspected vulnerabilities privately by opening a GitHub Security Advisory for this repository. If advisory access is unavailable, contact the maintainer through the GitHub profile linked from the repository owner account and include:

* Affected version or commit.
* Reproduction steps.
* Impact assessment.
* Any relevant logs, crafted media files, or model package samples.

Do not publish exploit details in public issues until a fix or mitigation is available.

## Scope

In scope:

* Unsafe model package import behavior.
* Plugin sandbox escapes.
* Release signing, update verification, or package integrity failures.
* Local API authentication or authorization bypasses.
* Path traversal or unsafe file writes in media processing workflows.

Out of scope:

* Vulnerabilities requiring already-compromised local administrator access.
* Issues in third-party drivers, FFmpeg builds, or ONNX Runtime binaries unless the project packaging directly worsens exposure.
