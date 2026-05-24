from .models import EmailLog


def create_email_log(
    *,
    task_name,
    recipient='',
    subject='',
    status,
    tenant=None,
    related_object_id='',
    message='',
    error='',
):
    return EmailLog.all_objects.create(
        tenant=tenant,
        task_name=task_name,
        recipient=recipient or '',
        subject=subject or '',
        status=status,
        related_object_id=str(related_object_id or ''),
        message=message or '',
        error=error or '',
    )
