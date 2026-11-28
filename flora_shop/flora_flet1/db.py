# -*- coding: utf-8 -*-
"""Слой данных (SQLite): пользователи, цветы, заказы, избранное."""
import hashlib
import os
import secrets
import sqlite3
import threading
from datetime import datetime

from flowers_data import FLOWERS

STATUSES = ["Новый", "В работе", "Готов", "Завершён", "Отменён"]
ACTIVE_STATUSES = ("Новый", "В работе", "Готов")
METHODS = ["Самовывоз", "Доставка"]

PROMOS = {"SPRING10": 10, "FLORA15": 15, "HELLO5": 5}  # промокод -> скидка, %
DELIVERY_FEE = 300
FREE_DELIVERY_FROM = 3000

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin123"

_lock = threading.RLock()
_conn = None


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120_000).hex()


def init(path):
    global _conn
    with _lock:
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                salt TEXT NOT NULL,
                pw_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'customer',
                full_name TEXT DEFAULT '',
                phone TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS flowers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, latin TEXT, category TEXT, wiki TEXT,
                price INTEGER NOT NULL, stock INTEGER NOT NULL,
                soil TEXT, feeding TEXT, bloom TEXT, height TEXT, light TEXT,
                watering TEXT, vase TEXT, meaning TEXT, fact TEXT,
                photo_url TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS orders(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created TEXT NOT NULL,
                method TEXT NOT NULL,
                address TEXT DEFAULT '',
                when_dt TEXT NOT NULL,
                phone TEXT DEFAULT '',
                comment TEXT DEFAULT '',
                promo TEXT DEFAULT '',
                subtotal INTEGER, discount INTEGER, delivery INTEGER, total INTEGER,
                status TEXT NOT NULL DEFAULT 'Новый'
            );
            CREATE TABLE IF NOT EXISTS order_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                flower_id INTEGER NOT NULL,
                name TEXT, price INTEGER, qty INTEGER
            );
            CREATE TABLE IF NOT EXISTS favorites(
                user_id INTEGER NOT NULL, flower_id INTEGER NOT NULL,
                PRIMARY KEY(user_id, flower_id)
            );
            """
        )
        _conn.commit()
        _seed()


def _seed():
    if _conn.execute("SELECT COUNT(*) FROM flowers").fetchone()[0] == 0:
        cols = list(FLOWERS[0].keys())
        sql = "INSERT INTO flowers(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols)))
        with _conn:
            _conn.executemany(sql, [tuple(f[c] for c in cols) for f in FLOWERS])
    if _conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 0:
        create_user(ADMIN_LOGIN, ADMIN_PASSWORD, "Администратор", "", role="admin")


# ---------- пользователи ----------
def create_user(username, password, full_name="", phone="", role="customer"):
    username = username.strip()
    if len(username) < 3:
        raise ValueError("Логин — минимум 3 символа")
    if len(password) < 4:
        raise ValueError("Пароль — минимум 4 символа")
    salt = secrets.token_hex(16)
    with _lock:
        if _conn.execute("SELECT 1 FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone():
            raise ValueError("Такой логин уже занят")
        try:
            with _conn:
                _conn.execute(
                    "INSERT INTO users(username,salt,pw_hash,role,full_name,phone) VALUES(?,?,?,?,?,?)",
                    (username, salt, _hash(password, salt), role, full_name.strip(), phone.strip()),
                )
        except sqlite3.IntegrityError:
            raise ValueError("Такой логин уже занят")
    return authenticate(username, password)


def authenticate(username, password):
    with _lock:
        row = _conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username.strip(),)).fetchone()
    if row and secrets.compare_digest(row["pw_hash"], _hash(password, row["salt"])):
        return dict(row)
    return None


def update_profile(user_id, full_name, phone):
    with _lock, _conn:
        _conn.execute("UPDATE users SET full_name=?, phone=? WHERE id=?", (full_name.strip(), phone.strip(), user_id))


# ---------- цветы ----------
def list_flowers(search="", category="Все", sort="name", fav_user=None):
    with _lock:
        rows = [dict(r) for r in _conn.execute("SELECT * FROM flowers").fetchall()]
        favs = set()
        if fav_user is not None:
            favs = fav_ids(fav_user)
    q = search.strip().casefold()
    if q:
        rows = [r for r in rows if q in r["name"].casefold() or q in (r["latin"] or "").casefold()]
    if category and category != "Все":
        rows = [r for r in rows if r["category"] == category]
    if fav_user is not None:
        rows = [r for r in rows if r["id"] in favs]
    if sort == "price_asc":
        rows.sort(key=lambda r: (r["price"], r["name"]))
    elif sort == "price_desc":
        rows.sort(key=lambda r: (-r["price"], r["name"]))
    elif sort == "stock":
        rows.sort(key=lambda r: (r["stock"] <= 0, r["name"]))
    else:
        rows.sort(key=lambda r: r["name"])
    return rows


def get_flower(fid):
    with _lock:
        r = _conn.execute("SELECT * FROM flowers WHERE id=?", (fid,)).fetchone()
    return dict(r) if r else None


def add_flower(data):
    cols = ["name", "latin", "category", "wiki", "price", "stock", "soil", "feeding",
            "bloom", "height", "light", "watering", "vase", "meaning", "fact", "photo_url"]
    row = [data.get(c, "") for c in cols]
    with _lock, _conn:
        _conn.execute("INSERT INTO flowers(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))), row)


def update_flower(fid, price, stock, photo_url):
    with _lock, _conn:
        _conn.execute("UPDATE flowers SET price=?, stock=?, photo_url=? WHERE id=?",
                      (int(price), int(stock), photo_url.strip(), fid))


def set_photo_url(fid, url):
    with _lock, _conn:
        _conn.execute("UPDATE flowers SET photo_url=? WHERE id=?", (url, fid))


# ---------- избранное ----------
def fav_ids(user_id):
    with _lock:
        return {r[0] for r in _conn.execute("SELECT flower_id FROM favorites WHERE user_id=?", (user_id,))}


def toggle_fav(user_id, fid):
    with _lock, _conn:
        if _conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND flower_id=?", (user_id, fid)).fetchone():
            _conn.execute("DELETE FROM favorites WHERE user_id=? AND flower_id=?", (user_id, fid))
            return False
        _conn.execute("INSERT INTO favorites VALUES(?,?)", (user_id, fid))
        return True


# ---------- заказы ----------
def calc_totals(subtotal, method, promo=""):
    percent = PROMOS.get((promo or "").upper(), 0)
    discount = round(subtotal * percent / 100)
    delivery = DELIVERY_FEE if (method == "Доставка" and subtotal - discount < FREE_DELIVERY_FROM) else 0
    return {"subtotal": subtotal, "percent": percent, "discount": discount,
            "delivery": delivery, "total": subtotal - discount + delivery}


def place_order(user_id, cart, method, address, when_dt, phone, comment="", promo=""):
    """cart: {flower_id: qty}. Бросает ValueError, если что-то не так."""
    with _lock:
        if not cart:
            raise ValueError("Корзина пуста")
        lines, subtotal = [], 0
        for fid, qty in cart.items():
            f = get_flower(fid)
            if not f:
                raise ValueError("Один из цветов больше не продаётся")
            if qty > f["stock"]:
                raise ValueError("«%s»: в наличии только %d шт." % (f["name"], f["stock"]))
            lines.append((f, qty))
            subtotal += f["price"] * qty
        promo = promo.upper() if promo.upper() in PROMOS else ""
        t = calc_totals(subtotal, method, promo)
        with _conn:
            cur = _conn.execute(
                "INSERT INTO orders(user_id,created,method,address,when_dt,phone,comment,promo,"
                "subtotal,discount,delivery,total,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (user_id, datetime.now().strftime("%Y-%m-%d %H:%M"), method, address,
                 when_dt.strftime("%Y-%m-%d %H:%M"), phone, comment, promo,
                 t["subtotal"], t["discount"], t["delivery"], t["total"], "Новый"),
            )
            oid = cur.lastrowid
            for f, qty in lines:
                _conn.execute("INSERT INTO order_items(order_id,flower_id,name,price,qty) VALUES(?,?,?,?,?)",
                              (oid, f["id"], f["name"], f["price"], qty))
                _conn.execute("UPDATE flowers SET stock = stock - ? WHERE id=?", (qty, f["id"]))
        return oid


def list_orders(user_id=None, status=None):
    sql = ("SELECT o.*, u.full_name AS customer, u.username AS login FROM orders o "
           "JOIN users u ON u.id=o.user_id")
    cond, args = [], []
    if user_id is not None:
        cond.append("o.user_id=?")
        args.append(user_id)
    if status and status != "Все":
        cond.append("o.status=?")
        args.append(status)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    with _lock:
        orders = [dict(r) for r in _conn.execute(sql, args).fetchall()]
        for o in orders:
            o["items"] = [dict(r) for r in _conn.execute(
                "SELECT * FROM order_items WHERE order_id=?", (o["id"],))]
    return orders


def set_order_status(order_id, new_status):
    with _lock:
        row = _conn.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise ValueError("Заказ не найден")
        if row["status"] in ("Завершён", "Отменён"):
            raise ValueError("Заказ уже закрыт")
        with _conn:
            if new_status == "Отменён":  # вернуть товар на склад
                for it in _conn.execute("SELECT flower_id, qty FROM order_items WHERE order_id=?", (order_id,)):
                    _conn.execute("UPDATE flowers SET stock = stock + ? WHERE id=?", (it["qty"], it["flower_id"]))
            _conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))


def stats():
    with _lock:
        c = _conn
        total_orders = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        active = c.execute("SELECT COUNT(*) FROM orders WHERE status IN ('Новый','В работе','Готов')").fetchone()[0]
        revenue = c.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='Отменён'").fetchone()[0]
        by_status = {s: c.execute("SELECT COUNT(*) FROM orders WHERE status=?", (s,)).fetchone()[0] for s in STATUSES}
        top = [(r[0], r[1]) for r in c.execute(
            "SELECT i.name, SUM(i.qty) q FROM order_items i JOIN orders o ON o.id=i.order_id "
            "WHERE o.status!='Отменён' GROUP BY i.flower_id ORDER BY q DESC LIMIT 5")]
        low = [(r[0], r[1]) for r in c.execute(
            "SELECT name, stock FROM flowers WHERE stock<=5 ORDER BY stock, name")]
        customers = c.execute("SELECT COUNT(*) FROM users WHERE role='customer'").fetchone()[0]
        flowers = c.execute("SELECT COUNT(*) FROM flowers").fetchone()[0]
    done = total_orders - by_status["Отменён"]
    return {"total_orders": total_orders, "active": active, "revenue": revenue,
            "avg": round(revenue / done) if done else 0, "by_status": by_status,
            "top": top, "low": low, "customers": customers, "flowers": flowers}
