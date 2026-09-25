# Security policy

## Reporting a vulnerability

Please report security vulnerabilities privately through [GitHub security advisories](https://github.com/chayan-bit/Jev-Frame/security/advisories/new).
Do not open a public issue for a suspected vulnerability.

Include a description of the issue, the affected version or commit, and steps to reproduce it.
You should receive an acknowledgement within a few days, and fixes are coordinated with the reporter before public disclosure.

## Handling credentials

Never paste TypeSafe API keys or any other credentials into issues, pull requests, advisories, logs, or fixtures.
If a key is exposed, revoke it in your TypeSafe account immediately and redact the text where it appeared.
Jev-Frame reads keys only from the arguments or environment you provide and keeps key material out of its error messages and inspection records.

## Supported versions

Security fixes are made on the latest release and the `main` branch.
