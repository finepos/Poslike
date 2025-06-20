# app/routes.py
import json
import re
import time
from math import ceil
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from sqlalchemy import func

from .extensions import db
from .models import Product, InTransitOrder, Printer, ColorSetting, PrintJob
from .utils import (get_pagination_window, calculate_forecast,
                   natural_sort_key, get_all_placeholders, get_default_template_for_size)
from .printing import generate_zpl_code, send_zpl_to_printer, check_printer_status


@current_app.route('/')
def index():
    # ... (код функції index без змін) ...
    page = request.args.get('page', 1, type=int)
    show_all = request.args.get('show_all')
    search_sku = request.args.get('search_sku', '')
    search_name = request.args.get('search_name', '')
    stock_filter = request.args.get('stock_filter', '')
    stock_quantity = request.args.get('stock_quantity', '')
    search_category = request.args.get('search_category', '')
    stock_level_filter = request.args.get('stock_level', '')

    query = Product.query
    if search_sku: query = query.filter(Product.sku.ilike(f'%{search_sku}%'))
    if search_name: query = query.filter(Product.name.ilike(f'%{search_name}%'))
    if search_category: query = query.filter(Product.xml_data.like(f'%"product_category": "{search_category.replace("\"", "\"\"")}"%'))
    if stock_filter and stock_quantity.isdigit():
        q = int(stock_quantity)
        if stock_filter == 'less': query = query.filter(Product.stock < q)
        elif stock_filter == 'more': query = query.filter(Product.stock > q)
        elif stock_filter == 'equal': query = query.filter(Product.stock == q)

    param_filters = {}
    if search_category:
        products_in_cat = Product.query.filter(Product.xml_data.like(f'%"product_category": "{search_category.replace("\"", "\"\"")}"%')).with_entities(Product.xml_data).all()
        unique_param_names = {k for p_xml, in products_in_cat if p_xml for k in json.loads(p_xml).get('product_params', {}).keys()}
        param_name_map = {re.sub(r'[\s/]+', '_', name): name for name in unique_param_names}
        for key, value in request.args.items():
            if key.startswith('param_') and value:
                original_name = param_name_map.get(key[len('param_'):])
                if original_name:
                    param_filters[original_name] = value
                    query = query.filter(Product.xml_data.like(f'%"{original_name.replace("\"", "\"\"")}": "{value.replace("\"", "\"\"")}"%'))

    all_filtered_products = query.all()
    products_by_category = {}
    for p in all_filtered_products:
        if p.xml_data:
            try:
                category = json.loads(p.xml_data).get('product_category')
                products_by_category.setdefault(category, []).append(p)
            except (json.JSONDecodeError, AttributeError):
                continue

    benchmark_stock = {}
    for cat, stocks_list in products_by_category.items():
        if stocks_list:
            sorted_stocks = sorted([p.stock for p in stocks_list], reverse=True)
            top_20_percent_count = ceil(len(stocks_list) * 0.2) or 1
            top_stocks = sorted_stocks[:top_20_percent_count]
            benchmark_stock[cat] = sum(top_stocks) / len(top_stocks) if top_stocks else 0
        else:
            benchmark_stock[cat] = 0

    final_products_to_display = []
    for p in all_filtered_products:
        xml_data = json.loads(p.xml_data) if p.xml_data else {}
        category = xml_data.get('product_category')
        bm = benchmark_stock.get(category, 0)
        perc = (p.stock / bm) * 100 if bm > 0 else 0

        status = 'status-critical' if p.minimum_stock is not None and p.stock < p.minimum_stock else \
                 'status-level-1' if perc <= 20 else 'status-level-2' if perc <= 40 else \
                 'status-level-3' if perc <= 60 else 'status-level-4' if perc <= 80 else 'status-level-5'

        item_data = {
            'product': p,
            'product_url': xml_data.get('product_url', ''),
            'product_picture': xml_data.get('product_picture', ''),
            'status_class': status
        }
        if not stock_level_filter or stock_level_filter == status:
            final_products_to_display.append(item_data)

    for item in final_products_to_display:
        avg_sales, days_left = calculate_forecast(item['product'].id, item['product'].stock)
        item['avg_sales_per_day'] = avg_sales
        item['days_left'] = days_left

    if search_category:
        params_in_cat = {k for p in products_by_category.get(search_category, []) if p.xml_data for k in (json.loads(p.xml_data).get('product_params', {}) or {})}
        if params_in_cat:
            dynamic_sort_order = sorted(list(params_in_cat), reverse=True)
            final_products_to_display.sort(key=lambda item: tuple(natural_sort_key(json.loads(item['product'].xml_data).get('product_params', {}).get(p)) for p in dynamic_sort_order) if item['product'].xml_data else ())

    total = len(final_products_to_display)
    items_per_page = total if show_all and search_category and total > 0 else 100
    start = (page - 1) * items_per_page
    paginated_products = final_products_to_display[start : start + items_per_page]

    pagination = { 'page': page, 'per_page': items_per_page, 'total': total, 'pages': ceil(total / items_per_page) }
    pagination['window'] = get_pagination_window(pagination['page'], pagination['pages'])

    all_categories = sorted({d.get('product_category') for p in Product.query.with_entities(Product.xml_data).all() if p.xml_data and (d := json.loads(p.xml_data)) and d.get('product_category')})

    return render_template('index.html', products=paginated_products, pagination=pagination, pagination_args={k: v for k, v in request.args.items() if k != 'page'},
                           search_sku=search_sku, search_name=search_name, stock_filter=stock_filter, stock_quantity=stock_quantity,
                           printers_json=json.dumps([p.to_dict() for p in Printer.query.all()]), categories=all_categories, search_category=search_category,
                           param_filters=param_filters, color_settings=[s.to_dict() for s in ColorSetting.query.order_by(ColorSetting.id).all()], stock_level_filter=stock_level_filter)


@current_app.route('/get-params-for-category')
def get_params_for_category():
    # ... (код без змін) ...
    category_name = request.args.get('category')
    if not category_name: return jsonify({})
    products_in_cat = Product.query.filter(Product.xml_data.like(f'%"product_category": "{category_name.replace("\"", "\"\"")}"%')).all()
    params = {}
    for product in products_in_cat:
        if product.xml_data:
            try:
                product_params = json.loads(product.xml_data).get('product_params', {})
                for name, value in product_params.items():
                    if value:
                        params.setdefault(name, set()).add(value)
            except (json.JSONDecodeError, AttributeError):
                continue
    return jsonify({name: sorted(list(values), key=natural_sort_key) for name, values in params.items()})


@current_app.route('/get-test-product-info')
def get_test_product_info():
    # ... (код без змін) ...
    test_sku = 'M3*10-ISO7380-1-12.9'
    product = Product.query.filter_by(sku=test_sku).first() or Product.query.first()
    if not product:
        return jsonify({'error': 'В базі даних немає жодного товару для тесту.'}), 404
    if product.sku != test_sku:
        flash(f'Увага: Тестовий товар {test_sku} не знайдено. Використовується {product.sku}.', 'warning')
    return jsonify({'product_id': product.id, 'product_name': product.name, 'product_sku': product.sku})


@current_app.route('/update-minimum-stock', methods=['POST'])
def update_minimum_stock():
    # ... (код без змін) ...
    product_id = request.form.get('product_id')
    product = Product.query.get(product_id)
    if product:
        min_stock_str = request.form.get('minimum_stock')
        product.minimum_stock = int(min_stock_str) if min_stock_str and min_stock_str.isdigit() else None
        db.session.commit()
    return redirect(request.referrer or url_for('index'))


@current_app.route('/add-in-transit-form/<int:product_id>')
def add_in_transit_form(product_id):
    # ... (код без змін) ...
    product = Product.query.get_or_404(product_id)
    return render_template('add_in_transit_form.html', product=product)


@current_app.route('/add-in-transit', methods=['POST'])
def add_in_transit():
    # ... (код без змін) ...
    product_id = request.form.get('product_id')
    quantity = request.form.get('quantity')
    product = Product.query.get(product_id)

    if not product or not quantity.isdigit() or int(quantity) <= 0:
        flash("Помилка: Некоректні дані.", "danger")
        return redirect(url_for('index'))

    product.in_transit_quantity += int(quantity)

    arrival_date_str = request.form.get('arrival_date')
    arrival_date = datetime.strptime(arrival_date_str, '%Y-%m-%d').date() if arrival_date_str else None

    new_order = InTransitOrder(
        product_id=product.id,
        quantity=int(quantity),
        order_number=request.form.get('order_number'),
        arrival_date=arrival_date
    )
    db.session.add(new_order)
    db.session.commit()
    flash(f"Додано {quantity} од. товару '{product.name}' в дорозі.", "success")
    return redirect(request.referrer or url_for('index'))


@current_app.route('/settings', methods=['GET', 'POST'])
def settings():
    # ... (код без змін, він вже оновлений) ...
    if request.method == 'POST':
        if 'name' in request.form and 'ip_address' in request.form:
             if 'is_default' in request.form:
                 Printer.query.update({Printer.is_default: False})
             new_printer = Printer(
                 name=request.form.get('name'),
                 ip_address=request.form.get('ip_address'),
                 port=int(request.form.get('port')),
                 label_size=request.form.get('label_size'),
                 is_default='is_default' in request.form,
                 is_for_sorting='is_for_sorting' in request.form
             )
             db.session.add(new_printer)
             flash("Принтер успішно додано.", "success")
        else:
            for key, value in request.form.items():
                if key.startswith('bg_'):
                    level_name = key[3:]
                    setting = ColorSetting.query.filter_by(level_name=level_name).first()
                    if setting:
                        setting.background_color = value
                        setting.text_color = request.form.get(f'text_{level_name}')
            flash("Налаштування кольорів оновлено.", "success")

        db.session.commit()
        return redirect(url_for('settings'))

    job_counts = dict(db.session.query(PrintJob.printer_id, func.count(PrintJob.id)).group_by(PrintJob.printer_id).all())
    printers = Printer.query.order_by(Printer.name).all()
    for printer in printers:
        printer.job_count = job_counts.get(printer.id, 0)

    color_settings = ColorSetting.query.order_by(ColorSetting.id).all()
    return render_template('settings.html', printers=printers, color_settings=color_settings)


@current_app.route('/settings/printers/delete/<int:id>', methods=['POST'])
def delete_printer(id):
    # ... (код без змін) ...
    printer_to_delete = Printer.query.get_or_404(id)
    db.session.delete(printer_to_delete)
    db.session.commit()
    flash("Принтер видалено.", "success")
    return redirect(url_for('settings'))


@current_app.route('/settings/printers/edit/<int:id>', methods=['GET', 'POST'])
def edit_printer(id):
    # ... (код без змін) ...
    printer = Printer.query.get_or_404(id)
    if request.method == 'POST':
        if 'is_default' in request.form and not printer.is_default:
            Printer.query.filter(Printer.id != id).update({Printer.is_default: False})

        printer.name = request.form.get('name')
        printer.ip_address = request.form.get('ip_address')
        printer.port = int(request.form.get('port'))
        printer.label_size = request.form.get('label_size')
        printer.pause_between_jobs = int(request.form.get('pause_between_jobs', 1))
        printer.is_default = 'is_default' in request.form
        printer.is_for_sorting = 'is_for_sorting' in request.form
        printer.zpl_code_template = request.form.get('zpl_code_template')

        db.session.commit()
        flash("Налаштування принтера оновлено.", "success")
        return redirect(url_for('settings'))

    placeholders = get_all_placeholders()
    default_template = printer.zpl_code_template or get_default_template_for_size(printer.is_for_sorting)
    return render_template('edit_printer.html', printer=printer, placeholders=placeholders, default_template=default_template)


@current_app.route('/execute-print', methods=['POST'])
def execute_print():
    """ОНОВЛЕНО: Створює одне завдання з потрібною кількістю."""
    try:
        product_id = request.form.get('product_id')
        printer_id = request.form.get('printer_id')
        quantity = int(request.form.get('quantity', 1))
        sorting_quantity = request.form.get('sorting_quantity')

        product = Product.query.get(product_id)
        printer = Printer.query.get(printer_id)
        
        if not product or not printer:
            return jsonify({'status': 'error', 'message': 'Товар або принтер не знайдено!'}), 404

        # Передаємо кількість у генератор коду
        zpl_code = generate_zpl_code(printer, product, sorting_quantity, quantity)
        
        # Створюємо лише одне завдання
        new_job = PrintJob(printer_id=printer.id, zpl_code=zpl_code)
        db.session.add(new_job)
        db.session.commit()
        
        message = f"Додано завдання ({quantity} шт.) до черги для принтера '{printer.name}'."
        return jsonify({'status': 'success', 'message': message})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Помилка: {e}'}), 500

@current_app.route('/settings/clear-print-queue/<int:printer_id>', methods=['POST'])
def clear_print_queue(printer_id):
    """Видаляє всі завдання з черги для конкретного принтера."""
    try:
        printer_name = Printer.query.get(printer_id).name
        num_deleted = PrintJob.query.filter_by(printer_id=printer_id).delete()
        db.session.commit()
        flash(f"Чергу для принтера '{printer_name}' очищено. Видалено завдань: {num_deleted}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Помилка під час очищення черги: {e}", "danger")
    return redirect(url_for('settings'))

# --- ПОВЕРТАЄМО МАРШРУТ ---
@current_app.route('/settings/check-printer-status/<int:printer_id>')
def check_printer_status_route(printer_id):
    """AJAX-ендпоінт для перевірки статусу конкретного принтера."""
    printer = Printer.query.get_or_404(printer_id)
    is_ready, message = check_printer_status(printer.ip_address, printer.port)
    return jsonify({'is_ready': is_ready, 'message': message})