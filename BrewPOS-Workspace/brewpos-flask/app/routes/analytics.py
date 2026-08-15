from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from sqlalchemy import func
from app.extensions import db
from app.models.transaction import Transaction, TransactionItem
from app.models.expense import Expense, ExpenseCategory
from app.models.customer import Customer
from app.models.menu import Menu
from app.models.inventory import InventoryItem, InventoryLog, DailyOpname
from app.models.shift import Shift

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

def _parse_date_filter():
    days = request.args.get('days')
    start_date_str = request.args.get('startDate')
    end_date_str = request.args.get('endDate')

    start_date = None
    end_date = None

    if start_date_str and end_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).replace(hour=23, minute=59, second=59, microsecond=999999)
        except Exception:
            pass
    elif days and days != 'all':
        try:
            days_int = int(days)
            now = datetime.utcnow()
            if days_int == 1:
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                start_date = (now - timedelta(days=days_int)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        except ValueError:
            pass

    return start_date, end_date, days


@analytics_bp.route('', methods=['GET'])
def get_analytics():
    try:
        start_date, end_date, days = _parse_date_filter()

        tx_query = Transaction.query.filter(Transaction.status == 'COMPLETED')
        exp_query = Expense.query

        if start_date:
            tx_query = tx_query.filter(Transaction.createdAt >= start_date)
            exp_query = exp_query.filter(Expense.date >= start_date)
        if end_date:
            tx_query = tx_query.filter(Transaction.createdAt <= end_date)
            exp_query = exp_query.filter(Expense.date <= end_date)

        transactions_with_items = tx_query.all()
        total_transactions = len(transactions_with_items)
        total_revenue = sum(t.totalAmount for t in transactions_with_items)

        expenses_list = exp_query.all()
        total_expenses = sum(e.amount for e in expenses_list)

        # Calculate HPP
        total_hpp = sum(
            sum((item.hpp or 0) * item.quantity for item in tx.items)
            for tx in transactions_with_items
        )

        net_profit = total_revenue - total_hpp - total_expenses
        total_customers = Customer.query.count()

        # Repeat customer rate
        multi_visit_customers = Customer.query.filter(Customer.xp > 100).count()
        repeat_rate = round((multi_visit_customers / total_customers * 100)) if total_customers > 0 else 0

        # Top 5 customers by XP
        top_customers = [c.to_dict() for c in Customer.query.order_by(Customer.xp.desc()).limit(5).all()]

        # Generate Time Series chart data
        sales_by_date = {}
        menu_popularity = {}

        num_days = 7
        if days == '1': num_days = 2
        elif days and days != 'all':
            try:
                num_days = max(2, int(days))
            except ValueError:
                pass

        now = datetime.utcnow()
        if days != 'all':
            for i in range(num_days - 1, -1, -1):
                d = now - timedelta(days=i)
                date_str = d.strftime('%d %b')
                sales_by_date[date_str] = 0

        for tx in transactions_with_items:
            date_str = tx.createdAt.strftime('%d %b') if tx.createdAt else 'Unknown'
            sales_by_date[date_str] = sales_by_date.get(date_str, 0) + tx.totalAmount

            for item in tx.items:
                menu_name = item.menu.name if item.menu else f"Menu #{item.menuId}"
                category_name = item.menu.category.name if item.menu and item.menu.category else 'Menu'
                price_val = item.price or (item.menu.price if item.menu else 0)

                if menu_name not in menu_popularity:
                    menu_popularity[menu_name] = {
                        'name': menu_name,
                        'category': category_name,
                        'price': price_val,
                        'count': 0,
                        'revenue': 0
                    }
                menu_popularity[menu_name]['count'] += item.quantity
                menu_popularity[menu_name]['revenue'] += (price_val * item.quantity)

        chart_data = [{'date': d, 'revenue': rev, 'total': rev} for d, rev in sales_by_date.items()]
        popular_menus = sorted(list(menu_popularity.values()), key=lambda x: x['count'], reverse=True)[:10]

        return jsonify({
            'totalRevenue': total_revenue,
            'totalExpenses': total_expenses,
            'totalHpp': total_hpp,
            'netProfit': net_profit,
            'totalOrders': total_transactions,
            'totalCustomers': total_customers,
            'repeatCustomerRate': repeat_rate,
            'topCustomers': top_customers,
            'chartData': chart_data,
            'dailySales': chart_data,
            'popularMenus': popular_menus
        })
    except Exception as e:
        print(f"Error fetching analytics: {e}")
        return jsonify({'error': 'Failed to fetch analytics', 'details': str(e)}), 500


@analytics_bp.route('/comprehensive-reports', methods=['GET'])
def get_comprehensive_reports():
    try:
        start_date, end_date, days = _parse_date_filter()

        # 1. SALES REPORT
        tx_query = Transaction.query.order_by(Transaction.createdAt.desc())
        if start_date: tx_query = tx_query.filter(Transaction.createdAt >= start_date)
        if end_date: tx_query = tx_query.filter(Transaction.createdAt <= end_date)
        all_tx = tx_query.all()

        completed_tx = [t for t in all_tx if t.status == 'COMPLETED']
        void_tx = [t for t in all_tx if t.status == 'VOID']

        total_gross = sum(t.subTotal + (t.discountAmount or 0) for t in completed_tx)
        total_discounts = sum((t.discountAmount or 0) + sum((it.discountAmount or 0) * it.quantity for it in t.items) for t in completed_tx)
        total_tax = sum(t.taxAmount for t in completed_tx)
        total_parking = sum(t.parkingFee for t in completed_tx)
        total_net_sales = sum(t.totalAmount for t in completed_tx)
        total_void_amount = sum(t.totalAmount for t in void_tx)

        # Payment Methods breakdown
        by_payment = {}
        for t in completed_tx:
            m = t.paymentMethod or 'CASH'
            by_payment[m] = by_payment.get(m, 0) + t.totalAmount

        # 2. COGS / HPP & MENU PROFITABILITY
        menus = Menu.query.all()
        menu_sales_map = {}
        for t in completed_tx:
            for it in t.items:
                m_id = it.menuId
                if m_id not in menu_sales_map:
                    menu_sales_map[m_id] = {'soldQty': 0, 'revenue': 0, 'actualHpp': 0}
                menu_sales_map[m_id]['soldQty'] += it.quantity
                menu_sales_map[m_id]['revenue'] += (it.price * it.quantity)
                menu_sales_map[m_id]['actualHpp'] += ((it.hpp or 0) * it.quantity)

        cogs_list = []
        total_all_hpp = 0
        for m in menus:
            stats = menu_sales_map.get(m.id, {'soldQty': 0, 'revenue': 0, 'actualHpp': 0})
            sold_qty = stats['soldQty']
            rev = stats['revenue']
            hpp_val = stats['actualHpp'] if stats['actualHpp'] > 0 else (m.hpp * sold_qty)
            profit = rev - hpp_val
            margin_pct = round((profit / rev * 100), 1) if rev > 0 else 0
            total_all_hpp += hpp_val

            cogs_list.append({
                'menuId': m.id,
                'name': m.name,
                'category': m.category.name if m.category else '-',
                'price': m.price,
                'unitHpp': m.hpp,
                'soldQty': sold_qty,
                'totalRevenue': rev,
                'totalHpp': hpp_val,
                'grossProfit': profit,
                'marginPct': margin_pct
            })

        cogs_list.sort(key=lambda x: x['totalRevenue'], reverse=True)

        # 3. PURCHASES & OPEX
        exp_query = Expense.query.order_by(Expense.date.desc())
        if start_date: exp_query = exp_query.filter(Expense.date >= start_date)
        if end_date: exp_query = exp_query.filter(Expense.date <= end_date)
        all_expenses = exp_query.all()

        total_opex = sum(e.amount for e in all_expenses)
        expenses_by_cat = {}
        for e in all_expenses:
            cat_name = e.category.name if e.category else 'Lain-lain'
            expenses_by_cat[cat_name] = expenses_by_cat.get(cat_name, 0) + e.amount

        # Inventory Restock Purchases (Stock IN logs)
        log_query = InventoryLog.query.filter_by(type='IN').order_by(InventoryLog.createdAt.desc())
        if start_date: log_query = log_query.filter(InventoryLog.createdAt >= start_date)
        if end_date: log_query = log_query.filter(InventoryLog.createdAt <= end_date)
        restock_logs = [l.to_dict() for l in log_query.limit(50).all()]

        # 4. INVENTORY VARIANCE & USAGE
        inv_items = InventoryItem.query.all()
        inv_variance_list = []
        for item in inv_items:
            cur_stock = item.stock or 0
            unit = item.unit
            inv_variance_list.append({
                'id': item.id,
                'name': item.name,
                'unit': unit,
                'currentStock': cur_stock,
                'minStock': getattr(item, 'minStock', 10.0) or 10.0,
                'isLowStock': cur_stock <= (getattr(item, 'minStock', 10.0) or 10.0)
            })

        # 5. PROFIT & LOSS (P&L) STATEMENT
        gross_profit = total_net_sales - total_all_hpp
        net_operating_profit = gross_profit - total_opex

        pnl_statement = {
            'netRevenue': total_net_sales,
            'totalCogs': total_all_hpp,
            'grossProfit': gross_profit,
            'grossMarginPct': round((gross_profit / total_net_sales * 100), 1) if total_net_sales > 0 else 0,
            'totalOpex': total_opex,
            'netOperatingProfit': net_operating_profit,
            'netMarginPct': round((net_operating_profit / total_net_sales * 100), 1) if total_net_sales > 0 else 0
        }

        return jsonify({
            'salesSummary': {
                'totalGross': total_gross,
                'totalDiscounts': total_discounts,
                'totalTax': total_tax,
                'totalParking': total_parking,
                'totalNet': total_net_sales,
                'totalOrders': len(completed_tx),
                'totalVoid': len(void_tx),
                'totalVoidAmount': total_void_amount,
                'byPaymentMethod': by_payment
            },
            'transactions': [t.to_dict(include_items=True, include_customer=True) for t in completed_tx],
            'voidTransactions': [t.to_dict(include_items=True, include_customer=True) for t in void_tx],
            'cogsReport': cogs_list,
            'purchasesReport': {
                'totalOpex': total_opex,
                'byCategory': expenses_by_cat,
                'expensesList': [e.to_dict() for e in all_expenses],
                'restockLogs': restock_logs
            },
            'inventoryVariance': inv_variance_list,
            'pnlStatement': pnl_statement
        })
    except Exception as e:
        print(f"Error fetching comprehensive reports: {e}")
        return jsonify({'error': 'Failed to generate comprehensive reports', 'details': str(e)}), 500


@analytics_bp.route('/export-excel', methods=['GET'])
def export_excel_report():
    """
    Generates and downloads a professionally formatted multi-sheet Excel (.xlsx) report workbook.
    """
    import io
    from flask import send_file
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    try:
        # Same filter as /comprehensive-reports so the workbook and the screen never disagree
        start_date, end_date, days_param = _parse_date_filter()
        days_param = days_param or 'all'
        now = datetime.utcnow()

        wb = openpyxl.Workbook()
        default_sheet = wb.active

        # Styling definitions
        primary_header_fill = PatternFill(start_color="6F4E37", end_color="6F4E37", fill_type="solid")
        danger_header_fill = PatternFill(start_color="B71C1C", end_color="B71C1C", fill_type="solid")
        summary_fill = PatternFill(start_color="F4EAE1", end_color="F4EAE1", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Segoe UI", size=14, bold=True, color="6F4E37")
        subtitle_font = Font(name="Segoe UI", size=9, italic=True, color="7F7F7F")
        bold_font = Font(name="Segoe UI", size=10, bold=True)
        regular_font = Font(name="Segoe UI", size=10)
        border_thin = Border(
            left=Side(style='thin', color='E0E0E0'),
            right=Side(style='thin', color='E0E0E0'),
            top=Side(style='thin', color='E0E0E0'),
            bottom=Side(style='thin', color='E0E0E0')
        )

        def style_header_row(ws, row_idx, max_col, fill=primary_header_fill):
            for col in range(1, max_col + 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.fill = fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        def auto_fit_columns(ws):
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or '')
                    if cell.row in [1, 2]:
                        continue
                    max_len = max(max_len, len(val_str))
                ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        # -------------------------------------------------------------
        # SHEET 1: RINGKASAN & LABA RUGI (P&L STATEMENT)
        # -------------------------------------------------------------
        ws_pnl = wb.create_sheet(title="1. Laba Rugi (P&L)")
        ws_pnl.cell(row=1, column=1, value="ARUNIKA COFFEE & LOUNGE").font = title_font
        ws_pnl.cell(row=2, column=1, value=f"LAPORAN LABA RUGI OPERASIONAL | Periode: {days_param.upper()} | Dicetak: {now.strftime('%d-%m-%Y %H:%M')}").font = subtitle_font

        tx_query = Transaction.query
        if start_date: tx_query = tx_query.filter(Transaction.createdAt >= start_date)
        if end_date: tx_query = tx_query.filter(Transaction.createdAt <= end_date)
        completed_tx = tx_query.filter_by(status='COMPLETED').order_by(Transaction.createdAt.desc()).all()
        void_tx = tx_query.filter_by(status='VOID').order_by(Transaction.createdAt.desc()).all()

        total_net_sales = sum(t.totalAmount for t in completed_tx)
        total_tax = sum(t.taxAmount or 0 for t in completed_tx)
        total_discounts = sum(t.discountAmount or 0 for t in completed_tx)

        menus = Menu.query.all()
        menu_sales_map = {}
        for t in completed_tx:
            for it in t.items:
                if it.menuId not in menu_sales_map:
                    menu_sales_map[it.menuId] = {'soldQty': 0, 'actualHpp': 0, 'revenue': 0}
                menu_sales_map[it.menuId]['soldQty'] += it.quantity
                menu_sales_map[it.menuId]['actualHpp'] += ((it.hpp or 0) * it.quantity)
                menu_sales_map[it.menuId]['revenue'] += (it.price * it.quantity)

        total_cogs = sum(
            stats['actualHpp'] if stats['actualHpp'] > 0 else (m.hpp * stats['soldQty'])
            for m in menus
            for stats in [menu_sales_map.get(m.id, {'soldQty': 0, 'actualHpp': 0})]
        )

        gross_profit = total_net_sales - total_cogs
        gross_margin_pct = round((gross_profit / total_net_sales * 100), 1) if total_net_sales > 0 else 0

        exp_query = Expense.query
        if start_date: exp_query = exp_query.filter(Expense.date >= start_date)
        if end_date: exp_query = exp_query.filter(Expense.date <= end_date)
        all_expenses = exp_query.order_by(Expense.date.desc()).all()
        total_opex = sum(e.amount for e in all_expenses)

        net_operating_profit = gross_profit - total_opex
        net_margin_pct = round((net_operating_profit / total_net_sales * 100), 1) if total_net_sales > 0 else 0

        pnl_rows = [
            ("1. Pendapatan Penjualan Bersih (Net Revenue)", total_net_sales, "100.0%"),
            ("2. Harga Pokok Penjualan / Modal Bahan (COGS)", -total_cogs, f"{round(total_cogs/total_net_sales*100, 1) if total_net_sales > 0 else 0}%"),
            ("= LABA KOTOR (GROSS PROFIT)", gross_profit, f"{gross_margin_pct}%"),
            ("3. Total Beban Biaya Operasional (OPEX)", -total_opex, f"{round(total_opex/total_net_sales*100, 1) if total_net_sales > 0 else 0}%"),
            ("= LABA BERSIH OPERASIONAL (NET PROFIT)", net_operating_profit, f"{net_margin_pct}%")
        ]

        ws_pnl.cell(row=4, column=1, value="Komponen Laporan Keuangan")
        ws_pnl.cell(row=4, column=2, value="Nominal (Rp)")
        ws_pnl.cell(row=4, column=3, value="Rasio Margin (%)")
        style_header_row(ws_pnl, 4, 3)

        for i, (item_name, amount, ratio) in enumerate(pnl_rows, start=5):
            c1 = ws_pnl.cell(row=i, column=1, value=item_name)
            c2 = ws_pnl.cell(row=i, column=2, value=amount)
            c3 = ws_pnl.cell(row=i, column=3, value=ratio)
            c2.number_format = '#,##0'
            c3.alignment = Alignment(horizontal="center")
            if "=" in item_name:
                c1.font = bold_font; c2.font = bold_font; c3.font = bold_font
                c1.fill = summary_fill; c2.fill = summary_fill; c3.fill = summary_fill
            else:
                c1.font = regular_font; c2.font = regular_font; c3.font = regular_font
            c1.border = border_thin; c2.border = border_thin; c3.border = border_thin

        auto_fit_columns(ws_pnl)

        # -------------------------------------------------------------
        # SHEET 2: PENJUALAN SAH (COMPLETED SALES ONLY)
        # -------------------------------------------------------------
        ws_sales = wb.create_sheet(title="2. Penjualan Sah")
        ws_sales.cell(row=1, column=1, value="ARUNIKA COFFEE & LOUNGE").font = title_font
        ws_sales.cell(row=2, column=1, value=f"RINCIAN TRANSAKSI PENJUALAN SAH (COMPLETED) | Total: {len(completed_tx)} Transaksi").font = subtitle_font

        headers_sales = ["Kode Transaksi", "Waktu", "Pelanggan", "Rincian Menu", "Subtotal (Rp)", "Diskon (Rp)", "PPN (Rp)", "Total Bayar (Rp)", "Metode", "Status"]
        for col_idx, h in enumerate(headers_sales, 1):
            ws_sales.cell(row=4, column=col_idx, value=h)
        style_header_row(ws_sales, 4, len(headers_sales))

        for row_idx, t in enumerate(completed_tx, start=5):
            items_str = ", ".join([f"{it.quantity}x {it.menu.name if it.menu else 'Menu'}" for it in t.items])
            cust_name = t.customer.nickname if t.customer else "Guest"
            date_str = t.createdAt.strftime('%Y-%m-%d %H:%M') if t.createdAt else ""
            tx_code = t.get_code()
            row_data = [
                tx_code, date_str, cust_name, items_str, t.subTotal, t.discountAmount or 0,
                t.taxAmount or 0, t.totalAmount, t.paymentMethod or "CASH", t.status
            ]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws_sales.cell(row=row_idx, column=col_idx, value=val)
                cell.font = regular_font
                cell.border = border_thin
                if col_idx in [5, 6, 7, 8]:
                    cell.number_format = '#,##0'

        auto_fit_columns(ws_sales)

        # -------------------------------------------------------------
        # SHEET 3: TRANSAKSI DIBATALKAN (VOID TRANSACTIONS)
        # -------------------------------------------------------------
        ws_void = wb.create_sheet(title="3. Transaksi Batal (VOID)")
        ws_void.cell(row=1, column=1, value="ARUNIKA COFFEE & LOUNGE").font = title_font
        ws_void.cell(row=2, column=1, value=f"DAFTAR TRANSAKSI DIBATALKAN (VOID) | Total: {len(void_tx)} Transaksi Dibatalkan").font = subtitle_font

        headers_void = ["Kode Transaksi", "Waktu Order", "Waktu Void", "Pelanggan", "Rincian Menu", "Total Batal (Rp)", "Metode", "Alasan Void", "Petugas Void"]
        for col_idx, h in enumerate(headers_void, 1):
            ws_void.cell(row=4, column=col_idx, value=h)
        style_header_row(ws_void, 4, len(headers_void), fill=danger_header_fill)

        for row_idx, t in enumerate(void_tx, start=5):
            items_str = ", ".join([f"{it.quantity}x {it.menu.name if it.menu else 'Menu'}" for it in t.items])
            cust_name = t.customer.nickname if t.customer else "Guest"
            date_str = t.createdAt.strftime('%Y-%m-%d %H:%M') if t.createdAt else ""
            void_date_str = t.voidedAt.strftime('%Y-%m-%d %H:%M') if getattr(t, 'voidedAt', None) else "-"
            tx_code = t.get_code()
            voided_by_user = t.voidedByUser.username if getattr(t, 'voidedByUser', None) else (str(t.voidedBy) if t.voidedBy else "Staff")
            
            row_data = [
                tx_code, date_str, void_date_str, cust_name, items_str, t.totalAmount,
                t.paymentMethod or "CASH", t.voidReason or "Tanpa Keterangan", voided_by_user
            ]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws_void.cell(row=row_idx, column=col_idx, value=val)
                cell.font = regular_font
                cell.border = border_thin
                if col_idx == 6:
                    cell.number_format = '#,##0'

        auto_fit_columns(ws_void)

        # -------------------------------------------------------------
        # SHEET 4: HPP & MARGIN MENU (COGS)
        # -------------------------------------------------------------
        ws_cogs = wb.create_sheet(title="4. HPP & Margin Menu")
        ws_cogs.cell(row=1, column=1, value="ARUNIKA COFFEE & LOUNGE").font = title_font
        ws_cogs.cell(row=2, column=1, value="ANALISIS HPP, OMSET & PROFITABILITAS PER MENU").font = subtitle_font

        headers_cogs = ["ID Menu", "Nama Menu", "Kategori", "Harga Jual (Rp)", "Modal / Cup (HPP)", "Terjual (Cup)", "Total Omset (Rp)", "Total Modal (HPP)", "Laba Kotor (Rp)", "Margin (%)"]
        for col_idx, h in enumerate(headers_cogs, 1):
            ws_cogs.cell(row=4, column=col_idx, value=h)
        style_header_row(ws_cogs, 4, len(headers_cogs))

        for row_idx, m in enumerate(menus, start=5):
            stats = menu_sales_map.get(m.id, {'soldQty': 0, 'actualHpp': 0, 'revenue': 0})
            sold_qty = stats['soldQty']
            rev = stats['revenue']
            hpp_val = stats['actualHpp'] if stats['actualHpp'] > 0 else (m.hpp * sold_qty)
            profit = rev - hpp_val
            margin_pct = round((profit / rev * 100), 1) if rev > 0 else 0

            row_data = [
                m.id, m.name, m.category.name if m.category else "-", m.price, m.hpp,
                sold_qty, rev, hpp_val, profit, f"{margin_pct}%"
            ]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws_cogs.cell(row=row_idx, column=col_idx, value=val)
                cell.font = regular_font
                cell.border = border_thin
                if col_idx in [4, 5, 7, 8, 9]:
                    cell.number_format = '#,##0'

        auto_fit_columns(ws_cogs)

        # -------------------------------------------------------------
        # SHEET 5: PEMBELIAN & BIAYA (OPEX)
        # -------------------------------------------------------------
        ws_exp = wb.create_sheet(title="5. Biaya & Pembelian")
        ws_exp.cell(row=1, column=1, value="ARUNIKA COFFEE & LOUNGE").font = title_font
        ws_exp.cell(row=2, column=1, value="BIAYA OPERASIONAL & PEMBELIAN BAHAN BAKU").font = subtitle_font

        headers_exp = ["ID", "Tanggal", "Kategori Biaya", "Nominal Biaya (Rp)", "Keterangan / Keperluan", "Dicatat Oleh"]
        for col_idx, h in enumerate(headers_exp, 1):
            ws_exp.cell(row=4, column=col_idx, value=h)
        style_header_row(ws_exp, 4, len(headers_exp))

        for row_idx, e in enumerate(all_expenses, start=5):
            date_str = e.date.strftime('%Y-%m-%d') if e.date else ""
            cat_name = e.category.name if e.category else "-"
            user_name = e.recordedBy.username if e.recordedBy else "Staff"
            row_data = [e.id, date_str, cat_name, e.amount, e.notes or "-", user_name]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws_exp.cell(row=row_idx, column=col_idx, value=val)
                cell.font = regular_font
                cell.border = border_thin
                if col_idx == 4:
                    cell.number_format = '#,##0'

        auto_fit_columns(ws_exp)

        # -------------------------------------------------------------
        # SHEET 6: STOK BAHAN BAKU
        # -------------------------------------------------------------
        ws_inv = wb.create_sheet(title="6. Stok Bahan Baku")
        ws_inv.cell(row=1, column=1, value="ARUNIKA COFFEE & LOUNGE").font = title_font
        ws_inv.cell(row=2, column=1, value="STATUS & TINGKAT PERSEDIAAN BAHAN BAKU").font = subtitle_font

        headers_inv = ["ID", "Nama Bahan Baku", "Satuan", "Sisa Stok Fisik", "Harga Pokok Satuan (Rp)", "Batas Minimum", "Status Stok"]
        for col_idx, h in enumerate(headers_inv, 1):
            ws_inv.cell(row=4, column=col_idx, value=h)
        style_header_row(ws_inv, 4, len(headers_inv))

        inv_items = InventoryItem.query.all()
        for row_idx, it in enumerate(inv_items, start=5):
            stock_val = it.stock or 0
            min_val = getattr(it, 'minStock', 10.0) or 10.0
            cost_val = it.costPerUnit or 0
            status_str = "Habis" if stock_val <= 0 else ("Stok Menipis" if stock_val <= min_val else "Aman")

            row_data = [it.id, it.name, it.unit, stock_val, cost_val, min_val, status_str]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws_inv.cell(row=row_idx, column=col_idx, value=val)
                cell.font = regular_font
                cell.border = border_thin
                if col_idx in [5]:
                    cell.number_format = '#,##0'

        auto_fit_columns(ws_inv)

        # -------------------------------------------------------------
        # SHEET 6: REKAP SHIFT KASIR
        # -------------------------------------------------------------
        ws_shift = wb.create_sheet(title="6. Rekap Shift")
        ws_shift.cell(row=1, column=1, value="ARUNIKA COFFEE & LOUNGE").font = title_font
        ws_shift.cell(row=2, column=1, value="AUDIT & REKONSILIASI SHIFT KASIR").font = subtitle_font

        headers_shift = ["ID Shift", "Sesi Shift", "Nama Kasir", "Waktu Mulai", "Waktu Selesai", "Modal Awal (Rp)", "Ekspektasi Kas (Rp)", "Kas Fisik Akhir (Rp)", "Selisih Kas (Rp)", "Status"]
        for col_idx, h in enumerate(headers_shift, 1):
            ws_shift.cell(row=4, column=col_idx, value=h)
        style_header_row(ws_shift, 4, len(headers_shift))

        shifts = Shift.query.order_by(Shift.startTime.desc()).all()
        for row_idx, s in enumerate(shifts, start=5):
            start_str = s.startTime.strftime('%Y-%m-%d %H:%M') if s.startTime else ""
            end_str = s.endTime.strftime('%Y-%m-%d %H:%M') if s.endTime else "Aktif"
            cashier_name = s.user.username if s.user else "Kasir"
            diff = (s.endingCash - s.expectedEndingCash) if (s.endingCash is not None and s.expectedEndingCash is not None) else 0

            row_data = [
                s.id, s.type, cashier_name, start_str, end_str,
                s.startingCash, s.expectedEndingCash or 0, s.endingCash or 0, diff, s.status
            ]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws_shift.cell(row=row_idx, column=col_idx, value=val)
                cell.font = regular_font
                cell.border = border_thin
                if col_idx in [6, 7, 8, 9]:
                    cell.number_format = '#,##0'

        auto_fit_columns(ws_shift)

        if default_sheet in wb.worksheets:
            wb.remove(default_sheet)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"Laporan_Arunika_POS_{now.strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Error generating Excel report: {e}")
        return jsonify({'error': 'Failed to generate Excel report', 'details': str(e)}), 500


@analytics_bp.route('/reports', methods=['GET'])
def get_reports():
    return get_comprehensive_reports()
