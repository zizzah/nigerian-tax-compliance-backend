import asyncio
from app.core.email import send_email_smtp
import logging

logger = logging.getLogger(__name__)

async def send_email_async(to_email, subject, html_body, cc_email=None):
    loop = asyncio.get_event_loop()

    try:
        await loop.run_in_executor(
            None,
            send_email_smtp,
            to_email,
            subject,
            html_body,
            cc_email
        )
        return True, None
    except Exception as e:
        return False, str(e)