"""
Alert generation and delivery system
Handles thresholding, deduplication, and multi-channel notifications
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from enum import Enum
from sqlalchemy.orm import Session
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

from db import Alert, Station, Reading

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertThresholds:
    """Risk score thresholds for alert levels"""
    LOW = 30
    MEDIUM = 50
    HIGH = 75
    CRITICAL = 90


class AlertDebouncer:
    """Prevent alert fatigue by suppressing repeated alerts within time window"""

    def __init__(self, min_interval_minutes: int = 30):
        self.min_interval_minutes = min_interval_minutes
        self.last_alert_time: Dict[str, datetime] = {}

    def should_alert(self, station_id: str, alert_level: AlertLevel) -> bool:
        """Check if enough time has passed since last alert for this station"""
        last_time = self.last_alert_time.get(station_id)
        if last_time is None:
            return True

        time_since = datetime.utcnow() - last_time
        should_send = time_since >= timedelta(minutes=self.min_interval_minutes)

        if should_send:
            self.last_alert_time[station_id] = datetime.utcnow()
        else:
            logger.debug(
                f"Alert suppressed for {station_id}: only {time_since.seconds}s since last alert"
            )
        return should_send

    def record_alert(self, station_id: str):
        """Record alert sent time"""
        self.last_alert_time[station_id] = datetime.utcnow()


def get_alert_level(risk_score: float) -> AlertLevel:
    """Convert risk score (0-100) to alert level"""
    if risk_score >= AlertThresholds.CRITICAL:
        return AlertLevel.CRITICAL
    elif risk_score >= AlertThresholds.HIGH:
        return AlertLevel.HIGH
    elif risk_score >= AlertThresholds.MEDIUM:
        return AlertLevel.MEDIUM
    else:
        return AlertLevel.LOW


def create_alert(
    db: Session,
    station_id: str,
    risk_score: float,
    predicted_peak: Optional[float] = None,
    trigger_reason: str = "automatic_monitoring",
) -> Optional[Alert]:
    """
    Create a new alert if conditions warrant it.
    Checks deduplication and returns the alert or None if suppressed.
    """
    alert_level = get_alert_level(risk_score)

    # Don't create LOW alerts (only for internal tracking)
    if alert_level == AlertLevel.LOW:
        return None

    # Check for recent duplicate alerts at same level
    recent_alert = (
        db.query(Alert)
        .filter(
            Alert.station_id == station_id,
            Alert.alert_level == alert_level.value,
            Alert.is_active == True,
            Alert.created_at > datetime.utcnow() - timedelta(minutes=30),
        )
        .first()
    )
    if recent_alert:
        logger.info(f"Alert suppressed for {station_id}: duplicate within 30 min")
        return None

    # Create new alert
    alert = Alert(
        station_id=station_id,
        alert_level=alert_level.value,
        risk_score=risk_score,
        predicted_peak=predicted_peak,
        trigger_reason=trigger_reason,
        is_active=True,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    logger.info(f"Alert created: {station_id} -> {alert_level} (score: {risk_score})")
    return alert


def dismiss_alert(db: Session, alert_id: str) -> bool:
    """Mark an alert as dismissed"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_active = False
        alert.dismissed_at = datetime.utcnow()
        db.commit()
        return True
    return False


def acknowledge_alert(db: Session, alert_id: str, operator_id: str) -> bool:
    """Acknowledge an alert by operator"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.acknowledged = True
        alert.acknowledged_by = operator_id
        alert.acknowledged_at = datetime.utcnow()
        db.commit()
        return True
    return False


class EmailNotifier:
    """Send email alerts via SMTP"""

    def __init__(
        self,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
        sender_email: str = None,
        sender_password: str = None,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email or os.getenv("ALERT_EMAIL")
        self.sender_password = sender_password or os.getenv("ALERT_EMAIL_PASSWORD")

    def send_alert_email(
        self, recipient_email: str, station_name: str, alert_level: str, risk_score: float
    ) -> bool:
        """Send alert email to recipient"""
        if not self.sender_email or not self.sender_password:
            logger.warning("Email credentials not configured")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = recipient_email
            msg["Subject"] = f"🚨 FLOOD ALERT: {alert_level} at {station_name}"

            body = f"""
            <html>
              <body style="font-family: Arial, sans-serif;">
                <h2 style="color: {'red' if alert_level == 'CRITICAL' else 'orange'};">Flood Alert - {alert_level}</h2>
                <p><strong>Location:</strong> {station_name}</p>
                <p><strong>Risk Score:</strong> {risk_score:.1f}/100</p>
                <p><strong>Alert Time:</strong> {datetime.utcnow().isoformat()}</p>
                <p><a href="https://floodguard.example.com/dashboard">View Dashboard</a></p>
              </body>
            </html>
            """

            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            logger.info(f"Alert email sent to {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class SMSNotifier:
    """Send SMS alerts via Twilio"""

    def __init__(self, account_sid: str = None, auth_token: str = None, from_number: str = None):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = from_number or os.getenv("TWILIO_PHONE_NUMBER")
        self.client = None
        if self.account_sid and self.auth_token:
            try:
                from twilio.rest import Client
                self.client = Client(self.account_sid, self.auth_token)
            except ImportError:
                logger.warning("Twilio not installed")

    def send_alert_sms(self, phone_number: str, station_name: str, alert_level: str, risk_score: float) -> bool:
        """Send alert SMS to recipient"""
        if not self.client:
            logger.warning("Twilio client not configured")
            return False

        try:
            message = (
                f"🚨 {alert_level} FLOOD ALERT at {station_name}. "
                f"Risk: {risk_score:.0f}%. Check dashboard for details."
            )

            self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=phone_number
            )
            logger.info(f"Alert SMS sent to {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return False


class AlertDispatcher:
    """Centralized alert delivery coordinator"""

    def __init__(self):
        self.email_notifier = EmailNotifier()
        self.sms_notifier = SMSNotifier()
        self.debouncer = AlertDebouncer(min_interval_minutes=30)

    def dispatch_alert(
        self,
        db: Session,
        station: Station,
        risk_score: float,
        predicted_peak: Optional[float] = None,
        channels: List[str] = None,
    ) -> Optional[Alert]:
        """
        Full alert workflow: create alert, check dedup, send notifications
        
        Args:
            channels: List of delivery channels ('email', 'sms', 'dashboard')
        """
        if channels is None:
            channels = ["email", "dashboard"]

        # Create alert in DB (with dedup)
        alert = create_alert(
            db,
            station.station_id,
            risk_score,
            predicted_peak,
            trigger_reason="water_level_trend",
        )
        if alert is None:
            return None

        # Send notifications
        if "email" in channels:
            self.email_notifier.send_alert_email(
                "operators@floodguard.example.com",
                station.name,
                alert.alert_level,
                risk_score,
            )

        if "sms" in channels:
            self.sms_notifier.send_alert_sms(
                "+911234567890",  # TODO: retrieve from operator DB
                station.name,
                alert.alert_level,
                risk_score,
            )

        logger.info(f"Alert dispatched via {channels}")
        return alert


# Global dispatcher instance
_dispatcher: Optional[AlertDispatcher] = None


def get_alert_dispatcher() -> AlertDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AlertDispatcher()
    return _dispatcher
