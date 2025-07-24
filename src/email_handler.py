#!/usr/bin/env python3
"""
Email Handler Service for Bird Detection System
"""

import smtplib
import socket
import os
import json
import time
import glob
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from queue import Queue, Empty
from .logger import get_logger

logger = get_logger(__name__)

class EmailHandler:
    """Handles all email functionality for the bird detection system"""
    
    def __init__(self, config):
        self.config = config['email']
        self.storage_config = config['storage']
        
        # Email credentials from config
        self.sender_email = self.config['sender']
        self.email_password = self.config.get('password', '')
        
        if not self.email_password:
            logger.warning("Email password not configured in config.json")
        
        # Email queue for async sending
        self.email_queue = Queue()
        self.email_thread = None
        self.running = False
        
        # Hourly report scheduler
        self.hourly_timer = None
        self.last_hourly_report = None
        
        # Tracking
        self.last_sent_record = os.path.join(self.storage_config['save_dir'], 'last_sent.json')
        
        logger.info("Email handler initialized")
    
    def start(self):
        """Start the email service"""
        if self.running:
            return
            
        self.running = True
        self.email_thread = threading.Thread(target=self._email_worker, daemon=True)
        self.email_thread.start()
        
        # Start hourly report scheduler if enabled
        if self.config.get('hourly_report', False):
            self._schedule_hourly_reports()
        
        # Send startup notification
        self.send_startup_email()
        
        logger.info("Email service started")
    
    def stop(self):
        """Stop the email service"""
        self.running = False
        if self.hourly_timer:
            self.hourly_timer.cancel()
        if self.email_thread:
            self.email_thread.join(timeout=5)
        logger.info("Email service stopped")
    
    def _email_worker(self):
        """Background worker for sending emails"""
        while self.running:
            try:
                # Get email from queue with timeout
                email_data = self.email_queue.get(timeout=1)
                if email_data is None:
                    break
                
                # Send the email
                self._send_email(**email_data)
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in email worker: {e}")
    
    def _schedule_hourly_reports(self):
        """Schedule hourly reports to run at the top of each hour"""
        if not self.running:
            return
            
        # Calculate seconds until next hour
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        seconds_until_next_hour = (next_hour - now).total_seconds()
        
        # Schedule the next hourly report
        self.hourly_timer = threading.Timer(seconds_until_next_hour, self._hourly_report_callback)
        self.hourly_timer.start()
        
        logger.info(f"Next hourly report scheduled for {next_hour.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def _hourly_report_callback(self):
        """Callback for hourly report timer"""
        if not self.running:
            return
            
        try:
            # Send hourly report
            self.send_hourly_report()
            
            # Schedule next report
            self._schedule_hourly_reports()
            
        except Exception as e:
            logger.error(f"Error in hourly report callback: {e}")
    
    def _send_email(self, subject, body_html, image_paths, recipient=None):
        """Send email with attachments"""
        try:
            if not self.email_password:
                logger.warning("No email password configured, skipping email")
                return False
            
            # Use primary recipient if none specified
            if recipient is None:
                recipient = self.config['receivers']['primary']
            
            logger.info(f"Sending email to {recipient}: {subject}")
            
            # Create message
            message = MIMEMultipart()
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient
            
            # Attach HTML body
            message.attach(MIMEText(body_html, "html"))
            
            # Attach images
            for img_path in image_paths:
                try:
                    if os.path.exists(img_path):
                        with open(img_path, 'rb') as img_file:
                            img = MIMEImage(img_file.read())
                            img.add_header(
                                'Content-Disposition', 
                                'attachment', 
                                filename=os.path.basename(img_path)
                            )
                            message.attach(img)
                            logger.debug(f"Attached image: {os.path.basename(img_path)}")
                    else:
                        logger.warning(f"Image not found: {img_path}")
                except Exception as e:
                    logger.error(f"Error attaching image {img_path}: {e}")
            
            # Send email
            with smtplib.SMTP_SSL(self.config['smtp_server'], self.config['smtp_port']) as server:
                server.login(self.sender_email, self.email_password)
                server.sendmail(self.sender_email, recipient, message.as_string())
            
            logger.info(f"Email sent successfully to {recipient}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication Error: {e}")
        except socket.gaierror as e:
            logger.error(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
        
        return False
    
    def send_reboot_notification(self, system_info):
        """Send notification when system reboots"""
        try:
            hostname = system_info.get('hostname', 'unknown')
            ip_address = system_info.get('ip_address', 'unknown')
            uptime = system_info.get('uptime', 'unknown')
            
            subject = f"🔄 Bird Detection System Reboot - {hostname}"
            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h2 style="color: #2E8B57;">🔄 Bird Detection System Reboot Notification</h2>
                
                <div style="background-color: #f0f8ff; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <h3 style="color: #1e90ff; margin-top: 0;">System Information</h3>
                    <p><strong>Hostname:</strong> {hostname}</p>
                    <p><strong>IP Address:</strong> {ip_address}</p>
                    <p><strong>Reboot Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>System Uptime:</strong> {uptime}</p>
                </div>
                
                <div style="background-color: #f0fff0; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <h3 style="color: #228b22; margin-top: 0;">🐦 Bird Detection Status</h3>
                    <p>✅ <strong>Bird Detection System Started Successfully</strong></p>
                    <p>📹 Camera initialization in progress...</p>
                    <p>🎯 Motion detection will be active shortly</p>
                </div>
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated notification from the Bird Detection Motion Capture System.
                </p>
            </body>
            </html>
            """
            
            # Queue the email
            self.email_queue.put({
                'subject': subject,
                'body_html': body_html,
                'image_paths': [],
                'recipient': self.config['receivers']['primary']
            })
            
            logger.info("Reboot notification queued")
            
        except Exception as e:
            logger.error(f"Error preparing reboot notification: {e}")
    
    def send_motion_capture(self, image_path):
        """Send notification for motion capture"""
        try:
            if self._is_quiet_hours():
                logger.info("Skipping motion capture email - quiet hours")
                return
            
            capture_time = datetime.fromtimestamp(os.path.getctime(image_path))
            subject = f"🐦 Bird Detected - {capture_time.strftime('%Y-%m-%d %H:%M:%S')}"
            
            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h2 style="color: #2E8B57;">🐦 Bird Detection Alert</h2>
                
                <div style="background-color: #f0fff0; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>Motion detected at:</strong> {capture_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Image file:</strong> {os.path.basename(image_path)}</p>
                    <p><strong>File size:</strong> {os.path.getsize(image_path) / 1024:.1f} KB</p>
                </div>
                
                <p>See attached image for the captured bird photo.</p>
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Automated capture from Bird Detection Motion Capture System.
                </p>
            </body>
            </html>
            """
            
            # Queue the email
            self.email_queue.put({
                'subject': subject,
                'body_html': body_html,
                'image_paths': [image_path],
                'recipient': self.config['receivers']['primary']
            })
            
            logger.info(f"Motion capture notification queued: {image_path}")
            
        except Exception as e:
            logger.error(f"Error preparing motion capture notification: {e}")
    
    def send_hourly_report(self):
        """Send hourly report with latest images"""
        try:
            if self._is_quiet_hours():
                logger.info("Skipping hourly report - quiet hours")
                return
            
            # Find all images
            image_files = self._get_image_files()
            if not image_files:
                logger.info("No images found for hourly report")
                return
            
            # Sort by timestamp
            image_files.sort()
            
            # Get latest 5 images (always send these regardless of previous sends)
            latest_images = image_files[-5:]
            
            subject = f"📊 Hourly Bird Report - Latest 5 Images"
            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h2 style="color: #2E8B57;">📊 Hourly Bird Detection Report</h2>
                
                <div style="background-color: #f0f8ff; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>Report Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Latest Images:</strong> {len(latest_images)}</p>
                    <p><strong>Total Images:</strong> {len(image_files)}</p>
                </div>
                
                <p>Attached are the {len(latest_images)} most recent bird captures from the past hour.</p>
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Automated hourly report from Bird Detection System.
                </p>
            </body>
            </html>
            """
            
            # Queue the email
            self.email_queue.put({
                'subject': subject,
                'body_html': body_html,
                'image_paths': latest_images,
                'recipient': self.config['receivers']['primary']
            })
            
            logger.info(f"Hourly report queued with {len(latest_images)} latest images")
            
        except Exception as e:
            logger.error(f"Error preparing hourly report: {e}")
    
    def send_daily_summary(self):
        """Send daily summary email"""
        try:
            image_files = self._get_image_files()
            if not image_files:
                logger.info("No images found for daily summary")
                return
            
            # Get today's images
            today = datetime.now().strftime('%Y-%m-%d')
            today_images = [
                img for img in image_files 
                if datetime.fromtimestamp(os.path.getctime(img)).strftime('%Y-%m-%d') == today
            ]
            
            # Get latest image
            latest_image = max(image_files, key=os.path.getctime) if image_files else None
            
            subject = f"📅 Daily Bird Summary - {today}"
            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h2 style="color: #2E8B57;">📅 Daily Bird Detection Summary</h2>
                
                <div style="background-color: #f0f8ff; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>Date:</strong> {today}</p>
                    <p><strong>Today's Captures:</strong> {len(today_images)}</p>
                    <p><strong>Total Images:</strong> {len(image_files)}</p>
                </div>
                
                {"<p>Latest capture attached.</p>" if latest_image else "<p>No captures today.</p>"}
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Daily summary from Bird Detection System.
                </p>
            </body>
            </html>
            """
            
            # Queue the email
            self.email_queue.put({
                'subject': subject,
                'body_html': body_html,
                'image_paths': [latest_image] if latest_image else [],
                'recipient': self.config['receivers']['primary']
            })
            
            logger.info(f"Daily summary queued - {len(today_images)} today's captures")
            
        except Exception as e:
            logger.error(f"Error preparing daily summary: {e}")
    
    def _get_image_files(self):
        """Get all image files from storage directory"""
        try:
            jpg_files = glob.glob(os.path.join(self.storage_config['save_dir'], "*.jpg"))
            jpeg_files = glob.glob(os.path.join(self.storage_config['save_dir'], "*.jpeg"))
            return jpg_files + jpeg_files
        except Exception as e:
            logger.error(f"Error getting image files: {e}")
            return []
    
    def _load_last_sent_record(self):
        """Load record of last sent images"""
        try:
            if os.path.exists(self.last_sent_record):
                with open(self.last_sent_record, 'r') as f:
                    return set(json.load(f))
            return set()
        except Exception as e:
            logger.error(f"Error loading last sent record: {e}")
            return set()
    
    def _save_last_sent_record(self, image_paths):
        """Save record of sent images"""
        try:
            with open(self.last_sent_record, 'w') as f:
                json.dump(list(image_paths), f)
        except Exception as e:
            logger.error(f"Error saving last sent record: {e}")
    
    def _is_quiet_hours(self):
        """Check if current time is in quiet hours"""
        try:
            current_hour = datetime.now().hour
            start_hour = self.config['quiet_hours']['start']
            end_hour = self.config['quiet_hours']['end']
            
            if start_hour <= end_hour:
                return start_hour <= current_hour <= end_hour
            else:
                return current_hour >= start_hour or current_hour <= end_hour
        except Exception:
            return False
    
    def send_startup_email(self):
        """Send email notification on system startup/reboot"""
        try:
            hostname = socket.gethostname()
            startup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            subject = f"🚀 Bird Detection System Started - {hostname}"
            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h2 style="color: #2E8B57;">🚀 System Startup Notification</h2>
                
                <div style="background-color: #f0f8ff; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>Hostname:</strong> {hostname}</p>
                    <p><strong>Startup Time:</strong> {startup_time}</p>
                    <p><strong>Status:</strong> All services started successfully</p>
                </div>
                
                <h3>Active Services:</h3>
                <ul>
                    <li>Camera Service: Active</li>
                    <li>Motion Detection: Active</li>
                    <li>Email Service: Active</li>
                    <li>Google Drive Upload: {'Active' if self.config.get('drive_upload', {}).get('enabled', False) else 'Disabled'}</li>
                    <li>Hourly Reports: {'Active' if self.config.get('hourly_report', False) else 'Disabled'}</li>
                </ul>
                
                <p>The bird detection system has started successfully and is now monitoring.</p>
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated notification from the Bird Detection System.
                </p>
            </body>
            </html>
            """
            
            # Queue the email
            self.email_queue.put({
                'subject': subject,
                'body_html': body_html,
                'image_paths': [],
                'recipient': self.config['receivers']['primary']
            })
            
            logger.info("Startup email notification queued")
            
        except Exception as e:
            logger.error(f"Error sending startup email: {e}")
    
    def get_queue_size(self):
        """Get current email queue size"""
        return self.email_queue.qsize()
    
    def send_email_with_attachments(self, recipient, subject, body, attachment_paths):
        """Send email with multiple image attachments"""
        try:
            if not self.email_password:
                logger.error("Email password not configured")
                return False
                
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = recipient
            
            # Add text body
            msg.attach(MIMEText(body, 'plain'))
            
            # Add attachments
            for path in attachment_paths:
                path_str = str(path)  # Convert Path object to string
                if os.path.exists(path_str):
                    with open(path_str, 'rb') as f:
                        img = MIMEImage(f.read())
                        img.add_header('Content-Disposition', 'attachment', 
                                     filename=os.path.basename(path_str))
                        msg.attach(img)
                        
            # Send email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.sender_email, self.email_password)
                server.send_message(msg)
                
            logger.info(f"Sent email with {len(attachment_paths)} attachments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email with attachments: {e}")
            return False
    
    def clear_queue(self):
        """Clear email queue"""
        try:
            while not self.email_queue.empty():
                self.email_queue.get_nowait()
            logger.info("Email queue cleared")
        except Exception as e:
            logger.error(f"Error clearing email queue: {e}")