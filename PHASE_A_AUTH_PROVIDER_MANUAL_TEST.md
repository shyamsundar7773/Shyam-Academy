# Phase A manual authentication and provider verification

These steps require credentials configured outside the repository. Do not commit `.env`, API keys, Firebase service credentials, or tokens.

## Configure Firebase

1. In Firebase Console, create or select the project.
2. Enable **Authentication > Sign-in method > Email/Password**.
3. Create two test accounts, for example Account A and Account B.
4. Copy the Web API key and project ID from the Firebase web app settings.
5. Set these environment variables in the local shell or secret manager:

```text
SHYAM_ACADEMY_FIREBASE_PROJECT_ID=<project-id>
SHYAM_ACADEMY_FIREBASE_WEB_API_KEY=<web-api-key>
SHYAM_ACADEMY_FIREBASE_AUTH_DOMAIN=<project-id>.firebaseapp.com
```

## Configure the real AI provider

```text
SHYAM_ACADEMY_AI_PROVIDER=openai
SHYAM_ACADEMY_AI_MODEL=<available-model>
SHYAM_ACADEMY_AI_API_KEY=<provider-key>
SHYAM_ACADEMY_AI_BASE_URL=https://api.openai.com/v1
```

Use the provider's compatible base URL if a different OpenAI-compatible service is selected.

## Verify the application

1. Start from the project root with `streamlit run app.py`.
2. Confirm the first screen is **Sign in to Shyam Academy**, not the application dashboard.
3. Sign in with Account A.
4. Confirm the sidebar shows the Firebase UID, not an email address or demo user ID.
5. Open **AI Assistant** and run one explicit generation.
6. Confirm the response is from the configured provider and no key appears in the UI or error output.
7. Refresh the browser and navigate across Timetable, Notes, Progress, Tests, Interview, Mentor, Notifications, and Body + Routine.
8. Sign out and confirm protected application pages are no longer accessible.
9. Sign in again with Account A and confirm Account A's data remains available.
10. Sign out, sign in with Account B, and confirm Account A's modules, notes, sessions, notifications, AI tasks, and proposals are not visible.

This document is a procedure only. No real Firebase or AI-provider flow is claimed as executed unless it is run with actual configured credentials.
