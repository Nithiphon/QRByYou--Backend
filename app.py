from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import qrcode
from PIL import Image, ImageDraw
import io
import os
import base64
import re
from werkzeug.utils import secure_filename
import hashlib
from datetime import datetime

app = Flask(__name__)

# กำหนด CORS ให้รองรับ Vercel
CORS(app, resources={
    r"/*": {
        "origins": ["*"],  # ใน production ควรระบุ domain ของ Vercel
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# ตั้งค่าโฟลเดอร์สำหรับเก็บไฟล์
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'zip', 'rar', 'jpg', 'jpeg', 'png', 'gif', 'mp4', 'mp3'
}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


def allowed_file(filename):
    """ตรวจสอบว่าไฟล์ที่อัปโหลดเป็นประเภทที่อนุญาตหรือไม่"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def create_qr_with_logo(data, fg_color, bg_color, size, center_image_base64=None):
    """สร้าง QR Code พร้อมโลโก้ตรงกลาง"""
    
    # สร้าง QR Code พื้นฐาน
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # ใช้ H เพื่อให้รองรับโลโก้
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # สร้างภาพ QR
    img = qr.make_image(fill_color=fg_color, back_color=bg_color).convert('RGB')
    
    # ปรับขนาด
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    # ถ้ามีโลโก้ให้เพิ่มเข้าไป
    if center_image_base64:
        try:
            # แปลง base64 เป็นรูปภาพ
            logo_data = re.sub('^data:image/.+;base64,', '', center_image_base64)
            logo_bytes = base64.b64decode(logo_data)
            logo = Image.open(io.BytesIO(logo_bytes))
            
            # คำนวณขนาดโลโก้ (ประมาณ 20% ของ QR)
            logo_size = size // 5
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            
            # สร้างพื้นหลังสีขาวรอบโลโก้
            logo_bg = Image.new('RGB', (logo_size + 20, logo_size + 20), 'white')
            logo_bg_pos = ((logo_bg.size[0] - logo_size) // 2,
                          (logo_bg.size[1] - logo_size) // 2)
            
            # ถ้าโลโก้มี alpha channel ให้ใช้ paste แบบมี mask
            if logo.mode == 'RGBA':
                logo_bg.paste(logo, logo_bg_pos, logo)
            else:
                logo_bg.paste(logo, logo_bg_pos)
            
            # วางโลโก้ลงกลาง QR Code
            logo_pos = ((img.size[0] - logo_bg.size[0]) // 2,
                       (img.size[1] - logo_bg.size[1]) // 2)
            img.paste(logo_bg, logo_pos)
            
        except Exception as e:
            print(f"Error adding logo: {e}")
            # ถ้าเกิดข้อผิดพลาดก็ข้ามการเพิ่มโลโก้
            pass
    
    return img


@app.route('/health', methods=['GET'])
def health_check():
    """ตรวจสอบสถานะ Backend"""
    return jsonify({
        'status': 'ok',
        'message': 'Backend is running',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/generate', methods=['POST'])
def generate_qr():
    """สร้าง QR Code จากข้อความหรือ URL"""
    try:
        data = request.json
        text = data.get('text', '')
        fg = data.get('fg', '#000000')
        bg = data.get('bg', '#ffffff')
        size = data.get('size', 300)
        center_image = data.get('center_image', None)
        
        if not text:
            return jsonify({'error': 'กรุณากรอกข้อความ'}), 400
        
        # จำกัดขนาด
        size = max(200, min(size, 1000))
        
        # สร้าง QR Code
        img = create_qr_with_logo(text, fg, bg, size, center_image)
        
        # แปลงเป็น bytes เพื่อส่งกลับ
        img_io = io.BytesIO()
        img.save(img_io, 'PNG', quality=95)
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
        
    except Exception as e:
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500


@app.route('/upload', methods=['POST'])
def upload_file():
    """อัปโหลดไฟล์และเก็บไว้ในเซิร์ฟเวอร์"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'ไม่พบไฟล์'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'ประเภทไฟล์ไม่ถูกต้อง'}), 400
        
        # สร้างชื่อไฟล์ที่ปลอดภัย
        filename = secure_filename(file.filename)
        
        # เพิ่ม timestamp เพื่อป้องกันชื่อซ้ำ
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{name}_{timestamp}{ext}"
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        # สร้าง URL สำหรับดาวน์โหลด
        file_url = f"/download/{unique_filename}"
        
        return jsonify({
            'message': 'อัปโหลดสำเร็จ',
            'filename': unique_filename,
            'url': file_url,
            'size': os.path.getsize(filepath)
        })
        
    except Exception as e:
        return jsonify({'error': f'อัปโหลดไม่สำเร็จ: {str(e)}'}), 500


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """ดาวน์โหลดไฟล์ที่อัปโหลดไว้"""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({'error': 'ไม่พบไฟล์'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/generate-file-qr', methods=['POST'])
def generate_file_qr():
    """สร้าง QR Code สำหรับลิงก์ดาวน์โหลดไฟล์"""
    try:
        data = request.json
        file_url = data.get('file_url', '')
        fg = data.get('fg', '#000000')
        bg = data.get('bg', '#ffffff')
        size = data.get('size', 300)
        center_image = data.get('center_image', None)
        
        if not file_url:
            return jsonify({'error': 'ไม่พบ URL ไฟล์'}), 400
        
        # จำกัดขนาด
        size = max(200, min(size, 1000))
        
        # สร้าง QR Code
        img = create_qr_with_logo(file_url, fg, bg, size, center_image)
        
        # แปลงเป็น bytes
        img_io = io.BytesIO()
        img.save(img_io, 'PNG', quality=95)
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
        
    except Exception as e:
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500


@app.route('/scan-qr', methods=['POST'])
def scan_qr():
    """สแกน QR Code จากรูปภาพที่อัปโหลด"""
    try:
        data = request.json
        image_base64 = data.get('image', '')
        
        if not image_base64:
            return jsonify({'error': 'ไม่พบรูปภาพ'}), 400
        
        # แปลง base64 เป็นรูปภาพ
        image_data = re.sub('^data:image/.+;base64,', '', image_base64)
        image_bytes = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(image_bytes))
        
        # ใช้ pyzbar สแกน QR Code (ต้องติดตั้ง: pip install pyzbar)
        try:
            from pyzbar.pyzbar import decode
            decoded_objects = decode(img)
            
            if decoded_objects:
                results = []
                for obj in decoded_objects:
                    results.append({
                        'type': obj.type,
                        'data': obj.data.decode('utf-8'),
                        'quality': 'good'
                    })
                return jsonify({'results': results})
            else:
                return jsonify({'error': 'ไม่พบ QR Code ในรูปภาพ'}), 404
                
        except ImportError:
            return jsonify({
                'error': 'ฟีเจอร์ QR Scanner ต้องการ library pyzbar (ยังไม่ได้ติดตั้ง)'
            }), 501
            
    except Exception as e:
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500


if __name__ == '__main__':
    # ใช้ port จาก environment variable หรือ 5000 เป็น default
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)