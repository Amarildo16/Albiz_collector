# Changes Made

## What changed

- Changed the default `DATABASE_URL` from SQLite to MySQL in the runtime settings.
- Updated `.env.example` to use a MySQL connection string.
- Added the `PyMySQL` runtime dependency so SQLAlchemy can connect with the new default URL.
- Added a short README note describing the new default database configuration.

## Why it changed

- The project configuration was still defaulting to SQLite.
- This pass changes the default database setup to MySQL in a way that is immediately runnable with the correct SQLAlchemy driver installed.

## Files modified

- README.md
- .env.example
- pyproject.toml
- src/albiz_collector/config.py
- changes_made.md

## Files created

- None

## Files removed

- None

## Follow-up notes

- Install dependencies again so `PyMySQL` is available in the environment.
- Update the MySQL username, password, host, and database name in `.env` before running the app locally.