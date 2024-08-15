import sys
import logging
from logging.handlers import RotatingFileHandler
import os
from email.parser import Parser
from email.header import decode_header
import pdb
import re
import quopri
from datetime import datetime
import argparse

from icalendar import Calendar, Event
import pytz


def setup_logging(log_path):
    """
    Sets up the logging configuration.
    """
    log_directory = os.path.dirname(log_path)
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    logger = logging.getLogger('CalsyncLogger')
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(
        log_path, 
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=5
    )
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Log to console (terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger

def process_email(data, ics_directory):
    """
    Processes the incoming email to extract reservation details and create or cancel an ICS event.
    """
    parser = Parser()
    mail_content = parser.parsestr(data)
    subject = decode_header(mail_content['subject'])[0][0]
    if isinstance(subject, bytes):
        subject = subject.decode('utf-8')

    if mail_content.is_multipart():
        parts = mail_content.get_payload()
        text = ''
        for part in parts:
            if part.get_content_type() == 'text/plain':
                text += quopri.decodestring(part.get_payload()).decode('utf8')
    else:
        text = quopri.decodestring(mail_content.get_payload()).decode('utf8')

    if "Le voyage de" in subject:
        process_reservation(text, ics_directory, subject)
    elif "a annulé son voyage" in subject:
        process_cancellation(text, ics_directory, subject)
    else:
        logger.warning(f"Email '{subject} did not match known patterns for reservation or cancellation.")

def process_reservation(text, ics_directory, subject):
    start_time = re.search(r'Début : (\d{2}/\d{2}/\d{2}) (\d{2}:\d{2})', text)
    end_time = re.search(r'Fin du voyage : (\d{2}/\d{2}/\d{2}) (\d{2}:\d{2})', text)
    name = re.search(r'Le voyage de (.+?) dans votre', text)
    car_name = re.search(r'dans votre (.*?) est réservé', text)

    if not (start_time and end_time and name):
        logger.warning(f"Email '{subject}' did not contain all required reservation details.")
        return

    paris_tz = pytz.timezone('Europe/Paris')
    start = paris_tz.localize(datetime.strptime(start_time.group(1) + ' ' + start_time.group(2), '%d/%m/%y %H:%M'))
    end = paris_tz.localize(datetime.strptime(end_time.group(1) + ' ' + end_time.group(2), '%d/%m/%y %H:%M'))

    event_name = name.group(1)
    car = car_name.group(1)
    create_ics_file(event_name, start, end, car, ics_directory)
    logger.info(f"Processed reservation for {event_name} from {start} to {end}")

def process_cancellation(text, ics_directory, subject):
    start_time = re.search(r'Début : (\d{2}/\d{2}/\d{2}) (\d{2}:\d{2})', text)
    name = re.search(r'(.+?) a annulé son voyage', text)

    if not (start_time and name):
        logger.warning(f"Email '{subject}' did not contain all required cancellation details.")
        return

    paris_tz = pytz.timezone('Europe/Paris')
    start = paris_tz.localize(datetime.strptime(start_time.group(1) + ' ' + start_time.group(2), '%d/%m/%y %H:%M'))
    event_name = name.group(1)

    if cancel_ics_event(event_name, start, ics_directory):
        logger.info(f"Cancelled reservation for {event_name} starting at {start}")

def create_ics_file(name, start, end, car, directory):
    ics_path = os.path.join(directory, 'reservation.ics')

    calendar = Calendar()
    if os.path.exists(ics_path):
        with open(ics_path, 'r') as f:
            calendar = Calendar.from_ical(f.read())

    event = Event()
    event.add('summary', f"{car} by {name}")
    event.add('dtstart', start)
    event.add('dtend', end)
    event.add('dtstamp', datetime.now(pytz.utc))

    calendar.add_component(event)

    with open(ics_path, 'wb') as f:
        f.write(calendar.to_ical())
    logger.info(f"ICS file updated successfully at {ics_path}")

def cancel_ics_event(name, start, directory):
    ics_path = os.path.join(directory, 'reservation.ics')

    if not os.path.exists(ics_path):
        logger.warning("ICS file not found. No event to cancel.")
        return

    with open(ics_path, 'r') as f:
        calendar = Calendar.from_ical(f.read())

    event_found = False
    for component in list(calendar.subcomponents):
        if component.name == "VEVENT":
            event_name = component.get('summary', '')
            event_start = component.decoded('dtstart')
            if name in event_name and start == event_start:
                calendar.subcomponents.remove(component)
                event_found = True
                logger.info(f"Event for {name} on {start} cancelled.")
                break

    if event_found:
        with open(ics_path, 'wb') as f:
            f.write(calendar.to_ical())
        logger.info(f"ICS file updated successfully at {ics_path}")
        return True
    else:
        logger.warning(f"No matching event found for {name} on {start}.")
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process email to generate or cancel an ICS calendar event.")
    parser.add_argument('-f', '--file', type=str, help='Path to the .eml file to process.')
    parser.add_argument('-p', '--path', type=str, default='/var/www/calsync/', help='Directory path to save the ICS file.')
    parser.add_argument('-l', '--log', type=str, default='/var/log/calsync/calsync.log', help='Path to the log file.')
    args = parser.parse_args()

    logger = setup_logging(args.log)

    if args.file:
        with open(args.file, 'r') as file:
            data = file.read()
    else:
        data = sys.stdin.read()

    process_email(data, args.path)