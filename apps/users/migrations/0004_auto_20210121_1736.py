# Generated by Django 2.2 on 2021-01-21 17:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_auto_20200905_1358'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='about_page',
        ),
        migrations.AddField(
            model_name='user',
            name='about',
            field=models.TextField(blank=True, verbose_name='About information'),
        ),
    ]