Street agitation bot
=======

Telegram bot

## Install

    $ git clone git@github.com:Kurpilyansky/street-agitation-telegram-bot.git
    $ cd street-agitation-telegram-bot/
    $ virtualenv -p python3 venv
    $ source ./venv/bin/activate
    $ pip install -Ur src/requirements.txt

Ask someone to make you a database dump of the test instance:

    $ python src/web/manage.py dumpdata > db.json

Then load it locally:

    $ python src/web/manage.py migrate
    $ src/web/manage.py sqlflush | sqlite3 db.sqlite3
    $ python src/web/manage.py loaddata db.json

Run bot:

    set valid BOT_TOKEN in bot_settings.py
    $ python manage.py run_bot
   
Run web server (database view):

    $ python manage.py createsuperuser # only at first time
    $ python manage.py runserver
    Open http://localhost:8000/admin in browser
