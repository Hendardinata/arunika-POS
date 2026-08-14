import os
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from sqlalchemy import func
from app.extensions import db
from app.models.expense import Expense, ExpenseCategory
from app.services.system_logger import log_activity

expenses_bp = Blueprint('expenses', __name__, url_prefix='/api/expenses')

def _save_receipt_file(file):
    if not file or file.filename == '':
        return None
    filename = secure_filename(f"receipt_{int(time.time()*1000)}_{file.filename}")
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'receipts')
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)
    return f"/uploads/receipts/{filename}"


# --- CATEGORIES ---

@expenses_bp.route('/categories', methods=['GET'])
def get_expense_categories():
    try:
        categories = ExpenseCategory.query.all()
        if not categories:
            defaults = [
                ('Bahan Baku / Restok', 'Pembelian biji kopi, susu, sirup, dan kemasan'),
                ('Operasional Bar', 'Peralatan bar, sabun cuci, tisu, dan perlengkapan'),
                ('Gaji Staff', 'Gaji bulanan dan harian barista serta kasir'),
                ('Sewa Tempat', 'Biaya sewa outlet kafe'),
                ('Utilitas & Listrik', 'Tagihan listrik, air PDAM, dan internet wifi'),
                ('Lain-lain', 'Pengeluaran tak terduga lainnya')
            ]
            for name, desc in defaults:
                db.session.add(ExpenseCategory(name=name, description=desc))
            db.session.commit()
            categories = ExpenseCategory.query.all()
        return jsonify([c.to_dict() for c in categories])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch expense categories'}), 500

@expenses_bp.route('/categories', methods=['POST'])
def create_expense_category():
    data = request.get_json() or {}
    name = data.get('name')
    description = data.get('description')
    if not name:
        return jsonify({'error': 'Category name is required'}), 400

    try:
        category = ExpenseCategory(name=name, description=description)
        db.session.add(category)
        db.session.commit()
        return jsonify(category.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create expense category'}), 500


# --- EXPENSES ---

@expenses_bp.route('', methods=['GET'])
def get_expenses():
    try:
        days = request.args.get('days')
        start_date_str = request.args.get('startDate')
        end_date_str = request.args.get('endDate')

        query = Expense.query.order_by(Expense.date.desc())

        if start_date_str and end_date_str:
            start = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).replace(hour=0, minute=0, second=0)
            end = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).replace(hour=23, minute=59, second=59)
            query = query.filter(Expense.date >= start, Expense.date <= end)
        elif days and days != 'all':
            try:
                days_int = int(days)
                now = datetime.utcnow()
                if days_int == 1:
                    start = now.replace(hour=0, minute=0, second=0)
                else:
                    start = (now - timedelta(days=days_int)).replace(hour=0, minute=0, second=0)
                query = query.filter(Expense.date >= start)
            except ValueError:
                pass

        expenses = query.all()
        return jsonify([e.to_dict() for e in expenses])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch expenses'}), 500


@expenses_bp.route('/summary', methods=['GET'])
def get_expenses_summary():
    try:
        total = db.session.query(func.sum(Expense.amount)).scalar() or 0

        # Group by category
        grouped = db.session.query(
            Expense.categoryId,
            func.sum(Expense.amount).label('total_amount')
        ).group_by(Expense.categoryId).all()

        category_group = [{'categoryId': g[0], '_sum': {'amount': int(g[1] or 0)}} for g in grouped]

        return jsonify({
            'totalExpenses': int(total),
            'categoryGroup': category_group
        })
    except Exception as e:
        return jsonify({'error': 'Failed to fetch expense summary'}), 500


@expenses_bp.route('', methods=['POST'])
def create_expense():
    try:
        if request.is_json:
            data = request.get_json() or {}
            amount = int(data.get('amount', 0))
            date_str = data.get('date')
            notes = data.get('notes')
            category_id = int(data.get('categoryId', 0))
            user_id = int(data.get('userId', 0))
            receipt_url = data.get('receiptUrl')
        else:
            amount = int(request.form.get('amount', 0))
            date_str = request.form.get('date')
            notes = request.form.get('notes')
            category_id = int(request.form.get('categoryId', 0))
            user_id = int(request.form.get('userId', 0))
            receipt_url = request.form.get('receiptUrl')
            if 'receipt' in request.files:
                receipt_url = _save_receipt_file(request.files['receipt'])

        date_val = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if date_str else datetime.utcnow()

        expense = Expense(
            amount=amount,
            date=date_val,
            notes=notes,
            categoryId=category_id,
            userId=user_id,
            receiptUrl=receipt_url
        )
        db.session.add(expense)
        db.session.commit()

        return jsonify(expense.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error creating expense: {e}")
        return jsonify({'error': 'Failed to create expense', 'details': str(e)}), 500


@expenses_bp.route('/seed-categories', methods=['POST'])
def seed_categories():
    try:
        default_categories = ['Bahan Baku', 'Operasional', 'Gaji', 'Sewa', 'Lain-lain']
        created = []
        for name in default_categories:
            existing = ExpenseCategory.query.filter_by(name=name).first()
            if not existing:
                cat = ExpenseCategory(name=name)
                db.session.add(cat)
                created.append(cat)
        db.session.commit()
        return jsonify({'message': 'Seeded default categories', 'created': [c.to_dict() for c in created]})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to seed categories'}), 500
