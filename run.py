# run.py
from app import create_app
from app.initialization import init_app_data
from app.sync import sync_products_from_xml
from app.queue_worker import init_worker

app = create_app()
init_worker(app)

if __name__ == '__main__':
    init_app_data(app)
    
    with app.app_context():
        sync_products_from_xml() 
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)