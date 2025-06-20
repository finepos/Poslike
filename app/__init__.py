# app/__init__.py
from flask import Flask
from .config import Config
from .extensions import db, scheduler

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    
    app.config.from_object(Config)
    app.jinja_env.add_extension('jinja2.ext.do')
    
    db.init_app(app)
    scheduler.init_app(app)
    
    with app.app_context():
        from . import models
        from . import routes
        from .sync import sync_products_from_xml
        from .queue_worker import process_print_queue

        if not scheduler.get_job('sync_job'):
            scheduler.add_job(id='sync_job', func=sync_products_from_xml, trigger='interval', seconds=1800)
        
        if not scheduler.get_job('print_queue_job'):
            scheduler.add_job(id='print_queue_job', func=process_print_queue, trigger='interval', seconds=5)
        
        if scheduler.state != 1:
             scheduler.start()

    return app