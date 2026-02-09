# SafeSense
Multisensor intelligence for real time hazard detection

**Team Members:**  
- Kavya Mohankumar
- Sai Pranavi Gogineni  

---

## Purpose of the Project

Fire and flood damage cause billions of dollars in losses every year, yet most security systems only **record incidents after they happen**. Cameras miss events when guards aren’t watching, smoke detectors trigger too late, and false alarms cause people to ignore real emergencies.

SafeSense was built to answer one question:  
**What if cameras could recognize danger as it happens and confirm it before alerting?**

Our goal was to create a **real-time hazard detection system** that prevents disasters instead of just documenting them — while eliminating false alarms that make existing systems unreliable.

Demo: https://www.youtube.com/watch?v=yAHVaK9cRas 
---

## What SafeSense Does

SafeSense uses **AI vision combined with physical sensors** to detect fires, floods, and emergencies in real time.

- Detects flames using AI vision  
- Confirms fires using temperature data  
- Detects flooding through humidity spikes  
- Detects people near danger zones  
- Sends alerts only when multiple sensors agree  

This sensor-fusion approach allows SafeSense to:
- Reject fake fires on TV screens  
- Prevent alert fatigue  
- Deliver verified alerts in under 2 seconds  

Alerts are delivered via **SMS**, a **web dashboard**, and a **local LCD display**.

---

## Tools & Technologies Used

### Hardware
- Arduino Nano  
- DHT22 Temperature & Humidity Sensor  
- HC-SR04 Ultrasonic Distance Sensor  
- Grove LCD Display  
- USB Webcam  

### Software
- Python  
- Flask (Web Server)  
- OpenCV (Video Processing)  
- YOLOv8 (Computer Vision Model)  
- PySerial (Arduino Communication)  
- Twilio API (SMS Alerts)  
- HTML / CSS / JavaScript (Dashboard)

---

## Challenges & How We Overcame Them

### False Positives
**Problem:**  
The system initially triggered alerts for YouTube videos, images of fire, and even orange clothing.

**Solution:**  
We implemented a **sensor fusion algorithm** that requires temperature confirmation before classifying a fire as real.

---

### Unstable Sensor Data
**Problem:**  
Arduino serial data was frequently corrupted or misread.

**Solution:**  
We added structured serial formatting and validation on the Python side to ensure reliable sensor readings.

---

### Performance Bottlenecks
**Problem:**  
Running AI detection and video streaming together caused lag.

**Solution:**  
We switched to a faster YOLO model and used multithreading to separate video capture, inference, and sensor processing.

---

### Limited Testing Conditions
**Problem:**  
We couldn’t safely test with real fire during the hackathon.

**Solution:**  
We demonstrated SafeSense’s **false-positive prevention**, showing it correctly reject fake fires while still detecting real flooding conditions.

---

## Accomplishments

- Zero false positives during 6+ hours of testing  
- Alert delivery in under 2 seconds  
- Built for ~$30 using off-the-shelf hardware  
- One system detects multiple hazard types  

---

## Credits & Frameworks Used

- **YOLOv8** – Ultralytics open-source object detection model  
- **OpenCV** – Open-source computer vision library  
- **Flask** – Python web framework  
- **Twilio API** – SMS alert delivery  
- **Arduino Framework** – Microcontroller programming  

---

## What’s Next

- Add gas detection and sound analysis (glass breaking)  
- Deploy on Raspberry Pi for standalone operation  
- Build a mobile app for remote monitoring  
- Pilot deployment in real buildings  
