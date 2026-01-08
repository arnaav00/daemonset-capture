#!/usr/bin/env python3
from flask import Flask, jsonify, request, abort
from datetime import datetime

app = Flask(__name__)

users_db = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com", "role": "admin", "status": "active"},
    2: {"id": 2, "name": "Bob", "email": "bob@example.com", "role": "user", "status": "active"},
    3: {"id": 3, "name": "Charlie", "email": "charlie@example.com", "role": "user", "status": "inactive"}
}

orders_db = {
    1: {"id": 1, "user_id": 1, "items": [{"product_id": 1, "quantity": 2}], "total": 1999.98, "status": "completed"},
    2: {"id": 2, "user_id": 1, "items": [{"product_id": 2, "quantity": 1}], "total": 29.99, "status": "pending"},
    3: {"id": 3, "user_id": 2, "items": [{"product_id": 3, "quantity": 1}], "total": 79.99, "status": "completed"}
}

products_db = {
    1: {"id": 1, "name": "Laptop", "price": 999.99, "stock": 10},
    2: {"id": 2, "name": "Mouse", "price": 29.99, "stock": 50},
    3: {"id": 3, "name": "Keyboard", "price": 79.99, "stock": 25}
}

@app.route('/')
def health():
    return jsonify({"status": "healthy", "service": "example-api", "timestamp": datetime.utcnow().isoformat() + "Z"})

@app.route('/api/v1/users', methods=['GET'])
def get_users():
    return jsonify({"users": list(users_db.values()), "count": len(users_db)})

@app.route('/api/v1/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    if user_id not in users_db:
        abort(404, description="User not found")
    return jsonify(users_db[user_id])

@app.route('/api/v1/users', methods=['POST'])
def create_user():
    data = request.get_json()
    if not data or 'name' not in data or 'email' not in data:
        abort(400, description="Name and email are required")
    new_id = max(users_db.keys()) + 1 if users_db else 1
    new_user = {
        "id": new_id, 
        "name": data["name"], 
        "email": data["email"],
        "role": data.get("role", "user"),
        "status": data.get("status", "active")
    }
    users_db[new_id] = new_user
    return jsonify(new_user), 201

@app.route('/api/v1/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    if user_id not in users_db:
        abort(404, description="User not found")
    data = request.get_json()
    if data:
        # Modified: Changed field name from 'name' to 'fullName' for testing updates
        if 'fullName' in data:
            data['name'] = data.pop('fullName')
        users_db[user_id].update(data)
    return jsonify(users_db[user_id])

@app.route('/api/v1/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    if user_id not in users_db:
        abort(404, description="User not found")
    deleted_user = users_db.pop(user_id)
    return jsonify({"message": "User deleted", "user": deleted_user}), 200

@app.route('/api/v1/products', methods=['GET'])
def get_products():
    return jsonify({"products": list(products_db.values()), "count": len(products_db)})

@app.route('/api/v1/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    if product_id not in products_db:
        abort(404, description="Product not found")
    return jsonify(products_db[product_id])

@app.route('/api/v1/products', methods=['POST'])
def create_product():
    data = request.get_json()
    if not data or 'name' not in data:
        abort(400, description="Name is required")
    new_id = max(products_db.keys()) + 1 if products_db else 1
    new_product = {"id": new_id, "name": data.get("name"), "price": data.get("price", 0.0), "stock": data.get("stock", 0)}
    products_db[new_id] = new_product
    return jsonify(new_product), 201

@app.route('/api/v1/search', methods=['GET'])
def search():
    query = request.args.get('q', '')
    if not query:
        abort(400, description="Query parameter 'q' is required")
    matching_users = [u for u in users_db.values() if query.lower() in u["name"].lower() or query.lower() in u["email"].lower()]
    matching_products = [p for p in products_db.values() if query.lower() in p["name"].lower()]
    return jsonify({"query": query, "users": matching_users, "products": matching_products, "total_results": len(matching_users) + len(matching_products)})

# New endpoint 1: PATCH for partial user updates
@app.route('/api/v1/users/<int:user_id>', methods=['PATCH'])
def patch_user(user_id):
    if user_id not in users_db:
        abort(404, description="User not found")
    data = request.get_json()
    if not data:
        abort(400, description="Request body is required")
    # Partial update - only update provided fields
    for key, value in data.items():
        if key in users_db[user_id]:
            users_db[user_id][key] = value
    return jsonify(users_db[user_id])

# New endpoint 2: Get user orders
@app.route('/api/v1/users/<int:user_id>/orders', methods=['GET'])
def get_user_orders(user_id):
    if user_id not in users_db:
        abort(404, description="User not found")
    user_orders = [order for order in orders_db.values() if order["user_id"] == user_id]
    return jsonify({"user_id": user_id, "orders": user_orders, "count": len(user_orders)})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
