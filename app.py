import os
import re
import sqlite3
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify
from flask_wtf import FlaskForm, CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from wtforms import StringField, SelectField, TextAreaField, HiddenField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError
from dotenv import load_dotenv

# ----------------------------
# Config
# ----------------------------
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")
app.config["DATABASE"] = os.getenv("DATABASE_PATH", "inquiries.db")

app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_TO"] = os.getenv("MAIL_TO", "")

csrf = CSRFProtect(app)
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=["120 per hour"])

PHONE_REGEX = re.compile(r"^\+?[1-9][0-9\-\s()]{6,19}$")


# ----------------------------
# Database helpers
# ----------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            service_type TEXT NOT NULL,
            message TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.commit()


# ----------------------------
# Form
# ----------------------------
class InquiryForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    phone_number = StringField("Phone Number", validators=[DataRequired(), Length(min=7, max=20)])
    service_type = SelectField(
        "Service Required",
        choices=[
            ("", "Select a service"),
            ("Web Development", "Web Development"),
            ("Mobile App Development", "Mobile App Development"),
            ("UI/UX Design", "UI/UX Design"),
            ("Automation & AI", "Automation & AI"),
            ("Consultation", "Consultation"),
        ],
        validators=[DataRequired()],
    )
    message = TextAreaField("Message", validators=[Length(max=1000)])
    website = HiddenField("Website")  # honeypot
    submit = SubmitField("Send Inquiry")

    def validate_phone_number(self, field):
        if not PHONE_REGEX.match(field.data.strip()):
            raise ValidationError("Please enter a valid phone number.")


# ----------------------------
# Email
# ----------------------------
def build_email_html(payload: dict) -> str:
    return f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#0f0b1e;color:#eee;padding:24px;">
        <h2 style="color:#c084fc;">New Service Inquiry</h2>
        <p><strong>Submitted:</strong> {payload['timestamp']}</p>
        <p><strong>Full Name:</strong> {payload['full_name']}</p>
        <p><strong>Phone Number:</strong> {payload['phone_number']}</p>
        <p><strong>Service Type:</strong> {payload['service_type']}</p>
        <p><strong>Message:</strong> {payload['message'] or 'N/A'}</p>
        <p><strong>IP Address:</strong> {payload['ip_address'] or 'Unknown'}</p>
      </body>
    </html>
    """


def send_email(payload: dict):
    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"] or not app.config["MAIL_TO"]:
        raise RuntimeError("Missing email credentials or MAIL_TO in environment variables.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New Inquiry - {payload['service_type']}"
    msg["From"] = app.config["MAIL_USERNAME"]
    msg["To"] = app.config["MAIL_TO"]
    msg.attach(MIMEText(build_email_html(payload), "html"))

    with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]) as server:
        server.starttls()
        server.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
        server.sendmail(app.config["MAIL_USERNAME"], app.config["MAIL_TO"], msg.as_string())


# ----------------------------
# Routes
# ----------------------------
@app.before_request
def setup_db():
    init_db()


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET", "POST"])
@limiter.limit("8 per minute")
def index():
    form = InquiryForm()

    if form.validate_on_submit():
        # Honeypot anti-bot
        if form.website.data:
            flash("Submission blocked.", "warning")
            return redirect(url_for("index") + "#contact")

        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        db = get_db()
        db.execute(
            """
            INSERT INTO inquiries (full_name, phone_number, service_type, message, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                form.full_name.data.strip(),
                form.phone_number.data.strip(),
                form.service_type.data,
                form.message.data.strip() if form.message.data else None,
                ip_address,
                created_at,
            ),
        )
        db.commit()

        payload = {
            "full_name": form.full_name.data.strip(),
            "phone_number": form.phone_number.data.strip(),
            "service_type": form.service_type.data,
            "message": form.message.data.strip() if form.message.data else None,
            "ip_address": ip_address,
            "timestamp": created_at,
        }

        try:
            send_email(payload)
            flash("Inquiry sent successfully! We will contact you soon.", "success")
        except Exception:
            flash("Inquiry saved, but email delivery failed. Check SMTP credentials.", "warning")

        return redirect(url_for("index") + "#contact")

    return render_template("index.html", form=form)


if __name__ == "__main__":
    app.run(debug=True)