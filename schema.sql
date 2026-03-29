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
    standardDrinks NUMERIC(3,1) DEFAULT 0.0,
    BAC NUMERIC(4,3) DEFAULT 0.000,
    timeDrinking NUMERIC(2,1) DEFAULT 0.5
);