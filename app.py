# app.py
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import qrcode
import io
import os
from PIL import Image, ImageDraw
import uuid
from datetime import datetime
import base64
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'zip', 'rar'}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 10MB

# Create upload folder if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/generate', methods=['POST'])
def generate_qr():
    try:
        data = request.json.get('text', '').strip()
        fg_color = request.json.get('fg', '#000000')
        bg_color = request.json.get('bg', '#ffffff')
        center_image = request.json.get('center_image', None)  # base64 image
        size = int(request.json.get('size', 250))
        pattern = request.json.get('pattern', 'square')  # square, rounded, circular
        
        if not data:
            return {"error": "กรุณากรอกข้อความหรือลิงก์!"}, 400

        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Higher error correction for overlay
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color=fg_color, back_color=bg_color)
        img = img.convert('RGB')
        
        # Resize to requested size
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        # Add center image if provided
        if center_image:
            try:
                # Decode base64 image
                center_data = center_image.split(',')[1] if ',' in center_image else center_image
                center_img_bytes = base64.b64decode(center_data)
                center_img = Image.open(io.BytesIO(center_img_bytes))
                center_img = center_img.convert('RGBA')
                
                # Resize center image to 25% of QR size
                center_size = int(size * 0.25)
                center_img = center_img.resize((center_size, center_size), Image.Resampling.LANCZOS)
                
                # Create circular mask for center image
                mask = Image.new('L', (center_size, center_size), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse([0, 0, center_size, center_size], fill=255)
                
                # Apply circular mask
                center_img.putalpha(mask)
                
                # Paste center image
                paste_x = (size - center_size) // 2
                paste_y = (size - center_size) // 2
                img = img.convert('RGBA')
                img.paste(center_img, (paste_x, paste_y), center_img)
                img = img.convert('RGB')
                
            except Exception as e:
                print(f"Error adding center image: {e}")

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)

        return send_file(img_io, mimetype='image/png')

    except Exception as e:
        return {"error": "เกิดข้อผิดพลาด: " + str(e)}, 500

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return {"error": "ไม่พบไฟล์"}, 400
        
        file = request.files['file']
        
        if file.filename == '':
            return {"error": "กรุณาเลือกไฟล์"}, 400
        
        if not allowed_file(file.filename):
            return {"error": "ประเภทไฟล์ไม่รองรับ"}, 400
        
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        file_ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{unique_id}.{file_ext}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save file
        file.save(filepath)
        
        # Check file size
        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            os.remove(filepath)
            return {"error": "ขนาดไฟล์ใหญ่เกินไป (ไม่เกิน 10MB)"}, 400
        
        # Return file info
        return jsonify({
            "success": True,
            "filename": filename,
            "file_id": unique_id,
            "size": file_size,
            "url": f"/files/{unique_filename}"
        })
        
    except Exception as e:
        return {"error": "เกิดข้อผิดพลาด: " + str(e)}, 500

@app.route('/files/<filename>', methods=['GET'])
def serve_file(filename):
    try:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            return send_file(filepath)
        else:
            return {"error": "ไม่พบไฟล์"}, 404
    except Exception as e:
        return {"error": "เกิดข้อผิดพลาด: " + str(e)}, 500

@app.route('/generate-file-qr', methods=['POST'])
def generate_file_qr():
    try:
        file_url = request.json.get('file_url', '')
        
        if not file_url:
            return {"error": "กรุณาระบุ URL ของไฟล์"}, 400
        
        # Optional customization
        fg_color = request.json.get('fg', '#000000')
        bg_color = request.json.get('bg', '#ffffff')
        size = int(request.json.get('size', 250))
        center_image = request.json.get('center_image', None)
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(file_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color=fg_color, back_color=bg_color)
        img = img.convert('RGB')
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        # Add center image if provided
        if center_image:
            try:
                center_data = center_image.split(',')[1] if ',' in center_image else center_image
                center_img_bytes = base64.b64decode(center_data)
                center_img = Image.open(io.BytesIO(center_img_bytes))
                center_img = center_img.convert('RGBA')
                
                center_size = int(size * 0.25)
                center_img = center_img.resize((center_size, center_size), Image.Resampling.LANCZOS)
                
                mask = Image.new('L', (center_size, center_size), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse([0, 0, center_size, center_size], fill=255)
                
                center_img.putalpha(mask)
                
                paste_x = (size - center_size) // 2
                paste_y = (size - center_size) // 2
                img = img.convert('RGBA')
                img.paste(center_img, (paste_x, paste_y), center_img)
                img = img.convert('RGB')
                
            except Exception as e:
                print(f"Error adding center image: {e}")

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)

        return send_file(img_io, mimetype='image/png')

    except Exception as e:
        return {"error": "เกิดข้อผิดพลาด: " + str(e)}, 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)