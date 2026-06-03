# Contributing to silukman_video_enhancer

Thank you for your interest in contributing to `silukman_video_enhancer`! As an offline, local-first open-source project, we rely on community contributions to optimize and expand our capabilities.

Please review this guide before submitting issues or pull requests.

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful, welcoming, and professional environment for all contributors.

---

## How to Contribute

### 1. Reporting Bugs
*   Ensure the bug is reproducible with the latest main branch.
*   Search the Issue Tracker to check if the bug has already been reported.
*   Open an issue with a clear description, reproduction steps, your OS version, GPU hardware specs, and relevant logs.

### 2. Suggesting Features
*   Open a Feature Request issue.
*   Clearly explain the use case, why this feature is beneficial for offline/local-first video processing, and any proposed implementation details.

### 3. Submitting Pull Requests (PRs)
*   Fork the repository and create a feature branch off `main`:
    ```bash
    git checkout -b feature/your-feature-name
    ```
*   Implement your changes, keeping edits focused and modular.
*   Ensure all code conforms to the [Coding Standards](#coding-standards) below.
*   Push to your fork and submit a Pull Request to our `main` branch.

---

## Coding Standards

To maintain code quality across the codebase, we adhere to the following standards:

*   **Language**: All Python code, comments, variables, and docstrings must be written in **English**.
*   **Style Guide**: Adhere strictly to **PEP 8** style guidelines. We recommend formatting your code using `black` and linting with `flake8`.
*   **Documentation**: If you introduce a new feature or change CLI parameters, make sure to update the relevant markdown files in `/docs/` and log the feature status (`[Planned]`, `[MVP]`, `[Experimental]`, `[Future]`).

---

## Commit Message Guidelines

We use clear and structured commit messages. Commit messages should be structured as follows:

```
<type>(<scope>): <short description>
```

### Types:
*   `feat`: A new feature or model implementation.
*   `fix`: A bug fix (e.g., resolving GPU memory leak, fixing audio sync).
*   `docs`: Documentation changes only.
*   `style`: Code formatting updates (no logic changes).
*   `refactor`: Code changes that neither fix a bug nor add a feature.
*   `perf`: Performance optimizations (e.g., double buffering updates).
*   `test`: Adding or correcting tests.

### Example:
```
feat(pipeline): add ZSTD compression caching to frame queues
```

---

## Release Versioning Policy

Releases use Semantic Versioning with tags formatted as `vMAJOR.MINOR.PATCH`.

*   **Patch release (`vX.Y.Z`)**: Bug fixes, compatibility fixes, packaging repairs, and documentation corrections that do not add new user-facing behavior.
*   **Minor release (`vX.Y.0`)**: New enhancement features, provider support, desktop/API workflow additions, model integrations, or CI/CD capabilities that preserve existing behavior.
*   **Major release (`vX.0.0`)**: Breaking CLI/API changes, incompatible model package formats, removed features, or migration-requiring configuration changes.

Release process:

1.  Update `[project].version` in `pyproject.toml`.
2.  Add a matching `CHANGELOG.md` section.
3.  Push the version bump to `main`.
4.  The `Version Tag` workflow creates the matching `vX.Y.Z` tag when it does not already exist.
5.  The release workflow builds signed installer artifacts using the naming convention documented in `docs/developer/BUILD_AND_PACKAGING.md`.
