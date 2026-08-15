# Security

[日本語版](../../ja/project/security.md)

The dashboard binds only to a loopback address and requires a cryptographically random token for every API request. Static assets are bundled locally, request bodies are size-limited, directory traversal is rejected, and a restrictive Content Security Policy is sent.

Do not modify `ui.bind_address` to a non-loopback address. Configuration validation rejects such values. Treat exported board geometry and reports as potentially sensitive design data.

Report vulnerabilities privately to the project maintainer before public disclosure. This source snapshot does not designate a public security mailbox; deployments should add an organization-owned contact before distribution.
