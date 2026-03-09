## Database migrations

The backend now uses versioned SQL migrations stored in `src/data/migrations/versions`.

Migration rules:

- Name every file as `<version>_<snake_case_name>.sql`.
- Use a monotonically increasing numeric version prefix. If you need multiple migrations on the same day, extend the numeric prefix such as `2026030901_...`, `2026030902_...`.
- Keep migrations append-only. Do not edit an applied file; add a new one.
- The runner stores the file identifier, parsed version number, name, and checksum in `schema_migrations`.

Run migrations manually:

```powershell
cd Backend
python -m src.data.migrations
```

Application startup also runs pending migrations through the same runner.
