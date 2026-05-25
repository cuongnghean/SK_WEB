# Hệ thống Tra cứu và Quản lý Nghĩa vụ Người Nộp Thuế

## Mục lục

1. [Giới thiệu](#giới-thiệu)
2. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
3. [Cài đặt](#cài-đặt)
4. [Cấu hình](#cấu-hình)
5. [Chạy ứng dụng](#chạy-ứng-dụng)
6. [Sử dụng Docker](#sử-dụng-docker)
7. [Khởi tạo dữ liệu](#khởi-tạo-dữ-liệu)
8. [API Endpoints](#api-endpoints)
9. [Cấu trúc dự án](#cấu-trúc-dự-án)

---

## Giới thiệu

Hệ thống Tra cứu và Quản lý Nghĩa vụ Người Nộp Thuế (Tax Obligation Management System) là một ứng dụng web hoàn chỉnh được xây dựng bằng Flask, thiết kế theo mô hình Kiến trúc Phân tầng (Layered Architecture).

### Tính năng chính

- **Tra cứu công khai**: Tìm kiếm thông tin người nộp thuế qua MST hoặc CCCD
- **Quản lý Admin**: Dashboard, nhập liệu Excel, quản lý người dùng
- **Bảo mật**: Rate limiting, CAPTCHA, masking dữ liệu nhạy cảm
- **Xử lý dữ liệu lớn**: Batch processing với thuật toán UPSERT thông minh
- **Giao diện**: AdminLTE 3 / Bootstrap 5 theo phong cách Tổng cục Thuế

---

## Yêu cầu hệ thống

- Python 3.12+
- PostgreSQL (Supabase Cloud)
- Docker & Docker Compose (tùy chọn)

### Python Dependencies

Xem file `requirements.txt`

---

## Cài đặt

### 1. Clone repository

```bash
git clone <repository-url>
cd SK_WEB
```

### 2. Tạo virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 4. Cấu hình môi trường

```bash
# Copy file cấu hình mẫu
cp .env.example .env

# Chỉnh sửa file .env với thông tin Supabase của bạn
```

---

## Cấu hình

### File `.env`

```env
# Database Configuration (Supabase)
DATABASE_URL=postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require

# Application Secret Keys
SECRET_KEY=your-super-secret-key-change-in-production
WTF_CSRF_SECRET_KEY=your-wtf-csrf-secret-key

# Application Settings
APP_ENV=production
DEBUG=False

# Admin Default Credentials
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
```

### Cấu hình Supabase Connection Pooling

Ứng dụng sử dụng SQLAlchemy với các thiết lập connection pooling tối ưu cho Supabase:

- `pool_size=10`
- `max_overflow=20`
- `pool_recycle=300`
- `pool_pre_ping=True`

---

## Chạy ứng dụng

### Development Mode

```bash
# Khởi tạo database và seed dữ liệu
flask init-db

# Chạy development server
flask run
# Hoặc
python app.py
```

### Production Mode

```bash
# Sử dụng Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 --threads 2 --timeout 120 app:app
```

### Docker Mode

```bash
# Build và chạy với Docker Compose
docker-compose up -d

# Xem logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## Khởi tạo dữ liệu

### Khởi tạo Database

```bash
flask init-db
```

Lệnh này sẽ:
1. Tạo tất cả các bảng trong database
2. Tạo 5 loại nợ mặc định
3. Tạo tài khoản admin: `admin / admin123`
4. Tạo 20 bản ghi NNT mẫu

### CLI Commands

```bash
# Khởi tạo database
flask init-db

# Seed dữ liệu mẫu
flask seed-db

# Tạo admin user mới
flask create-admin <username> <password>
```

---

## API Endpoints

### Public API

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `GET /api/public/search` | GET | Tra cứu NNT (cần CAPTCHA, rate limited) |
| `GET /captcha` | GET | Lấy hình CAPTCHA |
| `GET /health` | GET | Health check |

### Admin API

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `GET /admin/api/dashboard` | GET | Lấy dữ liệu dashboard |
| `POST /admin/api/import` | POST | Import Excel file |
| `GET /api/nnt/<mst>` | GET | Chi tiết NNT (raw data) |
| `PUT /api/nnt/<mst>` | PUT | Cập nhật NNT |
| `DELETE /api/nnt/<mst>` | DELETE | Xóa NNT |

### User API

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `GET /user/api/dashboard` | GET | Dashboard user |
| `GET /user/api/quick-search` | GET | Tra cứu nhanh |
| `PUT /user/api/profile` | PUT | Cập nhật profile |

---

## Cấu trúc dự án

```
SK_WEB/
├── app.py                 # Main application entry point
├── config.py             # Configuration module
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose file
├── database_seeder.py    # Database seeding script
│
├── models/               # Database models (Layer 1)
│   ├── __init__.py
│   ├── nnt.py           # Người nộp thuế
│   ├── users.py         # User authentication
│   ├── import_history.py
│   ├── no_history.py
│   └── search_log.py
│
├── services/             # Business logic (Layer 2)
│   ├── __init__.py
│   ├── excel_service.py # Excel import with UPSERT
│   └── tax_service.py   # Tax operations
│
├── routes/               # Routes & Controllers (Layer 3)
│   ├── __init__.py
│   ├── auth.py          # Authentication routes
│   ├── admin.py         # Admin routes
│   ├── public.py        # Public search routes
│   └── user.py          # User routes
│
├── utils/               # Utilities (Layer 4)
│   ├── __init__.py
│   ├── security.py      # Security utilities
│   └── captcha.py       # CAPTCHA generator
│
├── templates/            # Jinja2 templates
│   ├── base.html
│   ├── public_search.html
│   ├── admin_dashboard.html
│   ├── user_dashboard.html
│   ├── admin_import.html
│   └── ...
│
└── static/               # Static files
    ├── css/custom.css
    └── js/app.js
```

---

## Bảo mật

### Rate Limiting

- Public API: 20 requests/phút/IP
- Admin API: 200 requests/ngày, 50 requests/giờ

### Data Masking

- CCCD: Hiển thị 4 ký tự cuối (VD: `********1234`)
- CMT: Không hiển thị trong tra cứu công khai

### Authentication

- Flask-Login với bcrypt password hashing
- CSRF protection
- Session security (HTTPOnly, Secure, SameSite)

---

## Xử lý Excel Import

### Thuật toán UPSERT

1. Đọc tất cả MST hiện có vào memory set
2. Phân loại rows: Insert vs Update
3. Bulk insert/update để giảm database queries
4. Ghi log biến động nợ vào `no_history`

### Batch Processing

- Chunk size: 1000 rows
- Batch size: 5000 rows
- Nested transaction cho mỗi batch

---

## License

Copyright © 2026 Tổng cục Thuế Việt Nam
