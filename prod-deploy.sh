export DEBUG=False

python manage.py migrate
python manage.py collectstatic --no-input
daphne hyperlog.asgi:application
