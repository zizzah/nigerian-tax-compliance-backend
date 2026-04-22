"""
Email Service
Location: app/core/email.py

Sends transactional emails using SMTP (Gmail with App Password).
Used for: invoice delivery, payment receipts, welcome emails.

Dependencies:
    pip install fastapi-mail jinja2 aiofiles

Environment variables required (add to .env):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=chukwud.okolo@gmail.com
    SMTP_PASSWORD=qspiahsstwbvwvbf
    SMTP_TLS=true
    SMTP_SSL=false
    FROM_EMAIL=noreply@taxcompliance.ng
    FROM_NAME=Nigerian Tax Compliance
    SUPPORT_EMAIL=support@taxcompliance.ng
"""

import logging
from pathlib import Path
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import smtplib
import ssl

from app.core.config import settings

logger = logging.getLogger(__name__)


# ─── HTML email templates ─────────────────────────────────────────────────────

def _base_template(content: str, title: str = "Notification") -> str:
    """Wraps content in a consistent HTML email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f0;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f0;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:#0f0e0b;padding:24px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <span style="font-family:Georgia,serif;font-size:22px;font-weight:700;color:#c8952a;letter-spacing:-0.5px;">
                    {getattr(settings, 'FROM_NAME', 'Nigerian Tax Compliance')}
                  </span>
                </td>
                <td align="right">
                  <span style="font-size:11px;color:#9e9990;text-transform:uppercase;letter-spacing:1px;">Invoice System</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px;">
            {content}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#faf9f6;padding:20px 32px;border-top:1px solid #ede9de;">
            <p style="margin:0;font-size:11px;color:#9e9990;text-align:center;">
              This email was sent by {getattr(settings, 'FROM_NAME', 'Nigerian Tax Compliance')} ·
              <a href="mailto:{getattr(settings, 'SUPPORT_EMAIL', 'support@taxcompliance.ng')}"
                 style="color:#c8952a;text-decoration:none;">
                {getattr(settings, 'SUPPORT_EMAIL', 'support@taxcompliance.ng')}
              </a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _invoice_email_body(
    customer_name: str,
    invoice_number: str,
    invoice_date: str,
    due_date: str,
    total_amount: str,
    business_name: str,
    custom_message: Optional[str] = None,
) -> str:
    message_block = f"""
      <p style="margin:0 0 16px;font-size:14px;color:#2c2a24;line-height:1.6;">
        {custom_message}
      </p>""" if custom_message else f"""
      <p style="margin:0 0 16px;font-size:14px;color:#2c2a24;line-height:1.6;">
        Please find your invoice attached. Kindly ensure payment is made by the due date.
      </p>"""

    return f"""
      <h2 style="margin:0 0 8px;font-family:Georgia,serif;font-size:22px;color:#0f0e0b;">
        Invoice {invoice_number}
      </h2>
      <p style="margin:0 0 24px;font-size:13px;color:#9e9990;">From {business_name}</p>

      {message_block}

      <!-- Invoice summary box -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:#faf9f6;border:1px solid #ede9de;border-radius:10px;margin-bottom:24px;">
        <tr>
          <td style="padding:20px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:12px;color:#9e9990;padding-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Bill To</td>
                <td style="font-size:12px;color:#9e9990;padding-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;text-align:right;">Invoice Date</td>
              </tr>
              <tr>
                <td style="font-size:15px;font-weight:600;color:#0f0e0b;padding-bottom:16px;">{customer_name}</td>
                <td style="font-size:14px;color:#2c2a24;padding-bottom:16px;text-align:right;">{invoice_date}</td>
              </tr>
              <tr>
                <td style="font-size:12px;color:#9e9990;padding-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Invoice #</td>
                <td style="font-size:12px;color:#9e9990;padding-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;text-align:right;">Due Date</td>
              </tr>
              <tr>
                <td style="font-size:14px;color:#2c2a24;padding-bottom:16px;">{invoice_number}</td>
                <td style="font-size:14px;color:#b83232;font-weight:600;padding-bottom:16px;text-align:right;">{due_date}</td>
              </tr>
              <tr>
                <td colspan="2" style="border-top:1px solid #ede9de;padding-top:16px;">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="font-size:13px;color:#9e9990;">Amount Due</td>
                      <td style="font-size:20px;font-weight:700;color:#c8952a;text-align:right;">{total_amount}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 8px;font-size:13px;color:#6b6560;">
        The PDF invoice is attached to this email for your records.
      </p>
      <p style="margin:0;font-size:13px;color:#6b6560;">
        If you have any questions, please reply to this email or contact
        <a href="mailto:{getattr(settings, 'SUPPORT_EMAIL', 'support@taxcompliance.ng')}"
           style="color:#c8952a;text-decoration:none;">
          {getattr(settings, 'SUPPORT_EMAIL', 'support@taxcompliance.ng')}
        </a>.
      </p>"""


# ─── Core send function ───────────────────────────────────────────────────────

def send_email_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    cc_email: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
) -> None:
    """
    Send an HTML email via SMTP.
    Raises on failure so callers can surface the error to the user.
    """
    from_email   = getattr(settings, 'FROM_EMAIL',   'noreply@taxcompliance.ng')
    from_name    = getattr(settings, 'FROM_NAME',    'Nigerian Tax Compliance')
    smtp_host    = getattr(settings, 'SMTP_HOST',    'smtp.gmail.com')
    smtp_port    = int(getattr(settings, 'SMTP_PORT', 587))
    smtp_user    = getattr(settings, 'SMTP_USER',    '')
    smtp_pass    = getattr(settings, 'SMTP_PASSWORD','')
    use_tls      = str(getattr(settings, 'SMTP_TLS', 'true')).lower() == 'true'
    use_ssl      = str(getattr(settings, 'SMTP_SSL', 'false')).lower() == 'true'

    # Build message
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From']    = f"{from_name} <{from_email}>"
    msg['To']      = to_email
    if cc_email:
        msg['Cc'] = cc_email

    # HTML body
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    # Attachment
    if attachment_bytes and attachment_filename:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{attachment_filename}"')
        part.add_header('Content-Type', 'application/pdf')
        msg.attach(part)

    recipients = [to_email] + ([cc_email] if cc_email else [])

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                if use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, recipients, msg.as_string())

        logger.info(f"Email sent to {to_email} | subject: {subject}")

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed — check SMTP_USER and SMTP_PASSWORD")
        raise ValueError("Email authentication failed. Check your SMTP credentials.")
    except smtplib.SMTPRecipientsRefused:
        logger.error(f"Recipient refused: {to_email}")
        raise ValueError(f"Email address rejected by server: {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        raise ValueError(f"Failed to send email: {str(e)}")


# ─── Public helpers ───────────────────────────────────────────────────────────

def send_invoice_email(
    to_email: str,
    customer_name: str,
    invoice_number: str,
    invoice_date: str,
    due_date: str,
    total_amount: str,
    business_name: str,
    pdf_bytes: Optional[bytes] = None,
    custom_message: Optional[str] = None,
    cc_email: Optional[str] = None,
) -> None:
    """Send an invoice email with optional PDF attachment."""
    body = _invoice_email_body(
        customer_name=customer_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        total_amount=total_amount,
        business_name=business_name,
        custom_message=custom_message,
    )
    html = _base_template(body, title=f"Invoice {invoice_number}")
    send_email_smtp(
        to_email=to_email,
        subject=f"Invoice {invoice_number} from {business_name}",
        html_body=html,
        cc_email=cc_email,
        attachment_bytes=pdf_bytes,
        attachment_filename=f"invoice-{invoice_number}.pdf" if pdf_bytes else None,
    )


def send_welcome_email(to_email: str, user_name: str) -> None:
    """Send welcome email to new users."""
    body = f"""
      <h2 style="margin:0 0 16px;font-family:Georgia,serif;font-size:22px;color:#0f0e0b;">
        Welcome, {user_name}! 🎉
      </h2>
      <p style="margin:0 0 12px;font-size:14px;color:#2c2a24;line-height:1.6;">
        Your account has been created successfully. You can now start creating invoices,
        managing customers, and tracking payments — all in one place.
      </p>
      <p style="margin:0;font-size:13px;color:#6b6560;">
        Need help getting started? Contact us at
        <a href="mailto:{getattr(settings, 'SUPPORT_EMAIL', 'support@taxcompliance.ng')}"
           style="color:#c8952a;text-decoration:none;">
          {getattr(settings, 'SUPPORT_EMAIL', 'support@taxcompliance.ng')}
        </a>.
      </p>"""
    html = _base_template(body, title="Welcome!")
    send_email_smtp(
        to_email=to_email,
        subject=f"Welcome to {getattr(settings, 'FROM_NAME', 'Nigerian Tax Compliance')}",
        html_body=html,
    )