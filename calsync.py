import sys
import logging
from logging.handlers import RotatingFileHandler
import os
from email.parser import Parser
import re
import quopri

from ics import Calendar, Event

# Setup logging
log_directory = '/var/log/calsync'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

logger = logging.getLogger('CalsyncLogger')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(
    os.path.join(log_directory, 'calsync.log'), 
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def process_email(data):
    """
    Processes the incoming email to extract reservation details and create an ICS file.
    """
    # Parse the email content using a more compatible method
    parser = Parser()
    mail_content = parser.parsestr(data)
    
    # Assuming text/plain content is direct in the email body (not multipart)
    if mail_content.is_multipart():
        parts = mail_content.get_payload()
        text = ''
        for part in parts:
            if part.get_content_type() == 'text/plain':
                text += quopri.decodestring(part.get_payload()).decode('utf8')
    else:
        text = quopri.decodestring(mail_content.get_payload()).decode('utf8')

    # Extract data using regex

    start_time = re.search(r'Début : (\d{2}/\d{2}/\d{2}) (\d{2}:\d{2})', text)
    end_time = re.search(r'Fin du voyage : (\d{2}/\d{2}/\d{2}) (\d{2}:\d{2})', text)
    name = re.search(r'Le voyage de (\w+) dans votre', text)
    car_name = re.search(r'dans votre (.*?) est réservé', text)

    if not (start_time and end_time and name):
        logger.warning("Email did not contain all required reservation details.")
        return

    # Create ICS file if valid data is found
    start = '20' + start_time.group(1).replace('/', '-') + ' ' + start_time.group(2)
    end = '20' + end_time.group(1).replace('/', '-') + ' ' + end_time.group(2)
    event_name = name.group(1)
    car = car_name.group(1)
    create_ics_file(event_name, start, end, car, '/var/www/calsync/')
    logger.info(f"Processed reservation for {event_name} from {start} to {end}")

def create_ics_file(name, start, end, car, directory):
    """
    Creates an ICS file based on the reservation details.
    """
    ics_path = os.path.join(directory, 'reservation.ics')

    # Load existing calendar events
    calendar = Calendar()
    if os.path.exists(ics_path):
        with open(ics_path, 'r') as f:
            calendar = Calendar(f.read())

    # Create new event
    event = Event()
    event.name = f"{car} by {name}"
    event.begin = start
    event.end = end

    # Add new event to calendar
    calendar.events.add(event)

    # Write all events back to the ICS file
    with open(ics_path, 'w') as f:
        f.writelines(calendar.serialize())
    logger.info(f"ICS file updated successfully at {ics_path}")
if __name__ == '__main__':
    # Read email data from stdin
    data = sys.stdin.read()
    # for testing purpose, uncomment these lines to read from file
    # with open('/opt/example.eml', 'r') as file:
    #     data = file.read()    
    process_email(data)

