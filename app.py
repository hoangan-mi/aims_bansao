from flask import Flask, render_template, request, redirect, session
import csv
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "123456"

# =========================
# ROLE
# =========================
def require_role(roles):
    def wrapper(func):
        def decorated(*args, **kwargs):
            if "username" not in session:
                return redirect("/login")

            if session.get("role") not in roles:
                return "❌ Bạn không có quyền truy cập"

            return func(*args, **kwargs)

        decorated.__name__ = func.__name__
        return decorated
    return wrapper


# =========================
# LOAD USERS
# =========================
def load_users():
    users = {}

    if not os.path.exists("users.csv"):
        return users

    with open("users.csv", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            users[row["username"].strip()] = row

    return users


# =========================
# LOAD ASSETS (ATS ĐỘNG)
# =========================
def load_assets():
    assets = {}

    if not os.path.exists("aims.csv"):
        return assets

    # LOAD ALERTS
    alerts_map = {}

    if os.path.exists("alerts.csv"):
        with open("alerts.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                aid = row.get("asset_id")
                t = row.get("type_alert")

                if not aid:
                    continue

                if aid not in alerts_map:
                    alerts_map[aid] = {"damage": 0, "wrong_room": 0}

                if t == "damage":
                    alerts_map[aid]["damage"] += 25
                elif t == "wrong_room":
                    alerts_map[aid]["wrong_room"] += 15

    # LOAD ASSETS
    with open("aims.csv", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            asset_id = row.get("ID_assets", "").strip()
            if not asset_id:
                continue

            # ATS gốc
            try:
                original_ats = int(row.get("ATS", 100))
            except:
                original_ats = 100

            # KHẤU HAO
            try:
                year = int(row.get("Year", 2024))
                years_used = datetime.now().year - year
                depreciation = max(0, years_used * 3)
            except:
                depreciation = 0

            # SỰ CỐ
            damage_loss = 0
            wrong_room_loss = 0

            if asset_id in alerts_map:
                damage_loss = alerts_map[asset_id]["damage"]
                wrong_room_loss = alerts_map[asset_id]["wrong_room"]

            final_ats = max(0, original_ats - depreciation - damage_loss - wrong_room_loss)

            row["ATS_value"] = final_ats

            # HIỂN THỊ CHI TIẾT
            detail = []
            if depreciation > 0:
                detail.append(f"khấu hao: -{depreciation}")
            if damage_loss > 0:
                detail.append(f"hỏng: -{damage_loss}")
            if wrong_room_loss > 0:
                detail.append(f"sai phòng: -{wrong_room_loss}")

            row["ATS_display"] = f"{final_ats} ({', '.join(detail)})" if detail else str(final_ats)

            assets[asset_id] = row

    return assets


# =========================
# SAVE ALERT
# =========================
def save_alert(user, asset_id, expected_room, scanned_room, alert_type, description=""):
    file_exists = os.path.exists("alerts.csv")

    with open("alerts.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "user","asset_id","expected_room",
                "scanned_room","type_alert","description","time"
            ])

        writer.writerow([
            user,
            asset_id,
            expected_room,
            scanned_room,
            alert_type,
            description,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])


# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        users = load_users()
        user = users.get(username)

        if user and user["password"] == password:
            session["username"] = username
            session["role"] = user.get("role")
            return redirect("/")

        return render_template("login.html", error="Sai tài khoản hoặc mật khẩu")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================
# HOME
# =========================
@app.route("/")
@require_role(["admin","manager","user"])
def home():
    return render_template("index.html")


@app.route("/scan")
@require_role(["admin","manager","user"])
def scan_qr():
    return render_template("scan.html")


# =========================
# API (FIX QUÉT QR)
# =========================
@app.route("/api/asset/<asset_id>")
def api_asset(asset_id):

    if "username" not in session:
        return {"status": "error", "message": "not login"}

    assets = load_assets()
    asset = assets.get(asset_id.strip())

    if not asset:
        return {"status": "error", "message": "not found"}

    return {"status": "ok", "data": asset}


# =========================
# LIST
# =========================
@app.route("/assets")
@require_role(["admin","manager"])
def assets():
    assets = load_assets()

    room = request.args.get("room")
    asset_type = request.args.get("type")

    result = {}

    for id, asset in assets.items():
        if room and room.lower() not in asset.get("Room", "").lower():
            continue
        if asset_type and asset_type.lower() not in asset.get("Type_asset", "").lower():
            continue

        result[id] = asset

    return render_template("assets.html", assets=result)


# =========================
# DETAIL + SCAN
# =========================
@app.route("/asset/<asset_id>")
@require_role(["admin","manager","user"])
def asset_detail(asset_id):

    assets = load_assets()
    asset = assets.get(asset_id)

    if not asset:
        return "Không tìm thấy tài sản"

    # Lưu lịch sử scan
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    file_exists = os.path.exists("scan_history.csv")

    with open("scan_history.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["user", "asset_id", "room", "type", "time"])

        writer.writerow([
            session["username"],
            asset_id,
            asset.get("Room"),
            asset.get("Type_asset"),
            now
        ])

    # CHECK SAI PHÒNG
    scanned_room = request.args.get("scan_room")
    real_room = asset.get("Room", "").strip()

    if scanned_room and scanned_room != real_room:
        save_alert(session["username"], asset_id, real_room, scanned_room, "wrong_room")

    return render_template("asset.html", asset=asset)


# =========================
# REPORT HỎNG
# =========================
@app.route("/report/<asset_id>", methods=["GET", "POST"])
@require_role(["admin","manager","user"])
def report(asset_id):

    assets = load_assets()
    asset = assets.get(asset_id)

    if not asset:
        return redirect("/scan")

    if request.method == "POST":
        description = request.form.get("description")

        save_alert(
            session["username"],
            asset_id,
            asset.get("Room"),
            asset.get("Room"),
            "damage",
            description
        )

        return render_template("report_success.html", asset=asset)

    return render_template("report_form.html", asset=asset)


# =========================
# HISTORY
# =========================
@app.route("/history")
@require_role(["admin","manager"])
def history():
    history = []

    if os.path.exists("scan_history.csv"):
        with open("scan_history.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                history.append(row)

    return render_template("history.html", history=history)


# =========================
# ABNORMAL
# =========================
@app.route("/abnormal")
@require_role(["admin"])
def abnormal():

    abnormal_assets = []

    if os.path.exists("alerts.csv"):
        with open("alerts.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                abnormal_assets.append(row)

    return render_template("abnormal.html", abnormal_assets=abnormal_assets)


# =========================
# DELETE ALERT
# =========================
@app.route("/delete_abnormal", methods=["POST"])
@require_role(["admin"])
def delete_abnormal():

    asset_id = request.form.get("asset_id")

    if not os.path.exists("alerts.csv"):
        return redirect("/abnormal")

    rows = []

    with open("alerts.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["asset_id"] != asset_id:
                rows.append(row)

    with open("alerts.csv", "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "user","asset_id","expected_room",
            "scanned_room","type_alert","description","time"
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return redirect("/abnormal")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
