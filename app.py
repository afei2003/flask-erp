import pyodbc
from flask import Flask, render_template, request, redirect, url_for, flash
import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_development')

# --- Database Configuration ---
# Load from environment variables. These must be set in the environment.
DB_SERVER = os.environ.get('DB_SERVER')
DB_NAME = os.environ.get('DB_NAME')
DB_USERNAME = os.environ.get('DB_USERNAME')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_DRIVER = os.environ.get('DB_DRIVER', '{ODBC Driver 17 for SQL Server}') # Keep a default for the driver as it's less sensitive

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

@app.route('/orders')
def order_payments():
    """Displays a paginated list of order payment information, with search."""
    search_params = {
        'client': request.args.get('client', '').strip(),
        'short_name': request.args.get('short_name', '').strip(),
        'coid': request.args.get('coid', '').strip(),
        'start_date': request.args.get('start_date', '').strip(),
        'end_date': request.args.get('end_date', '').strip(),
    }

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    per_page = 20
    offset = (page - 1) * per_page

    conn = get_db_connection()
    orders = []
    total_orders = 0

    if conn:
        cursor = get_cursor(conn)

        # Base query
        base_query = "from v_step_pay_all"

        # Build WHERE clause
        where_conditions = []
        params = []

        if search_params['client']:
            where_conditions.append("client LIKE ?")
            params.append(f"%{search_params['client']}%")
        if search_params['short_name']:
            where_conditions.append("short_name LIKE ?")
            params.append(f"%{search_params['short_name']}%")
        if search_params['coid']:
            where_conditions.append("coid LIKE ?")
            params.append(f"%{search_params['coid']}%")
        if search_params['start_date']:
            where_conditions.append("updated_at >= ?")
            params.append(search_params['start_date'])
        if search_params['end_date']:
            # Add 1 day to end_date to make it inclusive
            # This is a simple approach; a more robust one would parse and add a day
            where_conditions.append("updated_at < dateadd(day, 1, ?)")
            params.append(search_params['end_date'])

        where_clause = ""
        if where_conditions:
            where_clause = " WHERE " + " AND ".join(where_conditions)

        # Get total count for pagination
        count_sql = f"SELECT COUNT(*) {base_query} {where_clause}"
        try:
            cursor.execute(count_sql, params)
            total_orders = cursor.fetchone()[0]
        except pyodbc.Error as e:
            flash(f"Error fetching order count: {e}", "danger")
            total_orders = 0

        # Get paginated results
        # Correcting the typo from the user's query: updated_byfrom -> updated_by from
        select_fields = "CONVERT(varchar, created_at, 23) as created_at, client, short_name, coid, order_id, name, model, packaging, quantity, unit_price, count_pass, count_neg, note, mini_total, discount, total_paid, pay_method, right (invoice_id, 5) as invoice_id, paid_at, updated_at, updated_by"

        paginated_sql = f"""
        SELECT {select_fields} {base_query} {where_clause}
        ORDER BY updated_at ASC
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        paginated_params = params + [offset, per_page]

        try:
            cursor.execute(paginated_sql, paginated_params)
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
            orders = [dict(zip(columns, row)) for row in rows]
        except pyodbc.Error as e:
            flash(f"Error fetching orders: {e}", "danger")
            orders = []

        conn.close()

    total_pages = (total_orders + per_page - 1) // per_page

    return render_template('order_payments.html',
                           orders=orders,
                           search_params=search_params,
                           page=page,
                           total_pages=total_pages)


# --- 4. App execution ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
