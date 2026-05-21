#!/bin/sh
set -e

run_startup_tasks() {
    case "$*" in
        *"manage.py runserver"*|*"gunicorn "*|*"daphne "*|*"uvicorn "*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

if [ "${RUN_STARTUP_TASKS:-true}" = "true" ] && run_startup_tasks "$@"; then
    attempts=0
    max_attempts="${MIGRATION_MAX_ATTEMPTS:-30}"

    until python manage.py migrate --noinput; do
        attempts=$((attempts + 1))

        if [ "$attempts" -ge "$max_attempts" ]; then
            echo "Database migrations failed after ${max_attempts} attempts."
            exit 1
        fi

        echo "Database is not ready yet. Retrying migrations in 2 seconds..."
        sleep 2
    done

    python manage.py collectstatic --noinput
fi

exec "$@"
