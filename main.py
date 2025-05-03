from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import logging
import pymysql.cursors
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')  # Only use .env

# Secret key for session
app.secret_key = os.environ.get('SECRET_KEY')  # Consider using a stronger, environment-based secret key

# MySQL database configuration
db_config = {
    'host': os.environ.get('DB_HOST', 'fyp-2-fyp-2.f.aivencloud.com'),
    'user': os.environ.get('DB_USER', 'avnadmin'),
    'password': os.environ.get('DB_PASSWORD', 'AVNS_14oRr0YWlxnqJO_IQSy'),
    'database': os.environ.get('DB_NAME', 'fyp'),
    'port': int(os.environ.get('DB_PORT', 17738)) 
}

# Configure upload folders
UPLOAD_FOLDER = 'static/uploads'
EXERCISE_IMAGE_FOLDER = 'static/exercise_images'
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['EXERCISE_IMAGE_FOLDER'] = EXERCISE_IMAGE_FOLDER

# Create upload folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EXERCISE_IMAGE_FOLDER, exist_ok=True)

# Database connection helper
def get_db_connection():
    try:
        connection = pymysql.connect(**db_config)
        return connection
    except pymysql.MySQLError as e:
        logging.error(f"Database connection error: {e}")
        raise e

def allowed_video_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# User registration
@app.route('/register_now', methods=['POST'])
def register_now():
    try:
        name = request.form.get('name')
        age = request.form.get('age')
        gender = request.form.get('gender')
        role = request.form.get('role')

        if not all([name, age, gender, role]):
            return jsonify({"error": "All fields are required."}), 400

        connection = get_db_connection()
        cursor = connection.cursor()
        query = "INSERT INTO users (Name, Age, Gender, Role) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (name, int(age), gender, role))
        connection.commit()

        return render_template('ThankYou.html')

    except Exception as e:
        logging.error(f"Error during registration: {e}")
        return jsonify({"error": "An error occurred during registration."}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

# User login
@app.route('/login_now', methods=['POST'])
def login_now():
    try:
        name = request.form.get('name')
        role = request.form.get('role')
        password = request.form.get('password')

        connection = get_db_connection()
        cursor = connection.cursor()
        query = "SELECT * FROM users WHERE Name = %s AND Role = %s"
        cursor.execute(query, (name, role))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Invalid credentials. Please register."}), 403

        if role == 'Teacher' and password != "20Tumbler24$":
            return jsonify({"error": "Incorrect password. Please try again."}), 403

        session['UserID'] = user[0]
        session['Name'] = user[1]  # Store name in session
        session['Role'] = role  # Store role in session for later use
        return render_template('teacher_page.html' if role == 'Teacher' else 'student_page.html')

    except Exception as e:
        logging.error(f"Error during login: {e}")
        return jsonify({"error": "An error occurred during login."}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    files = request.files.getlist('file')
    topic_index = request.form.get('topic_index')
    user_id = session.get('UserID')
    if not user_id:
        return jsonify({"error": "User not logged in"}), 403
    file_urls = []
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        for file in files:
            if file and allowed_video_file(file.filename):
                filename = secure_filename(file.filename)

                # Check if the file already exists for this user and topic
                cursor.execute(
                    "SELECT FilePath FROM videos WHERE UserID = %s AND TopicIndex = %s AND FilePath LIKE %s",
                    (user_id, topic_index, f"%{filename}")
                )
                existing_file = cursor.fetchone()
                if existing_file:
                    continue  # Skip duplicate files for the same topic

                # Ensure filename is unique to prevent overwrites
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                unique_filename = f"{timestamp}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)

                # Save metadata to the database
                query = "INSERT INTO videos (UserID, TopicIndex, FilePath, UploadDate) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (user_id, topic_index, file_path, datetime.now()))
                connection.commit()
                file_urls.append(file_path)
        connection.close()
    except Exception as e:
        logging.error(f"Error saving video to database: {e}")
        return jsonify({"error": "An error occurred while uploading videos."}), 500

    return jsonify({"file_urls": file_urls})

@app.route('/delete_all', methods=['POST'])
def delete_all():
    topic_index = request.form.get('topic_index')
    user_id = session.get('UserID')

    if not user_id:
        return jsonify({"error": "User not logged in"}), 403

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        query = "SELECT FilePath FROM videos WHERE UserID = %s AND TopicIndex = %s"
        cursor.execute(query, (user_id, topic_index))
        videos = cursor.fetchall()

        for video in videos:
            file_path = video[0]
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError as e:
                    logging.error(f"Error deleting file {file_path}: {e}")
                    continue

        query = "DELETE FROM videos WHERE UserID = %s AND TopicIndex = %s"
        cursor.execute(query, (user_id, topic_index))
        connection.commit()
        return jsonify({"message": "All files deleted"})
    except Exception as e:
        logging.error(f"Error in delete_all: {e}")
        return jsonify({"error": "An error occurred while deleting files."}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

@app.route('/delete', methods=['POST'])
def delete():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        url = data.get('url')
        user_id = session.get('UserID')

        if not user_id:
            return jsonify({"error": "User not logged in"}), 403

        if os.path.exists(url):
            try:
                os.remove(url)
            except OSError as e:
                logging.error(f"Error deleting file {url}: {e}")
                return jsonify({"error": "Failed to delete file"}), 500

        connection = get_db_connection()
        cursor = connection.cursor()
        query = "DELETE FROM videos WHERE FilePath = %s AND UserID = %s"
        cursor.execute(query, (url, user_id))
        connection.commit()
        return jsonify({"message": "File deleted"})
    except Exception as e:
        logging.error(f"Error in delete: {e}")
        return jsonify({"error": "An error occurred while deleting the file."}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

@app.route('/get_uploaded_videos', methods=['GET'])
def get_uploaded_videos():
    topic_index = request.args.get('topic_index')
    user_id = session.get('UserID')

    if not user_id:
        return jsonify({"error": "User not logged in"}), 403

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        query = "SELECT FilePath FROM videos WHERE UserID = %s AND TopicIndex = %s"
        cursor.execute(query, (user_id, topic_index))
        videos = cursor.fetchall()
        file_urls = [video[0] for video in videos]
        return jsonify({"file_urls": file_urls})
    except Exception as e:
        logging.error(f"Error fetching videos: {e}")
        return jsonify({"error": "An error occurred while fetching videos."}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

# Exercise Management Endpoints
@app.route('/save_exercise', methods=['POST'])
def save_exercise():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        user_id = session.get('UserID')
        if not user_id:
            return jsonify({"error": "User not logged in"}), 403

        required_fields = ['topic_index', 'question', 'options', 'correct_option']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        if len(data['options']) != 4:
            return jsonify({"error": "Exactly 4 options are required"}), 400

        # Handle image upload if present
        image_path = ''
        if 'question_image' in data and data['question_image']:
            try:
                # Decode base64 image data
                image_data = data['question_image'].split(',')[1]  # Remove data:image/... prefix
                image_bytes = base64.b64decode(image_data)
                
                # Generate unique filename
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"exercise_{user_id}_{timestamp}.jpg"
                image_path = os.path.join(app.config['EXERCISE_IMAGE_FOLDER'], filename)
                
                # Save image to file system
                with open(image_path, 'wb') as f:
                    f.write(image_bytes)
            except Exception as e:
                logging.error(f"Error saving exercise image: {e}")
                return jsonify({"error": "Failed to save image"}), 500

        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO exercises 
                (UserID, TopicIndex, Question, QuestionImage, Option1, Option2, Option3, Option4, CorrectOption)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    user_id,
                    data['topic_index'],
                    data['question'],
                    image_path if image_path else '',
                    data['options'][0],
                    data['options'][1],
                    data['options'][2],
                    data['options'][3],
                    data['correct_option']
                )
            )
            connection.commit()
        return jsonify({"success": True, "message": "Exercise saved successfully"})

    except Exception as e:
        logging.error(f"Error saving exercise: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_exercises', methods=['GET'])
def get_exercises():
    try:
        user_id = session.get('UserID')
        if not user_id:
            return jsonify({"error": "User not logged in"}), 403

        topic_index = request.args.get('topic_index')
        if not topic_index:
            return jsonify({"error": "Topic index is required"}), 400

        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM exercises WHERE UserID = %s AND TopicIndex = %s",
                (user_id, topic_index)
            )
            exercises = cursor.fetchall()

        exercises_list = []
        for exercise in exercises:
            exercises_list.append({
                "exercise_id": exercise[0],
                "question": exercise[3],
                "question_image": exercise[4],
                "options": [exercise[5], exercise[6], exercise[7], exercise[8]],
                "correct_option": exercise[9]
            })

        return jsonify({"exercises": exercises_list})

    except Exception as e:
        logging.error(f"Error fetching exercises: {e}")
        return jsonify({"error": "An error occurred while fetching exercises."}), 500

@app.route('/delete_exercise', methods=['POST'])
def delete_exercise():
    try:
        user_id = session.get('UserID')
        if not user_id:
            return jsonify({"error": "User not logged in"}), 403

        data = request.get_json()
        if not data or 'exercise_id' not in data:
            return jsonify({"error": "Exercise ID is required"}), 400

        # First get the exercise to check for image
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # Get exercise info to delete associated image
            cursor.execute(
                "SELECT QuestionImage FROM exercises WHERE ExerciseID = %s AND UserID = %s",
                (data['exercise_id'], user_id)
            )
            exercise = cursor.fetchone()
            
            if exercise and exercise[0] and os.path.exists(exercise[0]):
                try:
                    os.remove(exercise[0])
                except OSError as e:
                    logging.error(f"Error deleting exercise image: {e}")

            # Now delete the exercise record
            cursor.execute(
                "DELETE FROM exercises WHERE ExerciseID = %s AND UserID = %s",
                (data['exercise_id'], user_id)
            )
            connection.commit()
        return jsonify({"message": "Exercise deleted successfully."})

    except Exception as e:
        logging.error(f"Error deleting exercise: {e}")
        return jsonify({"error": "An error occurred while deleting the exercise."}), 500

@app.route('/get_topic_videos', methods=['GET'])
def get_topic_videos():
    topic_index = request.args.get('topic_index')
    if not topic_index:
        return jsonify({"error": "Topic index is required"}), 400
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        # Get all videos for this topic along with teacher's name
        query = """
            SELECT v.FilePath, u.Name  
            FROM videos v
            JOIN users u ON v.UserID = u.UserID
            WHERE u.Role = 'Teacher' AND v.TopicIndex = %s
            ORDER BY v.UploadDate DESC
        """
        cursor.execute(query, (topic_index,))
        videos = cursor.fetchall()
        
        video_list = []
        for video in videos:
            video_list.append({
                "file_url": video[0],
                "teacher_name": video[1] or "Teacher"
            })

        return jsonify({"videos": video_list})
    except Exception as e:
        logging.error(f"Error fetching topic videos: {e}")
        return jsonify({"error": "An error occurred while fetching videos."}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

# Get all exercises for a topic (for students)
@app.route('/get_topic_exercises', methods=['GET'])
def get_topic_exercises():
    topic_index = request.args.get('topic_index')
    if not topic_index:
        return jsonify({"error": "Topic index is required"}), 400
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Get ALL exercises for this topic created by ANY teacher
        cursor.execute("""
            SELECT e.*, u.Name as teacher_name 
            FROM exercises e
            JOIN users u ON e.UserID = u.UserID
            WHERE u.Role = 'Teacher' AND e.TopicIndex = %s
        """, (topic_index,))

        exercises = cursor.fetchall()
        exercises_list = []
        for exercise in exercises:
            exercises_list.append({
                "exercise_id": exercise[0],
                "question": exercise[3],
                "question_image": exercise[4],
                "options": [exercise[5], exercise[6], exercise[7], exercise[8]],
                "correct_option": exercise[9],
                "teacher_name": exercise[10]
            })
        return jsonify({"exercises": exercises_list})
    except Exception as e:
        logging.error(f"Error fetching topic exercises: {e}")
        return jsonify({"error": "An error occurred while fetching exercises."}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals(): connection.close()

# Static routes
@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route('/AboutUs')
def AboutUs():
    return render_template('AboutUs.html')

@app.route('/Register')
def Register():
    return render_template('Register.html')

@app.route('/Login')
def Login():
    return render_template('Login.html')

@app.route('/TopicsOverview')
def TopicsOverview():
    return render_template('TopicsOverview.html')

@app.route('/ThankYou')
def ThankYou():
    return render_template('ThankYou.html')

@app.route('/teacher_page')
def teacher_page():
    if session.get('Role') != 'Teacher':
        return redirect(url_for('Login'))
    return render_template('teacher_page.html')

@app.route('/teacher_exercise_page')
def teacher_exercise_page():
    if session.get('Role') != 'Teacher':
        return redirect(url_for('Login'))
    return render_template('teacher_exercise_page.html')

@app.route('/student_page')
def student_page():
    if session.get('Role') != 'Student':
        return redirect(url_for('Login'))
    return render_template('student_page.html')

# Route to serve exercise images
@app.route('/exercise_images/<filename>')
def serve_exercise_image(filename):
    return send_from_directory(app.config['EXERCISE_IMAGE_FOLDER'], filename)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
