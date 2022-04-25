CREATE TABLE Workers(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    worker_name TEXT NOT NULL
);

CREATE TABLE Rooms(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    url_qr_code TEXT NOT NULL,
    room_description TEXT
);

CREATE TABLE Machine(
    id INTEGER NOT NULL PRIMARY KEY,
    url_qr_code TEXT NOT NULL,
    machine_type INTEGER NOT NULL
);

CREATE TABLE Machine_login(
    id INTEGER NOT NULL PRIMARY KEY,
    id_room INTEGER NOT NULL,
    id_current_worker INTEGER NOT NULL,
    id_machine INTEGER NOT NULL,
    FOREIGN KEY(id_room) REFERENCES Rooms(id) ON DELETE CASCADE,
    FOREIGN KEY(id_current_worker) REFERENCES Workers(id) ON DELETE CASCADE,
    FOREIGN KEY(id_machine) REFERENCES Machine(id) ON DELETE CASCADE
);

CREATE TABLE Products(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    machine_type INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    needed_materials TEXT NOT NULL,
    needle_size INTEGER,
    yarn_count INTEGER,
    url_qr_code TEXT NOT NULL
);

CREATE TABLE Product_Steps(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    id_product INTEGER NOT NULL,
    step_number INTEGER NOT NULL,
    product_description TEXT NOT NULL,
    additional_information TEXT,
    url_images TEXT,
    url_videos TEXT,
    url_qr_code TEXT NOT NULL,
    FOREIGN KEY(id_product) REFERENCES Products(id) ON DELETE CASCADE
);

CREATE TABLE Produced_Products(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    id_product INTEGER NOT NULL,
    id_worker INTEGER NOT NULL,
    completion_time INTEGER NOT NULL,
    FOREIGN KEY(id_product) REFERENCES Products(id) ON DELETE CASCADE,
    FOREIGN KEY(id_worker) REFERENCES Workers(id) ON DELETE CASCADE
);

CREATE TABLE Produced_Products_Steps(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    id_produced_product INTEGER NOT NULL,
    completion_time INTEGER NOT NULL,
    FOREIGN KEY(id_produced_product) REFERENCES Produced_Products(id) ON DELETE CASCADE
);

CREATE TABLE Current_Jobs(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    id_machine INTEGER NOT NULL,
    id_product INTEGER NOT NULL,
    id_current_step INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY(id_machine) REFERENCES Machine_login(id) ON DELETE CASCADE,
    FOREIGN KEY(id_product) REFERENCES Products(id) ON DELETE CASCADE,
    FOREIGN KEY(id_current_step) REFERENCES Product_Steps(id) ON DELETE CASCADE
);

CREATE TABLE Open_Jobs(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    id_product INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY(id_product) REFERENCES Products(id) ON DELETE CASCADE
);

CREATE TABLE Help(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    id_machine_login INTEGER NOT NULL,
    call_time INTEGER NOT NULL,
    FOREIGN KEY(id_machine_login) REFERENCES Machine_login(id) ON DELETE CASCADE
);