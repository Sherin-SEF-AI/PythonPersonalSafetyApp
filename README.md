# PythonPersonalSafetyApp
python gui application for personal safety



# Personal Safety Application

## Overview

The Personal Safety Application is a comprehensive tool designed to enhance personal security. It offers features such as emergency SOS, real-time location tracking, mood analysis, scheduled check-ins, and more. The application is built using PyQt5 and integrates various services to provide a robust safety solution.

## Features

- Emergency SOS with 10-second delay and cancellation option
- Voice commands for key functions
- Real-time location tracking and history visualization
- Simple mood analysis
- Scheduled check-ins
- Safe locations management
- Emergency contacts management
- Text-to-speech and speech-to-text capabilities
- Panic phrase and safe phrase detection
- SMS notifications via Twilio integration
- Interactive map view for current location and location history
- User profile management with medical information
- Nearby safe places suggestions
- Emergency services calling (112)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/Sherin-SEF-AI/PythonPersonalSafetyApp.git
   cd personal-safety-app
   ```

2. Install the required dependencies:
   ```
  
   ```

3. Set up your Twilio credentials:
   - Create a `.env` file in the project root
   - Add your Twilio credentials:
     ```
     TWILIO_ACCOUNT_SID=your_account_sid
     TWILIO_AUTH_TOKEN=your_auth_token
     TWILIO_PHONE_NUMBER=your_twilio_phone_number
     ```

4. Ensure you have a `safety_app_icon.png` file in the project directory for the application icon.

## Usage

Run the application:
```
python personal_safety_app.py
```

- Use the GUI to navigate through different features.
- The SOS button has a 10-second delay. Press "Cancel SOS" to stop the SOS from being sent.
- Use voice commands by clicking the "Voice Command" button and speaking your instruction.
- Keep your profile and emergency contacts up to date for the best experience.

## Note

This application is designed for personal safety, but it should not be relied upon as the sole means of emergency response. Always ensure you have access to traditional emergency services and follow local safety guidelines.


Dependencies

PyQt5==5.15.6
PyQtWebEngine==5.15.5
geocoder==1.38.1
twilio==7.0.0
folium==0.12.1
schedule==1.1.0
requests==2.26.0
pyaudio==0.2.11
SpeechRecognition==3.8.1
pyttsx3==2.90
phonenumbers==8.12.33
python-dotenv==0.19.1
