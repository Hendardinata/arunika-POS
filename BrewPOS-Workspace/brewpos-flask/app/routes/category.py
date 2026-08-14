from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.category import Category

category_bp = Blueprint('category', __name__, url_prefix='/api/categories')

@category_bp.route('', methods=['GET'])
def get_categories():
    try:
        categories = Category.query.all()
        return jsonify([c.to_dict() for c in categories])
    except Exception as e:
        print(f"Error fetching categories: {e}")
        return jsonify({'error': 'Failed to fetch categories', 'details': str(e)}), 500

@category_bp.route('', methods=['POST'])
def create_category():
    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    try:
        category = Category(name=name)
        db.session.add(category)
        db.session.commit()
        return jsonify(category.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error creating category: {e}")
        return jsonify({'error': 'Failed to create category', 'details': str(e)}), 500
