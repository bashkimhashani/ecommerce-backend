from celery.signals import task_failure

from .models import FailedTask


@task_failure.connect
def log_exhausted_task(
    sender=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **extra,
):
    request = getattr(sender, 'request', None)
    retries = getattr(request, 'retries', 0)
    max_retries = getattr(sender, 'max_retries', None)

    if max_retries is not None and retries < max_retries:
        return

    FailedTask.all_objects.create(
        task_name=getattr(sender, 'name', str(sender)),
        arguments={
            'args': list(args or []),
            'kwargs': dict(kwargs or {}),
        },
        exception=str(exception),
        traceback=str(einfo or traceback or ''),
    )
