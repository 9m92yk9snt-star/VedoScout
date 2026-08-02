# Emergent Google Auth — Testing Playbook (ScoutMePlay adaptation)

IMPORTANT: This app BRIDGES Emergent Google OAuth into its EXISTING JWT auth system.
There are NO session_token cookies. The flow is:

1. Frontend: "Continue with Google" → `https://auth.emergentagent.com/?redirect=<origin>/dashboard` (or `/upload` from the upload gate modal)
2. Google → user lands back at `{redirect}#session_id=<sid>`
3. AppRouter detects `#session_id=` in the URL fragment (useLocation().hash) and renders `<AuthCallback />`
4. AuthCallback POSTs `/api/auth/google/session` with `{session_id}` — backend calls
   `GET https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data` (header `X-Session-ID`)
   server-side, finds-or-creates the user by email, and returns the SAME TokenResponse
   (`access_token` JWT + `user`) as `/api/auth/login`.
5. Frontend persists it in localStorage (`elite_token` / `elite_user`) via auth-context — identical to email/password login.

## What CAN be tested without a real Google account
- `POST /api/auth/google/session` with a bogus session_id → 401 "invalid or expired"
- `POST /api/auth/google/session` with empty session_id → 400
- Google-only accounts (password_hash=None) trying email/password login → 401 with
  "This account uses Google sign-in" message
- UI: "Continue with Google" buttons exist on /login, /signup and the upload AccountGateModal,
  and clicking them redirects to auth.emergentagent.com (assert navigation URL prefix, then go back)

## Simulating a Google login for E2E (backend-side)
You cannot mint a real session_id. Instead, create a Google-style user directly and login-bridge manually:
```bash
cd /app/backend && python -c "
import asyncio, os, uuid
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv()
async def main():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    email = 'google.test@elitescout.com'
    if not await db.users.find_one({'email': email}):
        await db.users.insert_one({'id': str(uuid.uuid4()), 'email': email, 'password_hash': None,
            'full_name': 'Google Test', 'role': 'user', 'auth_provider': 'google',
            'created_at': '2026-06-01T00:00:00+00:00'})
    print('ok')
asyncio.run(main())
"
```
Then verify /api/auth/login with that email returns the "uses Google sign-in" 401.

## Existing JWT test accounts
See /app/memory/test_credentials.md (admin, free, prepaid accounts). All JWT flows unchanged.
