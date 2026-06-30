from flask import Flask, render_template, redirect, url_for, session, flash, request
from flask_wtf import FlaskForm
from wtforms import StringField,PasswordField,SubmitField
from wtforms.validators import DataRequired, Email, ValidationError
import string
import random
from flask_mysqldb import MySQL
import MySQLdb 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
load_dotenv()
import os 

SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))
SMTP_EMAIL = os.getenv('SMTP_EMAIL')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')

app = Flask(__name__)

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.secret_key = os.getenv('SECRET_KEY')
mysql = MySQL(app)

class LoginForm(FlaskForm):
    email = StringField("Email",validators=[DataRequired(), Email()])
    password = PasswordField("Password",validators=[DataRequired()])
    submit = SubmitField("Login")

def generate_password(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def send_email(to_email, subject, html_content):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(html_content, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())

        print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Email sending failed to {to_email}: {e}")


@app.route('/usermaster', methods=['GET', 'POST'])
def usermaster():
    if 'id' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        password = generate_password()

        try:
            cursor.execute(
                "INSERT INTO users (name, emailid, password, role) VALUES (%s, %s, %s, %s)",
                (name, email, password, role)
            )
            mysql.connection.commit()
            # flash(f"User {name} created successfully with password: {password}", "success")
            
            subject = "Your Account Has Been Created"
            html_content = f"""
            <h3>Welcome, {name}!</h3>
            <p>Your account has been created successfully.</p>
            <p><b>Email:</b> {email}</p>
            <p><b>Password:</b> {password}</p>
            <p>Please keep this information secure.</p>
            """

            # Send email
            send_email(email, subject, html_content)
            flash('User created and credentials emailed successfully', 'success')


        except MySQLdb.IntegrityError as e:
            if e.args[0] == 1062:
                flash("❌ This email ID already exists. Please use a different one.", "danger")
            else:
                flash("⚠️ An error occurred while creating the user.", "danger")

    # Fetch users list
    cursor.execute("SELECT id, name, emailid, role, password, created_at FROM users")
    users = cursor.fetchall()
    cursor.close()

    return render_template('usermaster.html', users=users)


@app.route('/usermaster/delete/<int:id>', methods=['POST'])
def delete_user(id):
    if 'id' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s", (id,))
    mysql.connection.commit()
    cursor.close()
    flash("User deleted successfully", "success")
    return redirect(url_for('usermaster'))


@app.route('/usermaster/edit/<int:id>', methods=['POST'])
def edit_user(id):
    if 'id' not in session:
        return redirect(url_for('login'))

    name = request.form.get('edit_name')
    email = request.form.get('edit_email')
    role = request.form.get('edit_role')

    cursor = mysql.connection.cursor()
    cursor.execute(
        "UPDATE users SET name=%s, emailid=%s, role=%s WHERE id=%s",
        (name, email, role, id)
    )
    mysql.connection.commit()
    cursor.close()
    flash("User updated successfully", "success")
    return redirect(url_for('usermaster'))


# change route to login
@app.route('/', methods=['GET', 'POST'])   
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE emailid = %s", (email,))
        user = cursor.fetchone()
        cursor.close()

        if user and password == user[3]:
            session['id'] = user[0]
            return redirect(url_for('dashboard'))
        else:
            flash("Login failed. Please check your email and password", "danger")
            return redirect(url_for('login'))

    return render_template('login.html', form=form)


@app.route('/dashboard')
def dashboard():
    if 'id' in session:
        id = session['id']
        cursor = mysql.connection.cursor()
        
        # Get user info
        cursor.execute("SELECT * FROM users where id=%s",(id,))
        user = cursor.fetchone()

        # 1. Get Ticket Status Counts for Pie Chart
        cursor.execute("SELECT ticket_status, COUNT(*) FROM tickets GROUP BY ticket_status")
        status_data = cursor.fetchall()
        # Format: {'Open': 5, 'Closed': 10...}
        status_counts = {status: count for status, count in status_data}

        # 2. Get Total Tickets Count
        cursor.execute("SELECT COUNT(*) FROM tickets")
        total_tickets = cursor.fetchone()[0]

        cursor.close()

        if user:
            return render_template('dashboard.html', 
                                 user=user, 
                                 status_counts=status_counts, 
                                 total_tickets=total_tickets)
            
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('id', None)
    flash("You have been logged out successfully.")
    return redirect(url_for('login'))

@app.route('/create_tickets', methods=['GET', 'POST'])
def create_tickets():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        problem_desc = request.form['problem_desc']
        priority = request.form['priority']  # BUG: this field doesn't exist in the HTML form!

        if len(problem_desc) > 255:
            flash("Problem description is too long (max 255 characters).", "danger")
            return redirect('/create_tickets')

        cursor = mysql.connection.cursor()

        cursor.execute("SELECT id FROM users WHERE name = %s AND emailid = %s", (name, email))
        user = cursor.fetchone()

        if not user:
            flash("User not found! Please enter valid details.", "danger")
            return redirect('/create_tickets')

        user_id = user[0]

        cursor.execute("""
            INSERT INTO tickets (ticket_status, user_id, problem_desc)
            VALUES (%s, %s, %s)
        """, ("Open", user_id, problem_desc))

        mysql.connection.commit()
        cursor.close()

        flash("Ticket created successfully!", "success")
        return redirect('/create_tickets')

    return render_template('create_tickets.html')


@app.route('/ticket_lists', methods=['GET', 'POST'])
def ticket_lists():
    if 'id' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Fetch ticket lists
    cursor.execute("SELECT * FROM tickets")
    tickets = cursor.fetchall()
    cursor.close()

    return render_template('ticket_lists.html', tickets=tickets)

@app.route('/ticket_lists/delete/<int:ticket_id>', methods=['POST'])
def delete_ticket(ticket_id):
    if 'id' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM tickets WHERE ticket_id = %s", (ticket_id,))
    mysql.connection.commit()
    cursor.close()
    flash("Ticket deleted successfully", "success")
    return redirect(url_for('ticket_lists'))


@app.route('/ticket_lists/edit/<int:ticket_id>', methods=['POST'])
def edit_ticket(ticket_id):
    assigned_dt = request.form['edit_assigned_dt']
    solution_dt = request.form['edit_solution_dt']
    completed_dt = request.form['edit_completed_dt']
    closed_dt = request.form['edit_closed_dt']
    solution_desc = request.form['edit_solution_desc']
    ticket_status = request.form['edit_ticket_status']

    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE tickets 
        SET assigned_dt=%s, solution_dt=%s, completed_dt=%s, closed_dt=%s, 
            solution_desc=%s, ticket_status=%s
        WHERE ticket_id=%s
    """, (assigned_dt, solution_dt, completed_dt, closed_dt, solution_desc, ticket_status, ticket_id))

    mysql.connection.commit()
    cursor.close()
    flash("Ticket updated successfully!", "success")
    return redirect('/ticket_lists')


@app.route('/productmaster', methods=['GET', 'POST'])
def productmaster():
    if 'id' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        prod_name = request.form.get('prod_name')
        dop = request.form.get('dop')
        wsd = request.form.get('wsd')
        wed = request.form.get('wed')

        try:
            cursor.execute(
                "INSERT INTO product_master (prod_name, dop, wsd, wed) VALUES (%s, %s, %s, %s)",
                (prod_name, dop, wsd, wed)
            )
            mysql.connection.commit()
            flash(f"✅ Product '{prod_name}' added successfully.", "success")
        except MySQLdb.IntegrityError:
            flash("⚠️ An error occurred while adding the product.", "danger")

    # Fetch all products
    cursor.execute("SELECT prod_ID, prod_name, dop, wsd, wed FROM product_master")
    products = cursor.fetchall()
    cursor.close()

    return render_template('productmaster.html', products=products)


@app.route('/productmaster/delete/<int:prod_ID>', methods=['POST'])
def delete_product(prod_ID):
    if 'id' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM product_master WHERE prod_ID = %s", (prod_ID,))
    mysql.connection.commit()
    cursor.close()
    flash("🗑️ Product deleted successfully.", "success")
    return redirect(url_for('productmaster'))


@app.route('/productmaster/edit/<int:prod_ID>', methods=['POST'])
def edit_product(prod_ID):
    if 'id' not in session:
        return redirect(url_for('login'))

    prod_name = request.form.get('edit_prod_name')
    dop = request.form.get('edit_dop')
    wsd = request.form.get('edit_wsd')
    wed = request.form.get('edit_wed')

    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE product_master 
        SET prod_name=%s, dop=%s, wsd=%s, wed=%s 
        WHERE prod_ID=%s
    """, (prod_name, dop, wsd, wed, prod_ID))
    mysql.connection.commit()
    cursor.close()
    flash("✏️ Product updated successfully.", "success")
    return redirect(url_for('productmaster'))


if __name__ == '__main__':
    app.run(debug=True)