# Issue #770: Email Sending Failure Resolution

## Problem
When contact requests come from the homepage, emails are not being sent to interested parties despite:
- Contact being created ✓
- Message being stored ✓
- Newsletter subscription being created ✓
- No error messages appearing ✗

## Root Cause
The email sending failures were **silent** because:

1. `MailService.send_template()` returns `False` on failure but never raises exceptions
2. The contact API (`crm/api.py`) was not checking return values from email sending calls
3. Email failures were logged in AuditLog as `MAIL_FAILED` but not propagated to application logs
4. No warnings or errors were visible to administrators

## Solution Implemented

### 1. Email Failure Tracking (crm/api.py)
- Added `email_results` dictionary to track success/failure of each email
- Capture return values from all `MailService.send_template()` calls
- Include email results in API response: `email_status` field
- Include email results in audit logs: `email_results` in `after` field

### 2. Warning Logging
- Added `logger.warning()` calls when any emails fail
- Log includes contact ID, email address, and which emails failed
- Warnings appear in application logs for immediate visibility

### 3. Enhanced Audit Logs
- Audit log note now includes: "Emails sent: X/Y"
- Shows immediately if emails are failing
- Email results stored in `after` dict for debugging

### 4. Newsletter API Updates
- Same pattern applied to `newsletter/api.py`
- DOI email failures now logged
- Confirmation email failures now logged

## How to Diagnose Email Issues

### Check Application Logs
```bash
# Look for warning messages
grep "Failed to send emails" /var/log/zenico-admin.log

# Check for specific contact
grep "contact_id" /var/log/zenico-admin.log
```

### Check Audit Logs
```python
# In Django shell
from audit.models import AuditLog

# Check MAIL_FAILED entries
failed_mails = AuditLog.objects.filter(action='mail.failed').order_by('-created_at')
for log in failed_mails[:10]:
    print(f"{log.created_at}: {log.note}")
    print(f"Error: {log.after.get('error', 'Unknown')}")

# Check contact creation logs for email status
contact_logs = AuditLog.objects.filter(
    action='contact.created'
).order_by('-created_at')[:10]
for log in contact_logs:
    results = log.after.get('email_results', {})
    print(f"{log.note}: {results}")
```

### Check Azure/Graph API Configuration

The most common cause of email failures is Azure AD authentication issues.

**Required Environment Variables:**
```bash
AZURE_TENANT_ID=<your-tenant-id>
AZURE_CLIENT_ID=<your-client-id>
AZURE_CLIENT_SECRET=<your-client-secret>
MAIL_FROM_ADDRESS=noreply@zenico.app
MAIL_FROM_NAME=Zenico
ADMIN_NOTIFICATION_EMAIL=team@zenico.app
```

**Verify Configuration:**
```python
# In Django shell
from core.services.mail import MailService
import os

# Check environment variables
print("AZURE_TENANT_ID:", os.getenv('AZURE_TENANT_ID', 'NOT SET'))
print("AZURE_CLIENT_ID:", os.getenv('AZURE_CLIENT_ID', 'NOT SET'))
print("AZURE_CLIENT_SECRET:", '***' if os.getenv('AZURE_CLIENT_SECRET') else 'NOT SET')

# Try to get access token
try:
    token = MailService._get_access_token()
    print("✓ Successfully acquired access token")
except Exception as e:
    print(f"✗ Failed to acquire token: {e}")
```

**Common Azure AD Issues:**

1. **Invalid Client Secret**
   - Error: "AADSTS7000215: Invalid client secret"
   - Solution: Generate new secret in Azure Portal > App Registrations > Certificates & secrets

2. **Missing API Permissions**
   - Error: "Insufficient privileges to complete the operation"
   - Required permissions: `Mail.Send` (Application permission)
   - Solution: Add permission in Azure Portal > App Registrations > API permissions

3. **Shared Mailbox Not Configured**
   - Error: "HTTP 401: Unauthorized"
   - Solution: Ensure app has access to send from `MAIL_FROM_ADDRESS`

4. **Token Expired**
   - Error: "The provided access token has expired"
   - Solution: MSAL handles auto-refresh, but check system time is correct

### Test Email Sending Manually

```python
# In Django shell
from core.services.mail import MailService

# Test basic email
success = MailService.send(
    to='test@example.com',
    subject='Test Email',
    html_body='<p>This is a test</p>',
    text_body='This is a test'
)
print(f"Email sent: {success}")

# Test template email
success = MailService.send_template(
    to='test@example.com',
    template='contact_confirmation',
    context={
        'first_name': 'Test',
        'last_name': 'User',
        'email': 'test@example.com',
        'phone': '',
        'company': '',
        'message': 'Test message',
        'subject': 'Test'
    }
)
print(f"Template email sent: {success}")
```

## API Response Changes

The contact API now returns email status:

```json
{
  "message": "Contact created successfully",
  "email_status": {
    "contact_confirmation": true,
    "admin_notification": true,
    "newsletter_doi": true
  }
}
```

If any emails fail:
```json
{
  "message": "Contact created successfully",
  "email_status": {
    "contact_confirmation": false,
    "admin_notification": true,
    "newsletter_doi": true
  }
}
```

## Testing

Run the test suite:
```bash
python manage.py test tests_api.EmailFailureHandlingTestCase
```

Tests verify:
- ✓ All emails sent successfully
- ✓ All emails fail
- ✓ Partial email failures
- ✓ Warning logging on failures
- ✓ Audit logs include email results
- ✓ Newsletter API failures

## Migration Notes

No database migrations required. This is a code-only change that:
- Improves observability of email failures
- Adds warning logging
- Returns email status in API responses
- Enhances audit log entries

## Backwards Compatibility

- API response now includes `email_status` field
- All existing API consumers should continue to work
- New field can be ignored or used for monitoring

## Monitoring Recommendations

1. **Set up alerts for email failures:**
   - Monitor application logs for "Failed to send emails"
   - Alert on spike in MAIL_FAILED audit logs

2. **Dashboard metrics:**
   - Track email success rate by type
   - Monitor Azure AD token acquisition failures

3. **Regular health checks:**
   - Test email sending periodically
   - Verify Azure AD configuration monthly
