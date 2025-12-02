#!/usr/bin/env python3
from flask import Flask, jsonify, request, abort
from datetime import datetime

app = Flask(__name__)

orders_db = {
    1: {"id": 1, "customer": "John Doe", "total": 150.50, "status": "pending"},
    2: {"id": 2, "customer": "Jane Smith", "total": 75.25, "status": "completed"},
    3: {"id": 3, "customer": "Bob Johnson", "total": 200.00, "status": "processing"}
}

inventory_db = {
    1: {"id": 1, "item": "Widget A", "quantity": 100, "location": "Warehouse 1"},
    2: {"id": 2, "item": "Widget B", "quantity": 50, "location": "Warehouse 2"},
    3: {"id": 3, "item": "Widget C", "quantity": 200, "location": "Warehouse 1"}
}

@app.route('/')
def health():
    return jsonify({"status": "healthy", "service": "order-service", "timestamp": datetime.utcnow().isoformat() + "Z"})

@app.route('/api/v2/orders', methods=['GET'])
def get_orders():
    return jsonify({"orders": list(orders_db.values()), "count": len(orders_db)})

@app.route('/api/v2/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    if order_id not in orders_db:
        abort(404, description="Order not found")
    return jsonify(orders_db[order_id])

@app.route('/api/v2/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'customer' not in data or 'total' not in data:
        abort(400, description="Customer and total are required")
    new_id = max(orders_db.keys()) + 1 if orders_db else 1
    new_order = {"id": new_id, "customer": data["customer"], "total": data["total"], "status": data.get("status", "pending")}
    orders_db[new_id] = new_order
    return jsonify(new_order), 201

@app.route('/api/v2/orders/<int:order_id>', methods=['PUT'])
def update_order(order_id):
    if order_id not in orders_db:
        abort(404, description="Order not found")
    data = request.get_json()
    if data:
        orders_db[order_id].update(data)
    return jsonify(orders_db[order_id])

@app.route('/api/v2/orders/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    if order_id not in orders_db:
        abort(404, description="Order not found")
    deleted_order = orders_db.pop(order_id)
    return jsonify({"message": "Order deleted", "order": deleted_order}), 200

@app.route('/api/v2/inventory', methods=['GET'])
def get_inventory():
    return jsonify({"inventory": list(inventory_db.values()), "count": len(inventory_db)})

@app.route('/api/v2/inventory/<int:item_id>', methods=['GET'])
def get_inventory_item(item_id):
    if item_id not in inventory_db:
        abort(404, description="Inventory item not found")
    return jsonify(inventory_db[item_id])

@app.route('/api/v2/inventory', methods=['POST'])
def create_inventory_item():
    data = request.get_json()
    if not data or 'item' not in data:
        abort(400, description="Item name is required")
    new_id = max(inventory_db.keys()) + 1 if inventory_db else 1
    new_item = {"id": new_id, "item": data.get("item"), "quantity": data.get("quantity", 0), "location": data.get("location", "Unknown")}
    inventory_db[new_id] = new_item
    return jsonify(new_item), 201

@app.route('/api/v2/reports/sales', methods=['GET'])
def get_sales_report():
    total_sales = sum(order["total"] for order in orders_db.values() if order["status"] == "completed")
    pending_orders = len([o for o in orders_db.values() if o["status"] == "pending"])
    return jsonify({"total_sales": total_sales, "pending_orders": pending_orders, "total_orders": len(orders_db)})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

