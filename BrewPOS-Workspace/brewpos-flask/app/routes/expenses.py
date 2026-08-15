import os
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from sqlalchemy import func
from app.extensions import db
from app.models.expense import Expense, ExpenseCategory
from app.middleware.auth import get_current_user_id, is_supervisor
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

@expenses_bp.route('/categories/<int:id>', methods=['PUT'])
def update_expense_category(id):
    try:
        category = ExpenseCategory.query.get(id)
        if not category:
            return jsonify({'error': 'Kategori tidak ditemukan'}), 404

        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Nama kategori wajib diisi'}), 400

        clash = ExpenseCategory.query.filter(ExpenseCategory.name == name,
                                             ExpenseCategory.id != id).first()
        if clash:
            return jsonify({'error': f'Kategori "{name}" sudah ada'}), 409

        category.name = name
        if 'description' in data:
            category.description = data.get('description')
        db.session.commit()
        return jsonify(category.to_dict())
    except Exception as e:
        db.session.rollback()
        print(f"Error updating expense category: {e}")
        return jsonify({'error': 'Gagal memperbarui kategori'}), 500


@expenses_bp.route('/categories/<int:id>', methods=['DELETE'])
def delete_expense_category(id):
    """Kategori yang sudah dipakai tidak dihapus supaya rincian biaya lama tetap terbaca."""
    try:
        category = ExpenseCategory.query.get(id)
        if not category:
            return jsonify({'error': 'Kategori tidak ditemukan'}), 404

        used = Expense.query.filter_by(categoryId=id).count()
        if used:
            return jsonify({
                'error': f'Kategori "{category.name}" sudah dipakai {used} pengeluaran, '
                         'jadi tidak bisa dihapus. Ubah namanya saja bila perlu.'
            }), 400

        db.session.delete(category)
        db.session.commit()
        return '', 204
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting expense category: {e}")
        return jsonify({'error': 'Gagal menghapus kategori'}), 500


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


def _read_expense_payload():
    """Baca field dari JSON maupun FormData (halaman mengirim FormData karena ada foto nota)."""
    src = request.get_json() or {} if request.is_json else request.form
    receipt_url = src.get('receiptUrl')
    if not request.is_json and 'receipt' in request.files:
        uploaded = _save_receipt_file(request.files['receipt'])
        if uploaded:
            receipt_url = uploaded
    return {
        'amount': src.get('amount'),
        'date': src.get('date'),
        'notes': src.get('notes'),
        'categoryId': src.get('categoryId'),
        'paymentSource': src.get('paymentSource'),
        'receiptUrl': receipt_url,
    }


def _validate_expense(payload, partial=False):
    """Returns (cleaned, error). error = (message, status)."""
    cleaned = {}

    if payload.get('amount') is not None or not partial:
        try:
            amount = int(payload.get('amount') or 0)
        except (TypeError, ValueError):
            return None, ('Nominal pengeluaran harus berupa angka', 400)
        if amount <= 0:
            return None, ('Nominal pengeluaran harus lebih dari 0', 400)
        cleaned['amount'] = amount

    if payload.get('categoryId') is not None or not partial:
        try:
            category_id = int(payload.get('categoryId') or 0)
        except (TypeError, ValueError):
            return None, ('Kategori biaya tidak valid', 400)
        if not ExpenseCategory.query.get(category_id):
            return None, ('Kategori biaya tidak ditemukan', 400)
        cleaned['categoryId'] = category_id

    if payload.get('date'):
        try:
            cleaned['date'] = datetime.fromisoformat(str(payload['date']).replace('Z', '+00:00'))
        except ValueError:
            return None, ('Format tanggal tidak valid', 400)
    elif not partial:
        cleaned['date'] = datetime.utcnow()

    source = (payload.get('paymentSource') or '').upper()
    if source:
        if source not in ('CASH_DRAWER', 'OTHER'):
            return None, ('Sumber dana tidak dikenal', 400)
        cleaned['paymentSource'] = source
    elif not partial:
        cleaned['paymentSource'] = 'CASH_DRAWER'

    if 'notes' in payload:
        cleaned['notes'] = payload.get('notes')
    if payload.get('receiptUrl') is not None:
        cleaned['receiptUrl'] = payload.get('receiptUrl')

    return cleaned, None


@expenses_bp.route('', methods=['POST'])
def create_expense():
    try:
        # Pencatat diambil dari token, bukan dari payload. Sebelumnya userId dibaca
        # dari body; halaman tidak pernah mengirimnya sehingga selalu 0 dan setiap
        # pencatatan pengeluaran gagal karena melanggar foreign key.
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Sesi tidak valid, silakan login ulang'}), 401

        cleaned, err = _validate_expense(_read_expense_payload())
        if err:
            return jsonify({'error': err[0]}), err[1]

        expense = Expense(userId=int(user_id), **cleaned)

        # Pengeluaran tunai diikat ke sesi kas yang sedang terbuka supaya
        # rekonsiliasi laci ikut memperhitungkan uang yang keluar.
        if expense.paymentSource == 'CASH_DRAWER':
            from app.routes.checkout import _get_open_shift
            open_shift = _get_open_shift()
            if open_shift:
                expense.shiftId = open_shift.id

        db.session.add(expense)
        db.session.commit()

        log_activity('CREATE_EXPENSE', int(user_id),
                     f"Mencatat pengeluaran Rp {expense.amount:,}".replace(',', '.'),
                     'Expense', expense.id)

        return jsonify(expense.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error creating expense: {e}")
        return jsonify({'error': 'Gagal menyimpan pengeluaran', 'details': str(e)}), 500


@expenses_bp.route('/<int:id>', methods=['PUT'])
def update_expense(id):
    """Koreksi pengeluaran yang salah input (nominal, kategori, tanggal, catatan)."""
    try:
        expense = Expense.query.get(id)
        if not expense:
            return jsonify({'error': 'Pengeluaran tidak ditemukan'}), 404

        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Sesi tidak valid, silakan login ulang'}), 401

        cleaned, err = _validate_expense(_read_expense_payload(), partial=True)
        if err:
            return jsonify({'error': err[0]}), err[1]

        for field, value in cleaned.items():
            setattr(expense, field, value)

        db.session.commit()
        log_activity('UPDATE_EXPENSE', int(user_id),
                     f"Mengubah pengeluaran #{expense.id}", 'Expense', expense.id)
        return jsonify(expense.to_dict())
    except Exception as e:
        db.session.rollback()
        print(f"Error updating expense: {e}")
        return jsonify({'error': 'Gagal memperbarui pengeluaran'}), 500


@expenses_bp.route('/<int:id>', methods=['DELETE'])
def delete_expense(id):
    """Hapus catatan pengeluaran. Dibatasi HEADBAR ke atas karena mengubah laba rugi."""
    try:
        expense = Expense.query.get(id)
        if not expense:
            return jsonify({'error': 'Pengeluaran tidak ditemukan'}), 404

        if not is_supervisor():
            return jsonify({'error': 'Hanya Head Barista ke atas yang boleh menghapus pengeluaran'}), 403

        user_id = get_current_user_id()
        amount = expense.amount
        db.session.delete(expense)
        db.session.commit()

        log_activity('DELETE_EXPENSE', int(user_id) if user_id else None,
                     f"Menghapus pengeluaran Rp {amount:,}".replace(',', '.'), 'Expense', id)
        return '', 204
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting expense: {e}")
        return jsonify({'error': 'Gagal menghapus pengeluaran'}), 500


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
