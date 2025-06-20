# app/printing.py
import socket
import json
import re
import logging

from .utils import get_default_template_for_size

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_printer_status(printer_ip, printer_port):
    # ... (ця функція залишається без змін, вона вже правильна) ...
    log = logging.getLogger(__name__)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((printer_ip, int(printer_port)))
            s.send(b"~HS")
            response_raw = s.recv(1024)

        if not response_raw:
            return False, "Empty Response"
        
        response_decoded = response_raw.decode("utf-8", errors='ignore')
        clean_response = response_decoded.replace('\x02', '').replace('\x03', '')
        
        log.info(f"Printer {printer_ip}:{printer_port} cleaned response:\n{clean_response.strip()}")

        is_paused = False
        is_paper_out = False
        is_ready = False
        
        for line in clean_response.strip().split('\n'):
            clean_line = line.strip()
            if not clean_line:
                continue

            if clean_line.startswith('030,0,0'):
                is_ready = True

            parts = clean_line.split(',')
            if len(parts) >= 3:
                if parts[1] == '1':
                    is_paused = True
                if parts[2] == '1':
                    is_paper_out = True
        
        if is_paused:
            return False, "Paused"
        if is_paper_out:
            return False, "Paper Out / Alarm"
        if is_ready:
            return True, "Ready"
        
        return False, "Not Ready (Unknown Response)"

    except socket.timeout:
        log.warning(f"Printer {printer_ip}:{printer_port} - Connection timed out.")
        return False, "Offline"
    except (socket.error, ConnectionRefusedError) as e:
        log.warning(f"Printer {printer_ip}:{printer_port} - Connection error: {e}")
        return False, "Offline"
    except Exception as e:
        log.error(f"Printer {printer_ip}:{printer_port} - Unknown error on status check: {e}")
        return False, "Unknown Error"


def generate_zpl_code(printer, product, sorting_quantity=None, quantity=1):
    """ОНОВЛЕНО: Генерує ZPL-код та додає команду для друку кількох копій."""
    if not product.xml_data:
        return "^XA^FDError: No XML data^FS^XZ"

    data = json.loads(product.xml_data)
    template = printer.zpl_code_template or get_default_template_for_size(printer.is_for_sorting)

    template = re.sub(r'\{product_param:([^}]+)\}', lambda m: str(data.get('product_params', {}).get(m.group(1), '')), template)
    sorting_text = f'{sorting_quantity} шт.' if sorting_quantity and sorting_quantity.isdigit() else ''
    template = template.replace('{product_sorting_quantity}', sorting_text)

    for key, value in data.items():
        if key.startswith('product_') and key != 'product_params':
            template = template.replace(f'{{{key}}}', str(value or ''))

    # --- НОВА ЛОГІКА ДЛЯ КІЛЬКОСТІ ---
    # Додаємо команду ^PQ (Print Quantity) перед кінцевою командою ^XZ
    if quantity > 1:
        if '^XZ' in template:
            # Вставляємо команду перед ^XZ
            template = template.replace('^XZ', f'^PQ{quantity}^XZ')
        else:
            # Якщо з якоїсь причини немає ^XZ, просто додаємо в кінець
            template += f'^PQ{quantity}'

    return template


def send_zpl_to_printer(printer_ip, printer_port, zpl_code):
    # ... (ця функція без змін) ...
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((printer_ip, int(printer_port)))
            s.sendall(zpl_code.encode('utf-8'))
        return True, "Завдання успішно відправлено."
    except socket.timeout:
        return False, "Помилка: Таймаут підключення до принтера."
    except Exception as e:
        return False, f"Помилка відправки: {e}"