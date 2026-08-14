import os
from flask import Flask, send_from_directory
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
        settings_bp, shift_bp, role_access_bp, recipe_bp, logs_bp,
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
    app.register_blueprint(role_access_bp)
    app.register_blueprint(recipe_bp)
    app.register_blueprint(logs_bp)
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
