## Contributing to Runa

**Security vulnerability?** Don't open an issue, see [SECURITY.md](./SECURITY.md).

**Bug?** Search [Issues](https://github.com/Benybrahim/runa/issues) first, then
open one with a minimal repro.

**Fixing a bug?** Open a PR. Run `make check` first, and read
[RUNA.md](./RUNA.md) and [CLAUDE.md](./CLAUDE.md) so the patch fits Runa's
conventions.

**Cosmetic-only patch?** `make format` and `make lint-fix` already keep the
codebase consistent, so bundle formatting changes with a substantive one
instead of sending them alone.

**New feature or behavior change?** Open an issue first and describe the
problem. Runa is opinionated, work through [`RUNA.md`](./RUNA.md)'s "Runa Standard" before
proposing a new abstraction. Wait for feedback before opening a PR for
anything touching core architecture.

**Docs?** Live in [`docs/`](./docs). PR them like a code change, and keep
vocabulary consistent with [`concepts.md`](./docs/concepts.md).

By participating, you agree to follow the [Code of Conduct](./CODE_OF_CONDUCT.md).
