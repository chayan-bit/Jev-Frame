# Security policy

## Supported versions

| Version | Supported |
|---|---|
| Latest release (currently 0.1.x) | Yes |
| `main` branch | Yes |
| Older releases | No; please upgrade |

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's [private vulnerability reporting](https://github.com/chayan-bit/Jev-Frame/security/advisories/new).
Do not open a public issue, discussion, or pull request for a suspected vulnerability.

Include a description of the issue, the affected version or commit, the impact you expect, and steps or a minimal script to reproduce it.
You should receive an acknowledgement within 3 business days and an initial assessment within 10 business days.
Fixes are developed in a private advisory, released as a patch version, and disclosed publicly with credit to the reporter unless you prefer to stay anonymous.

## Scope

Examples of issues we treat as security vulnerabilities:

- A path that lets a `MUTATION` tool run without the required policy, checkpoint, exact-action authorization, or revalidation.
- Evidence, credentials, or host dependency values leaking into serialized results, events, diagnostics, fixtures, or model-visible schemas.
- Scope or authority widening between parent and child runs or across candidate snapshots.
- Any network request or credential lookup performed on import or by offline paths.

Bugs in model quality, or recommendations you disagree with, are not vulnerabilities; please open a regular issue for those.

## Handling credentials

Never paste TypeSafe API keys or any other credentials into issues, pull requests, advisories, logs, fixtures, or recordings.
If a key is exposed, revoke it in your TypeSafe account immediately and redact the text where it appeared.
Jev-Frame reads keys only from the arguments or environment you provide and keeps key material out of its error messages and inspection records.
