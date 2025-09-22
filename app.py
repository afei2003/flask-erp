import pyodbc
from flask import Flask, render_template, request, redirect, url_for, flash
import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_development')

# --- Database Configuration ---
# Load from environment variables with default values for development
DB_SERVER = os.environ.get('DB_SERVER', '192.168.100.100,2025')
DB_NAME = os.environ.get('DB_NAME', 'secLab')
DB_USERNAME = os.environ.get('DB_USERNAME', 'sa')
DB_PASSWORD = os.environ.get('DB_PASSWORD') # No default for password
DB_DRIVER = os.environ.get('DB_DRIVER', '{ODBC Driver 17 for SQL Server}')

def get_db_connection():
    """Creates and returns a connection to the SQL Server database."""
    try:
        conn_str = (
            f"DRIVER={DB_DRIVER};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"UID={DB_USERNAME};"
            f"PWD={DB_PASSWORD};"
        )
        # Add a timeout to prevent hanging
        conn = pyodbc.connect(conn_str, timeout=10)
        return conn
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        print(f"Database Connection Error: {sqlstate}")
        print(ex)
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_cursor(conn):
    """Returns a cursor from a database connection."""
    if conn:
        return conn.cursor()
    return None

# --- Table of Contents ---
# 1. Database Initialization
# 2. Main Routes (CRUD)
# 3. Helper functions
# 4. App execution

# --- 1. Database Initialization ---
def create_customers_table():
    """Creates the 'customers' table if it does not already exist."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            table_check_query = "IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='customers' and xtype='U') CREATE TABLE customers (...)"

            # More robust check
            cursor.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'customers'")
            if cursor.fetchone()[0] == 0:
                print("Creating 'customers' table...")
                create_table_query = """
                CREATE TABLE customers (
                    id INT PRIMARY KEY IDENTITY(1,1),
                    coid NVARCHAR(50) NOT NULL,
                    company_name NVARCHAR(255) NOT NULL,
                    short_name NVARCHAR(100),
                    contact_person NVARCHAR(255),
                    phone NVARCHAR(50),
                    email NVARCHAR(255),
                    address_line1 NVARCHAR(255),
                    address_line2 NVARCHAR(255),
                    city NVARCHAR(100),
                    state NVARCHAR(100),
                    postal_code NVARCHAR(20),
                    country NVARCHAR(100),
                    is_active BIT DEFAULT 1,
                    date_created DATETIME DEFAULT GETDATE(),
                    date_updated DATETIME DEFAULT GETDATE()
                );
                """
                cursor.execute(create_table_query)
                conn.commit()
                print("'customers' table created successfully.")
            else:
                print("'customers' table already exists.")
        except pyodbc.Error as e:
            print(f"Error creating table: {e}")
        finally:
            conn.close()

# --- 2. Main Routes (CRUD) ---

@app.route('/')
def index():
    """Displays a paginated list of all customers, with search."""
    search_term = request.args.get('search', '').strip()
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    per_page = 20
    offset = (page - 1) * per_page

    conn = get_db_connection()
    customers = []
    total_customers = 0

    if conn:
        cursor = get_cursor(conn)

        # Base query and params for filtering
        where_clause = ""
        params = []
        if search_term:
            where_clause = """
            WHERE company_name LIKE ?
               OR short_name LIKE ?
               OR contact_person LIKE ?
               OR email LIKE ?
               OR coid LIKE ?
            """
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern] * 5)

        # Get total count for pagination
        count_sql = f"SELECT COUNT(*) FROM customers {where_clause}"
        cursor.execute(count_sql, params)
        total_customers = cursor.fetchone()[0]

        # Get paginated results
        sql_query = f"""
        SELECT * FROM customers
        {where_clause}
        ORDER BY company_name
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        paginated_params = params + [offset, per_page]
        cursor.execute(sql_query, paginated_params)

        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]
        customers = [dict(zip(columns, row)) for row in rows]
        conn.close()

    total_pages = (total_customers + per_page - 1) // per_page

    return render_template('index.html', customers=customers, search_term=search_term,
                           page=page, total_pages=total_pages)

@app.route('/add', methods=['GET', 'POST'])
def add_customer():
    """Handles adding a new customer."""
    if request.method == 'POST':
        # Get form data
        is_active = 1 if 'is_active' in request.form else 0

        conn = get_db_connection()
        if conn:
            try:
                cursor = get_cursor(conn)
                sql = """
                INSERT INTO customers (coid, company_name, short_name, contact_person, phone, email,
                                     address_line1, address_line2, city, state, postal_code, country, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                params = (
                    request.form['coid'], request.form['company_name'], request.form.get('short_name'),
                    request.form.get('contact_person'), request.form.get('phone'), request.form.get('email'),
                    request.form.get('address_line1'), request.form.get('address_line2'), request.form.get('city'),
                    request.form.get('state'), request.form.get('postal_code'), request.form.get('country'), is_active
                )
                cursor.execute(sql, params)
                conn.commit()
                flash('Customer added successfully!', 'success')
            except pyodbc.Error as e:
                flash(f'Error adding customer: {e}', 'danger')
            finally:
                conn.close()
        else:
            flash('Could not connect to the database.', 'danger')
        return redirect(url_for('index'))

    return render_template('add_customer.html')

@app.route('/edit/<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    """Handles editing an existing customer."""
    conn = get_db_connection()
    customer = None
    if conn:
        cursor = get_cursor(conn)
        cursor.execute("SELECT * FROM customers WHERE id = ?", customer_id)
        row = cursor.fetchone()
        if row:
            columns = [column[0] for column in cursor.description]
            customer = dict(zip(columns, row))

        if request.method == 'POST':
            if customer:
                is_active = 1 if 'is_active' in request.form else 0
                date_updated = datetime.datetime.now()

                sql = """
                UPDATE customers SET
                    coid = ?, company_name = ?, short_name = ?, contact_person = ?, phone = ?, email = ?,
                    address_line1 = ?, address_line2 = ?, city = ?, state = ?, postal_code = ?, country = ?,
                    is_active = ?, date_updated = ?
                WHERE id = ?
                """
                params = (
                    request.form['coid'], request.form['company_name'], request.form.get('short_name'),
                    request.form.get('contact_person'), request.form.get('phone'), request.form.get('email'),
                    request.form.get('address_line1'), request.form.get('address_line2'), request.form.get('city'),
                    request.form.get('state'), request.form.get('postal_code'), request.form.get('country'),
                    is_active, date_updated, customer_id
                )
                try:
                    cursor.execute(sql, params)
                    conn.commit()
                    flash('Customer updated successfully!', 'success')
                except pyodbc.Error as e:
                    flash(f'Error updating customer: {e}', 'danger')

                return redirect(url_for('index'))

        conn.close() # Close connection after GET or after POST fails before render
        if customer:
            return render_template('edit_customer.html', customer=customer)

    flash('Customer not found or could not connect to DB.', 'danger')
    return redirect(url_for('index'))


@app.route('/delete/<int:customer_id>', methods=['POST'])
def delete_customer(customer_id):
    """Handles deleting a customer."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = get_cursor(conn)
            cursor.execute("DELETE FROM customers WHERE id = ?", customer_id)
            conn.commit()
            flash('Customer deleted successfully!', 'success')
        except pyodbc.Error as e:
            flash(f'Error deleting customer: {e}', 'danger')
        finally:
            conn.close()
    else:
        flash('Could not connect to the database.', 'danger')

    return redirect(url_for('index'))

# --- 4. App execution ---
if __name__ == '__main__':
    with app.app_context():
        create_customers_table()
    app.run(debug=True, host='0.0.0.0', port=5000)
