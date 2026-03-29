CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    nickname TEXT,
    sex TEXT,
    weight NUMERIC(3,0),
    age NUMERIC(2,0),
    favoriteDrink TEXT,
    likes TEXT,
    dislikes TEXT,
    avoid TEXT,
    alcGramsConsumed INTEGER DEFAULT 0,
    BAC NUMERIC(4,3) DEFAULT 0.000,
    sessionStart DATETIME
);