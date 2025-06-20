# app/sync.py
import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime
from flask import current_app

from .extensions import db
from .models import Product, Sale

def sync_products_from_xml():
    """Завантажує та синхронізує товари з XML-фіда."""
    with current_app.app_context():
        # ... (решта коду функції без змін)
        url = "https://printec.salesdrive.me/export/yml/export.yml?publicKey=i1wcuj4-4oGrmFhj9I6iyLpolm12OeeDhdqg_w8XH_Qitjr4zud3seyWgBpJ"
        print(f"[{datetime.now()}] Починаю синхронізацію з XML...")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            categories = {cat.attrib['id']: cat.text for cat in root.findall('.//category')}
            offers = root.findall('.//offer')

            all_skus_in_xml = {offer.find('article').text for offer in offers if offer.find('article') is not None}
            all_db_products = {p.sku: p for p in Product.query.all()}
            
            for offer in offers:
                sku = offer.find('article').text if offer.find('article') is not None else None
                if not sku: continue

                category_id = offer.find('categoryId').text if offer.find('categoryId') is not None else ''
                picture_tag = offer.find('picture')
                picture_url = picture_tag.text if picture_tag is not None else ''

                offer_data = {
                    'product_id': offer.attrib.get('id'), 'product_sku': sku,
                    'product_name': offer.find('name').text if offer.find('name') is not None else 'Без назви',
                    'product_description': offer.find('description').text if offer.find('description') is not None else '',
                    'product_price': offer.find('price').text if offer.find('price') is not None else '0',
                    'product_price_currency': offer.find('currencyId').text if offer.find('currencyId') is not None else 'UAH',
                    'product_quantity_in_stock': offer.find('quantity_in_stock').text if offer.find('quantity_in_stock') is not None else '0',
                    'product_url': offer.find('url').text if offer.find('url') is not None else '',
                    'product_category': categories.get(category_id, ''),
                    'product_vendor': offer.find('vendorCode').text if offer.find('vendorCode') is not None else '',
                    'product_picture': picture_url,
                    'product_params': {p.attrib['name']: p.text for p in offer.findall('param')}
                }
                
                name = offer_data['product_name']
                price = float(offer_data['product_price'])
                stock = int(offer_data['product_quantity_in_stock'])
                product = all_db_products.get(sku)

                if product:
                    if product.stock != stock and product.stock > stock:
                        db.session.add(Sale(product_id=product.id, quantity_sold=product.stock - stock))
                    product.name, product.price, product.stock = name, price, stock
                    product.xml_data = json.dumps(offer_data, ensure_ascii=False)
                else:
                    db.session.add(Product(sku=sku, name=name, price=price, stock=stock, xml_data=json.dumps(offer_data, ensure_ascii=False)))
            
            skus_to_delete = set(all_db_products.keys()) - all_skus_in_xml
            if skus_to_delete:
                Product.query.filter(Product.sku.in_(skus_to_delete)).delete(synchronize_session=False)

            db.session.commit()
            print(f"[{datetime.now()}] Синхронізація успішно завершена.")
        except Exception as e:
            db.session.rollback()
            print(f"Помилка під час синхронізації: {e}")