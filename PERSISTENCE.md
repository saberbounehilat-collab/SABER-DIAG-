# SABER ACTROS DZ — Storage repair

This is the safety/staging branch for the store's persistence repair. It is **not automatically deployed** by the existing Render service, which currently tracks `main`.

## Root cause and safety

The app originally uses `DATABASE_URL` when defined, but silently falls back to `sqlite:///store.db` when missing. SQLite on a free Render web service is **ephemeral**: redeploys, restarts and spin-downs can remove the database and all its product, image, PDF, account, workshop and YouTube-link records.

The repair changes production startup to **fail closed** if `DATABASE_URL` is absent or not PostgreSQL. This prevents creating new data in temporary SQLite storage. Admin-only `/admin/storage` offers a database status screen, a full ZIP backup, and an all-or-nothing restore.

## Preserve existing records before any deployment

**Do not merge or deploy this branch until existing records have been saved.** A new Render deployment cannot automatically access the previous live instance's ephemeral SQLite file. The existing source does not expose a full backup route; use any existing copies and export currently visible product text, video links, photos and PDFs first. If the current site has already restarted and lost its SQLite file, this code cannot magically recover those records.

Never publish an exported ZIP: it includes customer and account data and password hashes.

## Connect persistent storage

From the Render dashboard, open the existing `saber-actros-db` PostgreSQL database, copy its **Internal Database URL** under Connect, then open the `saber-actros-dz` web service -> Environment -> set `DATABASE_URL` to that URL. Keep the URL/password private and do not commit it to GitHub. Changes to production environment variables may initiate a redeploy.

Only after protecting existing data and configuring the database should the branch be merged into `main`. Its source is compatible with PostgreSQL and creates missing tables on boot.

After deployment:
1. Sign in as administrator and open `/admin/storage`.
2. Verify it says PostgreSQL, not SQLite.
3. Download and privately store the ZIP backup.
4. Add a test product, a photo, a PDF and a YouTube training link; verify each after an intentional redeploy **only after the backup**.

Render's existing free PostgreSQL instance is scheduled to expire on **November 28, 2026**. Before that, move to a plan/provider that retains databases long-term; free Render Postgres is not permanent.

## Media

The image uploads and PDFs are currently stored in database binary fields. Links to educational YouTube videos are stored in the database; actual large video file uploads are **not implemented**. Large files should eventually use object storage rather than PostgreSQL binary columns.

## Restore

The ZIP download contains `store.json` with all application tables. The restore form requires typing `RESTORE` and a confirmation dialog; validation is performed before any deletion, then the full restore is committed transactionally. Always take a backup of the current destination database before restoring an older backup. 
