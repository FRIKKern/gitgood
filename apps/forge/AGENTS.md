# Forge implementation

Follow the root AGENTS.md. This is a Phoenix JSON API with a separate TanStack interface.

- Run `mix precommit` before integration; keep compilation, formatting and tests clean.
- Keep authorization and durable Git operations in contexts, not only controllers.
- Use changesets and database constraints. Actor and ownership fields are assigned by trusted code.
- No shell interpolation for Git arguments. Never execute hooks from user code.
- Generate migrations with `mix ecto.gen.migration`.
- Use isolated test stores and `start_supervised!` for test processes; avoid timing sleeps.
