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
    Machine_Types: List[Machine_Type]


class Login_Data(BaseModel):
    User: int
    Machine_Type: int
    Room: int


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
        cursor.execute("""
            INSERT INTO Open_Jobs(id_product, quantity) VALUES(?, ?);
        """, (rows[0][0], rows[0][1]))
        cursor.execute("""
            DELETE FROM Current_Jobs WHERE id_machine == ?;
        """, (m_id, ))


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
        cursor_machine = conn.cursor()
        cursor_machine.execute("""
            SELECT id, machine_type from Machine m;
        """)
        rows_machine = cursor_machine.fetchall()
    Rooms = []
    for i in rows_room:
        Rooms.append(Room(id=i[0], room=i[1]))
    Workers = []
    for i in rows_worker:
        Workers.append(Worker(id=i[0], user=i[1]))
    Machine_Types = []
    for i in rows_machine:
        Machine_Types.append(Machine_Type(id=i[0], machine=i[1]))
    return Login_Info(Users=Workers, Rooms=Rooms, Machine_Types=Machine_Types)


@app.post("/MESsy/{m_id}/login", status_code=status.HTTP_201_CREATED)
def post_login(m_id: int, login_data: Login_Data, response: Response):
    success = True
    message = None
    try:
        with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Machine_login(id, id_room, id_current_worker, id_machine)
                VALUES (?, ?, ?, ?);
            """, (m_id, login_data.Room, login_data.User, login_data.Machine_Type))
    except sqlite3.IntegrityError:
        response.status_code = status.HTTP_409_CONFLICT
        success = False
        message = "Machine is already logged in"
    return Result_Success(success=success, message=message)


@app.delete("/MESsy/{m_id}/login")
def delete_login(m_id: int):
    with sqlite3.connect("./MESsy/DB/DB.sqlite3") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            PRAGMA foreign_keys = 1;
        """)
        cursor.execute("""
            DELETE FROM Machine_login WHERE id == ?;
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
def get_job(m_id: int):
    return {"Hallo": m_id}


@app.put("/MESsy/{m_id}/job")
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
            SELECT h.call_time, w.worker_name, r.room_description, h.id FROM
            (SELECT h.call_time, m.id_current_worker, m.id_room, m.id FROM Help h 
                INNER JOIN Machine_login m ON h.id_machine_login==m.id) h
            INNER JOIN Workers w ON h.id_current_worker==w.id
            INNER JOIN Rooms r ON h.id_room==r.id;
        """)
        rows = cursor.fetchall()
    rows = map(lambda x: Help_Object(
        time=time_to_str(x[0]), worker=x[1], room=x[2], machine=x[3]), rows)
    return list(rows)


app.mount("/images", StaticFiles(directory="MESsy/images"), name="images")
app.mount("/ui", StaticFiles(directory="MESsy/UI"), name="UI")
