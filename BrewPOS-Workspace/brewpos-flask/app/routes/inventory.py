import os
import time
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app.middleware.auth import get_current_user_id
from werkzeug.utils import secure_filename
from sqlalchemy import func
from app.extensions import db
from app.models.inventory import InventoryItem, InventoryLog, DailyOpname, DailyOpnameItem
from app.services.system_logger import log_activity
from app.services.period_lock import assert_period_open, PeriodLockedError

inventory_bp = Blueprint('inventory', __name__, url_prefix='/api/inventory')

def _save_upload_file(file, prefix='inv'):
    if not file or file.filename == '':
        return None
    filename = secure_filename(f"{prefix}_{int(time.time()*1000)}_{file.filename}")
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)
    return f"/uploads/{filename}"


def _recalc_hpp_for_item(item_id):
    """
    Harga bahan berubah -> modal setiap menu yang memakainya ikut berubah.
    Dipanggil dari pembelian, produksi, dan koreksi harga manual, supaya HPP
    tidak pernah tertinggal di angka lama.
    """
    from app.models.menu import Menu, RecipeIngredient
    affected = RecipeIngredient.query.filter_by(inventoryItemId=item_id).all()
    for r in affected:
        m = Menu.query.get(r.menuId)
        if m and m.recipeIngredients:
            calc = sum(int(round(ri.quantityNeeded * (ri.inventoryItem.costPerUnit or 0)))
                       for ri in m.recipeIngredients)
            if calc > 0:
                m.hpp = calc


@inventory_bp.route('', methods=['GET'])
def get_inventory():
    try:
        query = InventoryItem.query
        if request.args.get('activeOnly') in ('1', 'true'):
            # MSSQL menolak "IS 1" yang dihasilkan is_(True); pakai perbandingan biasa.
            query = query.filter(InventoryItem.isActive == True)  # noqa: E712
        items = query.all()
        res = []
        for i in items:
            d = i.to_dict()
            d['minStock'] = getattr(i, 'minStock', 10.0) or 10.0
            res.append(d)
        return jsonify(res)
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        return jsonify({'error': 'Failed to fetch inventory', 'details': str(e)}), 500


@inventory_bp.route('', methods=['POST'])
def create_inventory_item():
    try:
        if request.is_json:
            data = request.get_json() or {}
            name = data.get('name')
            stock = float(data.get('stock', 0))
            min_stock = float(data.get('minStock', 10))
            unit = data.get('unit', 'pcs')
            image_url = data.get('imageUrl')
            cost_per_unit = data.get('costPerUnit')
        else:
            name = request.form.get('name')
            stock = float(request.form.get('stock', 0))
            min_stock = float(request.form.get('minStock', 10))
            unit = request.form.get('unit', 'pcs')
            image_url = request.form.get('imageUrl')
            cost_per_unit = request.form.get('costPerUnit')
            if 'image' in request.files:
                image_url = _save_upload_file(request.files['image'], 'inventory')

        if not name:
            return jsonify({'error': 'Item name is required'}), 400

        item = InventoryItem(
            name=name,
            stock=stock,
            unit=unit or 'pcs',
            imageUrl=image_url
        )
        # Harga boleh dikosongkan dulu -- bahan tetap tercatat dengan harga 0 dan
        # bisa diisi belakangan lewat form Edit Bahan atau lewat Pembelian.
        if cost_per_unit not in (None, ''):
            item.costPerUnit = float(cost_per_unit)
        if hasattr(item, 'minStock'):
            item.minStock = min_stock
        db.session.add(item)
        db.session.flush()

        if item.stock > 0:
            log = InventoryLog(
                itemId=item.id,
                quantity=item.stock,
                type='IN',
                notes='Initial stock'
            )
            db.session.add(log)

        db.session.commit()

        user_id = get_current_user_id()
        log_activity('CREATE_INVENTORY', int(user_id) if user_id else None,
                     f"Added new item: {name}", 'InventoryItem', item.id)

        d = item.to_dict()
        d['minStock'] = min_stock
        return jsonify(d), 201
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create inventory item', 'details': str(e)}), 500


@inventory_bp.route('/<int:id>', methods=['PUT'])
def update_inventory_item(id):
    try:
        item = InventoryItem.query.get(id)
        if not item:
            return jsonify({'error': 'Item not found'}), 404

        if request.is_json:
            data = request.get_json() or {}
            if 'name' in data: item.name = data['name']
            if 'unit' in data: item.unit = data['unit']
            if 'imageUrl' in data: item.imageUrl = data['imageUrl']
            if 'minStock' in data and hasattr(item, 'minStock'):
                item.minStock = float(data['minStock'])
            if 'isActive' in data: item.isActive = bool(data['isActive'])
            cost_per_unit = data.get('costPerUnit')
        else:
            if 'name' in request.form: item.name = request.form['name']
            if 'unit' in request.form: item.unit = request.form['unit']
            if 'imageUrl' in request.form: item.imageUrl = request.form['imageUrl']
            if 'minStock' in request.form and hasattr(item, 'minStock'):
                item.minStock = float(request.form['minStock'])
            if 'image' in request.files:
                uploaded = _save_upload_file(request.files['image'], 'inventory')
                if uploaded: item.imageUrl = uploaded
            cost_per_unit = request.form.get('costPerUnit')

        # Koreksi harga beli menyusul. Form ini sempat mengirim costPerUnit tapi
        # tidak pernah dibaca di sini -- harga terlihat tersimpan padahal hilang.
        if cost_per_unit not in (None, ''):
            new_cost = float(cost_per_unit)
            if new_cost < 0:
                return jsonify({'error': 'Harga pokok tidak boleh negatif'}), 400
            if new_cost != (item.costPerUnit or 0.0):
                item.costPerUnit = new_cost
                _recalc_hpp_for_item(item.id)

        db.session.commit()
        d = item.to_dict()
        d['minStock'] = getattr(item, 'minStock', 10.0)
        return jsonify(d)
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update inventory item'}), 500


@inventory_bp.route('/<int:id>', methods=['DELETE'])
def delete_inventory_item(id):
    """
    Hapus bahan hanya kalau benar-benar belum meninggalkan jejak. Begitu ada
    mutasi stok, resep, atau opname, menghapusnya akan merusak riwayat HPP —
    arahkan ke arsip (isActive=false).
    """
    try:
        item = InventoryItem.query.get(id)
        if not item:
            return jsonify({'error': 'Bahan tidak ditemukan'}), 404

        from app.models.menu import RecipeIngredient
        recipe_count = RecipeIngredient.query.filter_by(inventoryItemId=id).count()
        log_count = InventoryLog.query.filter_by(itemId=id).count()
        opname_count = DailyOpnameItem.query.filter_by(inventoryItemId=id).count()

        if recipe_count or log_count or opname_count:
            reasons = []
            if recipe_count: reasons.append(f'dipakai di {recipe_count} resep menu')
            if log_count: reasons.append(f'punya {log_count} riwayat mutasi stok')
            if opname_count: reasons.append(f'tercatat di {opname_count} opname')
            return jsonify({
                'error': f'Bahan "{item.name}" ' + ', '.join(reasons) +
                         '. Menghapusnya akan merusak riwayat HPP. Arsipkan saja.',
                'canArchive': True,
                'itemId': item.id
            }), 400

        name = item.name
        db.session.delete(item)
        db.session.commit()

        user_id = get_current_user_id()
        log_activity('DELETE_INVENTORY', int(user_id) if user_id else None,
                     f"Menghapus bahan: {name}", 'InventoryItem', id)
        return '', 204
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting inventory item: {e}")
        return jsonify({'error': 'Gagal menghapus bahan'}), 500


@inventory_bp.route('/<int:id>/adjust', methods=['PUT'])
def adjust_inventory_stock(id):
    try:
        item = InventoryItem.query.get(id)
        if not item:
            return jsonify({'error': 'Item not found'}), 404

        if request.is_json:
            data = request.get_json() or {}
            qty = float(data.get('quantity', 0))
            adj_type = data.get('type')  # 'IN' or 'OUT'
            notes = data.get('notes')
            receipt_url = data.get('receiptUrl')
        else:
            qty = float(request.form.get('quantity', 0))
            adj_type = request.form.get('type')
            notes = request.form.get('notes')
            receipt_url = request.form.get('receiptUrl')
            if 'receipt' in request.files:
                receipt_url = _save_upload_file(request.files['receipt'], 'receipt')

        if qty <= 0 or adj_type not in ['IN', 'OUT']:
            return jsonify({'error': 'Invalid quantity or type'}), 400

        if adj_type == 'IN':
            item.stock = (item.stock or 0.0) + qty
        else:
            item.stock = (item.stock or 0.0) - qty

        log = InventoryLog(
            itemId=id,
            quantity=qty,
            type=adj_type,
            notes=notes,
            receiptUrl=receipt_url
        )
        db.session.add(log)
        db.session.commit()

        user_id = get_current_user_id()
        log_activity('UPDATE_INVENTORY', int(user_id) if user_id else None,
                     f"Adjusted stock {adj_type} {qty} for {item.name}", 'InventoryItem', item.id)

        d = item.to_dict()
        d['minStock'] = getattr(item, 'minStock', 10.0)
        return jsonify(d)
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to adjust inventory stock', 'details': str(e)}), 500


@inventory_bp.route('/purchase', methods=['POST'])
def purchase_material():
    """
    Record material purchase / restock with purchase cost, auto-calculates costPerUnit,
    syncs to store expenses, and auto-recalculates menu HPP!
    """
    try:
        if request.is_json:
            data = request.get_json() or {}
            item_id = int(data.get('itemId'))
            quantity = float(data.get('quantity', 0))
            total_cost = float(data.get('totalCost', 0))
            supplier = data.get('supplier')
            notes = data.get('notes')
            purchase_date_str = data.get('date')
            sync_expense = data.get('syncExpense', True)
            recalc_hpp = data.get('recalcHpp', True)
            receipt_url = data.get('receiptUrl')
        else:
            item_id = int(request.form.get('itemId'))
            quantity = float(request.form.get('quantity', 0))
            total_cost = float(request.form.get('totalCost', 0))
            supplier = request.form.get('supplier')
            notes = request.form.get('notes')
            purchase_date_str = request.form.get('date')
            sync_expense = request.form.get('syncExpense', 'true').lower() == 'true'
            recalc_hpp = request.form.get('recalcHpp', 'true').lower() == 'true'
            receipt_url = request.form.get('receiptUrl')
            if 'receipt' in request.files:
                receipt_url = _save_upload_file(request.files['receipt'], 'purchase')

        if quantity <= 0 or total_cost < 0:
            return jsonify({'error': 'Jumlah dan total biaya harus valid'}), 400

        item = InventoryItem.query.get(item_id)
        if not item:
            return jsonify({'error': 'Bahan baku tidak ditemukan'}), 404

        unit_cost = round(total_cost / quantity, 2) if quantity > 0 else 0.0

        # Tanggal pembelian dipakai baris pengeluaran DAN mutasi stok. Dulu cuma
        # pengeluarannya yang mundur, sementara mutasi stok tetap bertanggal hari
        # ini -- satu pembelian muncul di dua tanggal berbeda di dua laporan, dan
        # riwayat stok tidak bisa dicocokkan dengan nota fisiknya.
        purchase_date = datetime.utcnow()
        if purchase_date_str:
            try:
                purchase_date = datetime.fromisoformat(purchase_date_str)
            except ValueError:
                pass    # tanggal tidak terbaca: pakai hari ini, jangan gagalkan pembelian
        assert_period_open(purchase_date)

        # Update item stock & cost
        item.stock = (item.stock or 0.0) + quantity
        item.costPerUnit = unit_cost

        # Log purchase
        log = InventoryLog(
            itemId=item.id,
            quantity=quantity,
            type='IN',
            totalCost=total_cost,
            costPerUnit=unit_cost,
            supplier=supplier,
            notes=notes or f"Pembelian dari {supplier or 'Supplier'}",
            receiptUrl=receipt_url,
            createdAt=purchase_date
        )
        db.session.add(log)

        # Sync to Expense if enabled
        if sync_expense and total_cost > 0:
            from app.models.expense import Expense, ExpenseCategory
            from app.models.user import User
            cat = ExpenseCategory.query.filter(ExpenseCategory.name.like('%Bahan%')).first()
            if not cat:
                cat = ExpenseCategory.query.first()
            user_id = get_current_user_id()
            admin_user = User.query.first()
            exp_user_id = int(user_id) if user_id else (admin_user.id if admin_user else 1)

            expense = Expense(
                amount=int(total_cost),
                date=purchase_date,
                notes=f"Pembelian {quantity} {item.unit} {item.name}" + (f" ({supplier})" if supplier else ""),
                categoryId=cat.id if cat else 1,
                userId=exp_user_id,
                receiptUrl=receipt_url
            )
            db.session.add(expense)

        # Recalculate Menu HPP for all menus using this ingredient
        if recalc_hpp:
            _recalc_hpp_for_item(item.id)

        db.session.commit()

        user_id = get_current_user_id()
        log_activity('PURCHASE_MATERIAL', int(user_id) if user_id else None,
                     f"Purchased {quantity} {item.unit} {item.name} for Rp {int(total_cost):,}".replace(',', '.'),
                     'InventoryItem', item.id)

        return jsonify({
            'message': 'Pembelian bahan berhasil dicatat!',
            'item': item.to_dict(),
            'unitCost': unit_cost,
            'totalCost': total_cost
        }), 201
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal mencatat pembelian', 'details': str(e)}), 500


@inventory_bp.route('/production', methods=['POST'])
def produce_material():
    """
    Olah bahan jadi bahan setengah jadi. Contoh nyatanya: 60 g bubuk kopi
    diseduh mokapot jadi 300 ml Base Espresso.

    Gunanya supaya barista tidak perlu menebak berapa gram kopi yang jatuh ke
    tiap cup. Cukup ukur sekali per batch, sisanya sistem yang hitung: stok
    bahan mentah berkurang, stok hasil bertambah, dan harga per ml hasil
    diturunkan dari harga bahan yang dipakai.

    Harga hasil memakai rata-rata tertimbang, bukan batch terakhir -- base yang
    masih tersisa dari seduhan sebelumnya ikut diperhitungkan, jadi nilai stok
    tidak melompat setiap kali menyeduh dengan harga kopi yang berbeda.
    """
    try:
        data = request.get_json() or {}
        output_id = int(data.get('outputItemId') or 0)
        output_qty = float(data.get('outputQty') or 0)
        raw_inputs = data.get('inputs') or []
        notes = (data.get('notes') or '').strip()

        if output_qty <= 0:
            return jsonify({'error': 'Jumlah hasil produksi harus lebih dari 0'}), 400
        if not raw_inputs:
            return jsonify({'error': 'Bahan yang dipakai belum diisi'}), 400

        output = InventoryItem.query.get(output_id)
        if not output:
            return jsonify({'error': 'Bahan hasil tidak ditemukan'}), 404

        # Kumpulkan dulu, jangan ubah stok apa pun sebelum semuanya sah -- kalau
        # baris ketiga bermasalah, dua baris pertama tidak boleh terlanjur terpotong.
        parsed = []
        for row in raw_inputs:
            src = InventoryItem.query.get(int(row.get('itemId') or 0))
            if not src:
                return jsonify({'error': f"Bahan dengan id {row.get('itemId')} tidak ditemukan"}), 404
            if src.id == output.id:
                return jsonify({'error': 'Bahan hasil tidak boleh dipakai sebagai bahan masukan'}), 400
            qty = float(row.get('quantity') or 0)
            if qty <= 0:
                return jsonify({'error': f"Jumlah {src.name} harus lebih dari 0"}), 400
            parsed.append((src, qty))

        batch_label = notes or f"Produksi {output.name}"
        total_input_cost = 0.0
        warnings = []

        for src, qty in parsed:
            unit_cost = src.costPerUnit or 0.0
            line_cost = qty * unit_cost
            total_input_cost += line_cost

            src.stock = (src.stock or 0.0) - qty
            if src.stock < 0:
                warnings.append(f"Stok {src.name} jadi minus ({src.stock:g} {src.unit})")
            if unit_cost <= 0:
                warnings.append(f"{src.name} belum punya harga beli, modal hasil jadi terlalu murah")

            db.session.add(InventoryLog(
                itemId=src.id, quantity=qty, type='OUT',
                costPerUnit=unit_cost, totalCost=line_cost,
                notes=f"{batch_label}: dipakai untuk {output_qty:g} {output.unit} {output.name}"
            ))

        # Rata-rata tertimbang: nilai stok lama + nilai batch baru, dibagi stok total.
        prev_value = (output.stock or 0.0) * (output.costPerUnit or 0.0)
        output.stock = (output.stock or 0.0) + output_qty
        # 4 desimal, bukan 2: harga per ml sering di bawah Rp 1 dan pembulatan
        # ke rupiah penuh akan menghapusnya jadi nol.
        output.costPerUnit = round((prev_value + total_input_cost) / output.stock, 4) if output.stock > 0 else 0.0

        batch_unit_cost = round(total_input_cost / output_qty, 4)
        db.session.add(InventoryLog(
            itemId=output.id, quantity=output_qty, type='IN',
            costPerUnit=batch_unit_cost, totalCost=total_input_cost,
            notes=f"{batch_label}: dari " + ", ".join(f"{q:g} {s.unit} {s.name}" for s, q in parsed)
        ))

        # Biaya bahan sudah tercatat saat pembelian. Produksi cuma memindahkan
        # nilai antar bahan, jadi tidak ada Expense baru di sini -- kalau dicatat
        # lagi, modal terhitung dua kali.
        _recalc_hpp_for_item(output.id)
        db.session.commit()

        user_id = get_current_user_id()
        log_activity('PRODUCE_MATERIAL', int(user_id) if user_id else None,
                     f"Produksi {output_qty:g} {output.unit} {output.name} "
                     f"(modal Rp {int(total_input_cost):,})".replace(',', '.'),
                     'InventoryItem', output.id)

        return jsonify({
            'message': f"Produksi {output.name} berhasil dicatat",
            'item': output.to_dict(),
            'totalCost': round(total_input_cost, 2),
            'batchCostPerUnit': batch_unit_cost,
            'averageCostPerUnit': output.costPerUnit,
            'warnings': warnings
        }), 201
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal mencatat produksi', 'details': str(e)}), 500


@inventory_bp.route('/transactions', methods=['GET'])
@inventory_bp.route('/logs', methods=['GET'])
def get_inventory_transactions():
    try:
        logs = InventoryLog.query.order_by(InventoryLog.createdAt.desc()).limit(100).all()
        res = []
        for l in logs:
            item_name = l.item.name if l.item else f"Item #{l.itemId}"
            item_unit = l.item.unit if l.item else 'pcs'
            d = l.to_dict()
            d['itemName'] = item_name
            d['unit'] = item_unit
            res.append(d)
        return jsonify(res)
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        return jsonify({'error': 'Failed to fetch inventory transactions', 'details': str(e)}), 500


# --- OPNAME ---

@inventory_bp.route('/opname/today', methods=['GET'])
@inventory_bp.route('/opname/active', methods=['GET'])
def get_opname_today():
    try:
        opname = DailyOpname.query.filter_by(status='OPEN').order_by(DailyOpname.createdAt.desc()).first()
        if opname:
            # Dynamically compute addedStock since opname opened
            for op_item in opname.items:
                added_sum = db.session.query(func.sum(InventoryLog.quantity)).filter(
                    InventoryLog.itemId == op_item.inventoryItemId,
                    InventoryLog.type == 'IN',
                    InventoryLog.createdAt >= opname.createdAt
                ).scalar() or 0.0
                op_item.addedStock = added_sum

            return jsonify({
                'status': 'OPEN',
                'opname': opname.to_dict()
            })

        inventory = InventoryItem.query.all()
        return jsonify({
            'status': 'NOT_OPEN',
            'inventory': [i.to_dict() for i in inventory]
        })
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        return jsonify({'error': 'Failed to fetch opname status', 'details': str(e)}), 500


@inventory_bp.route('/opname/open', methods=['POST'])
def open_opname():
    data = request.get_json() or {}
    items_data = data.get('items', [])

    try:
        existing = DailyOpname.query.filter_by(status='OPEN').first()
        if existing:
            return jsonify({'error': 'Opname already open'}), 400

        opname = DailyOpname(
            status='OPEN',
            isStockConfirmed=False,
            date=datetime.utcnow()
        )
        db.session.add(opname)
        db.session.flush()

        for it in items_data:
            inv_id = it.get('inventoryItemId')
            opening_stock = float(it.get('openingStock', 0))
            morning_notes = it.get('morningNotes')

            op_item = DailyOpnameItem(
                opnameId=opname.id,
                inventoryItemId=inv_id,
                openingStock=opening_stock,
                morningNotes=morning_notes
            )
            db.session.add(op_item)

            inv_item = InventoryItem.query.get(inv_id)
            if inv_item:
                inv_item.stock = opening_stock

        db.session.commit()
        return jsonify(opname.to_dict()), 201
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to open opname', 'details': str(e)}), 500


@inventory_bp.route('/opname/confirm-stock', methods=['POST'])
def confirm_stock():
    try:
        opname = DailyOpname.query.filter_by(status='OPEN').first()
        if not opname:
            return jsonify({'error': 'No open opname found'}), 400

        opname.isStockConfirmed = True
        db.session.commit()
        return jsonify(opname.to_dict())
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to confirm stock'}), 500


@inventory_bp.route('/opname/cancel-confirm-stock', methods=['POST'])
def cancel_confirm_stock():
    try:
        opname = DailyOpname.query.filter_by(status='OPEN').first()
        if not opname:
            return jsonify({'error': 'No open opname found'}), 400

        opname.isStockConfirmed = False
        db.session.commit()
        return jsonify(opname.to_dict())
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to cancel confirm stock'}), 500


@inventory_bp.route('/opname/close', methods=['POST'])
def close_opname():
    data = request.get_json() or {}
    opname_id = data.get('opnameId')
    items_data = data.get('items', [])

    try:
        opname = DailyOpname.query.get(opname_id)
        if not opname or opname.status == 'CLOSED':
            return jsonify({'error': 'Invalid or already closed opname'}), 400

        for it in items_data:
            inv_id = it.get('inventoryItemId')
            closing_stock = float(it.get('closingStock', 0))
            night_notes = it.get('nightNotes')

            op_item = next((oi for oi in opname.items if oi.inventoryItemId == inv_id), None)
            if op_item:
                added_sum = db.session.query(func.sum(InventoryLog.quantity)).filter(
                    InventoryLog.itemId == inv_id,
                    InventoryLog.type == 'IN',
                    InventoryLog.createdAt >= opname.createdAt
                ).scalar() or 0.0

                used = (op_item.openingStock + added_sum) - closing_stock
                op_item.closingStock = closing_stock
                op_item.addedStock = added_sum
                op_item.used = used
                op_item.nightNotes = night_notes

                inv_item = InventoryItem.query.get(inv_id)
                if inv_item:
                    inv_item.stock = closing_stock

        opname.status = 'CLOSED'
        db.session.commit()
        return jsonify(opname.to_dict())
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to close opname', 'details': str(e)}), 500


@inventory_bp.route('/opname/history', methods=['GET'])
def get_opname_history():
    try:
        history = DailyOpname.query.filter_by(status='CLOSED').order_by(DailyOpname.createdAt.desc()).all()
        return jsonify([h.to_dict() for h in history])
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        return jsonify({'error': 'Failed to fetch opname history'}), 500
