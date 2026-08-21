import os
from flask import Flask, request, send_from_directory
from app.config import Config
from app.extensions import db, jwt, cors, scheduler
from app.cron.daily_reset import reset_daily_quests

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure uploads directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'receipts'), exist_ok=True)

    # Initialize Extensions
    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/*": {"origins": "*"}})

    # Auto sync schema changes and seed default accounts
    from app.services.db_migrator import auto_sync_schema
    from app.services.db_seeder import seed_default_users
    auto_sync_schema(app)
    seed_default_users(app)

    # Setup global API Auth middleware
    from app.middleware.auth import setup_auth_middleware
    setup_auth_middleware(app)

    # Tutup buku ditegakkan di banyak jalur tulis. Diterjemahkan sekali di sini
    # supaya tiap endpoint cukup memanggil assert_period_open() tanpa try/except
    # sendiri-sendiri -- yang mudah terlupa di endpoint berikutnya.
    from app.services.period_lock import PeriodLockedError

    @app.errorhandler(PeriodLockedError)
    def _handle_period_locked(e):
        from flask import jsonify
        db.session.rollback()
        return jsonify({
            'error': str(e),
            'lockDate': e.lock_date.isoformat(),
            'businessDate': e.business_date.isoformat(),
        }), 423   # Locked

    @app.context_processor
    def inject_store_profile():
        """
        Store identity for the shell (sidebar brand, <title>). Rendered server-side on
        purpose: filling it from getStoreSettings() in JS would flash the placeholder
        name on every page load, and <title> cannot wait for JS at all.
        """
        defaults = {'store_name': 'Arunika-POS', 'store_tagline': 'Every Cup Has A Story'}
        try:
            from app.models.system_settings import SystemSettings
            rows = SystemSettings.query.filter(
                SystemSettings.key.in_(['STORE_NAME', 'TAGLINE'])
            ).all()
            found = {r.key: (r.value or '').strip() for r in rows}
            if found.get('STORE_NAME'):
                defaults['store_name'] = found['STORE_NAME']
            if found.get('TAGLINE'):
                defaults['store_tagline'] = found['TAGLINE']
        except Exception as e:
            # A missing table or a cold DB must never take the whole page down
            print(f"[StoreProfile] Falling back to defaults: {e}")
        return defaults

    @app.url_defaults
    def _bust_static_cache(endpoint, values):
        """
        Tempelkan waktu ubah berkas ke URL aset statis, jadi /static/js/app.js
        jadi ...?v=1723800000. Tanpa ini browser menyajikan CSS/JS versi lama
        sampai pengguna hard-refresh, dan perbaikan tampilan terlihat seperti
        tidak berpengaruh sama sekali.
        """
        if endpoint != 'static' or 'filename' not in values:
            return
        try:
            path = os.path.join(app.static_folder, values['filename'])
            values['v'] = int(os.stat(path).st_mtime)
        except OSError:
            pass  # berkas hilang -- biarkan url_for jalan seperti biasa

    # URL aset sudah berversi (?v=mtime di _bust_static_cache), jadi isinya
    # tidak mungkin berubah tanpa URL-nya ikut berubah. Tanpa setelan ini Flask
    # mengirim "no-cache" dan browser bertanya ulang ke server untuk SETIAP
    # css/js pada SETIAP pindah halaman -- lewat Tailscale itu tiga sampai empat
    # perjalanan bolak-balik hanya untuk dijawab "tidak berubah".
    app.config.setdefault('SEND_FILE_MAX_AGE_DEFAULT', 31536000)  # 1 tahun

    @app.after_request
    def _pasang_cache_aset(response):
        if request.path.startswith('/static/') and response.status_code == 200:
            if request.args.get('v'):
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            else:
                # Tanpa ?v tidak ada jaminan; jangan disimpan lama.
                response.headers['Cache-Control'] = 'public, max-age=300'
        elif (response.headers.get('Content-Type') or '').startswith('text/html'):
            # Halaman HTML WAJIB divalidasi ulang tiap dibuka.
            #
            # Tanpa header ini responsnya tidak punya Cache-Control maupun ETag
            # sama sekali, dan WebView Android memakai "heuristic caching": ia
            # boleh memakai salinan lama tanpa bertanya ke server. Karena URL
            # css/js dibubuhi ?v=mtime dan aset itu disimpan setahun sebagai
            # immutable, halaman basi berarti SELURUHNYA basi: markup lama,
            # CSS lama, JS lama. Aplikasi kasir bisa berhari-hari menampilkan
            # versi sebelum pembaruan sementara servernya sudah benar.
            #
            # no-cache bukan berarti tidak disimpan, hanya wajib divalidasi
            # dulu. Kerangka halaman kecil, jadi ini tidak membatalkan
            # penghematan yang datang dari aset berversi.
            response.headers['Cache-Control'] = 'no-cache'
        return response

    # Kompresi. Ditulis sendiri, bukan menambah dependensi: aset teks di sini
    # menyusut 71-78% dengan gzip, dan itu langsung terasa di sambungan kasir.
    @app.after_request
    def _kompres(response):
        if 'gzip' not in (request.headers.get('Accept-Encoding') or '').lower():
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if response.headers.get('Content-Encoding'):
            return response
        jenis = (response.headers.get('Content-Type') or '').split(';')[0].strip()
        if jenis not in ('text/html', 'text/css', 'application/javascript',
                         'text/javascript', 'application/json', 'image/svg+xml',
                         'text/plain'):
            return response
        # Respons berkas statis dikirim mode passthrough. Justru inilah yang
        # paling perlu dikompresi (CSS/JS puluhan KB), jadi jangan dilewati --
        # cukup batasi ukurannya supaya tidak ada berkas raksasa yang ditarik
        # ke memori hanya untuk dikompres.
        if response.direct_passthrough:
            panjang = response.content_length or 0
            if panjang > 2_000_000:
                return response
            response.direct_passthrough = False

        isi = response.get_data()
        # Di bawah ~1 KB, ongkos header gzip lebih besar dari hematnya.
        if len(isi) < 1024:
            return response

        import gzip as _gzip
        response.set_data(_gzip.compress(isi, 6))
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = str(len(response.get_data()))
        response.headers.add('Vary', 'Accept-Encoding')
        return response

    # Static uploads handler for /uploads/<path:filename>
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/api/rewards', methods=['GET'])
    def get_rewards_alias():
        from app.models.reward import Reward
        from flask import jsonify
        rewards = Reward.query.filter_by(active=True).all()
        return jsonify([r.to_dict() for r in rewards])

    # Register Blueprints
    from app.routes import (
        auth_bp, category_bp, menu_bp, checkout_bp, customer_bp,
        analytics_bp, gamification_bp, inventory_bp, expenses_bp,
        settings_bp, shift_bp, attendance_bp, role_access_bp, recipe_bp, logs_bp,
        historical_bp, notifications_bp, bootstrap_bp,
        monitoring_bp, web_bp
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(category_bp)
    app.register_blueprint(menu_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(gamification_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(shift_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(role_access_bp)
    app.register_blueprint(recipe_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(historical_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(bootstrap_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(web_bp)

    # Schedule Cron Jobs if not in reload process
    if not scheduler.running and os.environ.get('WERKZEUG_RUN_MAIN') != 'false':
        scheduler.add_job(
            id='daily_reset_quests',
            func=reset_daily_quests,
            args=[app],
            trigger='cron',
            hour=0,
            minute=0
        )
        try:
            scheduler.start()
        except Exception as e:
            print(f"[Scheduler] Warning starting scheduler: {e}")

    return app
