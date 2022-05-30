import random
from fastapi import FastAPI, UploadFile, status, Response
from fastapi.staticfiles import StaticFiles
import sqlite3
from time import time, asctime, localtime, daylight, tzname
from datetime import date, datetime
from pydantic import BaseModel
from starlette.responses import FileResponse
import configparser
import aiofiles
import os
import csv
import shutil

config: configparser.ConfigParser.read


class Help_Object(BaseModel):
    user: str
    room: str
    time: str
    machine: int


class Room(BaseModel):
    id: int | None
    room: str


class User(BaseModel):
    id: int | None
    user: str


class Login_Info(BaseModel):
    Rooms: list[Room]
    Users: list[User]
    Serialnumbers: list[int]


class Login_Data(BaseModel):
    User: int
    Room: int


class Step_Info(BaseModel):
    Job: int
    Step_Number: int
    Specified_Time: float
    Additional_Informations: str
    Step_Description: str


class Job_Infos(BaseModel):
    Materialnumber: int
    Product_Name: str
    Quantity: int
    Description: str
    Split: int
    URL_Pictures: list[str]
    URL_Videos: list[str]
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


class Machine_Type(BaseModel):
    id: int | None
    machine_type: str


class Machine(BaseModel):
    id: int
    id_machine_type: int
    machine_type: str | None


class Logins(BaseModel):
    serialnumber: int
    cur_product_name: str
    quantity: int
    user: str
    room: str


class Open_Job(BaseModel):
    id: int | None
    id_product: int
    quantity: int
    product_name: str | None


class Product(BaseModel):
    id: int
    Machine_Type: str
    Name: str
    Description: str


def logout_user(m_id: int, response: Response = None):
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
        if response is not None and rows:
            response.status_code = status.HTTP_400_BAD_REQUEST
        if rows:
            return Result_Message(message="The User has a current Job. Please cancle or complete it before logging out!")
        cursor.execute("""
            DELETE FROM Machine_login WHERE id_machine == ?;
        """, (m_id, ))
    return Result_Message(message="Logged out")


def time_to_str(time):
    return f"{asctime(localtime(time))} {tzname[daylight]}"


def job_done(m_id: int, amount: int = None):
    if amount is not None and amount < 0:
        return False
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
        if not rows or (amount is not None and amount > rows[0][1]):
            return False
        quantity = amount if amount is not None else rows[0][1]
        cursor.execute("""
            INSERT INTO Produced_Products (id_product, id_user, serial_number_machine, completion_time, quantity)
            VALUES (?, ?, ?, ?, ?);
        """, (rows[0][0], rows[0][2], m_id, int(time()), quantity))
        cursor.execute("""
            SELECT next_product_name, n_partitions FROM Products WHERE id==?;
        """, (rows[0][0], ))
        rows_next = cursor.fetchall()
        if rows_next[0][0]:
            cursor.execute("""
                SELECT id FROM Products WHERE product_name==?;
            """, (rows_next[0][0], ))
            rows_new = cursor.fetchall()
            if rows_next[0][1] > 0:
                for i in range(0, quantity - rows_next[0][1], rows_next[0][1]):
                    cursor.execute("""
                        INSERT INTO Open_Jobs (id_product, quantity)
                        VALUES (?, ?);
                    """, (rows_new[0][0], rows_next[0][1]))
                cursor.execute("""
                    INSERT INTO Open_Jobs (id_product, quantity)
                    VALUES (?, ?);
                """, (rows_new[0][0], j if (j := (quantity % rows_next[0][1])) != 0 else rows_next[0][1]))
            else:
                cursor.execute("""
                    INSERT INTO Open_Jobs (id_product, quantity)
                    VALUES (?, ?);
                """, (rows_new[0][0], quantity))
        if amount is not None:
            cursor.execute("""
                INSERT INTO Open_Jobs (id_product, quantity)
                VALUES (?, ?);
            """, (rows[0][0], rows[0][1] - amount))
        cursor.execute("""
            DELETE FROM Current_Jobs WHERE id==?;
        """, (rows[0][3], ))
    return True


def get_job_from_db(m_id, cursor):
    cursor.execute("""
        SELECT p.id, p.product_name, cj.quantity, p.product_description, p.n_partitions FROM Current_Jobs cj
        INNER JOIN Machine_login ml ON cj.id_machine==ml.id
        INNER JOIN Products p ON cj.id_product==p.id
        WHERE ml.id_machine == ?;
    """, (m_id, ))
    rows_product = cursor.fetchall()
    cursor.execute("""
        SELECT ps.id, ps.specified_time, ps.additional_information, ps.step_number, ps.step_description FROM Current_Jobs cj
        INNER JOIN Machine_login ml ON cj.id_machine==ml.id
        INNER JOIN Products p ON cj.id_product==p.id
        INNER JOIN Product_Steps ps ON p.id==cj.id_product
        WHERE ml.id_machine == ?;
    """, (m_id, ))
    rows_steps = cursor.fetchall()
    images = []
    videos = []
    if rows_product and rows_steps:
        path = os.path.join("./MESsy/images", str(rows_product[0][0]))
        if os.path.exists(path):
            images = [
                "/images/" + str(rows_product[0][0]) + "/" + f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        path = os.path.join("./MESsy/videos", str(rows_product[0][0]))
        if os.path.exists(path):
            videos = [
                "/videos/" + str(rows_product[0][0]) + "/" + f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    return rows_product, rows_steps, images, videos


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
        cursor_serialnumber = conn.cursor()
        cursor_serialnumber.execute("""
            SELECT id from Machine;
        """)
        rows_serialnumber = cursor_serialnumber.fetchall()
    Rooms = []
    for i in rows_room:
        Rooms.append(Room(id=i[0], room=i[1]))
    Users = []
    for i in rows_user:
        Users.append(User(id=i[0], user=i[1]))
    Serialnumbers = []
    for i in rows_serialnumber:
        Serialnumbers.append(i[0])
    return Login_Info(Users=Users, Rooms=Rooms, Serialnumbers=Serialnumbers)


@app.post("/MESsy/{m_id}/login", status_code=status.HTTP_201_CREATED)
def post_login(m_id: int, login_data: Login_Data, response: Response):
    message = "User logged in"
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
        message = "Machine or User is already logged in"
    return Result_Message(message=message)


@app.delete("/MESsy/{m_id}/login")
def delete_login(m_id: int, response: Response):
    return logout_user(m_id, response)


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
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM Lock_DB;
        """)  # Lock DB to prevent race conditions
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        rows = get_job_from_db(m_id, cursor)
        if rows[0] and rows[1]:
            steps = []
            for i in rows[1]:
                steps.append(Step_Info(Job=i[0], Specified_Time=i[1] if i[1] != "" else 0,
                             Additional_Informations=i[2], Step_Number=i[3], Step_Description=i[4]))
            return_value = Job_Infos(
                Materialnumber=rows[0][0][0], Product_Name=rows[0][0][1], Steps=steps, Quantity=rows[0][0][2], URL_Pictures=rows[2], URL_Videos=rows[3], Description=rows[0][0][3], Split=rows[0][0][4])
        else:
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
            rows = get_job_from_db(m_id, cursor)
            steps = []
            for i in rows[1]:
                steps.append(Step_Info(Job=i[0], Specified_Time=i[1] if i[1] != "" else 0,
                             Additional_Informations=i[2], Step_Number=i[3], Step_Description=i[4]))
            return_value = Job_Infos(
                Materialnumber=rows[0][0][0], Product_Name=rows[0][0][1], Steps=steps, Quantity=rows[0][0][2], URL_Pictures=rows[2], URL_Videos=rows[3], Description=rows[0][0][3], Split=rows[0][0][4])
    return return_value


@app.post("/MESsy/{m_id}/job")
def post_job(m_id: int, response: Response):
    if not job_done(m_id):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="No active Job found")
    return Result_Message(message="Job approved")


@app.post("/MESsy/{m_id}/cancel_job")
def post_cancel_job(m_id: int, cancle_job: Cancle_Job, response: Response):
    if not job_done(m_id, cancle_job.Produced):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="Couldn't cancle Job")
    return Result_Message(message="Job cancled")


@app.post("/MESsy/{m_id}/error")
def post_error(m_id: int, error: Error_Message, response: Response):
    print(
        f"Machine {m_id} got an critical error with message: {error.Message}")
    if error.Interrupted and not job_done(m_id, error.Produced):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="Couldn't cancle Job")
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
    complete_time = sum(map(lambda x: float(x[0] if x[0] else 0) * x[1], rows))
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
            SELECT id_machine FROM Machine_login;
        """)
        rows = cursor.fetchall()
    for i in rows:
        logout_user(i[0])
    return Result_Message(message="Logged out all machines without active Jobs")


@app.get("/uiapi/login")
def ui_get_login():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id_machine, id_current_user, id_room FROM Machine_login;
        """)
        rows = cursor.fetchall()
        result = []
        for i in rows:
            cursor.execute("""
                SELECT p.product_name, cj.quantity FROM Current_Jobs cj
                INNER JOIN Products p ON p.id==cj.id_product
                INNER JOIN Machine_login ml ON ml.id==cj.id_machine
                WHERE ml.id_machine==?;
            """, (i[0], ))
            rows_cj = cursor.fetchall()
            cursor.execute("""
                SELECT user_name FROM Users
                WHERE id==?;
            """, (i[1], ))
            rows_user = cursor.fetchall()
            cursor.execute("""
                SELECT room_description FROM Rooms
                WHERE id==?;
            """, (i[2], ))
            rows_room = cursor.fetchall()
            result.append(Logins(serialnumber=i[0], cur_product_name=rows_cj[0][0] if rows_cj else "Kein aktueller Job gefunden",
                          quantity=rows_cj[0][1] if rows_cj else 0, user=rows_user[0][0], room=rows_room[0][0]))
    return result


@app.delete("/uiapi/login/{m_id}")
def ui_delete_login(m_id: int, response: Response):
    return logout_user(m_id, response)


@app.get("/uiapi/machinetype")
def ui_get_machine_type():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, machine_type FROM Machine_Type;
        """)
        rows = cursor.fetchall()
    machine_types = []
    for i in rows:
        machine_types.append(Machine_Type(id=i[0], machine_type=i[1]))
    return machine_types


@app.post("/uiapi/machinetype")
def ui_post_machine_type(machine_type: Machine_Type, response: Response):
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Machine_Type (machine_type)
                VALUES (?);
            """, (machine_type.machine_type, ))
        return Result_Message(message="Machine Type created")
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="Machinetype already exists")


@app.put("/uiapi/machinetype/{id}")
def ui_put_machine_type(id: int, machine_type: Machine_Type, response: Response):
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE Machine_Type SET machine_type=? WHERE id==?;
            """, (machine_type.machine_type, id))
        return Result_Message(message="Machine Type updated")
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="Machinetype already exists")


@app.delete("/uiapi/machinetype/{id}")
def ui_delete_machine_type(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Machine_Type WHERE id==?;
        """, (id, ))
    return Result_Message(message="Machine Type deleted")


@app.get("/uiapi/machine")
def ui_get_machine_type():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, m.id_machine_type, mt.machine_type FROM Machine m
            INNER JOIN Machine_Type mt ON mt.id==m.id_machine_type;
        """)
        rows = cursor.fetchall()
    machines = []
    for i in rows:
        machines.append(
            Machine(id=i[0], id_machine_type=i[1], machine_type=i[2]))
    return machines


@app.post("/uiapi/machine")
def ui_post_machine(machine: Machine):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Machine (id, id_machine_type)
            VALUES (?, ?);
        """, (machine.id, machine.id_machine_type))
    return Result_Message(message="Machine created")


@app.delete("/uiapi/machine/{id}")
def ui_delete_machine(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Machine WHERE id==?;
        """, (id, ))
    return Result_Message(message="Machine deleted")


@app.get("/uiapi/room")
def ui_get_room():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, room_description FROM Rooms;
        """)
        rows = cursor.fetchall()
    rooms = []
    for i in rows:
        rooms.append(Room(id=i[0], room=i[1]))
    return rooms


@app.post("/uiapi/room")
def ui_post_room(room: Room, response: Response):
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Rooms (room_description)
                VALUES (?);
            """, (room.room, ))
        return Result_Message(message="Room created")
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="Room already exists")


@app.put("/uiapi/room/{id}")
def ui_put_room(id: int, room: Room, response: Response):
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE Rooms SET room_description==? WHERE id==?;
            """, (room.room, id))
        return Result_Message(message="Room updated")
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="Room already exists")


@app.delete("/uiapi/room/{id}")
def ui_delete_room(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Rooms WHERE id==?;
        """, (id, ))
    return Result_Message(message="Room deleted")


@app.get("/uiapi/user")
def ui_get_user():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_name FROM Users;
        """)
        rows = cursor.fetchall()
    rooms = []
    for i in rows:
        rooms.append(User(id=i[0], user=i[1]))
    return rooms


@app.post("/uiapi/user")
def ui_post_user(user: User, response: Response):
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Users (user_name)
                VALUES (?);
            """, (user.user, ))
        return Result_Message(message="User created")
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="User already exists")


@app.put("/uiapi/user/{id}")
def ui_put_user(id: int, user: User, response: Response):
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE Users SET user_name==? WHERE id==?;
            """, (user.user, id))
        return Result_Message(message="User updated")
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return Result_Message(message="User already exists")


@app.delete("/uiapi/user/{id}")
def ui_delete_user(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Users WHERE id==?;
        """, (id, ))
    return Result_Message(message="User deleted")


@app.get("/uiapi/open_job")
def ui_get_open_job():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT oj.id, oj.id_product, oj.quantity, p.product_name FROM Open_Jobs oj
            INNER JOIN Products p ON p.id==oj.id_product;
        """)
        rows = cursor.fetchall()
    open_jobs = []
    for i in rows:
        open_jobs.append(
            Open_Job(id=i[0], id_product=i[1], quantity=i[2], product_name=i[3]))
    return open_jobs


@app.post("/uiapi/open_job")
def ui_post_open_job(open_job: Open_Job):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Open_Jobs (id_product, quantity)
            VALUES (?, ?);
        """, (open_job.id_product, open_job.quantity))
    return Result_Message(message="Open Job created")


@app.delete("/uiapi/open_job/{id}")
def ui_delete_open_job(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Open_Jobs WHERE id==?;
        """, (id, ))
    return Result_Message(message="Open Job deleted")


@app.get("/uiapi/videos/{p_id}")
def ui_get_videos(p_id: int, response: Response):
    path = os.path.join("./MESsy/videos", str(p_id))
    if os.path.exists(path):
        return [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return Result_Message(message="Not found")


@app.post("/uiapi/uploadvideos/{p_id}")
async def ui_uploadvideos(p_id: int, videos: list[UploadFile]):
    written_files = []
    for video in videos:
        path = os.path.join("./MESsy/videos", str(p_id))
        path_with_name = os.path.join(path, video.filename)
        if os.path.exists(path) and not os.path.exists(path_with_name):
            written_files.append(video.filename)
            async with aiofiles.open(path_with_name, "wb") as out_file:
                content = await video.read()
                await out_file.write(content)
    return written_files


@app.delete("/uiapi/videos/{p_id}/{name}")
def ui_get_videos(p_id: int, name: str, response: Response):
    path = os.path.join("./MESsy/videos", str(p_id), name)
    try:
        os.remove(path)
    except FileNotFoundError:
        response.status_code = status.HTTP_404_NOT_FOUND
        return Result_Message(message="File not found")
    return Result_Message(message="File deleted")


@app.get("/uiapi/images/{p_id}")
def ui_get_images(p_id: int, response: Response):
    path = os.path.join("./MESsy/images", str(p_id))
    if os.path.exists(path):
        return [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return Result_Message(message="Not found")


@app.post("/uiapi/uploadimages/{p_id}")
async def ui_uploadimages(p_id: int, images: list[UploadFile]):
    written_files = []
    for image in images:
        path = os.path.join("./MESsy/images", str(p_id))
        path_with_name = os.path.join(path, image.filename)
        if os.path.exists(path) and not os.path.exists(path_with_name):
            written_files.append(image.filename)
            async with aiofiles.open(path_with_name, "wb") as out_file:
                content = await image.read()
                await out_file.write(content)
    return written_files


@app.delete("/uiapi/images/{p_id}/{name}")
def ui_get_images(p_id: int, name: str, response: Response):
    path = os.path.join("./MESsy/images", str(p_id), name)
    try:
        os.remove(path)
    except FileNotFoundError:
        response.status_code = status.HTTP_404_NOT_FOUND
        return Result_Message(message="File not found")
    return Result_Message(message="File deleted")


@app.get("/uiapi/create_report")
def ui_get_create_reports(response: Response):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.product_name, u.user_name, pp.serial_number_machine, pp.completion_time, pp.quantity FROM Produced_Products pp
            INNER JOIN Users u ON u.id==pp.id_user
            INNER JOIN Products p ON p.id==pp.id_product;
        """)
        rows = cursor.fetchall()
        if not rows:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Result_Message(message="No new Data")
        with open(f"./MESsy/reports/{int(time())}_report.csv", "w") as fp:
            writer = csv.writer(fp)
            writer.writerow(
                ["product", "username", "serialnumber machine", "completion time", "quantity"])
            writer.writerows(rows)
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Produced_Products;
        """)
    return Result_Message(message="report created")


@app.get("/uiapi/reports")
def ui_get_reports():
    path = "./MESsy/reports"
    return [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)) and (os.path.splitext(f)[1].lower() == ".csv")]


@app.get("/uiapi/products")
def ui_get_products():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, mt.machine_type, p.product_name, p.product_description FROM Products p
            INNER JOIN Machine_Type mt ON mt.id==p.id_machine_type;
        """)
        rows = cursor.fetchall()
    return list(map(lambda x: Product(id=x[0], Machine_Type=x[1], Name=x[2], Description=x[3]), rows))


@app.delete("/uiapi/products/{p_id}")
def ui_delete_products(p_id: int):
    try:
        path = os.path.join("./MESsy/videos", str(p_id))
        shutil.rmtree(path)
    except:
        pass
    try:
        path = os.path.join("./MESsy/images", str(p_id))
        shutil.rmtree(path)
    except:
        pass
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Products WHERE id==?;
        """, (p_id, ))


@app.post("/uiapi/products")
async def ui_post_products(product: UploadFile, response: Response):
    random_filename = os.path.join(
        "./MESsy/temp", str(random.randint(1, 100000)) + ".csv")
    async with aiofiles.open(random_filename, "wb") as out_file:
        content = await product.read()
        await out_file.write(content)
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        with open(random_filename, "r", encoding="iso-8859-1") as csv_file:
            csvreader = csv.reader(csv_file, delimiter=";")
            try:
                product_id = 0
                for index, row in enumerate(csvreader):
                    if index == 1:
                        cursor.execute("""
                            SELECT id from Machine_Type where machine_type==?;
                        """, (row[2], ))
                        rows_db = cursor.fetchall()
                        cursor.execute("""
                            INSERT INTO Products (id_machine_type, product_name, product_description, next_product_name, n_partitions)
                            VALUES (?, ?, ?, ?, ?);
                        """, (rows_db[0][0], row[0], row[1], row[3], int(row[4])))
                        cursor.execute("""
                            SELECT id FROM Products WHERE product_name==?;
                        """, (row[0], ))
                        rows_db = cursor.fetchall()
                        product_id = rows_db[0][0]
                    if index >= 3 and row[0] != "":
                        cursor.execute("""
                            INSERT INTO Product_Steps (id_product, step_number, step_description, specified_time, additional_information)
                            VALUES (?, ?, ?, ?, ?);
                        """, (product_id, row[0], row[1], float(row[2].replace(",", ".")) if row[2] != "" else 0.0, row[3]))
                path = os.path.join("./MESsy/videos", str(product_id))
                if os.path.exists(path):
                    shutil.rmtree(path)
                os.mkdir(path)
                path = os.path.join("./MESsy/images", str(product_id))
                if os.path.exists(path):
                    shutil.rmtree(path)
                os.mkdir(path)
            except sqlite3.IntegrityError:
                response.status_code = status.HTTP_400_BAD_REQUEST
            except IndexError:
                response.status_code = status.HTTP_400_BAD_REQUEST
            except ValueError:
                response.status_code = status.HTTP_400_BAD_REQUEST
    os.remove(random_filename)
    return


app.mount("/reports", StaticFiles(directory="MESsy/reports"), name="reports")
app.mount("/images", StaticFiles(directory="MESsy/images"), name="images")
app.mount("/videos", StaticFiles(directory="MESsy/videos"), name="videos")
app.mount("/ui", StaticFiles(directory="MESsy/UI"), name="UI")
