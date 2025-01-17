# encoding: UTF-8
import argparse

from typing import List, Any, Dict

## Веб сервер
import cherrypy

# Драйвер PostgreSQL
import psycopg2 as pg_driver
import psycopg2.pool as pool

# ORM
from peewee import *

# import logging
# logger = logging.getLogger('peewee')
# logger.addHandler(logging.StreamHandler())
# logger.setLevel(logging.DEBUG)

parser = argparse.ArgumentParser(description='Hello DB web application')
parser.add_argument('--pg-host', help='PostgreSQL host name', default='localhost')
parser.add_argument('--pg-port', help='PostgreSQL port', default=5432)
parser.add_argument('--pg-user', help='PostgreSQL user', default='postgres')
parser.add_argument('--pg-password', help='PostgreSQL password', default='')
parser.add_argument('--pg-database', help='PostgreSQL database', default='postgres')

args = parser.parse_args()

db = PostgresqlDatabase(args.pg_database, user=args.pg_user, host=args.pg_host, password=args.pg_password)
pg_pool = pool.SimpleConnectionPool(1, 100, user=args.pg_user, host=args.pg_host, password=args.pg_password)


# Классы ORM модели
class PlanetEntity(Model):
    id = PrimaryKeyField()
    distance = DecimalField()
    name = TextField(unique=True)  # 4. Передадим параметр unique=True для документировать. Чтобы можно было
                                   # узнать об уникальности поля, глядя на ORM-модель.

    class Meta:
        database = db
        db_table = "planet"


class FlightEntity(Model):
    id = PrimaryKeyField()
    date = DateField()
    planet = ForeignKeyField(PlanetEntity, related_name='flights')

    class Meta:
        database = db
        db_table = "flight"  # 1. вместо представления FlightEntityView будем отображать таблицу FlightEntity.
                             # В представлении FlightEntityView есть JOIN FlightAvailableSeatsView, в котором
                             # в свою очередь есть JOIN Spacecraft. Это лишняя работа по отношению к запросу,
                             # выполняемому в обработчике flights


@cherrypy.expose
class App(object):

    def __init__(self):
        pass

    @cherrypy.expose
    def index(self):
        return "Привет. Тебе интересно сходить на /flights, /delete_planet или /delay_flights"

    # Отображает таблицу с полетами в указанную дату или со всеми полетами,
    # если дата не указана
    #
    # Пример: /flights?flight_date=2084-06-12
    #         /flights
    @cherrypy.expose
    def flights(self, flight_date=None):
        # 3. Кэширование удалено. Во-первых, кэш может забить всю оперативную память.
        # Во-вторых, в коде баг: если информация о полёте будет обновлена, кэш об
        # этом не узнает.
        # Okeyla, now let's format the result HTML
        result_text = """
        <html>
        <body>
        <style>
    table > * {
        text-align: left;
    }
    td {
        padding: 5px;
    }
    table { 
        border-spacing: 5px; 
        border: solid grey 1px;
        text-align: left;
    }
        </style>
        <table>
            <tr><th>Flight ID</th><th>Date</th><th>Planet</th><th>Planet ID</th></tr>
        """
        query = (FlightEntity
                 .select(
            FlightEntity.id,
            FlightEntity.date,
            PlanetEntity.name,
            PlanetEntity.id.alias('planet_id')
        ).join(PlanetEntity))

        if flight_date is not None:
            query = query.where(FlightEntity.date == flight_date)

        for flight_id, flight_date, planet_name, planet_id  in query.namedtuples():
            # 5. XSS-уязвимость. Если окажется, что какая-то из планет называется
            # <script>alert('Boo!')</script>, то этот код будет исполнен на
            # стороне клиента
            result_text += '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(flight_id, flight_date,
                                                                                          planet_name,
                                                                                          planet_id)
        result_text += """
        </table>
        </body>
        </html>"""
        cherrypy.response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return result_text

    # Сдвигает полёты, начинающиеся в указанную дату на указанный интервал.
    # Формат даты: yyyy-MM-dd (например 2019-12-19)
    # Формат интервала: 1day, 2weeks, и так далее.
    # https://www.postgresql.org/docs/current/datatype-datetime.html#DATATYPE-INTERVAL-INPUT
    #
    # пример: /delay_flights?flight_date=2084-06-12&interval=1day
    @cherrypy.expose
    def delay_flights(self, flight_date=None, interval=None):
        if flight_date is None or interval is None:
            return "Please specify flight_date and interval arguments, like this: /delay_flights?flight_date=2084-06-12&interval=1week"

        # Update flights, reuse connections 'cause 'tis faster
        # 2. В комментарии выше заявлено, что здесь переиспользовались соединения, но это не так.
        # Чтобы переиспользовать сессии, воспользуемся пулом соединений базы данных, это позволит
        # и не выполнять на каждый запрос такую дорогую операцию как открытие соединений. Также
        # будем использовать пулом соединений в обработчике delete_planet.
        db = pg_pool.getconn()
        db.autocommit = True
        try:
            cur = db.cursor()
            cur.execute("UPDATE Flight SET date=date + interval %s WHERE date=%s", (interval, flight_date))
        finally:
            pg_pool.putconn(db)

    # Удаляет планету с указанным идентификатором.
    # Пример: /delete_planet?planet_id=1
    @cherrypy.expose
    def delete_planet(self, planet_id=None):
        if planet_id is None:
            return "Please specify planet_id, like this: /delete_planet?planet_id=1"
        db = pg_pool.getconn()
        db.autocommit = True
        try:
            cur = db.cursor()
            cur.execute("DELETE FROM Planet WHERE id = %s", (planet_id,))
        finally:
            pg_pool.putconn(db)


if __name__ == '__main__':
    cherrypy.quickstart(App())
