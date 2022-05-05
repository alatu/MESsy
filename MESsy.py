from asyncore import read
from email.message import Message
from os import stat
from fastapi import FastAPI, status, Response
from fastapi.staticfiles import StaticFiles
import sqlite3
from time import time, asctime, localtime, daylight, tzname
from datetime import date, datetime
from pydantic import BaseModel
from starlette.responses import FileResponse
import configparser


config: configparser.ConfigParser.read


class Help_Object(BaseModel):
    user: str
    room: str
    time: str
    machine: int


class Room(BaseModel):
    id: int
    room: str


class User(BaseModel):
    id: int
    user: str


class Login_Info(BaseModel):
    Rooms: list[Room]
    Users: list[User]


class Login_Data(BaseModel):
    User: int
    Room: int


class Step_Info(BaseModel):
    Job: int
    Step_Number: int
    Needed_Materials: str
    Description: str
    Specified_Time: float
    URL_Pictures: list[str]
    URL_Videos: list[str]
    Additional_Informations: str


class Job_Infos(BaseModel):
    Materialnumber: int
    Product_Name: str
    Needle_Size: int
    Yarn_Count: int
    Quantity: int
    Steps: list[Step_Info]


class Stats(BaseModel):
    ratio_done: float


class Error_Message(BaseModel):
    Message: str
    Interrupted: bool
    Produced: int


class Cancle_Job(BaseModel):
    Produced: int


class Result_Message(BaseModel):
    message: str


def time_to_str(time):
    return f"{asctime(localtime(time))} {tzname[daylight]}"


def cancel_job(m_id: int, produced: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM Lock_DB;
        """)  # Lock DB to prevent race conditions
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            SELECT cj.id_product, cj.id, ml.id_current_user, cj.quantity FROM Current_Jobs cj
            INNER JOIN Machine_login ml ON ml.id==cj.id_machine
            WHERE ml.id_machine == ?;
        """, (m_id, ))
        rows = cursor.fetchall()
        if not rows:
            return
        cursor.execute("""
            INSERT INTO Open_Jobs(id_product, quantity) VALUES(?, ?);
        """, (rows[0][0], rows[0][3] - produced))
        cursor.execute("""
            DELETE FROM Current_Jobs WHERE id == ?;
        """, (rows[0][1], ))
        if produced > 0:
            cursor.execute("""
                INSERT INTO Produced_Products (id_product, id_user, serial_number_machine, completion_time, quantity)
                VALUES (?, ?, ?, ?, ?);
            """, (rows[0][0], rows[0][2], m_id, int(time()), produced))


def get_job_from_db(m_id):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.product_name, p.needle_size, p.yarn_count, cj.quantity FROM Current_Jobs cj
            INNER JOIN Machine_login ml ON cj.id_machine==ml.id
            INNER JOIN Products p ON cj.id_product==p.id
            WHERE ml.id_machine == ?;
        """, (m_id, ))
        rows_product = cursor.fetchall()
        cursor.execute("""
            SELECT ps.id, ps.needed_materials, ps.step_description, ps.specified_time, ps.url_images, ps.url_videos, ps.additional_information, ps.step_number FROM Current_Jobs cj
            INNER JOIN Machine_login ml ON cj.id_machine==ml.id
            INNER JOIN Products p ON cj.id_product==p.id
            INNER JOIN Product_Steps ps ON p.id==cj.id_product
            WHERE ml.id_machine == ?;
        """, (m_id, ))
        rows_steps = cursor.fetchall()
    return rows_product, rows_steps


app = FastAPI(title="MESsy app")


@app.on_event("startup")
def startup():
    global config
    config = configparser.ConfigParser()
    config.read("MESsy.conf")


@app.get("/favicon.ico")
def favicon():
    return FileResponse("MESsy/favicon.png")


@app.get("/MESsy/logininfo")
def get_logininfo():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor_user = conn.cursor()
        cursor_user.execute("""
            SELECT id, user_name from Users;
        """)
        rows_user = cursor_user.fetchall()
        cursor_room = conn.cursor()
        cursor_room.execute("""
            SELECT id, room_description from Rooms;
        """)
        rows_room = cursor_room.fetchall()
    Rooms = []
    for i in rows_room:
        Rooms.append(Room(id=i[0], room=i[1]))
    Users = []
    for i in rows_user:
        Users.append(User(id=i[0], user=i[1]))
    return Login_Info(Users=Users, Rooms=Rooms)


@app.post("/MESsy/{m_id}/login", status_code=status.HTTP_201_CREATED)
def post_login(m_id: int, login_data: Login_Data, response: Response):
    success = True
    message = None
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM Machine WHERE id==?;
            """, (m_id, ))
            rows = cursor.fetchall()
            if not rows:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return Result_Message(message="Serialnumber doesn't exist")
            cursor.execute("""
                INSERT INTO Machine_login(id_room, id_current_user, id_machine)
                VALUES (?, ?, ?);
            """, (login_data.Room, login_data.User, m_id))
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_409_CONFLICT
        success = False
        message = "Machine or User is already logged in"
    return Result_Message(message=message)


@app.delete("/MESsy/{m_id}/login")
def delete_login(m_id: int, response: Response):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Lock_DB;
        """)  # Lock DB to prevent race conditions
        cursor.execute("""
            SELECT * FROM Current_Jobs cj
            INNER JOIN Machine_login ml ON ml.id==cj.id_machine
            WHERE ml.id_machine==?;
        """, (m_id, ))
        rows = cursor.fetchall()
        print(rows)
        if rows:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Result_Message(message="The User has a current Job. Please cancle or complete it before logging out!")
        cursor.execute("""
            DELETE FROM Machine_login WHERE id_machine == ?;
        """, (m_id, ))
    return Result_Message(message="Logged out")


@app.get("/MESsy/{m_id}/help")
def get_help(m_id: int, response: Response):
    help_time = int(time())
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM Machine_Login
            WHERE id_machine == ?
        """, (m_id, ))
        rows = cursor.fetchall()
        if not rows:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Result_Message(message="Machine not logged in")
        cursor.execute("""
            INSERT INTO help (id_machine_login, call_time) VALUES (?, ?);
        """, (rows[0][0], help_time))
    return Result_Message(message="Help requested")


@app.get("/MESsy/{m_id}/job")
def get_job(m_id: int, response: Response):
    rows = get_job_from_db(m_id)
    if rows[0] and rows[1]:
        steps = []
        for i in rows[1]:
            steps.append(Step_Info(Job=i[0], Needed_Materials=i[1], Description=i[2], Specified_Time=i[3], URL_Pictures=i[4].split(
                ","), URL_Videos=i[5].split(","), Additional_Informations=i[6], Step_Number=i[7]))
        return_value = Job_Infos(
            Materialnumber=rows[0][0][0], Product_Name=rows[0][0][1], Needle_Size=rows[0][0][2], Yarn_Count=rows[0][0][3], Steps=steps, Quantity=rows[0][0][4])
    else:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM Lock_DB;
            """)  # Lock DB to prevent race conditions
            cursor.execute("""
                PRAGMA foreign_keys = 1;
            """)
            cursor.execute("""
                SELECT o.id, ml.id, p.id, o.quantity FROM Open_Jobs o
                INNER JOIN Machine_login ml ON ml.id_machine==?
                INNER JOIN Machine m ON m.id==ml.id_machine
                INNER JOIN Products p ON p.id==o.id_product
                WHERE p.id_machine_type == m.id_machine_type;
            """, (m_id, ))
            rows_possible_jobs = cursor.fetchall()
            if not rows_possible_jobs:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return Result_Message(message="No Job found")
            cursor.execute("""
                INSERT INTO Current_Jobs(id_machine, id_product, quantity)
                VALUES (?, ?, ?);
            """, (rows_possible_jobs[-1][1], rows_possible_jobs[-1][2], rows_possible_jobs[-1][3]))
            cursor.execute("""
                DELETE FROM Open_Jobs WHERE id==?;
            """, (rows_possible_jobs[-1][0], ))
        rows = get_job_from_db(m_id)
        steps = []
        for i in rows[1]:
            steps.append(Step_Info(Job=i[0], Needed_Materials=i[1], Description=i[2], Specified_Time=i[3], URL_Pictures=i[4].split(
                ","), URL_Videos=i[5].split(","), Additional_Informations=i[6], Step_Number=i[7]))
            return_value = Job_Infos(
                Materialnumber=rows[0][0][0], Product_Name=rows[0][0][1], Needle_Size=rows[0][0][2], Yarn_Count=rows[0][0][3], Steps=steps, Quantity=rows[0][0][4])
    return return_value


@app.post("/MESsy/{m_id}/job")
def post_job(m_id: int, response: Response):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM Lock_DB;
        """)  # Lock DB to prevent race conditions
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            SELECT cj.id_product, cj.quantity, ml.id_current_user, cj.id FROM Current_Jobs cj
            INNER JOIN Machine_login ml ON ml.id==cj.id_machine
            WHERE ml.id_machine==?;
        """, (m_id, ))
        rows = cursor.fetchall()
        if not rows:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Result_Message(message="No active Job found")
        cursor.execute("""
            INSERT INTO Produced_Products (id_product, id_user, serial_number_machine, completion_time, quantity)
            VALUES (?, ?, ?, ?, ?);
        """, (rows[0][0], rows[0][2], m_id, int(time()), rows[0][1]))
        cursor.execute("""
            DELETE FROM Current_Jobs WHERE id==?;
        """, (rows[0][3], ))
    return Result_Message(message="Job approved")


@app.post("/MESsy/{m_id}/cancel_job")
def post_cancel_job(m_id: int, cancle_job: Cancle_Job):
    cancel_job(m_id, cancle_job.Produced)
    return Result_Message(message="Job canceled")


@app.post("/MESsy/{m_id}/error")
def post_error(m_id: int, error: Error_Message):
    print(
        f"Machine {m_id} got an critical error with message: {error.Message}")
    if error.Interrupted:
        cancel_job(m_id, error.Produced)
    return Result_Message(message="error reported")


@app.get("/MESsy/{m_id}/stats")
def get_stats(m_id: int, response: Response):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id_current_user FROM Machine_login WHERE id_machine==?;
        """, (m_id, ))
        rows = cursor.fetchall()
        if not rows:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Result_Message(message="No User logged in")
        cursor.execute("""
            SELECT ps.specified_time, pp.quantity FROM Produced_Products pp
            INNER JOIN Products p ON p.id==pp.id_product
            INNER JOIN Product_Steps ps ON p.id==ps.id_product
            WHERE pp.id_user==? AND pp.completion_time>=?;
        """, (rows[0][0], int(datetime.combine(date.today(), datetime.min.time()).timestamp())))
        rows = cursor.fetchall()
    complete_time = sum(map(lambda x: x[0] * x[1], rows))
    return Stats(ratio_done=round(complete_time / float(config["Work"]["daily_work_pensum"]), 3))


@app.get("/uiapi/help")
def ui_get_help():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Help WHERE call_time <= ?;",
                       (int(time()) - 3_600,))
        cursor.execute("""
            SELECT h.call_time, u.user_name, r.room_description, m.id_machine FROM Help h 
            INNER JOIN Machine_login m ON h.id_machine_login==m.id
            INNER JOIN Users u ON m.id_current_user==u.id
            INNER JOIN Rooms r ON m.id_room==r.id;
        """)
        rows = cursor.fetchall()
    rows = map(lambda x: Help_Object(
        time=time_to_str(x[0]), user=x[1], room=x[2], machine=x[3]), rows)
    return list(rows)


@app.get("/uiapi/logout_all")
def ui_logout_all():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Machine_login;
        """)
    return Result_Message(message="Logged out all users")


app.mount("/images", StaticFiles(directory="MESsy/images"), name="images")
app.mount("/videos", StaticFiles(directory="MESsy/videos"), name="videos")
app.mount("/ui", StaticFiles(directory="MESsy/UI"), name="UI")
