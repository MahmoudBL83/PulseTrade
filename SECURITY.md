# Security

- No secrets are committed. Configure via environment (see `.env.example`).
- Legacy hardcoded keys (Flask secret, Gmail app password, Stripe test keys,
  Google/HF keys, Fernet key) were stripped during refresh. Treat all old
  values as compromised — rotate before any prod use.
- Exchange API creds are Fernet-encrypted; `FERNET_KEY` must be set or the
  app raises at encrypt/decrypt time.
- To report a vulnerability, open a private security advisory on GitHub.
