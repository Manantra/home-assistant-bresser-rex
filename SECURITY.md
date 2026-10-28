# Security policy

This is an **unofficial, experimental** Home Assistant integration. It communicates with a printer over an unauthenticated local TCP connection (port 8899) and an MJPEG camera (port 8080). These services must **never be forwarded to the public Internet**.

- Use a trusted local network and limit printer access with firewall rules where possible.
- Do not publish your real IP address, serial number, MAC address, camera captures, or Home Assistant logs without redacting them.
- The integration does not send printer telemetry to third parties. Home Assistant may access the GitHub repository to install updates if installed via HACS.
- Treat printer commands as potentially safety relevant. This project currently only issues read commands and the tested LED command.
- If you discover a vulnerability, contact the repository maintainer privately instead of posting exploit details in a public issue.

No formal security support period or guarantees are currently offered.
