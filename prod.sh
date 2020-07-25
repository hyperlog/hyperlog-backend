export DEBUG=False

python -m pip install --upgrade -r requirements.txt

python manage.py migrate
python manage.py collectstatic --no-input
daphne hyperlog.asgi:application --bind localhost --port 8000
