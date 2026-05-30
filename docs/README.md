# Documentation Index

This folder collects the project documentation for the SignalBridge Test Suite.
Start with the user guide, then dive into the architecture reference for
implementation rules.

| Document | Audience | Purpose |
| --- | --- | --- |
| [../README.md](../README.md) | Users & operators | Quick start, feature tour, usage guide for every test mode, protocol reference, troubleshooting. **Entry point.** |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Contributors | Authoritative architectural rules — layers, module registration, threading model, serial protocol, and the canonical **Code Conventions**. Read before changing code. |
| [firmware_stress_test_plan.md](firmware_stress_test_plan.md) | Contributors | Roadmap for hardening firmware robustness validation, with current status per phase. |
| [../CLAUDE.md](../CLAUDE.md) | Claude Code | Orientation for AI-assisted development; defers to `ARCHITECTURE.md` for the detailed rules. |

## Conventions for this repository

- **Code conventions** live in a single place: [ARCHITECTURE.md §9](ARCHITECTURE.md#9-code-conventions).
- **Common commands** (install, test, lint, mutation testing) live in
  [../README.md](../README.md) under *Development*.
- Other documents link to those sources instead of duplicating them, so there is
  one place to update.
