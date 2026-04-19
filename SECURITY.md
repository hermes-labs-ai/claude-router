# Security Policy

## Scope

`claude-router` is a local prompt-routing utility. Security issues in scope include:

- code execution bugs in the package
- unsafe file handling
- dependency vulnerabilities introduced by this repo
- misconfigurations that could cause the CLI or library to expose secrets unexpectedly

Out of scope:

- benchmark disagreements
- workload-specific routing disagreements
- bugs in external Claude or Ollama services

## Reporting

Open a private security advisory on GitHub if possible. If that is not available, open an issue only for non-sensitive reports.

## Safe usage notes

- do not commit private prompts, API keys, or benchmark data
- treat routing decisions as workload-dependent and validate them before production use
