# Security Policy — Entity Standardizer 🏛️📞

At **Entity Standardizer**, security, data privacy, and anti-fraud engineering are foundational architectural pillars. Owned and maintained by **HobbyHabbit LLC** under the **MIT License**, Entity Standardizer provides high-throughput multi-national organization, person, web, address, and telephone standardization, bidirectional cross-healing, and fraud/IRSF risk detection.

---

## 1. Supported Versions

| Version | Supported | Status |
| :--- | :--- | :--- |
| `2.x` (Current: `2.1.0`) | :white_check_mark: | Current Active Production (Full Security Support) |
| `1.x` | :x: | Superseded by `2.x` Unified Entity-Standardizer |

---

## 2. Reporting a Vulnerability

We adhere to **Coordinated Vulnerability Disclosure (CVD)** principles.

- **Email**: Send vulnerability reports to `security@hobbyhabbit.com`, `support@hobbyhabbit.com`, and `jake@hobbyhabbit.com`.
- **Subject Line**: `[SECURITY VULNERABILITY] Entity-Standardizer — <Brief Description>`
- **GitHub Private Vulnerability Reporting**: Report privately via [GitHub Security Advisories](https://github.com/Jacob-white/Entity-Standardizer/security/advisories/new).
- **Response SLA**: Initial acknowledgment within **24 hours**, triage within **48 hours**, and critical patch prioritization within **7 days**.

> [!IMPORTANT]
> **Please do NOT file public GitHub issues for suspected security vulnerabilities.** Always use private communication channels and synthetic test data (e.g., `555-0100` through `555-0199`).

---

## 3. Threat Model & Defense-in-Depth Architecture

1. **Linear-Time Lexical Parsing (ReDoS Immunity)**:
   - Organization, person, email/URL, address, and phone normalization use bounded character translation tables and anchored regular expressions to prevent catastrophic backtracking on adversarial input strings.
2. **International Revenue Share Fraud (IRSF) & Premium-Rate Guardrails**:
   - Numbers matching domestic or international premium-rate prefixes (`+1 900`, `+44 90/91/98`, `+49 900`, etc.) are automatically tagged with `PhoneLineType.PREMIUM_RATE` and `PhoneRiskFlag.PREMIUM_RATE_IRSF_RISK` so downstream SMS/Voice OTP dispatchers can block toll-fraud payouts.
3. **Disposable, Sentinel & Placeholder Domain Rejection**:
   - `standardize_email()` and `standardize_url()` classify disposable temp-mail domains (`DISPOSABLE_EMAIL_DOMAIN`) and reject sentinel/placeholder domains (`example.com`, `none.com`, `test.com`, `invalid.com`, `localhost.localdomain` via `SENTINEL_DOMAIN_REJECTED`) to prevent synthetic/placeholder pollution in production identity graphs.
4. **PII Redaction & Masking (`mask_phone`)**:
   - Built-in `mask_phone(phone, strategy="partial" | "partial_phone" | "last4" | "redact" | "null" | "hash" | "sha256" | "md5")` ensures logs, audit trails, and multi-tenant queries never leak raw subscriber numbers.
5. **Zero-Network Offline Execution**:
   - The core library makes **zero outbound network requests**. All 249 ISO-3166-1 dial plans, NANP area code tables, USPS Pub 28 / UPU S42 postal reference tables, and ISO 20275 legal form registries execute 100% in-memory offline.
