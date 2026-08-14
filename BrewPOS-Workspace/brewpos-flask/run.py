import os
from app import create_app
from app.config import Config

app = create_app(Config)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3001))
    print(f"[SERVER] Arunika-POS Flask Server starting at http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
