# Email Configuration - Sample Template
# Copy this file to config.py and fill in your actual values

EMAIL_USER = 'your-email@gmail.com'
EMAIL_PASSWORD = 'your-app-password-here' # Use a Gmail App Password, not your regular password
EMAIL_RECIPIENT = 'where-to-send-notifications@email.com'

# Email Server Settings
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587

# Database Configuration
DATABASE_PATH = 'appointments.db'

# Instructions:
# 1. Copy this file: cp config.sample.py config.py
# 2. Edit config.py with your actual Gmail credentials
# 3. For EMAIL_PASSWORD, use a Gmail App Password (not your regular password)
# 4. Set EMAIL_RECIPIENT to where you want booking notifications sent