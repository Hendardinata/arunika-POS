from flask import Blueprint, render_template, redirect, url_for

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    return render_template('dashboard.html', active_page='dashboard')

@web_bp.route('/login')
def login():
    return render_template('login.html', active_page='login')

@web_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@web_bp.route('/pos')
def pos():
    return render_template('pos.html', active_page='pos')

@web_bp.route('/menus')
def menus():
    return render_template('menus.html', active_page='menus')

@web_bp.route('/inventory')
def inventory():
    return render_template('inventory.html', active_page='inventory')

@web_bp.route('/customers')
def customers():
    return render_template('customers.html', active_page='customers')

@web_bp.route('/expenses')
def expenses():
    return render_template('expenses.html', active_page='expenses')

@web_bp.route('/reports')
def reports():
    return render_template('reports.html', active_page='reports')

@web_bp.route('/monitoring')
def monitoring():
    return render_template('monitoring.html', active_page='monitoring')

@web_bp.route('/settings')
def settings():
    return render_template('settings.html', active_page='settings')

@web_bp.route('/profile')
def profile():
    return render_template('profile.html', active_page='profile')
