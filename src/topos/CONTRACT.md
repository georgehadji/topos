# topos — Package overview

**See:** Each submodule has its own `CONTRACT.md`.

| Submodule | Responsibility |
|---|---|
| `domain/` | Pure business logic, zero IO, zero project imports |
| `service/` | Orchestration + Protocol ports |
| `adapters/` | Concrete IO implementations |
| `interfaces/` | HTTP routers + CLI entry points |
| `config.py` | Environment-based settings |
| `telemetry.py` | Structured logging |
