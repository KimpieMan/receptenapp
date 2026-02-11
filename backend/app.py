from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
import os
from datetime import datetime
from urllib.parse import quote_plus

app = Flask(__name__)
CORS(app)

# Verbeterde database connectie
def get_db_connection():
    try:
        # Haal environment variables op
        host = os.environ.get('DB_HOST')
        database = os.environ.get('DB_NAME', 'postgres')
        user = os.environ.get('DB_USER', 'postgres')
        password = os.environ.get('DB_PASSWORD')
        
        if not all([host, database, user, password]):
            print("Missing database environment variables")
            return None
            
        # Maak connectie string met SSL
        conn = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=5432,
            sslmode='require'
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

# Initialize database tables
def init_db():
    try:
        conn = get_db_connection()
        if not conn:
            print("Could not connect to database for initialization")
            return
            
        cur = conn.cursor()
        
        # Create recipes table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS recipes (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                ingredients TEXT,
                instructions TEXT,
                cooking_time INTEGER DEFAULT 0,
                servings INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create timers table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS timers (
                id SERIAL PRIMARY KEY,
                recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
                step_number INTEGER NOT NULL,
                step_description TEXT,
                duration_minutes INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")

# === API ENDPOINTS ===

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "ReceptenApp API is running!", "timestamp": datetime.now().isoformat()})

# Database test endpoint (voor debugging)
@app.route('/api/db-test', methods=['GET'])
def db_test():
    try:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute('SELECT version()')
            version = cur.fetchone()
            cur.close()
            conn.close()
            return jsonify({"status": "Connected", "version": version[0]})
        else:
            return jsonify({"status": "Failed", "error": "Could not create connection"}), 500
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)}), 500

# Get all recipes
@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cur = conn.cursor()
        cur.execute('SELECT * FROM recipes ORDER BY created_at DESC')
        recipes = cur.fetchall()
        cur.close()
        conn.close()
        
        recipe_list = []
        for recipe in recipes:
            recipe_list.append({
                "id": recipe[0],
                "title": recipe[1],
                "ingredients": recipe[2],
                "instructions": recipe[3],
                "cooking_time": recipe[4],
                "servings": recipe[5],
                "created_at": recipe[6].isoformat() if recipe[6] else None
            })
        
        return jsonify(recipe_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Add new recipe
@app.route('/api/recipes', methods=['POST'])
def add_recipe():
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO recipes (title, ingredients, instructions, cooking_time, servings)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            data['title'],
            data.get('ingredients', ''),
            data.get('instructions', ''),
            data.get('cooking_time', 0),
            data.get('servings', 1)
        ))
        
        recipe_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"message": "Recept toegevoegd", "recipe_id": recipe_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get specific recipe
@app.route('/api/recipes/<int:recipe_id>', methods=['GET'])
def get_recipe(recipe_id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cur = conn.cursor()
        cur.execute('SELECT * FROM recipes WHERE id = %s', (recipe_id,))
        recipe = cur.fetchone()
        
        if not recipe:
            return jsonify({"error": "Recept niet gevonden"}), 404
        
        # Get timers for this recipe
        cur.execute('SELECT * FROM timers WHERE recipe_id = %s ORDER BY step_number', (recipe_id,))
        timers = cur.fetchall()
        
        cur.close()
        conn.close()
        
        recipe_data = {
            "id": recipe[0],
            "title": recipe[1],
            "ingredients": recipe[2],
            "instructions": recipe[3],
            "cooking_time": recipe[4],
            "servings": recipe[5],
            "created_at": recipe[6].isoformat() if recipe[6] else None,
            "timers": []
        }
        
        for timer in timers:
            recipe_data["timers"].append({
                "id": timer[0],
                "step_number": timer[2],
                "step_description": timer[3],
                "duration_minutes": timer[4],
                "active": timer[5]
            })
        
        return jsonify(recipe_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Add timer
@app.route('/api/timers', methods=['POST'])
def add_timer():
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO timers (recipe_id, step_number, step_description, duration_minutes)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (
            data['recipe_id'],
            data['step_number'],
            data.get('step_description', ''),
            data['duration_minutes']
        ))
        
        timer_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"message": "Timer toegevoegd", "timer_id": timer_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Toggle timer active state
@app.route('/api/timers/<int:timer_id>/toggle', methods=['POST'])
def toggle_timer(timer_id):
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cur = conn.cursor()
        cur.execute('UPDATE timers SET active = NOT active WHERE id = %s RETURNING active', (timer_id,))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if result:
            return jsonify({"active": result[0]}), 200
        else:
            return jsonify({"error": "Timer niet gevonden"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
