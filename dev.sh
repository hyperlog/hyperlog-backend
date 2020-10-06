export DEBUG=True

python -m pip install --upgrade -r requirements.txt

python manage.py migrate
python manage.py collectstatic --no-input
python manage.py runserver 0.0.0.0:8000
