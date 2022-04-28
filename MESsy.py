from fastapi import FastAPI, status, Response
from fastapi.staticfiles import StaticFiles
import sqlite3
from time import time_ns, asctime, localtime, daylight, tzname
from pydantic import BaseModel
from starlette.responses import FileResponse
from typing import List, Optional


class Help_Object(BaseModel):
    worker: str
    room: str
    time: str
    machine: int


class Room(BaseModel):
    id: int
    room: str


class Worker(BaseModel):
    id: int
    user: str


class Machine_Type(BaseModel):
    id: int
    machine: str


class Login_Info(BaseModel):
    Rooms: List[Room]
    Users: List[Worker]


class Login_Data(BaseModel):
    User: int
    Room: int


class QR_Codes(BaseModel):
    Room: str
    Machine: str
    Product: str
    Step: str


class Job_Infos(BaseModel):
    Materialnumber: int
    Job: int
    Product_Name: str
    Needed_Materials: str
    Description: str
    Needle_Size: int
    Yarn_Count: int
    Specified_Time: float
    URL_Pictures: List[str]
    URL_Videos: List[str]
    Additional_Informations: str
    QR_Codes: QR_Codes


class Error_Message(BaseModel):
    Message: str
    Interrupted: bool


class Result_Success(BaseModel):
    success: bool
    message: Optional[str]


def time_to_str(time):
    return f"{asctime(localtime(time))} {tzname[daylight]}"


def cancel_job(m_id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id_product, quantity FROM Current_Jobs WHERE id_machine == ?;
        """, (m_id, ))
        rows = cursor.fetchall()
        if not rows:
            return
        cursor.execute("""
            INSERT INTO Open_Jobs(id_product, quantity) VALUES(?, ?);
        """, (rows[0][0], rows[0][1]))
        cursor.execute("""
            DELETE FROM Current_Jobs WHERE id_machine == ?;
        """, (m_id, ))


def get_job_from_db(m_id):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, cj.id, p.product_name, ps.needed_materials, ps.step_description, p.needle_size, p.yarn_count, ps.specified_time, ps.url_images, ps.url_videos, r.url_qr_code, m.url_qr_code, p.url_qr_code, ps.url_qr_code, ps.additional_information FROM Current_Jobs cj
            INNER JOIN Machine_login ml ON cj.id_machine==ml.id
            INNER JOIN Products p ON cj.id_product==p.id
            INNER JOIN Product_Steps ps ON cj.current_step==ps.step_number AND p.id==cj.id_product
            INNER JOIN Rooms r ON ml.id_room==r.id
            INNER JOIN Machine m ON ml.id_machine==m.id
            WHERE ml.id_machine == ?;
        """, (m_id, ))
        rows = cursor.fetchall()
    return rows


app = FastAPI(title="MESsy app")


@app.get('/favicon.ico')
def favicon():
    return FileResponse("MESsy/favicon.png")


@app.get("/MESsy/logininfo")
def get_logininfo():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor_worker = conn.cursor()
        cursor_worker.execute("""
            SELECT id, worker_name from Workers;
        """)
        rows_worker = cursor_worker.fetchall()
        cursor_room = conn.cursor()
        cursor_room.execute("""
            SELECT id, room_description from Rooms;
        """)
        rows_room = cursor_room.fetchall()
    Rooms = []
    for i in rows_room:
        Rooms.append(Room(id=i[0], room=i[1]))
    Workers = []
    for i in rows_worker:
        Workers.append(Worker(id=i[0], user=i[1]))
    return Login_Info(Users=Workers, Rooms=Rooms)


@app.post("/MESsy/{m_id}/login", status_code=status.HTTP_201_CREATED)
def post_login(m_id: int, login_data: Login_Data, response: Response):
    success = True
    message = None
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Machine_login(id_room, id_current_worker, id_machine)
                VALUES (?, ?, ?);
            """, (login_data.Room, login_data.User, m_id))
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_409_CONFLICT
        success = False
        message = "Machine or User is already logged in"
    return Result_Success(success=success, message=message)


@app.delete("/MESsy/{m_id}/login")
def delete_login(m_id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Machine_login WHERE id_machine == ?;
        """, (m_id, ))
    return Result_Success(success=True)


@app.get("/MESsy/{m_id}/help")
def get_help(m_id: int):
    help_time = time_ns() // 1_000_000_000
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO help (id_machine_login, call_time) VALUES (?, ?);", (m_id, help_time))
    return {"id": m_id, "time": time_to_str(help_time)}


@app.get("/MESsy/{m_id}/job")
def get_job(m_id: int, response: Response):
    rows = get_job_from_db(m_id)
    if rows:
        qr_codes = QR_Codes(
            Room=rows[0][10], Machine=rows[0][11], Product=rows[0][12], Step=rows[0][13])
        return_value = Job_Infos(Materialnumber=rows[0][0], Job=rows[0][1], Product_Name=rows[0][2], Needed_Materials=rows[0][3], Description=rows[0][4], Needle_Size=rows[0][5],
                                 Yarn_Count=rows[0][6], Specified_Time=rows[0][7], URL_Pictures=rows[0][8].split(","), URL_Videos=rows[0][9].split(","), Additional_Informations=rows[0][14], QR_Codes=qr_codes)
    else:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                PRAGMA foreign_keys = 1;
            """)
            cursor.execute("""
                SELECT o.id, ml.id, p.id, o.quantity FROM Open_Jobs o
                INNER JOIN Machine_login ml ON ml.id_machine==?
                INNER JOIN Machine m ON m.id==ml.id_machine
                INNER JOIN Machine_Type mt ON mt.id==m.id_machine_type
                INNER JOIN Products p ON p.id==o.id_product
                WHERE p.machine_type == mt.machine_type;
            """, (m_id, ))
            rows_possible_jobs = cursor.fetchall()
            if not rows_possible_jobs:
                response.status_code = status.HTTP_404_NOT_FOUND
                return Result_Success(success=False, message="No Job found")
            cursor.execute("""
                INSERT INTO Current_Jobs(id_machine, id_product, current_step, quantity)
                VALUES (?, ?, 1, ?)
            """, (rows_possible_jobs[0][1], rows_possible_jobs[0][2], rows_possible_jobs[0][3]))
            cursor.execute("""
                DELETE FROM Open_Jobs WHERE id==?
            """, (rows_possible_jobs[0][0], ))
        rows = get_job_from_db(m_id)
        qr_codes = QR_Codes(
            Room=rows[0][10], Machine=rows[0][11], Product=rows[0][12], Step=rows[0][13])
        return_value = Job_Infos(Materialnumber=rows[0][0], Job=rows[0][1], Product_Name=rows[0][2], Needed_Materials=rows[0][3], Description=rows[0][4], Needle_Size=rows[0][5],
                                 Yarn_Count=rows[0][6], Specified_Time=rows[0][7], URL_Pictures=rows[0][8].split(","), URL_Videos=rows[0][9].split(","), Additional_Informations=rows[0][14], QR_Codes=qr_codes)
    return return_value


@app.post("/MESsy/{m_id}/job")
def put_job(m_id: int):
    return {"Hallo": m_id}


@app.delete("/MESsy/{m_id}/job")
def delete_job(m_id: int):
    cancel_job(m_id)
    return Result_Success(success=True)


@app.post("/MESsy/{m_id}/error")
def post_error(m_id: int, error: Error_Message):
    print(
        f"Machine {m_id} got an critical error with message: {error.Message}")
    if error.Interrupted:
        cancel_job(m_id)
    return Result_Success(success=True)


@app.get("/uiapi/help")
def ui_get_help():
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Help WHERE call_time <= ?;",
                       ((time_ns() // 1_000_000_000) - 3_600,))
        cursor.execute("""
            SELECT h.call_time, w.worker_name, r.room_description, m.id_machine FROM Help h 
            INNER JOIN Machine_login m ON h.id_machine_login==m.id
            INNER JOIN Workers w ON m.id_current_worker==w.id
            INNER JOIN Rooms r ON m.id_room==r.id;
        """)
        rows = cursor.fetchall()
    rows = map(lambda x: Help_Object(
        time=time_to_str(x[0]), worker=x[1], room=x[2], machine=x[3]), rows)
    return list(rows)


app.mount("/images", StaticFiles(directory="MESsy/images"), name="images")
app.mount("/videos", StaticFiles(directory="MESsy/videos"), name="videos")
app.mount("/ui", StaticFiles(directory="MESsy/UI"), name="UI")
