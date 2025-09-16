import sqlite3
from flask import Flask, request, jsonify, render_template, g, send_file
from flask_cors import CORS
import pandas as pd
from datetime import datetime, timedelta
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from apscheduler.schedulers.background import BackgroundScheduler
from io import BytesIO

account_sid = 'ACc1d5924f326a59a4a5fa20c367b680eb'
auth_token = 'e5311612703a9e45c5a2ffaeea99ce4b'
client = Client(account_sid, auth_token) 

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, methods=["GET", "POST", "PUT", "DELETE"])

DATABASE = 'orders.db'
user_sessions = {}

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.start()

@app.route('/')
def home():
   return render_template('index.html')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.executescript(f.read())
        db.commit()

@app.route('/set_reminder', methods=['POST'])
def set_reminder():
    data = request.json
    manual_time = data.get("manual_time")
    auto_reminder = data.get("auto_reminder")
    
    scheduler.remove_all_jobs()

    if manual_time:
        reminder_time = datetime.strptime(manual_time, "%H:%M").time()
        now = datetime.now()
        first_run = datetime.combine(now.date(), reminder_time)
        if first_run < now:
            first_run += timedelta(days=1)

        scheduler.add_job(send_manual_reminder, 'interval', days=1, start_date=first_run)

    if auto_reminder:
        scheduler.add_job(send_auto_reminder, 'interval', hours=24)

    return jsonify({"message": "Reminder settings updated successfully"}), 200

def send_manual_reminder():
    client.messages.create(
        body="This is your reminder to deliver the orders!",
        from_='whatsapp:+14155238886',
        to='whatsapp:+819034208719'
    )

def send_auto_reminder():
    db = get_db()
    undelivered_orders = db.execute('SELECT * FROM orders WHERE status = "pending"').fetchall()

    if undelivered_orders:
        orders_text = "\n".join([f"{order['name']} - {order['order_detail']} x {order['quantity']}" for order in undelivered_orders])
        message_body = f"Reminder: You have undelivered orders:\n{orders_text}"
        
        client.messages.create(
            body=message_body,
            from_='whatsapp:+14155238886',
            to='whatsapp:+819034208719'
        )

@app.route("/export_xlsx", methods=["GET"])
def export_xlsx():
    db = get_db()
    orders = pd.read_sql_query("SELECT * FROM orders", db)
    file = "database.xlsx"
    orders.to_excel(file, index=False)
    return send_file(file, as_attachment=True)

@app.route("/export_csv", methods=["GET"])
def export_csv():
    db = get_db()
    orders = pd.read_sql_query("SELECT * FROM orders", db)
    return orders.to_csv(index=False)

@app.route("/import_csv", methods=["POST"])
def import_csv():
    file = request.files.get("file")
    if not file:
        return {"error": "No file uploaded"}, 400

    data = pd.read_csv(file)
    db = get_db()

    db.execute("DELETE FROM orders") 
    data.to_sql("orders", db, if_exists="append", index=False)
    db.commit()

    return {"success": "Data imported successfully"}, 200

@app.route("/orders", methods=['GET'])
def get_orders():
    db = get_db()
    orders = db.execute('SELECT * FROM orders ORDER BY id DESC').fetchall()
    return jsonify([dict(order) for order in orders])

@app.route("/orders", methods=['POST'])
def add_order():
    order = request.json
    
    phone = order.get('phone')
    local_number = phone[3:] 

    if not local_number.isdigit() or len(local_number) != 10:
        return jsonify({'error': 'Phone number must be exactly 10 digits'}), 400

    db = get_db()
    product = db.execute('SELECT * FROM products WHERE name = ?', (order['order_detail'],)).fetchone()
    if product is None:
        return jsonify({'error': 'Product not found'}), 404

    if product['stock'] < order['quantity']:
        return jsonify({'error': 'Out of stock'}), 400

    new_stock = product['stock'] - order['quantity']
    db.execute('UPDATE products SET stock = ? WHERE name = ?', (new_stock, order['order_detail']))

    db.execute(
        'INSERT INTO orders (time, name, phone, order_detail, status, quantity, price) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (order['time'], order['name'], phone, order['order_detail'], order['status'], order['quantity'], order['price'])
    )
    db.commit()
    return jsonify(order), 201

@app.route("/orders/<int:id>", methods=['PUT'])
def update_order(id):
    order = request.json
    db = get_db()

    phone = order.get('phone')
    local_number = phone[3:]

    if not local_number.isdigit() or len(local_number) != 10:
        return jsonify({'error': 'Phone number must be exactly 10 digits'}), 400

    existing_order = db.execute('SELECT * FROM orders WHERE id = ?', (id,)).fetchone()
    if existing_order is None:
        return jsonify({'error': 'Order not found'}), 404

    old_quantity = existing_order['quantity']
    new_quantity = order['quantity']
    quantity_difference = new_quantity - old_quantity

    product = db.execute('SELECT * FROM products WHERE name = ?', (order['order_detail'],)).fetchone()
    if product:
        new_stock = product['stock'] - quantity_difference
        if new_stock < 0:
            return jsonify({'error': 'Insufficient stock for this update'}), 400
        db.execute('UPDATE products SET stock = ? WHERE name = ?', (new_stock, order['order_detail']))

    db.execute(
        'UPDATE orders SET name = ?, phone = ?, order_detail = ?, status = ?, quantity = ?, price = ? WHERE id = ?',
        (order['name'], phone, order['order_detail'], order['status'], new_quantity, order['price'], id)
    )
    db.commit()
    return jsonify(order), 200

@app.route("/orders/<int:id>", methods=['DELETE'])
def delete_order(id):
    db = get_db()
    
    order = db.execute('SELECT order_detail, quantity FROM orders WHERE id = ?', (id,)).fetchone()
    if order:
        product = db.execute('SELECT stock FROM products WHERE name = ?', (order['order_detail'],)).fetchone()
        
        if product:
            updated_stock = product['stock'] + order['quantity']
            db.execute('UPDATE products SET stock = ? WHERE name = ?', (updated_stock, order['order_detail']))
    
    db.execute('DELETE FROM orders WHERE id = ?', (id,))
    db.commit()
    return '', 204

@app.route("/products", methods=['GET'])
def get_products():
    db = get_db()
    products = db.execute('SELECT * FROM products').fetchall()
    return jsonify([dict(product) for product in products])

@app.route("/products", methods=['POST'])
def add_product():
    product = request.json
    db = get_db()
    db.execute('INSERT INTO products (name, stock, price) VALUES (?, ?, ?)',
               (product['name'], product['stock'], product['price']))
    db.commit()
    return jsonify(product), 201

@app.route("/products/<int:id>", methods=['PUT'])
def edit_product(id):
    product = request.json
    db = get_db()
    db.execute('UPDATE products SET name = ?, stock = ?, price = ? WHERE id = ?',
               (product['name'], product['stock'], product['price'], id))
    db.commit()
    return jsonify(product), 200

@app.route("/products/<int:id>", methods=['DELETE'])
def delete_product(id):
    db = get_db()
    product = db.execute('SELECT name FROM products WHERE id = ?', (id,)).fetchone()
    if product:
        db.execute('DELETE FROM orders WHERE order_detail = ?', (product['name'],))
    db.execute('DELETE FROM products WHERE id = ?', (id,))
    db.commit()
    return '', 204

@app.route("/whatsapp", methods=['POST'])
def whatsapp():
    incoming_msg = request.values.get('Body', '').strip().lower()
    phone_number = request.values.get('From', '').replace('whatsapp:', '')  # Clean phone format with uncessary characters removed
    response = MessagingResponse()
    msg = response.message()

    owner_contact = "+819034208719"  
    
    try:
        if incoming_msg == "exit":
            msg.body("You've exited the order process. Type 'help' if you need assistance.")
            user_sessions.pop(phone_number, None)
            return str(response)

        if "help" in incoming_msg:
            msg.body(
                "Commands:\n"
                "1. 'add order' - Start a new order.\n"
                "2. 'list products' - View products.\n"
                "3. 'exit' - Exit order process.\n"
                "4. 'contact owner' - For queries or preferences.\n"
                "5. 'help' - List commands."
            )
            return str(response)

        elif "contact owner" in incoming_msg:
            msg.body(f"For queries or special requests, please reach out to the owner directly at {owner_contact}.")
            return str(response)

        elif "list products" in incoming_msg:
            products = get_products()
            product_list = "\n".join([f"{product['name']}: ¥{int(product['price'])}" for product in products.json]) if products else "No products are currently available."
            msg.body(f"Available products:\n{product_list}")
            return str(response)

        elif "add order" in incoming_msg:
            msg.body("Let's start your order! What's your name? Please use letters only.")
            user_sessions[phone_number] = {'step': 'get_name', 'cart': []}
            return str(response)

        elif phone_number in user_sessions and user_sessions[phone_number]['step'] == 'get_name':
            name = incoming_msg.capitalize()
            if not name.isalpha():
                msg.body("Invalid name. Please enter a valid name using letters only.")
                return str(response)

            user_sessions[phone_number]['name'] = name
            products = get_products()
            product_list = "\n".join([f"{product['name']}: ¥{int(product['price'])}" for product in products.json]) if products else "No products available."
            msg.body(f"Thank you, {name}! Here are our products:\n{product_list}\n\nType the product name you'd like to add to your cart.")
            user_sessions[phone_number]['step'] = 'select_product'
            return str(response)

        elif phone_number in user_sessions and user_sessions[phone_number]['step'] == 'select_product':
            product_name = incoming_msg.lower()
            db = get_db()
            product = db.execute('SELECT * FROM products WHERE LOWER(name) = ?', (product_name,)).fetchone()

            if not product:
                msg.body("Product not found. Please type a valid product name from the list.")
                return str(response)
            user_sessions[phone_number]['current_product'] = product['name']
            user_sessions[phone_number]['current_price'] = product['price']
            msg.body("Got it! How many units would you like? Please enter a number.")
            user_sessions[phone_number]['step'] = 'get_quantity'
            return str(response)

        elif phone_number in user_sessions and user_sessions[phone_number]['step'] == 'get_quantity':
            try:
                quantity = int(incoming_msg)
                if quantity <= 0:
                    raise ValueError("Quantity must be positive")

                cart = user_sessions[phone_number]['cart']
                cart.append({
                    'product': user_sessions[phone_number]['current_product'],
                    'quantity': quantity,
                    'price': user_sessions[phone_number]['current_price'] * quantity
                })

                cart_summary = "\n".join([f"{idx+1}. {item['product']} - {item['quantity']} units, ¥{int(item['price'])}" for idx, item in enumerate(cart)])
                msg.body(f"Your Cart:\n{cart_summary}\n\nType 'confirm' to place your order, 'add' to add another product, or 'edit' to change an item.")
                user_sessions[phone_number]['step'] = 'cart_action'
            except ValueError:
                msg.body("Please enter a valid numeric quantity.")
            return str(response)

        elif phone_number in user_sessions and user_sessions[phone_number]['step'] == 'cart_action':
            if "confirm" in incoming_msg:
                db = get_db()
                formatted_time = datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p")
                for item in user_sessions[phone_number]['cart']:
                    product = db.execute('SELECT * FROM products WHERE LOWER(name) = ?', (item['product'].lower(),)).fetchone()
                    new_stock = product['stock'] - item['quantity']
                    if new_stock < 0:
                        msg.body(f"Insufficient stock for {item['product']}. Please adjust your order.")
                        return str(response)
                    db.execute('UPDATE products SET stock = ? WHERE name = ?', (new_stock, product['name']))
                    db.execute(
                        'INSERT INTO orders (time, name, phone, order_detail, status, quantity, price) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (formatted_time, user_sessions[phone_number]['name'], phone_number, item['product'], 'pending', item['quantity'], item['price'])
                    )
                db.commit()
                msg.body(f"Order placed successfully for {user_sessions[phone_number]['name']}!")
                user_sessions.pop(phone_number)

            elif "add" in incoming_msg:
                products = get_products()
                product_list = "\n".join([f"{product['name']}: ¥{int(product['price'])}" for product in products.json]) if products else "No products available."
                msg.body(f"Here are the available products:\n{product_list}\n\nType the product name you'd like to add.")
                user_sessions[phone_number]['step'] = 'select_product'

            elif "edit" in incoming_msg:
                cart = user_sessions[phone_number]['cart']
                cart_summary = "\n".join([f"{idx+1}. {item['product']} - {item['quantity']} units" for idx, item in enumerate(cart)])
                msg.body(f"Your current cart:\n{cart_summary}\n\nReply with 'edit' followed by the item number to edit (e.g., 'edit 1') or 'delete' followed by the item number to remove (e.g., 'delete 1').")
                user_sessions[phone_number]['step'] = 'edit_item'
            else:
                msg.body("Invalid option. Please type 'confirm', 'add', or 'edit'.")
            return str(response)

        elif phone_number in user_sessions and user_sessions[phone_number]['step'] == 'edit_item':
            input_parts = incoming_msg.split()
            action = input_parts[0]
            try:
                item_number = int(input_parts[1]) - 1
                cart = user_sessions[phone_number]['cart']
                
                if item_number < 0 or item_number >= len(cart):
                    msg.body("Invalid item number. Please enter a correct item number to edit or delete.")
                    return str(response)

                if action == "delete":
                    deleted_item = cart.pop(item_number)
                    msg.body(f"{deleted_item['product']} has been removed from your cart.\n\nType 'confirm' to finalize your order or 'add' to add more items.")
                    user_sessions[phone_number]['step'] = 'cart_action'

                elif action == "edit":
                    user_sessions[phone_number]['edit_index'] = item_number
                    msg.body(f"Editing {cart[item_number]['product']}. Reply with the new quantity.")
                    user_sessions[phone_number]['step'] = 'edit_quantity'

                else:
                    msg.body("Please enter 'edit' or 'delete' followed by the item number.")
                
            except (ValueError, IndexError):
                msg.body("Invalid command. Please enter 'edit' or 'delete' followed by the item number.")
            return str(response)

        elif phone_number in user_sessions and user_sessions[phone_number]['step'] == 'edit_quantity':
            try:
                new_quantity = int(incoming_msg)
                if new_quantity <= 0:
                    raise ValueError("Quantity must be positive")

                edit_index = user_sessions[phone_number]['edit_index']
                cart_item = user_sessions[phone_number]['cart'][edit_index]
                cart_item['price'] = (cart_item['price'] / cart_item['quantity']) * new_quantity
                cart_item['quantity'] = new_quantity

                cart_summary = "\n".join([f"{idx+1}. {item['product']} - {item['quantity']} units, ¥{int(item['price'])}" for idx, item in enumerate(user_sessions[phone_number]['cart'])])
                msg.body(f"Quantity updated.\n\nYour Cart:\n{cart_summary}\n\nType 'confirm' to finalize your order, 'add' to add more items, or 'edit' to modify another item.")
                user_sessions[phone_number]['step'] = 'cart_action'
            except ValueError:
                msg.body("Please enter a valid quantity.")
            return str(response)

        else:
            msg.body("I didn't understand that command. Try typing 'help'.")
            return str(response)

    except Exception as e:
        print(f"Error: {e}")
        msg.body(f"An error occurred: {str(e)}")

    return str(response)


if __name__ == "__main__":
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
