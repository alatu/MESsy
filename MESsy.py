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
    Needed_Materials: str
    Description: str
    Specified_Time: float
    Additional_Informations: str


class Job_Infos(BaseModel):
    Materialnumber: int
    Product_Name: str
    Needle_Size: int
    Yarn_Count: int
    Quantity: int
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


class Open_Job(BaseModel):
    id: int | None
    id_product: int
    quantity: int


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
        if (rows[0][3] - produced) < 0:
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
            SELECT ps.id, ps.needed_materials, ps.step_description, ps.specified_time, ps.additional_information, ps.step_number FROM Current_Jobs cj
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
            steps.append(Step_Info(Job=i[0], Needed_Materials=i[1], Description=i[2],
                         Specified_Time=i[3], Additional_Informations=i[4], Step_Number=i[5]))
        return_value = Job_Infos(
            Materialnumber=rows[0][0][0], Product_Name=rows[0][0][1], Needle_Size=rows[0][0][2], Yarn_Count=rows[0][0][3], Steps=steps, Quantity=rows[0][0][4], URL_Pictures=rows[2], URL_Videos=rows[3])
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
            steps.append(Step_Info(Job=i[0], Needed_Materials=i[1], Description=i[2],
                         Specified_Time=i[3], Additional_Informations=i[4], Step_Number=i[5]))
            return_value = Job_Infos(
                Materialnumber=rows[0][0][0], Product_Name=rows[0][0][1], Needle_Size=rows[0][0][2], Yarn_Count=rows[0][0][3], Steps=steps, Quantity=rows[0][0][4], URL_Pictures=rows[2], URL_Videos=rows[3])
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
def ui_post_machine_type(machine_type: Machine_Type):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Machine_Type (machine_type)
            VALUES (?);
        """, (machine_type.machine_type, ))
    return Result_Message(message="Machine Type created")


@app.put("/uiapi/machinetype/{id}")
def ui_put_machine_type(id: int, machine_type: Machine_Type):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Machine_Type SET machine_type==? WHERE id==?;
        """, (machine_type.machine_type, id))
    return Result_Message(message="Machine Type updated")


@app.delete("/uiapi/machinetype/{id}")
def ui_delete_machine_type(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM Machine_Type WHERE id==?;
        """, (id, ))
    return Result_Message(message="Machine Type deleted")


@app.get("/uiapi/machine")
def ui_get_machine_type():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, id_machine_type FROM Machine;
        """)
        rows = cursor.fetchall()
    machines = []
    for i in rows:
        machines.append(Machine(id=i[0], id_machine_type=i[1]))
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
def ui_post_room(room: Room):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Rooms (room_description)
            VALUES (?);
        """, (room.room, ))
    return Result_Message(message="Room created")


@app.put("/uiapi/room/{id}")
def ui_put_room(id: int, room: Room):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Rooms SET room_description==? WHERE id==?;
        """, (room.room, id))
    return Result_Message(message="Room updated")


@app.delete("/uiapi/room/{id}")
def ui_delete_room(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
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
def ui_post_user(user: User):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Users (user_name)
            VALUES (?);
        """, (user.user, ))
    return Result_Message(message="User created")


@app.put("/uiapi/user/{id}")
def ui_put_user(id: int, user: User):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Users SET user_name==? WHERE id==?;
        """, (user.user, id))
    return Result_Message(message="User updated")


@app.delete("/uiapi/user/{id}")
def ui_delete_user(id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM Users WHERE id==?;
        """, (id, ))
    return Result_Message(message="User deleted")


@app.get("/uiapi/open_job")
def ui_get_open_job():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, id_product, quantity FROM Open_Jobs;
        """)
        rows = cursor.fetchall()
    open_jobs = []
    for i in rows:
        open_jobs.append(Open_Job(id=i[0], id_product=i[1], quantity=i[2]))
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


app.mount("/images", StaticFiles(directory="MESsy/images"), name="images")
app.mount("/videos", StaticFiles(directory="MESsy/videos"), name="videos")
app.mount("/ui", StaticFiles(directory="MESsy/UI"), name="UI")
