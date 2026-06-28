# Render Deployment

This app can be exposed on the public internet using Render with a single web service and a persistent disk.

## Why the disk matters

The app currently uses:

- SQLite for ticket data
- local uploads for stored evidence

Without a persistent disk, both would be lost on restart or redeploy.

## Files added for Render

- `render.yaml`
- production data path support via `DATA_DIR`

## Suggested setup

1. Push this repo to GitHub.
2. In Render, create a new Blueprint deployment from the repo.
3. Confirm the persistent disk mount path:
   - `/opt/render/project/src/storage`
4. Set these environment variables in Render:
   - `APP_BASE_URL=https://your-service-name.onrender.com`
   - `SECRET_KEY=<strong-random-secret>`
   - `ADMIN_USERNAME=<your-admin-user>`
   - `ADMIN_PASSWORD=<strong-password-or-hash>`
   - `PAYSTACK_SECRET_KEY=<your-paystack-secret>`
   - `PAYSTACK_PUBLIC_KEY=<your-paystack-public>`

## Notes

- This SQLite deployment should stay on a single instance.
- Do not scale the web service horizontally while SQLite is on a single disk-backed instance.
- For a more serious public deployment, move tickets and payments to Postgres instead of SQLite.
