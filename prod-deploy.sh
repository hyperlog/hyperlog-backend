python manage.py migrate
python manage.py collectstatic --no-input
daphne hyperlog.asgi:application
