# Contributing to NetFleet

Thank you for your interest in contributing! NetFleet is an
[ITConnect](https://itconnect.ge) open-source project, and we welcome
contributions from MSP engineers, network operators, and anyone who shares the
vision of an open, vendor-agnostic network fleet management platform.

## Ways to contribute

- **Report bugs** - [open an issue](https://github.com/ITConnectGE/netfleet/issues/new?template=bug.yml) with reproduction steps
- **Suggest features** - open a [discussion](https://github.com/ITConnectGE/netfleet/discussions) first to align on scope
- **Add a vendor driver** - see [`docs/vendor-drivers.md`](docs/vendor-drivers.md) (in progress)
- **Improve documentation** - typos, clarifications, screenshots, translations all welcome
- **Translate the UI** - i18n PRs encouraged (Georgian, Russian, Ukrainian, Turkish, Arabic, Spanish, ...)
- **Star the repo** if NetFleet is useful to you

## Development setup

### Prerequisites

- Docker and Docker Compose (or Docker Desktop)
- Python 3.12+ (for backend dev outside Docker)
- Node 20+ and pnpm (for frontend dev outside Docker)
- A test MikroTik device (physical or [CHR VM](https://help.mikrotik.com/docs/display/ROS/Cloud+Hosted+Router%2C+CHR))

### Quick dev environment

```bash
git clone https://github.com/ITConnectGE/netfleet.git
cd netfleet
cp .env.example .env
# Edit .env if needed (defaults work for local dev)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Frontend: <http://localhost:3000> - API docs: <http://localhost:8000/docs>

### Backend (without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend (without Docker)

```bash
cd frontend
pnpm install
pnpm dev
```

## Code style

- **Python**: [ruff](https://docs.astral.sh/ruff/) for lint + format, [mypy](https://mypy.readthedocs.io) strict
  ```bash
  cd backend && ruff check . && ruff format --check . && mypy app
  ```
- **TypeScript**: ESLint + Prettier (via Next.js defaults)
  ```bash
  cd frontend && pnpm lint && pnpm format:check
  ```
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/) - `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- **Branch names**: `feat/short-description`, `fix/issue-123`, `docs/section`

## Pull request checklist

- [ ] Tests added or updated for the change
- [ ] All existing tests pass: `pytest backend/` and `pnpm test --filter frontend`
- [ ] Lint/format/type-check pass
- [ ] Docs updated if behavior changed
- [ ] Commit history is clean (squash WIP commits)
- [ ] CHANGELOG entry added under `[Unreleased]`

## Adding a vendor driver

NetFleet's killer feature is its vendor-agnostic API. To add support for a new vendor:

1. Create `backend/app/drivers/<vendor>.py` implementing the `VendorDriver` Protocol
2. Register it in `backend/app/drivers/registry.py`
3. Declare driver capabilities (which sections it supports)
4. Add integration tests in `backend/tests/drivers/test_<vendor>.py` using a mock/sandbox device
5. Update the driver table in `README.md`

See `backend/app/drivers/mikrotik.py` as the reference implementation.

## Reporting security issues

**Do not open a public issue** for security vulnerabilities. Email
**security@itconnect.ge** with details. We aim to respond within 48 hours
and to ship a fix within 30 days for critical issues.

## Code of Conduct

By participating in this project you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

---

Questions? Open a [Discussion](https://github.com/ITConnectGE/netfleet/discussions) or reach out at **opensource@itconnect.ge**.
