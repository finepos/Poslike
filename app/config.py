# config.py
import os

class Config:
    """Клас конфігурації Flask."""
    SCHEDULER_API_ENABLED = True
    SECRET_KEY = os.urandom(24)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///../instance/stock_control.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# Loglevel
# Глобальний порядок пріоритету сортування параметрів видалено,
# оскільки він більше не використовується.

# Стандартні ZPL-шаблони
DEFAULT_ZPL_SORTING = """^XA
^LS0
^CI28
^FO5,200^BXN,4,200,0,0,1
^FD{product_sku}^FS
^FO285,100^BQN,2,3
^FDQA,{product_url}^FS
^FO5,10^A0N,20,20^TBN,430,100
^FD{product_name}^FS
^FO140,232^A0N,30,30
^FD{product_sorting_quantity}^FS
^FO110,220^GB160,50,5
^FS
^FO5,120^A0N,29,23^TBN,320,100
^FD{product_sku}^FS
^FO80,290^A0N,20,20
^FDPRINTEC.COM.UA | +38 093 333 0 777^FS
^XZ"""

DEFAULT_ZPL_NO_SORTING = """^XA
^LS0
^CI28
^FO5,200^BXN,4,200,0,0,1
^FD{product_sku}^FS
^FO285,100^BQN,2,3
^FDQA,{product_url}^FS
^FO5,10^A0N,20,20^TBN,430,100
^FD{product_name}^FS
^FO5,120^A0N,29,23^TBN,320,100
^FD{product_sku}^FS
^FO80,290^A0N,20,20
^FDPRINTEC.COM.UA | +38 093 333 0 777^FS
^XZ"""