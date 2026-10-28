# Contributing

Thank you for helping support Adventurer III–compatible printers.

1. Reproduce issues with the latest version and review existing GitHub issues.
2. Open a focused issue or pull request. Include Home Assistant version, **model/firmware**, expected/actual result, and *sanitized* logs.
3. **Never** commit private network IPs, serial numbers, real MAC addresses, passwords, credentials, or camera recordings. Use `192.0.2.x` / `example.local` in examples.
4. Add protocol tests for new firmware responses. Do not assume a command is safe on every model.
5. Run `python -m unittest discover -s tests -v` before opening a PR.
6. Keep all device I/O local and do not add external telemetry.

Hardware testing is required before newly supported models or write commands can be documented as verified.
