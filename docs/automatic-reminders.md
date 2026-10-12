# MetroCRM automatic reminders

## Scope
The worker sends reminders to the assigned internal employee only; it does not send messages to customers. Follow-up reminders are issued when due within 30 minutes or overdue. Site-visit reminders are issued in the hour before a scheduled visit. Email is preferred when the employee has an email address; WhatsApp is used only when email is absent and a mobile number is available.

## Reliability
- A database row with a unique reminder key deduplicates each event, due timestamp, reminder stage, recipient and channel.
- Failed sends retry with bounded backoff (1, 5, 15, 30, 60 and 120 minutes), up to six attempts.
- Delivery status is recorded as SENT, TEST, RETRY or FAILED. TEST means the provider adapter is in test mode and does not mean a message reached the employee.
- If a provider accepts a message but the connection times out before acknowledgement, an external provider may receive a duplicate on retry. Exactly-once delivery cannot be guaranteed without provider idempotency support.
- The delivery table stores an internal user ID, not customer contact details.

## Worker process
Run the worker as a single dedicated service using the same release, environment variables and persistent database as the web app:
python -m app.services.reminder_worker

It runs immediately on startup and every five minutes. Do not register it in the web application's lifespan. Do not use the backup scheduler for this work. Configure email gateway settings (EMAIL_PROVIDER, EMAIL_API_URL, EMAIL_API_KEY, EMAIL_FROM) or WhatsApp settings before expecting live delivery. WhatsApp is selected only when the employee has no usable email.

## Verification and rollout
CI tests cover due follow-up notification, duplicate suppression, retry backoff and site-visit staff notification using test doubles. Production verification requires a separate worker deployment and a safe test employee account with provider credentials. Keep the existing backup/restore configuration and schedule unchanged.
