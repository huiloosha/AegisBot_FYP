# Google Sign-In setup

1. In Google Cloud Console, create/select a project.
2. Configure the OAuth consent screen.
3. Create an OAuth 2.0 Client ID with application type **Web application**.
4. Add Authorized JavaScript origins:
   - `http://127.0.0.1:5000`
   - `http://localhost:5000`
   - `https://aegisbot-45la.onrender.com`
5. Copy the Client ID.
6. Local PowerShell:
   ```powershell
   $env:GOOGLE_CLIENT_ID="530471939926-840iejf4hv4g886g1mv4mp75tju1gu5a.apps.googleusercontent.com"
   python backend/run.py
   ```
7. Render: Environment -> add `GOOGLE_CLIENT_ID` with the same value, then redeploy.

No Google Client Secret is required for this Google Identity Services ID-token flow.
The backend verifies the returned ID token and then creates its own AegisBot session token.

# Persisting accounts on Render

The default `render.yaml` stays on Render Free and therefore uses an ephemeral
SQLite file. Accounts can disappear after a restart/redeploy.

For persistent SQLite, deploy with `render-with-persistent-disk.yaml`. It uses a
paid Starter web service, mounts `/var/data`, and sets the database path to
`/var/data/aegisbot.db`.

An alternative is migrating SQLite to a hosted PostgreSQL database.