from flask import Flask, request, jsonify, render_template
from datetime import datetime
import sqlite3
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import uuid

app = Flask(__name__, template_folder='template')

# Import configuration
try:
    from config import *
except ImportError:
    print("Error: config.py not found. Please copy config.sample.py to config.py and fill in your settings.")
    exit(1)

def get_db_connection():
    """Get a database connection with row factory for easier data access."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = get_db_connection()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                duration INTEGER NOT NULL,
                lesson_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, time, duration)
            )
        ''')
        conn.commit()
        app.logger.info("Database initialized successfully")
    except Exception as e:
        app.logger.error(f"Error initializing database: {e}")
    finally:
        conn.close()

# Initialize database on startup
init_db()

def get_appointments_for_date(date):
    """Get all appointments for a specific date from database."""
    conn = get_db_connection()
    try:
        appointments = conn.execute(
            'SELECT * FROM appointments WHERE date = ?', (date,)
        ).fetchall()
        return [dict(row) for row in appointments]
    except Exception as e:
        app.logger.error(f"Error getting appointments for date {date}: {e}")
        return []
    finally:
        conn.close()

def save_appointment(appointment_data):
    """Save an appointment to the database with collision checking."""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO appointments (name, email, phone, date, time, duration, lesson_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            appointment_data['name'],
            appointment_data.get('email', ''),
            appointment_data.get('phone', ''),
            appointment_data['date'],
            appointment_data['time'],
            appointment_data['duration'],
            appointment_data['lesson_type']
        ))
        conn.commit()
        return True, "Appointment saved successfully"
    except sqlite3.IntegrityError:
        return False, "This time slot is already booked. Please select a different time."
    except Exception as e:
        app.logger.error(f"Error saving appointment: {e}")
        return False, "Failed to save appointment. Please try again."
    finally:
        conn.close()

def is_slot_available(date, time, duration):
    """Check if a specific time slot is available."""
    conn = get_db_connection()
    try:
        existing = conn.execute(
            'SELECT id FROM appointments WHERE date = ? AND time = ? AND duration = ?',
            (date, time, duration)
        ).fetchone()
        return existing is None
    except Exception as e:
        app.logger.error(f"Error checking slot availability: {e}")
        return False
    finally:
        conn.close()

def create_ics_file(appointment_data):
    """Create a proper .ics calendar invitation file for the appointment."""
    # Parse the date and time
    appointment_date = appointment_data['date']  # YYYY-MM-DD format
    appointment_time = appointment_data['time']  # HH:MM format
    duration = appointment_data['duration']  # minutes

    # Create datetime objects (assume Vienna timezone - Central European Time)
    from datetime import datetime, timedelta, timezone

    # Parse as local Vienna time and convert to UTC for .ics file
    local_datetime = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %H:%M")

    # Vienna is UTC+1 (CET) or UTC+2 (CEST), for simplicity using UTC+1
    # In production, you'd want proper timezone handling
    vienna_offset = timedelta(hours=1)
    start_utc = local_datetime - vienna_offset
    end_utc = start_utc + timedelta(minutes=duration)

    # Format for .ics (UTC format with Z suffix)
    start_str = start_utc.strftime("%Y%m%dT%H%M%SZ")
    end_str = end_utc.strftime("%Y%m%dT%H%M%SZ")
    created_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    # Generate unique ID
    event_uid = str(uuid.uuid4()) + "@piano-lessons.com"

    # Format lesson type for display
    lesson_type_display = appointment_data['lesson_type']
    if lesson_type_display == 'Student Location':
        lesson_type_display = 'At Student\'s Location'
    elif lesson_type_display == 'Teacher Location':
        lesson_type_display = 'At Teacher\'s Location'

    # Escape special characters in description for .ics format
    description = f"Piano lesson with {appointment_data['name']}\\n\\nLesson Type: {lesson_type_display}\\nDuration: {duration} minutes\\n\\nStudent Contact:\\nEmail: {appointment_data.get('email', 'Not provided')}\\nPhone: {appointment_data.get('phone', 'Not provided')}"

    # Clean email for attendee (handle missing email)
    attendee_email = appointment_data.get('email', 'noemail@example.com')
    attendee_name = appointment_data['name']

    # Create .ics content - simplified for better Outlook compatibility
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Piano Lessons//Piano Lesson Booking//EN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{event_uid}
DTSTART:{start_str}
DTEND:{end_str}
DTSTAMP:{created_str}
SUMMARY:Piano Lesson - {appointment_data['name']}
DESCRIPTION:{description}
ORGANIZER:mailto:{EMAIL_USER}
STATUS:CONFIRMED
SEQUENCE:0
BEGIN:VALARM
TRIGGER:-PT15M
ACTION:DISPLAY
DESCRIPTION:Reminder
END:VALARM
END:VEVENT
END:VCALENDAR"""

    return ics_content

def create_booking_email(appointment_data):
    """Create a professional email template for booking notifications."""
    subject = f"New Piano Lesson Booking - {appointment_data['name']} - {appointment_data['date']}"

    # Format lesson type for display
    lesson_type_display = appointment_data['lesson_type']
    if lesson_type_display == 'Student Location':
        lesson_type_display = 'At Student\'s Location'
    elif lesson_type_display == 'Teacher Location':
        lesson_type_display = 'At Teacher\'s Location'

    # Create HTML email content
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #7b3f00;">New Piano Lesson Booking</h2>

        <div style="background-color: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #7b3f00;">Student Information</h3>
            <p><strong>Name:</strong> {appointment_data['name']}</p>
            <p><strong>Email:</strong> {appointment_data.get('email', 'Not provided')}</p>
            <p><strong>Phone:</strong> {appointment_data.get('phone', 'Not provided')}</p>
        </div>

        <div style="background-color: #f0f8ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #7b3f00;">Lesson Details</h3>
            <p><strong>Date:</strong> {appointment_data['date']}</p>
            <p><strong>Time:</strong> {appointment_data['time']}</p>
            <p><strong>Duration:</strong> {appointment_data['duration']} minutes</p>
            <p><strong>Lesson Type:</strong> {lesson_type_display}</p>
        </div>

        <p style="margin-top: 30px; font-size: 14px; color: #666;">
            This booking was submitted through your piano lesson website.
        </p>
    </body>
    </html>
    """

    # Create plain text version
    text_content = f"""
New Piano Lesson Booking

Student Information:
- Name: {appointment_data['name']}
- Email: {appointment_data.get('email', 'Not provided')}
- Phone: {appointment_data.get('phone', 'Not provided')}

Lesson Details:
- Date: {appointment_data['date']}
- Time: {appointment_data['time']}
- Duration: {appointment_data['duration']} minutes
- Lesson Type: {lesson_type_display}

This booking was submitted through your piano lesson website.
    """

    return subject, html_content, text_content

def send_booking_email(appointment_data):
    """Send booking notification email with .ics calendar attachment."""
    try:
        # Create email content
        subject, html_content, text_content = create_booking_email(appointment_data)

        # Create .ics calendar file content
        ics_content = create_ics_file(appointment_data)

        # Create message
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_RECIPIENT

        # Create alternative container for text/HTML
        msg_alternative = MIMEMultipart('alternative')

        # Add both text and HTML parts
        text_part = MIMEText(text_content, 'plain')
        html_part = MIMEText(html_content, 'html')

        msg_alternative.attach(text_part)
        msg_alternative.attach(html_part)

        # Attach the alternative container to main message
        msg.attach(msg_alternative)

        # Create .ics calendar file as simple attachment
        ics_filename = f"piano_lesson_{appointment_data['name'].replace(' ', '_')}_{appointment_data['date']}.ics"

        # Use basic MIMEBase for better compatibility
        ics_attachment = MIMEBase('application', 'octet-stream')
        ics_attachment.set_payload(ics_content.encode('utf-8'))
        encoders.encode_base64(ics_attachment)
        ics_attachment.add_header(
            'Content-Disposition',
            f'attachment; filename="{ics_filename}"'
        )

        # Attach the .ics file
        msg.attach(ics_attachment)

        # Send email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)

        app.logger.info(f"Booking notification email with calendar attachment sent for {appointment_data['name']}")
        return True

    except Exception as e:
        app.logger.error(f"Failed to send booking email: {e}")
        return False

# Database is now used for appointments storage

@app.route('/')
def index():
    # Serve the main website instead of the booking-only template
    with open('index-main.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/image_diane.png')
def serve_image():
    # Serve the profile image
    from flask import send_file
    return send_file('image_diane.png')

#@app.route('/appointments', methods=['GET'])
#def get_appointments():
#    return jsonify(appointments)


# Sample appointments for testing
appointments_sample = [
    {"day": "2025-09-28", "time": "09:00", "duration": 60},
    {"day": "2025-09-28", "time": "11:30", "duration": 30},
    {"day": "2025-09-28", "time": "14:00", "duration": 90}
]

## ----------------------------------------------------------------------
## Helpers
## ----------------------------------------------------------------------
def time_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m
#
def minutes_to_time(m: int) -> str:
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}"
#
def generate_available_slots(date: str, dur: int, session_type: str):
    """
    Return half‑hour start times that do **not** overlap any booked slot.
    If `session_type` == "Student Location" we reserve an extra 30 min
    before **and** after the requested slot (travel/buffer).
    """
    # All possible half hour slots from 08:00 to 19:30
    possible = [minutes_to_time(m) for m in range(8 * 60, 20 * 60, 30)]

    # Booked slots for the requested day from database
    booked = get_appointments_for_date(date)

    # Buffer in minutes – only for Student Location
    buffer = 30 if session_type == "Student Location" else 0

    available = []
    for start in possible:
        start_min = time_to_minutes(start)
        end_min   = start_min + dur

        # Slot must stay inside the 08:00‑20:00 window
        if end_min > 20 * 60:
            continue

        # Apply travel buffer: the *effective* occupied interval becomes
        # [start‑buffer , end+buffer)
        eff_start = start_min - buffer
        eff_end   = end_min + buffer

        # Do not allow negative minutes – treat as 0
        if eff_start < 0:
            eff_start = 0

        # Check overlap with every booked appointment
        overlap = False
        for b in booked:
            b_start = time_to_minutes(b["time"])
            b_end   = b_start + b["duration"]
            if eff_start < b_end and eff_end > b_start:
                overlap = True
                break

        if not overlap:
            available.append(start)

    return available

# ----------------------------------------------------------------------
# Route
# ----------------------------------------------------------------------
@app.route("/appointments", methods=["GET"])
def get_appointments():
    date = request.args.get("date")                     # YYYY‑MM‑DD
    dur  = request.args.get("d", type=int)              # minutes
    typ  = request.args.get("type", default="Online")   # session type

    app.logger.info(f"API called with date={date}, duration={dur}, type={typ}")

    if not date or not dur:
        app.logger.error("Missing required parameters")
        return jsonify({"error": "date and d (duration) are required"}), 400

    slots = generate_available_slots(date, dur, typ)
    app.logger.info(f"Generated {len(slots)} slots: {slots}")

    return jsonify({
        "date": date,
        "duration": dur,
        "type": typ,
        "available": slots
    })


##@app.route('/appointments', methods=['GET'])
##def get_appointments():
##    date = request.args.get('date')  # e.g. "2025-09-11"
##    if date:
##        filtered = [a for a in appointments if a['day'] == date]
##        return jsonify(filtered)
##    return jsonify(appointments)

# XSS base payload from("https://findxss.com/")
#fetch('https://example.com/api/endpoint', { method: 'GET', credentials: 'include', headers:{'Content-Type': 'application/json',}})
# innerHTML # dangerous js function -> if user controls input .. potential xss

@app.route('/submit_appointment', methods=['POST'])
def submit_appointment():
    data        = request.json
    duration    = data.get('duration')
    lesson_type = data.get('lesson_type')
    day         = data.get('date')
    time        = data.get('time')
    email       = data.get('email', '')
    phone       = data.get('phone', '')
    name        = data.get('name', '').strip()
    
    errors = {}
    if duration not in [30, 60]:
        errors['duration'] = 'Invalid duration'
    if not day or not time:
        errors['datetime'] = 'Select a day and time'
    if not email and not phone:
        errors['contact'] = 'Provide at least email or phone'
    if not name:
        errors['name'] = 'Please provide your name'

    if errors:
        return jsonify({'success': False, 'errors': errors}), 400

    # Check if slot is available before saving
    if not is_slot_available(day, time, duration):
        return jsonify({
            'success': False,
            'errors': {'slot': 'This time slot is already booked. Please select a different time.'}
        }), 400

    appointment = {
        'name': name,
        'date': day,  # Changed from 'day' to 'date' to match database schema
        'time': time,
        'duration': duration,
        'lesson_type': lesson_type,
        'email': email,
        'phone': phone
    }

    # Save to database
    success, message = save_appointment(appointment)

    if success:
        app.logger.info(f"Appointment saved: {appointment}")

        # Send email notification
        email_sent = send_booking_email(appointment)
        if email_sent:
            app.logger.info(f"Email notification sent for booking: {appointment['name']}")
        else:
            app.logger.warning(f"Failed to send email notification for booking: {appointment['name']}")

        return jsonify({'success': True, 'appointment': appointment, 'message': message})
    else:
        app.logger.error(f"Failed to save appointment: {message}")
        return jsonify({
            'success': False,
            'errors': {'database': message}
        }), 400
    
if __name__ == "__main__":
    app.run(debug=True)
