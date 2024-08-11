import sys
import json
import os
import time
from datetime import datetime, timedelta
import pyaudio
import wave
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QLineEdit, QLabel, QVBoxLayout, QHBoxLayout,
                             QWidget, QMessageBox, QProgressBar, QListWidget, QTabWidget, QComboBox, QTextEdit,
                             QInputDialog, QDialog, QStyleFactory, QListWidgetItem)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QIcon, QFont, QDesktopServices
from PyQt5.QtWebEngineWidgets import QWebEngineView
import geocoder
from twilio.rest import Client
import folium
import schedule
import requests
import speech_recognition as sr
import pyttsx3
import phonenumbers
import webbrowser
import psutil  # For battery monitoring

class LocationTracker(QThread):
    location_update = pyqtSignal(list)

    def run(self):
        while True:
            location = geocoder.ip('me').latlng
            self.location_update.emit(location)
            time.sleep(300)  # Update every 5 minutes

class VoiceRecorder(QThread):
    finished = pyqtSignal(str)

    def __init__(self, duration=10):
        super().__init__()
        self.duration = duration
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.frames = []

    def run(self):
        self.stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        for _ in range(0, int(44100 / 1024 * self.duration)):
            data = self.stream.read(1024)
            self.frames.append(data)
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()

        wf = wave.open("emergency_audio.wav", 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(44100)
        wf.writeframes(b''.join(self.frames))
        wf.close()

        # Perform speech recognition
        r = sr.Recognizer()
        with sr.AudioFile("emergency_audio.wav") as source:
            audio = r.record(source)
        try:
            text = r.recognize_google(audio)
            self.finished.emit(text)
        except sr.UnknownValueError:
            self.finished.emit("Speech not recognized")
        except sr.RequestError:
            self.finished.emit("Could not request results from speech recognition service")

class PersonalSafetyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Personal Safety App")
        self.setGeometry(100, 100, 1000, 700)
        
        self.user_id = "user123"  # This should be set after user authentication
        self.load_user_data()
        self.setup_twilio()
        self.setup_voice_recognition()
        self.initUI()
        
        self.location_tracker = LocationTracker()
        self.location_tracker.location_update.connect(self.update_location_silently)
        self.location_tracker.start()
        
        self.schedule_thread = threading.Thread(target=self.run_schedule, daemon=True)
        self.schedule_thread.start()

        self.sos_timer = QTimer(self)
        self.sos_timer.timeout.connect(self.send_sos)
        self.sos_active = False

        # Start monitoring battery
        self.battery_monitor = QTimer(self)
        self.battery_monitor.timeout.connect(self.monitor_battery)
        self.battery_monitor.start(60000)  # Check every 60 seconds

    def load_user_data(self):
        try:
            with open('user_data.json', 'r') as f:
                self.user_data = json.load(f)
        except FileNotFoundError:
            self.user_data = {}

        # Ensure all necessary keys are present
        self.user_data.setdefault("name", "John Doe")
        self.user_data.setdefault("phone", "+1234567890")
        self.user_data.setdefault("emergency_contacts", [])
        self.user_data.setdefault("medical_info", "")
        self.user_data.setdefault("safe_locations", [])
        self.user_data.setdefault("scheduled_checks", [])
        self.user_data.setdefault("panic_phrase", "Help me")
        self.user_data.setdefault("safe_phrase", "I'm safe")
        self.user_data.setdefault("location_history", [])
        self.user_data.setdefault("keywords", ["help", "emergency", "danger", "hurt", "scared"])

        self.save_user_data()

    def save_user_data(self):
        with open('user_data.json', 'w') as f:
            json.dump(self.user_data, f)

    def setup_twilio(self):
        account_sid = os.getenv('TWILIO_ACCOUNT_SID', 'insert SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN', 'YOUR TOKEN')
        self.twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER', 'TWILIO PHONE NUMBER')
        
        self.twilio_client = Client(account_sid, auth_token)

    def setup_voice_recognition(self):
        self.recognizer = sr.Recognizer()
        self.engine = pyttsx3.init()

    def initUI(self):
        self.setStyle(QStyleFactory.create('Fusion'))
        main_widget = QWidget(self)
        main_layout = QVBoxLayout(main_widget)

        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)

        # Home tab
        home_tab = QWidget()
        home_layout = QVBoxLayout(home_tab)
        
        # Emergency Contact Call Button
        self.call_emergency_contact_button = QPushButton("Call Emergency Contact")
        self.call_emergency_contact_button.setStyleSheet("background-color: #0074D9; color: white; font-size: 16px; padding: 15px; border-radius: 10px;")
        self.call_emergency_contact_button.clicked.connect(self.call_emergency_contact)
        home_layout.addWidget(self.call_emergency_contact_button)

        # Panic Button with Immediate SOS Activation
        self.panic_button = QPushButton("PANIC (Immediate SOS)")
        self.panic_button.setStyleSheet("background-color: #FF0000; color: white; font-size: 18px; padding: 15px; border-radius: 10px;")
        self.panic_button.clicked.connect(self.send_sos_immediately)
        home_layout.addWidget(self.panic_button)

        self.sos_button = QPushButton("Activate SOS (10s delay)")
        self.sos_button.setStyleSheet("background-color: #FF4136; color: white; font-size: 18px; padding: 15px; border-radius: 10px;")
        self.sos_button.clicked.connect(self.activate_sos)
        home_layout.addWidget(self.sos_button)

        self.cancel_sos_button = QPushButton("Cancel SOS")
        self.cancel_sos_button.setStyleSheet("background-color: #FF851B; color: white; font-size: 16px; padding: 10px; border-radius: 5px;")
        self.cancel_sos_button.clicked.connect(self.cancel_sos)
        self.cancel_sos_button.hide()
        home_layout.addWidget(self.cancel_sos_button)

        self.sos_progress = QProgressBar(self)
        self.sos_progress.setRange(0, 10)
        self.sos_progress.setValue(0)
        self.sos_progress.hide()
        home_layout.addWidget(self.sos_progress)

        self.call_112_button = QPushButton("Call 112")
        self.call_112_button.setStyleSheet("background-color: #FF851B; color: white; font-size: 16px; padding: 10px; border-radius: 5px;")
        self.call_112_button.clicked.connect(self.call_emergency_services)
        home_layout.addWidget(self.call_112_button)

        buttons_layout = QHBoxLayout()
        
        self.location_button = QPushButton("Update Location")
        self.location_button.setStyleSheet("background-color: #0074D9; color: white; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.location_button.clicked.connect(self.update_location)
        buttons_layout.addWidget(self.location_button)

        self.alerts_button = QPushButton("Safety Alerts")
        self.alerts_button.setStyleSheet("background-color: #2ECC40; color: white; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.alerts_button.clicked.connect(self.show_safety_alerts)
        buttons_layout.addWidget(self.alerts_button)

        self.safe_check_in_button = QPushButton("Safe Check-In")
        self.safe_check_in_button.setStyleSheet("background-color: #3D9970; color: white; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.safe_check_in_button.clicked.connect(self.safe_check_in)
        buttons_layout.addWidget(self.safe_check_in_button)

        home_layout.addLayout(buttons_layout)

        self.schedule_check_button = QPushButton("Schedule Check-In")
        self.schedule_check_button.setStyleSheet("background-color: #B10DC9; color: white; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.schedule_check_button.clicked.connect(self.schedule_check_in)
        home_layout.addWidget(self.schedule_check_button)

        self.view_map_button = QPushButton("View Location History")
        self.view_map_button.setStyleSheet("background-color: #7FDBFF; color: white; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.view_map_button.clicked.connect(self.view_location_history)
        home_layout.addWidget(self.view_map_button)

        self.nearby_safe_places_button = QPushButton("Find Nearby Safe Places")
        self.nearby_safe_places_button.setStyleSheet("background-color: #01FF70; color: black; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.nearby_safe_places_button.clicked.connect(self.find_nearby_safe_places)
        home_layout.addWidget(self.nearby_safe_places_button)

        self.voice_command_button = QPushButton("Voice Command")
        self.voice_command_button.setStyleSheet("background-color: #39CCCC; color: white; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.voice_command_button.clicked.connect(self.voice_command)
        home_layout.addWidget(self.voice_command_button)

        self.mood_input = QLineEdit()
        self.mood_input.setPlaceholderText("How are you feeling? (Simple mood analysis)")
        self.mood_input.setStyleSheet("font-size: 14px; padding: 10px; border-radius: 5px; border: 1px solid #ddd;")
        home_layout.addWidget(self.mood_input)

        self.analyze_mood_button = QPushButton("Analyze Mood")
        self.analyze_mood_button.setStyleSheet("background-color: #FFDC00; color: black; font-size: 14px; padding: 10px; border-radius: 5px;")
        self.analyze_mood_button.clicked.connect(self.analyze_mood)
        home_layout.addWidget(self.analyze_mood_button)

        tab_widget.addTab(home_tab, "Home")

        # Contacts tab
        contacts_tab = QWidget()
        contacts_layout = QVBoxLayout(contacts_tab)

        self.contacts_list = QListWidget()
        self.contacts_list.setStyleSheet("font-size: 14px;")
        self.update_contacts_list()
        contacts_layout.addWidget(self.contacts_list)

        contact_input_layout = QHBoxLayout()
        self.contact_input = QLineEdit()
        self.contact_input.setPlaceholderText("Enter contact number (E.164 format)")
        self.contact_input.setStyleSheet("font-size: 14px; padding: 5px; border-radius: 5px; border: 1px solid #ddd;")
        contact_input_layout.addWidget(self.contact_input)

        self.add_contact_button = QPushButton("Add Contact")
        self.add_contact_button.setStyleSheet("background-color: #39CCCC; color: white; font-size: 14px; padding: 5px; border-radius: 5px;")
        self.add_contact_button.clicked.connect(self.add_emergency_contact)
        contact_input_layout.addWidget(self.add_contact_button)

        contacts_layout.addLayout(contact_input_layout)

        tab_widget.addTab(contacts_tab, "Contacts")

        # Profile tab
        profile_tab = QWidget()
        profile_layout = QVBoxLayout(profile_tab)

        self.name_input = QLineEdit(self.user_data["name"])
        self.name_input.setStyleSheet("font-size: 14px; padding: 5px; border-radius: 5px; border: 1px solid #ddd;")
        profile_layout.addWidget(QLabel("Name:"))
        profile_layout.addWidget(self.name_input)

        self.phone_input = QLineEdit(self.user_data["phone"])
        self.phone_input.setStyleSheet("font-size: 14px; padding: 5px; border-radius: 5px; border: 1px solid #ddd;")
        profile_layout.addWidget(QLabel("Phone:"))
        profile_layout.addWidget(self.phone_input)

        self.medical_info_input = QTextEdit(self.user_data["medical_info"])
        self.medical_info_input.setStyleSheet("font-size: 14px; padding: 5px; border-radius: 5px; border: 1px solid #ddd;")
        profile_layout.addWidget(QLabel("Medical Information:"))
        profile_layout.addWidget(self.medical_info_input)

        self.panic_phrase_input = QLineEdit(self.user_data["panic_phrase"])
        self.panic_phrase_input.setStyleSheet("font-size: 14px; padding: 5px; border-radius: 5px; border: 1px solid #ddd;")
        profile_layout.addWidget(QLabel("Panic Phrase:"))
        profile_layout.addWidget(self.panic_phrase_input)

        self.safe_phrase_input = QLineEdit(self.user_data["safe_phrase"])
        self.safe_phrase_input.setStyleSheet("font-size: 14px; padding: 5px; border-radius: 5px; border: 1px solid #ddd;")
        profile_layout.addWidget(QLabel("Safe Phrase:"))
        profile_layout.addWidget(self.safe_phrase_input)

        save_profile_button = QPushButton("Save Profile")
        save_profile_button.setStyleSheet("background-color: #01FF70; color: black; font-size: 14px; padding: 10px; border-radius: 5px;")
        save_profile_button.clicked.connect(self.save_profile)
        profile_layout.addWidget(save_profile_button)

        tab_widget.addTab(profile_tab, "Profile")

        # Safe Locations tab
        safe_locations_tab = QWidget()
        safe_locations_layout = QVBoxLayout(safe_locations_tab)

        self.safe_locations_list = QListWidget()
        self.safe_locations_list.setStyleSheet("font-size: 14px;")
        self.update_safe_locations_list()
        safe_locations_layout.addWidget(self.safe_locations_list)

        safe_location_input_layout = QHBoxLayout()
        self.safe_location_input = QLineEdit()
        self.safe_location_input.setPlaceholderText("Enter safe location name")
        self.safe_location_input.setStyleSheet("font-size: 14px; padding: 5px; border-radius: 5px; border: 1px solid #ddd;")
        safe_location_input_layout.addWidget(self.safe_location_input)

        self.add_safe_location_button = QPushButton("Add Safe Location")
        self.add_safe_location_button.setStyleSheet("background-color: #F012BE; color: white; font-size: 14px; padding: 5px; border-radius: 5px;")
        self.add_safe_location_button.clicked.connect(self.add_safe_location)
        safe_location_input_layout.addWidget(self.add_safe_location_button)

        safe_locations_layout.addLayout(safe_location_input_layout)

        tab_widget.addTab(safe_locations_tab, "Safe Locations")

        # Map View tab
        map_tab = QWidget()
        map_layout = QVBoxLayout(map_tab)
        self.map_view = QWebEngineView()
        map_layout.addWidget(self.map_view)
        tab_widget.addTab(map_tab, "Map View")

        # Safety Tips and Emergency Procedures tab
        tips_tab = QWidget()
        tips_layout = QVBoxLayout(tips_tab)
        self.tips_text = QTextEdit()
        self.tips_text.setReadOnly(True)
        self.tips_text.setStyleSheet("font-size: 14px; padding: 10px; border-radius: 5px;")
        self.tips_text.setText("""
        <h2>Safety Tips and Emergency Procedures</h2>
        <ul>
            <li><strong>Stay Calm:</strong> In an emergency, try to remain as calm as possible.</li>
            <li><strong>Call Emergency Services:</strong> Dial the emergency number in your region (e.g., 112, 911) as soon as possible.</li>
            <li><strong>Know Your Exits:</strong> Always be aware of the nearest exits in any building you enter.</li>
            <li><strong>First Aid:</strong> Learn basic first aid procedures for common injuries.</li>
            <li><strong>Stay Informed:</strong> Keep up to date with safety alerts and warnings in your area.</li>
            <li><strong>Personal Safety:</strong> Avoid walking alone at night in unfamiliar or unsafe areas.</li>
        </ul>
        """)
        tips_layout.addWidget(self.tips_text)
        tab_widget.addTab(tips_tab, "Safety Tips")

        self.setCentralWidget(main_widget)

    # Emergency Contact Call Button Feature
    def call_emergency_contact(self):
        if not self.user_data["emergency_contacts"]:
            QMessageBox.warning(self, "No Contacts", "No emergency contacts available.")
            return

        contact = self.user_data["emergency_contacts"][0]  # Call the first contact
        QMessageBox.information(self, "Call Emergency Contact", f"Please call your emergency contact: {contact}")
        # Optional: You could try to open a browser or dialer application if supported
        # webbrowser.open(f"tel:{contact}")

    # Panic Button with Immediate SOS Activation Feature
    def send_sos_immediately(self):
        self.send_sos(immediate=True)

    # SOS Activation with Delay
    def activate_sos(self):
        if not self.sos_active:
            self.sos_active = True
            self.sos_button.setEnabled(False)
            self.cancel_sos_button.show()
            self.sos_progress.show()
            self.sos_timer.start(1000)  # Start the timer, triggering every 1 second
            self.countdown = 10
            self.update_sos_progress()

    def cancel_sos(self):
        self.sos_active = False
        self.sos_timer.stop()
        self.sos_button.setEnabled(True)
        self.cancel_sos_button.hide()
        self.sos_progress.hide()
        self.sos_progress.setValue(0)
        QMessageBox.information(self, "SOS Cancelled", "The SOS alert has been cancelled.")

    def update_sos_progress(self):
        self.countdown -= 1
        self.sos_progress.setValue(10 - self.countdown)
        if self.countdown > 0:
            QTimer.singleShot(1000, self.update_sos_progress)
        else:
            self.send_sos()

    # Send SOS Message (with or without delay)
    def send_sos(self, immediate=False):
        if self.sos_active or immediate:
            location = self.get_location()
            sos_message = f"SOS Alert: Emergency\nUser: {self.user_data['name']}\nPhone: {self.user_data['phone']}\nLocation: {location}\nMedical Info: {self.user_data['medical_info']}"
            
            self.start_voice_recording()
            success = self.send_sms_to_contacts(sos_message)
            
            if success:
                QMessageBox.critical(self, "SOS Sent", "Your SOS has been sent to your emergency contacts.")
            else:
                QMessageBox.warning(self, "SOS Send Failed", "Failed to send SOS to some or all contacts. Please try again or contact emergency services directly.")

            if not immediate:
                self.sos_active = False
                self.sos_button.setEnabled(True)
                self.cancel_sos_button.hide()
                self.sos_progress.hide()
                self.sos_progress.setValue(0)

            # Start real-time location sharing
            self.start_location_sharing()

    def start_voice_recording(self):
        self.voice_recorder = VoiceRecorder()
        self.voice_recorder.finished.connect(self.process_voice_recording)
        self.voice_recorder.start()

    def process_voice_recording(self, text):
        spotted_keywords = [word for word in self.user_data["keywords"] if word in text.lower()]
        if spotted_keywords:
            keyword_message = f"Spotted keywords: {', '.join(spotted_keywords)}\nContext: {text}"
            self.send_sms_to_contacts(keyword_message)

    def send_sms_to_contacts(self, message):
        success = True
        for contact in self.user_data["emergency_contacts"]:
            try:
                self.twilio_client.messages.create(
                    body=message,
                    from_=self.twilio_phone_number,
                    to=contact
                )
            except Exception as e:
                print(f"Failed to send SMS to {contact}: {str(e)}")
                success = False
        return success

    def get_location(self):
        g = geocoder.ip('me')
        return g.latlng

    def update_location(self):
        location = self.get_location()
        if location:
            self.user_data["location_history"].append({"timestamp": time.time(), "location": location})
            self.save_user_data()
            self.update_map_view()
            QMessageBox.information(self, "Location Updated", f"Your location has been updated: {location}")
        else:
            QMessageBox.critical(self, "Location Error", "Unable to retrieve location")

    def update_location_silently(self, location):
        if location:
            self.user_data["location_history"].append({"timestamp": time.time(), "location": location})
            self.save_user_data()
            self.update_map_view()

    def update_map_view(self):
        if self.user_data["location_history"]:
            latest_location = self.user_data["location_history"][-1]["location"]
            m = folium.Map(location=latest_location, zoom_start=13)
            folium.Marker(latest_location, popup="Current Location").add_to(m)
            
            # Save the map as HTML
            m.save("current_location.html")
            
            # Load the HTML file into the QWebEngineView
            self.map_view.setUrl(QUrl.fromLocalFile(os.path.abspath("current_location.html")))

    def show_safety_alerts(self):
        # In a real application, you would fetch alerts from an API or local database
        QMessageBox.information(self, "Safety Alerts", "No current safety alerts in your area")

    def add_emergency_contact(self):
        contact = self.contact_input.text()
        if contact:
            try:
                parsed_number = phonenumbers.parse(contact, None)
                if phonenumbers.is_valid_number(parsed_number):
                    formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
                    self.user_data["emergency_contacts"].append(formatted_number)
                    self.update_contacts_list()
                    self.save_user_data()
                    QMessageBox.information(self, "Contact Added", f"Emergency contact '{formatted_number}' added successfully!")
                    self.contact_input.clear()
                else:
                    raise ValueError("Invalid phone number")
            except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
                QMessageBox.warning(self, "Input Error", "Please enter a valid phone number")
        else:
            QMessageBox.warning(self, "Input Error", "Please enter a contact number")

    def update_contacts_list(self):
        self.contacts_list.clear()
        for contact in self.user_data["emergency_contacts"]:
            self.contacts_list.addItem(contact)

    def save_profile(self):
        new_name = self.name_input.text()
        new_phone = self.phone_input.text()
        new_medical_info = self.medical_info_input.toPlainText()
        new_panic_phrase = self.panic_phrase_input.text()
        new_safe_phrase = self.safe_phrase_input.text()
        
        self.user_data["name"] = new_name
        self.user_data["phone"] = new_phone
        self.user_data["medical_info"] = new_medical_info
        self.user_data["panic_phrase"] = new_panic_phrase
        self.user_data["safe_phrase"] = new_safe_phrase
        self.save_user_data()
        
        QMessageBox.information(self, "Profile Updated", "Your profile has been updated successfully!")

    def safe_check_in(self):
        location = self.get_location()
        message = f"Safe Check-In: {self.user_data['name']} has checked in safely at location: {location}"
        success = self.send_sms_to_contacts(message)
        
        if success:
            QMessageBox.information(self, "Safe Check-In", "Your safe check-in has been sent to your emergency contacts.")
        else:
            QMessageBox.warning(self, "Check-In Failed", "Failed to send check-in to some or all contacts. Please try again.")

    def add_safe_location(self):
        location_name = self.safe_location_input.text()
        if location_name:
            self.user_data["safe_locations"].append(location_name)
            self.update_safe_locations_list()
            self.save_user_data()
            QMessageBox.information(self, "Safe Location Added", f"Safe location '{location_name}' added successfully!")
            self.safe_location_input.clear()
        else:
            QMessageBox.warning(self, "Input Error", "Please enter a location name")

    def update_safe_locations_list(self):
        self.safe_locations_list.clear()
        for location in self.user_data["safe_locations"]:
            self.safe_locations_list.addItem(location)

    def schedule_check_in(self):
        time, ok = QInputDialog.getText(self, "Schedule Check-In", "Enter check-in time (YYYY-MM-DD HH:MM):")
        if ok:
            try:
                check_time = datetime.strptime(time, "%Y-%m-%d %H:%M")
                self.user_data["scheduled_checks"].append(check_time.strftime("%Y-%m-%d %H:%M"))
                self.save_user_data()
                self.update_schedule()
                QMessageBox.information(self, "Check-In Scheduled", f"Check-in scheduled for {time}")
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter the time in the correct format.")

    def update_schedule(self):
        schedule.clear()
        for check_time in self.user_data["scheduled_checks"]:
            dt = datetime.strptime(check_time, "%Y-%m-%d %H:%M")
            if dt > datetime.now():
                schedule.every().day.at(dt.strftime("%H:%M")).do(self.scheduled_check_in, check_time).tag(check_time)

    def scheduled_check_in(self, check_time):
        location = self.get_location()
        message = f"Scheduled Check-In: {self.user_data['name']} was scheduled to check in at {check_time}. Current location: {location}"
        self.send_sms_to_contacts(message)
        
        # Remove the completed check-in from the schedule
        self.user_data["scheduled_checks"].remove(check_time)
        self.save_user_data()
        self.update_schedule()

    def run_schedule(self):
        self.update_schedule()
        while True:
            schedule.run_pending()
            time.sleep(1)

    def analyze_mood(self):
        text = self.mood_input.text()
        if text:
            # Simple sentiment analysis based on keywords
            positive_words = ['happy', 'good', 'great', 'excellent', 'wonderful', 'amazing', 'fantastic']
            negative_words = ['sad', 'bad', 'terrible', 'awful', 'horrible', 'depressed', 'angry']
            
            words = text.lower().split()
            positive_count = sum(word in positive_words for word in words)
            negative_count = sum(word in negative_words for word in words)
            
            if positive_count > negative_count:
                mood = "positive"
            elif negative_count > positive_count:
                mood = "negative"
            else:
                mood = "neutral"
            
            QMessageBox.information(self, "Mood Analysis", f"Your mood seems to be {mood}.")
        else:
            QMessageBox.warning(self, "Input Error", "Please enter some text to analyze your mood.")

    def view_location_history(self):
        if not self.user_data["location_history"]:
            QMessageBox.information(self, "No Data", "No location history available.")
            return

        m = folium.Map(location=self.user_data["location_history"][-1]["location"], zoom_start=10)
        
        for entry in self.user_data["location_history"]:
            folium.Marker(
                entry["location"],
                popup=datetime.fromtimestamp(entry["timestamp"]).strftime('%Y-%m-%d %H:%M:%S')
            ).add_to(m)

        # Save the map as HTML
        m.save("location_history.html")
        
        # Open the HTML file in the default web browser
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath("location_history.html")))

    def keyPressEvent(self, event):
        text = event.text().lower()
        if text == self.user_data["panic_phrase"].lower():
            self.send_panic_alert()
        elif text == self.user_data["safe_phrase"].lower():
            self.confirm_safety()
        super().keyPressEvent(event)

    def send_panic_alert(self):
        location = self.get_location()
        message = f"PANIC ALERT: {self.user_data['name']} has triggered their panic phrase. Current location: {location}"
        self.send_sms_to_contacts(message)
        self.start_voice_recording()
        QMessageBox.critical(self, "Panic Alert Sent", "Your panic alert has been sent to your emergency contacts.")

    def confirm_safety(self):
        location = self.get_location()
        message = f"Safety Confirmation: {self.user_data['name']} has confirmed their safety. Current location: {location}"
        self.send_sms_to_contacts(message)
        QMessageBox.information(self, "Safety Confirmed", "Your safety confirmation has been sent to your emergency contacts.")

    def text_to_speech(self, text):
        self.engine.say(text)
        self.engine.runAndWait()

    def speech_to_text(self):
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source)
            audio = self.recognizer.listen(source)
            try:
                text = self.recognizer.recognize_google(audio)
                return text
            except sr.UnknownValueError:
                return "Speech recognition could not understand audio"
            except sr.RequestError as e:
                return f"Could not request results from speech recognition service; {e}"

    def voice_command(self):
        self.text_to_speech("Please speak your command")
        command = self.speech_to_text()
        if "sos" in command.lower():
            self.activate_sos()
        elif "cancel" in command.lower() and "sos" in command.lower():
            self.cancel_sos()
        elif "check in" in command.lower():
            self.safe_check_in()
        elif "location" in command.lower():
            self.update_location()
        elif "emergency" in command.lower() and "call" in command.lower():
            self.call_emergency_services()
        elif "nearby" in command.lower() and "safe" in command.lower():
            self.find_nearby_safe_places()
        elif "mood" in command.lower():
            self.text_to_speech("How are you feeling?")
            mood = self.speech_to_text()
            self.mood_input.setText(mood)
            self.analyze_mood()
        else:
            self.text_to_speech("Command not recognized. Please try again.")

    def find_nearby_safe_places(self):
        location = self.get_location()
        if not location:
            QMessageBox.warning(self, "Location Error", "Unable to retrieve your location.")
            return

        # In a real application, you would use a places API (e.g., Google Places API) to get this information
        # For this example, we'll use dummy data
        safe_places = [
            {"name": "Central Police Station", "distance": "0.5 km"},
            {"name": "City Hospital", "distance": "1.2 km"},
            {"name": "Fire Department", "distance": "0.8 km"},
            {"name": "Community Center", "distance": "1.5 km"}
        ]

        safe_places_dialog = QDialog(self)
        safe_places_dialog.setWindowTitle("Nearby Safe Places")
        layout = QVBoxLayout()

        for place in safe_places:
            layout.addWidget(QLabel(f"{place['name']} - {place['distance']}"))


        close_button = QPushButton("Close")
        close_button.clicked.connect(safe_places_dialog.close)
        layout.addWidget(close_button)

        safe_places_dialog.setLayout(layout)
        safe_places_dialog.exec_()

    def call_emergency_services(self):
        emergency_number = "tel:112"  # Use the appropriate emergency number for your region
        QDesktopServices.openUrl(QUrl(emergency_number))
        QMessageBox.information(self, "Emergency Call", "Initiating call to emergency services (112)")

    # Battery Monitoring for Low Battery Alerts
    def monitor_battery(self):
        battery = psutil.sensors_battery()
        if battery and battery.percent < 20 and not battery.power_plugged:
            low_battery_message = f"Low Battery Alert: {self.user_data['name']} has less than 20% battery remaining. Please ensure their safety."
            self.send_sms_to_contacts(low_battery_message)

    # Real-time Location Sharing with Emergency Contacts
    def start_location_sharing(self):
        self.location_sharing_active = True
        self.location_sharing_timer = QTimer(self)
        self.location_sharing_timer.timeout.connect(self.share_location)
        self.location_sharing_timer.start(60000)  # Share location every 60 seconds

    def share_location(self):
        if self.location_sharing_active:
            location = self.get_location()
            location_message = f"Real-time Location Update: {self.user_data['name']} is currently at {location}."
            self.send_sms_to_contacts(location_message)

    def stop_location_sharing(self):
        self.location_sharing_active = False
        if hasattr(self, 'location_sharing_timer'):
            self.location_sharing_timer.stop()

    def closeEvent(self, event):
        self.stop_location_sharing()
        reply = QMessageBox.question(self, 'Exit',
            "Are you sure you want to exit the Personal Safety App?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))
    
    # Set the color palette
    palette = app.palette()
    palette.setColor(palette.Window, Qt.white)
    palette.setColor(palette.WindowText, Qt.black)
    palette.setColor(palette.Base, Qt.white)
    palette.setColor(palette.AlternateBase, Qt.lightGray)
    palette.setColor(palette.ToolTipBase, Qt.white)
    palette.setColor(palette.ToolTipText, Qt.black)
    palette.setColor(palette.Text, Qt.black)
    palette.setColor(palette.Button, Qt.lightGray)
    palette.setColor(palette.ButtonText, Qt.black)
    palette.setColor(palette.BrightText, Qt.red)
    palette.setColor(palette.Link, Qt.blue)
    palette.setColor(palette.Highlight, Qt.darkBlue)
    palette.setColor(palette.HighlightedText, Qt.white)
    app.setPalette(palette)

    # Set the application icon
    app_icon = QIcon("safety_app_icon.png")  # Make sure to have this icon file in your project directory
    app.setWindowIcon(app_icon)

    # Create and show the main window
    main_window = PersonalSafetyApp()
    main_window.show()

    # Start the event loop
    sys.exit(app.exec_())

